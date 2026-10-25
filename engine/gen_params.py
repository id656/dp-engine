# -*- coding: utf-8 -*-
"""Генерация файлов параметров помещений (этап 3) из единой модели проекта."""
import os, math
import model as D
import elev as EL
import tables as TB
from kit import num, lvl, PROJECT

import paths as _paths
OUT = _paths.out('params')
os.makedirs(OUT, exist_ok=True)

KIND_RU = {'r1': 'розетка', 'r2': 'розетка двойная', 'r2u': 'розетка двойная с USB', 'r1w': 'розетка IP44',
           'r2w': 'розетка двойная IP44', 'pow': 'силовой вывод 32 А', 'out': 'вывод кабеля', 'tvblock': 'блок 2Р+TV+RJ45',
           'medblock': 'блок 2Р+RJ45', 'deskblock': 'блок 3Р+RJ45', 'shk': 'щит ЩК', 'ssh': 'щит СЩ', 'int': 'домофон',
           'v1': 'выключатель 1-клав.', 'v2': 'выключатель 2-клав.', 'v1p': 'выключатель 1-клав. проходной',
           'v2p': 'выключатель 2-клав. проходной', 'tr': 'терморегулятор ТП'}
LKIND = {'spot': 'спот встраиваемый', 'spot44': 'спот IP44', 'spot65': 'спот IP65', 'pend': 'подвес «кольцо» Ø600',
         'track': 'магнитный трек', 'led': 'LED-лента', 'linear': 'линейный накладной', 'sconce': 'бра',
         'wall44': 'настенный IP44', 'fan': 'вентилятор вытяжной', 'mirrorled': 'питание подсветки зеркала',
         'ceil': 'светильник накладной потолочный'}
try:                                   # названия светильников объекта (texts.LKIND) поверх типовых
    import texts as _TX
    LKIND.update(getattr(_TX, 'LKIND', {}) or {})
except ImportError:                    # pragma: no cover
    pass
PKIND = {'hvs': 'ХВС', 'gvs': 'ГВС', 'k50': 'канализация Ø50', 'k110': 'канализация Ø110', 'tap': 'кран ХВС',
         'sif': 'сифон СМ'}


def wall_of_point(room, p, n=None):
    best = None
    for lab, pL, pR in D.RWALLS.get(room, []):
        W = EL.wall_geom(room, lab)
        s, d = EL.proj(W, p)
        if -5 <= s <= W['L'] + 5:
            if best is None or abs(d) < abs(best[2]):
                best = (lab, s, d)
    return best


def ceiling_ref(room, p):
    """Привязка точки потолка к двум стенам: ближайшая по каждой оси."""
    walls = D.RWALLS.get(room, [])
    out = []
    for lab, pL, pR in walls:
        W = EL.wall_geom(room, lab)
        s, d = EL.proj(W, p)
        if 0 <= s <= W['L']:
            out.append((d, lab))
    out.sort()
    seen = []
    res = []
    for d, lab in out:
        W = EL.wall_geom(room, lab)
        axis = 'x' if abs(W['d'][0]) < 1e-6 else 'y'
        if axis in seen:
            continue
        seen.append(axis)
        res.append(f'{round(d)} от стены {D.wall_span(room, lab)}')
        if len(res) == 2:
            break
    return ', '.join(res)


WALL_HINT = {}   # угловые предметы: к какой стене привязывать


def mount_ref(it, room):
    """Сантехника на стене/коробе: ось от левого края стены, вынос короба."""
    wall, face, axis = it['wall'], it['face'], it['axis']
    p = (face, axis) if wall in ('W', 'E') else (axis, face)
    along_y = wall in ('W', 'E')
    best = None
    for lab, pL, pR in D.RWALLS.get(room, []):
        W = EL.wall_geom(room, lab)
        if (abs(W['d'][0]) < 1e-6) != along_y:
            continue
        s, d = EL.proj(W, p)
        if -5 <= s <= W['L'] + 5 and d >= -5 and (best is None or d < best[2]):
            best = (lab, s, d)
    return best


