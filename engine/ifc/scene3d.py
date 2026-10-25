# -*- coding: utf-8 -*-
"""Сцена квартиры для IFC/OBJ: строится из единой модели проекта (design.py) — те же размеры, что на листах."""
import math
import os
import sys

import numpy as np

import model as D            # noqa: E402
import elev as EL             # noqa: E402
import textures as T          # noqa: E402
import drawplan as DP         # noqa: E402
from ifc import m3d as M      # noqa: E402
from ifc.m3d import Elem, box, prism, cyl, vquad, rect_cells, box_minus, ellipse  # noqa: E402
from ifc.m3d import tube, sphere, seg_prism, poly_cells, fabric_mat  # noqa: E402
from ifc import hp as HP  # noqa: E402
from ifc import detail as DT  # noqa: E402


def polytube(el, m, pts, r, n=12):
    """Трубопровод по ломаной со скруглёнными отводами (радиус гиба 3r)."""
    HP.pipe(el, m, pts, r, bend=max(3 * r, 25), n=max(16, n))

RF = -D.FLOOR_BUILDUP          # черновой пол
RC = D.ROUGH_CEIL              # черновой потолок
SLAB = 220
BALC_TOP = getattr(D, 'BALC_TOP', 2800)          # низ плиты балкона/лоджии (сущ.)
DOOR_TOP = getattr(D, 'DOOR_H', 2100) + 40       # верх проёма межкомнатных дверей (полотно + 40)
_TEX_T = {'paint': 3, 'panels': 16, 'slats': 26, 'tiles': 10, 'marble': 8}


def mkey(code):
    """Ключ 3D-материала кода отделки (латиница): С1 -> C1, П2 -> P2, Пт1 -> PT1."""
    return code.replace('Пт', 'PT').replace('П', 'P').replace('С', 'C')


def tex_of(code):
    return D.mat(code.split(' ')[0]).get('tex', 'paint')


def fin_t(code):
    return _TEX_T.get(tex_of(code), 5)


def indoor(room):
    return D.ROOM[room].get('zone') != 'out'


def _adjacent(r, poly, tol=6):
    """Прямоугольник r примыкает стороной к контуру poly."""
    x0, y0, x1, y1 = r
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if ya == yb and min(xa, xb) < x1 - 10 and max(xa, xb) > x0 + 10 and (abs(ya - y0) < tol or abs(ya - y1) < tol):
            return True
        if xa == xb and min(ya, yb) < y1 - 10 and max(ya, yb) > y0 + 10 and (abs(xa - x0) < tol or abs(xa - x1) < tol):
            return True
    return False


def outdoor_wall(r):
    """Стена балкона/лоджии: примыкает к наружному помещению и не примыкает к внутренним."""
    out_ = any(_adjacent(r, D.ROOMS[k]['poly']) for k in D.ROOMS if not indoor(k))
    in_ = any(_adjacent(r, D.ROOMS[k]['poly']) for k in D.ROOMS if indoor(k))
    return out_ and not in_


def parapets():
    """Ограждения балконов: design.PARAPETS или свободные (без стен) стороны наружных помещений, толщина 100."""
    if hasattr(D, 'PARAPETS'):
        return D.PARAPETS
    out = []
    for k in D.ROOMS:
        if indoor(k):
            continue
        poly = D.ROOMS[k]['poly']
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            if ya == yb:
                lo, hi = min(xa, xb), max(xa, xb)
                cuts = [(w[0], w[2]) for w in D.WALLS if (abs(w[1] - ya) < 6 or abs(w[3] - ya) < 6) and w[0] < hi and w[2] > lo]
                cx, cy = sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)
                sg = 1 if ya > cy else -1
                from kit import subtract_intervals
                if any(EL_inside(D.ROOMS[q]['poly'], ((lo + hi) / 2, ya + sg * 550)) for q in D.ROOMS if indoor(q)):
                    continue                      # за этой стороной — внутреннее помещение (балконный блок)
                for a, b in subtract_intervals((lo, hi), cuts):
                    if b - a > 300:
                        out.append((a, min(ya, ya + sg * 100), b, max(ya, ya + sg * 100)))
            elif xa == xb:
                lo, hi = min(ya, yb), max(ya, yb)
                cuts = [(w[1], w[3]) for w in D.WALLS if (abs(w[0] - xa) < 6 or abs(w[2] - xa) < 6) and w[1] < hi and w[3] > lo]
                cx = sum(p[0] for p in poly) / len(poly)
                sg = 1 if xa > cx else -1
                from kit import subtract_intervals
                if any(EL_inside(D.ROOMS[q]['poly'], (xa + sg * 550, (lo + hi) / 2)) for q in D.ROOMS if indoor(q)):
                    continue
                for a, b in subtract_intervals((lo, hi), cuts):
                    if b - a > 300:
                        out.append((min(xa, xa + sg * 100), a, max(xa, xa + sg * 100), b))
    return out


def zf_of(room):
    return D.ROOM[room]['level'] or 0


def zc_of(room):
    return D.ROOM[room]['ceil'] or BALC_TOP


# ------------------------------------------------------------ проёмы (конструктивные)
def _open3d():
    """Конструктивные проёмы (ключ, ось стены, c0, c1, a, b, z0, z1): design.OPEN3D или из проёмов развёрток."""
    if hasattr(D, 'OPEN3D'):
        return D.OPEN3D
    out = []
    for o in EL.OPENINGS:
        if o['kind'] == 'door':
            z0, z1 = RF, (o['z1'] + 40)
        else:
            z0, z1 = o['z0'], o['z1']
        out.append((o['key'], o['axis'], o['c0'], o['c1'], o['a'], o['b'], z0, z1))
    return out


OPEN3D = _open3d()
OKIND = {o['key']: o['kind'] for o in EL.OPENINGS}


def opening_box(o):
    k, ax, c0, c1, a, b, z0, z1 = o
    return (c0, a, z0, c1, b, z1) if ax == 'x' else (a, c0, z0, b, c1, z1)


def openings_on_wall(W, room):
    """Проёмы на стене помещения (s0, s1, z0, z1)."""
    res = []
    pL = W['pL']
    for o in OPEN3D:
        k, ax, c0, c1, a, b, z0, z1 = o
        if ax == 'x' and abs(W['d'][0]) < 1e-6 and c0 - 1 <= pL[0] <= c1 + 1:
            sa, _ = EL.proj(W, (pL[0], a)); sb, _ = EL.proj(W, (pL[0], b))
        elif ax == 'y' and abs(W['d'][1]) < 1e-6 and c0 - 1 <= pL[1] <= c1 + 1:
            sa, _ = EL.proj(W, (a, pL[1])); sb, _ = EL.proj(W, (b, pL[1]))
        else:
            continue
        s0, s1 = min(sa, sb), max(sa, sb)
        if s1 > 0 and s0 < W['L']:
            res.append((k, s0, s1, z0, z1))
    return res


def wpt(W, s, d):
    return (W['pL'][0] + W['d'][0] * s + W['n'][0] * d, W['pL'][1] + W['d'][1] * s + W['n'][1] * d)


def wbox(el, m, W, s0, s1, d0, d1, z0, z1, fm=None, uvf=None):
    if abs(W['d'][0]) > 1e-6 and abs(W['d'][1]) > 1e-6:          # косая стена (эркер) — призма по 4 углам
        prism(el, m, [wpt(W, s0, d0), wpt(W, s1, d0), wpt(W, s1, d1), wpt(W, s0, d1)], z0, z1, uvf=uvf)
        return
    a = wpt(W, s0, d0); b = wpt(W, s1, d1)
    box(el, m, a[0], a[1], z0, b[0], b[1], z1, fm=fm, uvf=uvf)


def fmat(code, default='FRONT'):
    """Материал фасада/корпуса по коду отделки объекта ('С2') или словом ('oak', 'walnut')."""
    if not code:
        return default
    w = {'oak': 'OAK', 'walnut': 'WALNUT', 'front': 'FRONT', 'white': 'WHITE'}.get(str(code).lower())
    if w:
        return w
    k = mkey(str(code))
    return k if k in M.MATS else default


def face_key(n):
    """Ключ грани параллелепипеда по нормали в плане."""
    if abs(n[0]) > 0.5:
        return '+x' if n[0] > 0 else '-x'
    return '+y' if n[1] > 0 else '-y'


# ------------------------------------------------------------ фактуры, привязанные к раскладке
def floor_texture(room):
    """Уникальная фактура пола помещения: u — вдоль y, v — вдоль x (габарит помещения)."""
    poly = D.ROOMS[room]['poly']
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = y1 - y0, x1 - x0
    code = D.ROOM[room]['floor']
    tex = tex_of(code)
    mpp = 1.4 if tex in ('herringbone', 'planks') else 1.3
    if tex == 'herringbone':
        arr = T.herringbone_tex(W, H, mpp, 11, axis='x')
    elif tex == 'planks':
        arr = T.planks_tex(W, H, mpp, 12 + int(room))
    else:
        if tex == 'concrete':
            arr = T.concrete_tex(W, H, mpp, 13 + int(room))
        elif D.mat(code).get('style') == 'marble':
            arr = marble_floor(room, code, W, H, mpp, x1, y0)
        else:
            arr = T.paint(W, H, mpp, T._col(code), 14, gradient=False)
        hpx, wpx = arr.shape[:2]
        # плитка: тон каждой плитки + швы по раскладке (FLOOR_TILES)
        yy = y0 + (np.arange(wpx) + 0.5) * mpp           # по горизонтали изображения — y
        xx = x1 - (np.arange(hpx) + 0.5) * mpp           # строки сверху вниз: верх — x1 (v=1)
        for r_, ppoly, a, b, ox, oy in D.FLOOR_TILES:
            if r_ != room:
                continue
            pxs = [p[0] for p in ppoly]; pys = [p[1] for p in ppoly]
            mx = (xx >= min(pxs)) & (xx <= max(pxs))
            my = (yy >= min(pys)) & (yy <= max(pys))
            ki = np.floor((yy - oy) / b).astype(int)
            kj = np.floor((xx - ox) / a).astype(int)
            tid = (ki[None, :] * 7919 + kj[:, None] * 104729) % 100003
            hs = np.sin(tid * 12.9898 + 78.233) * 43758.5453
            tv = ((hs - np.floor(hs)) - 0.5) * 7.0
            fy = np.abs(((yy - oy) / b + 0.5) % 1.0 - 0.5) * b
            fx = np.abs(((xx - ox) / a + 0.5) % 1.0 - 0.5) * a
            grout = np.exp(-(np.minimum(fx[:, None], fy[None, :]) / 1.6) ** 2) * 55
            msk = (mx[:, None] & my[None, :])
            arr = np.where(msk[..., None], arr + (tv - grout)[..., None], arr)
    f = f'floor_{room}.jpg'
    return M.unique_texture('FL' + room, D.ROOM[room]['floor'] + ' пол пом. ' + room, f, arr,
                            D.ROOM[room]['floor'] + ' ' + D.FINISH[D.ROOM[room]['floor']].split(';')[0][:60])


def marble_floor(room, code, W, H, mpp, x1, y0, slab=3600.0):
    """Керамогранит под мрамор на полу: у каждой плитки свой участок «слэба» (прожилки не идут сквозь швы, как в
    реальной укладке), часть плиток повёрнута на 180°; прожилки серые (тип Statuario)."""
    T.COL['marble'] = T._col(code, (238, 236, 233))
    lay = [t for t in D.FLOOR_TILES if t[0] == room]
    if not lay:
        return T.marble(W, H, mpp, 17 + int(room), vein_col=(170, 170, 174))
    src = T.marble(slab, slab, mpp, 17 + int(room), vein_col=(170, 170, 174))
    sh_, sw_ = src.shape[:2]
    w, h = T._grid_px(W, H, mpp)
    yy = y0 + (np.arange(w) + 0.5) * mpp                 # столбцы — y
    xx = x1 - (np.arange(h) + 0.5) * mpp                 # строки сверху вниз — x (верх — x1)
    _, _, a, b, ox, oy = lay[0]
    kj = np.floor((xx - ox) / a).astype(np.int64)
    ki = np.floor((yy - oy) / b).astype(np.int64)
    lx = ((xx - ox) - kj * a).astype(np.float32)
    ly = ((yy - oy) - ki * b).astype(np.float32)
    tid = ((ki[None, :] * 7919 + kj[:, None] * 104729) % 100003).astype(np.float64)

    def rnd(k1, k2, k3):
        v = np.sin(tid * k1 + k2) * k3
        return (v - np.floor(v)).astype(np.float32)
    r1, r2, r3 = rnd(1.731, 0.37, 43758.5453), rnd(3.117, 1.91, 24634.6345), rnd(5.33, 2.7, 9631.7)
    flip = r3 > 0.5
    LX = np.where(flip, a - lx[:, None], lx[:, None])
    LY = np.where(flip, b - ly[None, :], ly[None, :])
    sr = np.clip(((LX + r1 * (slab - a)) / mpp).astype(np.int32), 0, sh_ - 1)
    sc = np.clip(((LY + r2 * (slab - b)) / mpp).astype(np.int32), 0, sw_ - 1)
    return src[sr, sc]


def ceiling_steps(S):
    """Перепад потолков в открытом проёме между помещениями (общая граница без стены, напр. прихожая +2,600 /
    кухня-гостиная +2,700): вертикальная кромка ГКЛ от нижнего потолка до верхнего — без «щели» в межпотолочное
    пространство."""
    rooms_c = [k for k in D.rooms_all() if D.ROOM[k]['ceil'] and indoor(k)]
    for i, A in enumerate(rooms_c):
        for B in rooms_c[i + 1:]:
            za, zb = zc_of(A), zc_of(B)
            if abs(za - zb) < 5:
                continue
            low, z_lo, z_hi = (A, za, zb) if za < zb else (B, zb, za)
            for ax, c, s0, s1 in _shared_edges(D.ROOMS[A]['poly'], D.ROOMS[B]['poly']):
                el = S.add(Elem('IfcCovering', f'Кромка перепада потолков {A}/{B}', room=low, predefined='CEILING',
                                props={'Помещения': f'{A} / {B}', 'Перепад': f'{z_lo:.0f} / {z_hi:.0f}',
                                       'Конструкция': 'ГКЛ 12,5 по профилю, окраска в цвет потолка'}))
                m_ = (s0 + s1) / 2
                if ax == 'x':
                    sg = 1 if EL_inside(D.ROOMS[low]['poly'], (c + 30, m_)) else -1
                    box(el, 'CEIL', min(c, c + sg * 12.5), s0, z_lo + 12.5, max(c, c + sg * 12.5), s1, z_hi + 12.5)
                else:
                    sg = 1 if EL_inside(D.ROOMS[low]['poly'], (m_, c + 30)) else -1
                    box(el, 'CEIL', s0, min(c, c + sg * 12.5), z_lo + 12.5, s1, max(c, c + sg * 12.5), z_hi + 12.5)


def _shared_edges(pa, pb, tol=1.0, min_len=50):
    """Общие участки осевых рёбер двух контуров: ('x', x, y0, y1) — линия x = const; ('y', y, x0, x1)."""
    out = []
    for p, q in zip(pa, pa[1:] + pa[:1]):
        for r, t in zip(pb, pb[1:] + pb[:1]):
            if abs(p[0] - q[0]) < tol and abs(r[0] - t[0]) < tol and abs(p[0] - r[0]) < tol:
                lo, hi = max(min(p[1], q[1]), min(r[1], t[1])), min(max(p[1], q[1]), max(r[1], t[1]))
                if hi - lo > min_len:
                    out.append(('x', p[0], lo, hi))
            elif abs(p[1] - q[1]) < tol and abs(r[1] - t[1]) < tol and abs(p[1] - r[1]) < tol:
                lo, hi = max(min(p[0], q[0]), min(r[0], t[0])), min(max(p[0], q[0]), max(r[0], t[0]))
                if hi - lo > min_len:
                    out.append(('y', p[1], lo, hi))
    return out


def zone_texture(room, lab, s0, s1, z0, z1, code):
    """Уникальная фактура зоны стены (мрамор) — UV 0..1 по зоне."""
    W, H = s1 - s0, z1 - z0
    T.COL['marble'] = T._col(code, (241, 237, 231))
    arr = T.marble(W, H, 1.2, int(s0) % 13)
    key = f'Z{room}{lab}{int(s0)}'
    return M.unique_texture(key, f'{code} пом. {room} стена {lab}', f'zone_{room}_{ord(lab)}_{int(s0)}.jpg', arr,
                            f'{code} ' + D.FINISH.get(code, '').split(',')[0][:50])


# ------------------------------------------------------------ сборка
class Scene:
    def __init__(s):
        s.elems = []

    def add(s, el):
        s.elems.append(el)
        return el


def build(texdir):
    T.HQ = True
    M.TEXDIR = texdir
    os.makedirs(texdir, exist_ok=True)
    M.build_library(D)
    S = Scene()
    walls(S)
    slabs(S)
    floors(S)
    ceilings(S)
    wall_finishes(S)
    reveals(S)
    doors(S)
    windows(S)
    furniture(S)
    lights(S)
    electrics(S)
    # детализация
    trims(S)
    engineering(S)
    heating(S)
    spaces(S)
    return S


# ------------------------------------------------------------ стены
BEAR = getattr(D, 'BEARING_MIN', None)


def _facade(r):
    """Стена по линии окон (наружная)."""
    x0, y0, x1, y1 = r
    for w in getattr(D, 'WINDOWS', {}).values():
        ax, c = w['wall']
        if ax == 'x' and (x1 - x0) < (y1 - y0) and (abs(x1 - c) < 6 or abs(x0 - c) < 6):
            return True
        if ax == 'y' and (y1 - y0) < (x1 - x0) and (abs(y1 - c) < 6 or abs(y0 - c) < 6):
            return True
    return False


def walls(S):
    for i, r in enumerate(D.WALLS):
        x0, y0, x1, y1 = r
        out_ = outdoor_wall(r)
        top = BALC_TOP if out_ else RC
        t = min(x1 - x0, y1 - y0)
        bearing = BEAR is not None and t > BEAR
        ext = _facade(r)
        nm = f'Стена {t:.0f} мм' + (' — монолит ж/б, несущая' if bearing else ' — перегородка (сущ.)') + (' (балкон)' if out_ else '')
        el = S.add(Elem('IfcWall', nm, predefined='SOLIDWALL' if t >= 200 else 'PARTITIONING',
                        props={'Толщина, мм': t, 'Статус': 'существующая',
                               'Несущая': 'да — монолит, штробить запрещено' if bearing else 'нет'}))
        if BEAR is not None:
            el.psets = {'Pset_WallCommon': {'LoadBearing': bool(bearing), 'IsExternal': bool(ext)}}
        m = 'CONCRETE' if bearing else 'PLASTER'
        el.extr.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], RF, top, m))
        box(el, m, x0, y0, RF, x1, y1, top)
    for poly in getattr(D, 'WALL_POLYS', None) or []:
        bearing = bool(getattr(D, 'BEARING_POLYS', False))
        el = S.add(Elem('IfcWall', 'Стена эркера' + (' — монолит ж/б, несущая' if bearing else ''), predefined='SOLIDWALL',
                        props={'Статус': 'существующая', 'Несущая': 'да — монолит, штробить запрещено' if bearing else 'нет'}))
        el.psets = {'Pset_WallCommon': {'LoadBearing': bearing, 'IsExternal': True}}
        m = 'CONCRETE' if bearing else 'PLASTER'
        el.extr.append((list(poly), RF, RC, m))
        prism(el, m, list(poly), RF, RC)
    # перемычки и подоконные участки в проёмах
    for o in OPEN3D:
        k, ax, c0, c1, a, b, z0, z1 = o
        pieces = []
        if z0 > RF:
            pieces.append((RF, z0, 'Подоконный участок' if OKIND.get(k) == 'window' else 'Порог/подоконный участок'))
        pieces.append((z1, RC, 'Перемычка над проёмом'))
        for za, zb, nm in pieces:
            el = S.add(Elem('IfcWall', nm, predefined='SOLIDWALL' if c1 - c0 >= 200 else 'PARTITIONING',
                            props={'Проём': k}))
            pl = [(c0, a), (c1, a), (c1, b), (c0, b)] if ax == 'x' else [(a, c0), (b, c0), (b, c1), (a, c1)]
            el.extr.append((pl, za, zb, 'PLASTER'))
            bx = opening_box((k, ax, c0, c1, a, b, za, zb))
            box(el, 'PLASTER', *bx)
    # ограждения балконов (парапеты) под остеклением
    for (x0, y0, x1, y1) in parapets():
        el = S.add(Elem('IfcWall', 'Ограждение балкона (парапет)', predefined='PARAPET', props={'Статус': 'существующее'}))
        el.extr.append(([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], RF, 900, 'PLASTER'))
        box(el, 'PLASTER', x0, y0, RF, x1, y1, 900)


