# -*- coding: utf-8 -*-
"""Листы-планы 03–15 (М 1:50)."""
import math
from core import Sheet, Pen, mdim, tw, BLACK, DARK, MID, LIGHT, WHITE, WALLFILL, FILL_LT, Z_DAY, Z_NIGHT, Z_WET
import obmer as MV
import model as D
import drawplan as DP
import symbols as SY
from kit import (frame, notes, table, table_height, legend_box, leader, bubble, num, lvl, poly_scan,
                 clip_poly_convex, wrap, text_block, section_title, level_box, AREA_DEC)

RED = (0.85, 0.12, 0.12)
DEMO = dict(lw=0.35, layer='A-DEMO', color=RED, dash=(1.6, 0.9))
NEWC = (0.55, 0.35, 0.10)
ROD = (0.55, 0.20, 0.60)       # карнизы, шторы
BLUEW = (0.05, 0.30, 0.65)     # техника словами
COLORS = {'brown': SY.BROWN, 'blue': SY.BLUE, 'red': SY.RED, 'rod': ROD, 'eq': BLUEW, 'dark': DARK, 'mid': MID,
          'black': BLACK}


def ann(name, key=None, default=None):
    """Данные оформления объекта: annot.<name>[key] (или весь словарь)."""
    import annot as A
    d = getattr(A, name, None)
    if d is None:
        return default
    if key is None:
        return d
    return d.get(key, default)


def _kw(kw):
    kw = dict(kw or {})
    if isinstance(kw.get('color'), str):
        kw['color'] = COLORS[kw['color']]
    return kw


def bearing_legend():
    """Пункт легенды несущих стен (если в design.py задан BEARING_MIN)."""
    bm = getattr(D, 'BEARING_MIN', None)
    if bm is None:
        return []
    return [(lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=DP.BEARFILL, lw=0.5, layer='A-TEXT'),
             getattr(D, 'BEARING_LABEL', f'Несущие стены (толщина > {bm})'))]


def put_labels(sh, v, lst, **dflt):
    """Подписи: (точка, текст, h[, kw]) -> текст с подложкой по центру точки."""
    for e in lst or []:
        kw = dict(ha='c', va='m', layer='A-TEXT', bg=True)
        kw.update(dflt)
        kw.update(_kw(e[3] if len(e) > 3 else None))
        sh.text(v.P(*e[0]), e[1], h=e[2], **kw)


def draw_prims(sh, v, pen, prims):
    """Упорядоченный список элементов оформления (см. annot.py)."""
    for e in prims or []:
        t = e[0]
        if t == 'label':
            put_labels(sh, v, [e[1:]])
        elif t == 'dim':
            kw = _kw(e[5] if len(e) > 5 else None)
            mdim(sh, v, e[1], e[2], e[3], ext=e[4] if len(e) > 4 else None, **kw)
        elif t == 'bubble':
            kw = dict(r=2.0, h=1.6); kw.update(_kw(e[3] if len(e) > 3 else None))
            bubble(sh, v.P(*e[1]), e[2], **kw)
        elif t == 'level':
            level_box(sh, v.P(*e[1]), e[2])
        elif t == 'line':
            kw = dict(lw=0.25, layer='A-TEXT'); kw.update(_kw(e[3] if len(e) > 3 else None))
            pen.line(e[1], e[2], **kw)
        elif t == 'rect':
            kw = dict(lw=0.25, layer='A-TEXT'); kw.update(_kw(e[2] if len(e) > 2 else None))
            pen.rect(*e[1], **kw)


def mat(code):
    return D.mat(code)


def reserve(code):
    """Запас материала (доля): MATERIALS[code]['reserve'] или по типу (ёлочка/диагональ — 15 %, остальное — 10 %)."""
    m = mat(code)
    if 'reserve' in m:
        return m['reserve']
    return 0.15 if m.get('tex') == 'herringbone' or m.get('diag') else 0.10


def mat_name(code):
    m = mat(code)
    return m.get('short') or D.FINISH.get(code, code).split(',')[0]


_FILL_BY_TEX = {'herringbone': (0.96, 0.90, 0.80), 'planks': (0.97, 0.93, 0.85), 'concrete': (0.91, 0.91, 0.90),
                'tiles': (0.88, 0.93, 0.96)}


def floor_fill_default():
    return {D.ROOM[k]['floor']: mat(D.ROOM[k]['floor']).get('plan_col', _FILL_BY_TEX.get(mat(D.ROOM[k]['floor']).get('tex'),
                                                                                      (0.95, 0.95, 0.95)))
            for k in D.ROOM}


def floor_patterns_default():
    out = []
    for k in D.rooms_all():
        t = mat(D.ROOM[k]['floor']).get('tex')
        if t in ('herringbone', 'planks'):
            out.append((k, t))
    return out


def heat_labels():
    """Подписи терморегуляторов на плане тёплых полов: annot.HEATS['labels'] или у самого регулятора."""
    lab = ann('HEATS', 'labels')
    if lab is not None:
        return lab
    out = []
    pts = {P['id']: P for P in D.POINTS}
    for h in D.HEAT:
        P = pts.get(h['tr'])
        if P:
            n = P['n']
            out.append(((P['p'][0] + n[0] * 420, P['p'][1] + n[1] * 420), 'Т' + h['room']))
    return out


def inset_ortho(poly, d):
    """Внутренний контур ортогонального многоугольника на d мм (теневой профиль потолка)."""
    n = len(poly)
    a = 0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        a += x0 * y1 - x1 * y0
    sgn = 1 if a > 0 else -1           # обход против часовой — внутренняя нормаль слева
    out = []
    for i in range(n):
        p0, p1, p2 = poly[i - 1], poly[i], poly[(i + 1) % n]
        def nrm(a_, b_):
            dx, dy = b_[0] - a_[0], b_[1] - a_[1]
            L = (dx * dx + dy * dy) ** 0.5
            return (-dy / L * sgn, dx / L * sgn)
        n1, n2 = nrm(p0, p1), nrm(p1, p2)
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        if abs(dot) > 1e-9 and abs(dot - 1) > 1e-9 and dot > -0.999:
            # наклонная грань (не 90° и не 180°): смещение по биссектрисе (митра)
            out.append((p1[0] + d * (n1[0] + n2[0]) / (1 + dot), p1[1] + d * (n1[1] + n2[1]) / (1 + dot)))
            continue
        out.append((p1[0] + d * (n1[0] + n2[0]) if abs(n1[0] + n2[0]) <= 1 else p1[0] + d * n1[0],
                    p1[1] + d * (n1[1] + n2[1]) if abs(n1[1] + n2[1]) <= 1 else p1[1] + d * n1[1]))
    return [(int(x) if float(x).is_integer() else x, int(y) if float(y).is_integer() else y) for x, y in out]


def ceil_code(k):
    return D.ROOM[k].get('ceil_code') or ('Пт1' if D.ROOM[k].get('zone') not in ('wet', 'out') else
                                          ('Пт2' if D.ROOM[k].get('zone') == 'wet' else 'Пт3'))


def ceil_groups():
    """[(код потолка, [помещения])] в порядке первого появления."""
    g = {}
    for k in D.rooms_all():
        g.setdefault(ceil_code(k), []).append(k)
    return list(g.items())


def ceil_fill_default():
    out = {}
    for k in D.rooms_all():
        z = D.ROOM[k].get('zone')
        out[k] = (0.86, 0.94, 0.98) if z == 'wet' else ((0.93, 0.93, 0.93) if z == 'out' else (0.98, 0.98, 0.97))
    return out


def ceil_labels_default():
    tp = tag_pos('cei')
    out = {}
    for k in D.rooms_all():
        zc = D.ROOM[k]['ceil']
        p = tp.get(k)
        if p is None:
            continue
        out[k] = ((p[0] - 450, p[1]), f'{ceil_code(k)}  ' + (lvl(zc) if zc else 'сущ.'))
    return out


def power_rows_default():
    """Силовые и специальные выводы из POINTS: силовые, выводы, розетки IP44 и скрытые (в мебели)."""
    rows = []
    for P in D.POINTS:
        if P['kind'] in ('pow', 'out', 'r1w', 'r2w', 'shk', 'ssh') or P.get('hidden'):
            rows.append([P['room'], P.get('note', P['kind']), '+' + str(P['z']), ''])
    return rows


def frag_default():
    """Фрагмент мокрых зон для плана сантехники (если не задан в annot): М 1:25, если помещается под планом, иначе 1:40."""
    wet = [k for k in D.rooms_all() if D.ROOM[k].get('zone') == 'wet']
    xs = [p[0] for k in wet for p in D.ROOMS[k]['poly']]
    ys = [p[1] for k in wet for p in D.ROOMS[k]['poly']]
    rect = (min(xs) - 60, min(ys) - 60, max(xs) + 160, max(ys) + 60)
    k = 25.0
    for k in (25.0, 40.0, 50.0):
        if (rect[2] - rect[0]) / k <= 80 and (rect[3] - rect[1]) / k <= 190:
            break
    return dict(rect=rect, rooms=tuple(wet), X0=40 - rect[1] / k, Y0=90 + rect[0] / k, k=k,
                title='Фрагмент: санузлы ' + ', '.join(wet), title_at=(25, 97))


def room_at(p):
    for k in D.rooms_all():
        if _inside(D.ROOMS[k]['poly'], p):
            return k
    return None


def thresholds_default():
    """Пороги/стыки покрытий: в дверных проёмах между помещениями с разным покрытием или отметкой пола."""
    import elev as EL
    out = []
    for o in EL.OPENINGS:
        if o['kind'] != 'door':
            continue
        m = (o['a'] + o['b']) / 2
        c = (o['c0'] + o['c1']) / 2
        if o['axis'] == 'y':
            r1, r2 = room_at((m, o['c0'] - 60)), room_at((m, o['c1'] + 60))
            seg = ((o['a'], c), (o['b'], c))
        else:
            r1, r2 = room_at((o['c0'] - 60, m)), room_at((o['c1'] + 60, m))
            seg = ((c, o['a']), (c, o['b']))
        if r1 and r2 and (D.ROOM[r1]['floor'] != D.ROOM[r2]['floor'] or D.ROOM[r1]['level'] != D.ROOM[r2]['level']):
            out.append(seg)
    return out


def door_marks_default():
    """Марка двери — в стороне открывания от середины проёма."""
    out = {}
    for key in D.DOOR_MARK:
        d = D.DOORS[key]
        hx, hy = d['h']; cx, cy = d['c']; ox, oy = d['o']; L = d['L']
        out[key] = (hx + cx * L / 2 + ox * 300, hy + cy * L / 2 + oy * 300)
    return out


HEAT_NOTES = [
    'Маты — тонкие (≈3 мм) в слое плиточного клея; только на свободной площади пола: не под сантехникой (в т. ч. подвесной), коробами, шкафами и встроенной мебелью; отступ 50 мм от стен и предметов, 100 мм от трапа. Полосы уже 300 мм не обогреваются.',
    'Под мебелью на ножках обогрев допускается. В душевой зоне — мат с экранирующей оплёткой, соединённой с защитным проводником (ГОСТ Р 50571.7.701-2013).',
    'Терморегуляторы программируемые, с датчиком пола в гофротрубке между витками (д); регуляторы санузлов — вне помещения.',
    'Питание — отдельные группы через УЗО 30 мА (по электропроекту). Перед укладкой — замер сопротивления мата.',
]


def tag_pos(key):
    """Положения бирок помещений для листа key (annot.TAGS[key] -> TAGS['default'] -> автоматически)."""
    t = ann('TAGS') or {}
    return t.get(key) or t.get('default') or DP.auto_tag_pos()


def base(key, title, sub=None, zones=False, furniture='faint', doors='final', dims='outer', tags=True,
         tag_names=True, tag_pos=None):
    sh = Sheet(key, title)
    v = DP.new_view()
    pen = Pen(sh, v)
    if zones:
        DP.draw_zones(pen)
    if furniture == 'full':
        DP.draw_items(pen)
    elif furniture == 'faint':
        DP.draw_items(pen, faint_=True, skip=('rug',))
    return sh, v, pen


def finish_base(sh, v, pen, doors='final', dims='outer', faint_doors=False):
    DP.draw_walls(pen)
    if doors == 'final':
        DP.draw_openings(pen, faint_doors=faint_doors)
    elif doors == 'obmer':
        DP.draw_openings(pen, door_keys=getattr(MV, 'OBMER_DOORS', list(MV.DOORS)), doors=MV.DOORS)
    elif doors == 'none':
        DP.draw_openings(pen, door_keys=[])
    if dims == 'outer':
        DP.outer_dims(sh, v)
    elif dims == 'obmer':
        DP.outer_dims(sh, v)
        DP.inner_dims(sh, v)


