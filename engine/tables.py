# -*- coding: utf-8 -*-
"""Общие данные, ведомости и спецификации — все количества считаются из единой модели."""
import math
from collections import Counter, OrderedDict
from core import Sheet, View, Pen, tw, BLACK, DARK, MID, LIGHT, WHITE, WALLFILL
import model as D
import symbols as SY
from kit import frame, notes, table, table_height, num, wrap, text_block, PROJECT, section_title, lvl, AREA_DEC


def txt(name, default=None):
    """Тексты объекта: texts.<name> (иначе — типовые из движка)."""
    import texts as T_
    v = getattr(T_, name, None)
    return default if v is None else v


def plinth_rooms():
    return [k for k in D.rooms_all() if D.ROOM[k].get('plinth')]


def wet_rooms():
    return [k for k in D.rooms_all() if D.ROOM[k].get('zone') == 'wet']


def is_tile(code):
    return D.mat(code.split(' ')[0]).get('tex') == 'tiles'


# ---------------- расчёты ----------------
def _openings_area(W, room, s0, s1, z0, z1):
    import elev as EL
    a = 0.0
    for o in EL.openings_on(W, room):
        ss0, ss1 = max(s0, o['s0']), min(s1, o['s1'])
        zz0, zz1 = max(z0, o['z0']), min(z1, o['z1'] + (40 if o['kind'] == 'door' else 0))
        if ss1 > ss0 and zz1 > zz0:
            a += (ss1 - ss0) * (zz1 - zz0)
    return a


def _behind_strips(W, room, lab, s0, s1, z0, z1, zc, L, by_code=None):
    """Полосы окраски за мебелью (D.PAINT_BEHIND) по видимым кромкам зоны X: м² (мм²).
    by_code (dict) — если задан и в design.py PAINT_BEHIND_ZONES = True, полосы у окрашиваемых зон отделки (tex='paint',
    напр. акцентная стена С2) добавляются в by_code[код] (иначе такие кромки не учитываются)."""
    import elev as EL
    P = D.PAINT_BEHIND
    zall = [(a, b, c, d, code) for (r, l2, a, b, c, d, code) in D.WALL_ZONES if r == room and l2 == lab and (a, b, c, d) != (s0, s1, z0, z1)]
    zones = [(a, b, c, d) for a, b, c, d, code in zall]
    ops = EL.openings_on(W, room)
    use_zones = by_code is not None and getattr(D, 'PAINT_BEHIND_ZONES', False)

    def painted(s, z):
        if s <= 0 or s >= L or z <= 0 or z >= zc:
            return False
        if any(a <= s <= b and c <= z <= d for a, b, c, d in zones):
            return False
        if any(o['s0'] <= s <= o['s1'] and o['z0'] <= z <= o['z1'] + 40 for o in ops):
            return False
        return True

    def paint_zone(s, z):
        if not use_zones or s <= 0 or s >= L or z <= 0 or z >= zc:
            return None
        for a, b, c, d, code in zall:
            if a <= s <= b and c <= z <= d:
                return code if (code != 'X' and D.MATERIALS.get(code, {}).get('tex') == 'paint') else None
        return None
    area = 0.0
    zm = (z0 + min(z1, zc)) / 2
    h = min(z1, zc) - z0
    sm = (s0 + s1) / 2
    for (s_, z_, a_) in ((s0 - 20, zm, P * h), (s1 + 20, zm, P * h), (sm, min(z1, zc) + 20, P * (s1 - s0))):
        if painted(s_, z_):
            area += a_
        else:
            c_ = paint_zone(s_, z_)
            if c_:
                by_code[c_] = by_code.get(c_, 0.0) + a_
    return area


def wall_areas():
    """{(room, code): м²} для стен: зоны отделки + окраска по остатку (за вычетом проёмов).
    За встроенной и неподвижной мебелью (зоны X) окраска не считается, кроме полос D.PAINT_BEHIND по видимым кромкам."""
    import elev as EL
    res = Counter()
    for room, walls in D.RWALLS.items():
        zf = D.ROOM[room]['level'] or 0
        zc = D.ROOM[room]['ceil']
        for lab, pL, pR in walls:
            W = EL.wall_geom(room, lab)
            L = W['L']
            total = L * (zc - zf) - _openings_area(W, room, 0, L, zf, zc)
            used = 0.0
            for (r, l2, s0, s1, z0, z1, code) in D.WALL_ZONES:
                if r != room or l2 != lab:
                    continue
                z1c = min(z1, zc)
                ar = (s1 - s0) * (z1c - z0) - _openings_area(W, room, s0, s1, z0, z1c)
                if code != 'X':
                    res[(room, code)] += ar / 1e6
                    used += ar
                else:
                    extra = {}
                    used += ar - _behind_strips(W, room, lab, s0, s1, z0, z1, zc, L, by_code=extra)
                    for c_, a_ in extra.items():        # полосы у окрашиваемых зон (PAINT_BEHIND_ZONES)
                        res[(room, c_)] += a_ / 1e6
            dflt = D.WALL_DEFAULT.get(room)
            if dflt:
                rest = total - used
                if rest > 0:
                    res[(room, dflt)] += rest / 1e6
    for room, code, a in getattr(D, 'EXTRA_WALL_AREAS', []):
        res[(room, code)] += a
    return res