def slabs(S):
    inner_polys = [D.ROOMS[k]['poly'] for k in D.ROOMS if indoor(k)]
    wall_polys = [[(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])] for r in D.WALLS]
    polys = [D.ROOMS[k]['poly'] for k in D.ROOMS] + wall_polys + [list(p) for p in (getattr(D, 'WALL_POLYS', None) or [])]
    el = S.add(Elem('IfcSlab', 'Плита перекрытия (под квартирой)', predefined='FLOOR', props={'Статус': 'существующая'}))
    for p in polys:
        el.extr.append((p, RF - SLAB, RF, 'CONCRETE'))
        prism(el, 'CONCRETE', p, RF - SLAB, RF)
    el = S.add(Elem('IfcSlab', 'Плита перекрытия (над квартирой)', predefined='FLOOR', props={'Статус': 'существующая', 'Скрыть для вида сверху': 'да'}))
    el.hide_top = True
    for p, r in ([(q, None) for q in inner_polys] + [(q, r) for q, r in zip(wall_polys, D.WALLS)] +
                 [(list(q), None) for q in (getattr(D, 'WALL_POLYS', None) or [])]):
        if r is not None and outdoor_wall(r):
            continue
        el.extr.append((p, RC, RC + SLAB, 'CONCRETE'))
        prism(el, 'CONCRETE', p, RC, RC + SLAB)
    for k in D.ROOMS:
        if indoor(k):
            continue
        pts = list(D.ROOMS[k]['poly']) + [q for r in D.WALLS if outdoor_wall(r) and _adjacent(r, D.ROOMS[k]['poly'])
                                          for q in ((r[0], r[1]), (r[2], r[3]))]
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        el2 = S.add(Elem('IfcSlab', 'Плита балкона (верх)', predefined='FLOOR', props={'Статус': 'существующая'}))
        el2.hide_top = True
        bp = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
        el2.extr.append((bp, BALC_TOP, BALC_TOP + 150, 'CONCRETE'))
        prism(el2, 'CONCRETE', bp, BALC_TOP, BALC_TOP + 150)


# ------------------------------------------------------------ полы


def floors(S):
    for room, info in D.ROOM.items():
        poly = D.ROOMS[room]['poly']
        zf = zf_of(room)
        code = info['floor']
        t = 15 if tex_of(code) in ('herringbone', 'planks') else 10
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        sc = S.add(Elem('IfcCovering', f'Основание пола пом. {room}', room=room, predefined='USERDEFINED',
                        objtype='Стяжка / основание пола', props={'Помещение': room, 'Толщина, мм': zf - t - RF}))
        prism(sc, 'SCREED', poly, RF, zf - t)
        fm = floor_texture(room)
        el = S.add(Elem('IfcCovering', f'{code} — пол пом. {room}', room=room, predefined='FLOORING',
                        props={'Помещение': room, 'Код отделки': code, 'Описание': D.FINISH[code],
                               'Площадь, м²': round(D.AREA[room], 2), 'Отметка чистого пола': zf}))

        def uvf(m, n, p, x0=x0, x1=x1, y0=y0, y1=y1):
            return ((p[1] - y0) / (y1 - y0), (p[0] - x0) / (x1 - x0))
        prism(el, fm.key, poly, zf - t, zf, uvf=uvf)
        if info['level'] is None:
            el.props['Отметка чистого пола'] = 'уточнить по месту (в модели условно ±0,000)'


# ------------------------------------------------------------ потолки
def ceilings(S):
    import plans as PL
    for room in [k for k in D.rooms_all() if D.ROOM[k]['ceil']]:
        poly = D.ROOMS[room]['poly']
        zc = zc_of(room)
        holes = [r for it, r in D.builtin_to_ceiling(room)]
        feats = [f for f in D.CEIL_FEATURES if f['room'] == room and f['kind'] in ('niche', 'cove')]
        holes += [f['rect'] for f in feats]
        el = S.add(Elem('IfcCovering', f'Потолок пом. {room}', room=room, predefined='CEILING',
                        props={'Помещение': room, 'Код отделки': PL.ceil_code(room),
                               'Отметка': zc, 'Площадь, м²': round(D.ceil_area(room), 2),
                               'Примечание': 'ГКЛ примыкает к встроенной мебели до потолка и крепится к ней'}))
        rects, parts = poly_cells(poly, holes)
        for (a, b, c, d) in rects:
            box(el, 'CEIL', a, b, zc, c, d, zc + 12.5, fm={'+z': None})
        for pp in parts:
            prism(el, 'CEIL', pp, zc, zc + 12.5, top=False)
        for f in feats:
            x0, y0, x1, y1 = f['rect']
            # дно ниши (выше на 150) и кромка ниши со стороны комнаты
            box(el, 'CEIL', x0, y0, zc + 150, x1, y1, zc + 162.5, fm={'+z': None})
            # кромка — по длинной стороне, не совпадающей со стеной; у световых ниш — и торцы
            xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
            if (x1 - x0) > (y1 - y0):
                if abs(y1 - max(ys)) < 5:
                    box(el, 'CEIL', x0, y0 - 12.5, zc, x1, y0, zc + 150)
                else:
                    box(el, 'CEIL', x0, y1, zc, x1, y1 + 12.5, zc + 150)
            else:
                if abs(x0 - min(xs)) < 5:
                    box(el, 'CEIL', x1, y0, zc, x1 + 12.5, y1, zc + 150)
                else:
                    box(el, 'CEIL', x0 - 12.5, y0, zc, x0, y1, zc + 150)
                box(el, 'CEIL', x0, y0 - 12.5, zc, x1, y0, zc + 150)
                box(el, 'CEIL', x0, y1, zc, x1, y1 + 12.5, zc + 150)
    ceiling_steps(S)
    # балконы/лоджии — окраска плиты
    for room in [k for k in D.rooms_all() if not D.ROOM[k]['ceil']]:
        poly = D.ROOMS[room]['poly']
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        el = S.add(Elem('IfcCovering', f'Потолок пом. {room} (окраска)', room=room, predefined='CEILING',
                        props={'Помещение': room, 'Код отделки': PL.ceil_code(room)}))
        box(el, 'CEIL', min(xs), min(ys), BALC_TOP - 3, max(xs), max(ys), BALC_TOP, fm={'+z': None})


# ------------------------------------------------------------ отделка стен
def _box_in_front(room, W, s0, s1, z=None):
    """Короб инсталляции перед участком стены: (s_a, s_b, глубина[, верх короба]); z — только если отметка ниже верха короба."""
    for it in D.ITEMS:
        if it['room'] != room or it['kind'] != 'box':
            continue
        a, b, d0, d1 = EL.proj_rect(W, it['rect'])
        zt = it.get('z', (0, 9999))[1]
        if z is not None and z >= zt:
            continue
        if d0 <= 5 and a < s1 and b > s0:
            return max(a, s0), min(b, s1), d1
    return None


def _box_top(room, W, s0, s1):
    for it in D.ITEMS:
        if it['room'] != room or it['kind'] != 'box':
            continue
        a, b, d0, d1 = EL.proj_rect(W, it['rect'])
        if d0 <= 5 and a < s1 and b > s0:
            return it.get('z', (0, 9999))[1]
    return None


def _slats(el, W, s0, s1, z0, z1, d0, phase=0.0):
    """Рейки 20×40 шаг 60 на чёрной подложке (С3)."""
    wbox(el, 'BLACK', W, s0, s1, d0, d0 + 6, z0, z1)
    k0 = math.ceil((s0 - phase - 40) / 60.0)
    s = phase + k0 * 60
    while s < s1:
        a, b = max(s, s0), min(s + 40, s1)
        if b - a > 2:
            wbox(el, 'WALNUT', W, a, b, d0 + 6, d0 + 26, z0, z1)
        s += 60


def wall_finishes(S):
    for room, wls in D.RWALLS.items():
        zf, zc = zf_of(room), zc_of(room)
        for lab, pL, pR in wls:
            W = EL.wall_geom(room, lab)
            L = W['L']
            ops = openings_on_wall(W, room)
            zones = [(s0, s1, max(z0, zf), min(z1, zc), code) for (r, l2, s0, s1, z0, z1, code) in D.WALL_ZONES
                     if r == room and l2 == lab]
            dflt = D.WALL_DEFAULT.get(room)
            items = []
            for (s0, s1, z0, z1, code) in zones:
                if code != 'X':
                    items.append((s0, s1, z0, z1, code))
            # окраска по остатку стены
            if dflt:
                holes = [(s0, z0, s1, z1) for (s0, s1, z0, z1, code) in zones]
                poly = [(0, zf), (L, zf), (L, zc), (0, zc)]
                for (a, b, c, d) in rect_cells(poly, holes):
                    items.append((a, c, b, d, dflt))
            for (s0, s1, z0, z1, code) in items:
                c = mkey(code)
                tex = tex_of(code)
                t = fin_t(code)
                hole2 = [(o[1], o[3], o[2], o[4]) for o in ops]
                poly = [(s0, z0), (s1, z0), (s1, z1), (s0, z1)]
                pieces = rect_cells(poly, hole2)
                el = S.add(Elem('IfcCovering', f'{code} — пом. {room}, стена {lab}', room=room, predefined='CLADDING',
                                props={'Помещение': room, 'Стена': lab, 'Код отделки': code, 'Описание': D.FINISH[code],
                                       'Привязка, мм': f'{s0:.0f}…{s1:.0f} от левого края; отм. {z0:.0f}…{z1:.0f}'}))
                if tex == 'marble':
                    um = zone_texture(room, lab, s0, s1, z0, z1, code).key
                tp = EL.tile_params(room, lab, s0, s1, code) if tex == 'tiles' else None
                pieces2 = []
                for (a, b, cc, d) in pieces:              # разрез по верху короба: выше — стена без выноса
                    zt = _box_top(room, W, a, cc)
                    if zt is not None and b < zt < d:
                        pieces2 += [(a, b, cc, zt), (a, zt, cc, d)]
                    else:
                        pieces2.append((a, b, cc, d))
                for (a, b, cc, d) in pieces2:
                    off = 0
                    bx = _box_in_front(room, W, a, cc, z=(b + d) / 2)
                    segs = [(a, cc, 0)]
                    if bx:
                        sa, sb, dep = bx
                        segs = [(p, q, o) for p, q, o in ((a, sa, 0), (sa, sb, dep), (sb, cc, 0)) if q - p > 1]
                    for (p, q, off) in segs:
                        if tex == 'slats':
                            _slats(el, W, p, q, b, d, off, phase=s0 + 0.0)
                            continue
                        n3 = (W['n'][0], W['n'][1], 0)
                        fk = face_key(W['n'])

                        def uvf(m, n, pt, W=W, tex=tex, tp=tp, s0=s0, s1=s1, z0=z0, z1=z1):
                            s, _ = EL.proj(W, (pt[0], pt[1]))
                            if tex == 'tiles':
                                return ((s - tp['so']) / (4 * tp['tw']), (pt[2] - tp['zo']) / (4 * tp['th']))
                            if tex == 'marble':
                                return ((s - s0) / (s1 - s0), (pt[2] - z0) / (z1 - z0))
                            if tex == 'panels':
                                return ((s - s0) / 1200.0, pt[2] / 1200.0)
                            return (s / 1000.0, pt[2] / 1000.0)
                        mk = um if tex == 'marble' else c
                        wbox(el, mk, W, p, q, off, off + t, b, d, uvf=uvf)


def _obox(axis, a0, a1, c0, c1, z0, z1):
    """Параллелепипед в осях проёма: a — вдоль стены, c — поперёк."""
    if axis == 'y':
        return (min(a0, a1), min(c0, c1), z0, max(a0, a1), max(c0, c1), z1)
    return (min(c0, c1), min(a0, a1), z0, max(c0, c1), max(a0, a1), z1)


def _inner_face(o):
    """Грань проёма со стороны внутреннего помещения и плоскость рамы (середина стены)."""
    k, ax, c0, c1, a, b, z0, z1 = o
    m = (a + b) / 2
    for k_ in D.ROOMS:
        if indoor(k_):
            p = (m, c0 - 60) if ax == 'y' else (c0 - 60, m)
            if EL_inside(D.ROOMS[k_]['poly'], p):
                return c0, (c0 + c1) / 2
    return c1, (c0 + c1) / 2


def EL_inside(poly, p):
    c = False
    x, y = p
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if (ya > y) != (yb > y):
            xi = xa + (y - ya) * (xb - xa) / (yb - ya)
            if xi > x:
                c = not c
    return c


def reveals(S):
    """Откосы и подоконники окон (внутренняя часть до рамы); общие откосы окна и балконной двери не дублируются."""
    wins = [o for o in OPEN3D if OKIND.get(o[0]) in ('window', 'bdoor')]
    for o in wins:
        k, ax, c0, c1, a, b, z0, z1 = o
        inner, frame = _inner_face(o)
        shared_a = any(p is not o and p[1] == ax and p[2] == c0 and abs(p[5] - a) < 2 for p in wins)
        shared_b = any(p is not o and p[1] == ax and p[2] == c0 and abs(p[4] - b) < 2 for p in wins)
        el = S.add(Elem('IfcCovering', f'Откосы проёма {k}', predefined='CLADDING',
                        props={'Код отделки': 'С1', 'Проём': k}))
        c_lo, c_hi = (inner, frame) if frame > inner else (frame, inner)
        if not shared_b:
            box(el, 'C1', *_obox(ax, b - 3, b, c_lo, c_hi, z0, z1))
        if not shared_a:
            box(el, 'C1', *_obox(ax, a, a + 3, c_lo, c_hi, z0, z1))
        box(el, 'C1', *_obox(ax, a, b, c_lo, c_hi, z1 - 3, z1))
        if OKIND.get(k) == 'window':
            sill = S.add(Elem('IfcCovering', f'Подоконник {k}', predefined='USERDEFINED', objtype='Подоконник',
                              props={'Материал': 'ПВХ/искусственный камень, белый'}))
            ci = inner - 50 if frame > inner else inner + 50
            box(sill, 'WHITE', *_obox(ax, a - 50, b + (0 if shared_b else 50), ci, frame, z0 - 20, z0))


# ------------------------------------------------------------ двери
def _door_room(key):
    """Помещение, в которое открывается дверь."""
    d = D.DOORS[key]
    p = (d['h'][0] + d['o'][0] * 300 + d['c'][0] * d['L'] / 2, d['h'][1] + d['o'][1] * 300 + d['c'][1] * d['L'] / 2)
    return next((k for k in D.ROOMS if EL_inside(D.ROOMS[k]['poly'], p)), None)


def _wall_phase(room, along, face):
    """Начало стены развёртки помещения, на которой лежит грань face (для фазы реек)."""
    for lab, pL, pR in D.RWALLS.get(room, []):
        if along == 'y' and pL[0] == pR[0] and abs(pL[0] - face) < 120:
            return min(pL[1], pR[1])
        if along == 'x' and pL[1] == pR[1] and abs(pL[1] - face) < 120:
            return min(pL[0], pR[0])
    return 0.0


def doors(S):
    TCOL = {T_['mark']: T_ for T_ in D.DOOR_TYPES}
    for key, mark in D.DOOR_MARK.items():
        d = D.DOORS[key]
        hx, hy = d['h']; cx, cy = d['c']; ox, oy = d['o']; L = d['L']
        T_ = TCOL[mark]
        el = S.add(Elem('IfcDoor', f'{mark} — {T_["name"]}', tag=mark,
                        props={'Марка': mark, 'Полотно': T_['leaf'], 'Проём': T_['opening'], 'Отделка': T_['finish'],
                               'Открывание': D.DOOR_SCHED[[x['key'] for x in D.DOOR_SCHED].index(key)]['swing']}))
        op = next((o for o in EL.OPENINGS if o['key'] == key), {})
        el.door_dims = (op.get('z1', getattr(D, 'DOOR_H', 2100)), L)
        th = 40 if key != 'entry' else 70
        # полотно в закрытом положении: от петли вдоль c на L, толщина — внутрь проёма (против o)
        p1 = (hx, hy)
        p2 = (hx + cx * L, hy + cy * L)
        q1 = (p1[0] - ox * th, p1[1] - oy * th)
        x0, x1 = min(p1[0], p2[0], q1[0]), max(p1[0], p2[0], q1[0])
        y0, y1 = min(p1[1], p2[1], q1[1]), max(p1[1], p2[1], q1[1])
        h = el.door_dims[0]
        g0, g1 = _leaf_z(key, h)                   # полотно: зазор над полом/порогом и высота
        fo = face_key((ox, oy))                    # грань со стороны открывания
        fb = face_key((-ox, -oy))
        clad = op.get('clad', {})
        if key == 'entry':
            inner = fmat(getattr(D, 'FRONT', None), 'FRONT') if getattr(D, 'FRONT', None) else 'FRONT'
            fm = {fo: 'ENTRY', fb: inner}
            box(el, 'ENTRY', x0, y0, g0, x1, y1, g1, fm=fm)
        elif not clad:
            lm = fmat(getattr(D, 'DOOR_LEAF_FINISH', None), None) or mkey(D.WALL_DEFAULT.get(_door_room(key)) or 'С1')
            HP.rbox(el, lm, x0, y0, g0, x1, y1, g1, 2, 2)
            _leaf_panels(el, lm, (hx, hy), (cx, cy), (ox, oy), L, th, h, T_, z_off=g0)
        else:
            box(el, mkey(getattr(D, 'DOOR_LEAF_FINISH', 'С7')), x0, y0, 0, x1, y1, h, fm={fo: 'BLACK'})
            # рейки со стороны облицованного помещения — в шаге реек стены (фаза от начала стены развёртки)
            room_c = list(clad)[0]
            if ox:                        # полотно вдоль y, облицовка на грани x
                sx0, sx1 = (y0, y1)
                xf = x1 if ox > 0 else x0
                ph = _wall_phase(room_c, 'y', xf)
                s_ = ph + math.ceil((sx0 - ph) / 60.0) * 60
                while s_ < sx1:
                    a_, b_ = max(s_, sx0), min(s_ + 40, sx1)
                    if b_ - a_ > 2:
                        box(el, 'WALNUT', min(xf, xf + ox * 26), a_, 0, max(xf, xf + ox * 26), b_, h)
                    s_ += 60
                box(el, 'BLACK', min(xf, xf + ox * 6), sx0, 0, max(xf, xf + ox * 6), sx1, h)
            else:                         # полотно вдоль x, облицовка на грани y
                sx0, sx1 = (x0, x1)
                yf = y1 if oy > 0 else y0
                ph = _wall_phase(room_c, 'x', yf)
                s_ = ph + math.ceil((sx0 - ph) / 60.0) * 60
                while s_ < sx1:
                    a_, b_ = max(s_, sx0), min(s_ + 40, sx1)
                    if b_ - a_ > 2:
                        box(el, 'WALNUT', a_, min(yf, yf + oy * 26), 0, b_, max(yf, yf + oy * 26), h)
                    s_ += 60
                box(el, 'BLACK', sx0, min(yf, yf + oy * 6), 0, sx1, max(yf, yf + oy * 6), h)
        _door_trim(S, key, mark, op)
        # ручки: розетка + нажимная ручка (латунь матовая) с двух сторон
        hp_ = (hx + cx * (L - 70), hy + cy * (L - 70))
        for wf, sgn in ((0, 1), (-th, -1)):
            p = (hp_[0] + ox * wf, hp_[1] + oy * wf, 1000)
            DT.lever_handle(el, 'BRASS' if key != 'entry' else 'NICKEL', p, (ox * sgn, oy * sgn, 0), (-cx, -cy, 0))


# ------------------------------------------------------------ окна
def _frame_glass(el, a, b, z0, z1, y0, y1, splits=(), lower_panel=None):
    """Рама ПВХ 60 мм + стекло, по оси x от a до b, глубина y0..y1."""
    fw = 60
    box(el, 'PVC', a, y0, z0, b, y1, z0 + fw)
    box(el, 'PVC', a, y0, z1 - fw, b, y1, z1)
    box(el, 'PVC', a, y0, z0, a + fw, y1, z1)
    box(el, 'PVC', b - fw, y0, z0, b, y1, z1)
    xs = [a + fw] + [s for s in splits] + [b - fw]
    for i, s in enumerate(splits):
        box(el, 'PVC', s - 40, y0, z0, s + 40, y1, z1)
    ym = (y0 + y1) / 2
    zg0 = z0 + fw
    if lower_panel:
        box(el, 'PVC', a + fw, ym - 15, z0 + fw, b - fw, ym + 15, lower_panel)
        box(el, 'PVC', a + fw, y0, lower_panel, b - fw, y1, lower_panel + 50)
        zg0 = lower_panel + 50
    edges = [a + fw] + [x for s in splits for x in (s - 40, s + 40)] + [b - fw]
    for i in range(0, len(edges), 2):
        box(el, 'GLASS', edges[i], ym - 4, zg0, edges[i + 1], ym + 4, z1 - fw)