def title(sh, txt, sub=None):
    k = int((DP.VIEW or {}).get('k', 50))
    if k != 50:
        txt = txt.replace('М 1:50', f'М 1:{k}')
    sh.text((28, 286.5), txt, h=3.5, layer='A-TEXT', font='BoldObl')
    if sub:
        sh.text((28 + tw(txt, 3.5, 'BoldObl') + 4, 286.5), sub, h=2.4, layer='A-TEXT')


def tags(sh, v, pos=None, names=True):
    DP.room_tags(sh, v, pos=pos or tag_pos('default'), names=names)


# =============================== 03 ОБМЕРНЫЙ ===============================
def sheet_obmer(no, total):
    sh, v, pen = base('03', 'Обмерный план', furniture=None)
    finish_base(sh, v, pen, doors='obmer', dims='obmer')
    from core import adim
    for p1, p2, off, t_ in getattr(MV, 'OBMER_ADIMS', []):          # наклонные стены (эркер и т. п.)
        adim(sh, v, p1, p2, off, t_)
    O = ann('OBMER') or {}
    draw_prims(sh, v, Pen(sh, v), O.get('draw'))          # существующее оборудование (кондиционеры, радиаторы)
    put_labels(sh, v, O.get('labels'))
    names = O.get('names') or {k: D.ROOM[k]['name'] for k in D.ROOM}
    for k, p in (O.get('tags') or tag_pos('default')).items():
        DP.room_tag(sh, v, p, k, names.get(k, ''), D.AREA[k])
    title(sh, 'ОБМЕРНЫЙ ПЛАН  М 1:50', O.get('subtitle', 'по обмеру заказчика; черновые отметки'))
    tot = D.total_area()
    expl = O.get('expl') or [(k, D.ROOM[k]['name'], '') for k in D.rooms_all()]
    rows = [[k, nm, num(D.AREA[k], AREA_DEC()), h_] for k, nm, h_ in expl if k in D.rooms_counted()]
    rows.append(['', '**Итого по квартире', '**' + num(tot, AREA_DEC()), ''])
    rows += [[k, nm, num(D.AREA[k], AREA_DEC()), h_] for k, nm, h_ in expl if k not in D.rooms_counted()]
    yb = table(sh, 25, 96, [10, 60, 18, 20], ['№', 'Наименование', 'Площадь,\nм²', 'hчерн,\nм'], rows,
               aligns=['c', 'l', 'r', 'c'], title='Экспликация (существующее положение)', row_h=4.6)
    if O.get('notes'):
        notes(sh, 25, yb - 5, 106, 'Примечания', O['notes'])
    legend_box(sh, 376, 281, [
        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=WALLFILL, lw=0.5, layer='A-TEXT'),
         'Стены и перегородки существующие'), *bearing_legend(),
        (lambda s, x, y: (s.rect(x - 4, y - 1.5, x + 4, y + 1.5, lw=0.25, layer='A-TEXT'),
                          s.line((x - 4, y - 1.5), (x + 4, y + 1.5), lw=0.18, layer='A-TEXT'),
                          s.line((x - 4, y + 1.5), (x + 4, y - 1.5), lw=0.18, layer='A-TEXT')), 'Шахта (стояки — предп.)'),
    ], width=26)
    frame(sh, no, total, 'Обмерный план')
    return sh


# =============================== 04 ДЕМОНТАЖ ===============================
def sheet_demo(no, total):
    sh, v, pen = base('04', 'План демонтажа', furniture=None)
    DP.draw_walls(pen)
    S = ann('DEMO') or {}
    # сохраняемые двери (по умолчанию — балконные); остальные существующие полотна показываются как демонтируемые
    keep = S.get('keep_doors', [k for k in D.DOORS if k.startswith('balc')])
    DP.draw_openings(pen, door_keys=keep, doors=MV.DOORS if S.get('keep_from_obmer') else None)
    DP.outer_dims(sh, v)
    # существующие дверные полотна — демонтаж
    for k in S.get('doors', []):
        d = MV.DOORS[k]
        hx, hy = d['h']; ox, oy = d['o']; cx, cy = d['c']; L = d['L']
        p2 = (hx + ox * L, hy + oy * L)
        pen.line((hx, hy), p2, **DEMO)
        a0 = math.degrees(math.atan2(oy, ox)); a1 = math.degrees(math.atan2(cy, cx))
        if (a1 - a0) % 360 <= 180:
            pen.arc((hx, hy), L, a0, a1, **DEMO)
        else:
            pen.arc((hx, hy), L, a1, a0, **DEMO)
    # подиумы / стяжки
    for poly in S.get('areas', []):
        pen.poly(poly, lw=0.35, layer='A-DEMO', color=RED, dash=(1.6, 0.9))
        for a, b in poly_scan([v.P(*p) for p in poly], 45, 2.2):
            sh.line(a, b, lw=0.15, layer='A-DEMO', color=RED)
    # устройство проёмов
    for (x0, y0, x1, y1) in S.get('openings', []):
        pen.rect(x0, y0, x1, y1, lw=0.5, layer='A-DEMO', color=RED)
        pen.line((x0, y0), (x1, y1), lw=0.3, layer='A-DEMO', color=RED)
        pen.line((x0, y1), (x1, y0), lw=0.3, layer='A-DEMO', color=RED)
    for c, t in S.get('bubbles', []):
        bubble(sh, v.P(*c), t, r=2.0, h=1.6, fill=(1, 0.92, 0.92))
    tags(sh, v, names=False)
    title(sh, 'ПЛАН ДЕМОНТАЖА  М 1:50')
    if S.get('rows'):
        table(sh, 25, 96, [8, 150, 10, 14], ['№', 'Наименование работ', 'Ед.', 'Кол.'], S['rows'],
              aligns=['c', 'l', 'c', 'r'], title='Ведомость демонтажных работ', wraps=[False, True, False, False], row_h=4.6)
    if S.get('notes'):
        notes(sh, 233, 98, 178, 'Примечания', S['notes'], h=1.9, lead=2.9)
    legend_box(sh, 376, 281, [
        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=WALLFILL, lw=0.5, layer='A-TEXT'),
         'Сохраняемые стены и перегородки'), *bearing_legend(),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.35, dash=(1.6, 0.9), layer='A-DEMO', color=RED),
         'Демонтируемые элементы'),
        (lambda s, x, y: [s.rect(x - 4, y - 1.5, x + 4, y + 1.5, lw=0.3, layer='A-DEMO', color=RED)] +
         [s.line(a, b, lw=0.15, layer='A-DEMO', color=RED) for a, b in poly_scan([(x - 4, y - 1.5), (x + 4, y - 1.5), (x + 4, y + 1.5), (x - 4, y + 1.5)], 45, 1.4)],
         S.get('areas_label', 'Демонтаж подиума / стяжки')),
        (lambda s, x, y: (s.rect(x - 2, y - 1.5, x + 2, y + 1.5, lw=0.5, layer='A-DEMO', color=RED),
                          s.line((x - 2, y - 1.5), (x + 2, y + 1.5), lw=0.3, layer='A-DEMO', color=RED)),
         'Устройство проёма'),
    ], width=26)
    frame(sh, no, total, 'План демонтажа')
    return sh


# =============================== фрагмент плана в крупном масштабе ===============================
def frag_base(sh, F):
    """Основа фрагмента: вид F (X0, Y0, k), стены (отсечённые прямоугольником F['rect']), шахта, предметы помещений F['rooms']
    (бледно). Возвращает (вид, перо)."""
    from core import View, Pen as _Pen, wall_union_edges, wall_outline
    from kit import clip_seg_rect
    clipr = F['rect']
    fv = View(X0=F['X0'], Y0=F['Y0'], k=F['k'])
    fp = _Pen(sh, fv)
    for it in D.ITEMS:
        if it['room'] in F.get('rooms', ()):
            r_ = D.item_rect(it)
            if r_ and (r_[0] < clipr[0] or r_[2] > clipr[2] or r_[1] < clipr[1] or r_[3] > clipr[3]):
                continue                       # только предметы целиком внутри фрагмента
            DP.draw_item(fp, it, faint_=True)
    for r in D.WALLS:
        x0 = max(r[0], clipr[0]); y0 = max(r[1], clipr[1]); x1 = min(r[2], clipr[2]); y1 = min(r[3], clipr[3])
        if x1 > x0 and y1 > y0:
            fp.rect(x0, y0, x1, y1, fill=WALLFILL, stroke=False, layer='A-WALL-FILL')
    if D.WALL_POLYS:
        crect = [(clipr[0], clipr[1]), (clipr[2], clipr[1]), (clipr[2], clipr[3]), (clipr[0], clipr[3])]
        for p in D.WALL_POLYS:
            pp = clip_poly_convex(list(p), crect)
            if len(pp) >= 3:
                fp.poly(pp, fill=WALLFILL, stroke=False, layer='A-WALL-FILL')
    for a, b in (wall_outline(D.WALLS, D.WALL_POLYS) if D.WALL_POLYS else wall_union_edges(D.WALLS)):
        c = clip_seg_rect(a, b, clipr)
        if c:
            fp.line(c[0], c[1], lw=0.5, layer='A-WALL')
    if D.SHAFT:
        x0, y0, x1, y1 = D.SHAFT
        if not (x1 < clipr[0] or x0 > clipr[2] or y1 < clipr[1] or y0 > clipr[3]):
            fp.rect(x0, y0, x1, y1, lw=0.25, layer='A-HATCH')
            fp.line((x0, y0), (x1, y1), lw=0.18, layer='A-HATCH')
            fp.line((x0, y1), (x1, y0), lw=0.18, layer='A-HATCH')
    return fv, fp


# =============================== 05 МОНТАЖ ===============================
def sheet_mount(no, total):
    sh, v, pen = base('05', 'План монтажа', furniture=None)
    DP.draw_walls(pen)
    DP.draw_openings(pen)
    DP.outer_dims(sh, v)
    S = ann('MOUNT') or {}
    boxes = S.get('boxes')
    if boxes is None:
        boxes = [D.item_rect(it) for it in D.ITEMS if it['kind'] == 'box']
    for r in boxes:
        pen.rect(*r, fill=(1.0, 0.93, 0.80), lw=0.45, layer='A-NEW', color=NEWC)
        x0, y0, x1, y1 = r
        for a, b in poly_scan([v.P(x0, y0), v.P(x1, y0), v.P(x1, y1), v.P(x0, y1)], 45, 0.9):
            sh.line(a, b, lw=0.12, layer='A-NEW', color=NEWC)
    for r in S.get('openings', []):          # проёмы
        pen.rect(*r, lw=0.4, layer='A-NEW', color=NEWC)
    for (x0, y0, x1, y1) in S.get('narrow', []):          # сужение проёмов под скрытые двери
        pen.rect(x0, y0, x1, y1, fill=NEWC, lw=0.1, layer='A-NEW', color=NEWC)
    DP.dims_list(sh, v, S.get('dims', []))
    if S.get('adims'):
        from core import adim
        for p1, p2, off, t_ in S['adims']:
            adim(sh, v, p1, p2, off, t_)
    for c, t in S.get('bubbles', []):
        bubble(sh, v.P(*c), t, r=2.0, h=1.4, fill=(1, 0.95, 0.85))
    if S.get('frag'):                        # фрагмент (напр. короба санузлов) в крупном масштабе
        F = S['frag']
        pen.rect(*F['rect'], lw=0.3, layer='A-TEXT', dash=(3.0, 1.0, 0.6, 1.0))
        fv, fp = frag_base(sh, F)
        for r in boxes:
            x0, y0, x1, y1 = r
            c0 = (max(x0, F['rect'][0]), max(y0, F['rect'][1]), min(x1, F['rect'][2]), min(y1, F['rect'][3]))
            if c0[2] <= c0[0] or c0[3] <= c0[1]:
                continue
            fp.rect(*c0, fill=(1.0, 0.93, 0.80), lw=0.45, layer='A-NEW', color=NEWC)
            for a_, b_ in poly_scan([fv.P(c0[0], c0[1]), fv.P(c0[2], c0[1]), fv.P(c0[2], c0[3]), fv.P(c0[0], c0[3])], 45, 1.2):
                sh.line(a_, b_, lw=0.12, layer='A-NEW', color=NEWC)
        for r in S.get('openings', []):
            fp.rect(*r, lw=0.5, layer='A-NEW', color=NEWC)
        DP.dims_list(sh, fv, F.get('dims', []), h=2.0)
        for c, t in F.get('bubbles', []):
            bubble(sh, fv.P(*c), t, r=2.2, h=1.6, fill=(1, 0.95, 0.85))
        from kit import section_title
        section_title(sh, F['title_at'][0], F['title_at'][1], F['title'], f"М 1:{int(F['k'])}", h=2.6)
    tags(sh, v, names=False)
    title(sh, 'ПЛАН МОНТАЖА ПЕРЕГОРОДОК И КОРОБОВ  М 1:50')
    if S.get('rows'):
        table(sh, 25, 96, [8, 150, 10, 14], ['Марка', 'Наименование', 'Ед.', 'Кол.'], S['rows'],
              aligns=['c', 'l', 'c', 'r'], title='Ведомость монтажных работ', wraps=[False, True, False, False], row_h=4.6)
    if S.get('notes'):
        notes(sh, 233, 98, 178, 'Примечания', S['notes'], h=1.9, lead=2.9)
    legend_box(sh, 376, 281, [
        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=WALLFILL, lw=0.5, layer='A-TEXT'), 'Стены существующие'),
        *bearing_legend(),
        (lambda s, x, y: [s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=(1.0, 0.93, 0.80), lw=0.45, layer='A-NEW', color=NEWC)] +
         [s.line(a, b, lw=0.12, layer='A-NEW', color=NEWC) for a, b in poly_scan([(x - 4, y - 1.5), (x + 4, y - 1.5), (x + 4, y + 1.5), (x - 4, y + 1.5)], 45, 0.9)],
         'Возводимые конструкции (ГКЛВ)'),
    ] + ([(lambda s, x, y: s.rect(x - 0.6, y - 1.5, x + 0.6, y + 1.5, fill=NEWC, lw=0.1, layer='A-NEW', color=NEWC),
           'Сужение проёма')] if S.get('narrow') else []), width=26)
    frame(sh, no, total, 'План монтажа перегородок\nи коробов')
    return sh