def floor_areas():
    import plans as PL
    return PL.floor_areas()


def tile_quantities():
    q = Counter()
    wa = wall_areas()
    for (room, code), a in wa.items():
        if is_tile(code):
            q[(room, code)] += a
    fa = floor_areas()
    for room in wet_rooms():
        q[(room, D.ROOM[room]['floor'])] += fa[room]
    return q


def plinth_lengths():
    """Плинтус ПЛ: периметр минус дверные проёмы и встроенная мебель/кухня у стен (м)."""
    import elev as EL
    res = {}
    for room in plinth_rooms():
        tot = 0.0
        for lab, pL, pR in D.RWALLS[room]:
            W = EL.wall_geom(room, lab)
            L = W['L']
            cuts = []
            for o in EL.openings_on(W, room):
                if o['kind'] in ('door', 'bdoor'):
                    cuts.append((o['s0'], o['s1']))
            for it in D.ITEMS:
                if it['room'] != room or it['kind'] not in ('wardrobe', 'kitchen_run', 'column', 'filler', 'bench'):
                    continue
                r = EL.item_rect(it)
                s0, s1, d0, d1 = EL.proj_rect(W, r)
                if d0 <= 60:
                    cuts.append((max(0, s0), min(L, s1)))
            from kit import subtract_intervals
            tot += sum(b - a for a, b in subtract_intervals((0, L), cuts))
        res[room] = tot / 1000
    return res


def ceiling_areas():
    return {k: D.AREA[k] for k in D.AREA}


# ---------------- 03 ДИЗАЙН-ПРОЕКТ (цветной план) ----------------
def sheet_design(no, total):
    """Планировочное решение в цвете: фактуры полов, мебель по группам цвета, материалы проекта."""
    import textures as T
    import drawplan as DP
    import plans as PL
    sh = Sheet('03', 'Дизайн-проект')
    v = DP.new_view()
    pen = Pen(sh, v)
    k = v.k
    for room, info in D.ROOM.items():
        poly = D.ROOMS[room]['poly']
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        code = info['floor']
        Wr, Hr = y1 - y0, x1 - x0
        kw = {'axis': D.mat(code).get('plan_axis', 'x')} if D.mat(code).get('tex') == 'herringbone' else {}
        path = T.make(code, Wr, Hr, k, dpi=160, **kw)
        bl = v.P(x1, y0)
        clip = [v.P(*p) for p in poly]
        sh.image(path, bl[0], bl[1], Wr / k, Hr / k, clip=clip)
    for room, ppoly, a, b, ox, oy in D.FLOOR_TILES:
        PL.tile_grid(sh, v, ppoly, a, b, ox, oy, color=(0.55, 0.55, 0.55), lw=0.08)
    DP.COLORED['on'] = True
    DP.COLORED['words'] = True
    try:
        DP.draw_items(pen, skip=('rug',))
    finally:
        DP.COLORED['on'] = False
        DP.COLORED['words'] = False
    DP.draw_walls(pen, fill=(0.30, 0.30, 0.32))
    DP.draw_openings(pen)
    DP.room_tags(sh, v, pos=PL.tag_pos('design'), names=True, small_rooms_noname=True)
    PL.title(sh, 'ДИЗАЙН-ПРОЕКТ. ПЛАНИРОВОЧНОЕ РЕШЕНИЕ  М 1:50', 'материалы полов, мебель и оборудование по группам цвета')
    # материалы проекта
    y = 92
    sh.text((25, y + 4), 'Материалы проекта', h=2.8, layer='A-TEXT', font='BoldObl')
    items = txt('DESIGN_MATERIALS') or [(c, PL.mat_name(c)) for c in D.FINISH if not c.startswith('Пт') and c != 'ПЛ'][:10]
    SW = 15.0
    for i, (c, txt_) in enumerate(items):
        col, row = i % 5, i // 5
        x = 25 + col * 41
        yy = y - row * 30
        sh.image(T.swatch_for(c, SW), x, yy - SW, SW, SW)
        sh.rect(x, yy - SW, x + SW, yy, lw=0.2, layer='A-TEXT')
        sh.text((x + SW + 1.5, yy - 3), c, h=2.4, layer='A-TEXT', font='BoldObl')
        text_block(sh, x + SW + 1.5, yy - 6.5, 22, txt_, h=1.6, lead=2.3)
    if txt('STYLE'):
        text_block(sh, 233, 92, 178, txt('STYLE'), h=2.2, lead=3.3)

    def swc(col_):
        return lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=col_, lw=0.2, color=DARK)
    from kit import legend_box
    leg = PL.ann('FURN', 'legend_short') or [('built', 'Встроенная мебель'), ('walnut', 'Шпон ореха'), ('oak', 'Дуб'),
                                              ('soft', 'Мягкая мебель'), ('appl', 'Бытовая техника'), ('sani', 'Сантехника')]
    legend_box(sh, 376, 281, [(swc(DP.PAL[k_]), t_) for k_, t_ in leg], width=26, title='Цвета')
    frame(sh, no, total, 'Дизайн-проект.\nПланировочное решение')
    return sh