def windows(S):
    """Окна и балконные двери из проёмов (рама ПВХ в середине стены), остекление балконов над парапетами."""
    for o in OPEN3D:
        k, ax, c0, c1, a, b, z0, z1 = o
        kind = OKIND.get(k)
        if kind not in ('window', 'bdoor'):
            continue
        fr = (c0 + c1) / 2
        f0, f1 = fr - 35, fr + 35
        if kind == 'window':
            el = S.add(Elem('IfcWindow', f'Окно {k}', predefined='WINDOW', props={'Статус': 'существующее', 'Размер': f'{b - a:.0f}×{z1 - z0:.0f}'}))
            el.win_dims = (z1 - z0, b - a)
            spl = ((a + b) / 2,) if b - a >= 1300 else ()
            _frame_glass_ax(el, ax, a, b, z0, z1, f0, f1, splits=spl)
            inner, _ = _inner_face(o)
            hs = -1 if inner < fr else 1
            ea = np.array([1.0, 0, 0]) if ax == 'y' else np.array([0, 1.0, 0])
            en = np.array([0, 1.0, 0]) if ax == 'y' else np.array([1.0, 0, 0])
            for sx in ([s_ - 70 for s_ in spl] or [b - 100]):
                cpt = ea * sx + en * ((f1 if hs > 0 else f0)) + np.array([0, 0, (z0 + z1) / 2])
                DT.lever_handle(el, 'WHITE', cpt, en * hs, np.array([0, 0, -1.0]), L=110)
        else:
            el = S.add(Elem('IfcDoor', 'Балконная дверь (существующая)', tag='БД', props={'Статус': 'существующая'}))
            el.door_dims = (z1 - z0, b - a)
            _frame_glass_ax(el, ax, a, b, z0, z1, f0, f1, lower_panel=800)
            inner, _ = _inner_face(o)
            hs = -1 if inner < fr else 1
            box(el, 'BLACK', *_obox(ax, a + 50, a + 70, f0 if hs < 0 else f1, (f0 if hs < 0 else f1) + hs * 50, 1000, 1150))
    # остекление балконов над парапетами
    for (x0, y0, x1, y1) in parapets():
        el = S.add(Elem('IfcWindow', 'Остекление балкона (существующее)', predefined='WINDOW', props={'Статус': 'существующее'}))
        along_y = (y1 - y0) > (x1 - x0)
        a, b = (y0, y1) if along_y else (x0, x1)
        c = (x0 + x1) / 2 if along_y else (y0 + y1) / 2
        ax = 'x' if along_y else 'y'
        el.win_dims = (BALC_TOP - 900, b - a)
        n = max(1, round((b - a) / 750))
        posts = [a + i * (b - a) / n for i in range(n + 1)]
        box(el, 'PVC', *_obox(ax, a, b, c - 30, c + 30, 900, 960))
        box(el, 'PVC', *_obox(ax, a, b, c - 30, c + 30, BALC_TOP - 60, BALC_TOP))
        for i, p_ in enumerate(posts):
            box(el, 'PVC', *_obox(ax, p_ - (30 if i else 0), p_ + (30 if i < n else 0), c - 30, c + 30, 900, BALC_TOP))
        for i in range(n):
            box(el, 'GLASS', *_obox(ax, posts[i] + 30, posts[i + 1] - 30, c - 4, c + 4, 960, BALC_TOP - 60))


def _frame_glass_ax(el, ax, a, b, z0, z1, c0, c1, splits=(), lower_panel=None):
    """Рама ПВХ 60 мм + стекло в осях проёма (a — вдоль стены, c0..c1 — глубина рамы)."""
    fw = 60
    B = lambda a0, a1, cc0, cc1, za, zb, m='PVC': box(el, m, *_obox(ax, a0, a1, cc0, cc1, za, zb))  # noqa: E731
    B(a, b, c0, c1, z0, z0 + fw)
    B(a, b, c0, c1, z1 - fw, z1)
    B(a, a + fw, c0, c1, z0, z1)
    B(b - fw, b, c0, c1, z0, z1)
    for s_ in splits:
        B(s_ - 40, s_ + 40, c0, c1, z0, z1)
    cm = (c0 + c1) / 2
    zg0 = z0 + fw
    if lower_panel:
        B(a + fw, b - fw, cm - 15, cm + 15, z0 + fw, lower_panel)
        B(a + fw, b - fw, c0, c1, lower_panel, lower_panel + 50)
        zg0 = lower_panel + 50
    edges = [a + fw] + [x for s_ in splits for x in (s_ - 40, s_ + 40)] + [b - fw]
    for i in range(0, len(edges), 2):
        B(edges[i], edges[i + 1], cm - 4, cm + 4, zg0, z1 - fw, 'GLASS')


# ------------------------------------------------------------ мебель и оборудование
def _front_dir(r, room):
    """Сторона предмета, обращённая в помещение: '+x', '-x', '+y', '-y' (противоположная прилегающей к стене)."""
    poly = D.ROOMS[room]['poly']
    x0, y0, x1, y1 = r

    def on_edge(axis, c, lo, hi):
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            if axis == 'x' and xa == xb and abs(xa - c) < 8 and min(ya, yb) < hi - 5 and max(ya, yb) > lo + 5:
                return True
            if axis == 'y' and ya == yb and abs(ya - c) < 8 and min(xa, xb) < hi - 5 and max(xa, xb) > lo + 5:
                return True
        return False
    touch = {'-x': on_edge('x', x0, y0, y1), '+x': on_edge('x', x1, y0, y1), '-y': on_edge('y', y0, x0, x1),
             '+y': on_edge('y', y1, x0, x1)}
    opp = {'-x': '+x', '+x': '-x', '-y': '+y', '+y': '-y'}
    cands = [opp[k] for k, v in touch.items() if v and not touch[opp[k]]]
    if not cands:
        return '+y'
    lx, ly = x1 - x0, y1 - y0
    cands.sort(key=lambda f: -(lx if f in ('+y', '-y') else ly))
    return cands[0]


SIDE_N = {'W': (1, 0), 'E': (-1, 0), 'S': (0, 1), 'N': (0, -1)}      # внутренняя нормаль стены стороны


def lbox(el, m, side, face, u0, u1, w0, w1, z0, z1, fm=None):
    """Параллелепипед в локальных осях стены: u — от стены внутрь, w — вдоль стены (координата модели)."""
    nx, ny = SIDE_N[side]
    if nx:
        xa, xb = face + nx * u0, face + nx * u1
        bb = (min(xa, xb), min(w0, w1), z0, max(xa, xb), max(w0, w1), z1)
    else:
        ya, yb = face + ny * u0, face + ny * u1
        bb = (min(w0, w1), min(ya, yb), z0, max(w0, w1), max(ya, yb), z1)
    if fm is None and min(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) >= 6:
        HP.rbox(el, m, *bb, 1.5, 2)                      # кромки скруглены (мебель, фасады)
    else:
        box(el, m, *bb, fm=fm)


def side_of(r, room):
    """Сторона стены, к которой примыкает предмет (W/E/S/N) — по направлению фасада."""
    return {'-x': 'E', '+x': 'W', '-y': 'N', '+y': 'S'}[_front_dir(r, room)]


def _panels(el, m, r, front, z0, z1, n, gap=3, th=18, mats=None):
    """Фасадные панели (двери) n шт. с зазорами на лицевой стороне корпуса."""
    x0, y0, x1, y1 = r
    if front in ('+y', '-y'):
        yf = y1 if front == '+y' else y0
        w = (x1 - x0 - gap * (n + 1)) / n
        for i in range(n):
            a = x0 + gap + i * (w + gap)
            mm = mats[i] if mats else m
            HP.rbox(el, mm, a, yf - th if front == '+y' else yf, z0, a + w, yf if front == '+y' else yf + th, z1, 2, 2)
    else:
        xf = x1 if front == '+x' else x0
        w = (y1 - y0 - gap * (n + 1)) / n
        for i in range(n):
            a = y0 + gap + i * (w + gap)
            mm = mats[i] if mats else m
            HP.rbox(el, mm, xf - th if front == '+x' else xf, a, z0, xf if front == '+x' else xf + th, a + w, z1, 2, 2)


def _carcass(el, m, r, front, z0, z1, th=18):
    x0, y0, x1, y1 = r
    if front == '+y':
        y1 -= th
    elif front == '-y':
        y0 += th
    elif front == '+x':
        x1 -= th
    else:
        x0 += th
    box(el, m, x0, y0, z0, x1, y1, z1, fm={front: 'BLACK'})


def _shrink(r, front, d):
    x0, y0, x1, y1 = r
    return {'+y': (x0, y0, x1, y1 - d), '-y': (x0, y0 + d, x1, y1), '+x': (x0, y0, x1 - d, y1), '-x': (x0 + d, y0, x1, y1)}[front]


def _rot(c, ang, u, v):
    a = math.radians(ang)
    return (c[0] + u * math.cos(a) - v * math.sin(a), c[1] + u * math.sin(a) + v * math.cos(a))


def _rbox(el, m, c, ang, u0, v0, u1, v1, z0, z1):
    """Параллелепипед в локальных осях предмета (любой угол поворота)."""
    if abs(ang) % 90 < 1e-6:
        p = _rot(c, ang, u0, v0); q = _rot(c, ang, u1, v1)
        box(el, m, p[0], p[1], z0, q[0], q[1], z1)
        return
    prism(el, m, [_rot(c, ang, u0, v0), _rot(c, ang, u1, v0), _rot(c, ang, u1, v1), _rot(c, ang, u0, v1)], z0, z1)


def furniture(S):
    CLS = {'wc': ('IfcSanitaryTerminal', 'TOILETPAN'), 'vanity': ('IfcSanitaryTerminal', 'WASHHANDBASIN'),
           'mini_basin': ('IfcSanitaryTerminal', 'WASHHANDBASIN'), 'shower': ('IfcSanitaryTerminal', 'SHOWER'),
           'drain': ('IfcWasteTerminal', 'FLOORTRAP'), 'glass': ('IfcPlate', 'USERDEFINED'),
           'radiator': ('IfcSpaceHeater', 'RADIATOR'), 'towel': ('IfcSpaceHeater', 'USERDEFINED'),
           'mirror': ('IfcFurniture', 'USERDEFINED'), 'mirror_oval': ('IfcFurniture', 'USERDEFINED'),
           'ac': ('IfcUnitaryEquipment', 'SPLITSYSTEM'), 'tv': ('IfcAudioVisualAppliance', 'DISPLAY'),
           'box': ('IfcBuildingElementProxy', 'USERDEFINED'), 'bed': ('IfcFurniture', 'BED'), 'bed_single': ('IfcFurniture', 'BED'),
           'chair': ('IfcFurniture', 'CHAIR'), 'sofa': ('IfcFurniture', 'SOFA'), 'table': ('IfcFurniture', 'TABLE'),
           'desk': ('IfcFurniture', 'DESK'), 'shelving': ('IfcFurniture', 'SHELF'), 'wallshelf': ('IfcFurniture', 'SHELF'),
           'coffee': ('IfcFurniture', 'TABLE'), 'round': ('IfcFurniture', 'TABLE'), 'lounge': ('IfcFurniture', 'CHAIR'),
           'bath': ('IfcSanitaryTerminal', 'BATH'), 'hatch_wall': ('IfcBuildingElementProxy', 'USERDEFINED'),
           'nightstand': ('IfcFurniture', 'USERDEFINED'), 'tvconsole': ('IfcFurniture', 'USERDEFINED')}
    for it in D.ITEMS:
        k = it['kind']
        room = it['room']
        cls, pre = CLS.get(k, ('IfcFurniture', 'USERDEFINED'))
        name = it.get('name', k)
        el = Elem(cls, name, room=room, predefined=pre, objtype=OBJT.get(k, name) if pre == 'USERDEFINED' else None,
                  props={'Помещение': room, 'Позиция': it.get('pos', '')}, tag=it.get('pos') or None)
        r = M_item_rect(it)
        z = it.get('z', (0, 0))
        zf = zf_of(room)
        if r:
            el.props['Габарит в плане, мм'] = f'{r[2] - r[0]:.0f}×{r[3] - r[1]:.0f}'
        if isinstance(z, tuple):
            el.props['Отметки, мм'] = f'{z[0]}…{z[1]}'
        build_item(el, it, k, r, z, room, zf)
        if el.parts:
            S.add(el)
    # бытовая техника в колоннах, кухня — отдельные элементы
    appliances(S)
    curtains(S)


OBJT = {'wardrobe': 'Шкаф встроенный', 'bench': 'Банкетка', 'console': 'Консоль подвесная', 'mirror': 'Зеркало',
        'nightstand': 'Тумба прикроватная', 'kitchen_run': 'Кухня — нижние модули', 'upper': 'Кухня — верхние шкафы',
        'column': 'Кухня — колонна', 'filler': 'Кухня — заглушка', 'tvconsole': 'ТВ-тумба', 'rug': 'Ковёр',
        'wm_cab': 'Шкаф для стиральной и сушильной машин', 'towel': 'Полотенцесушитель электрический',
        'glass': 'Стеклянная перегородка', 'mirror_oval': 'Зеркало с подсветкой', 'box': 'Короб инсталляции (ГКЛВ)',
        'hatch_wall': 'Люк-невидимка под плитку'}


def M_item_rect(it):
    return D.item_rect(it)