# =============================== 06 МЕБЕЛЬ ===============================
def _word(sh, v, p, txt, h=1.5, ha='c', rot=0, color=BLACK):
    sh.text(v.P(*p), txt, h=h, ha=ha, va='m', layer='A-TEXT', color=color, bg=True, rot=rot, font='BoldObl')


def sheet_furniture(no, total):
    DP.COLORED['on'] = True
    DP.COLORED['words'] = True
    try:
        sh, v, pen = base('06', 'План мебели', zones=True, furniture='full')
    finally:
        DP.COLORED['on'] = False
        DP.COLORED['words'] = False
    finish_base(sh, v, pen)
    S = ann('FURN') or {}
    # карнизы (скрытые, в нише потолка) и шторы
    for f in D.CEIL_FEATURES:
        if f['kind'] == 'niche':
            x0, y0, x1, y1 = f['rect']
            yc = (y0 + y1) / 2
            pen.line((x0 + 60, yc), (x1 - 60, yc), lw=0.6, layer='A-EQPM', color=ROD, dash=(3.0, 0.8))
    # подписи словами: карнизы/шторы, техника и оборудование
    for p, txt, h, col, rot in S.get('words', []):
        _word(sh, v, p, txt, h=h, color=COLORS.get(col, col), rot=rot)
    tags(sh, v, pos=tag_pos('fur'))
    title(sh, 'ПЛАН РАССТАНОВКИ МЕБЕЛИ И ОБОРУДОВАНИЯ  М 1:50', 'техника — сокращённые обозначения (см. «Сокращения»); цвет — по группам')
    ab = S.get('abbr') or DP.abbr_used(sh)
    if ab:
        ax, ay = S.get('abbr_pos', (95, 96))
        notes(sh, ax, ay, 120, 'Сокращения', [f'{a_} — {t_}' for a_, t_ in ab], h=1.8, lead=2.7, numbered=False)
    if S.get('notes'):
        notes(sh, 233, 98, 178, 'Примечания', S['notes'], h=1.9, lead=2.9)

    def sw(col):
        return lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=col, lw=0.2, layer='A-FURN', color=DARK)
    pal_leg = S.get('legend') or [('built', 'Встроенная мебель (в цвет стен)'), ('walnut', 'Мебель — шпон ореха'),
                                  ('oak', 'Столы, стеллаж — дуб'), ('soft', 'Мягкая мебель'), ('appl', 'Бытовая техника'),
                                  ('sani', 'Сантехника')]
    legend_box(sh, 376, 281, [(sw(DP.PAL[k_]), t_) for k_, t_ in pal_leg] + [
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.6, dash=(3.0, 0.8), layer='A-EQPM', color=ROD), 'Карниз'),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.2, dash=(2.0, 1.2), layer='A-TEXT'),
         'Подвесные элементы, верхние шкафы, вытяжка'),
    ], width=26)
    # зоны — маленькая легенда снизу
    legend_box(sh, 23, 96, [
        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=Z_DAY, lw=0.18, layer='A-ZONE'), 'Дневная зона'),
        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=Z_NIGHT, lw=0.18, layer='A-ZONE'), 'Ночная зона'),
        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=Z_WET, lw=0.18, layer='A-ZONE'), 'Мокрые зоны'),
    ], width=40, title='Зоны')
    frame(sh, no, total, 'План расстановки мебели\nи оборудования')
    return sh


# =============================== 07 ПОЛЫ ===============================
def herringbone(sh, v, poly, bw=90, bl=600, color=(0.55, 0.45, 0.30), axis='y'):
    """Английская ёлочка bl×bw в выпуклом контуре poly (модель); ось («хребет») — вдоль axis, по центру помещения."""
    import textures as T
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    clip = [v.P(*p) for p in poly]
    a = 0
    for (xa, ya), (xb, yb) in zip(clip, clip[1:] + clip[:1]):
        a += xa * yb - xb * ya
    if a < 0:
        clip = clip[::-1]
    convex = _is_convex(clip)
    for brd, ori in T.herringbone_polys(min(xs), min(ys), max(xs), max(ys), bw, bl, axis=axis):
        pts = [v.P(*p) for p in brd]
        s = 0
        for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
            s += xa * yb - xb * ya
        if s < 0:
            pts = pts[::-1]
        # невыпуклое помещение (уступ, пилон): помещение отсекается выпуклой доской (результат тот же — пересечение)
        pp = clip_poly_convex(pts, clip) if convex else clip_poly_convex(clip, pts)
        if len(pp) >= 3:
            sh.poly(pp, lw=0.08, layer='A-FLOOR', color=color)


def _is_convex(pts):
    sg = 0
    n = len(pts)
    for i in range(n):
        (x0, y0), (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)
        if abs(c) < 1e-9:
            continue
        if sg == 0:
            sg = 1 if c > 0 else -1
        elif (c > 0) != (sg > 0):
            return False
    return True


def _is_rect(poly):
    xs = {p[0] for p in poly}; ys = {p[1] for p in poly}
    return len(poly) == 4 and len(xs) == 2 and len(ys) == 2


def planks(sh, v, poly, w=180, L=1800, along='y', color=(0.55, 0.45, 0.30)):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if not _is_rect(poly):
        # непрямоугольное помещение: те же линии, отсечённые контуром помещения
        pts = [v.P(*p) for p in poly]

        def ln(a, b):
            for p_, q_ in _clip_line_poly(pts, v.P(*a), v.P(*b)):
                sh.line(p_, q_, lw=0.08, layer='A-FLOOR', color=color)
        x = x0
        i = 0
        while x < x1 - 1:
            xa, xb = x, min(x + w, x1)
            ln((xb, y0), (xb, y1))
            off = (i * 600) % L
            y = y0 - off
            while y < y1:
                if y > y0:
                    ln((xa, y), (xb, y))
                y += L
            x += w
            i += 1
        return
    if along == 'y':
        x = x0
        i = 0
        while x < x1 - 1:
            xa, xb = x, min(x + w, x1)
            sh.line(v.P(xb, y0), v.P(xb, y1), lw=0.08, layer='A-FLOOR', color=color)
            off = (i * 600) % L
            y = y0 - off
            while y < y1:
                if y > y0:
                    sh.line(v.P(xa, y), v.P(xb, y), lw=0.08, layer='A-FLOOR', color=color)
                y += L
            x += w
            i += 1


def tile_grid(sh, v, poly, tw_, th_, ox, oy, color=(0.45, 0.45, 0.45), lw=0.1):
    pts = [v.P(*p) for p in poly]
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    import math as _m
    k0 = _m.floor((x0 - ox) / tw_); k1 = _m.ceil((x1 - ox) / tw_)
    for k in range(k0, k1 + 1):
        x = ox + k * tw_
        if x0 + 1 < x < x1 - 1:
            # вертикаль модели x=const -> горизонталь листа
            for a, b in _clip_line_poly(pts, v.P(x, y0 - 10), v.P(x, y1 + 10)):
                sh.line(a, b, lw=lw, layer='A-TILE', color=color)
    k0 = _m.floor((y0 - oy) / th_); k1 = _m.ceil((y1 - oy) / th_)
    for k in range(k0, k1 + 1):
        y = oy + k * th_
        if y0 + 1 < y < y1 - 1:
            for a, b in _clip_line_poly(pts, v.P(x0 - 10, y), v.P(x1 + 10, y)):
                sh.line(a, b, lw=lw, layer='A-TILE', color=color)


def _clip_line_poly(pts, p, q):
    """Пересечение отрезка pq с многоугольником (вершины pts) -> отрезки внутри."""
    ts = [0.0, 1.0]
    dx, dy = q[0] - p[0], q[1] - p[1]
    for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
        ex, ey = xb - xa, yb - ya
        den = dx * ey - dy * ex
        if abs(den) < 1e-12:
            continue
        t = ((xa - p[0]) * ey - (ya - p[1]) * ex) / den
        u = ((xa - p[0]) * dy - (ya - p[1]) * dx) / den
        if 0 <= t <= 1 and 0 <= u <= 1:
            ts.append(t)
    ts = sorted(set(round(t, 9) for t in ts))
    out = []
    for t0, t1 in zip(ts, ts[1:]):
        tm = (t0 + t1) / 2
        m = (p[0] + dx * tm, p[1] + dy * tm)
        if _inside(pts, m):
            out.append(((p[0] + dx * t0, p[1] + dy * t0), (p[0] + dx * t1, p[1] + dy * t1)))
    return out


def _inside(pts, m):
    c = False
    x, y = m
    for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
        if (ya > y) != (yb > y):
            xi = xa + (y - ya) * (xb - xa) / (yb - ya)
            if xi > x:
                c = not c
    return c


def floor_excl():
    """Участки без покрытия (под встроенной мебелью): annot.FLOORS['excl'] или встроенные предметы на полу."""
    e = ann('FLOORS', 'excl')
    if e is not None:
        return e
    kinds = ('wardrobe', 'kitchen_run', 'column', 'filler', 'box', 'wm_cab', 'shelving')
    return [D.item_rect(it) for it in D.ITEMS if it['kind'] in kinds and D.item_rect(it)]


def floor_areas():
    """Площади покрытий за вычетом встроенной мебели и коробов."""
    from kit import rect_minus, area_rects
    res = {}
    for k in D.rooms_all():
        a = D.AREA[k]
        for (x0, y0, x1, y1) in floor_excl():
            # пересечение с помещением (все помещения — прямоугольники, кроме 01)
            poly = D.ROOMS[k]['poly']
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            ix0, iy0, ix1, iy1 = max(x0, min(xs)), max(y0, min(ys)), min(x1, max(xs)), min(y1, max(ys))
            if ix1 > ix0 and iy1 > iy0:
                # проверим, что центр пересечения внутри помещения
                if _inside(poly, ((ix0 + ix1) / 2, (iy0 + iy1) / 2)):
                    a -= (ix1 - ix0) * (iy1 - iy0) / 1e6
        res[k] = a
    return res


START_COL = (0.80, 0.10, 0.10)