# ---------------- 02–03 ОБЩИЕ ДАННЫЕ ----------------
GENERAL_DEFAULT = [
    'Дизайн-проект разработан по обмерному плану заказчика; из референсов принята только стилистика.',
    'Размеры — в мм, отметки — в м. ±0,000 — уровень чистого пола жилых помещений. Высоты выводов — от ±0,000, размеры на развёртках — от чистого пола помещения.',
    'Размеры стен даны по обмеру без учёта выравнивающего слоя; привязки выводов и мебели — от чистовой поверхности стен. После штукатурных работ — контрольный обмер.',
    'Несущие конструкции не изменяются.',
    'Электромонтаж — по отдельному электропроекту (нагрузки, щит, группы) на основании планов освещения, управления освещением и розеток. Линии санузлов и балкона — через УЗО 30 мА (ГОСТ Р 50571.7.701-2013).',
    'Выключатели и терморегуляторы — +0,900 по всей квартире; от края дверного проёма до оси первого поста — не менее 100 мм. Изделия на одной высоте — в общих рамках. Код группы света одинаковый у светильника и выключателя.',
    'Самотёчная канализация — ПП трубы с уклоном не менее 2 %; подводки ХВС/ГВС — PEX без соединений в стяжке.',
    'Гидроизоляция санузлов: пол + стены на 200, в душевой зоне — до +2,000; в местах примыканий — армирующая лента.',
    'Отделочные материалы указаны по типу и характеристикам; производитель и артикулы — по согласованию с заказчиком. Запас: 10 %, ёлочка/диагональ — 15 %.',
    'Все размеры проверить по месту до начала работ; расхождения с проектом — сообщить автору. Допущения отмечены «уточнить по месту».',
]

REFS = [
    ['ГОСТ Р 21.101-2020', 'СПДС. Основные требования к проектной и рабочей документации'],
    ['ГОСТ 21.501-2018', 'СПДС. Правила выполнения рабочей документации АР и КР'],
    ['ГОСТ 21.210-2014', 'СПДС. Изображения условные графические электрооборудования на планах'],
    ['ГОСТ 21.608-2014', 'СПДС. Правила выполнения рабочей документации внутреннего электрического освещения'],
    ['ГОСТ 21.601-2011', 'СПДС. Правила выполнения рабочей документации внутренних систем водоснабжения и канализации'],
    ['ГОСТ Р 50571.7.701-2013', 'Электроустановки. Ванные и душевые помещения'],
    ['СП 54.13330.2022', 'Здания жилые многоквартирные'],
    ['СП 30.13330.2020', 'Внутренний водопровод и канализация зданий'],
    ['СП 71.13330.2017', 'Изоляционные и отделочные покрытия'],
    ['СП 29.13330.2011', 'Полы'],
    ['ПП РФ от 28.01.2006 № 47', 'Положение о признании помещения жилым… (п. 24 — размещение кухонь и санузлов)'],
]