def item_line(it, room):
    pos = (it.get('pos') + ' ') if it.get('pos') else ''
    z = it.get('z', (0, 0))
    zt = f'отм. {lvl(z[0])}…{lvl(z[1])}' if isinstance(z, tuple) else f'отм. {lvl(z)}'
    fl = D.ROOM[room]['level'] or 0
    if fl and isinstance(z, tuple) and z[1] > fl:
        zt += f' (от чистого пола {max(z[0] - fl, 0)}…{z[1] - fl})'
    if it['kind'] in ('wc', 'vanity', 'mini_basin'):
        m = mount_ref(it, room)
        if m:
            lab, s, d = m
            base = f'на коробе инсталляции {round(d)} мм' if d > 20 else 'на стене'
            dep = it.get('depth', 540); w = it.get('width', 360)
            if it['kind'] == 'wc':
                fl = D.ROOM[room]['level'] or 0
                zt = f'верх чаши {lvl(z[1])} ({z[1] - fl} от чистого пола)'
            return f'- {pos}{it["name"]}: ось — {round(s)} от левого края стены {D.wall_span(room, lab)}, {base}; габарит {w}×{dep}, {zt}'
    r = EL.item_rect(it)
    if r is None:
        if 'c' in it:
            w = wall_of_point(room, it['c'])
            if w and abs(w[2]) < 30:
                return f'- {pos}{it["name"]}: на стене {D.wall_span(room, w[0])}, ось — {round(w[1])} от левого края, {zt}'
            return f'- {pos}{it["name"]}: центр — {ceiling_ref(room, it["c"])}, {zt}'
        return f'- {pos}{it["name"]}'
    best = None
    hint = WALL_HINT.get(it.get('key'))
    for lab, pL, pR in D.RWALLS.get(room, []):
        if hint and lab != hint:
            continue
        W = EL.wall_geom(room, lab)
        s0, s1, d0, d1 = EL.proj_rect(W, r)
        if s1 > 0 and s0 < W['L'] and d0 <= 60:
            if best is None or (d1 - d0) < (best[4] - best[3]):
                best = (lab, s0, s1, d0, d1)
    if best:
        lab, s0, s1, d0, d1 = best
        gap = f', отступ от стены {round(d0)}' if d0 > 5 else ''
        return (f'- {pos}{it["name"]}: у стены {D.wall_span(room, lab)}, от левого края стены {round(max(s0, 0))} до {round(s1)}, '
                f'глубина {round(d1 - d0)}{gap}, {zt}')
    c = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
    return f'- {pos}{it["name"]}: центр — {ceiling_ref(room, c)}; габарит {round(r[2]-r[0])}×{round(r[3]-r[1])}, {zt}'