def start_mark(sh, P, lab, off=(2.2, 1.6)):
    """Знак начала раскладки: круг Ø3 с закрашенными четвертями, подпись (НР)."""
    X, Y = P
    r = 1.5
    sh.circle((X, Y), r, lw=0.3, layer='A-FLOOR', color=START_COL, fill=WHITE)
    import math as _m
    for a0 in (0, 180):
        pts = [(X, Y)] + [(X + r * _m.cos(_m.radians(a0 + t)), Y + r * _m.sin(_m.radians(a0 + t))) for t in range(0, 91, 15)]
        sh.poly(pts, lw=0.05, layer='A-FLOOR', color=START_COL, fill=START_COL)
    if lab:
        sh.text((X + off[0], Y + off[1]), lab, h=1.8, layer='A-TEXT', font='BoldObl', color=START_COL, bg=True)


def sheet_floors(no, total):
    sh, v, pen = base('07', 'План полов', furniture=None)
    S = ann('FLOORS') or {}
    WOOD = (0.60, 0.48, 0.32)
    FCOL = S.get('fill') or floor_fill_default()
    for k, info in D.ROOM.items():
        pen.poly(D.ROOMS[k]['poly'], fill=FCOL[info['floor']], stroke=False, layer='A-ZONE')
    for room, pat in (S.get('patterns') or floor_patterns_default()):
        if pat == 'herringbone':
            herringbone(sh, v, D.ROOMS[room]['poly'], color=WOOD,
                        axis=mat(D.ROOM[room]['floor']).get('plan_axis', 'y') if S.get('plan_axis', True) else 'y')
        else:
            planks(sh, v, D.ROOMS[room]['poly'], color=WOOD)
    for room, poly, a, b, ox, oy in D.FLOOR_TILES:
        tile_grid(sh, v, poly, a, b, ox, oy)
    for r in floor_excl():
        pen.rect(*r, fill=WHITE, lw=0.2, layer='A-FLOOR', color=MID)
        x0, y0, x1, y1 = r
        for a, b in poly_scan([v.P(x0, y0), v.P(x1, y0), v.P(x1, y1), v.P(x0, y1)], -45, 1.6):
            sh.line(a, b, lw=0.08, layer='A-FLOOR', color=LIGHT)
    finish_base(sh, v, pen, faint_doors=True)
    # пороги
    for (a, b) in (S['thresholds'] if 'thresholds' in S else thresholds_default()):
        pen.line(a, b, lw=0.9, layer='A-FLOOR', color=BLACK)
    # отметки
    from kit import level_box
    for p, t in S.get('levels') or [((tag_pos('default')[k][0] + 650, tag_pos('default')[k][1]),
                                     lvl(D.ROOM[k]['level']) if D.ROOM[k]['level'] is not None else 'уточн.')
                                    for k in D.rooms_all()]:
        level_box(sh, v.P(*p), t)
    # оси раскладки
    AX = dict(lw=0.18, layer='A-FLOOR', color=(0.1, 0.4, 0.8), dash=(4.0, 1.0, 0.6, 1.0))
    for a, b, lab, lp in S.get('axes', []):
        pen.line(a, b, **AX)
        if lab:
            sh.text(v.P(*lp), lab, h=1.6, ha='c', va='m', layer='A-TEXT', color=(0.1, 0.4, 0.8), bg=True)
    DP.dims_list(sh, v, S.get('dims', []), h=2.0)          # привязки швов раскладки (если заданы)
    # направления (третий элемент 'v' — стрелка вдоль x модели, вертикально на листе)
    for d_ in S.get('dirs', []):
        p, txt = d_[0], d_[1]
        X, Y = v.P(*p)
        if len(d_) > 2 and d_[2] == 'v':
            sh.line((X, Y - 6), (X, Y + 6), lw=0.3, layer='A-FLOOR')
            sh.poly([(X, Y + 6), (X + 0.8, Y + 4.5), (X - 0.8, Y + 4.5)], layer='A-FLOOR', fill=BLACK, lw=0.1)
            sh.poly([(X, Y - 6), (X + 0.8, Y - 4.5), (X - 0.8, Y - 4.5)], layer='A-FLOOR', fill=BLACK, lw=0.1)
            sh.text((X + 1.4, Y), txt, h=1.6, va='m', layer='A-TEXT', bg=True)
        else:
            sh.line((X - 6, Y), (X + 6, Y), lw=0.3, layer='A-FLOOR')
            sh.poly([(X + 6, Y), (X + 4.5, Y + 0.8), (X + 4.5, Y - 0.8)], layer='A-FLOOR', fill=BLACK, lw=0.1)
            sh.poly([(X - 6, Y), (X - 4.5, Y + 0.8), (X - 4.5, Y - 0.8)], layer='A-FLOOR', fill=BLACK, lw=0.1)
            sh.text((X, Y + 1.2), txt, h=1.6, ha='c', layer='A-TEXT', bg=True)
    # начало раскладки (стандарт бюро): знак у точки начала + привязки от чистовых стен
    for st_ in S.get('starts', []):
        start_mark(sh, v.P(*st_['p']), st_.get('lab', 'НР'), st_.get('off', (2.2, 1.6)))
        DP.dims_list(sh, v, st_.get('dims', []), h=2.0)
    codes = {k: D.ROOM[k]['floor'] for k in D.rooms_all()}
    cpos = S.get('code_pos') or tag_pos('default')
    for k, p in cpos.items():
        X, Y = v.P(*p)
        sh.rect(X - 4.5, Y - 2.2, X + 4.5, Y + 2.2, fill=WHITE, lw=0.3, layer='A-TEXT')
        sh.text((X, Y), codes[k], h=2.4, ha='c', va='m', layer='A-TEXT', font='BoldObl')
        sh.text((X, Y - 4.4), k, h=1.8, ha='c', va='m', layer='A-TEXT', bg=True)
    title(sh, 'ПЛАН ПОЛОВ  М 1:50', 'покрытия, раскладка, пороги, отметки')
    fa = floor_areas()
    sums = {}
    for k, c in codes.items():
        sums.setdefault(c, []).append(k)
    rows = []
    for c in sorted(sums):
        rooms = sums[c]
        area = sum(fa[k] for k in rooms)
        zp = reserve(c)
        rows.append([c, D.FINISH[c], ', '.join(rooms), num(area, 2), f'+{round(zp * 100)} %', num(area * (1 + zp), 1)])
    table(sh, 23, 97, [9, 106, 16, 13, 12, 14], ['Код', 'Покрытие', 'Пом.', 'Пл. нетто,\nм²', 'Запас', 'К заказу,\nм²'],
          rows, aligns=['c', 'l', 'c', 'r', 'c', 'r'], wraps=[False, True, False, False, False, False], row_h=4.6, h=1.7,
          title='Покрытия полов', title_h=2.4, head_h=7)
    if S.get('notes_build'):
        notes(sh, 23, 52, 200, 'Конструкция пола', S['notes_build'], h=1.75, lead=2.7, title_h=2.3)
    if S.get('notes_layout'):
        notes(sh, 233, 98, 178, 'Раскладка', S['notes_layout'], h=1.9, lead=2.9)
    lnames = S.get('legend_names') or {c: mat_name(c) for c in sums}
    legend_box(sh, 376, 281, [(lambda s, x, y, c=c: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, fill=FCOL[c], lw=0.2, layer='A-ZONE'),
                               c + ' — ' + lnames[c]) for c in sorted(sums)] + [

        (lambda s, x, y: s.rect(x - 4, y - 1.5, x + 4, y + 1.5, lw=0.2, layer='A-FLOOR', color=MID) or
         [s.line(a, b, lw=0.08, layer='A-FLOOR', color=LIGHT) for a, b in poly_scan([(x - 4, y - 1.5), (x + 4, y - 1.5), (x + 4, y + 1.5), (x - 4, y + 1.5)], -45, 1.0)],
         'Без покрытия (под встроенной мебелью)'),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.9, layer='A-FLOOR'), 'Порог / стык покрытий'),
        (lambda s, x, y: level_box(s, (x, y), '+0,020', h=1.5), 'Отметка чистого пола, м'),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.18, layer='A-FLOOR', color=(0.1, 0.4, 0.8), dash=(4.0, 1.0, 0.6, 1.0)),
         'Ось раскладки'),
    ] + ([(lambda s, x, y: start_mark(s, (x, y), '', (0, 0)), 'Начало раскладки (НР) с привязками')] if S.get('starts') else []),
        width=26)
    frame(sh, no, total, 'План полов')
    return sh


# =============================== 08 ТЁПЛЫЕ ПОЛЫ ===============================
def sheet_heat(no, total):
    sh, v, pen = base('08', 'План тёплых полов', furniture='faint')
    HC = (0.85, 0.20, 0.10)
    from kit import mask_draw, mask_center
    masks = {h['room']: D.heat_mask(h['room']) for h in D.HEAT}
    for h in D.HEAT:
        mask_draw(sh, v, masks[h['room']], HC, (1.0, 0.90, 0.86))
    # предметы поверх — видно, что мат их обходит
    DP.draw_items(pen, rooms=[h['room'] for h in D.HEAT], skip=('rug',))
    finish_base(sh, v, pen, faint_doors=True)
    # терморегуляторы и датчики
    tr_ids = {h['tr'] for h in D.HEAT}
    for p in D.POINTS:
        if p['id'] in tr_ids:
            P = v.P(*p['p']); N = SY.sheet_normal(p['n'])
            SY.switch(sh, P, N, 'tr')
    sensors = {k: mask_center(m) for k, m in masks.items()}
    sensors.update({k: p for k, p in (ann('HEATS', 'sensors') or {}).items() if k in sensors})   # положения датчиков объекта
    for k, p in sensors.items():
        X, Y = v.P(*p)
        sh.circle((X, Y), 1.2, lw=0.25, layer='A-HEAT', fill=WHITE, color=HC)
        sh.text((X, Y), 'д', h=1.3, ha='c', va='m', layer='A-HEAT', color=HC)
    for p, t in heat_labels():
        sh.text(v.P(*p), t, h=1.7, ha='c', va='m', layer='A-HEAT', color=HC, font='BoldObl', bg=True)
    tags(sh, v, names=False)
    title(sh, 'ПЛАН ТЁПЛЫХ ПОЛОВ  М 1:50', 'электрические нагревательные маты под плитку')
    rows = []
    tot_w = 0
    for h in D.HEAT:
        area = D.heat_area(h['room'])
        mat = D.heat_mat(h['room'])
        pw = mat * h['w']
        tot_w += pw
        rows.append([h['room'] + ' ' + D.ROOM[h['room']]['name'], num(area, 2), num(mat, 1), f'{h["w"]}', f'{pw:.0f}',
                     'Т' + h['room']])
    rows.append(['**Итого', '', '', '', f'**{tot_w:.0f}', ''])
    table(sh, 23, 97, [42, 18, 18, 18, 18, 22], ['Помещение', 'Зона обогрева,\nм²', 'Мат,\nм²', 'Вт/м²', 'Мощность,\nВт',
                                                 'Терморегулятор'],
          rows, aligns=['l', 'r', 'r', 'r', 'r', 'c'], row_h=4.6, title='Ведомость тёплых полов', title_h=2.4)
    notes(sh, 233, 98, 178, 'Примечания', ann('HEATS', 'notes') or HEAT_NOTES, h=1.9, lead=2.9)
    legend_box(sh, 376, 281, [
        (lambda s, x, y: [s.rect(x - 4, y - 1.5, x + 4, y + 1.5, lw=0.4, layer='A-HEAT', color=HC, fill=(1.0, 0.9, 0.86))] +
         [s.line(a, b, lw=0.12, layer='A-HEAT', color=HC) for a, b in poly_scan([(x - 4, y - 1.5), (x + 4, y - 1.5), (x + 4, y + 1.5), (x - 4, y + 1.5)], 30, 1.2)],
         'Зона укладки мата'),
        (lambda s, x, y: SY.switch(s, (x, y - 1.5), (0, 1), 'tr'), 'Терморегулятор, +0,900'),
        (lambda s, x, y: (s.circle((x, y), 1.2, lw=0.25, layer='A-HEAT', fill=WHITE, color=HC),
                          s.text((x, y), 'д', h=1.3, ha='c', va='m', layer='A-HEAT', color=HC)), 'Датчик температуры пола'),
    ], width=26)
    frame(sh, no, total, 'План тёплых полов')
    return sh


