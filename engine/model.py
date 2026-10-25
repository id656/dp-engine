# -*- coding: utf-8 -*-
"""Модель объекта для листов: данные из objects/<объект>/design.py (+ obmer.py) и расчётные функции.
Все модули движка обращаются к данным только через этот модуль: `import model as D`."""
from design import *            # noqa: F401,F403 — данные объекта
import design as _obj

# ---------------- значения по умолчанию (объект может переопределить в design.py) ----------------
HEAT_SKIP = getattr(_obj, 'HEAT_SKIP', ('rug', 'radiator', 'mirror', 'mirror_round', 'mirror_oval', 'shower', 'wallshelf',
                                        'ac', 'tv', 'lounge', 'round', 'chair'))
BUILTIN_KINDS = getattr(_obj, 'BUILTIN_KINDS', ('wardrobe', 'column', 'upper', 'wm_cab', 'shelving', 'box'))
PAINT_BEHIND = getattr(_obj, 'PAINT_BEHIND', 150)
CEIL_FEATURES = getattr(_obj, 'CEIL_FEATURES', [])
TRACKS = getattr(_obj, 'TRACKS', [])
VENT = getattr(_obj, 'VENT', [])
HEAT = getattr(_obj, 'HEAT', [])
PRESS_ROUTES = getattr(_obj, 'PRESS_ROUTES', [])
WATER_ROUTES = getattr(_obj, 'WATER_ROUTES', [])
SEWER_ROUTES = getattr(_obj, 'SEWER_ROUTES', [])
RISERS = getattr(_obj, 'RISERS', [])
TILE_LAYOUT = getattr(_obj, 'TILE_LAYOUT', [])
FLOOR_TILES = getattr(_obj, 'FLOOR_TILES', [])
WALL_ZONES = getattr(_obj, 'WALL_ZONES', [])
SHAFT = getattr(_obj, 'SHAFT', None)
try:                                  # стены с наклонными гранями (многоугольники) — из design или obmer
    import obmer as _obmer
except ImportError:                   # pragma: no cover
    _obmer = None
WALL_POLYS = list(getattr(_obj, 'WALL_POLYS', None) or getattr(_obmer, 'WALL_POLYS', None) or [])


def wall_extent():
    """Координаты всех стен (прямоугольники + многоугольники): (xs, ys) — для габаритов вида."""
    xs = [r[0] for r in WALLS] + [r[2] for r in WALLS]
    ys = [r[1] for r in WALLS] + [r[3] for r in WALLS]
    for p in WALL_POLYS:
        xs += [q[0] for q in p]
        ys += [q[1] for q in p]
    return xs, ys


def gcode(g):
    """Код группы для листов: '03д' -> '3Д' (номер помещения + буква группы); 'ТП05' -> 'Т05'."""
    if hasattr(_obj, 'gcode'):
        return _obj.gcode(g)
    if g.startswith('ТП'):
        return 'Т' + g[2:]
    return str(int(g[:2])) + g[2:].upper()


def item_rect(it):
    """Габарит предмета в плане (x0, y0, x1, y1) или None (для предмета-многоугольника 'pts' — габарит контура)."""
    if 'rect' in it:
        return it['rect']
    if 'pts' in it:
        xs = [p[0] for p in it['pts']]; ys = [p[1] for p in it['pts']]
        return (min(xs), min(ys), max(xs), max(ys))
    k = it['kind']
    if k in ('wc', 'vanity', 'mini_basin'):
        wall, face, axis = it['wall'], it['face'], it['axis']
        depth = it.get('depth', 540)
        w = it.get('width', 360)
        if wall == 'W':
            return (face, axis - w / 2, face + depth, axis + w / 2)
        if wall == 'E':
            return (face - depth, axis - w / 2, face, axis + w / 2)
        if wall == 'S':
            return (axis - w / 2, face, axis + w / 2, face + depth)
        if wall == 'N':
            return (axis - w / 2, face - depth, axis + w / 2, face)
    if 'c' in it and k == 'round':
        c, r = it['c'], it['r']
        return (c[0] - r, c[1] - r, c[0] + r, c[1] + r)
    if 'c' in it and k == 'chair':
        c = it['c']
        return (c[0] - 230, c[1] - 230, c[0] + 230, c[1] + 230)
    return None


