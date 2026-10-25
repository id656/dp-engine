# -*- coding: utf-8 -*-
"""PORTFOLIO Студия — настольное приложение бюро PORTFOLIO для Windows.

Три режима работы:
  1. IFC из планов и визуализаций / референсов;
  2. Альбом рабочих чертежей из IFC (+ референсы, рендеры);
  3. Дизайн-проект из планов и референсов (полный комплект движком dp-engine).

На каждый запрос открывается НОВАЯ сессия Claude (Claude Code в режиме без интерфейса, вход — вашей
подпиской Claude). Сессия работает в отдельной папке задания с копией движка dp-engine и навыком
«dizain-proekt-kvartiry», а в приложение возвращается только результат: папка «РЕЗУЛЬТАТ» с файлами
и короткий отчёт (решения + список вопросов и допущений).

Зависимости приложения: только стандартная библиотека Python 3.10+.
"""
import datetime as _dt
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import zipfile

APP_NAME = 'PORTFOLIO Студия'
APP_VER = '1.0'

# ---------------------------------------------------------------- пути и настройки
def app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'PortfolioStudio')
    os.makedirs(d, exist_ok=True)
    return d


SETTINGS_FILE = os.path.join(data_dir(), 'settings.json')
def repo_dir():
    """Корень клона репозитория dp-engine (приложение лежит в его папке studio/)."""
    up = os.path.dirname(app_dir())
    return up if os.path.exists(os.path.join(up, 'build.py')) else app_dir()


GITHUB_REPO = 'https://github.com/id656/dp-engine.git'

DEFAULTS = {
    'engine_zip': repo_dir(),
    'auto_update': True,
    'claude_exe': 'claude',
    'model': 'opus',
    'jobs_dir': os.path.join(os.path.expanduser('~'), 'Documents', 'PORTFOLIO Студия'),
    'max_parallel': 2,
    'extra_rules': '',
    'open_result': True,
}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- режимы и запросы
MODES = {
    'ifc': {
        'title': 'IFC из планов и визуализаций',
        'hint': 'Обмерный план / планировка (PDF, DXF, скан) + визуализации или референсы.',
        'need': ('Планы',),
    },
    'album': {
        'title': 'Альбом чертежей из IFC',
        'hint': 'IFC-модель квартиры + рендеры или референсы.',
        'need': ('IFC',),
    },
    'dp': {
        'title': 'Дизайн-проект из референсов и планов',
        'hint': 'Обмерный план + референсы (фото, 3ddd, Pinterest, панорамы 360°).',
        'need': ('Планы',),
    },
}

COMMON_RULES = """\
Ты работаешь в отдельной папке задания (текущая папка). Здесь:
- ./dp-engine — движок рабочих чертежей бюро PORTFOLIO (читай README.md, docs/workflow.md, docs/data-schema.md,
  docs/checklist.md, docs/skill/SKILL.md — это навык «dizain-proekt-kvartiry», работай строго по нему);
- ./ИСХОДНЫЕ — всё, что прислал заказчик (планы, IFC, референсы, рендеры, панорамы);
- ./РЕЗУЛЬТАТ — сюда и только сюда клади итоговые файлы для заказчика.

Режим автономный: никаких вопросов и подтверждений, людей рядом нет. Чего не хватает — типовое решение,
пометка «уточнить по месту» и запись в общий список вопросов. Ничего не выдумывай молча. Размеры только
реальные. Не удаляй и не меняй файлы в ./ИСХОДНЫЕ. Сеть — только для установки пакетов pip.
Если нужен пакет: python -m pip install <пакет> (reportlab numpy scipy pillow pypdf pdfplumber ifcopenshell).

Обязательно в конце положи в ./РЕЗУЛЬТАТ файл «ОТЧЁТ.md»:
1) список выданных файлов (по одной строке);
2) 2–3 строки о принятых решениях;
3) единый список вопросов и допущений с принятыми вариантами.
Без пересказа процесса. Последним сообщением выведи содержимое ОТЧЁТ.md.
"""

MODE_PROMPTS = {
    'ifc': """\
ЗАДАЧА: создать IFC-модель квартиры по планам и визуализациям/референсам.
Порядок: docs/workflow.md движка, этапы до модели. Новый объект {shifr} (objects/<шифр в нижнем регистре>
из objects/_template). Обмер → obmer.py (tools/obmer_import.py как черновик, затем точная доводка по цепочкам
размеров), решения по визуализациям/референсам → design.py (помещения, проёмы, двери, окна, мебель, отделка,
свет). tools/check.py — 0 ошибок. Затем: python tools/model3d.py objects/<шифр> ifc и pack.
В ./РЕЗУЛЬТАТ: <шифр>.ifc, GLB (если собрался), превью-лист модели PNG/PDF, zip выпуска, обмерный план PDF
для сверки, ОТЧЁТ.md.""",
    'album': """\
ЗАДАЧА: выпустить альбом рабочих чертежей по готовой IFC-модели квартиры (+ рендеры/референсы).
Движок не читает IFC напрямую: разбери IFC сам (python -m pip install ifcopenshell; IfcWall, IfcSpace, IfcDoor,
IfcWindow, IfcSlab, IfcFurnishingElement, IfcLightFixture, IfcSanitaryTerminal, IfcOutlet/IfcSwitchingDevice,
отметки IfcBuildingStorey), переведи геометрию в данные объекта {shifr} (obmer.py + design.py, координаты по
data-schema: x — вниз по листу, y — вправо, мм), отделку и стиль — по рендерам/референсам.
Дальше — полный цикл навыка: экспликация → параметры помещений → сквозная проверка → черчение → самопроверка
(каждый лист PDF, tools/check.py — 0 ошибок) → выпуск: build.py all --dxf, tools/cover.py, build.py --params.
В ./РЕЗУЛЬТАТ: PDF альбома с обложкой, DXF-zip, папку params (00-obshchee.md, NN-…-parametry.md), ОТЧЁТ.md.""",
    'dp': """\
ЗАДАЧА: полный дизайн-проект квартиры по обмерному плану и референсам — навык «dizain-proekt-kvartiry»
целиком, автономно. Новый объект {shifr}. Состав комплекта и порядок листов — docs/instrukcii-proekta.md
движка (титул, ведомость и экспликация, дизайн-проект, общие указания и сквозная проверка, все планы на всю
квартиру, спецификации, по помещениям — схемы, развёртки, раскладки плитки, узлы, визуализации при панорамах 360°).
Самопроверка обязательна (каждый лист PDF, сверка размеров и номеров, tools/check.py — 0 ошибок).
Выпуск: build.py all --dxf, tools/cover.py, build.py --params; если есть время и всё прошло — model3d.py ifc.
В ./РЕЗУЛЬТАТ: PDF альбома с обложкой, DXF-zip, папку params, IFC (если собран), ОТЧЁТ.md.""",
}