# =============================== 09 ПОТОЛКИ ===============================
def sheet_ceiling(no, total):
    sh, v, pen = base('09', 'План потолков', furniture=None)
    CC = (0.15, 0.35, 0.65)
    VC = (0.0, 0.50, 0.45)
    BUILT = (0.93, 0.88, 0.78)
    S = ann('CEIL') or {}
    cfill = S.get('fill') or ceil_fill_default()
    for k, col in cfill.items():
        pen.poly(D.ROOMS[k]['poly'], fill=col, stroke=False, layer='A-ZONE')
    # теневой профиль по периметру (внутренний контур 15 мм)
    ceil_rooms = [k for k in D.rooms_all() if D.ROOM[k]['ceil']]
    for k in ceil_rooms:
        pen.poly(inset_ortho(D.ROOMS[k]['poly'], 15), lw=0.12, layer='A-CEIL', color=CC)
    # встроенная мебель до потолка: потолок примыкает к корпусу
    for k in ceil_rooms:
        for it, r in D.builtin_to_ceiling(k):
            x0, y0, x1, y1 = r
            pts = [v.P(x0, y0), v.P(x1, y0), v.P(x1, y1), v.P(x0, y1)]
            fillc = FILL_LT if it['kind'] == 'box' else BUILT
            sh.poly(pts, lw=0.35, layer='A-CEIL', color=DARK, fill=fillc)
            for a_, b_ in poly_scan(pts, -45, 1.2):
                sh.line(a_, b_, lw=0.1, layer='A-CEIL', color=MID)
    for f in D.CEIL_FEATURES:
        x0, y0, x1, y1 = f['rect']
        if f['kind'] == 'niche':
            pts = [v.P(x0, y0), v.P(x1, y0), v.P(x1, y1), v.P(x0, y1)]
            sh.poly(pts, lw=0.3, layer='A-CEIL', color=CC, fill=(0.85, 0.89, 0.95))
            for a_, b_ in poly_scan(pts, 45, 0.9):
                sh.line(a_, b_, lw=0.1, layer='A-CEIL', color=CC)
            yc = (y0 + y1) / 2
            pen.line((x0 + 60, yc), (x1 - 60, yc), lw=0.6, layer='A-CEIL', color=(0.55, 0.20, 0.60), dash=(3.0, 0.8))
        elif f['kind'] == 'cove':
            pen.rect(x0, y0, x1, y1, lw=0.3, layer='A-CEIL', color=CC, fill=(1.0, 0.93, 0.70))
        elif f['kind'] == 'hatch':
            pen.rect(x0, y0, x1, y1, lw=0.3, layer='A-CEIL', color=VC, fill=WHITE)
            pen.line((x0, y0), (x1, y1), lw=0.15, layer='A-CEIL', color=VC)
            pen.line((x0, y1), (x1, y0), lw=0.15, layer='A-CEIL', color=VC)
    # паз в ГКЛ под встраиваемый трек (конструкция потолка; сам светильник — на плане освещения)
    for tr in D.TRACKS:
        x0, y0, x1, y1 = tr['rect']
        pen.rect(x0, y0, x1, y1, lw=0.3, layer='A-CEIL', color=CC, fill=WHITE, dash=(1.2, 0.6))
    # вентиляция: вентиляторы, воздуховоды над потолком, приточные клапаны
    for L in D.LIGHTS:
        if L['kind'] == 'fan':
            SY.light_c(sh, v.P(*L['p']), 'fan', col=VC)
    for item in D.VENT:
        if item['kind'] == 'duct':
            sh.poly([v.P(*p) for p in item['pts']], closed=False, lw=0.6, layer='M-VENT', color=VC, dash=(2.0, 0.8))
        elif item['kind'] == 'valve':
            X, Y = v.P(*item['p'])
            N = SY.sheet_normal(item['n'])
            T = (-N[1], N[0])
            box = [(X + T[0] * 2.2, Y + T[1] * 2.2), (X - T[0] * 2.2, Y - T[1] * 2.2),
                   (X - T[0] * 2.2 + N[0] * 1.2, Y - T[1] * 2.2 + N[1] * 1.2), (X + T[0] * 2.2 + N[0] * 1.2, Y + T[1] * 2.2 + N[1] * 1.2)]
            sh.poly(box, lw=0.3, layer='M-VENT', color=VC, fill=(0.80, 0.95, 0.92))
    finish_base(sh, v, pen, faint_doors=True)
    # подписи уровней
    for k, (p, t_) in (S.get('labels') or ceil_labels_default()).items():
        X, Y = v.P(*p)
        w = tw(t_, 2.2, 'BoldObl')
        sh.rect(X - w / 2 - 1.2, Y - 1.9, X + w / 2 + 1.2, Y + 2.1, fill=WHITE, lw=0.35, layer='A-CEIL', color=CC)
        sh.text((X, Y), t_, h=2.2, ha='c', va='m', layer='A-TEXT', font='BoldObl')
    for c, t_ in S.get('bubbles', []):
        bubble(sh, v.P(*c), t_, r=2.0, h=1.6, fill=(0.9, 0.94, 1.0))
    # подписи вентиляции и встройки
    for p, t_ in S.get('vent_labels', []):
        sh.text(v.P(*p), t_, h=1.6, ha='c', va='m', layer='A-TEXT', color=VC, font='BoldObl', bg=True)
    for p, t_, rot in S.get('builtin_labels', []):
        sh.text(v.P(*p), t_, h=1.3, ha='c', va='m', layer='A-TEXT', color=DARK, bg=True, rot=rot)
    DP.dims_list(sh, v, S.get('dims', []))
    draw_prims(sh, v, pen, S.get('draw'))          # доп. элементы потолка объекта (карнизы и т. п.)
    tags(sh, v, names=False, pos=tag_pos('cei'))
    title(sh, 'ПЛАН ПОТОЛКОВ  М 1:50', S.get('subtitle', 'уровни от ±0,000; светильники — на плане освещения'))
    rows = []
    for code, rooms in ceil_groups():
        a = sum(D.ceil_area(k) if D.ROOM[k]['ceil'] else D.AREA[k] for k in rooms)
        rows.append([code, D.FINISH[code], ', '.join(rooms), num(a, 1)])
    table(sh, 23, 97, [10, 132, 24, 16], ['Код', 'Потолок', 'Пом.', 'Площадь,\nм²'], rows, aligns=['c', 'l', 'c', 'r'],
          wraps=[False, True, False, False], row_h=4.6, title='Потолки (за вычетом встроенной мебели до потолка)', title_h=2.4, h=1.8)
    if S.get('notes_marks'):
        notes(sh, 233, 98, 178, 'Обозначения на плане', S['notes_marks'], numbered=True, h=1.9, lead=2.9)
    if S.get('notes'):
        notes(sh, 23, 68, 200, 'Примечания', S['notes'], h=1.75, lead=2.7, title_h=2.3)
    legend_box(sh, 376, 281, [
        (lambda s, x, y: [s.rect(x - 4, y - 1.5, x + 4, y + 1.5, lw=0.3, layer='A-CEIL', color=CC, fill=(0.85, 0.89, 0.95))] +
         [s.line(a_, b_, lw=0.1, layer='A-CEIL', color=CC) for a_, b_ in poly_scan([(x - 4, y - 1.5), (x + 4, y - 1.5), (x + 4, y + 1.5), (x - 4, y + 1.5)], 45, 0.9)] +
         [s.line((x - 3.5, y), (x + 3.5, y), lw=0.6, color=(0.55, 0.20, 0.60), dash=(3.0, 0.8), layer='A-CEIL')],
         'Ниша с карнизом'),
        (lambda s, x, y: s.rect(x - 4, y - 1.0, x + 4, y + 1.0, lw=0.3, layer='A-CEIL', color=CC, fill=(1.0, 0.93, 0.70)),
         'Световая ниша (LED)'),
        (lambda s, x, y: [s.rect(x - 4, y - 1.5, x + 4, y + 1.5, lw=0.35, layer='A-CEIL', color=DARK, fill=BUILT)] +
         [s.line(a_, b_, lw=0.1, layer='A-CEIL', color=MID) for a_, b_ in poly_scan([(x - 4, y - 1.5), (x + 4, y - 1.5), (x + 4, y + 1.5), (x - 4, y + 1.5)], -45, 1.2)],
         'Встроенная мебель до потолка'),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.12, layer='A-CEIL', color=CC), S.get('profile_label', 'Теневой профиль')),
    ] + ([
        (lambda s, x, y: s.rect(x - 4, y - 0.6, x + 4, y + 0.6, lw=0.3, layer='A-CEIL', color=CC, fill=WHITE, dash=(1.2, 0.6)),
         'Паз под встраиваемый трек')] if getattr(D, 'TRACKS', None) else []) + [
        (lambda s, x, y, _c=COLORS.get(c_, c_), _kw=kw_: s.line((x - 4, y), (x + 4, y), color=_c, **_kw), t_)
        for c_, kw_, t_ in S.get('legend_extra', [])] + [
        (lambda s, x, y: SY.light_c(s, (x, y), 'fan', col=VC), 'Вентилятор вытяжной'),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.6, layer='M-VENT', color=VC, dash=(2.0, 0.8)), 'Воздуховод над потолком'),
        (lambda s, x, y: s.rect(x - 2.2, y - 0.6, x + 2.2, y + 0.6, lw=0.3, layer='M-VENT', color=VC, fill=(0.80, 0.95, 0.92)),
         'Приточный клапан (стена, +2,100)'),
    ], width=26)
    frame(sh, no, total, 'План потолков')
    return sh


# =============================== 10 ОСВЕЩЕНИЕ ===============================
LIGHT_LEGEND = [
    ('spot', 'Светильник встраиваемый поворотный, GU10/LED 7 Вт, 3000 K'),
    ('spot44', 'То же, IP44 (санузлы)'),
    ('spot65', 'То же, IP65 (душевая зона)'),
    ('pend', 'Подвесной светильник'),
    ('track', 'Магнитный трек встраиваемый со спотами'),
    ('led', 'Светодиодная лента в профиле 2700–3000 K'),
    ('linear', 'Линейный светильник'),
    ('sconce', 'Бра настенное'),
    ('wall44', 'Настенный светильник IP44'),
    ('fan', 'Вентилятор вытяжной (в группе со светом)'),
    ('mirrorled', 'Питание подсветки зеркала'),
]