def sheet_general(no, total, sheet_list):
    sh = Sheet('02', 'Общие данные')
    rows = [[str(i), name, ''] for i, (k, name, fn) in enumerate(sheet_list, 1)]
    yb = table(sh, 25, 280, [12, 162, 12], ['Лист', 'Наименование', 'Прим.'], rows, aligns=['c', 'l', 'c'],
               row_h=3.9, h=1.75, head_h=5.5, title='Ведомость листов рабочей документации', title_h=2.6)
    tot = D.total_area()

    def lv(k):
        return 'уточн.' if D.ROOM[k]['level'] is None else lvl(D.ROOM[k]['level'])
    er = [[k, D.ROOM[k]['name'], num(D.AREA[k], AREA_DEC()), D.ROOM[k]['floor'], lv(k)] for k in D.rooms_counted()]
    er.append(['', '**Итого по квартире', '**' + num(tot, AREA_DEC()), '', ''])
    er += [[k, D.ROOM[k]['name'] + ' (в итог не входит)', num(D.AREA[k], AREA_DEC()), D.ROOM[k]['floor'], lv(k)] for k in D.rooms_outdoor()]
    table(sh, 222, 280, [12, 82, 26, 26, 40], ['№', 'Наименование', 'Площадь, м²', 'Пол', 'Отметка пола'], er,
          aligns=['c', 'l', 'r', 'c', 'c'], row_h=4.4, h=1.8, head_h=5.5, title='Экспликация помещений', title_h=2.6)
    table(sh, 222, 230, [42, 144], ['Обозначение', 'Наименование'], txt('REFS', REFS), aligns=['l', 'l'], wraps=[False, True],
          row_h=4.0, h=1.65, head_h=5, title='Ведомость ссылочных нормативных документов (действующие редакции)', title_h=2.4)
    # схема квартиры с номерами помещений
    import drawplan as DP
    import plans as PL
    sv = PL.ann('SCHEME_VIEW') or scheme_view_default()
    v = View(sv['X0'], sv['Y0'], sv['k'])
    pen = Pen(sh, v)
    DP.draw_zones(pen)
    DP.draw_walls(pen)
    DP.draw_openings(pen)
    DP.room_tags(sh, v, names=False, small_rooms_noname=True)
    sh.text((sv['X0'], sv['Y0'] + 8), f"Схема помещений  М 1:{int(sv['k'])}", h=2.4, layer='A-TEXT', font='BoldObl')
    frame(sh, no, total, 'Общие данные. Ведомость листов,\nэкспликация помещений')
    return sh


def sheet_notes(no, total):
    from kit import level_box, bubble, legend_box
    sh = Sheet('03', 'Общие указания')
    y = notes(sh, 25, 282, 188, 'Общие указания', txt('GENERAL', GENERAL_DEFAULT), h=2.1, lead=3.15)
    rows = [[a, b, c] for a, b, c in txt('CHECKS', [])]
    table(sh, 222, 280, [62, 104, 20], ['Проверка / конфликт', 'Решение в проекте', 'Статус'], rows,
          aligns=['l', 'l', 'c'], wraps=[True, True, False], row_h=4.4, h=1.8, head_h=5.5,
          title='Сквозная проверка решений', title_h=2.6)

    def tagfn(code):
        def f(s, x, y):
            w = tw(code, 1.9, 'BoldObl') + 2.0
            s.rect(x - w / 2, y - 1.5, x + w / 2, y + 1.5, fill=WHITE, lw=0.3, layer='A-TEXT')
            s.text((x, y), code, h=1.9, ha='c', va='m', layer='A-TEXT', font='BoldObl')
        return f
    items = [
        (lambda s, x, yy: level_box(s, (x, yy), '+0,020'), 'Отметка уровня чистого пола на плане, м'),
        (lambda s, x, yy: bubble(s, (x, yy), 'С1', h=1.4), 'Позиция сантехники / техники (см. спецификацию)'),
        (tagfn('С3'), 'Код отделки (см. ведомость отделки и спецификацию материалов)'),
        (lambda s, x, yy: s.text((x, yy), '3Д', h=2.0, ha='c', va='m', layer='A-TEXT', font='BoldObl',
                                 color=(0.75, 0.45, 0.0)), 'Группа освещения: номер помещения + буква'),
        (lambda s, x, yy: (s.circle((x, yy), 2.0, lw=0.3, layer='A-TEXT', fill=WHITE),
                           s.text((x, yy), 'Б', h=1.8, ha='c', va='m', layer='A-TEXT', font='BoldObl')),
         'Угол помещения на схеме (А, Б, В… по часовой от входа); развёртка «А–Б» — стена между углами' if D.CORNER_LETTERS
         else 'Обозначение стены на схеме развёрток (А, Б, В… по часовой от входа)'),
        (lambda s, x, yy: SY.light_c(s, (x, yy), 'spot'), 'Светильники — красным; одной группы — связаны пунктиром (LED-ленты — без связи)'),
        (lambda s, x, yy: SY.outlet_c(s, (x, yy - 1.3), (0, 1), 'r2'), 'Розетки — красным, у каждой — высота до низа рамки'),
        (lambda s, x, yy: SY.switch_c(s, (x - 1.5, yy - 1.5), (0, 1), 'v1'), 'Выключатели — синим, терморегуляторы — оранжевым'),
        (lambda s, x, yy: (s.poly([(x - 2.3, yy), (x - 1.15, yy + 2), (x + 1.15, yy + 2), (x + 2.3, yy), (x + 1.15, yy - 2), (x - 1.15, yy - 2)],
                                  lw=0.35, fill=(0.85, 0.94, 0.88), color=(0.15, 0.55, 0.35)),
                           s.text((x, yy), 'Д2', h=1.5, ha='c', va='m', font='BoldObl', color=(0.15, 0.55, 0.35))),
         'Тип двери (одинаковые двери — один тип)'),
    ]
    legend_box(sh, 25, max(y - 8, 70), items, width=150, title='Основные обозначения', sym_w=10)
    frame(sh, no, total, 'Общие указания.\nСквозная проверка решений')
    return sh