def build_prompt(mode, shifr, wishes, files, extra_rules):
    lst = '\n'.join('- ' + f for f in files) or '- (нет файлов)'
    p = [COMMON_RULES, MODE_PROMPTS[mode].format(shifr=shifr or 'шифр не задан — следующий номер бюро ДП-NN-ГГГГ-АИ, отметить в вопросах')]
    p.append('ИСХОДНЫЕ ФАЙЛЫ:\n' + lst)
    if wishes.strip():
        p.append('ПОЖЕЛАНИЯ ЗАКАЗЧИКА (приоритет над типовыми решениями):\n' + wishes.strip())
    if extra_rules.strip():
        p.append('ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА БЮРО:\n' + extra_rules.strip())
    return '\n\n'.join(p)


# ---------------------------------------------------------------- задание
def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\s]+', '_', s.strip())
    return s[:60] or 'объект'


class Job:
    STATES = {'wait': 'в очереди', 'prep': 'подготовка', 'run': 'работает', 'ok': 'готово',
              'err': 'ошибка', 'stop': 'остановлено'}

    def __init__(self, mode, shifr, wishes, files, settings):
        self.mode, self.shifr, self.wishes, self.files = mode, shifr, wishes, list(files)
        self.s = dict(settings)
        stamp = _dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.name = f'{stamp}_{mode}_{safe_name(shifr or "новый")}'
        self.dir = os.path.join(self.s['jobs_dir'], self.name)
        self.src = os.path.join(self.dir, 'ИСХОДНЫЕ')
        self.res = os.path.join(self.dir, 'РЕЗУЛЬТАТ')
        self.log_path = os.path.join(self.dir, 'журнал.txt')
        self.state = 'wait'
        self.status = ''
        self.session_id = ''
        self.report = ''
        self.cost = None
        self.proc = None
        self.started = None
        self.finished = None

    # -- подготовка папки
    def prepare(self):
        os.makedirs(self.src, exist_ok=True)
        os.makedirs(self.res, exist_ok=True)
        rel = []
        for f in self.files:
            if os.path.isdir(f):
                dst = os.path.join(self.src, os.path.basename(f.rstrip('\\/')))
                shutil.copytree(f, dst, dirs_exist_ok=True)
                for r, _, fs in os.walk(dst):
                    rel += [os.path.relpath(os.path.join(r, x), self.dir).replace('\\', '/') for x in fs]
            else:
                dst = os.path.join(self.src, os.path.basename(f))
                shutil.copy2(f, dst)
                rel.append(os.path.relpath(dst, self.dir).replace('\\', '/'))
        eng = self.s['engine_zip']
        if not os.path.exists(eng):
            raise RuntimeError(f'Не найден движок: {eng}. Укажите dp-engine.zip или папку в настройках.')
        target = os.path.join(self.dir, 'dp-engine')
        if os.path.isdir(eng):
            shutil.copytree(eng, target, ignore=shutil.ignore_patterns('.git', 'studio', 'out', '__pycache__', '*.pyc', '*.cmd'))
        else:
            tmp = os.path.join(self.dir, '_engine_tmp')
            with zipfile.ZipFile(eng) as z:
                z.extractall(tmp)
            inner = tmp
            if not os.path.exists(os.path.join(inner, 'build.py')):
                for d in os.listdir(tmp):
                    if os.path.exists(os.path.join(tmp, d, 'build.py')):
                        inner = os.path.join(tmp, d)
                        break
            shutil.move(inner, target)
            shutil.rmtree(tmp, ignore_errors=True)
        # навык — в папку проекта сессии, чтобы Claude Code подхватил его автоматически
        sk = os.path.join(target, 'docs', 'skill', 'SKILL.md')
        if os.path.exists(sk):
            dst = os.path.join(self.dir, '.claude', 'skills', 'dizain-proekt-kvartiry')
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(sk, os.path.join(dst, 'SKILL.md'))
        prompt = build_prompt(self.mode, self.shifr, self.wishes, rel, self.s.get('extra_rules', ''))
        with open(os.path.join(self.dir, 'ЗАПРОС.md'), 'w', encoding='utf-8') as f:
            f.write(prompt)
        sysp = os.path.join(target, 'docs', 'instrukcii-proekta.md')
        return prompt, (sysp if os.path.exists(sysp) else None)

    # -- запуск новой сессии Claude
    def command(self, prompt, sys_prompt_file):
        cmd = [self.s['claude_exe'], '-p', prompt,
               '--output-format', 'stream-json', '--verbose',
               '--permission-mode', 'bypassPermissions']
        if self.s.get('model'):
            cmd += ['--model', self.s['model']]
        if sys_prompt_file:
            cmd += ['--append-system-prompt-file', sys_prompt_file]
        return cmd

    def run(self, on_event):
        self.started = _dt.datetime.now()
        try:
            self.state = 'prep'
            on_event(self, 'Готовлю папку задания…')
            prompt, sysf = self.prepare()
            self.state = 'run'
            on_event(self, 'Сессия Claude запущена')
            cmd = self.command(prompt, sysf)
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            exe = shutil.which(cmd[0]) or cmd[0]
            cmd[0] = exe
            if os.name == 'nt' and exe.lower().endswith(('.cmd', '.bat')):
                cmd = ['cmd', '/c'] + cmd
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
            self.proc = subprocess.Popen(cmd, cwd=self.dir, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         env=env, creationflags=flags)
            with open(self.log_path, 'a', encoding='utf-8') as log:
                for raw in self.proc.stdout:
                    line = raw.decode('utf-8', 'replace').rstrip()
                    if not line:
                        continue
                    log.write(line + '\n')
                    log.flush()
                    msg = self.parse(line)
                    if msg:
                        on_event(self, msg)
            rc = self.proc.wait()
            if self.state == 'stop':
                pass
            elif rc == 0 and self.has_result():
                self.state = 'ok'
            else:
                self.state = 'err'
                if not self.status:
                    self.status = f'Claude завершился с кодом {rc}; см. журнал.txt'
        except Exception as e:  # noqa: BLE001
            self.state = 'err'
            self.status = str(e)
        self.finished = _dt.datetime.now()
        self.collect_report()
        on_event(self, None)

    def parse(self, line):
        try:
            ev = json.loads(line)
        except ValueError:
            return line[:200]
        t = ev.get('type')
        if t == 'system' and ev.get('subtype') == 'init':
            self.session_id = ev.get('session_id', '')
            return f'Новая сессия {self.session_id[:8]}…'
        if t == 'assistant':
            for c in (ev.get('message') or {}).get('content') or []:
                if c.get('type') == 'text' and c.get('text', '').strip():
                    return c['text'].strip().splitlines()[0][:200]
                if c.get('type') == 'tool_use':
                    inp = c.get('input') or {}
                    d = inp.get('description') or inp.get('subject') or inp.get('file_path') or ''
                    return f'· {c.get("name")}: {str(d)[:150]}'
        if t == 'result':
            self.report = ev.get('result') or ''
            self.cost = ev.get('total_cost_usd')
            if ev.get('is_error'):
                self.status = (ev.get('result') or 'ошибка сессии')[:300]
            return 'Сессия завершена'
        return None

    def has_result(self):
        return any(os.scandir(self.res)) if os.path.isdir(self.res) else False

    def collect_report(self):
        rp = os.path.join(self.res, 'ОТЧЁТ.md')
        if os.path.exists(rp):
            with open(rp, encoding='utf-8', errors='replace') as f:
                self.report = f.read()
        elif self.report and os.path.isdir(self.res):
            with open(rp, 'w', encoding='utf-8') as f:
                f.write(self.report)
        with open(os.path.join(self.dir, 'задание.json'), 'w', encoding='utf-8') as f:
            json.dump({'mode': self.mode, 'shifr': self.shifr, 'state': self.state,
                       'session_id': self.session_id, 'status': self.status,
                       'started': str(self.started), 'finished': str(self.finished)},
                      f, ensure_ascii=False, indent=2)

    def stop(self):
        self.state = 'stop'
        if self.proc and self.proc.poll() is None:
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.proc.pid)],
                                creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                self.proc.kill()

    def result_files(self):
        out = []
        for r, _, fs in os.walk(self.res):
            out += [os.path.relpath(os.path.join(r, f), self.res) for f in fs]
        return sorted(out)