def group_links(sh, v, color=None, lw=0.25):
    """Светильники одной группы связаны прерывистой линией (минимальное остовное дерево) — для наглядности."""
    color = color or SY.EL_RED
    groups = {}
    for L in D.LIGHTS:
        if L['kind'] in ('mirrorled', 'led'):      # LED-ленты — без связи с линией управления (стандарт бюро)
            continue
        if 'p' in L:
            reps = [v.P(*L['p'])]
        else:
            a_, b_ = v.P(*L['a']), v.P(*L['b'])
            reps = [a_, b_, ((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2)]
        groups.setdefault(L['g'], []).append(reps)
    for g, nodes in groups.items():
        if len(nodes) < 2:
            continue
        inside = {0}
        while len(inside) < len(nodes):
            best = None
            for i in inside:
                for j in range(len(nodes)):
                    if j in inside:
                        continue
                    for p in nodes[i]:
                        for q in nodes[j]:
                            d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                            if best is None or d < best[0]:
                                best = (d, j, p, q)
            _, j, p, q = best
            sh.line(p, q, lw=lw, layer='E-LINK', color=color, dash=(1.6, 1.0))
            inside.add(j)


def draw_lights(sh, v, labels=True, links=True):
    """Рисует светильники; возвращает габариты подписей и знаков (для обхода другими подписями)."""
    boxes = []
    if links:
        group_links(sh, v)
    for L in D.LIGHTS:
        k = L['kind']
        if k in ('track', 'led', 'linear'):
            a, b = v.P(*L['a']), v.P(*L['b'])
            SY.light_c(sh, None, k, a=a, b=b)
            if labels:
                m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                txt = D.gcode(L['g'])
                sh.text((m[0] + 1.2, m[1] + 1.2), txt, h=1.7, layer='E-LIGHT',
                        color=SY.ORANGE if k == 'led' else SY.EL_RED, font='BoldObl', bg=True)
                boxes.append((m[0] + 1.2, m[0] + 1.2 + tw(txt, 1.7, 'BoldObl'), m[1] + 1.2, m[1] + 2.9))
        else:
            P = v.P(*L['p'])
            N = None
            if k in ('sconce', 'wall44', 'mirrorled'):
                N = _wall_normal_for_light(L)
            SY.light_c(sh, P, k, N=N)
            boxes.append((P[0] - 2.0, P[0] + 2.0, P[1] - 2.0, P[1] + 2.0))
            if labels:
                off = (1.9, 1.6) if k != 'pend' else (2.6, 2.4)
                txt = D.gcode(L['g'])
                sh.text((P[0] + off[0], P[1] + off[1]), txt, h=1.7, layer='E-LIGHT', font='BoldObl', bg=True,
                        color=SY.EL_RED)
                boxes.append((P[0] + off[0], P[0] + off[0] + tw(txt, 1.7, 'BoldObl'), P[1] + off[1], P[1] + off[1] + 1.7))
    return boxes


def _wall_normal_for_light(L):
    x, y = L['p']
    room = L['room']
    poly = D.ROOMS[room]['poly']
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    if 'n' in L:
        return SY.sheet_normal(L['n'])
    if L.get('wall') == 'x':
        n = (1, 0) if abs(x - min(xs)) < abs(x - max(xs)) else (-1, 0)
    else:
        n = (0, 1) if abs(y - min(ys)) < abs(y - max(ys)) else (0, -1)
    return SY.sheet_normal(n)


def light_dims(sh, v):
    """Привязки светильников по осям от чистовых стен (annot.LIGHT['dims']), h=2,0."""
    DP.dims_list(sh, v, ann('LIGHT', 'dims', []), h=2.0)


def sheet_lighting(no, total):
    sh, v, pen = base('10', 'План освещения', furniture='faint')
    finish_base(sh, v, pen, faint_doors=True)
    draw_lights(sh, v)
    light_dims(sh, v)
    tags(sh, v, names=False, pos=tag_pos('lgt'))
    title(sh, 'ПЛАН ОСВЕЩЕНИЯ  М 1:50', 'код у светильника: номер помещения + буква группы (см. план управления освещением)')
    rows = [[D.gcode(g), d] for g, d in D.GROUPS.items()]
    half = (len(rows) + 1) // 2
    table(sh, 23, 97, [16, 85], ['Группа', 'Назначение'], rows[:half], aligns=['c', 'l'], wraps=[False, True],
          row_h=4.0, h=1.6, head_h=5.5, title='Группы освещения', title_h=2.3)
    table(sh, 126, 97, [16, 85], ['Группа', 'Назначение'], rows[half:], aligns=['c', 'l'], wraps=[False, True],
          row_h=4.0, h=1.6, head_h=5.5)
    notes(sh, 233, 98, 178, 'Примечания (электрика)', (ann('LIGHT', 'notes') or LIGHT_NOTES) + elec_notes()[4:],
          h=1.65, lead=2.45, title_h=2.3)
    used = {L['kind'] for L in D.LIGHTS}
    leg = [(k, t) for k, t in (ann('LIGHT', 'legend') or LIGHT_LEGEND) if k in used or ann('LIGHT', 'legend')]
    legend_box(sh, 376, 281, [(SY.lg_light_c(k), t) for k, t in leg] +
               [(lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.25, color=SY.EL_RED, dash=(1.6, 1.0), layer='E-LINK'),
                 'Светильники одной группы (одно подключение)')], width=26, h=1.7)
    frame(sh, no, total, 'План освещения')
    return sh


LIGHT_NOTES = [
    'Светильники одной группы (одно подключение) связаны красным пунктиром (LED-ленты — без линии связи, по коду группы); код у светильника = код у выключателя.',
    'Привязки — по осям светильников от чистовых стен. Санузлы: душ — IP65, остальное — IP44, УЗО 30 мА.',
    'Цветовая температура 3000 K, ниши — 2700 K, CRI ≥ 90.',
]


def elec_notes():
    return ann('ELEC_NOTES') or ELEC_NOTES


ELEC_NOTES = [
    'Высоты — от ±0,000 (чистый пол) до низа рамки; привязки — от чистовых поверхностей стен до оси поста (после штукатурки — контрольный обмер).',
    'Выключатели и терморегуляторы — +0,900 по всей квартире. От края дверного проёма до оси первого поста — не менее 100 мм (коробка двери ≈ 100 мм, нужно основание под подрозетник); в проекте — 150.',
    'Изделия на одной высоте — в общих рамках, шаг постов 71 мм; размеры даны до оси крайнего поста со стороны проёма.',
    'Розетки санузлов, балкона, КНС, СМ и сушки — IP44, линии через УЗО 30 мА; в санузле — вне зон 0–2 (ГОСТ Р 50571.7.701-2013).',
    'Трассы — по потолку в гофре, к выводам — вертикально; не сверлить ближе 150 мм к осям выводов. Нагрузки, щит, сечения — по электропроекту.',
]


# =============================== 11 ВЫКЛЮЧАТЕЛИ ===============================
SW_KINDS = ('v1', 'v2', 'v1p', 'v2p', 'tr')


def sheet_switches(no, total):
    import pts as PT
    sh, v, pen = base('11', 'План управления освещением', furniture='faint')
    finish_base(sh, v, pen, faint_doors=True)
    # светильники — красные, с кодами групп; светильники одной группы связаны пунктиром; к выключателям линий нет
    import core as CORE
    lboxes = draw_lights(sh, v, labels=True, links=True)
    swpts = [P for P in D.POINTS if P['kind'] in SW_KINDS]

    def dfn(sh_, Ps, N, P):
        return SY.switch_c(sh_, Ps, N, P['kind'])

    def lfn(P):
        if P['kind'] == 'tr':
            return D.gcode(P['g'][0])
        return ';'.join(D.gcode(g) for g in P['g'])

    def cfn(P):
        return SY.TR_ORANGE if P['kind'] == 'tr' else SY.SW_BLUE

    def ffn(cl):
        zs = {P['z'] for P in cl}
        return '+' + str(zs.pop()) if len(zs) == 1 else ''
    # привязки — до оси первого поста со стороны проёма (каждая отдельно)
    CORE.DIM_BOXES.clear()
    for args in ann('SWITCH', 'dims', []):
        mdim(sh, v, args[0], args[1], args[2], ext=args[3], h=2.2, prefer=args[4] if len(args) > 4 else None)
    sym = []
    if ann('SWITCH', 'avoid_lights'):         # подписи выключателей не накладываются на значки светильников
        for L_ in D.LIGHTS:
            if 'p' in L_ and L_['kind'] not in ('sconce', 'wall44', 'mirrorled'):
                X_, Y_ = v.P(*L_['p'])
                sym.append((X_ - 2.4, X_ + 2.4, Y_ - 2.4, Y_ + 2.4))
    # подписи не ложатся на знаки выключателей (соседние рамки) — читаемость кодов групп
    for P_ in swpts:
        X_, Y_ = v.P(*P_['p'])
        sym.append((X_ - 2.0, X_ + 2.0, Y_ - 2.0, Y_ + 2.0))
    PT.LABEL_GAP = ann('SWITCH', 'label_gap', 0.8)
    try:
        PT.draw_clusters(sh, v, swpts, dfn, lfn, spacing=3.8, label_h=ann('SWITCH', 'label_h', 2.1), colorfn=cfn,
                         framefn=ffn, merge_same=False, obstacles=lboxes + list(CORE.DIM_BOXES) + sym)
    finally:
        PT.LABEL_GAP = 0.6
    tags(sh, v, names=False, pos=tag_pos('swi'))
    title(sh, 'ПЛАН УПРАВЛЕНИЯ ОСВЕЩЕНИЕМ  М 1:50', 'выключатели и терморегуляторы — низ +0,900; код у выключателя = код группы у светильника')
    rows = []
    for P in D.POINTS:
        if P['kind'] in ('v1', 'v2', 'v1p', 'v2p'):
            nm = {'v1': 'одноклавишный', 'v2': 'двухклавишный', 'v1p': 'одноклав. проходной', 'v2p': 'двухклав. проходной'}[P['kind']]
            rows.append([P['room'], nm, '; '.join(D.gcode(g) for g in P['g']), '+0,900'])
    half = (len(rows) + 1) // 2
    table(sh, 23, 97, [10, 40, 34, 14], ['Пом.', 'Выключатель', 'Группы', 'Высота'], rows[:half], aligns=['c', 'l', 'c', 'c'],
          row_h=4.0, h=1.6, head_h=5.5, title='Ведомость выключателей', title_h=2.3)
    table(sh, 125, 97, [10, 40, 34, 14], ['Пом.', 'Выключатель', 'Группы', 'Высота'], rows[half:], aligns=['c', 'l', 'c', 'c'],
          row_h=4.0, h=1.6, head_h=5.5)
    notes(sh, 233, 98, 178, 'Примечания (электрика)', elec_notes() + ann('SWITCH', 'notes_extra', [
        'Выключатель управляет светильниками с тем же кодом (3Б — пом. 03, группа Б).']), h=1.65, lead=2.45, title_h=2.3)
    legend_box(sh, 376, 281, [
        (SY.lg_switch_c('v1'), 'Выключатель одноклавишный'), (SY.lg_switch_c('v2'), 'Выключатель двухклавишный'),
        (SY.lg_switch_c('v1p'), 'Выключатель проходной одноклавишный'), (SY.lg_switch_c('v2p'), 'Выключатель проходной двухклавишный'),
        (lambda s, x, y: SY.switch_c(s, (x, y - 1.5), (0, 1), 'tr'), 'Терморегулятор тёплого пола'),
        (lambda s, x, y: (SY.light_c(s, (x - 2, y), 'spot'),
                          s.text((x + 0.2, y + 0.6), '3Б', h=1.6, layer='E-LIGHT', color=SY.EL_RED, font='BoldObl')),
         'Светильник с кодом группы'),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.25, color=SY.EL_RED, dash=(1.6, 1.0), layer='E-LINK'),
         'Светильники одной группы'),
        (lambda s, x, y: s.text((x, y), '+900', h=1.5, ha='c', va='m', layer='A-TEXT'), 'Высота рамки (до низа)'),
    ], width=26, h=1.7)
    frame(sh, no, total, 'План управления\nосвещением')
    return sh


# =============================== 12 РОЗЕТКИ ===============================
OUT_KINDS = ('r1', 'r2', 'r2u', 'r1w', 'r2w', 'pow', 'out', 'tvblock', 'medblock', 'deskblock', 'shk', 'ssh', 'int')


def out_label(P):
    """Подпись вывода: высота у каждого изделия (в т. ч. +300), для выводов — назначение."""
    if P['kind'] in ('shk', 'ssh'):
        return ('ЩК' if P['kind'] == 'shk' else 'СЩ') + ' +' + str(P['z'])
    if P['kind'] == 'pow':
        return '32А +' + str(P['z'])
    lab = '+' + str(P['z'])
    if P['kind'] == 'out':
        lab = (P.get('tag', '') + ' ' + lab).strip()
    return lab


def sheet_outlets(no, total):
    import pts as PT
    sh, v, pen = base('12', 'План розеток', furniture='faint')
    finish_base(sh, v, pen, faint_doors=True)
    opts = [P for P in D.POINTS if P['kind'] in OUT_KINDS]

    def dfn(sh_, Ps, N, P):
        return SY.outlet_c(sh_, Ps, N, P['kind'])

    def cfn(P):
        return SY.LOW_GREEN if P['kind'] in ('ssh', 'int') else (0.55, 0.05, 0.05)
    import core as CORE
    CORE.DIM_BOXES.clear()
    S = ann('OUTLET') or {}
    PT.auto_wall_dims(sh, v, opts, off=S.get('wall_off', 650), offs=S.get('offs', {}), skip_keys=S.get('skip', set()))
    DP.dims_list(sh, v, S.get('dims', []), h=2.2)
    PT.draw_clusters(sh, v, opts, dfn, out_label, spacing=3.6, colorfn=cfn, obstacles=list(CORE.DIM_BOXES))
    tags(sh, v, names=False, pos=tag_pos('out'))
    title(sh, 'ПЛАН РОЗЕТОК И ВЫВОДОВ  М 1:50', 'высота — у каждого изделия, до низа рамки; совмещённые выводы условно разнесены')
    rows = S.get('rows') or power_rows_default()
    table(sh, 23, 97, [12, 52, 58, 30], ['Пом.', 'Потребитель', 'Вывод', 'Примечание'], rows,
          aligns=['c', 'l', 'l', 'l'], row_h=4.2, h=1.65, head_h=5.5, title='Силовые и специальные выводы', title_h=2.3)
    notes(sh, 233, 98, 178, 'Примечания (электрика)', elec_notes() + S.get('notes_extra', [
        'Типовые высоты: розетки +0,300; у столешницы +1,100; у кровати +0,650; над столами +0,900; ТВ +1,000 (за экраном).']),
          h=1.65, lead=2.45, title_h=2.3)
    legend_box(sh, 376, 281, [
        (SY.lg_outlet_c('r1'), 'Розетка с заземлением'), (SY.lg_outlet_c('r2'), 'Розетка двойная'),
        (SY.lg_outlet_c('r2u'), 'Двойная с USB'), (SY.lg_outlet_c('r1w'), 'Розетка IP44 с крышкой'),
        (SY.lg_outlet_c('r2w'), 'Двойная IP44'),
        (SY.lg_outlet_c('pow'), 'Силовой кабельный вывод'), (SY.lg_outlet_c('out'), 'Вывод кабеля (подсветка, кондиционер и т. п.)'),
        (SY.lg_outlet_c('tvblock'), 'Блок: 2Р + TV / RJ45'), (SY.lg_outlet_c('deskblock'), 'Блок: 3Р + RJ45'),
        (SY.lg_outlet_c('shk'), 'Щит квартирный ЩК'), (SY.lg_outlet_c('ssh'), 'Слаботочный щит СЩ'),
        (SY.lg_outlet_c('int'), 'Домофон'),
        (lambda s, x, y: s.text((x, y), '+300', h=1.4, ha='c', va='m', layer='A-TEXT', color=(0.55, 0.05, 0.05)),
         'Высота до низа рамки, мм'),
    ], width=26, h=1.7)
    frame(sh, no, total, 'План розеток и выводов')
    return sh