# ---------------- 26 ВЕДОМОСТЬ ОТДЕЛКИ ----------------
def sheet_finish_schedule(no, total):
    sh = Sheet('26', 'Ведомость отделки помещений')
    wa = wall_areas()
    fa = floor_areas()
    pl = plinth_lengths()
    import plans as PL
    rows = []
    for k in D.rooms_all():
        info = D.ROOM[k]
        c = PL.ceil_code(k)
        ceil = f'{c} ({lvl_txt(info["ceil"])}) — {num(D.ceil_area(k) if info["ceil"] else D.AREA[k], 1)}'
        walls = []
        for (r, code), a in sorted(wa.items()):
            if r == k and a > 0.05:
                walls.append(f'{code} — {num(a, 1)}')
        if info.get('walls_note'):
            walls = [info['walls_note']]
        fl = f'{info["floor"]} — {num(fa[k], 1)}'
        plt = f'ПЛ — {num(pl[k], 1)} м' if k in pl else '—'
        note = info.get('finish_note', '')
        rows.append([k + ' ' + info['name'], ceil, '; '.join(walls), fl, plt, note])
    yb = table(sh, 23, 280, [44, 50, 130, 42, 30, 94], ['Помещение', 'Потолок (код, отм., м²)', 'Стены (код — м²)',
                                                       'Пол (код — м²)', 'Плинтус', 'Примечание'], rows,
               aligns=['l', 'l', 'l', 'l', 'l', 'l'], wraps=[True, True, True, True, False, True], row_h=8.0, h=2.1,
               head_h=7, title='Ведомость отделки помещений', title_h=3.0)
    import textures as T
    y = yb - 12
    sh.text((23, y), 'Расшифровка кодов отделки', h=2.8, layer='A-TEXT', font='BoldObl')
    y -= 5
    codes = list(D.FINISH.keys())
    half = (len(codes) + 1) // 2
    SW = 10.0
    for i, c in enumerate(codes):
        x = 23 if i < half else 222
        top = y - (i if i < half else i - half) * 12.5
        sh.image(T.swatch_for(c, SW), x, top - SW, SW, SW)
        sh.rect(x, top - SW, x + SW, top, lw=0.2, layer='A-TEXT')
        w = tw(c, 2.0, 'BoldObl') + 2.4
        sh.rect(x + SW + 2, top - 3.4, x + SW + 2 + w, top - 0.2, fill=WHITE, lw=0.3, layer='A-TEXT')
        sh.text((x + SW + 2 + w / 2, top - 1.8), c, h=2.0, ha='c', va='m', layer='A-TEXT', font='BoldObl')
        text_block(sh, x + SW + 4 + w, top - 2.4, 172 - w, D.FINISH[c], h=1.9, lead=2.8)
    notes(sh, 23, 52, 200, 'Примечания', txt('FINISH_NOTES', [
        'Площади стен — за вычетом проёмов. За встроенной и неподвижной мебелью окраска не считается: заводится за мебель на 150 мм по видимым кромкам.',
        'Потолки — за вычетом встроенной мебели до потолка. Полы — за вычетом участков под встроенной мебелью.',
        'Образцы — условное изображение фактуры и цвета материала.']), h=1.9, lead=2.9)
    frame(sh, no, total, 'Ведомость отделки помещений')
    return sh


def lvl_txt(z):
    if z is None:
        return 'сущ.'
    return '+' + f'{z / 1000:.3f}'.replace('.', ',')