# ---------------------------------------------------------------- обновление движка из GitHub
def update_engine(s):
    """git pull в клоне dp-engine. Возвращает строку статуса."""
    root = s['engine_zip']
    if not os.path.isdir(os.path.join(root, '.git')) or not shutil.which('git'):
        return 'движок: локальная копия'
    fl = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        pull = ['git', '-C', root, 'pull', '--ff-only', '-q']
        r = subprocess.run(pull, capture_output=True, text=True, timeout=120, creationflags=fl)
        if r.returncode != 0:      # локальные правки мешают — убрать их в stash (не удаляются) и повторить
            subprocess.run(['git', '-C', root, 'stash', 'push', '-u', '-q', '-m', 'portfolio-studio auto'],
                           capture_output=True, timeout=60, creationflags=fl)
            r = subprocess.run(pull, capture_output=True, text=True, timeout=120, creationflags=fl)
        h = subprocess.run(['git', '-C', root, 'log', '-1', '--format=%h · %cd', '--date=format:%d.%m.%Y'],
                           capture_output=True, text=True, timeout=20, creationflags=fl).stdout.strip()
        return ('движок ' + h) if r.returncode == 0 else ('движок ' + h + ' · не обновился')
    except Exception:  # noqa: BLE001
        return 'движок: нет связи с GitHub'