# ---------------- тёплые полы ----------------
def heat_mask(room, cell=25, wall_off=50, item_off=50, drain_off=100, min_w=300):
    """Маска зоны укладки мата: dict(x0, y0, cell, nx, ny, cells=set((i, j))).
    Свободный пол помещения минус предметы (+item_off), трап (+drain_off), отступ от стен wall_off;
    полосы уже min_w исключаются. Доп. исключения — HEAT[i]['excl'] = [(x0, y0, x1, y1), ...]."""
    poly = ROOMS[room]['poly']
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    nx, ny = int((x1 - x0) // cell), int((y1 - y0) // cell)

    def inside(px, py):
        c = False
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            if (ya > py) != (yb > py):
                xi = xa + (py - ya) * (xb - xa) / (yb - ya)
                if xi > px:
                    c = not c
        return c

    def dist_edge(px, py):
        d = 1e9
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            ex, ey = xb - xa, yb - ya
            L2 = ex * ex + ey * ey
            t = max(0.0, min(1.0, ((px - xa) * ex + (py - ya) * ey) / L2))
            qx, qy = xa + t * ex, ya + t * ey
            d = min(d, ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5)
        return d
    rects = []
    polys = []                         # предметы-многоугольники ('pts'): исключаются по контуру + item_off
    for it in ITEMS:
        if it['room'] != room or it['kind'] in HEAT_SKIP:
            continue
        if 'pts' in it and 'rect' not in it:
            polys.append(list(it['pts']))
            continue
        r = item_rect(it)
        if r is None and 'c' in it:
            rr = it.get('r', 260)
            r = (it['c'][0] - rr, it['c'][1] - rr, it['c'][0] + rr, it['c'][1] + rr)
        if r is None:
            continue
        off = drain_off if it['kind'] == 'drain' else item_off
        rects.append((r[0] - off, r[1] - off, r[2] + off, r[3] + off))
    for h in HEAT:
        if h['room'] == room:
            rects += list(h.get('excl', []))
    import numpy as np
    from scipy import ndimage
    g = np.zeros((nx, ny), bool)
    for i in range(nx):
        for j in range(ny):
            cx, cy = x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell
            if not inside(cx, cy) or dist_edge(cx, cy) < wall_off + cell / 2:
                continue
            if any(a <= cx <= c and b <= cy <= d for a, b, c, d in rects):
                continue
            if polys and any(_in_poly(pp, cx, cy) or _dist_poly(pp, cx, cy) < item_off for pp in polys):
                continue
            g[i, j] = True
    n = max(1, int(round(min_w / cell)))
    g = ndimage.binary_opening(g, structure=np.ones((n, n), bool))
    cells = set(zip(*np.nonzero(g)))
    cells = {(int(i), int(j)) for i, j in cells}
    return dict(x0=x0, y0=y0, cell=cell, nx=nx, ny=ny, cells=cells)


def _in_poly(poly, px, py):
    c = False
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if (ya > py) != (yb > py):
            xi = xa + (py - ya) * (xb - xa) / (yb - ya)
            if xi > px:
                c = not c
    return c


def _dist_poly(poly, px, py):
    d = 1e9
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        ex, ey = xb - xa, yb - ya
        L2 = ex * ex + ey * ey or 1
        t = max(0.0, min(1.0, ((px - xa) * ex + (py - ya) * ey) / L2))
        d = min(d, ((px - xa - t * ex) ** 2 + (py - ya - t * ey) ** 2) ** 0.5)
    return d


def heat_area(room):
    m = heat_mask(room)
    return len(m['cells']) * m['cell'] ** 2 / 1e6


def heat_mat(room):
    """Площадь мата (кратно 0,5 м², не более зоны)."""
    a = heat_area(room)
    return max(0.5, int(a * 2) / 2.0)


# ---------------- встроенная мебель до потолка ----------------
def builtin_to_ceiling(room):
    """Габариты встроенной мебели помещения, доходящей до потолка (потолок к ней примыкает)."""
    zc = ROOM[room]['ceil']
    out = []
    for it in ITEMS:
        if it['room'] != room or it['kind'] not in BUILTIN_KINDS or zc is None:
            continue
        z = it.get('z', (0, 0))
        if isinstance(z, tuple) and z[1] >= zc - 5:
            out.append((it, item_rect(it)))
    return out


def ceil_area(room):
    """Площадь потолка (м²): помещение за вычетом встроенной мебели до потолка."""
    a = AREA[room]
    for it, r in builtin_to_ceiling(room):
        a -= (r[2] - r[0]) * (r[3] - r[1]) / 1e6
    return a


# ---------------- состав помещений ----------------
def rooms_all():
    """Все помещения в порядке номеров."""
    return sorted(ROOM.keys())


def rooms_counted():
    """Помещения, входящие в площадь квартиры (без балконов/лоджий: zone='out' или count=False)."""
    return [k for k in rooms_all() if ROOM[k].get('count', ROOM[k].get('zone') != 'out')]


def rooms_outdoor():
    return [k for k in rooms_all() if k not in rooms_counted()]


def total_area():
    return sum(AREA[k] for k in rooms_counted())


# ---------------- материалы (коды отделки) ----------------
_TEX_WORDS = [('ёлочк', 'herringbone'), ('доска', 'planks'), ('ламинат', 'planks'), ('рейк', 'slats'), ('панел', 'panels'),
              ('мрамор', 'marble'), ('слэб', 'marble'), ('керамогранит', 'tiles'), ('плитка', 'tiles'), ('окраск', 'paint'),
              ('краск', 'paint'), ('гкл', 'paint'), ('плинтус', 'plinth')]


def mat(code):
    """Описание материала по коду отделки: design.MATERIALS[code] или вывод по тексту FINISH (тип текстуры tex)."""
    M = getattr(_obj, 'MATERIALS', {})
    if code in M:
        return M[code]
    txt = FINISH.get(code, '').lower()
    for w, t in _TEX_WORDS:
        if w in txt:
            return {'tex': t}
    return {}


# ---------------- стены помещений для развёрток ----------------
WALL_LABELS = 'АБВГДЕЖИКЛМНПРСТ'


def auto_rwalls(room):
    """Стены помещения по часовой (вид изнутри: слева направо), начиная со стены с дверью входа: [(буква, pL, pR)]."""
    poly = list(ROOMS[room]['poly'])
    a = 0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        a += x0 * y1 - x1 * y0
    if a > 0:                       # против часовой -> по часовой (нормаль n = (dy, -dx) смотрит внутрь)
        poly = poly[::-1]
    edges = list(zip(poly, poly[1:] + poly[:1]))
    start = 0
    best = None
    for key in getattr(_obj, 'DOOR_LIST', []):
        hx, hy = DOORS[key]['h']
        for i, ((xa, ya), (xb, yb)) in enumerate(edges):
            if ya == yb and min(xa, xb) - 1 <= hx <= max(xa, xb) + 1:
                d = abs(hy - ya)
            elif xa == xb and min(ya, yb) - 1 <= hy <= max(ya, yb) + 1:
                d = abs(hx - xa)
            else:
                continue
            if d <= 450 and (best is None or d < best[0]):
                best = (d, i)
        if best is not None:
            break
    if best:
        start = best[1]
    edges = edges[start:] + edges[:start]
    return [(WALL_LABELS[i], e[0], e[1]) for i, e in enumerate(edges)]


RWALLS = dict(getattr(_obj, 'RWALLS', {}) or {})
for _k in ROOM:
    if _k not in RWALLS and ROOM[_k].get('zone') != 'out':
        RWALLS[_k] = auto_rwalls(_k)


# ---------------- буквы углов (стандарт бюро: буквами обозначаются углы, стена — «А–Б») ----------------
CORNER_LETTERS = getattr(_obj, 'CORNER_LETTERS', True)


def _same_pt(p, q, tol=6):
    return abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol


CORNER_MERGE = 300       # разрыв между стенами короче (пилястра, скос угла) — один угол


def _corner_pts(room):
    """Угловые точки по ходу стен: [[точки угла]] — короткий разрыв (< CORNER_MERGE) объединяется в один угол."""
    ws = RWALLS[room]
    groups = []
    for i, (lab, pL, pR) in enumerate(ws):
        if groups and (_same_pt(groups[-1][-1], pL, CORNER_MERGE)):
            groups[-1].append(pL)
        else:
            groups.append([pL])
        if i == len(ws) - 1 and _same_pt(pR, ws[0][1], CORNER_MERGE):
            groups[0].insert(0, pR)
            continue
        groups.append([pR])
    return groups


def corners(room):
    """Углы помещения по ходу стен (по часовой от входа): [(буква, точка)]. Открытый проём в цепочке стен даёт
    два угла (по краям проёма); короткий разрыв (пилястра, скос) — один угол."""
    out = []
    for i, g in enumerate(_corner_pts(room)):
        x = sum(p[0] for p in g) / len(g)
        y = sum(p[1] for p in g) / len(g)
        out.append((WALL_LABELS[i], (x, y)))
    return out


def wall_span(room, lab):
    """Обозначение стены (развёртки) по угловым буквам: «А–Б»; без стандарта углов — сама буква стены."""
    if not CORNER_LETTERS or room not in RWALLS:
        return lab
    gs = _corner_pts(room)

    def letter(p):
        for i, g in enumerate(gs):
            if any(_same_pt(p, q) for q in g):
                return WALL_LABELS[i]
        return '?'
    for l_, pL, pR in RWALLS[room]:
        if l_ == lab:
            return f'{letter(pL)}–{letter(pR)}'
    return lab


def wall_spans(room, labs):
    return ', '.join(wall_span(room, l_) for l_ in labs)