def build_item(el, it, k, r, z, room, zf):
    if DT.build_item(el, it, k, r, z, room, zf):
        return
    if k == 'wardrobe':
        fr = _front_dir(r, room)
        fm_ = fmat(it.get('mat'), 'FRONT')
        _carcass(el, 'FRONT', r, fr, z[0] + 60, z[1])
        box(el, fm_, *_shrink(r, fr, 40)[:2], z[0], *_shrink(r, fr, 40)[2:], z[0] + 59)
        wlen = ((r[2] - r[0]) if fr in ('+y', '-y') else (r[3] - r[1]))
        n = it.get('doors') or max(1, round(wlen / 600))
        _panels(el, fm_, r, fr, z[0] + 60, z[1] - 3, n)
        if 'молдинг' in it.get('name', '') or it.get('mat') not in ('oak', 'walnut'):
            zb = z[0] + 60 + (z[1] - z[0] - 60) * 0.3
            _panel_frames(el, fm_, r, fr, n, [(z[0] + 150, zb - 45), (zb + 45, z[1] - 120)])
        _panel_handles(el, r, fr, n, z[0] + 1000, z[0] + 1300, pairs=True)
    elif k == 'column':
        fr = _front_dir(r, room)
        cf = fmat(it.get('front') or it.get('mat'), 'FRONT')
        _carcass(el, cf, r, fr, 100, z[1])
        sd = side_of(r, room)
        face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
        dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
        w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
        if 'ДШ' in it.get('label', ''):    # духовой шкаф и СВЧ — отдельными элементами (appliances)
            lbox(el, cf, sd, face, dep - 18, dep, w0 + 3, w1 - 3, 100, 847)
            lbox(el, cf, sd, face, dep - 18, dep, w0 + 3, w1 - 3, 1830, z[1] - 3)
        else:
            lbox(el, cf, sd, face, dep - 18, dep, w0 + 3, w1 - 3, 100, 1877)
            lbox(el, cf, sd, face, dep - 18, dep, w0 + 3, w1 - 3, 1880, z[1] - 3)
            lbox(el, 'BRASS', sd, face, dep, dep + 25, w0 + 40, w0 + 52, 900, 1400)
            lbox(el, 'BRASS', sd, face, dep, dep + 25, w0 + 40, w0 + 52, 1950, 2250)
        lbox(el, 'BLACK', sd, face, 0, dep - 50, w0 + 1, w1 - 1, 0, 99)
    elif k == 'filler':
        box(el, 'FRONT', *r[:2], 100, *r[2:], 900)
    elif k == 'kitchen_run':
        sd = it.get('side', 'W')
        face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
        dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
        w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
        fk = face_key(SIDE_N[sd])                        # грань фасадов (в помещение)
        kf = fmat(it.get('front'), 'FRONT')
        top = 'MARBLE' if it.get('top') and D.mat(it['top']).get('tex') == 'marble' else fmat(it.get('top'), 'OAK')
        lbox(el, 'BLACK', sd, face, 0, dep - 50, w0, w1, 0, 100)
        lbox(el, kf, sd, face, 0, dep - 18, w0, w1, 100, 870, fm={fk: 'BLACK'})
        for a, b, kind in it['modules']:
            if kind in ('dw', 'sink', 'tech'):
                lbox(el, kf, sd, face, dep - 18, dep, a + 2, b - 2, 103, 867)
                lbox(el, 'BRASS', sd, face, dep, dep + 22, (a + b) / 2 - 80, (a + b) / 2 + 80, 820, 832)
            elif kind == 'hob':                       # духовой шкаф под варочной панелью (appliances) + ящик
                lbox(el, kf, sd, face, dep - 18, dep, a + 2, b - 2, 103, 150)
                lbox(el, kf, sd, face, dep - 18, dep, a + 2, b - 2, 750, 867)
                lbox(el, 'BRASS', sd, face, dep, dep + 22, (a + b) / 2 - 80, (a + b) / 2 + 80, 820, 832)
            else:
                lbox(el, kf, sd, face, dep - 18, dep, a + 2, b - 2, 103, 480)
                lbox(el, kf, sd, face, dep - 18, dep, a + 2, b - 2, 484, 867)
                for zz in (440, 820):
                    lbox(el, 'BRASS', sd, face, dep, dep + 22, (a + b) / 2 - 80, (a + b) / 2 + 80, zz, zz + 12)
        lbox(el, top, sd, face, 0, dep + 10, w0, w1, 870, 900)
        for a, b, kind in it['modules']:
            cy = (a + b) / 2
            if kind == 'sink':
                lbox(el, 'STEEL', sd, face, dep - 480, dep - 80, cy - 240, cy + 240, 900, 901.5)
                lbox(el, 'STEEL', sd, face, dep - 470, dep - 90, cy - 230, cy + 230, 700, 702)
                lbox(el, 'BRASS', sd, face, 50, 90, cy - 20, cy + 20, 900, 1250)
                lbox(el, 'BRASS', sd, face, 50, 250, cy - 15, cy + 15, 1220, 1250)
    elif k == 'upper':
        sd = it.get('side', 'W')
        face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
        dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
        w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
        fk = face_key(SIDE_N[sd])
        zs = min(it.get('split', z[0] + 850), z[1])     # нижний ряд и антресоли
        m_lo = fmat(it.get('front_low'), 'WALNUT') if it.get('front_low') else 'WALNUT'
        m_hi = fmat(it.get('front'), 'FRONT')
        lbox(el, m_lo, sd, face, 0, dep - 18, w0, w1, z[0], zs, fm={fk: 'BLACK'})
        if z[1] > zs + 10:
            lbox(el, m_hi, sd, face, 0, dep - 18, w0, w1, zs, z[1], fm={fk: 'BLACK'})
        n = max(1, int(round((w1 - w0) / 600)))
        w = (w1 - w0) / n
        for i in range(n):
            a = w0 + i * w
            lbox(el, m_lo, sd, face, dep - 18, dep, a + 2, a + w - 2, z[0] + 3, zs - 3)
            lbox(el, 'BRASS', sd, face, dep, dep + 22, a + w / 2 - 60, a + w / 2 + 60, z[0] + 40, z[0] + 52)
            if z[1] > zs + 10:
                lbox(el, m_hi, sd, face, dep - 18, dep, a + 2, a + w - 2, zs + 3, z[1] - 3)
        if it.get('hood'):                                # встроенная вытяжка (рециркуляция) — дно в уровне низа шкафов
            h0, h1 = it['hood']
            lbox(el, 'STEEL', sd, face, 20, dep - 18, h0 + 20, h1 - 20, z[0] - 6, z[0])
            lbox(el, 'BLACKGLASS', sd, face, dep - 140, dep - 30, h0 + 60, h1 - 60, z[0] - 7, z[0] - 6)
    elif k == 'table':
        x0, y0, x1, y1 = r
        box(el, 'OAK', x0, y0, z[1] - 30, x1, y1, z[1])
        for (px, py) in ((x0 + 60, y0 + 60), (x1 - 100, y0 + 60), (x0 + 60, y1 - 100), (x1 - 100, y1 - 100)):
            box(el, 'BLACK', px, py, 0, px + 40, py + 40, z[1] - 30)
    elif k == 'chair':
        c = it['c']
        ang = it['ang']
        if 'pouf' in it['key']:
            cyl(el, 'FAB_CHAIR', c[0], c[1], 210, 0, z[1])
            return
        if it.get('style') == 'office' or 'кресло' in it.get('name', '').lower():
            cyl(el, 'BLACK', c[0], c[1], 260, 0, 30, 5)
            cyl(el, 'BLACK', c[0], c[1], 25, 30, 430)
            _rbox(el, 'FAB_CHAIR', c, ang, -240, -230, 240, 230, 430, 500)
            _rbox(el, 'FAB_CHAIR', c, ang, -260, -230, -200, 230, 520, 1000)
            return
        # локальные оси как на плане: u — глубина (спинка при u<0), v — ширина
        _rbox(el, 'FAB_CHAIR', c, ang, -230, -220, 230, 220, 430, 480)
        _rbox(el, 'FAB_CHAIR', c, ang, -230, -220, -190, 220, 480, 820)
        for u, v in ((-215, -205), (190, -205), (-215, 180), (190, 180)):
            _rbox(el, 'OAK', c, ang, u, v, u + 25, v + 25, 0, 430)
    elif k == 'sofa' and 'pts' in it and it.get('lines'):
        pts = [tuple(p) for p in it['pts']]
        fab = fabric_mat(it['fabric_col']) if it.get('fabric_col') else 'FAB_TAUPE'
        l0 = [tuple(p) for p in it['lines'][0]]
        nb = len(l0)
        back = pts[:nb] + l0[::-1]
        seat = l0 + pts[nb:]
        prism(el, 'BLACK', pts, 0, 90)
        prism(el, fab, pts, 90, 400)
        prism(el, fab, seat, 400, 470)
        prism(el, fab, back, 400, z[1])
        # подушки спинки
        for a, b in zip(l0, l0[1:]):
            L_ = math.hypot(b[0] - a[0], b[1] - a[1])
            nseg = max(1, int(L_ // 700))
            for i in range(nseg):
                pa = (a[0] + (b[0] - a[0]) * (i + 0.04) / nseg, a[1] + (b[1] - a[1]) * (i + 0.04) / nseg)
                pb = (a[0] + (b[0] - a[0]) * (i + 0.96) / nseg, a[1] + (b[1] - a[1]) * (i + 0.96) / nseg)
                seg_prism(el, fab, pa, pb, 140, 470, z[1] - 60, off=-140 if _left_inside(pa, pb, seat) else 0)
    elif k == 'sofa':
        sd = it.get('back', 'W')                       # спинка у стороны back
        face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
        dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
        w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
        wm = (w0 + w1) / 2
        lbox(el, 'BLACK', sd, face, 40, dep - 40, w0 + 40, w1 - 40, 0, 80)
        lbox(el, 'FAB_TAUPE', sd, face, 0, dep, w0, w1, 80, 400)
        lbox(el, 'FAB_TAUPE', sd, face, 220, dep - 20, w0 + 200, wm - 5, 400, 470)
        lbox(el, 'FAB_TAUPE', sd, face, 220, dep - 20, wm + 5, w1 - 200, 400, 470)
        lbox(el, 'FAB_TAUPE', sd, face, 0, 220, w0 + 200, w1 - 200, 400, z[1])
        lbox(el, 'FAB_TAUPE', sd, face, 0, dep, w0, w0 + 200, 400, 620)
        lbox(el, 'FAB_TAUPE', sd, face, 0, dep, w1 - 200, w1, 400, 620)
    elif k == 'coffee':
        x0, y0, x1, y1 = r
        box(el, 'OAK', x0, y0, z[1] - 30, x1, y1, z[1])
        box(el, 'BLACK', x0 + 80, y0 + 80, 0, x1 - 80, y1 - 80, z[1] - 30)
    elif k in ('tvconsole', 'nightstand', 'console'):
        x0, y0, x1, y1 = r
        m = fmat(it.get('mat'), 'WALNUT')
        fr = _front_dir(r, room)
        _carcass(el, m, r, fr, z[0], z[1])
        wlen = (x1 - x0) if fr in ('+y', '-y') else (y1 - y0)
        n = max(1, int(round(wlen / 500)))
        if k == 'nightstand':
            zm = (z[0] + z[1]) / 2
            _panels(el, m, r, fr, z[0] + 3, zm - 2, 1)
            _panels(el, m, r, fr, zm + 2, z[1] - 3, 1)
            _panel_handles(el, r, fr, 1, zm - 70, zm - 58, knob=True)
            _panel_handles(el, r, fr, 1, z[1] - 70, z[1] - 58, knob=True)
        else:
            _panels(el, m, r, fr, z[0] + 3, z[1] - 3, n)
            _panel_handles(el, r, fr, n, z[1] - 70, z[1] - 58, knob=True)
        if z[0] == 0:
            box(el, 'BRASS', x0 + 40, y0 + 40, 0, x0 + 60, y0 + 60, 1)
    elif k == 'tv':
        x0, y0, x1, y1 = r
        fr = _front_dir(r, room)
        box(el, 'BLACK', x0, y0, z[0], x1, y1, z[1], fm={fr: 'SCREEN'})
    elif k == 'rug':
        box(el, 'FAB_RUG', *r[:2], zf, *r[2:], zf + 10)
    elif k == 'radiator':
        x0, y0, x1, y1 = r
        along_x = (x1 - x0) > (y1 - y0)
        n = int(((x1 - x0) if along_x else (y1 - y0)) / 80)
        for i in range(n):
            if along_x:
                a = x0 + i * (x1 - x0) / n
                box(el, 'WHITE', a + 5, y0, z[0], a + (x1 - x0) / n - 5, y1, z[1])
            else:
                a = y0 + i * (y1 - y0) / n
                box(el, 'WHITE', x0, a + 5, z[0], x1, a + (y1 - y0) / n - 5, z[1])
        # коллекторы и подводки (существующие)
        if along_x:
            for zz in (z[0] + 30, z[1] - 30):
                tube(el, 'WHITE', (x0, (y0 + y1) / 2, zz), (x1, (y0 + y1) / 2, zz), 14)
        else:
            for zz in (z[0] + 30, z[1] - 30):
                tube(el, 'WHITE', ((x0 + x1) / 2, y0, zz), ((x0 + x1) / 2, y1, zz), 14)
        el.props['Статус'] = 'существующий (система отопления дома)'
    elif k in ('bed', 'bed_single') and it.get('head', 'S') in ('E', 'S') or (k in ('bed', 'bed_single') and it.get('fabric_col')):
        _bed(el, it, k, r, z)
    elif k == 'bed' or k == 'bed_single':
        x0, y0, x1, y1 = r
        head = it.get('head', 'S')
        hb = 1100 if k == 'bed' else 900
        box(el, 'FAB_GREY', x0, y0, 80, x1, y1, 320)
        box(el, 'BLACK', x0 + 60, y0 + 60, 0, x1 - 60, y1 - 60, 80)
        inset = {'W': (100, 0, 0, 0), 'N': (0, 0, 0, 100), 'S': (0, 100, 0, 0), 'E': (0, 0, 100, 0)}[head]
        box(el, 'MATTRESS', x0 + 20 + inset[0], y0 + 20 + inset[1], 320, x1 - 20 - inset[2], y1 - 20 - inset[3], 540)
        if head == 'W':
            box(el, 'FAB_GREY', x0, y0 - (0 if k == 'bed_single' else 0), 0, x0 + 100, y1, hb)
            box(el, 'FAB_LINEN', x0 + 750, y0 + 10, 540, x1 - 10, y1 - 10, 575)
            for (a, b) in ((y0 + 80, (y0 + y1) / 2 - 20), ((y0 + y1) / 2 + 20, y1 - 80)):
                box(el, 'MATTRESS', x0 + 140, a, 540, x0 + 520, b, 660)
        elif head == 'N':
            box(el, 'FAB_GREY', x0, y1 - 100, 0, x1, y1, hb)
            box(el, 'FAB_LINEN', x0 + 10, y0 + 10, 540, x1 - 10, y1 - 750, 575)
            box(el, 'MATTRESS', x0 + 120, y1 - 520, 540, x1 - 120, y1 - 140, 660)
    elif k == 'desk':
        x0, y0, x1, y1 = r
        m = fmat(it.get('mat'), 'OAK')
        if it.get('mat') == 'walnut':
            box(el, 'WALNUT', x0, y0, 600, x1, y1, z[1])
        elif (y1 - y0) >= (x1 - x0):          # стол вдоль y — опоры по торцам y
            box(el, m, x0, y0, z[1] - 30, x1, y1, z[1])
            box(el, m, x0, y0, 0, x1, y0 + 25, z[1] - 30)
            box(el, m, x0, y1 - 25, 0, x1, y1, z[1] - 30)
            fr = _front_dir(r, room)
            box(el, m, *(_shrink((x0, y0 + 25, x1, y1 - 25), fr, 0)[:2]), z[1] - 180, *(_shrink((x0, y0 + 25, x1, y1 - 25), fr, 0)[2:]), z[1] - 30)
        else:
            box(el, m, x0, y0, z[1] - 30, x1, y1, z[1])
            box(el, m, x0, y0, 0, x0 + 25, y1, z[1] - 30)
            box(el, m, x1 - 25, y0, 0, x1, y1, z[1] - 30)
    elif k == 'shelving' and it.get('variant') == 'pencil':
        x0, y0, x1, y1 = r       # пенал открыт к −y
        box(el, 'WALNUT', x0, y0, 0, x0 + 18, y1, z[1])
        box(el, 'WALNUT', x1 - 18, y0, 0, x1, y1, z[1])
        box(el, 'WALNUT', x0 + 18, y1 - 10, 0, x1 - 18, y1, z[1])
        zz = 100
        box(el, 'BLACK', x0 + 18, y0 + 30, 0, x1 - 18, y1 - 10, 100)
        while zz <= z[1] - 18:
            box(el, 'WALNUT', x0 + 18, y0, zz, x1 - 18, y1 - 10, zz + 18)
            zz += 380
    elif k == 'shelving':
        x0, y0, x1, y1 = r
        m = {'walnut': 'WALNUT', 'oak': 'OAK'}.get(it.get('mat'), 'WALNUT')
        fr = _front_dir(r, room)
        if fr in ('+x', '-x'):          # стеллаж вдоль y: боковины по торцам y, задняя стенка у стены
            box(el, m, x0, y0, 0, x1, y0 + 20, z[1])
            box(el, m, x0, y1 - 20, 0, x1, y1, z[1])
            bx0 = x0 if fr == '+x' else x1 - 10
            box(el, m, bx0, y0, 0, bx0 + 10, y1, z[1])
            zz = 0
            while zz <= z[1] - 20:
                box(el, m, x0, y0 + 20, zz, x1, y1 - 20, zz + 20)
                zz += 380
        else:
            box(el, m, x0, y0, 0, x0 + 20, y1, z[1])
            box(el, m, x1 - 20, y0, 0, x1, y1, z[1])
            by0 = y0 if fr == '+y' else y1 - 10
            box(el, m, x0, by0, 0, x1, by0 + 10, z[1])
            zz = 0
            while zz <= z[1] - 20:
                box(el, m, x0 + 20, y0, zz, x1 - 20, y1, zz + 20)
                zz += 380
    elif k == 'ac':
        x0, y0, x1, y1 = r
        box(el, 'WHITE', x0, y0, z[0] + 20, x1, y1, z[1])
        fr = _front_dir(r, room)
        sx = _shrink(r, {'+x': '-x', '-x': '+x', '+y': '-y', '-y': '+y'}[fr], 60)
        box(el, 'GRAPHITE', sx[0], sx[1], z[0], sx[2], sx[3], z[0] + 20)          # жалюзи выдува
        el.name = (it.get('name') or 'Внутренний блок сплит-системы') + ' (существующий — проверить)'
        el.props['Статус'] = 'существующий, проверить'
    elif k == 'lounge':
        x0, y0, x1, y1 = r       # кресла развёрнуты к столику
        box(el, 'FAB_TAUPE', x0, y0, 300, x1, y1, 420)
        tab = next((t for t in D.ITEMS if t['room'] == room and t['kind'] in ('round', 'coffee')), None)
        tc = tab['c'] if tab and 'c' in tab else ((tab['rect'][0] + tab['rect'][2]) / 2, (tab['rect'][1] + tab['rect'][3]) / 2) if tab else None
        if tc and abs(tc[1] - (y0 + y1) / 2) < abs(tc[0] - (x0 + x1) / 2):
            # столик выше/ниже по x: спинка с противоположной стороны по x
            if tc[0] > (x0 + x1) / 2:
                box(el, 'FAB_TAUPE', x0, y0, 420, x0 + 120, y1, z[1])
            else:
                box(el, 'FAB_TAUPE', x1 - 120, y0, 420, x1, y1, z[1])
        elif tc:
            if tc[1] > (y0 + y1) / 2:
                box(el, 'FAB_TAUPE', x0, y0, 420, x1, y0 + 120, z[1])
            else:
                box(el, 'FAB_TAUPE', x0, y1 - 120, 420, x1, y1, z[1])
        else:
            box(el, 'FAB_TAUPE', x0, y0, 420, x0 + 120, y1, z[1])
        for px, py in ((x0 + 30, y0 + 30), (x1 - 60, y0 + 30), (x0 + 30, y1 - 60), (x1 - 60, y1 - 60)):
            box(el, 'BLACK', px, py, 0, px + 30, py + 30, 300)
    elif k == 'round':
        c = it['c']
        cyl(el, 'MARBLE' if it.get('pal') == 'marble' else 'OAK', c[0], c[1], it['r'], z[1] - 25, z[1], 48)
        cyl(el, 'BLACK', c[0], c[1], 20, 30, z[1] - 25, 12)
        cyl(el, 'BLACK', c[0], c[1], 160, 0, 30, 24)
    elif k == 'box':
        x0, y0, x1, y1 = r
        el.name = it.get('name') or 'Короб инсталляции (ГКЛВ)'
        el.objtype = 'Короб инсталляции / коммуникаций (ГКЛВ)'
        tile = next((mkey(c) for (r_, l_, a_, b_, z0_, z1_, c) in D.WALL_ZONES
                     if r_ == room and c != 'X' and tex_of(c) == 'tiles' and mkey(c) in M.MATS), 'GKL')
        box(el, tile, x0, y0, 0, x1, y1, z[1] - 10)             # ГКЛВ, облицовка плиткой
        box(el, tile, x0 - 1, y0 - 1, z[1] - 10, x1 + 1, y1 + 1, z[1])           # полка — плитка
        el.props['Отметка полки'] = f'+{z[1]:.0f}'
    elif k == 'wc':
        to_model = DP.to_model
        wall, face, axis = it['wall'], it['face'], it['axis']
        off = 10      # облицовка короба (плитка)
        pts = [(0, -180), (190, -180)] + [(190 + 350 * math.cos(math.radians(a)), 180 * math.sin(math.radians(a)))
                                          for a in range(-75, 76, 15)] + [(190, 180), (0, 180)]
        poly = [to_model(wall, face, axis, a + off, b) for a, b in pts]
        inner = [to_model(wall, face, axis, a * 0.8 + 40 + off, b * 0.7) for a, b in pts]
        prism(el, 'CERAMIC', poly, 300, 400)
        prism(el, 'CERAMIC', inner, 230, 300)
        prism(el, 'WHITE', poly, 400, 420)
        # клавиша смыва на коробе (латунь матовая)
        p = to_model(wall, face, axis, off, -125); q = to_model(wall, face, axis, off + 10, 125)
        box(el, 'BRASS', p[0], p[1], 1000, q[0], q[1], 1160)
    elif k == 'vanity':
        sd, face, ax_ = it['wall'], it['face'], it['axis']
        dep, wd = it.get('depth', 460), it.get('width', 600)
        vm = fmat(it.get('mat'), 'WALNUT')
        lbox(el, vm, sd, face, 0, dep - 18, ax_ - wd / 2, ax_ + wd / 2, z[0], z[1] - 20)
        zm = (z[0] + z[1] - 20) / 2
        lbox(el, vm, sd, face, dep - 18, dep, ax_ - wd / 2 + 2, ax_ + wd / 2 - 2, z[0] + 2, zm - 2)
        lbox(el, vm, sd, face, dep - 18, dep, ax_ - wd / 2 + 2, ax_ + wd / 2 - 2, zm + 2, z[1] - 22)
        for zz in (zm - 60, z[1] - 80):
            lbox(el, 'BRASS', sd, face, dep, dep + 22, ax_ - 70, ax_ + 70, zz, zz + 12)
        lbox(el, 'CERAMIC', sd, face, 0, dep + 10, ax_ - wd / 2 - 5, ax_ + wd / 2 + 5, z[1] - 20, z[1])
        lbox(el, 'WHITE', sd, face, 120, dep - 60, ax_ - wd / 2 + 120, ax_ + wd / 2 - 120, z[1] - 1, z[1] + 1)
        lbox(el, 'NICKEL', sd, face, 40, 80, ax_ - 20, ax_ + 20, z[1], z[1] + 230)
        lbox(el, 'NICKEL', sd, face, 40, 230, ax_ - 14, ax_ + 14, z[1] + 200, z[1] + 230)
        lbox(el, 'NICKEL', sd, face, 30, 90, ax_ + 50, ax_ + 64, z[1], z[1] + 90)
    elif k == 'mini_basin':
        sd, face, ax_ = it['wall'], it['face'], it['axis']
        dep, wd = it.get('depth', 250), it.get('width', 400)
        lbox(el, 'CERAMIC', sd, face, 0, dep, ax_ - wd / 2, ax_ + wd / 2, z[0], z[1])
        lbox(el, 'BLACK', sd, face, 0, 150, ax_ - 15, ax_ + 15, z[1] + 80, z[1] + 110)
    elif k == 'mirror':
        fr0 = _front_dir(r, room)
        code = _zone_code_at(room, ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), (z[0] + z[1]) / 2)
        t0 = fin_t(code) if code and code != 'X' else 0
        sh = {'+x': (t0, 0), '-x': (-t0, 0), '+y': (0, t0), '-y': (0, -t0)}[fr0]
        r = (r[0] + sh[0], r[1] + sh[1], r[2] + sh[0], r[3] + sh[1])          # зеркало — на чистовой поверхности
        box(el, 'MIRROR', *r[:2], z[0], *r[2:], z[1])
        if D.ROOM[room].get('zone') != 'wet':          # латунная рамка декоративных зеркал
            x0, y0, x1, y1 = r
            if (x1 - x0) < (y1 - y0):
                xf = x1 if _front_dir(r, room) == '+x' else x0
                xa, xb = (x0, x1 + 8) if xf == x1 else (x0 - 8, x1)
                box(el, 'BRASS', xa, y0 - 25, z[0] - 25, xb, y0, z[1] + 25)
                box(el, 'BRASS', xa, y1, z[0] - 25, xb, y1 + 25, z[1] + 25)
                box(el, 'BRASS', xa, y0, z[0] - 25, xb, y1, z[0])
                box(el, 'BRASS', xa, y0, z[1], xb, y1, z[1] + 25)
            else:
                ya, yb = (y0, y1 + 8) if _front_dir(r, room) == '+y' else (y0 - 8, y1)
                box(el, 'BRASS', x0 - 25, ya, z[0] - 25, x0, yb, z[1] + 25)
                box(el, 'BRASS', x1, ya, z[0] - 25, x1 + 25, yb, z[1] + 25)
                box(el, 'BRASS', x0, ya, z[0] - 25, x1, yb, z[0])
                box(el, 'BRASS', x0, ya, z[1], x1, yb, z[1] + 25)
        else:                                            # зеркало санузла — LED-подсветка по контуру (сзади)
            x0, y0, x1, y1 = r
            if (x1 - x0) < (y1 - y0):
                box(el, 'LED', x0, y0 + 30, z[0] + 30, x1, y0 + 34, z[1] - 30)
                box(el, 'LED', x0, y1 - 34, z[0] + 30, x1, y1 - 30, z[1] - 30)
    elif k == 'mirror_oval' and (r[3] - r[1]) < (r[2] - r[0]):      # зеркало на стене постоянного y — упрощённо
        box(el, 'MIRROR', *r[:2], z[0], *r[2:], z[1])
    elif k == 'mirror_oval':
        x0, y0, x1, y1 = r
        cyc, czc = (y0 + y1) / 2, (z[0] + z[1]) / 2
        ry, rz = (y1 - y0) / 2, (z[1] - z[0]) / 2
        # вертикальный стадион в плоскости стены x=0..15
        pts = []
        rr = ry
        for a in range(0, 181, 15):
            pts.append((cyc + rr * math.cos(math.radians(a)), czc + (rz - rr) + rr * math.sin(math.radians(a))))
        for a in range(180, 361, 15):
            pts.append((cyc + rr * math.cos(math.radians(a)), czc - (rz - rr) + rr * math.sin(math.radians(a))))
        _xprism(el, 'MIRROR', pts, x0, x1)
        _xprism(el, 'LED', [(y, zz) for y, zz in _offset_poly(pts, 8)], x0, x0 + 5)
    elif k == 'wm_cab':
        fr = _front_dir(r, room)
        m = fmat(it.get('mat'), 'WALNUT')
        _carcass(el, m, r, fr, 0, z[1])
        nd = 2 if (r[2] - r[0] if fr in ('+y', '-y') else r[3] - r[1]) > 800 else 1
        _panels(el, m, r, fr, 0, z[1] - 3, nd)
        if it.get('mat') not in ('oak', 'walnut'):
            _panel_frames(el, m, r, fr, nd, [(150, 1750), (1830, z[1] - 120)])
        _panel_handles(el, r, fr, nd, 1000, 1300, pairs=True)
    elif k == 'towel':
        sd = side_of(r, room)
        face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
        w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
        lbox(el, 'NICKEL', sd, face, 40, 70, w0, w0 + 25, z[0], z[1])
        lbox(el, 'NICKEL', sd, face, 40, 70, w1 - 25, w1, z[0], z[1])
        for ww in (w0 + 12, w1 - 12):
            for zz in (z[0] + 80, z[1] - 80):
                lbox(el, 'NICKEL', sd, face, 0, 40, ww - 8, ww + 8, zz - 8, zz + 8)
        zz = z[0] + 60
        while zz < z[1] - 30:
            lbox(el, 'NICKEL', sd, face, 45, 65, w0 + 25, w1 - 25, zz, zz + 20)
            zz += 100
    elif k == 'glass' and (r[2] - r[0]) < (r[3] - r[1]):     # стекло вдоль y
        x0, y0, x1, y1 = r
        box(el, 'GLASS_SH', x0 + 3, y0 + 12, z[0], x1 - 3, y1, z[1])
        box(el, 'NICKEL', x0 - 5, y0, z[0], x1 + 5, y0 + 15, z[1])          # пристенный профиль
        box(el, 'NICKEL', x0 - 3, y0 + 12, z[0], x1 + 3, y1, z[0] + 12)     # нижний профиль
        el.props['Описание'] = 'Стекло закалённое 8 мм, пристенный и нижний профиль, сатин-никель'
    elif k == 'glass':
        x0, y0, x1, y1 = r
        box(el, 'GLASS_SH', x0 + 10, y0 + 4, z[0], x1, y1 - 4, z[1])
        box(el, 'BLACK', x0, y0, z[0], x0 + 10, y1, z[1])
        box(el, 'BLACK', x0, y0, z[1] - 20, x1, y1, z[1])
    elif k == 'drain':
        x0, y0, x1, y1 = r
        box(el, 'NICKEL', x0, y0, zf - 1, x1, y1, zf + 0.8)
        box(el, 'STEEL', x0 + 15, y0 + 15, zf - 60, x1 - 15, y1 - 15, zf - 1)      # корпус трапа
        el.name = 'Трап линейный пристенный ' + f'{max(x1 - x0, y1 - y0):.0f}' + ' (решётка сатин / под плитку)'
    elif k == 'bath':
        _bath(el, it, r, z, room)
    elif k == 'hatch_wall':
        x0, y0, x1, y1 = r
        code = _zone_code_at(room, ((x0 + x1) / 2, (y0 + y1) / 2), (z[0] + z[1]) / 2)
        tile = mkey(code) if code and mkey(code) in M.MATS else 'C1'
        if (x1 - x0) > (y1 - y0):
            box(el, tile, x0 + 4, y0, z[0] + 4, x1 - 4, y1 + 1, z[1] - 4)
            for a_, b_, za, zb in ((x0, x0 + 4, z[0], z[1]), (x1 - 4, x1, z[0], z[1]), (x0, x1, z[0], z[0] + 4), (x0, x1, z[1] - 4, z[1])):
                box(el, 'STEEL', a_, y0, za, b_, y1 + 1.5, zb)
        else:
            box(el, tile, x0, y0 + 4, z[0] + 4, x1 + 1, y1 - 4, z[1] - 4)
        el.name = 'Люк-невидимка ' + f'{max(x1 - x0, y1 - y0):.0f}×{z[1] - z[0]:.0f}' + ' под плитку (нажимной)'
        el.props['Назначение'] = 'доступ к стоякам, кранам и счётчикам в шахте'
    elif k == 'shower':
        cx, cy = it['c']
        sd = ({(1, 0): 'W', (-1, 0): 'E', (0, 1): 'S', (0, -1): 'N'}.get(tuple(it['n'])) if it.get('n')
              else _point_side(it['c'], room))
        face = cx if sd in ('W', 'E') else cy
        w = cy if sd in ('W', 'E') else cx
        zt = z[1] if isinstance(z, tuple) else 2150
        lbox(el, 'NICKEL', sd, face, 0, 60, w - 150, w + 150, 1060, 1140)          # термостат
        for ww in (w - 110, w + 110):
            lbox(el, 'NICKEL', sd, face, 60, 75, ww - 22, ww + 22, 1078, 1122)     # рукоятки
        lbox(el, 'NICKEL', sd, face, 30, 54, w - 12, w + 12, 1140, zt)
        lbox(el, 'NICKEL', sd, face, 30, 330, w - 12, w + 12, zt - 20, zt)
        nx, ny = SIDE_N[sd]
        cyl(el, 'NICKEL', cx + nx * 330, cy + ny * 330, 125, zt - 30, zt - 18, 32)
        # ручная лейка на держателе
        lbox(el, 'NICKEL', sd, face, 54, 90, w - 18, w + 18, 1500, 1540)
        tube(el, 'NICKEL', (cx + nx * 75, cy + ny * 75, 1380), (cx + nx * 75, cy + ny * 75, 1620), 18)
        el.name = 'Душевая система с термостатом, верхний душ Ø250, ручная лейка (сатин-никель)'
    elif k == 'wallshelf':
        x0, y0, x1, y1 = r
        m = {'walnut': 'WALNUT', 'oak': 'OAK'}.get(it.get('mat'), 'BLACK' if it.get('shelves') else 'WALNUT')
        box(el, m, x0, y0, z[0], x1, y1, z[1])
        if it.get('shelves'):
            box(el, m, x0, y0, z[0] + 250, x1, y1, z[1] + 250)
    elif k == 'bench':
        x0, y0, x1, y1 = r
        m = fmat(it.get('mat'), 'WALNUT')
        fab = fabric_mat(it['fabric_col']) if it.get('fabric_col') else 'FAB_OLIVE'
        for px, py in ((x0 + 20, y0 + 20), (x1 - 60, y0 + 20), (x0 + 20, y1 - 60), (x1 - 60, y1 - 60)):
            box(el, m, px, py, 0, px + 40, py + 40, 340)
        box(el, m, x0, y0, 340, x1, y1, 380)
        box(el, m, x0 + 40, y0 + 40, 120, x1 - 40, y1 - 40, 140)
        box(el, fab, x0 + 10, y0 + 10, 380, x1 - 10, y1 - 10, 450)


def _point_side(p, room):
    """Сторона стены (W/E/S/N), на которой лежит точка p помещения (внутренняя нормаль — SIDE_N)."""
    poly = D.ROOMS[room]['poly']
    best = None
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if xa == xb and min(ya, yb) - 1 <= p[1] <= max(ya, yb) + 1:
            d = abs(p[0] - xa)
            sd = 'W' if EL_inside(poly, (xa + 30, p[1])) else 'E'
        elif ya == yb and min(xa, xb) - 1 <= p[0] <= max(xa, xb) + 1:
            d = abs(p[1] - ya)
            sd = 'S' if EL_inside(poly, (p[0], ya + 30)) else 'N'
        else:
            continue
        if best is None or d < best[0]:
            best = (d, sd)
    return best[1] if best else 'S'


def _offset_poly(pts, d):
    cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
    out = []
    for x, y in pts:
        L = math.hypot(x - cx, y - cy) or 1
        out.append((x + (x - cx) / L * d, y + (y - cy) / L * d))
    return out


def _xprism(el, m, pts_yz, x0, x1):
    """Призма с контуром в плоскости (y, z), выдавленная вдоль x."""
    from ifc.m3d import ear_clip, default_uv
    a = 0
    for (ya, za), (yb, zb) in zip(pts_yz, pts_yz[1:] + pts_yz[:1]):
        a += ya * zb - yb * za
    if a < 0:
        pts_yz = pts_yz[::-1]
    tris = ear_clip(pts_yz)
    P = el.part(m)
    for (i, j, k) in tris:
        A = [(x1, pts_yz[i][0], pts_yz[i][1]), (x1, pts_yz[j][0], pts_yz[j][1]), (x1, pts_yz[k][0], pts_yz[k][1])]
        P.face(A, [default_uv(m, (1, 0, 0), p, None) for p in A])
        B = [(x0, pts_yz[k][0], pts_yz[k][1]), (x0, pts_yz[j][0], pts_yz[j][1]), (x0, pts_yz[i][0], pts_yz[i][1])]
        P.face(B, [default_uv(m, (-1, 0, 0), p, None) for p in B])
    for (ya, za), (yb, zb) in zip(pts_yz, pts_yz[1:] + pts_yz[:1]):
        Q = [(x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za)]
        P.face(Q, [(0, 0), (1, 0), (1, 1), (0, 1)])


def appliances(S):
    """Бытовая техника отдельными элементами (для ведомостей в BIM): из модулей кухни, колонн и шкафа СМ."""
    for it in D.ITEMS:
        r = D.item_rect(it)
        room = it['room']
        if it['kind'] == 'kitchen_run':
            sd = it.get('side', 'W')
            face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
            for a, b, kind in it['modules']:
                if kind == 'hob':
                    el = S.add(Elem('IfcElectricAppliance', 'Варочная панель 60 см', room=room, predefined='ELECTRICCOOKER',
                                    props={'Помещение': room}))
                    DT.lrbox(el, 'BLACKGLASS', sd, face, 45, 565, a + 20, b - 20, 900, 906, 4, 3)       # стеклокерамика, фаска
                    for (uu, ww, rr) in ((190, a + 165, 105), (190, b - 165, 80), (410, a + 165, 80), (410, b - 165, 105)):
                        bx_, by_ = DT.lw(sd, face, uu, ww)
                        HP.ring(el, 'GRAPHITE', (bx_, by_, 906), rr - 2.5, rr, 0, 0.4, 72)           # зоны нагрева
                        HP.ring(el, 'GRAPHITE', (bx_, by_, 906), rr * 0.55 - 1.5, rr * 0.55, 0, 0.4, 48)
                        for k_ in range(4):                                                          # крестики-метки
                            ang = math.pi / 4 + k_ * math.pi / 2
                            HP.rbox(el, 'GRAPHITE', bx_ + math.cos(ang) * rr * 0.78 - 1, by_ + math.sin(ang) * rr * 0.78 - 1,
                                    906, bx_ + math.cos(ang) * rr * 0.78 + 1, by_ + math.sin(ang) * rr * 0.78 + 1, 906.4, 0, 1)
                    # сенсорная панель: слайдер и кнопки
                    DT.lrbox(el, 'GRAPHITE', sd, face, 520, 528, a + 150, b - 150, 906, 906.4, 0, 1)
                    for ww in (a + 80, a + 110, b - 110, b - 80):
                        bx_, by_ = DT.lw(sd, face, 524, ww)
                        HP.ring(el, 'GRAPHITE', (bx_, by_, 906), 6, 8, 0, 0.4, 24)
                    el.name = 'Варочная панель индукционная 60 см, стеклокерамика с фаской, сенсорное управление'
                    el2 = S.add(Elem('IfcElectricAppliance', 'Духовой шкаф встраиваемый 60 см (под варочной панелью)', room=room,
                                     predefined='ELECTRICCOOKER', props={'Помещение': room}))
                    dep_ = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
                    DT.lrbox(el2, 'BLACKGLASS', sd, face, dep_ - 22, dep_, a + 4, b - 4, 152, 748, 3, 3)
                    DT.lrbox(el2, 'STEEL', sd, face, dep_ - 22, dep_ + 1, a + 4, b - 4, 690, 748, 2, 2)
                    eu, ew, _ = DT.wall_frame(sd)
                    hx_, hy_ = DT.lw(sd, face, dep_, (a + b) / 2)
                    DT.bar_handle(el2, 'STEEL', (hx_, hy_, 660), ew, eu, L=b - a - 120, h=40, r=8)
                    for ww in (a + 70, b - 70):                                                         # ручки-переключатели
                        kx, ky = DT.lw(sd, face, dep_ + 1, ww)
                        DT.knob(el2, 'STEEL', (kx, ky, 719), eu, 34)
                    DT.lrbox(el2, 'BLACKGLASS', sd, face, dep_ + 1, dep_ + 3, (a + b) / 2 - 60, (a + b) / 2 + 60, 705, 733, 2, 2)  # дисплей
                    el2.name = 'Духовой шкаф встраиваемый 60 см (под варочной панелью), стекло, ручка — сталь'
                elif kind == 'dw':
                    el = S.add(Elem('IfcElectricAppliance', 'Посудомоечная машина встраиваемая 60 см', room=room,
                                    predefined='DISHWASHER', props={'Помещение': room}))
                    lbox(el, 'STEEL', sd, face, 20, 560, a + 20, b - 20, 110, 860)
        elif it['kind'] == 'column':
            sd = side_of(r, room)
            face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
            dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
            w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
            for z0, z1, lab in it.get('inner', []):
                if lab == 'холодильник':
                    el = S.add(Elem('IfcElectricAppliance', 'Холодильник встраиваемый (в колонне)', room=room,
                                    predefined='REFRIGERATOR', props={'Помещение': room}))
                    lbox(el, 'WHITE', sd, face, 30, dep - 50, w0 + 30, w1 - 30, z0 + 10, z1 - 10)
                else:
                    nm = 'Духовой шкаф встраиваемый 60 см' if lab == 'ДШ' else 'Микроволновая печь встраиваемая'
                    el = S.add(Elem('IfcElectricAppliance', nm, room=room, predefined='ELECTRICCOOKER' if lab == 'ДШ' else 'MICROWAVE',
                                    props={'Помещение': room}))
                    lbox(el, 'BLACKGLASS', sd, face, dep - 20, dep + 2, w0 + 3, w1 - 3, z0, z1 - 3)
                    lbox(el, 'STEEL', sd, face, dep + 2, dep + 24, w0 + 60, w1 - 60, z1 - 90, z1 - 75)
        elif it['kind'] == 'wm_cab':
            z = it.get('z', (0, 900))
            x0, y0, x1, y1 = r
            el = S.add(Elem('IfcElectricAppliance', 'Стиральная машина 60 см', room=room, predefined='WASHINGMACHINE',
                            props={'Помещение': room}))
            box(el, 'WHITE', x0 + 30, y0 + 30, 30, x1 - 30, y1 - 30, 880)
            if z[1] > 1600:
                el = S.add(Elem('IfcElectricAppliance', 'Сушильная машина 60 см', room=room, predefined='TUMBLEDRYER',
                                props={'Помещение': room}))
                box(el, 'WHITE', x0 + 30, y0 + 30, 900, x1 - 30, y1 - 30, 1750)


def curtains(S):
    """Шторы у окон помещений: ROOM['curtains'] = 'niche' (на скрытом карнизе в нише) | 'blind' (рулонные)."""
    for o in OPEN3D:
        k, ax, c0, c1, a, b, z0, z1 = o
        if OKIND.get(k) not in ('window', 'bdoor'):
            continue
        inner, frame = _inner_face(o)
        sg = -1 if frame > inner else 1                 # от стены внутрь
        m = (a + b) / 2
        room = next((r_ for r_ in D.ROOMS if indoor(r_) and EL_inside(D.ROOMS[r_]['poly'],
                     (m, inner + sg * 60) if ax == 'y' else (inner + sg * 60, m))), None)
        if not room:
            continue
        mode = D.ROOM[room].get('curtains')
        if mode == 'niche':
            zc = D.ROOM[room]['ceil'] or 2700
            cpos = inner + sg * 110
            el = S.add(Elem('IfcFurniture', 'Шторы (лён, на скрытом карнизе)', room=room, predefined='USERDEFINED', objtype='Шторы',
                            props={'Помещение': room}))
            def PP(aa, cc):
                return (aa, cc) if ax == 'y' else (cc, aa)
            for s0, s1 in ((a - 650, a + 250), (b - 250, b + 650)):
                HP.drape(el, 'LINEN_SHEER', PP(s0, cpos), PP(s1, cpos), 15, zc + 140, depth=70, nz=8)
                HP.drape(el, 'FAB_LINEN', PP(s0, cpos + sg * 60), PP(s0 + (s1 - s0) * 0.45, cpos + sg * 60), 10, zc + 140,
                         depth=90, nz=8) if s0 < a else HP.drape(el, 'FAB_LINEN', PP(s1 - (s1 - s0) * 0.45, cpos + sg * 60),
                                                                 PP(s1, cpos + sg * 60), 10, zc + 140, depth=90, nz=8)
        elif mode == 'blind' and OKIND.get(k) == 'window':
            el = S.add(Elem('IfcFurniture', 'Рулонная штора', room=room, predefined='USERDEFINED', objtype='Рулонная штора',
                            props={'Помещение': room}))
            pl = frame - sg * 60
            box(el, 'BLIND', *_obox(ax, a + 70, b - 70, pl, pl - sg * 1.5, z0 + 850, z1 - 70))
            HP.rbox(el, 'WHITE', *_obox(ax, a + 60, b - 60, pl + sg * 10, pl - sg * 45, z1 - 72, z1 - 10), 10, 4)
            q0 = _obox(ax, a + 70, b - 70, pl - sg * 0.75, pl - sg * 0.75, z0 + 850, z0 + 850)
            HP.pipe(el, 'WHITE', [(q0[0], q0[1], z0 + 845), (q0[3], q0[4], z0 + 845)], 9, n=16)


# ------------------------------------------------------------ светильники
def lights(S):
    for L in D.LIGHTS:
        room = L['room']
        zc = zc_of(room)
        k = L['kind']
        grp = D.gcode(L['g'])
        props = {'Помещение': room, 'Группа': grp, 'Тип': k}
        pre = 'POINTSOURCE' if k in ('spot', 'spot44', 'spot65', 'pend', 'sconce', 'wall44', 'ceil') else 'DIRECTIONSOURCE'
        if L.get('note'):
            props['Примечание'] = L['note']
        if L.get('z') is not None:
            props['Отметка, мм'] = L['z']
        nm = {'spot': 'Светильник встраиваемый поворотный', 'spot44': 'Светильник встраиваемый IP44', 'spot65': 'Светильник встраиваемый IP65',
              'pend': 'Подвесной светильник «кольцо» Ø600', 'track': 'Магнитный трек встраиваемый со спотами', 'led': 'Светодиодная лента',
              'linear': 'Светильник линейный накладной', 'sconce': 'Бра настенное', 'wall44': 'Светильник настенный IP44',
              'fan': 'Вентилятор вытяжной', 'mirrorled': 'Подсветка зеркала',
              'ceil': 'Светильник накладной потолочный Ø400 (опал, латунь)'}[k]
        if k == 'mirrorled':
            continue
        cls = 'IfcLightFixture'
        if k == 'fan':
            cls, pre = 'IfcFan', 'PROPELLORAXIAL'
        el = Elem(cls, f'{nm} ({grp})', room=room, predefined=pre, props=props)
        if k != 'fan' and DT.light(el, L, k, zc):
            S.add(el)
            continue
        if k == 'fan':
            x, y = L['p']
            HP.rbox(el, 'WHITE', x - 100, y - 100, zc - 10, x + 100, y + 100, zc, 4, 3)
            for i in range(6):
                HP.rbox(el, 'GRAPHITE', x - 70, y - 60 + i * 24, zc - 11, x + 70, y - 52 + i * 24, zc - 10, 1, 2)
            S.add(el)
            continue
        if k in ('spot', 'spot44', 'spot65'):
            x, y = L['p']
            cyl(el, 'BLACK' if k == 'spot' else 'WHITE', x, y, 42, zc - 25, zc, 16)
            cyl(el, 'LED', x, y, 25, zc - 27, zc - 25, 12)
        elif k == 'fan':
            x, y = L['p']
            box(el, 'WHITE', x - 100, y - 100, zc - 8, x + 100, y + 100, zc)
        elif k == 'ceil':
            x, y = L['p']
            cyl(el, 'BRASS', x, y, 200, zc - 20, zc, 32)
            cyl(el, 'OPAL', x, y, 190, zc - 70, zc - 20, 32)
            sphere(el, 'OPAL', (x, y, zc - 70), 190, 4, 32, sz=0.18)
        elif k == 'pend' and _pend_style(L) != 'ring':
            _pendant(el, L, zc, _pend_style(L))
        elif k == 'pend':
            x, y = L['p']
            zl = L['z']
            _ring(el, 'BLACK', x, y, 300, 18, zl, zl + 25)
            _ring(el, 'LED', x, y, 296, 8, zl - 1, zl)
            for ang in (0, 120, 240):
                px, py = x + 290 * math.cos(math.radians(ang)), y + 290 * math.sin(math.radians(ang))
                box(el, 'BLACK', px - 1, py - 1, zl + 25, px + 1, py + 1, zc)
            cyl(el, 'BLACK', x, y, 50, zc - 15, zc, 16)
        elif k == 'track':
            (xa, ya), (xb, yb) = L['a'], L['b']
            box(el, 'BLACK', xa - 18, min(ya, yb), zc - 5, xa + 18, max(ya, yb), zc)
            for i in range(4):
                yy = min(ya, yb) + (i + 0.5) * abs(yb - ya) / 4
                cyl(el, 'BLACK', xa, yy, 28, zc - 120, zc - 5, 12)
        elif k == 'led':
            (xa, ya), (xb, yb) = L['a'], L['b']
            z = L.get('z', zc)
            el.props['Длина, м'] = round(math.hypot(xb - xa, yb - ya) / 1000, 2)
            if z >= zc - 5:      # лента в световой нише / нише карниза — под дном ниши (+150 над потолком)
                el.props['Расположение'] = 'в нише потолка'
                seg_prism(el, 'LED', (xa, ya), (xb, yb), 12, zc + 130, zc + 145, off=-6)
            else:
                seg_prism(el, 'STEEL', (xa, ya), (xb, yb), 16, z - 12, z, off=-8)
                seg_prism(el, 'LED', (xa, ya), (xb, yb), 10, z - 13, z - 12, off=-5)
        elif k == 'linear':
            (xa, ya), (xb, yb) = L['a'], L['b']
            seg_prism(el, 'WHITE', (xa, ya), (xb, yb), 50, zc - 60, zc, off=-25)
            seg_prism(el, 'LED', (xa, ya), (xb, yb), 40, zc - 61, zc - 60, off=-20)
        elif k in ('sconce', 'wall44'):
            x, y = L['p']
            z = L.get('z', 1500)
            sd = _point_side(L['p'], room)
            if L.get('style') == 'bar':
                lbox(el, 'BLACK', sd, x if sd in ('W', 'E') else y, 0, 25, (y if sd in ('W', 'E') else x) - 20,
                     (y if sd in ('W', 'E') else x) + 20, 1500, 2000)
                lbox(el, 'LED', sd, x if sd in ('W', 'E') else y, 25, 27, (y if sd in ('W', 'E') else x) - 15,
                     (y if sd in ('W', 'E') else x) + 15, 1505, 1995)
            elif k == 'wall44':
                lbox(el, 'WHITE', sd, x if sd in ('W', 'E') else y, 0, 90, (y if sd in ('W', 'E') else x) - 100,
                     (y if sd in ('W', 'E') else x) + 100, z - 60, z + 60)
            else:
                face = x if sd in ('W', 'E') else y
                w = y if sd in ('W', 'E') else x
                lbox(el, 'BRASS', sd, face, 0, 12, w - 60, w + 60, z - 90, z + 30)
                lbox(el, 'BRASS', sd, face, 0, 200, w - 8, w + 8, z - 8, z + 8)
                nx, ny = SIDE_N[sd]
                tube(el, 'FAB_LINEN', (x + nx * 200, y + ny * 200, z - 60), (x + nx * 200, y + ny * 200, z + 110), 95, 24)
                cyl(el, 'BRASS', x + nx * 200, y + ny * 200, 20, z - 10, z + 60, 12)
        if el.parts:
            S.add(el)


def _ring(el, m, cx, cy, R, w, z0, z1, n=48):
    P = el.part(m)
    ro, ri = R, R - w
    for i in range(n):
        a0 = 2 * math.pi * i / n; a1 = 2 * math.pi * (i + 1) / n
        o0 = (cx + ro * math.cos(a0), cy + ro * math.sin(a0)); o1 = (cx + ro * math.cos(a1), cy + ro * math.sin(a1))
        i0 = (cx + ri * math.cos(a0), cy + ri * math.sin(a0)); i1 = (cx + ri * math.cos(a1), cy + ri * math.sin(a1))
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        P.face([(o0[0], o0[1], z0), (o1[0], o1[1], z0), (o1[0], o1[1], z1), (o0[0], o0[1], z1)], uv)
        P.face([(i1[0], i1[1], z0), (i0[0], i0[1], z0), (i0[0], i0[1], z1), (i1[0], i1[1], z1)], uv)
        P.face([(i0[0], i0[1], z1), (o0[0], o0[1], z1), (o1[0], o1[1], z1), (i1[0], i1[1], z1)], uv)
        P.face([(i1[0], i1[1], z0), (o1[0], o1[1], z0), (o0[0], o0[1], z0), (i0[0], i0[1], z0)], uv)


# ------------------------------------------------------------ ЭУИ
POST_W = {'r1': 1, 'r1w': 1, 'r2': 2, 'r2u': 2, 'r2w': 2, 'tvblock': 4, 'medblock': 3, 'deskblock': 4,
          'v1': 1, 'v2': 1, 'v1p': 1, 'v2p': 1, 'tr': 1, 'pow': 1, 'out': 1, 'int': 1}


def _finish_depth(room, lab, W, s, z):
    """Толщина отделки (и короба) в точке стены — изделие ставится на чистую поверхность."""
    bx = _box_in_front(room, W, s - 1, s + 1, z=z)
    extra = bx[2] if bx else 0
    for (r, l2, s0, s1, z0, z1, code) in D.WALL_ZONES:
        if r == room and l2 == lab and code != 'X' and s0 <= s <= s1 and z0 <= z <= z1:
            return fin_t(code) + extra
    return fin_t(D.WALL_DEFAULT.get(room) or getattr(D, 'DOOR_LEAF_FINISH', 'С1')) + extra


def electrics(S):
    for P in D.POINTS:
        k = P['kind']
        if k in ('shk', 'ssh'):
            _board(S, P)
            continue
        room = P['room']
        W = None
        for lab, pL, pR in D.RWALLS.get(room, []):
            Wc = EL.wall_geom(room, lab)
            s, d = EL.proj(Wc, P['p'])
            if abs(d) < 8 and -5 <= s <= Wc['L'] + 5:
                W, sP, labP = Wc, s, lab
                break
        if W is None:        # балкон: развёрток нет — стена по направлению n
            nx, ny = P['n']
            W = dict(pL=P['p'], d=(-ny, nx), n=(nx, ny), L=1)      # n = (d[1], −d[0])
            sP, labP, d0 = 0.0, None, 3
        z = P['z']
        n = POST_W.get(k, 1)
        w = 80 + (n - 1) * 71
        if labP is not None:
            d0 = _finish_depth(room, labP, W, sP, z + 40)
        if k.startswith('v'):
            cls, pre = 'IfcSwitchingDevice', 'TOGGLESWITCH'
        elif k == 'tr':
            cls, pre = 'IfcUnitaryControlElement', 'THERMOSTAT'
        elif k == 'int':
            cls, pre = 'IfcCommunicationsAppliance', 'USERDEFINED'
        elif k == 'out':
            cls, pre = 'IfcOutlet', 'USERDEFINED'
        elif k in ('tvblock', 'medblock', 'deskblock'):
            cls, pre = 'IfcOutlet', 'DATAOUTLET'
        else:
            cls, pre = 'IfcOutlet', 'POWEROUTLET'
        nm = {'v1': 'Выключатель одноклавишный', 'v2': 'Выключатель двухклавишный', 'v1p': 'Выключатель проходной',
              'v2p': 'Выключатель проходной двухклавишный', 'tr': 'Терморегулятор тёплого пола', 'r1': 'Розетка',
              'r2': 'Розетка двойная', 'r2u': 'Розетка двойная с USB', 'r1w': 'Розетка IP44', 'r2w': 'Розетка двойная IP44',
              'tvblock': 'Блок 2Р+TV+RJ45', 'medblock': 'Блок 2Р+RJ45', 'deskblock': 'Блок 3Р+RJ45', 'pow': 'Силовой вывод 32 А',
              'out': 'Вывод кабеля', 'int': 'Домофон'}.get(k, k)
        props = {'Помещение': room, 'Высота (низ рамки), мм': z}
        if P.get('g'):
            props['Группы'] = ', '.join(D.gcode(g) for g in P['g'])
        if P.get('note'):
            props['Примечание'] = P['note']
        el = S.add(Elem(cls, f'{nm} +{z}', room=room, predefined=pre, props=props))
        m = 'WHITE' if k in ('tr', 'int') else 'GRAPHITE'
        _eui(el, k, m, W, sP, d0, z, n, w)


# ------------------------------------------------------------ помещения
def spaces(S):
    for room, info in D.ROOM.items():
        el = S.add(Elem('IfcSpace', room, room=room, predefined='INTERNAL' if indoor(room) else 'EXTERNAL',
                        props={'Наименование': info['name'], 'Площадь, м²': round(D.AREA[room], 1),
                               'Пол': info['floor'], 'Отметка пола': zf_of(room), 'Высота до потолка': zc_of(room) - zf_of(room)}))
        el.long_name = info['name']
        el.space = True
        el.extr.append((D.ROOMS[room]['poly'], zf_of(room), zc_of(room), 'SPACE'))



# ------------------------------------------------------------ детализация: вспомогательные
def _zone_code_at(room, p, z):
    """Код отделки стены помещения в точке плана p на отметке z (по WALL_ZONES, иначе — по умолчанию)."""
    for lab, pL, pR in D.RWALLS.get(room, []):
        W = EL.wall_geom(room, lab)
        s_, d_ = EL.proj(W, p)
        if abs(d_) < 25 and -5 <= s_ <= W['L'] + 5:
            for (r, l2, s0, s1, z0, z1, code) in D.WALL_ZONES:
                if r == room and l2 == lab and s0 <= s_ <= s1 and z0 <= z <= z1:
                    return code
            return D.WALL_DEFAULT.get(room)
    return D.WALL_DEFAULT.get(room)


def _left_inside(a, b, poly):
    """Точка слева от отрезка a–b (на 70 мм) внутри poly."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1
    m = ((a[0] + b[0]) / 2 - dy / L * 70, (a[1] + b[1]) / 2 + dx / L * 70)
    return EL_inside(poly, m)


def _panel_rects(r, front, n, gap=3):
    """Полосы дверей фасада: [(a, b)] вдоль фасада + координата плоскости фасада и знак наружу."""
    x0, y0, x1, y1 = r
    if front in ('+y', '-y'):
        lo, hi = x0, x1
        f, sg = (y1, 1) if front == '+y' else (y0, -1)
    else:
        lo, hi = y0, y1
        f, sg = (x1, 1) if front == '+x' else (x0, -1)
    w = (hi - lo - gap * (n + 1)) / n
    return [(lo + gap + i * (w + gap), lo + gap + i * (w + gap) + w) for i in range(n)], f, sg


def _fbox(el, m, front, f, sg, a, b, d0, d1, z0, z1):
    """Параллелепипед у фасада: a..b вдоль фасада, d0..d1 — наружу от плоскости f."""
    if front in ('+y', '-y'):
        box(el, m, a, f + sg * d0, z0, b, f + sg * d1, z1)
    else:
        box(el, m, f + sg * d0, a, z0, f + sg * d1, b, z1)


def _panel_frames(el, m, r, front, n, rows, inset=90, w=22, d=8):
    """Рамки-молдинги (профиль «гусёк», углы на ус) на дверях фасада."""
    spans, f, sg = _panel_rects(r, front, n)
    if front in ('+y', '-y'):
        n_out, ew = (0, sg, 0), (1, 0, 0)
        pp = (0, f, 0)
    else:
        n_out, ew = (sg, 0, 0), (0, 1, 0)
        pp = (f, 0, 0)
    DT.front_frames(el, m, pp, n_out, ew, [(a + inset, b - inset) for a, b in spans], rows, w=w, d=d)


def _panel_handles(el, r, front, n, z0, z1, pairs=False, knob=False):
    """Латунные ручки: у шкафов — скобы у притвора пар дверей, у тумб — ручки-скобы/кнопки по центру."""
    spans, f, sg = _panel_rects(r, front, n)
    if front in ('+y', '-y'):
        out, ax = np.array([0, sg, 0.0]), np.array([1.0, 0, 0])

        def P(s, zz):
            return np.array([s, f, zz])
    else:
        out, ax = np.array([sg, 0, 0.0]), np.array([0, 1.0, 0])

        def P(s, zz):
            return np.array([f, s, zz])
    zc = (z0 + z1) / 2
    for i, (a, b) in enumerate(spans):
        if knob:
            DT.bar_handle(el, 'BRASS', P((a + b) / 2, zc), ax, out, L=128, h=26, r=5)
            continue
        c = (b - 45 if i % 2 == 0 else a + 45) if (pairs and n > 1) else b - 45
        DT.bar_handle(el, 'BRASS', P(c, zc), np.array([0, 0, 1.0]), out, L=max(160, z1 - z0), h=30, r=7)


def _bed(el, it, k, r, z):
    """Кровать с мягким изголовьем, любая сторона изголовья (W/E/S/N)."""
    x0, y0, x1, y1 = r
    head = it.get('head', 'S')
    hb = z[1] if isinstance(z, tuple) and z[1] > 600 else (1100 if k == 'bed' else 900)
    fab = fabric_mat(it['fabric_col']) if it.get('fabric_col') else 'FAB_GREY'
    if head in ('W', 'E'):
        L_, sg, h0 = x1 - x0, (1 if head == 'W' else -1), (x0 if head == 'W' else x1)
        wlo, whi = y0, y1

        def B(m, u0, u1, w0, w1, za, zb):
            box(el, m, h0 + sg * u0, w0, za, h0 + sg * u1, w1, zb)
    else:
        L_, sg, h0 = y1 - y0, (1 if head == 'S' else -1), (y0 if head == 'S' else y1)
        wlo, whi = x0, x1

        def B(m, u0, u1, w0, w1, za, zb):
            box(el, m, w0, h0 + sg * u0, za, w1, h0 + sg * u1, zb)
    B('BLACK', 160, L_ - 60, wlo + 60, whi - 60, 0, 80)
    B(fab, 100, L_, wlo, whi, 80, 320)                          # царга
    B(fab, 0, 100, wlo - 20, whi + 20, 0, hb)                    # изголовье
    B(fab, 100, 160, wlo + 40, whi - 40, 320, hb - 150)          # мягкая панель изголовья
    B('MATTRESS', 120, L_ - 20, wlo + 20, whi - 20, 320, 540)
    B('FAB_LINEN', 750, L_ - 10, wlo + 5, whi - 5, 540, 575)     # покрывало
    width = whi - wlo
    npl = 2 if width > 1200 else 1
    pw = (width - 160) / npl
    for i in range(npl):
        a = wlo + 80 + i * pw
        B('MATTRESS', 150, 520, a + 10, a + pw - 10, 540, 660)
    el.props['Изголовье'] = f'мягкое, h={hb:.0f}'


def _bath(el, it, r, z, room):
    """Ванна встроенная с экраном под плитку, борт, чаша, перелив, смеситель на борту."""
    x0, y0, x1, y1 = r
    zt = z[1] if isinstance(z, tuple) else 600
    fr = _front_dir(r, room)
    ap = it.get('apron')
    am = mkey(ap) if ap and mkey(ap) in M.MATS else 'C1'
    rim = 60
    # экран под плиткой (лицевая сторона), ниша для стоп
    sx = _shrink(r, fr, 0)
    if fr in ('+y', '-y'):
        yf = y1 if fr == '+y' else y0
        sg = 1 if fr == '+y' else -1
        box(el, am, x0, yf - sg * 30, 0, x1, yf, zt - 40)
        box(el, 'STEEL', (x0 + x1) / 2 + 400, yf, 120, (x0 + x1) / 2 + 700, yf + sg * 2, 320)   # люк ревизионный
        yi0, yi1 = (y0, yf - sg * 30) if sg > 0 else (yf - sg * 30, y1)
    else:
        xf = x1 if fr == '+x' else x0
        sg = 1 if fr == '+x' else -1
        box(el, am, xf - sg * 30, y0, 0, xf, y1, zt - 40)
        yi0, yi1 = y0, y1
    # борт и чаша (санитарный акрил)
    bx0, bx1, by0, by1 = x0, x1, y0, y1
    box(el, 'ACRYL', bx0, by0, zt - 40, bx1, by0 + rim, zt)
    box(el, 'ACRYL', bx0, by1 - rim, zt - 40, bx1, by1, zt)
    box(el, 'ACRYL', bx0, by0 + rim, zt - 40, bx0 + 120, by1 - rim, zt)
    box(el, 'ACRYL', bx1 - 160, by0 + rim, zt - 40, bx1, by1 - rim, zt)
    ix0, ix1, iy0, iy1 = bx0 + 120, bx1 - 160, by0 + rim, by1 - rim
    box(el, 'ACRYL', ix0, iy0, 160, ix1, iy1, 175)                                    # дно
    for (a, b, c, d) in ((ix0, iy0, ix1, iy0 + 8), (ix0, iy1 - 8, ix1, iy1), (ix0, iy0, ix0 + 8, iy1), (ix1 - 8, iy0, ix1, iy1)):
        box(el, 'ACRYL', a, b, 175, c, d, zt - 40)
    # сифон-перелив и смеситель на борту — со стороны слива
    de = it.get('drain', 'E')
    cy = (iy0 + iy1) / 2
    if de in ('E', 'W'):
        xd = ix1 - 8 if de == 'E' else ix0 + 8
        sgd = -1 if de == 'E' else 1
        tube(el, 'NICKEL', (xd, cy, zt - 120), (xd + sgd * 6, cy, zt - 120), 36, 20)
        cyl(el, 'NICKEL', xd + sgd * 120, cy, 35, 175, 177, 20)
        xm = (bx1 - 80) if de == 'E' else (bx0 + 60)
        tube(el, 'NICKEL', (xm, cy, zt), (xm, cy, zt + 160), 18)
        tube(el, 'NICKEL', (xm, cy, zt + 160), (xm + sgd * 170, cy, zt + 160), 14)
        for dy in (-110, 110):
            tube(el, 'NICKEL', (xm, cy + dy, zt), (xm, cy + dy, zt + 70), 16)
        tube(el, 'NICKEL', (xm, cy + 190, zt), (xm, cy + 190, zt + 220), 20)          # лейка в борту
    el.name = 'Ванна встроенная 1800×800, санитарный акрил; смеситель врезной на борт, экран под плитку с люком'
    el.props['Отметка борта'] = f'+{zt:.0f}'


def _pend_style(L):
    n = (L.get('note') or '').lower()
    if 'стекл' in n:
        return 'globes'
    if 'хрустал' in n:
        return 'crystal'
    if 'многорожк' in n or 'потолочн' in n:
        return 'arms'
    return 'ring'


def _pendant(el, L, zc, style):
    x, y = L['p']
    zl = L.get('z', zc - 600)
    cyl(el, 'BRASS', x, y, 60, zc - 20, zc, 24)                     # чашка
    if style == 'globes':                                          # над столом: обод Ø800, стеклянные плафоны
        tube(el, 'BRASS', (x, y, zc - 20), (x, y, zl + 60), 6, 8)
        _ring(el, 'BRASS', x, y, 400, 14, zl + 40, zl + 60)
        for i in range(8):
            a = 2 * math.pi * i / 8
            px, py = x + 400 * math.cos(a), y + 400 * math.sin(a)
            tube(el, 'BRASS', (px, py, zl + 40), (px, py, zl), 8, 8)
            sphere(el, 'OPAL', (px, py, zl - 70), 75, 8, 16)
        for i in range(3):
            a = 2 * math.pi * i / 3
            tube(el, 'BRASS', (x, y, zl + 300), (x + 400 * math.cos(a), y + 400 * math.sin(a), zl + 60), 3, 6)
        el.name = 'Люстра подвесная над столом Ø800, стеклянные плафоны, латунь (02а)'
    elif style == 'crystal':                                       # хрустальная Ø600
        tube(el, 'BRASS', (x, y, zc - 20), (x, y, zl + 450), 8, 8)
        for k, (R, zz) in enumerate(((300, zl + 420), (230, zl + 260), (150, zl + 120))):
            _ring(el, 'BRASS', x, y, R, 10, zz - 10, zz)
            n = int(2 * math.pi * R / 45)
            for i in range(n):
                a = 2 * math.pi * (i + 0.5 * k) / n
                px, py = x + R * math.cos(a), y + R * math.sin(a)
                sphere(el, 'CRYSTAL', (px, py, zz - 60), 14, 4, 6, sz=2.6)
            for i in range(4):
                a = 2 * math.pi * i / 4 + 0.3 * k
                tube(el, 'BRASS', (x, y, zl + 450), (x + R * math.cos(a), y + R * math.sin(a), zz), 3, 6)
        sphere(el, 'CRYSTAL', (x, y, zl + 30), 45, 6, 10, sz=1.6)
        el.name = 'Люстра хрустальная Ø600, латунь (04а)'
    else:                                                          # потолочная многорожковая
        tube(el, 'BRASS', (x, y, zc - 20), (x, y, zl + 120), 10, 8)
        sphere(el, 'BRASS', (x, y, zl + 120), 50, 6, 12)
        for i in range(6):
            a = 2 * math.pi * i / 6
            px, py = x + 320 * math.cos(a), y + 320 * math.sin(a)
            tube(el, 'BRASS', (x, y, zl + 120), (px, py, zl + 120), 8, 8)
            tube(el, 'BRASS', (px, py, zl + 120), (px, py, zl + 170), 8, 8)
            tube(el, 'OPAL', (px, py, zl + 170), (px, py, zl + 300), 55, 16)
        el.name = 'Люстра потолочная многорожковая (6 плафонов), опал / латунь (03а)'



# ------------------------------------------------------------ двери: филёнки, коробка, наличники, пороги
def _leaf_z(key, h):
    """Низ и верх полотна: входная — над металлическим порогом 20; межкомнатные — зазор 8, в санузлы — над порогом + 10."""
    if key == 'entry':
        return 20.0, 20.0 + h
    lv = [zf_of(r_) for r_ in _door_rooms(key) if r_]
    thr = max(lv) if len(lv) == 2 and abs(lv[0] - lv[1]) > 1 else 0
    g = thr + 10 if thr else 8
    return float(g), float(g + h)


def _door_axes(key, o):
    """Геометрия полотна в осях проёма: границы по длине проёма, плоскость полотна и тыльная грань."""
    d = D.DOORS[key]
    k, ax, c0, c1, a, b, z0, z1 = o
    ea = (1.0, 0.0) if ax == 'y' else (0.0, 1.0)
    en = (0.0, 1.0) if ax == 'y' else (1.0, 0.0)
    th = 40 if key != 'entry' else 70
    s_h = d['h'][0] * ea[0] + d['h'][1] * ea[1]
    s_e = s_h + (d['c'][0] * ea[0] + d['c'][1] * ea[1]) * d['L']
    f_ = d['h'][0] * en[0] + d['h'][1] * en[1]
    on = d['o'][0] * en[0] + d['o'][1] * en[1]
    return min(s_h, s_e), max(s_h, s_e), f_, f_ - on * th, on, th


def _leaf_panels(el, m, h_, c_, o_, L, th, h, T_, z_off=0.0):
    """Филёнки: рамки молдингов (углы на ус) на обеих сторонах полотна — верхняя и нижняя."""
    if T_.get('style') != 'panel' and 'филён' not in T_.get('name', '').lower():
        return
    hx, hy = h_; cx, cy = c_; ox, oy = o_
    k0 = hx * cx + hy * cy
    rows_w = [(k0 + 110, k0 + L - 110)]
    rows_z = [(z_off + 180, z_off + 950), (z_off + 1100, z_off + h - 180)]
    for wf, sg in ((0, 1), (-th, -1)):
        pp = (hx + ox * wf, hy + oy * wf, 0)
        DT.front_frames(el, m, pp, (ox * sg, oy * sg, 0), (cx, cy, 0), rows_w, rows_z, w=24, d=9)


def _casing(el, m, ax, a, b, cf, cs, ztop, w=70, t=12):
    """Наличник профильный по контуру проёма (П-образный, углы на ус) на грани стены cf, наружу cs."""
    ea = np.array([1.0, 0, 0]) if ax == 'y' else np.array([0, 1.0, 0])
    en = np.array([0, 1.0, 0]) if ax == 'y' else np.array([1.0, 0, 0])
    n_out = en * cs

    def Pt(aa, zz):
        q = ea * aa + en * cf
        return (q[0], q[1], zz)
    path = [Pt(a, 0), Pt(a, ztop), Pt(b, ztop), Pt(b, 0)]
    left = np.cross(n_out, np.array([0, 0, 1.0]))
    prof = DT.casing_profile(w, t)
    prof = [(u - 10, v) for u, v in prof]
    if float(np.dot(left, -ea)) < 0:
        prof = [(-u, v) for u, v in prof][::-1]
    HP.sweep_up(el, m, path, prof, n_out, closed_path=False)


def _door_trim(S, key, mark, op):
    """Коробка (облицовка откосов проёма) и наличники 70 мм с двух сторон; порог в санузлы."""
    o = next((q for q in OPEN3D if q[0] == key), None)
    if not o:
        return
    k, ax, c0, c1, a, b, z0, z1 = o
    lm = fmat(getattr(D, 'DOOR_LEAF_FINISH', None), 'WHITE')
    rooms = _door_rooms(key)
    lo, hi, f_, back, on, th = _door_axes(key, o)
    hl = (D.DOOR_TYPES and next((T_.get('h') for T_ in D.DOOR_TYPES if key in T_.get('keys', [])), None)) or op.get('z1', 2000)
    g0, g1 = _leaf_z(key, op.get('z1', hl))
    sa, sb = sorted((back, back - on * 12))                 # притворная планка — за полотном
    if key != 'entry':
        el = S.add(Elem('IfcCovering', f'Коробка с притвором и наличники {mark} ({key})', predefined='MOLDING',
                        props={'Марка двери': mark, 'Наличник': '70×12 профильный, в цвет полотна',
                               'Коробка': 'добор на всю толщину стены, зазор до полотна 3 мм, притвор 12 мм'}))
        # коробка: стойки от откоса проёма до кромки полотна (зазор 3), верхняя перекладина — до полотна
        for (aa, bb) in ((a, lo - 3), (hi + 3, b)):
            if bb - aa > 1:
                HP.rbox(el, lm, *_obox(ax, aa, bb, c0, c1, 0, z1), 1, 2)
        HP.rbox(el, lm, *_obox(ax, a, b, c0, c1, g1 + 3, z1), 1, 2)
        # притворные планки
        HP.rbox(el, lm, *_obox(ax, lo - 3, lo + 12, sa, sb, g0, g1 + 3), 1, 2)
        HP.rbox(el, lm, *_obox(ax, hi - 12, hi + 3, sa, sb, g0, g1 + 3), 1, 2)
        HP.rbox(el, lm, *_obox(ax, lo - 3, hi + 3, sa, sb, g1 - 12, g1 + 3), 1, 2)
        for cf, cs in ((c0, -1), (c1, 1)):
            _casing(el, lm, ax, a, b, cf, cs, z1)
    else:
        inner = None
        for k_ in D.ROOMS:
            pp = ((a + b) / 2, c0 - 100) if ax == 'y' else (c0 - 100, (a + b) / 2)
            if EL_inside(D.ROOMS[k_]['poly'], pp):
                inner = c0
        cf, cs = (c0, -1) if inner is not None else (c1, 1)
        el = S.add(Elem('IfcCovering', 'Наличники и откосы входной двери Д1 (МДФ)', predefined='MOLDING',
                        props={'Марка двери': mark, 'Отделка': 'МДФ, эмаль в цвет полотна изнутри'}))
        im = fmat(getattr(D, 'FRONT', None), 'FRONT')
        _casing(el, im, ax, a, b, cf, cs, z1)
        # откосы МДФ (от внутренней грани стены до коробки двери)
        fr0 = back - on * 40                                     # внутренняя кромка металлической коробки
        ra, rb = sorted((cf, fr0))
        for (aa, bb, za, zb) in ((a, a + 12, 0, z1), (b - 12, b, 0, z1), (a, b, z1 - 12, z1)):
            HP.rbox(el, im, *_obox(ax, aa, bb, ra, rb, za, zb), 1, 2)
        # металлическая коробка с притвором и порог
        ef = S.add(Elem('IfcBuildingElementProxy', 'Коробка входной двери Д1 (металл, сущ.)', predefined='USERDEFINED',
                        objtype='Дверная коробка', props={'Статус': 'существующая', 'Порог': 'металлический, 20 мм'}))
        ca, cb = sorted((fr0, f_))
        for (aa, bb) in ((a + 12, lo - 3), (hi + 3, b - 12)):
            if bb - aa > 1:
                HP.rbox(ef, 'ENTRY', *_obox(ax, aa, bb, ca, cb, 0, z1 - 12), 1, 2)
        HP.rbox(ef, 'ENTRY', *_obox(ax, a + 12, b - 12, ca, cb, g1 + 3, z1 - 12), 1, 2)
        HP.rbox(ef, 'ENTRY', *_obox(ax, lo - 3, lo + 14, sa, sb, g0, g1 + 3), 1, 2)
        HP.rbox(ef, 'ENTRY', *_obox(ax, hi - 14, hi + 3, sa, sb, g0, g1 + 3), 1, 2)
        HP.rbox(ef, 'ENTRY', *_obox(ax, lo - 3, hi + 3, sa, sb, g1 - 14, g1 + 3), 1, 2)
        HP.rbox(ef, 'STEEL', *_obox(ax, a + 12, b - 12, ca, cb, 0, 20), 2, 2)
    # порог — при перепаде полов
    lv = [zf_of(r_) for r_ in rooms if r_]
    if len(lv) == 2 and abs(lv[0] - lv[1]) > 1:
        el = S.add(Elem('IfcCovering', f'Порог мраморный проёма {key}', predefined='USERDEFINED', objtype='Порог',
                        props={'Перепад, мм': abs(lv[0] - lv[1]), 'Материал': 'мрамор белый, фаска'}))
        HP.rbox(el, 'MARBLE_SILL', *_obox(ax, a + 30, b - 30, c0 - 8, c1 + 8, 0, max(lv)), 4, 3)


def _door_rooms(key):
    d = D.DOORS[key]
    out = []
    for sg in (1, -1):
        p = (d['h'][0] + d['o'][0] * 250 * sg + d['c'][0] * d['L'] / 2,
             d['h'][1] + d['o'][1] * 250 * sg + d['c'][1] * d['L'] / 2)
        out.append(next((k for k in D.ROOMS if EL_inside(D.ROOMS[k]['poly'], p)), None))
    return out



# ------------------------------------------------------------ щиты
def _board(S, P):
    x, y = P['p']
    nx, ny = P.get('n') or (1, 0)
    z = P['z']
    shk = P['kind'] == 'shk'
    w, h, d = (310, 480, 120) if shk else (300, 350, 110)
    el = S.add(Elem('IfcElectricDistributionBoard', 'Щит квартирный ЩК (24 мод.)' if shk else 'Щит слаботочный СЩ',
                    room=P['room'], predefined='CONSUMERUNIT' if shk else 'DISTRIBUTIONBOARD',
                    props={'Помещение': P['room'], 'Низ, мм': z, 'Примечание': P.get('note', ''), 'Установка': 'накладной, в шкафу прихожей'}))
    el.system = 'Э Электроснабжение' if shk else 'СС Слаботочные сети'
    if nx:
        box(el, 'WHITE', x, y - w / 2, z, x + nx * d, y + w / 2, z + h)
        box(el, 'GRAPHITE', x + nx * d, y - w / 2 + 20, z + 20, x + nx * (d + 2), y + w / 2 - 20, z + h - 20)
    else:
        box(el, 'WHITE', x - w / 2, y, z, x + w / 2, y + ny * d, z + h)
        box(el, 'GRAPHITE', x - w / 2 + 20, y + ny * d, z + 20, x + w / 2 - 20, y + ny * (d + 2), z + h - 20)


# ------------------------------------------------------------ плинтус, потолочный молдинг, буазери, пояс
def _cuts_on_wall(room, W, kinds, dmax=60, ceil=False):
    from kit import subtract_intervals  # noqa: F401
    cuts = []
    for it in D.ITEMS:
        if it['room'] != room or it['kind'] not in kinds:
            continue
        r = D.item_rect(it)
        if r is None:
            continue
        if ceil:
            z = it.get('z', (0, 0))
            if not (isinstance(z, tuple) and z[1] >= (D.ROOM[room]['ceil'] or 9e9) - 5):
                continue
        s0, s1, d0, d1 = EL.proj_rect(W, r)
        if d0 <= dmax:
            cuts.append((max(0, s0), min(W['L'], s1)))
    return cuts


def trims(S):
    from kit import subtract_intervals
    for room in D.rooms_all():
        info = D.ROOM[room]
        zf, zc = zf_of(room), zc_of(room)
        # плинтус (профиль МДФ 100×16, углы на ус)
        if info.get('plinth'):
            el = S.add(Elem('IfcCovering', f'Плинтус МДФ h=100 — пом. {room}', room=room, predefined='SKIRTINGBOARD',
                            props={'Помещение': room, 'Описание': D.FINISH.get('ПЛ', 'Плинтус'), 'Высота, мм': 100}))

            def cuts_p(W):
                c_ = [(o['s0'], o['s1']) for o in EL.openings_on(W, room) if o['kind'] in ('door', 'bdoor')]
                return c_ + _cuts_on_wall(room, W, ('wardrobe', 'kitchen_run', 'column', 'filler', 'bench', 'wm_cab', 'box', 'bath'))

            def mat_p(W, a, b):
                code = _zone_code_at(room, wpt(W, (a + b) / 2, 0), zf + 50) or info.get('wall')
                m = mkey(code) if code and code != 'X' and mkey(code) in M.MATS else 'C1'
                return m, (fin_t(code) if code and code != 'X' else 3)
            tot = 0.0
            for pts, m, t, closed, L_ in _chains(room, cuts_p, mat_p):
                prof = [(u - t, v) for u, v in DT.plinth_profile(100, 16)]
                HP.sweep_up(el, m, [(q[0], q[1], zf) for q in pts], prof, (0, 0, 1), closed_path=closed)
                tot += L_
            el.props['Длина, м'] = round(tot / 1000, 2)
        # потолочный молдинг (галтель 60, вогнутый профиль, углы на ус)
        if info.get('ceil_code') == 'Пт1' and info.get('ceil'):
            el = S.add(Elem('IfcCovering', f'Галтель потолочная 60 — пом. {room}', room=room, predefined='MOLDING',
                            props={'Помещение': room, 'Профиль': 'полиуретан 60×60, окраска в цвет потолка'}))
            feats = [f for f in D.CEIL_FEATURES if f['room'] == room and f['kind'] in ('niche', 'cove')]

            def cuts_c(W):
                c_ = _cuts_on_wall(room, W, D.BUILTIN_KINDS, dmax=60, ceil=True)
                for f in feats:
                    s0, s1, d0, d1 = EL.proj_rect(W, f['rect'])
                    if d0 <= 5 and s1 > 0 and s0 < W['L']:
                        c_.append((max(0, s0), min(W['L'], s1)))
                return c_
            for pts, m, t, closed, L_ in _chains(room, cuts_c, lambda W, a, b: ('CEIL', 3)):
                prof = [(u - t, v) for u, v in DT.cornice_profile(60)]
                HP.sweep_up(el, 'CEIL', [(q[0], q[1], zc) for q in pts], prof, (0, 0, 1), closed_path=closed, smooth=True)
        # буазери (молдинги) и пояс-разделитель
        for (r_, lab, s0, s1, z0, z1, code) in D.WALL_ZONES:
            if r_ != room or code == 'X':
                continue
            m_ = D.mat(code)
            W = EL.wall_geom(room, lab)
            t = fin_t(code)
            z0, z1 = max(z0, zf), min(z1, zc)
            if m_.get('style') == 'boiserie':
                el = S.add(Elem('IfcCovering', f'Буазери — молдинги, пом. {room}, стена {lab}', room=room, predefined='MOLDING',
                                props={'Помещение': room, 'Стена': lab, 'Описание': D.FINISH.get(code, '')}))
                step = m_.get('step', 900)
                n = max(1, int(round((s1 - s0) / step)))
                pw = (s1 - s0) / n
                H = z1 - z0
                zb = z0 + H * 0.33
                ops = openings_on_wall(W, room)
                for i in range(n):
                    a, b = s0 + i * pw + 130, s0 + (i + 1) * pw - 130
                    if any(o[1] < b and o[2] > a for o in ops):
                        continue
                    for za, zb_ in ((z0 + 130, zb - 80), (zb + 80, z1 - 130)):
                        _wframe(el, mkey(code), W, a, b, za, zb_, t)
                # горизонтальный пояс-молдинг на 1/3 высоты
                _hmold(el, mkey(code), W, s0 + 40, s1 - 40, zb, t)
            elif m_.get('tex') == 'paint' and 'молдинг' in D.FINISH.get(code, '') and z1 < zc - 100:
                el = S.add(Elem('IfcCovering', f'Молдинг-разделитель +{z1:.0f}, пом. {room}, стена {lab}', room=room,
                                predefined='MOLDING', props={'Помещение': room, 'Стена': lab}))
                _hmold(el, 'C1' if 'C1' in M.MATS else mkey(code), W, s0, s1, z1, t)
    # ревизионные люки в потолке
    for f in D.CEIL_FEATURES:
        if f['kind'] != 'hatch':
            continue
        x0, y0, x1, y1 = f['rect']
        zc = zc_of(f['room'])
        el = S.add(Elem('IfcBuildingElementProxy', 'Люк ревизионный потолочный ' + f'{x1 - x0:.0f}×{y1 - y0:.0f}', room=f['room'],
                        predefined='USERDEFINED', objtype='Люк ревизионный', props={'Помещение': f['room'], 'Назначение': f.get('note', '')}))
        for (a, b, c, d) in ((x0, y0, x1, y0 + 8), (x0, y1 - 8, x1, y1), (x0, y0, x0 + 8, y1), (x1 - 8, y0, x1, y1)):
            box(el, 'WHITE', a, b, zc - 2, c, d, zc)
        box(el, 'CEIL', x0 + 8, y0 + 8, zc - 1, x1 - 8, y1 - 8, zc)


def _wframe(el, m, W, a, b, z0, z1, t, w=40, d=18):
    """Рамка буазери: полиуретановый молдинг (полукруглый с полками), углы на ус, в плоскости стены."""
    n3 = (W['n'][0], W['n'][1], 0)
    path = []
    for s_, z_ in ((a + w / 2, z0 + w / 2), (b - w / 2, z0 + w / 2), (b - w / 2, z1 - w / 2), (a + w / 2, z1 - w / 2)):
        q = wpt(W, s_, t)
        path.append((q[0], q[1], z_))
    hw = w / 2
    prof = [(-hw, 0), (hw, 0), (hw, 3), (hw * 0.7, 8), (hw * 0.35, d), (-hw * 0.35, d), (-hw * 0.7, 8), (-hw, 3)]
    HP.sweep_up(el, m, path, prof, n3, closed_path=True, smooth=True)


def _hmold(el, m, W, s0, s1, zc_, t, w=50, d=20):
    """Горизонтальный молдинг (пояс) по стене."""
    n3 = (W['n'][0], W['n'][1], 0)
    q0, q1 = wpt(W, s0, t), wpt(W, s1, t)
    hw = w / 2
    prof = [(-hw, 0), (hw, 0), (hw, 4), (hw * 0.6, 9), (hw * 0.4, d), (-hw * 0.2, d), (-hw * 0.6, 11), (-hw, 5)]
    HP.sweep_up(el, m, [(q0[0], q0[1], zc_), (q1[0], q1[1], zc_)], prof, n3, closed_path=False, smooth=True)


def _chains(room, cutfn, matfn):
    """Непрерывные участки по периметру помещения (через углы) за вычетом проёмов/мебели:
    [(точки пути на линии стен, материал, толщина отделки, замкнут, длина)]."""
    from kit import subtract_intervals
    walls = []
    for lab, pL, pR in D.RWALLS[room]:
        W = EL.wall_geom(room, lab)
        ivs = [(a, b) for a, b in subtract_intervals((0, W['L']), cutfn(W)) if b - a >= 20]
        walls.append((W, ivs))
    segs = []
    for wi, (W, ivs) in enumerate(walls):
        for a, b in ivs:
            m, t = matfn(W, a, b)
            segs.append(dict(w=wi, a=a, b=b, m=m, t=t, W=W))
    chains = []
    for sg in segs:
        if chains:
            pv = chains[-1][-1]
            Wp = walls[pv['w']][0]
            cont = (pv['w'] + 1 == sg['w'] and abs(pv['b'] - Wp['L']) < 1 and sg['a'] < 1 and pv['m'] == sg['m']
                    and math.hypot(Wp['pR'][0] - sg['W']['pL'][0], Wp['pR'][1] - sg['W']['pL'][1]) < 2)
            if cont:
                chains[-1].append(sg)
                continue
        chains.append([sg])
    closed_all = False
    if len(chains) > 1:
        f, l = chains[0][0], chains[-1][-1]
        Wl = walls[l['w']][0]
        if (l['w'] == len(walls) - 1 and f['w'] == 0 and abs(l['b'] - Wl['L']) < 1 and f['a'] < 1 and f['m'] == l['m']
                and math.hypot(Wl['pR'][0] - f['W']['pL'][0], Wl['pR'][1] - f['W']['pL'][1]) < 2):
            chains[0] = chains[-1] + chains[0]
            chains.pop()
    elif len(chains) == 1 and len(chains[0]) == len(walls) and all(abs(c['b'] - c['W']['L']) < 1 and c['a'] < 1 for c in chains[0]):
        closed_all = True
    out = []
    for ch in chains:
        pts = []
        for i, sg in enumerate(ch):
            W = sg['W']
            pa, pb = wpt(W, sg['a'], 0), wpt(W, sg['b'], 0)
            if not pts:
                pts.append(pa)
            pts.append(pb)
        L_ = sum(sg['b'] - sg['a'] for sg in ch)
        if closed_all:
            pts = pts[:-1]
        out.append((pts, ch[0]['m'], ch[0]['t'], closed_all, L_))
    return out


# ------------------------------------------------------------ инженерные системы
def _room_at(p):
    return next((k for k in D.ROOMS if EL_inside(D.ROOMS[k]['poly'], p)), None)


def _diam(label, kind=None):
    import re
    m = re.search(r'Ø\s?(\d+)', label or '')
    if m:
        return int(m.group(1))
    return {'k110': 110, 'k50': 50, 'hvs': 32, 'gvs': 32}.get(kind, 50)


SYS = {'k': 'К1 Канализация', 'hvs': 'В1 Водопровод холодный', 'gvs': 'Т3 Водопровод горячий',
       'vent': 'В Вентиляция вытяжная', 'ac': 'КВ Кондиционирование', 'el': 'Э Электроснабжение', 'heat': 'ТП Тёплый пол (электр.)'}


def engineering(S):
    # стояки
    for R in D.RISERS:
        k = R['kind']
        x, y = R['p']
        d = _diam(R.get('label'), k)
        down = 'вниз' in (R.get('label') or '')
        z_top = 420 if down else RC + SLAB
        nm = ('Стояк канализации ' if k.startswith('k') else 'Стояк ') + (R.get('label') or k) + (' — новый, вниз к стояку соседей' if down else ' (сущ.)')
        el = S.add(Elem('IfcPipeSegment', nm, predefined='RIGIDSEGMENT',
                        props={'Диаметр, мм': d, 'Материал': 'ПП' if k.startswith('k') else 'сталь / PPR (сущ.)',
                               'Статус': 'новый' if down else 'существующий'}))
        el.system = SYS['k'] if k.startswith('k') else SYS[k]
        m = 'PP_GREY' if k.startswith('k') else ('PEX_BLUE' if k == 'hvs' else 'PEX_RED')
        tube(el, m, (x, y, RF - SLAB), (x, y, z_top), d / 2, 16)
        if k.startswith('k'):                                     # ревизия и раструбы (у нового стояка — внутри тумбы)
            zr = 250 if down else 900
            tube(el, m, (x, y, zr), (x, y, zr + 150), d / 2 + 8, 16)
            tube(el, 'WHITE', (x, y, zr + 70), (x + (d / 2 + 30 if not down else 0), y + (0 if not down else d / 2 + 30), zr + 70), d / 4, 12)
    # канализация (по ломаной, уклон 2 % к стояку)
    for pts, lab in D.SEWER_ROUTES:
        d = _diam(lab)
        r = d / 2
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        room = _room_at(pts[0]) or _room_at(pts[-1])
        z_end = r + 15
        acc, p3 = 0.0, []
        for i, q in enumerate(pts):
            if i:
                acc += math.hypot(q[0] - pts[i - 1][0], q[1] - pts[i - 1][1])
            p3.append((q[0], q[1], z_end + 0.02 * (L - acc)))
        el = S.add(Elem('IfcPipeSegment', f'Канализация {lab}', room=room, predefined='RIGIDSEGMENT',
                        props={'Диаметр, мм': d, 'Уклон': '0,02 к стояку', 'Длина, м': round(L / 1000, 2), 'Материал': 'ПП серый'}))
        el.system = SYS['k']
        polytube(el, 'PP_GREY', p3, r, 14)
    # подводки ХВС/ГВС к кухне (в стяжке)
    for pts, lab in getattr(D, 'WATER_ROUTES', []):
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        for kk, off, m in (('hvs', -22, 'PEX_BLUE'), ('gvs', 22, 'PEX_RED')):
            p3 = []
            for i, q in enumerate(pts):
                a_ = pts[max(0, i - 1)]; b_ = pts[min(len(pts) - 1, i + 1)]
                dx, dy = b_[0] - a_[0], b_[1] - a_[1]
                Lq = math.hypot(dx, dy) or 1
                p3.append((q[0] - dy / Lq * off, q[1] + dx / Lq * off, -RF * 0 - 35))
            el = S.add(Elem('IfcPipeSegment', f'{"В1" if kk == "hvs" else "Т3"} — {lab} (PEX 20 в гофре, в штробе стяжки)',
                            predefined='FLEXIBLESEGMENT',
                            props={'Диаметр, мм': 20, 'Длина, м': round(L / 1000, 2), 'Прокладка': 'в канавке стяжки, без соединений'}))
            el.system = SYS[kk]
            polytube(el, m, p3, 12, 10)
    # выводы сантехники
    for P in D.PLUMB:
        k = P['kind']
        x, y = P['p']
        z = P.get('z', 0)
        n = P.get('n')
        cls, pre = ('IfcPipeFitting', 'EXIT')
        if k == 'tap':
            cls, pre = 'IfcValve', 'DRAWOFFCOCK'
        nm = {'hvs': 'Вывод ХВС (водорозетка)', 'gvs': 'Вывод ГВС (водорозетка)', 'k50': 'Вывод канализации Ø50',
              'k110': 'Вывод канализации Ø110', 'sif': 'Сифон встраиваемый для СМ/СУШ', 'tap': 'Кран шаровой для техники'}.get(k, k)
        el = S.add(Elem(cls, f'{nm} — {P.get("fx", "")}', room=P['room'], predefined=pre,
                        props={'Помещение': P['room'], 'Прибор': P.get('fx', ''), 'Отметка, мм': z, 'Примечание': P.get('note', '')}))
        el.system = SYS['k'] if k.startswith('k') or k == 'sif' else (SYS['gvs'] if k == 'gvs' else SYS['hvs'])
        m = {'hvs': 'BRASS', 'gvs': 'BRASS', 'k50': 'PP_GREY', 'k110': 'PP_GREY', 'sif': 'WHITE', 'tap': 'BRASS'}.get(k, 'BRASS')
        r = {'k50': 25, 'k110': 55, 'hvs': 12, 'gvs': 12, 'tap': 12}.get(k, 20)
        if n:
            nx, ny = n
            if k == 'sif':
                box(el, 'WHITE', min(x, x + nx * 5) - (100 if not nx else 0), min(y, y + ny * 5) - (100 if not ny else 0), z - 90,
                    max(x, x + nx * 5) + (100 if not nx else 0), max(y, y + ny * 5) + (100 if not ny else 0), z + 90)
            else:
                tube(el, m, (x - nx * 60, y - ny * 60, z), (x + nx * 25, y + ny * 25, z), r, 12)
                if k == 'tap':
                    box(el, 'RED' if 'RED' in M.MATS else 'BRASS', x + nx * 25 - 8, y + ny * 25 - 8, z, x + nx * 25 + 8, y + ny * 25 + 8, z + 60)
                if k in ('hvs', 'gvs'):
                    cyl(el, 'PEX_BLUE' if k == 'hvs' else 'PEX_RED', x + nx * 26, y + ny * 26, 6, z - 6, z + 6, 8)
        else:                                     # вывод из пола: под ванной — до подводки смесителя, иначе — в уровне стяжки
            top = 250 if 'ванн' in P.get('fx', '') else zf_of(P['room']) - 15
            tube(el, m, (x, y, -60), (x, y, top), r, 12)
    # оборудование в шахте: краны, фильтры, счётчики, регуляторы давления (за люком)
    for R in D.RISERS:
        if R['kind'] not in ('hvs', 'gvs'):
            continue
        x, y = R['p']
        sysn = SYS[R['kind']]
        m = 'PEX_BLUE' if R['kind'] == 'hvs' else 'PEX_RED'
        yo = y + 60 if y + 60 < 3400 else y - 60
        el = S.add(Elem('IfcPipeFitting', f'Отвод от стояка {R.get("label", "")} (тройник)', predefined='JUNCTION', props={'Установка': 'шахта, за люком'}))
        el.system = sysn
        tube(el, m, (x, y, 350), (x, yo, 350), 12)
        tube(el, m, (x, yo, 350), (x, yo, 900), 10)
        for nm, cls, pre, z0, z1, mm in (('Кран шаровой отсекающий', 'IfcValve', 'ISOLATING', 380, 440, 'BRASS'),
                                         ('Фильтр сетчатый', 'IfcFilter', 'STRAINER', 470, 560, 'BRASS'),
                                         ('Счётчик воды с импульсным выходом', 'IfcFlowMeter', 'WATERMETER', 590, 720, 'BRASS'),
                                         ('Регулятор давления', 'IfcValve', 'PRESSUREREDUCING', 750, 840, 'BRASS')):
            e2 = S.add(Elem(cls, f'{nm} — {"ХВС" if R["kind"] == "hvs" else "ГВС"}', predefined=pre,
                            props={'Установка': 'шахта между санузлами, за люком-невидимкой', 'Ду': 15}))
            e2.system = sysn
            tube(e2, mm, (x, yo, z0), (x, yo, z1), 20, 12)
            if cls == 'IfcFlowMeter':
                tube(e2, 'WHITE', (x, yo, (z0 + z1) / 2), (x + 45, yo, (z0 + z1) / 2), 32, 16)
            if cls == 'IfcValve' and pre == 'ISOLATING':
                box(e2, 'PEX_RED' if R['kind'] == 'gvs' else 'PEX_BLUE', x, yo - 8, (z0 + z1) / 2 - 6, x + 90, yo + 8, (z0 + z1) / 2 + 6)
    # вентиляция: воздуховоды от вентиляторов в каналы шахты, приточные клапаны, трассы фреона
    for V in getattr(D, 'VENT', []):
        kd = V['kind']
        if kd == 'duct':
            pts = V['pts']
            room = _room_at(pts[0])
            zc = zc_of(room) if room else 2420
            zd = zc + 70
            el = S.add(Elem('IfcDuctSegment', f'Воздуховод {V.get("d", "Ø100")} — {V.get("note", "")}', room=room,
                            predefined='FLEXIBLESEGMENT', props={'Диаметр': V.get('d', 'Ø100'), 'Прокладка': 'над подвесным потолком'}))
            el.system = SYS['vent']
            polytube(el, 'DUCT', [(p[0], p[1], zd) for p in pts], 50, 16)
            e2 = S.add(Elem('IfcAirTerminal', 'Решётка вентканала (вход воздуховода в канал шахты)', predefined='GRILLE',
                            props={'Примечание': 'уточнить по месту'}))
            e2.system = SYS['vent']
            px, py = pts[-1]
            box(e2, 'WHITE', px - 80, py - 80, zd - 80, px + 80, py + 80, zd + 80)
        elif kd == 'valve':
            x, y = V['p']
            nx, ny = V.get('n', (1, 0))
            el = S.add(Elem('IfcAirTerminal', 'Клапан приточный стеновой (КИВ) Ø125', room=V.get('room'), predefined='REGISTER',
                            props={'Отметка, мм': 2100, 'Примечание': V.get('note', '')}))
            el.system = 'П Приток (естественный)'
            tube(el, 'WHITE', (x, y, 2100), (x + nx * 40, y + ny * 40, 2100), 95, 24)
            tube(el, 'WHITE', (x + nx * 40, y + ny * 40, 2100), (x + nx * 70, y + ny * 70, 2100), 110, 24)
        elif kd == 'acroute':
            pts = V['pts']
            room = V.get('room')
            ac = next((it for it in D.ITEMS if it['room'] == room and it['kind'] == 'ac'), None)
            zz = (ac['z'][1] - 60) if ac else 2500
            el = S.add(Elem('IfcPipeSegment', f'Трасса фреона и дренажа кондиционера — {V.get("note", "")}', room=room,
                            predefined='RIGIDSEGMENT', props={'Статус': 'существующая — проверить', 'Трубы': 'медь 1/4" + 3/8" в изоляции, дренаж Ø16'}))
            el.system = SYS['ac']
            for dz, rr, m in ((0, 9, 'COPPER'), (24, 12, 'COPPER'), (-24, 8, 'WHITE')):
                polytube(el, m, [(p[0], p[1], zz + dz) for p in pts], rr, 10)
    # рамы инсталляций унитазов
    for it in D.ITEMS:
        if it['kind'] != 'wc':
            continue
        wall, face, axis = it['wall'], it['face'], it['axis']
        el = S.add(Elem('IfcBuildingElementProxy', 'Рама инсталляции подвесного унитаза с бачком', room=it['room'],
                        predefined='USERDEFINED', objtype='Инсталляция', props={'Помещение': it['room'], 'Высота рамы, мм': 1120}))

        def B(m, u0, u1, w0, w1, z0, z1):
            p = DP.to_model(wall, face, axis, u0, w0); q = DP.to_model(wall, face, axis, u1, w1)
            box(el, m, p[0], p[1], z0, q[0], q[1], z1)
        for w0 in (-250, 210):
            B('STEELFRAME', -170, -130, w0, w0 + 40, 0, 1120)
        for z0 in (0, 380, 1080):
            B('STEELFRAME', -170, -130, -250, 250, z0, z0 + 40)
        B('WHITE', -160, -30, -200, 200, 650, 1100)                  # бачок скрытого монтажа
        B('STEELFRAME', -130, -10, -110, -90, 300, 340)               # шпильки крепления унитаза
        B('STEELFRAME', -130, -10, 90, 110, 300, 340)
    # ввод питающего кабеля (сверху над входной дверью) → в потолке → к ЩК
    pin = next((P for P in D.POINTS if P.get('tag') == 'ввод'), None)
    shk = next((P for P in D.POINTS if P['kind'] == 'shk'), None)
    if pin and shk:
        (x, y), (xs, ys) = pin['p'], shk['p']
        nx, ny = pin.get('n') or (0, 0)
        zc = zc_of(pin['room'])
        zv = zc + 60
        pts = [(x, y, pin['z']), (x + nx * 30, y + ny * 30, pin['z']), (x + nx * 30, y + ny * 30, zv),
               (xs + nx * 30, ys + ny * 30, zv), (xs + nx * 30, ys + ny * 30, shk['z'] + 480)]
        el = S.add(Elem('IfcCableSegment', 'Питающий кабель ВВГнг-LS 3×10 (ввод над входной дверью → к ЩК)', room=pin['room'],
                        predefined='CABLESEGMENT', props={'Прокладка': 'в гофре, в пространстве потолка', 'Примечание': 'сечение и трассу уточнить по ТУ'}))
        el.system = SYS['el']
        polytube(el, 'GRAPHITE', pts, 12, 10)


def heating(S):
    """Нагревательные маты тёплого пола — по маске укладки (как на плане тёплых полов) + датчик в гофре."""
    for h in getattr(D, 'HEAT', []):
        room = h['room']
        try:
            mk = D.heat_mask(room)
        except Exception:  # noqa: BLE001
            continue
        cells = mk['cells']
        if not cells:
            continue
        x0, y0, c = mk['x0'], mk['y0'], mk['cell']
        zf = zf_of(room)
        el = S.add(Elem('IfcSpaceHeater', f'Нагревательный мат тёплого пола — пом. {room}', room=room, predefined='USERDEFINED',
                        objtype='Нагревательный мат (электр.)',
                        props={'Помещение': room, 'Мощность, Вт/м²': h.get('w', 150), 'Площадь укладки, м²': round(D.heat_area(room), 2),
                               'Мат, м²': D.heat_mat(room), 'Терморегулятор': h.get('tr', ''), 'Укладка': 'в слой плиточного клея'}))
        el.system = SYS['heat']
        # слияние ячеек в полосы по j и прямоугольники по i
        rows = {}
        for (i, j) in cells:
            rows.setdefault(i, []).append(j)
        runs = {}
        for i, js in rows.items():
            js.sort()
            a = js[0]; prev = a
            for j in js[1:] + [None]:
                if j is None or j != prev + 1:
                    runs.setdefault((a, prev), []).append(i)
                    if j is not None:
                        a = j
                if j is not None:
                    prev = j
        for (ja, jb), iis in runs.items():
            iis.sort()
            a = iis[0]; prev = a
            for i in iis[1:] + [None]:
                if i is None or i != prev + 1:
                    box(el, 'HEATMAT', x0 + a * c, y0 + ja * c, zf - 12, x0 + (prev + 1) * c, y0 + (jb + 1) * c, zf - 9)
                    if i is not None:
                        a = i
                if i is not None:
                    prev = i
        # датчик пола в гофре от терморегулятора
        P = next((q for q in D.POINTS if q.get('id') == h.get('tr')), None)
        if P:
            px, py = P['p']
            nx, ny = P.get('n') or (0, 0)
            # ближайшая к регулятору ячейка мата
            best = min(cells, key=lambda ij: (x0 + (ij[0] + 0.5) * c - px) ** 2 + (y0 + (ij[1] + 0.5) * c - py) ** 2)
            tx, ty = x0 + (best[0] + 0.5) * c, y0 + (best[1] + 0.5) * c
            if _room_at((px + nx * 50, py + ny * 50)) == room:
                qx, qy = px - nx * 25, py - ny * 25            # гофра — в штробе (перегородка), не в объёме помещения
                pts = [(qx, qy, P['z']), (qx, qy, zf - 15), (tx, ty, zf - 15)]
                polytube(el, 'PP_GREY', pts, 8, 8)



def wrbox(el, m, W, s0, s1, d0, d1, z0, z1, r, seg=3):
    """Скруглённый брусок в осях стены (в т. ч. косой)."""
    c = wpt(W, (s0 + s1) / 2, (d0 + d1) / 2)
    HP.rbox_f(el, m, (c[0], c[1], (z0 + z1) / 2), (W['d'][0], W['d'][1], 0), (W['n'][0], W['n'][1], 0), (0, 0, 1),
              abs(s1 - s0) / 2, abs(d1 - d0) / 2, abs(z1 - z0) / 2, r, seg)


def _eui(el, k, m, W, sP, d0, z, n, w):
    """ЭУИ: рамка, механизм, клавиши / гнёзда с заземлением, дисплей терморегулятора."""
    nrm = np.array([W['n'][0], W['n'][1], 0.0])
    if k == 'out':
        wrbox(el, 'GRAPHITE', W, sP - 22, sP + 22, d0, d0 + 5, z, z + 44, 4)
        q = wpt(W, sP, d0 + 5)
        HP.lathe(el, 'BLACK', [(0, 0), (9, 0), (9, 2), (0, 2)], (q[0], q[1], z + 22), 16, frame=HP.axis_frame(nrm))
        return
    if k == 'int':
        wrbox(el, 'WHITE', W, sP - 55, sP + 55, d0, d0 + 18, z, z + 200, 10, 4)
        wrbox(el, 'BLACKGLASS', W, sP - 40, sP + 40, d0 + 17, d0 + 19, z + 110, z + 180, 3, 2)
        for i in range(3):
            q = wpt(W, sP - 25 + i * 25, d0 + 18)
            HP.lathe(el, 'GRAPHITE', [(0, 0), (8, 0), (8, 3), (0, 4)], (q[0], q[1], z + 60), 16, frame=HP.axis_frame(nrm))
        return
    wrbox(el, m, W, sP - w / 2, sP + w / 2, d0, d0 + 9, z, z + 80, 8, 4)                 # рамка
    for i in range(n):
        sc = sP - w / 2 + 40 + i * 71
        if k.startswith('v'):                                                            # клавиши
            keys = 2 if k in ('v2', 'v2p') else 1
            kw = 52 / keys
            for j in range(keys):
                a0 = sc - 26 + j * kw
                wrbox(el, m, W, a0 + 1, a0 + kw - 1, d0 + 8, d0 + 14, z + 14, z + 66, 3, 2)
        elif k == 'tr':
            wrbox(el, 'WHITE', W, sc - 27, sc + 27, d0 + 8, d0 + 15, z + 13, z + 67, 4, 2)
            wrbox(el, 'BLACKGLASS', W, sc - 18, sc + 18, d0 + 14, d0 + 16, z + 32, z + 60, 2, 2)
        else:                                                                            # розетка / блок
            wrbox(el, m, W, sc - 26, sc + 26, d0 + 8, d0 + 13, z + 14, z + 66, 6, 3)
            q = wpt(W, sc, d0 + 13)
            fr = HP.axis_frame(nrm)
            HP.lathe(el, 'BLACK', [(0, -9), (19, -9), (19, -1), (21, 0), (0, 0.5)], (q[0], q[1], z + 40), 32, frame=fr)
            for dd in (-9.5, 9.5):
                p2 = wpt(W, sc + dd, d0 + 13)
                HP.lathe(el, 'BLACK', [(0, -6), (2.4, -6), (2.4, 0.6), (0, 0.6)], (p2[0], p2[1], z + 40), 12, frame=fr)