def load_fonts():
    """Фирменные шрифты сайта (Prata, PT Sans Narrow, PT Mono) — только для процесса приложения."""
    d = os.path.join(app_dir(), 'fonts')
    if os.name != 'nt' or not os.path.isdir(d):
        return
    import ctypes
    for f in os.listdir(d):
        if f.lower().endswith('.ttf'):
            ctypes.windll.gdi32.AddFontResourceExW(os.path.join(d, f), 0x10, 0)


# ---------------------------------------------------------------- поиск Claude Code
def _is_claude_code(exe):
    try:
        v = subprocess.run([exe, '--version'], capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return 'claude code' in (v.stdout + v.stderr).lower()
    except Exception:  # noqa: BLE001
        return False


def refresh_path():
    """Ярлык из Проводника получает PATH на момент входа в Windows. Перечитываем актуальный из реестра."""
    if os.name != 'nt':
        return
    import winreg
    parts = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
                      (winreg.HKEY_CURRENT_USER, 'Environment')):
        try:
            with winreg.OpenKey(hive, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, 'Path')[0]))
        except OSError:
            pass
    extra = [os.path.join(os.path.expanduser('~'), '.local', 'bin'), os.path.join(os.environ.get('APPDATA', ''), 'npm')]
    cur = os.environ.get('PATH', '').split(os.pathsep)
    new = [x for x in os.pathsep.join(parts + extra).split(os.pathsep) if x]
    os.environ['PATH'] = os.pathsep.join(dict.fromkeys(new + cur))


def find_claude():
    """Ищет уже установленный Claude Code: PATH, установщик, npm, встроенный в приложение Claude."""
    import glob
    refresh_path()
    w = shutil.which('claude')
    if w:
        return w
    if os.name != 'nt':
        return None
    H, A, L = os.path.expanduser('~'), os.environ.get('APPDATA', ''), os.environ.get('LOCALAPPDATA', '')
    direct = [os.path.join(H, '.local', 'bin', 'claude.exe'), os.path.join(A, 'npm', 'claude.cmd'),
              os.path.join(L, 'Programs', 'claude', 'claude.exe'),
              os.path.join(L, 'Microsoft', 'WinGet', 'Links', 'claude.exe'),
              os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'nodejs', 'claude.cmd')]
    for c in direct:
        if os.path.exists(c):
            return c
    found = []
    for root in (os.path.join(A, 'Claude'), os.path.join(L, 'Claude'), os.path.join(L, 'AnthropicClaude'),
                 os.path.join(L, 'Claude-Data'), os.path.join(L, 'Claude-3p'), os.path.join(L, 'Programs'),
                 os.path.join(L, 'Microsoft', 'WinGet', 'Packages')):
        found += glob.glob(os.path.join(root, '**', 'claude.exe'), recursive=True)
    # приложение Claude (Claude.exe в app-*/корне) — не CLI; проверяем кандидатов запуском --version
    found = sorted({f for f in found if not os.path.basename(os.path.dirname(f)).lower().startswith('app-')},
                   key=os.path.getmtime, reverse=True)
    for f in found[:6]:
        if _is_claude_code(f):
            return f
    return None


def resolve_claude(s):
    refresh_path()
    exe = shutil.which(s.get('claude_exe') or 'claude') or (s.get('claude_exe') if os.path.exists(s.get('claude_exe') or '') else None)
    if not exe:
        exe = find_claude()
        if exe:
            s['claude_exe'] = exe
            save_settings(s)
    return exe