# ---------------- 27 СПЕЦИФИКАЦИЯ МАТЕРИАЛОВ ----------------
def sheet_materials(no, total):
    sh = Sheet('27', 'Спецификация отделочных материалов')
    wa = wall_areas()
    fa = floor_areas()
    pl = plinth_lengths()
    by = Counter()
    rooms = {}
    for (r, c), a in wa.items():
        key = c.split(' ')[0]
        by[key] += a
        rooms.setdefault(key, set()).add(r)
    for r in fa:
        c = D.ROOM[r]['floor']
        by[c] += fa[r]
        rooms.setdefault(c, set()).add(r)
    import plans as PL
    for r, c in ((k, PL.ceil_code(k)) for k in D.rooms_all()):
        by[c] += D.ceil_area(r) if D.ROOM[r]['ceil'] else D.AREA[r]
        rooms.setdefault(c, set()).add(r)
    order = [c for c in D.FINISH if D.mat(c).get('tex') != 'plinth']
    import textures as T
    SW = 11.0
    rows = []
    for c in order:
        if by[c] <= 0:
            continue
        m = D.mat(c)
        zap = 0.0 if m.get('tex') == 'paint' else PL.reserve(c)
        net = by[c]
        extra = m.get('spec_note', '')
        if m.get('tex') == 'slats':
            extra = f"≈ {net / (m.get('step', 60) / 1000) * 1.1:.0f} п. м реек"
        if m.get('tex') == 'paint':
            extra = 'расход — по ТУ (2 слоя)'
        rows.append([dict(img=T.swatch_for(c, SW), w=SW, h=SW), c, D.FINISH[c], ', '.join(sorted(rooms[c])), num(net, 2),
                     (f'{int(zap * 100)} %' if zap else '—'), num(net * (1 + zap), 1), extra])
    for pc in [c for c in D.FINISH if D.mat(c).get('tex') == 'plinth'][:1]:
        rows.append([dict(img=T.swatch_for(pc, SW), w=SW, h=SW), pc, D.FINISH[pc], ', '.join(plinth_rooms()),
                     num(sum(pl.values()), 1) + ' м', '10 %', num(sum(pl.values()) * 1.1, 1) + ' м', ''])
    table(sh, 23, 280, [14, 10, 128, 22, 16, 12, 18, 36], ['Образец', 'Код', 'Материал', 'Пом.', 'Нетто,\nм²', 'Запас',
                                                          'К заказу,\nм²', 'Примечание'], rows,
          aligns=['c', 'c', 'l', 'c', 'r', 'c', 'r', 'l'], wraps=[False, False, True, True, False, False, False, True],
          row_h=4.8, h=1.75, head_h=6.5, title='Спецификация отделочных материалов', title_h=2.8)
    notes(sh, 290, 280, 122, 'Примечания', txt('MATERIALS_NOTES', [
        'Площади посчитаны по модели проекта; перед закупкой — контрольный обмер после черновых работ.',
        'Запас: плитка, панели, рейки — 10 %; ёлочка — 15 % (подрезка по периметру).',
        'Образцы — условное изображение фактуры и цвета; окончательный выбор — по физическим образцам.',
        'Клей, затирка, грунт, гидроизоляция, профили — по технологическим картам производителей.',
    ]), h=1.9, lead=2.9)
    frame(sh, no, total, 'Спецификация отделочных\nматериалов')
    return sh


# ---------------- 28 САНТЕХНИКА И ТЕХНИКА ----------------
def sheet_sanitary(no, total):
    sh = Sheet('28', 'Спецификация сантехники и техники')
    rows = [[a, b, c, str(d)] for a, b, c, d in txt('SANT', [])]
    table(sh, 23, 280, [12, 16, 160, 10], ['Поз.', 'Пом.', 'Наименование, характеристики', 'Кол.'], rows,
          aligns=['c', 'c', 'l', 'c'], wraps=[False, False, True, False], row_h=4.6, h=1.8, head_h=6,
          title='Спецификация сантехнического оборудования и бытовой техники', title_h=2.6)
    rows2 = txt('SANT_OUTPUTS') or sant_outputs_default()
    table(sh, 233, 280, [16, 12, 30, 30, 40], ['Поз.', 'Пом.', 'ХВС', 'ГВС', 'Канализация'], rows2,
          aligns=['c', 'c', 'c', 'c', 'c'], row_h=4.4, h=1.75, head_h=5.5, title='Выводы сантехприборов (от ±0,000)', title_h=2.4)
    notes(sh, 233, 220, 178, 'Примечания', txt('SANT_NOTES', [
        'Модели — по выбору заказчика в указанных габаритах; привязки выводов — по плану сантехники и развёрткам.',
        'Встраиваемая техника — по размерам ниш мебели (уточнить у изготовителя).']), h=1.9, lead=2.9)
    frame(sh, no, total, 'Спецификация сантехники\nи бытовой техники')
    return sh