def room_file(room):
    info = D.ROOM[room]
    lines = [f'# {room} {info["name"]} — параметры', '',
             f"Статус: {PROJECT.get('status', '')}. Источник для листов {PROJECT['cipher']}.", '',
             '## Помещение']
    lines.append(f'- Площадь {num(D.AREA[room], 1)} м²; пол {info["floor"]}, отм. {lvl(info["level"]) if info["level"] is not None else "уточнить"};'
                 f' потолок {lvl(info["ceil"]) if info["ceil"] else "существующий"}.')
    if room in D.RWALLS:
        ws = ', '.join(f'{D.wall_span(room, lab)} — {round(EL.wall_geom(room, lab)["L"])}' for lab, a, b in D.RWALLS[room])
        what = 'Стены между углами (буквы углов по часовой от входа' if D.CORNER_LETTERS else 'Стены (по часовой от входа'
        lines.append(f'- {what}, длина мм): {ws}. Привязки «от левого края» — при взгляде изнутри на стену.')
        if info.get('params_note'):
            lines.append('- ' + info['params_note'])
    lines += ['', '## Расстановка']
    for it in D.ITEMS:
        if it['room'] == room and it['kind'] not in ('rug', 'radiator', 'box'):
            lines.append(item_line(it, room))
    for it in D.ITEMS:
        if it['room'] == room and it['kind'] in ('radiator',):
            t = item_line(it, room)
            lines.append(t if 'уточнить' in t else t + ' (уточнить по месту)')
    lines += ['', '## Отделка']
    lines.append(f'- Пол: {info["floor"]} — {D.FINISH[info["floor"]]}.')
    wa = WA
    for (r, code), a in sorted(wa.items()):
        if r == room and a > 0.05:
            cc = code.split(' ')[0]
            lines.append(f'- Стены {code}: {num(a, 1)} м² — {D.FINISH.get(cc, "")}')
    for (r, lab, s0, s1, z0, z1, code) in D.WALL_ZONES:
        if r == room and code != 'X':
            lines.append(f'  - зона {code}: стена {D.wall_span(room, lab)}, {round(s0)}…{round(s1)} от левого края, отм. {lvl(z0)}…{lvl(z1)}')
    import plans as PL
    cc = PL.ceil_code(room)
    lines.append(f'- Потолок: {cc} — {D.FINISH[cc]}' + (f', отм. {lvl(info["ceil"])}' if info['ceil'] else ''))
    for f in D.CEIL_FEATURES:
        if f['room'] == room:
            lines.append(f'  - {f["note"]}')
    for (r, lab, s0, s1, z0, z1, tw_, th_, so, zo) in D.TILE_LAYOUT:
        if r == room:
            if so <= s0 and so + tw_ >= s1:
                lines.append(f'- Раскладка стены {D.wall_span(room, lab)} ({round(s0)}…{round(s1)}): плитка {tw_}×{th_} {"горизонтально" if tw_ > th_ else "вертикально"}, '
                             f'одна по ширине участка — без вертикальных швов, ряды от {lvl(zo)}.')
            else:
                lines.append(f'- Раскладка стены {D.wall_span(room, lab)}: плитка {tw_}×{th_}, шов от {round(so)} по горизонтали, ряды от {lvl(zo)}.')
    for (r, poly, a, b, ox, oy) in D.FLOOR_TILES:
        if r == room:
            lines.append(f'- Раскладка пола: модуль {a}×{b}, шов по линиям x={round(ox)}, y={round(oy)} (координаты плана).')
    lines += ['', '## Свет']
    for L in D.LIGHTS:
        if L['room'] != room:
            continue
        g = D.gcode(L['g'])
        if L['kind'] == 'pend':
            lines.append(f'- гр. {g}: {LKIND[L["kind"]]} — {ceiling_ref(room, L["p"])}, низ {lvl(L["z"])}'
                         + (f' ({L["note"]})' if L.get('note') else ''))
        elif 'p' in L and 'z' in L:
            w = wall_of_point(room, L['p'])
            where = f'стена {D.wall_span(room, w[0])}, {round(w[1])} от левого края' if w else ''
            lines.append(f'- гр. {g}: {LKIND[L["kind"]]} — {where}, центр {lvl(L["z"])}' + (f' ({L["note"]})' if L.get('note') else ''))
        elif 'p' in L:
            lines.append(f'- гр. {g}: {LKIND[L["kind"]]} — {ceiling_ref(room, L["p"])}' + (f' ({L["note"]})' if L.get('note') else ''))
        else:
            ln = math.hypot(L['b'][0] - L['a'][0], L['b'][1] - L['a'][1])
            lines.append(f'- гр. {g}: {LKIND[L["kind"]]} L={round(ln)} — от {ceiling_ref(room, L["a"])}' + (f' ({L["note"]})' if L.get('note') else ''))
    for g, dsc in D.GROUPS.items():
        if g[:2] == room:
            lines.append(f'  - группа {D.gcode(g)}: {dsc}')
    lines += ['', '## Инженерия']
    for P in D.POINTS:
        if P['room'] != room:
            continue
        w = wall_of_point(room, P['p'])
        where = f'стена {D.wall_span(room, w[0])}, {round(w[1])} от левого края' if w else ''
        extra = (', группы ' + ', '.join(D.gcode(g) for g in P['g'])) if P.get('g') and P['kind'] != 'tr' else ''
        note = f' — {P["note"]}' if P.get('note') else ''
        kr = KIND_RU[P['kind']] + (f' Т{P["g"][0][2:]}' if P['kind'] == 'tr' else '')
        lines.append(f'- {kr}: {where}, {lvl(P["z"])}{extra}{note}')
    for P in D.PLUMB:
        if P['room'] != room:
            continue
        w = wall_of_point(room, P['p'])
        where = f'стена {D.wall_span(room, w[0])}, {round(w[1])} от левого края' if w and P['n'] else 'в полу'
        lines.append(f'- {PKIND[P["kind"]]} ({P["fx"]}): {where}, {lvl(P["z"]) if P["z"] else "пол"}' + (f' — {P["note"]}' if P.get('note') else ''))
    for h in D.HEAT:
        if h['room'] == room:
            lines.append(f'- Тёплый пол: зона {num(D.heat_area(room), 2)} м², мат {num(D.heat_mat(room), 1)} м², {h["w"]} Вт/м²; '
                         f'не под мебелью/сантехникой/коробами (+50), трап +100, стены 50, полосы < 300 исключены; '
                         f'терморегулятор Т{room} (+0,900, см. план тёплых полов и план управления освещением).')
    for vv in D.VENT:
        if vv.get('room') == room or (vv['kind'] == 'duct' and room in vv['note']):
            lines.append(f'- Вентиляция: {vv["note"]}')
    for d in D.DOOR_SCHED:
        if room in d['where']:
            lines.append(f'- Дверь {d["mark"]}: {d["type"]}, полотно {d["leaf"]}, проём {d["opening"]}, открывание — {d["swing"]}.')
    return '\n'.join(lines) + '\n'


WA = None
_TR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
               ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u', 'f',
                'h', 'ts', 'ch', 'sh', 'sch', '', 'y', '', 'e', 'yu', 'ya']))


def slug(name):
    """Транслитерация названия помещения для имени файла: «Кухня-гостиная» -> kuhnya-gostinaya."""
    out = ''.join(_TR.get(ch, ch) for ch in name.lower())
    return '-'.join(w for w in ''.join(c if c.isalnum() else '-' for c in out).split('-') if w)


def main():
    # балкон: развёрток нет, обозначение стен вводится только для привязок в файле параметров
    global WA
    WA = TB.wall_areas()
    for k, walls in getattr(D, 'RWALLS_PARAMS', {}).items():      # стены без развёрток — только для привязок
        D.RWALLS.setdefault(k, walls)
    fin = '\n'.join(f'- {k}: {v}' for k, v in D.FINISH.items())
    import texts as TX
    tpl = getattr(TX, 'COMMON_MD', '# 00 Общие решения\n\n## Коды отделки\n{finishes}\n')
    common = tpl.format(finishes=fin, **{k: v for k, v in getattr(D, 'NCS', {}).items()})
    files = {'00-obshchee.md': common}
    for k in D.rooms_all():
        files[f'{k}-{slug(D.ROOM[k]["name"])}-parametry.md'] = room_file(k)
    for fn, txt in files.items():
        with open(os.path.join(OUT, fn), 'w', encoding='utf-8') as f:
            f.write(txt)
    print('\n'.join(files.keys()))


if __name__ == '__main__':
    main()