# =============================== 13 САНТЕХНИКА ===============================
def fixture_name(P):
    """Что подключается к выводу: «С13 мойка / ПММ» -> «мойка / ПММ»."""
    import re as _re
    return _re.sub(r'^[А-ЯA-Z]\d+(/[А-ЯA-Z]\d+)?\s+', '', P.get('fx', '') or '').strip()


def plumb_layer(sh, v, k=50.0, labels=True, dims=False, bbox=None, routes=None):
    """Выводы сантехприборов. Стандарт бюро: линии подключения (подводки, трассы) не чертятся — у вывода подписано,
    что к нему подключается, и высота; routes=True (annot.PLUMB_SHEET['routes']) — трассы как раньше."""
    def inb(p):
        return bbox is None or (bbox[0] <= p[0] <= bbox[2] and bbox[1] <= p[1] <= bbox[3])
    if routes is None:
        routes = ann('PLUMB_SHEET', 'routes', False)
    if routes:
        for pts_, lab in D.SEWER_ROUTES:
            if not all(inb(p) for p in pts_):
                continue
            P = [v.P(*p) for p in pts_]
            sh.poly(P, closed=False, lw=0.45 if k >= 50 else 0.7, layer='P-SEWER', color=SY.BROWN, dash=(2.0, 0.8))
        if bbox is None:
            for pts_, lab in getattr(D, 'PRESS_ROUTES', []):
                P = [v.P(*p) for p in pts_]
                sh.poly(P, closed=False, lw=0.5, layer='P-SEWER', color=SY.BROWN, dash=(3.0, 0.7, 0.6, 0.7))
            for pts_, lab in getattr(D, 'WATER_ROUTES', []):
                P = [v.P(*p) for p in pts_]
                sh.poly(P, closed=False, lw=0.35, layer='P-WATER', color=SY.BLUE, dash=(1.2, 0.8))
    for R in D.RISERS:
        if inb(R['p']):
            SY.plumb(sh, v.P(*R['p']), R['kind'])
    import pts as PT
    wallpts = []
    floor_named = set()
    for P in D.PLUMB:
        if not inb(P['p']):
            continue
        X, Y = v.P(*P['p'])
        N = SY.sheet_normal(P['n']) if P['n'] else (0, 0)
        SY.plumb(sh, (X, Y), P['kind'], N=N)
        if P['n']:
            wallpts.append(P)
        elif labels:
            lab = P.get('label') or fixture_name(P)
            if lab and lab not in floor_named:
                floor_named.add(lab)
                sh.text((X + 2.4, Y + 2.0), lab + (' (в полу)' if P['kind'] != 'k50' or 'трап' not in lab else ''),
                        h=1.5, layer='A-TEXT', bg=True)
    if labels:
        short = {'hvs': 'Х', 'gvs': 'Г', 'k50': 'К', 'k110': 'К', 'tap': 'кран', 'sif': 'сифон'}
        for key, cl in PT.clusters(wallpts, gap=260):
            byfx = {}
            for P in cl:
                byfx.setdefault(fixture_name(P) or '—', {}).setdefault(P['z'], []).append(short[P['kind']])
            parts = []
            for fx, byz in byfx.items():
                hz = ' · '.join('/'.join(sorted(set(ks))) + ' +' + str(z) for z, ks in sorted(byz.items(), reverse=True))
                parts.append(f'{fx}: {hz}')
            txt = '; '.join(parts)
            cx = sum(P['p'][0] for P in cl) / len(cl)
            cy = sum(P['p'][1] for P in cl) / len(cl)
            N = SY.sheet_normal(cl[0]['n'])
            C = v.P(cx, cy)
            d = 5.2 if k < 50 else 4.0
            sh.text((C[0] + N[0] * d, C[1] + N[1] * d), txt, h=1.5 if k < 50 else 1.3, ha='c', va='m', layer='A-TEXT',
                    bg=True, rot=90 if N[1] == 0 else 0)


def sheet_plumbing(no, total):
    from core import View, Pen as _Pen
    sh, v, pen = base('13', 'План сантехники', furniture='faint')
    finish_base(sh, v, pen, faint_doors=True)
    plumb_layer(sh, v, labels=False)
    S = ann('PLUMB_SHEET') or {}
    draw_prims(sh, v, pen, S.get('draw'))
    F = S.get('frag') or frag_default()
    clipr = F['rect']
    pen.rect(*clipr, lw=0.3, layer='A-TEXT', dash=(3.0, 1.0, 0.6, 1.0))
    tags(sh, v, names=False, pos=tag_pos('plb'))
    # ---- фрагмент мокрых зон М 1:25
    fv = View(X0=F['X0'], Y0=F['Y0'], k=F['k'])
    fp = _Pen(sh, fv)
    for it in D.ITEMS:
        if it['room'] in F['rooms']:
            DP.draw_item(fp, it, faint_=True)
    # стены фрагмента (отсечённые)
    from kit import clip_seg_rect
    for r in D.WALLS:
        x0 = max(r[0], clipr[0]); y0 = max(r[1], clipr[1]); x1 = min(r[2], clipr[2]); y1 = min(r[3], clipr[3])
        if x1 > x0 and y1 > y0:
            fp.rect(x0, y0, x1, y1, fill=WALLFILL, stroke=False, layer='A-WALL-FILL')
    from core import wall_union_edges, wall_outline
    if D.WALL_POLYS:
        crect = [(clipr[0], clipr[1]), (clipr[2], clipr[1]), (clipr[2], clipr[3]), (clipr[0], clipr[3])]
        for p in D.WALL_POLYS:
            pp = clip_poly_convex(list(p), crect)
            if len(pp) >= 3:
                fp.poly(pp, fill=WALLFILL, stroke=False, layer='A-WALL-FILL')
    for a, b in (wall_outline(D.WALLS, D.WALL_POLYS) if D.WALL_POLYS else wall_union_edges(D.WALLS)):
        c = clip_seg_rect(a, b, clipr)
        if c:
            fp.line(c[0], c[1], lw=0.5, layer='A-WALL')
    if D.SHAFT:
        x0, y0, x1, y1 = D.SHAFT
        fp.rect(x0, y0, x1, y1, lw=0.25, layer='A-HATCH')
        fp.line((x0, y0), (x1, y1), lw=0.18, layer='A-HATCH')
        fp.line((x0, y1), (x1, y0), lw=0.18, layer='A-HATCH')
    plumb_layer(sh, fv, k=F['k'], labels=True, bbox=clipr)
    for p, t in S.get('frag_labels', []):
        X, Y = fv.P(*p)
        sh.text((X, Y + 2.2), t, h=1.5, ha='c', va='m', layer='A-TEXT', color=SY.BROWN, bg=True)
    DP.dims_list(sh, fv, S.get('frag_dims', []), h=2.0)
    if S.get('frag_text'):
        X_, Y_ = fv.P(*S['frag_text'][0])
        sh.text((X_, Y_), S['frag_text'][1], h=1.5, ha='c', va='m', layer='A-TEXT', bg=True)
    from kit import section_title
    section_title(sh, F['title_at'][0], F['title_at'][1], F['title'], f"М 1:{int(F['k'])}", h=2.6)
    title(sh, 'ПЛАН САНТЕХНИКИ  М 1:50', 'выводы к приборам: что подключается и высота от ±0,000; линии подключения не показаны')
    if S.get('notes'):
        notes(sh, 233, 98, 178, 'Примечания', S['notes'], h=1.9, lead=2.9)
    routes = S.get('routes', False)
    legend_box(sh, 376, 281, [
        (SY.lg_plumb('hvs'), 'Вывод ХВС (Х)'), (SY.lg_plumb('gvs'), 'Вывод ГВС (Г)'),
        (SY.lg_plumb('k50'), 'Канализация (К): раковина, мойка, трап'),
        (SY.lg_plumb('k110'), 'Канализация (К): унитаз'), (SY.lg_plumb('tap'), 'Кран для СМ / ПММ'),
        (SY.lg_plumb('sif'), 'Сифон для СМ'),
        (lambda s, x, y: s.text((x, y), 'Х +500', h=1.3, ha='c', va='m', layer='A-TEXT'),
         'У вывода: прибор, вывод и высота, мм (мойка: Х/Г +500)')] + ([] if not routes else [
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.45, layer='P-SEWER', color=SY.BROWN, dash=(2.0, 0.8)),
         'Трасса канализации'),
        *([((lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.5, layer='P-SEWER', color=SY.BROWN, dash=(3.0, 0.7, 0.6, 0.7)),
         'Напорная линия от КНС'))] if getattr(D, 'PRESS_ROUTES', None) else []),
        (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.35, layer='P-WATER', color=SY.BLUE, dash=(1.2, 0.8)),
         'Подводки ХВС/ГВС к кухне'),
    ]), width=26, h=1.7)
    frame(sh, no, total, 'План сантехнических\nприборов и выводов')
    return sh


# =============================== 14 ДВЕРИ ===============================
def _hexmark(sh, X, Y, txt, col, w=4.8):
    pts = [(X - w / 2, Y), (X - w / 4, Y + 2.0), (X + w / 4, Y + 2.0), (X + w / 2, Y), (X + w / 4, Y - 2.0), (X - w / 4, Y - 2.0)]
    light = tuple(1 - (1 - c) * 0.25 for c in col)
    sh.poly(pts, lw=0.4, layer='A-TEXT', fill=light, color=col)
    sh.text((X, Y), txt, h=1.8, ha='c', va='m', layer='A-TEXT', font='BoldObl', color=col)


def sheet_doors(no, total):
    sh, v, pen = base('14', 'План дверей', furniture='faint')
    finish_base(sh, v, pen)
    TCOL = {T['mark']: T['col'] for T in D.DOOR_TYPES}
    for k, mark in D.DOOR_MARK.items():
        col = TCOL[mark]
        DP.door(pen, k, color=col, fill=tuple(1 - (1 - c) * 0.18 for c in col))
    S = ann('DOORS_SHEET') or {}
    marks = S.get('marks') or door_marks_default()
    for k, p in marks.items():
        X, Y = v.P(*p)
        _hexmark(sh, X, Y, D.DOOR_MARK[k], TCOL[D.DOOR_MARK[k]])
    tags(sh, v, names=True, pos=tag_pos('dor'))
    title(sh, 'ПЛАН ДВЕРЕЙ  М 1:50', 'одинаковые двери — один тип; цвет полотна = цвет марки')
    if not S.get('schedule_sheet'):           # иначе ведомость с эскизами — отдельным листом (sheet_door_schedule)
        rows = [[T['mark'], T['name'], T['opening'], T['leaf'], T['finish'], str(T['qty']), T['note']] for T in D.DOOR_TYPES]
        table(sh, 23, 97, [11, 40, 18, 18, 46, 9, 62],
              ['Марка', 'Тип', 'Проём', 'Полотно', 'Отделка', 'Кол.', 'Примечание'], rows,
              aligns=['c', 'l', 'c', 'c', 'l', 'c', 'l'], wraps=[False, True, False, False, True, False, True],
              row_h=6.0, h=1.9, head_h=6.0, title='Ведомость дверей', title_h=2.6)
    if S.get('notes'):
        notes(sh, 233, 98, 178, 'Примечания', S['notes'], h=1.8, lead=2.7)
    legend_box(sh, 376, 281, [(lambda s, x, y, T=T: _hexmark(s, x, y, T['mark'], T['col'], w=4.4),
                               f"{T['mark']} — {T['name'].lower()}, {T['qty']} шт.") for T in D.DOOR_TYPES], width=26)
    frame(sh, no, total, 'План дверей' if S.get('schedule_sheet') else 'План дверей.\nВедомость дверей')
    return sh