# ---------------- 29 СВЕТИЛЬНИКИ ----------------
LTYPES_DEFAULT = OrderedDict([
    ('spot', ('Л1', 'Светильник встраиваемый поворотный, Ø80, GU10 LED 7 Вт, 3000 K, CRI≥90, чёрный', 'шт')),
    ('spot44', ('Л2', 'То же, IP44 (санузлы)', 'шт')),
    ('spot65', ('Л3', 'Светильник встраиваемый IP65 (душевая зона)', 'шт')),
    ('track', ('Л4', 'Магнитный трек встраиваемый 48 В L=2000 + 4 спота 10 Вт + линейный модуль 20 Вт, чёрный', 'компл.')),
    ('pend', ('Л5', 'Подвесной светильник «кольцо» Ø600, LED 30 Вт, 3000 K', 'шт')),
    ('led', ('Л6', 'Светодиодная лента 2700–3000 K 10 Вт/м в алюм. профиле с рассеивателем + блоки питания', 'п. м')),
    ('linear', ('Л7', 'Светильник линейный накладной 1200, 24 Вт, 3000 K, чёрный', 'шт')),
    ('sconce', ('Л8', 'Бра настенное (прихожая — вертикальное линейное на зеркале; спальня — бра с поворотом)', 'шт')),
    ('wall44', ('Л9', 'Светильник настенный IP44 (балкон)', 'шт')),
    ('fan', ('В1/В2', 'Вентилятор вытяжной бесшумный с таймером и обратным клапаном', 'шт')),
])


def light_counts():
    cnt = Counter()
    rooms = {}
    for L in D.LIGHTS:
        k = L['kind']
        if k == 'mirrorled':
            continue
        if k == 'led':
            a, b = L['a'], L['b']
            cnt[k] += math.hypot(b[0] - a[0], b[1] - a[1]) / 1000
        else:
            cnt[k] += 1
        rooms.setdefault(k, set()).add(L['room'])
    return cnt, rooms


def sheet_lights(no, total):
    sh = Sheet('29', 'Спецификация светильников')
    cnt, rooms = light_counts()
    rows = []
    for k, (mark, name, unit) in OrderedDict(txt('LTYPES') or LTYPES_DEFAULT).items():
        if cnt[k] <= 0:
            continue
        q = cnt[k]
        qs = f'{q * 1.1:.1f}' if k == 'led' else str(int(q))
        rows.append([mark, name, ', '.join(sorted(rooms[k])), unit, qs.replace('.', ',')])
    table(sh, 23, 280, [14, 170, 30, 14, 14], ['Марка', 'Наименование, характеристики', 'Пом.', 'Ед.', 'Кол.'], rows,
          aligns=['c', 'l', 'c', 'c', 'r'], wraps=[False, True, False, False, False], row_h=5.0, h=1.8, head_h=6,
          title='Спецификация светильников', title_h=2.8)
    # по помещениям и группам
    rows2 = []
    for g, desc in D.GROUPS.items():
        n = sum(1 for L in D.LIGHTS if L['g'] == g and L['kind'] not in ('led',))
        ln = sum(math.hypot(L['b'][0] - L['a'][0], L['b'][1] - L['a'][1]) / 1000 for L in D.LIGHTS
                 if L['g'] == g and L['kind'] == 'led')
        q = (f'{n} шт' if n else '') + ((' + ' if n else '') + f'{ln:.1f} м ленты'.replace('.', ',') if ln else '')
        rows2.append([g[:2], D.gcode(g), desc.split('—', 1)[-1].strip(), q])
    table(sh, 23, 150, [12, 14, 120, 40], ['Пом.', 'Код\nгруппы', 'Назначение', 'Состав'], rows2,
          aligns=['c', 'c', 'l', 'l'], row_h=3.9, h=1.65, head_h=5, title='Группы освещения', title_h=2.4)
    notes(sh, 233, 98, 178, 'Примечания', txt('LIGHTS_NOTES', [
        'Лента — с запасом 10 %; блоки питания — в доступных местах, с запасом мощности 30 %.',
        'Конкретные модели — по согласованию с заказчиком в указанных параметрах.']), h=1.9, lead=2.9)
    frame(sh, no, total, 'Спецификация светильников')
    return sh