# ---------------------------------------------------------------- проверка окружения
def check_env(s):
    msgs = []
    exe = resolve_claude(s)
    if not exe:
        msgs.append('✗ Claude Code не найден. Укажите путь к claude.exe в «Настройках».')
    else:
        try:
            v = subprocess.run([exe, '--version'], capture_output=True, text=True, timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            msgs.append('✓ Claude Code ' + (v.stdout.strip() or v.stderr.strip()))
        except Exception as e:  # noqa: BLE001
            msgs.append(f'✗ Claude Code не запускается: {e}')
    py = shutil.which('python') or shutil.which('py')
    msgs.append(('✓ Python: ' + py) if py else '✗ Python не найден в PATH (нужен движку).')
    msgs.append(('✓ Движок: ' if os.path.exists(s['engine_zip']) else '✗ Нет движка: ') + s['engine_zip'])
    return msgs


# ---------------------------------------------------------------- интерфейс
def write_diag():
    """Журнал окружения: %LOCALAPPDATA%\\PortfolioStudio\\diag.txt (для поддержки)."""
    import glob, platform
    L = []
    try:
        L.append(f'{APP_NAME} {APP_VER} · {sys.executable} · {platform.platform()}')
        for c in ('claude', 'git', 'node', 'python', 'pythonw'):
            L.append(f'which {c}: {shutil.which(c)}')
        H, A, LA = os.path.expanduser('~'), os.environ.get('APPDATA', ''), os.environ.get('LOCALAPPDATA', '')
        pats = [H + r'\.local\bin\claude*', A + r'\npm\claude*', A + r'\Claude\**\claude*.exe',
                LA + r'\Claude*\**\claude*.exe', LA + r'\AnthropicClaude\**\claude*.exe',
                LA + r'\Programs\**\claude*.exe', LA + r'\Packages\*Claude*\**\claude*.exe']
        seen = set()
        for pt in pats:
            for f in glob.glob(pt, recursive=True):
                if f in seen:
                    continue
                seen.add(f)
                try:
                    v = subprocess.run([f, '--version'], capture_output=True, text=True, timeout=20,
                                       stdin=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    L.append(f'cand {f} => {(v.stdout + v.stderr).strip()[:150]}')
                except Exception as e:  # noqa: BLE001
                    L.append(f'cand {f} ERR {e}')
        L.append('find_claude: ' + str(find_claude()))
        for m in ('reportlab', 'numpy', 'scipy', 'PIL', 'pypdf', 'pdfplumber', 'ifcopenshell'):
            try:
                __import__(m)
                L.append('mod ok ' + m)
            except Exception as e:  # noqa: BLE001
                L.append(f'mod MISSING {m}: {e}')
        L.append('PATH=' + os.environ.get('PATH', ''))
    except Exception as e:  # noqa: BLE001
        L.append('diag ERR ' + repr(e))
    try:
        d = os.path.join(os.environ.get('LOCALAPPDATA', data_dir()), 'PortfolioStudio')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'diag.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(L))
    except OSError:
        pass


def run_gui():
    threading.Thread(target=write_diag, daemon=True).start()
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    s = load_settings()
    os.makedirs(s['jobs_dir'], exist_ok=True)
    events = queue.Queue()
    jobs = []
    sem = {'running': 0}

    # Палитра и шрифты — как у сайта/просмотрщика бюро: глубокий синий, тёплый белый, матовая латунь.
    load_fonts()
    GROUND, PANEL, FIELD = '#10141f', '#161c2c', '#1c2336'
    INK, MUTE, LINE = '#ece6db', '#afb3c2', '#2c3448'
    NAVY, BRASS, BRASS_D, ERR, OK = '#283658', '#c9a96e', '#a88a52', '#e07a6a', '#9cc59a'
    root = tk.Tk()
    import tkinter.font as tkfont
    fam = set(tkfont.families())
    def pick(*names):
        return next((n for n in names if n in fam), names[-1])
    F_DISP = pick('Prata', 'Georgia', 'Times New Roman')
    F_UI = pick('PT Sans Narrow', 'Arial Narrow', 'Segoe UI')
    F_DATA = pick('PT Mono', 'Consolas', 'Courier New')
    PAPER, ACC = GROUND, BRASS
    root.title(f'{APP_NAME} {APP_VER}')
    root.geometry('1200x780')
    root.minsize(1000, 660)
    root.configure(bg=GROUND)
    root.option_add('*TCombobox*Listbox.background', FIELD)
    try:
        ico = os.path.join(app_dir(), 'icon.ico')
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except tk.TclError:
        pass

    st = ttk.Style()
    st.theme_use('clam')
    st.configure('.', background=GROUND, foreground=INK, font=(F_UI, 12), bordercolor=LINE,
                 lightcolor=GROUND, darkcolor=GROUND, troughcolor=PANEL, fieldbackground=FIELD,
                 selectbackground=NAVY, selectforeground=INK, insertcolor=INK)
    st.configure('TFrame', background=GROUND)
    st.configure('Panel.TFrame', background=PANEL)
    st.configure('H.TLabel', font=(F_DISP, 22), background=GROUND, foreground=INK)
    st.configure('Sub.TLabel', foreground=MUTE, background=GROUND, font=(F_UI, 11))
    st.configure('Sec.TLabel', font=(F_UI, 11, 'bold'), foreground=BRASS, background=GROUND)
    st.configure('Doc.TLabel', font=(F_DATA, 10), foreground=MUTE, background=GROUND)
    st.configure('TButton', background=PANEL, foreground=INK, bordercolor=LINE, focusthickness=0,
                 padding=(10, 5), font=(F_UI, 12), width=-6)
    st.map('TButton', background=[('active', NAVY)], bordercolor=[('active', BRASS)])
    st.configure('Go.TButton', font=(F_UI, 14, 'bold'), padding=(22, 9), background=BRASS,
                 foreground=GROUND, bordercolor=BRASS)
    st.map('Go.TButton', background=[('active', '#d9bd86')], foreground=[('active', GROUND)])
    st.configure('TRadiobutton', background=GROUND, foreground=INK, font=(F_UI, 13),
                 indicatorbackground=FIELD, indicatorforeground=BRASS)
    st.map('TRadiobutton', background=[('active', GROUND)], indicatorbackground=[('selected', BRASS)])
    st.configure('TCheckbutton', background=PANEL, foreground=INK, indicatorbackground=FIELD)
    st.map('TCheckbutton', indicatorbackground=[('selected', BRASS)])
    st.configure('TEntry', fieldbackground=FIELD, foreground=INK, bordercolor=LINE, padding=4)
    st.map('TEntry', bordercolor=[('focus', BRASS)])
    st.configure('Treeview', rowheight=28, background=FIELD, fieldbackground=FIELD, foreground=INK,
                 bordercolor=LINE, font=(F_UI, 12))
    st.map('Treeview', background=[('selected', NAVY)], foreground=[('selected', INK)])
    st.configure('Treeview.Heading', font=(F_UI, 11, 'bold'), background=PANEL, foreground=BRASS,
                 bordercolor=LINE, relief='flat')
    st.map('Treeview.Heading', background=[('active', PANEL)])
    st.configure('Vertical.TScrollbar', background=PANEL, troughcolor=GROUND, arrowcolor=MUTE, bordercolor=GROUND)
    st.configure('TPanedwindow', background=GROUND)
    TXT = dict(bg=FIELD, fg=INK, insertbackground=BRASS, selectbackground=NAVY, relief='flat',
               highlightthickness=1, highlightbackground=LINE, highlightcolor=BRASS, bd=6)

    # шапка: логотип бюро, название, шифр-статус движка
    top = ttk.Frame(root, padding=(22, 14, 22, 8))
    top.pack(fill='x')
    try:
        root._logo = tk.PhotoImage(file=os.path.join(app_dir(), 'assets', 'logo.png')).subsample(1, 1)
        tk.Label(top, image=root._logo, bg=GROUND, bd=0).pack(side='left')
    except tk.TclError:
        ttk.Label(top, text='PORTFOLIO', style='H.TLabel').pack(side='left')
    tb = ttk.Frame(top)
    tb.pack(side='left', padx=16)
    ttk.Label(tb, text='Студия рабочих чертежей', style='H.TLabel').pack(anchor='w')
    eng_status = tk.StringVar(value='движок: проверяю обновления…')
    ttk.Label(tb, textvariable=eng_status, style='Doc.TLabel').pack(anchor='w')
    ttk.Button(top, text='Настройки', command=lambda: open_settings()).pack(side='right')
    ttk.Button(top, text='Проверить окружение',
               command=lambda: messagebox.showinfo(APP_NAME, '\n'.join(check_env(s)))).pack(side='right', padx=6)
    tk.Frame(root, bg=BRASS, height=1).pack(fill='x', padx=22)

    def _upd():
        msg = update_engine(s) if s.get('auto_update', True) else 'движок: обновление выключено'
        root.after(0, lambda: eng_status.set(msg + '  ·  новый чат Claude на каждый запрос'))
    threading.Thread(target=_upd, daemon=True).start()

    body = ttk.PanedWindow(root, orient='horizontal')
    body.pack(fill='both', expand=True, padx=22, pady=(12, 18))

    # ---- левая колонка: новый запрос
    left = ttk.Frame(body, padding=(0, 0, 18, 0), width=470)
    body.add(left, weight=1)
    ttk.Label(left, text='1  РЕЖИМ', style='Sec.TLabel').pack(anchor='w')
    mode = tk.StringVar(value='dp')
    hint = ttk.Label(left, style='Sub.TLabel', wraplength=380)
    for k, m in MODES.items():
        ttk.Radiobutton(left, text=m['title'], value=k, variable=mode,
                        command=lambda: hint.configure(text=MODES[mode.get()]['hint'])).pack(anchor='w', pady=1)
    hint.configure(text=MODES['dp']['hint'])
    hint.pack(anchor='w', pady=(2, 10))

    ttk.Label(left, text='2  ИСХОДНЫЕ ДАННЫЕ', style='Sec.TLabel').pack(anchor='w')
    fl = tk.Listbox(left, height=7, activestyle='none', font=(F_UI, 12),
                    **{k: v for k, v in TXT.items() if k != 'insertbackground'})
    fl.pack(fill='x', pady=(4, 4))
    files = []

    def add_files():
        for f in filedialog.askopenfilenames(title='Планы, IFC, референсы, рендеры, панорамы',
                                              filetypes=[('Все исходные', '*.pdf *.dxf *.dwg *.ifc *.jpg *.jpeg *.png *.webp *.zip *.7z *.txt *.md *.docx'),
                                                         ('Все файлы', '*.*')]):
            if f not in files:
                files.append(f)
                fl.insert('end', os.path.basename(f))

    def add_folder():
        d = filedialog.askdirectory(title='Папка с исходными данными')
        if d and d not in files:
            files.append(d)
            fl.insert('end', '📁 ' + os.path.basename(d))

    def rm_file():
        for i in reversed(fl.curselection()):
            fl.delete(i)
            files.pop(i)

    bf = ttk.Frame(left)
    bf.pack(fill='x')
    ttk.Button(bf, text='+ Файлы', command=add_files).pack(side='left')
    ttk.Button(bf, text='+ Папка', command=add_folder).pack(side='left', padx=6)
    ttk.Button(bf, text='Убрать', command=rm_file).pack(side='left')

    ttk.Label(left, text='3  ОБЪЕКТ И ПОЖЕЛАНИЯ', style='Sec.TLabel').pack(anchor='w', pady=(12, 0))
    sf = ttk.Frame(left)
    sf.pack(fill='x', pady=4)
    ttk.Label(sf, text='Шифр').pack(side='left')
    shifr = tk.StringVar()
    ttk.Entry(sf, textvariable=shifr, width=22).pack(side='left', padx=6)
    ttk.Label(sf, text='пусто — следующий номер', style='Sub.TLabel').pack(side='left')
    go = ttk.Frame(left)
    go.pack(side='bottom', fill='x', pady=(10, 0))
    wish = tk.Text(left, height=6, wrap='word', font=(F_UI, 12), **TXT)
    wish.pack(fill='both', expand=True, pady=(2, 0))
    wish.insert('1.0', '')

    def start():
        m = mode.get()
        if not files:
            messagebox.showwarning(APP_NAME, 'Добавьте исходные файлы.')
            return
        if m == 'album' and not any(f.lower().endswith('.ifc') or os.path.isdir(f) for f in files):
            if not messagebox.askyesno(APP_NAME, 'Среди файлов нет .ifc. Всё равно запустить?'):
                return
        j = Job(m, shifr.get().strip(), wish.get('1.0', 'end'), files, s)
        jobs.append(j)
        tree.insert('', 0, iid=j.name, values=(MODES[m]['title'], j.shifr or '—',
                                               Job.STATES['wait'], j.name[5:16].replace('_', ' ')))
        files.clear()
        fl.delete(0, 'end')
        wish.delete('1.0', 'end')
        pump()

    ttk.Button(go, text='Отправить в Claude   →', style='Go.TButton', command=start).pack(side='right')

    # ---- правая колонка: задания и результат
    right = ttk.Frame(body)
    body.add(right, weight=3)
    root.after(50, lambda: body.sashpos(0, 470))
    ttk.Label(right, text='ЗАДАНИЯ', style='Sec.TLabel').pack(anchor='w')
    cols = ('mode', 'shifr', 'state', 'when')
    tree = ttk.Treeview(right, columns=cols, show='headings', height=8, selectmode='browse')
    for c, t, w in zip(cols, ('Режим', 'Шифр', 'Статус', 'Создано'), (230, 120, 80, 100)):
        tree.heading(c, text=t)
        tree.column(c, width=w, minwidth=60, anchor='w', stretch=(c == 'mode'))
    tree.pack(fill='x', pady=(4, 6))
    tree.tag_configure('ok', foreground=OK)
    tree.tag_configure('err', foreground=ERR)
    tree.tag_configure('run', foreground=BRASS)

    act = ttk.Frame(right)
    act.pack(fill='x')

    def cur():
        sel = tree.selection()
        return next((j for j in jobs if sel and j.name == sel[0]), None)

    def open_path(p):
        if os.name == 'nt':
            os.startfile(p)  # noqa: S606
        else:
            subprocess.Popen(['xdg-open', p])

    ttk.Button(act, text='Результат', command=lambda: cur() and open_path(cur().res)).pack(side='left')
    ttk.Button(act, text='Папка', command=lambda: cur() and open_path(cur().dir)).pack(side='left', padx=6)
    ttk.Button(act, text='Журнал', command=lambda: cur() and os.path.exists(cur().log_path)
               and open_path(cur().log_path)).pack(side='left')

    def stop_job():
        j = cur()
        if j and j.state in ('wait', 'prep', 'run') and messagebox.askyesno(APP_NAME, 'Остановить задание?'):
            j.stop()
            refresh(j)

    def revise():
        j = cur()
        if not j:
            return
        mode.set(j.mode)
        shifr.set(j.shifr)
        for f in j.files:
            if f not in files:
                files.append(f)
                fl.insert('end', os.path.basename(f))
        if os.path.isdir(j.res):
            files.append(j.res)
            fl.insert('end', '📁 предыдущий результат (' + j.name[:10] + ')')
        wish.delete('1.0', 'end')
        wish.insert('1.0', 'ПРАВКИ — новая редакция (ред. N+1). Предыдущий результат приложен; '
                           'сначала обновить данные объекта, потом пересобрать затронутые листы:\n- ')
        wish.focus_set()

    ttk.Button(act, text='Стоп', command=stop_job).pack(side='right')
    ttk.Button(act, text='Правки · ред. N+1', command=revise).pack(side='right', padx=6)

    ttk.Label(right, text='ХОД / ОТЧЁТ', style='Sec.TLabel').pack(anchor='w', pady=(10, 0))
    out = tk.Text(right, wrap='word', font=(F_DATA, 10), state='disabled', **TXT)
    out.pack(fill='both', expand=True, pady=(4, 0))
    logs = {}

    def show(j):
        out.configure(state='normal')
        out.delete('1.0', 'end')
        txt = ''
        if j.state in ('ok', 'err', 'stop'):
            files_ = j.result_files()
            txt += f'Статус: {Job.STATES[j.state]}  {j.status}\n'
            if j.cost:
                txt += f'Стоимость сессии (оценка): ${j.cost:.2f}\n'
            if files_:
                txt += '\nФайлы результата:\n' + '\n'.join('  ' + f for f in files_) + '\n'
            if j.report:
                txt += '\n' + j.report + '\n'
            txt += '\n— ход работы —\n'
        txt += '\n'.join(logs.get(j.name, [])[-300:])
        out.insert('1.0', txt)
        out.configure(state='disabled')
        out.see('end' if j.state == 'run' else '1.0')

    tree.bind('<<TreeviewSelect>>', lambda e: cur() and show(cur()))

    def refresh(j):
        if tree.exists(j.name):
            tree.set(j.name, 'state', Job.STATES[j.state])
            tree.item(j.name, tags=(j.state,))
        if cur() is j:
            show(j)

    # ---- очередь
    def on_event(j, msg):
        events.put((j, msg))

    def pump():
        for j in jobs:
            if j.state == 'wait' and sem['running'] < int(s['max_parallel']):
                sem['running'] += 1
                threading.Thread(target=j.run, args=(on_event,), daemon=True).start()

    def poll():
        try:
            while True:
                j, msg = events.get_nowait()
                if msg is None:
                    sem['running'] -= 1
                    refresh(j)
                    root.bell()
                    if j.state == 'ok':
                        if s.get('open_result'):
                            open_path(j.res)
                        messagebox.showinfo(APP_NAME, f'Готово: {MODES[j.mode]["title"]}\n{j.shifr or j.name}')
                    elif j.state == 'err':
                        messagebox.showerror(APP_NAME, f'Задание не выполнено:\n{j.status[:400]}')
                    pump()
                else:
                    logs.setdefault(j.name, []).append(_dt.datetime.now().strftime('%H:%M:%S  ') + msg)
                    refresh(j)
        except queue.Empty:
            pass
        root.after(400, poll)

    # ---- настройки
    def open_settings():
        w = tk.Toplevel(root)
        w.title('Настройки')
        w.configure(bg=PANEL)
        try:
            w.iconbitmap(os.path.join(app_dir(), 'icon.ico'))
        except tk.TclError:
            pass
        w.transient(root)
        fr = ttk.Frame(w, padding=18, style='Panel.TFrame')
        fr.pack(fill='both', expand=True)
        vars_ = {}
        rows = [('engine_zip', 'Движок dp-engine (клон GitHub, папка или zip)', 'dir'),
                ('claude_exe', 'Claude Code (claude / путь к claude.exe)', 'file'),
                ('model', 'Модель (opus / sonnet / полное имя)', None),
                ('jobs_dir', 'Папка заданий и результатов', 'dir'),
                ('max_parallel', 'Одновременных заданий', None)]
        for i, (k, t, kind) in enumerate(rows):
            ttk.Label(fr, text=t, background=PANEL).grid(row=i, column=0, sticky='w', pady=3)
            v = tk.StringVar(value=str(s[k]))
            vars_[k] = v
            ttk.Entry(fr, textvariable=v, width=56).grid(row=i, column=1, padx=6)
            if kind:
                def pick(v=v, kind=kind):
                    p = (filedialog.askdirectory() if kind == 'dir'
                         else filedialog.askopenfilename())
                    if p:
                        v.set(p)
                ttk.Button(fr, text='…', width=3, command=pick).grid(row=i, column=2)
        ttk.Label(fr, text='Доп. правила бюро (добавляются к каждому запросу)', background=PANEL).grid(
            row=len(rows), column=0, columnspan=3, sticky='w', pady=(10, 2))
        ex = tk.Text(fr, height=6, width=80, wrap='word', font=(F_UI, 11), **TXT)
        ex.grid(row=len(rows) + 1, column=0, columnspan=3)
        ex.insert('1.0', s.get('extra_rules', ''))
        op = tk.BooleanVar(value=bool(s.get('open_result')))
        ttk.Checkbutton(fr, text='Открывать папку результата по готовности', variable=op).grid(
            row=len(rows) + 2, column=0, columnspan=3, sticky='w', pady=6)

        def ok():
            for k, v in vars_.items():
                s[k] = v.get().strip()
            try:
                s['max_parallel'] = max(1, int(s['max_parallel']))
            except ValueError:
                s['max_parallel'] = 1
            s['extra_rules'] = ex.get('1.0', 'end').strip()
            s['open_result'] = op.get()
            os.makedirs(s['jobs_dir'], exist_ok=True)
            save_settings(s)
            w.destroy()
        ttk.Button(fr, text='Сохранить', style='Go.TButton', command=ok).grid(
            row=len(rows) + 3, column=2, sticky='e')

    # прошлые задания
    try:
        for d in sorted(os.listdir(s['jobs_dir'])):
            meta = os.path.join(s['jobs_dir'], d, 'задание.json')
            if os.path.exists(meta):
                with open(meta, encoding='utf-8') as f:
                    mj = json.load(f)
                j = Job(mj['mode'], mj.get('shifr', ''), '', [], s)
                j.name, j.dir = d, os.path.join(s['jobs_dir'], d)
                j.src, j.res = os.path.join(j.dir, 'ИСХОДНЫЕ'), os.path.join(j.dir, 'РЕЗУЛЬТАТ')
                j.log_path = os.path.join(j.dir, 'журнал.txt')
                j.state = mj.get('state', 'ok') if mj.get('state') in Job.STATES else 'ok'
                j.status = mj.get('status', '')
                j.collect_report = lambda: None
                rp = os.path.join(j.res, 'ОТЧЁТ.md')
                if os.path.exists(rp):
                    with open(rp, encoding='utf-8', errors='replace') as f:
                        j.report = f.read()
                jobs.append(j)
                tree.insert('', 0, iid=d, values=(MODES.get(j.mode, {'title': j.mode})['title'],
                                                  j.shifr or '—', Job.STATES[j.state], d[5:16].replace('_', ' ')),
                            tags=(j.state,))
    except OSError:
        pass

    def _find():
        exe = resolve_claude(s)
        if not exe:
            root.after(0, lambda: messagebox.showwarning(
                APP_NAME, 'Claude Code не найден автоматически.\n\nОткройте «Настройки» и укажите путь к claude.exe '
                          '(или claude.cmd). Узнать путь: в командной строке выполните  where claude'))
    threading.Thread(target=_find, daemon=True).start()
    poll()
    root.mainloop()


# ---------------------------------------------------------------- консольный режим (без окна)
def run_cli(argv):
    """portfolio_studio.py --run dp|ifc|album --files a.pdf b.jpg [--shifr ...] [--wish "..."]"""
    import argparse
    ap = argparse.ArgumentParser(prog='portfolio_studio')
    ap.add_argument('--run', choices=list(MODES), required=True)
    ap.add_argument('--files', nargs='+', required=True)
    ap.add_argument('--shifr', default='')
    ap.add_argument('--wish', default='')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args(argv)
    s = load_settings()
    j = Job(a.run, a.shifr, a.wish, [os.path.abspath(f) for f in a.files], s)
    done = threading.Event()

    def ev(job, msg):
        if msg is None:
            done.set()
        else:
            print(msg, flush=True)
    j.run(ev)
    print(f'\n[{Job.STATES[j.state]}] {j.res}\n{j.report}')
    return 0 if j.state == 'ok' else 1


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--check':
        print('\n'.join(check_env(load_settings())))
    elif len(sys.argv) > 1:
        sys.exit(run_cli(sys.argv[1:]))
    else:
        run_gui()