def door_hand(key):
    """Сторона петель при виде со стороны открывания (дверь открывается на смотрящего): 'L' или 'R'."""
    d = D.DOORS[key]
    cx, cy = d['c']; ox, oy = d['o']
    # модель (x вниз, y вправо) -> лист (E, N) = (y, -x); взгляд — против открывания (-o)
    vE, vN = -oy, ox
    rE, rN = vN, -vE                                 # правая рука смотрящего
    hE, hN = -cy, cx                                 # от центра полотна к петле (-c)
    return 'R' if hE * rE + hN * rN > 0 else 'L'


def door_sketch(sh, T, cx, y0, k=40.0):
    """Эскиз двери типа T (вид со стороны открывания), низ — y0, ось — cx (мм листа).
    T: w, h — полотно; ow, oh — проём; style 'panel' | 'flat' | 'metal'; hand — 'L'/'R' (по первой двери типа)."""
    from elev import EV, FV
    w, h = T['w'], T['h']
    ow, oh = T.get('ow', w + 100), T.get('oh', h + 70)
    hand = T.get('hand') or door_hand(T['keys'][0])
    ev = EV(cx - ow / 2 / k, y0, k)
    s0 = (ow - w) / 2                                 # полотно — по центру проёма
    col = T.get('col', (0.4, 0.4, 0.4))
    leaf_fill = T.get('fill') or tuple(1 - (1 - c) * 0.15 for c in col)
    P = ev.P
    # проём (штрих), наличники 70, коробка 30
    sh.rect(*P(0, 0), *P(ow, oh), lw=0.2, layer='A-DET', dash=(1.0, 0.6), color=MID)
    if T.get('style') != 'metal':
        sh.rect(*P(s0 - 100, 0), *P(s0 + w + 100, h + 100), lw=0.3, layer='A-DET', fill=(0.97, 0.96, 0.93))
        sh.rect(*P(s0 - 30, 0), *P(s0 + w + 30, h + 30), lw=0.25, layer='A-DET', fill=(0.95, 0.94, 0.90))
    else:
        sh.rect(*P(s0 - 50, 0), *P(s0 + w + 50, h + 50), lw=0.35, layer='A-DET', fill=(0.30, 0.30, 0.32))
    sh.rect(*P(s0, 0), *P(s0 + w, h), lw=0.4, layer='A-DET', fill=leaf_fill)
    if T.get('style') == 'panel':                     # филёнки с раскладкой
        for z0, z1 in ((140, 760), (900, h - 140)):
            sh.rect(*P(s0 + 110, z0), *P(s0 + w - 110, z1), lw=0.25, layer='A-DET')
            sh.rect(*P(s0 + 140, z0 + 30), *P(s0 + w - 140, z1 - 30), lw=0.12, layer='A-DET', color=MID)
    # петли и ручка
    hx = s0 if hand == 'L' else s0 + w
    for zz in (220, h - 320):
        sh.rect(*P(hx - 12, zz), *P(hx + 12, zz + 100), lw=0.15, layer='A-DET', fill=(0.75, 0.62, 0.30))
    gx = s0 + w - 70 if hand == 'L' else s0 + 70
    sh.rect(*P(gx - 15, 960), *P(gx + 15, 1040), lw=0.15, layer='A-DET', fill=(0.75, 0.62, 0.30))
    sh.line(P(gx, 1000), P(gx + (-130 if hand == 'L' else 130), 1000), lw=0.5, layer='A-DET', color=(0.6, 0.48, 0.2))
    # линии открывания в ведомости не показываются (стандарт бюро): сторона петель — в строке «Открывание»
    fv = FV(ev)
    mdim(sh, fv, 'y', [s0, s0 + w], -180, ext=0, h=1.6)
    mdim(sh, fv, 'y', [0, ow], -420, ext=0, h=1.6)
    mdim(sh, fv, 'x', [0, h], ow + 230, ext=s0 + w if T.get('style') == 'metal' else s0 + w + 100, h=1.6)
    return ev


def sheet_door_schedule(no, total):
    """Ведомость дверей с эскизами: столбец на тип (одинаковые по размеру и работе двери — один тип)."""
    sh = Sheet('14b', 'Ведомость дверей')
    S = ann('DOORS_SHEET') or {}
    types = D.DOOR_TYPES
    x0, top = 25.0, 278.0
    hw = 38.0
    cw = min(92.0, (385.0 - hw) / len(types))
    k = S.get('sketch_k', 40.0)
    rows = [('Марка', 9.0, lambda T: T['mark']),
            ('Эскиз (вид со стороны\nоткрывания), М 1:' + str(int(k)), 78.0, None),
            ('Проём, мм', 7.0, lambda T: T['opening'] + (' × ' + str(T['oh']) if T.get('oh') else '')),
            ('Полотно, мм', 7.0, lambda T: T['leaf']),
            ('Тип', 12.0, lambda T: T['name']),
            ('Отделка', 14.0, lambda T: T['finish']),
            ('Фурнитура', 12.0, lambda T: T.get('hw_full', '')),
            ('Открывание', 9.0, lambda T: ('петли справа' if (T.get('hand') or door_hand(T['keys'][0])) == 'R' else 'петли слева')
             + ' (вид со стороны открывания)'),
            ('Где', 9.0, lambda T: '; '.join(next((d_['where'] for d_ in getattr(D, 'DOOR_SCHED', []) if d_['key'] == k_), k_)
                                             for k_ in T['keys'])),
            ('Кол., шт', 7.0, lambda T: str(T['qty'])),
            ('Примечание', 12.0, lambda T: T['note'])]
    sh.text((x0, top + 5), 'Ведомость дверей', h=2.8, layer='A-TEXT', font='BoldObl')
    y = top
    W = hw + cw * len(types)
    sh.line((x0, y), (x0 + W, y), lw=0.5, layer='A-TEXT')
    for name, rh, fn in rows:
        yb = y - rh
        lines = name.split('\n')
        for i, ln in enumerate(lines):
            sh.text((x0 + 1.5, y - rh / 2 + (len(lines) - 1) * 1.4 - i * 2.8), ln, h=1.8, va='m', layer='A-TEXT')
        for j, T in enumerate(types):
            cx = x0 + hw + cw * (j + 0.5)
            if fn is None:
                door_sketch(sh, T, cx, yb + 14.0, k)
            else:
                txt = fn(T)
                from kit import wrap
                ls = wrap(txt, cw - 4, 1.7)
                bold = name == 'Марка'
                if bold:
                    _hexmark(sh, cx, y - rh / 2, txt, T['col'])
                    continue
                for i, ln in enumerate(ls[:4]):
                    sh.text((cx, y - rh / 2 + (min(len(ls), 4) - 1) * 1.35 - i * 2.7), ln, h=1.7, ha='c', va='m',
                            layer='A-TEXT')
        sh.line((x0, yb), (x0 + W, yb), lw=0.5 if name in ('Марка',) else 0.25, layer='A-TEXT')
        y = yb
    for j in range(len(types) + 1):
        xx = x0 + hw + cw * j
        sh.line((xx, top), (xx, y), lw=0.5 if j == 0 else 0.25, layer='A-TEXT')
    sh.rect(x0, y, x0 + W, top, lw=0.6, layer='A-TEXT')
    if S.get('notes'):
        notes(sh, 25, y - 8, 200, 'Примечания', S['notes'], h=1.8, lead=2.7)
    frame(sh, no, total, 'Ведомость дверей')
    return sh


# =============================== 15 ВЕНТИЛЯЦИЯ ===============================
def sheet_vent(no, total):
    sh, v, pen = base('15', 'План вентиляции', furniture='faint')
    finish_base(sh, v, pen, faint_doors=True)
    VC = (0.10, 0.45, 0.45)
    S = ann('VENT_SHEET') or {}
    routes = S.get('routes', False)       # стандарт бюро: только оборудование с привязками, без трасс и воздуховодов
    for it in D.ITEMS:                    # внутренние блоки кондиционеров
        if it['kind'] == 'ac' and D.item_rect(it):
            pen.rect(*D.item_rect(it), fill=(0.93, 0.90, 0.98), lw=0.35, layer='M-VENT', color=SY.VIOLET)
    for item in D.VENT:
        if item['kind'] in ('duct', 'acroute') and not routes:
            continue
        if item['kind'] == 'duct':
            P = [v.P(*p) for p in item['pts']]
            sh.poly(P, closed=False, lw=1.0, layer='M-VENT', color=VC)
            a, b = P[-2], P[-1]
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            sh.poly([b, (b[0] - 2.2 * math.cos(ang - 0.4), b[1] - 2.2 * math.sin(ang - 0.4)),
                     (b[0] - 2.2 * math.cos(ang + 0.4), b[1] - 2.2 * math.sin(ang + 0.4))], layer='M-VENT', fill=VC, color=VC, lw=0.1)
        elif item['kind'] == 'valve':
            X, Y = v.P(*item['p'])
            N = SY.sheet_normal(item['n'])
            T = (-N[1], N[0])
            box = [(X + T[0] * 2 , Y + T[1] * 2), (X - T[0] * 2, Y - T[1] * 2), (X - T[0] * 2 + N[0] * 1.5, Y - T[1] * 2 + N[1] * 1.5),
                   (X + T[0] * 2 + N[0] * 1.5, Y + T[1] * 2 + N[1] * 1.5)]
            sh.poly(box, lw=0.3, layer='M-VENT', color=VC, fill=WHITE)
            sh.line((X, Y), (X + N[0] * 4.5, Y + N[1] * 4.5), lw=0.3, layer='M-VENT', color=VC)
        elif item['kind'] == 'acroute':
            P = [v.P(*p) for p in item['pts']]
            sh.poly(P, closed=False, lw=0.5, layer='M-VENT', color=SY.VIOLET, dash=(2.0, 0.6, 0.5, 0.6))
    for L in D.LIGHTS:
        if L['kind'] == 'fan':
            SY.light(sh, v.P(*L['p']), 'fan')
    import core as CORE
    CORE.DIM_BOXES.clear()
    DP.dims_list(sh, v, S.get('dims', []), h=2.0)          # привязки оборудования от чистовых стен
    put_labels(sh, v, S.get('labels'))
    for p, t in S.get('marks', []):
        sh.text(v.P(*p), t, h=1.8, ha='c', va='m', layer='M-VENT', color=VC, font='BoldObl', bg=True)
    tags(sh, v, names=False)
    title(sh, 'ПЛАН ВЕНТИЛЯЦИИ И КОНДИЦИОНИРОВАНИЯ  М 1:50', 'оборудование и привязки от чистовых стен')
    if S.get('rows'):
        rows_ = [r[:3] for r in S['rows']]
        table(sh, 23, 97, [14, 18, 148], ['Марка', 'Пом.', 'Оборудование'], rows_, aligns=['c', 'c', 'l'],
              row_h=4.4, h=1.7, head_h=5.5, title='Оборудование вентиляции и кондиционирования', title_h=2.3, wraps=[False, False, True])
    if S.get('notes'):
        notes(sh, 233, 98, 178, 'Примечания', S['notes'], h=1.9, lead=2.9)
    leg = [(lambda s, x, y: s.rect(x - 4, y - 1.2, x + 4, y + 1.2, fill=(0.93, 0.90, 0.98), lw=0.35, layer='M-VENT',
                                   color=SY.VIOLET), 'Кондиционер, внутренний блок (К1…)'),
           (SY.lg_light('fan'), 'Вентилятор вытяжной (В1…)'),
           (lambda s, x, y: s.rect(x - 2, y - 0.8, x + 2, y + 0.8, lw=0.3, layer='M-VENT', color=VC), 'Приточный клапан (ПК)')]
    if routes:
        leg += [(lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=1.0, layer='M-VENT', color=VC), 'Воздуховод'),
                (lambda s, x, y: s.line((x - 4, y), (x + 4, y), lw=0.5, layer='M-VENT', color=SY.VIOLET,
                                        dash=(2.0, 0.6, 0.5, 0.6)), 'Трасса кондиционера')]
    legend_box(sh, 376, 281, leg, width=26)
    frame(sh, no, total, 'План вентиляции\nи кондиционирования')
    return sh