# ---------------- 30 ЭУИ ----------------
def eui_counts():
    c = Counter()
    for P in D.POINTS:
        k = P['kind']
        if k == 'r1':
            c['Розетка одинарная с заземлением 16 А'] += 1
        elif k == 'r2':
            c['Розетка двойная с заземлением 16 А'] += 1
        elif k == 'r2u':
            c['Розетка двойная с USB-A/C'] += 1
        elif k == 'r1w':
            c['Розетка одинарная IP44 с крышкой'] += 1
        elif k == 'r2w':
            c['Розетка двойная IP44 с крышкой'] += 1
        elif k == 'tvblock':
            c['Розетка двойная с заземлением 16 А'] += 1
            c['Розетка TV'] += 1
            c['Розетка компьютерная RJ45 cat.6'] += 1
        elif k == 'medblock':
            c['Розетка двойная с заземлением 16 А'] += 1
            c['Розетка компьютерная RJ45 cat.6'] += 1
        elif k == 'deskblock':
            c['Розетка двойная с заземлением 16 А'] += 1
            c['Розетка одинарная с заземлением 16 А'] += 1
            c['Розетка компьютерная RJ45 cat.6'] += 1
        elif k == 'v1':
            c['Выключатель одноклавишный'] += 1
        elif k == 'v2':
            c['Выключатель двухклавишный'] += 1
        elif k == 'v1p':
            c['Выключатель одноклавишный проходной'] += 1
        elif k == 'v2p':
            c['Выключатель двухклавишный проходной'] += 1
        elif k == 'tr':
            c['Терморегулятор тёплого пола программируемый (в рамку серии)'] += 1
        elif k == 'pow':
            c['Кабельный вывод (варочная панель, 32 А)'] += 1
        elif k == 'out':
            c['Кабельный вывод (подсветка, кондиционер, полотенцесушитель, зеркало)'] += 1
        elif k == 'int':
            c['Домофон (трубка) — по системе дома'] += 1
        elif k == 'shk':
            c['Щит квартирный ЩК (по электропроекту)'] += 1
        elif k == 'ssh':
            c['Щит слаботочный СЩ (роутер, кросс RJ45/TV)'] += 1
    return c


def sheet_eui(no, total):
    import pts as PT
    sh = Sheet('30', 'Спецификация ЭУИ')
    c = eui_counts()
    rows = [[str(i), k, 'шт', str(v)] for i, (k, v) in enumerate(sorted(c.items(), key=lambda t: t[0]), 1)]
    # рамки: по местам установки (кластеры) отдельно для розеток и выключателей
    sw = [P for P in D.POINTS if P['kind'] in ('v1', 'v2', 'v1p', 'v2p', 'tr')]
    ot = [P for P in D.POINTS if P['kind'] in ('r1', 'r2', 'r2u', 'r1w', 'r2w', 'tvblock', 'medblock', 'deskblock')]
    frames = Counter()
    for key, cl in PT.clusters(sw, gap=160):
        n = len(cl)
        frames[f'Рамка {n}-постовая (выключатели)'] += 1
    for P in ot:
        n = {'r1': 1, 'r1w': 1, 'r2': 2, 'r2u': 2, 'r2w': 2, 'tvblock': 4, 'medblock': 3, 'deskblock': 4}[P['kind']]
        frames[f'Рамка {n}-постовая (розетки)'] += 1
    for k, v in sorted(frames.items()):
        rows.append([str(len(rows) + 1), k, 'шт', str(v)])
    table(sh, 23, 280, [12, 150, 12, 14], ['№', 'Наименование', 'Ед.', 'Кол.'], rows, aligns=['c', 'l', 'c', 'r'],
          row_h=4.2, h=1.8, head_h=5.5, title='Спецификация электроустановочных изделий', title_h=2.8)
    notes(sh, 233, 280, 178, 'Примечания', txt('EUI_NOTES', [
        'Серия ЭУИ — по согласованию с заказчиком.',
        'Высоты: выключатели и терморегуляторы +0,900; розетки +0,300, у столешницы +1,100, у кровати +0,650.',
        'Розетки в санузле и на балконе — IP44; все линии санузлов — через УЗО 30 мА.']), h=1.9, lead=2.9)
    frame(sh, no, total, 'Спецификация\nэлектроустановочных изделий')
    return sh




def sant_outputs_default():
    """Выводы приборов из PLUMB: (прибор, пом., ХВС, ГВС, канализация)."""
    by = OrderedDict()
    for P in D.PLUMB:
        fx = P.get('fx', '').split(' ')[0]
        r = by.setdefault((fx, P['room']), {'hvs': '—', 'gvs': '—', 'k': '—'})
        z = '+' + f"{P['z'] / 1000:.3f}".replace('.', ',') if P['z'] else 'в полу'
        if P['kind'] == 'hvs':
            r['hvs'] = z
        elif P['kind'] == 'gvs':
            r['gvs'] = z
        elif P['kind'] == 'tap':
            r['hvs'] = 'кран ' + z
        elif P['kind'] in ('k50', 'k110', 'sif'):
            r['k'] = {'k50': '', 'k110': '', 'sif': 'сифон '}[P['kind']] + z
    return [[fx, room, r['hvs'], r['gvs'], r['k']] for (fx, room), r in by.items()]


def scheme_view_default():
    """Схема помещений М 1:100 в правой половине листа общих данных."""
    xs, ys = D.wall_extent()
    k = 100.0
    return dict(X0=250 - min(ys) / k, Y0=158 + min(xs) / k, k=k)
