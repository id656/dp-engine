# -*- coding: utf-8 -*-
"""Многополигональные построители предметов 3D-модели (мебель, сантехника, светильники, фурнитура, молдинги).
Подключаются из scene3d: build_item() возвращает True, если предмет построен здесь."""
import math

import numpy as np

import model as D
from ifc import hp as H
from ifc.m3d import box, prism, MATS, fabric_mat

SIDE_N = {'W': (1, 0), 'E': (-1, 0), 'S': (0, 1), 'N': (0, -1)}


# ---------------------------------------------------------------- локальные оси у стены
def lw(sd, face, u, w):
    """Точка плана по локальным координатам у стены: u — от стены внутрь, w — вдоль стены."""
    if sd == 'W':
        return (face + u, w)
    if sd == 'E':
        return (face - u, w)
    if sd == 'S':
        return (w, face + u)
    return (w, face - u)


def wall_frame(sd):
    """Оси: eu — внутрь помещения, ew — вдоль стены (по возрастанию w), ez — вверх."""
    nx, ny = SIDE_N[sd]
    eu = (nx, ny, 0)
    ew = (0, 1, 0) if sd in ('W', 'E') else (1, 0, 0)
    return eu, ew, (0, 0, 1)


def lrbox(el, m, sd, face, u0, u1, w0, w1, z0, z1, r, seg=4):
    eu, ew, ez = wall_frame(sd)
    cu, cw = (u0 + u1) / 2, (w0 + w1) / 2
    x, y = lw(sd, face, cu, cw)
    H.rbox_f(el, m, (x, y, (z0 + z1) / 2), eu, ew, ez, abs(u1 - u0) / 2, abs(w1 - w0) / 2, abs(z1 - z0) / 2, r, seg)


def front_of(r, room):
    from ifc import scene3d as S3
    return S3._front_dir(r, room)


def front_sd(fr):
    """'+x' (фасад смотрит в +x) -> стена 'W' и т. д."""
    return {'+x': 'W', '-x': 'E', '+y': 'S', '-y': 'N'}[fr]


def rect_local(r, sd):
    """Прямоугольник предмета в осях стены sd: face, (u0,u1), (w0,w1)."""
    x0, y0, x1, y1 = r
    if sd == 'W':
        return x0, (0, x1 - x0), (y0, y1)
    if sd == 'E':
        return x1, (0, x1 - x0), (y0, y1)
    if sd == 'S':
        return y0, (0, y1 - y0), (x0, x1)
    return y1, (0, y1 - y0), (x0, x1)


# ---------------------------------------------------------------- профили
OGEE = [(0, 0), (0, 4), (4, 6), (7, 10), (9, 14), (12, 16), (16, 17), (22, 17), (22, 0)]       # молдинг фасада/филёнки (u, v)


def ogee(w=22, d=17):
    return [(u * w / 22.0, v * d / 17.0) for u, v in OGEE]


def plinth_profile(h=100, t=16):
    # u — от стены (отрицательно внутрь — см. sweep_up), v — высота
    pts = [(0, 0), (-t, 0), (-t, h * 0.55), (-t + 3, h * 0.62), (-t + 3, h * 0.70), (-t + 7, h * 0.80),
           (-t + 10, h * 0.90), (-t + 12, h * 0.96), (-6, h), (0, h)]
    return pts


def cornice_profile(s=60):
    pts = [(0, 0), (0, -s)]
    for i in range(1, 9):                          # вогнутая галтель
        a = math.radians(90 * i / 8)
        pts.append((-s * (1 - math.cos(a)) * 0.85 - 4, -s + s * math.sin(a) * 0.85 + 2))
    pts += [(-s, -6), (-s, 0)]
    return pts


def casing_profile(w=70, t=12):
    return [(0, 0), (w, 0), (w, t * 0.55), (w - 4, t * 0.75), (w - 10, t), (w * 0.45, t), (w * 0.35, t * 0.8),
            (8, t * 0.8), (3, t * 0.5), (0, t * 0.45)]


# ---------------------------------------------------------------- фурнитура
def bar_handle(el, m, p, axis, out, L=160, h=28, r=6):
    """Скоба-ручка: центр p (3D), axis — направление ручки, out — наружу от фасада."""
    p, axis, out = np.asarray(p, float), np.asarray(axis, float), np.asarray(out, float)
    a = p - axis * L / 2
    b = p + axis * L / 2
    H.pipe(el, m, [a, a + out * h, b + out * h, b], r, bend=r * 2.5, n=12)


def knob(el, m, p, out, d=30):
    fr = H.axis_frame(out)
    H.lathe(el, m, [(0, 0), (d * 0.3, 0), (d * 0.22, d * 0.5), (d * 0.5, d * 0.85), (d * 0.45, d), (0, d * 1.02)], p, 24, frame=fr)


def lever_handle(el, m, p, out, along, L=125):
    """Дверная ручка: розетка + нажимная ручка (вдоль along), p — точка на поверхности полотна."""
    out = np.asarray(out, float)
    along = np.asarray(along, float)
    fr = H.axis_frame(out)
    H.lathe(el, m, [(0, 0), (26, 0), (26, 3), (22, 8), (12, 10), (0, 10)], p, 32, frame=fr)
    q0 = np.asarray(p, float) + out * 10
    q1 = q0 + out * 45
    q2 = q1 + along * L
    H.pipe(el, m, [q0, q1, q2], 9, bend=18, n=14)


# ---------------------------------------------------------------- рамки-молдинги на фасадах
def front_frames(el, m, plane_pt, n_out, ew, rows_w, rows_z, w=22, d=10):
    """Рамки молдингов (на ус) на плоскости фасада: plane_pt — точка плоскости, n_out — наружу,
    ew — горизонтальная ось вдоль фасада; rows_w — [(a, b)] вдоль ew (абсолютные координаты по оси ew),
    rows_z — [(z0, z1)]."""
    n_out = np.asarray(n_out, float)
    ew = np.asarray(ew, float)
    base = np.asarray(plane_pt, float)
    k = float(np.dot(base, ew))
    prof = [(u * w / 22.0 - w / 2, v * d / 17.0) for u, v in OGEE]
    for a, b in rows_w:
        for z0, z1 in rows_z:
            if b - a < 3 * w or z1 - z0 < 3 * w:
                continue
            def P(s, z):
                q = base + ew * (s - k)
                return (q[0], q[1], z)
            path = [P(a, z0), P(b, z0), P(b, z1), P(a, z1)]
            H.sweep_up(el, m, path, prof, n_out, closed_path=True)


# ---------------------------------------------------------------- построители предметов
def build_item(el, it, k, r, z, room, zf):
    f = BUILD.get(k)
    if not f:
        return False
    return f(el, it, r, z, room, zf) is not False


def _chair(el, it, r, z, room, zf):
    c = it['c']; ang = it['ang']
    nm = it.get('name', '').lower()
    if 'pouf' in it['key'] or 'пуф' in nm:
        zt = z[1]
        prof = [(0, 0), (190, 0), (205, 15), (215, 60), (218, zt - 70), (212, zt - 30), (195, zt - 8), (160, zt), (0, zt + 4)]
        H.lathe(el, 'FAB_CHAIR', prof, (c[0], c[1], 0), 64)
        H.lathe(el, 'BRASS', [(0, -1), (200, -1), (200, 12), (0, 12)], (c[0], c[1], 0), 64)
        H.sphere(el, 'FAB_CHAIR', (c[0], c[1], zt + 2), 12, 16)
        el.name = it.get('name') or 'Пуф'
        return
    if it.get('style') == 'office' or 'рабоч' in nm:
        _office_chair(el, it, c, ang, z)
        return
    a = math.radians(ang)
    ex = np.array([math.cos(a), math.sin(a), 0.0])
    ey = np.array([-math.sin(a), math.cos(a), 0.0])
    C = np.array([c[0], c[1], 0.0])

    def P(u, v, h):
        return C + ex * u + ey * v + np.array([0, 0, h])
    fab = 'FAB_CHAIR'
    wood = 'WALNUT'
    # ножки: передние — точёные конические, задние — саблевидные с продолжением в стойки спинки
    for v in (-185, 185):
        H.cone(el, wood, P(195, v * 1.03, 0), P(185, v, 430), 11, 17, 20)
        H.sphere(el, 'BRASS', P(195, v * 1.03, 6), 12, 16, sz=0.5)
        H.pipe(el, wood, [P(-215, v * 1.03, 0), P(-195, v, 420), P(-205, v, 600), P(-235, v * 0.98, 860)], 14, bend=120, n=14)
        H.sphere(el, 'BRASS', P(-215, v * 1.03, 6), 12, 16, sz=0.5)
    # царга
    H.rbox_f(el, wood, P(0, 0, 400), ex, ey, (0, 0, 1), 205, 190, 30, 6, 3)
    # сиденье
    H.rbox_f(el, fab, P(5, 0, 460), ex, ey, (0, 0, 1), 230, 225, 32, 26, 6)
    # спинка-полукресло: изогнутая мягкая панель
    ring = []
    for i in range(25):
        t = -1 + 2 * i / 24
        vv = 215 * t
        uu = -215 + 55 * (1 - t * t)
        ring.append((uu, vv))
    for h0, h1 in ((520, 870),):
        G = []
        for hz in np.linspace(h0, h1, 10):
            rowo, rowi = [], []
            k = 1 - ((hz - h0) / (h1 - h0) - 0.5) ** 2 * 0.25
            for uu, vv in ring:
                rowo.append(P(uu - 18 - (hz - h0) * 0.06, vv * k, hz))
            G.append(rowo)
        Gi = []
        for hz in np.linspace(h0, h1, 10):
            k = 1 - ((hz - h0) / (h1 - h0) - 0.5) ** 2 * 0.25
            Gi.append([P(uu + 22 - (hz - h0) * 0.06, vv * k, hz) for uu, vv in ring])
        H.add_grid(el, fab, G, orient='auto', center=P(80, 0, 700))
        H.add_grid(el, fab, Gi, orient='auto', center=P(-500, 0, 700))
        # кромки спинки
        H.add_grid(el, fab, [G[-1], Gi[-1]], orient='auto', center=P(-200, 0, 0))
        H.add_grid(el, fab, [G[0], Gi[0]], orient='auto', center=P(-200, 0, 2000))
        H.add_grid(el, fab, [[G[j][0] for j in range(len(G))], [Gi[j][0] for j in range(len(Gi))]], orient='auto', center=P(-200, 500, 700))
        H.add_grid(el, fab, [[G[j][-1] for j in range(len(G))], [Gi[j][-1] for j in range(len(Gi))]], orient='auto', center=P(-200, -500, 700))
    el.name = it.get('name') or 'Стул'


def _office_chair(el, it, c, ang, z):
    a = math.radians(ang)
    ex = np.array([math.cos(a), math.sin(a), 0.0])
    ey = np.array([-math.sin(a), math.cos(a), 0.0])
    C = np.array([c[0], c[1], 0.0])

    def P(u, v, h):
        return C + ex * u + ey * v + np.array([0, 0, h])
    for i in range(5):
        t = 2 * math.pi * i / 5
        d = ex * math.cos(t) + ey * math.sin(t)
        tip = C + d * 300
        H.pipe(el, 'GRAPHITE', [C + np.array([0, 0, 95]), tip + np.array([0, 0, 75])], 16, n=12)
        H.lathe(el, 'BLACK', [(0, 25), (28, 30), (30, 50), (22, 70), (0, 72)], tip + np.array([0, 0, 0]), 20)
        H.sphere(el, 'BLACK', tip + np.array([0, 0, 25]), 25, 18)
    H.lathe(el, 'GRAPHITE', [(0, 80), (40, 80), (40, 110), (22, 120), (22, 300), (16, 300), (16, 420), (0, 420)], C, 32)
    H.rbox_f(el, 'FAB_CHAIR', P(0, 0, 450), ex, ey, (0, 0, 1), 240, 235, 35, 30, 6)
    H.pipe(el, 'GRAPHITE', [P(-150, 0, 420), P(-250, 0, 430), P(-262, 0, 560)], 20, bend=60)
    H.rbox_f(el, 'FAB_CHAIR', P(-262, 0, 780), ex, ey, (0, 0, 1), 28, 220, 230, 26, 6)
    for v in (-245, 245):
        H.pipe(el, 'GRAPHITE', [P(-120, v * 0.9, 430), P(-110, v, 620), P(120, v, 640)], 12, bend=40)
        H.rbox_f(el, 'BLACK', P(20, v, 650), ex, ey, (0, 0, 1), 120, 25, 12, 10, 4)
    el.name = it.get('name') or 'Кресло рабочее'


def offset_poly(poly, d):
    """Смещение многоугольника внутрь на d (миттер; для малых d), контур против часовой."""
    P = [np.asarray(p, float) for p in poly]
    A = sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
    if A < 0:
        P = P[::-1]
    n = len(P)
    out = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        d1 = (b - a) / (np.linalg.norm(b - a) or 1)
        d2 = (c - b) / (np.linalg.norm(c - b) or 1)
        n1 = np.array([-d1[1], d1[0]])
        n2 = np.array([-d2[1], d2[0]])
        mv = (n1 + n2) / (1 + float(np.dot(n1, n2)))
        out.append(tuple(b + mv * d))
    return out


def rslab(el, m, poly, z0, z1, r, seg=4):
    """Мягкая призма по многоугольнику со скруглёнными кромками (подушки, корпуса мягкой мебели)."""
    r = min(r, (z1 - z0) / 2 - 0.5)
    rings = []
    for i in range(seg + 1):
        t = math.radians(90 * i / seg)
        rings.append((r * (1 - math.sin(t)), z0 + r * (1 - math.cos(t))))
    for i in range(seg + 1):
        t = math.radians(90 * i / seg)
        rings.append((r * (1 - math.cos(t)), z1 - r + r * math.sin(t)))
    G = []
    for dd, zz in rings:
        op = offset_poly(poly, dd)
        G.append([(p[0], p[1], zz) for p in op])
    cen = list(np.mean(np.asarray(poly, float), 0)) + [(z0 + z1) / 2]
    H.add_grid(el, m, G, closed_u=True, orient='auto', center=cen)
    top = offset_poly(poly, r)
    from ifc.m3d import ear_clip
    for zz, up in ((z1, True), (z0, False)):
        pts = top
        A = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        if A < 0:
            pts = pts[::-1]
        tris = ear_clip(pts)
        part = el.part(m)
        tw, th = MATS[m].tile
        for (i, j, k) in tris:
            q = [(pts[i][0], pts[i][1], zz), (pts[j][0], pts[j][1], zz), (pts[k][0], pts[k][1], zz)]
            if not up:
                q = q[::-1]
            part.face(q, [(p[1] / tw, p[0] / th) for p in q])


def _sofa(el, it, r, z, room, zf):
    if 'pts' not in it or not it.get('lines'):
        return False
    from ifc.scene3d import _left_inside
    pts = [tuple(p) for p in it['pts']]
    fab = fabric_mat(it['fabric_col']) if it.get('fabric_col') else 'FAB_TAUPE'
    l0 = [tuple(p) for p in it['lines'][0]]
    nb = len(l0)
    back = pts[:nb] + l0[::-1]
    front = pts[nb:]                       # от конца у b[-1] к началу
    seat = l0 + front
    # ножки
    for p in offset_poly(pts, 70):
        H.cone(el, 'BRASS', (p[0], p[1], 0), (p[0], p[1], 90), 14, 20, 20)
    rslab(el, 'BLACK', offset_poly(pts, 40), 80, 110, 8)
    rslab(el, fab, pts, 110, 400, 30, 5)                                # корпус
    rslab(el, fab, back, 400, z[1], 45, 6)                               # спинка
    # подушки сиденья по сегментам (на ус в углу)
    fr = front[::-1]
    for i in range(nb - 1):
        q = [l0[i], l0[i + 1], fr[i + 1], fr[i]]
        rslab(el, fab, offset_poly(q, 8), 400, 540, 45, 6)
    # подушки спинки
    for i in range(nb - 1):
        a, b = l0[i], l0[i + 1]
        L_ = math.hypot(b[0] - a[0], b[1] - a[1])
        nseg = max(1, int(round(L_ / 750)))
        side = 1 if _left_inside(a, b, seat) else -1
        for j in range(nseg):
            pa = (a[0] + (b[0] - a[0]) * (j + 0.03) / nseg, a[1] + (b[1] - a[1]) * (j + 0.03) / nseg)
            pb = (a[0] + (b[0] - a[0]) * (j + 0.97) / nseg, a[1] + (b[1] - a[1]) * (j + 0.97) / nseg)
            w0, w1 = (0, 190) if side > 0 else (-190, 0)
            H.rbox_seg(el, fab, pa, pb, w0, w1, 540, z[1] - 20, 70, 6)
    # декоративные подушки в углу
    if nb >= 3:
        cpt = np.asarray(l0[1])
        for j, (a, b) in enumerate(((l0[0], l0[1]), (l0[1], l0[2]))):
            d = np.asarray(b) - np.asarray(a)
            d = d / np.linalg.norm(d)
            pc = cpt - d * 330 if j == 0 else cpt + d * 330
            n = np.array([-d[1], d[0]])
            if not _left_inside(tuple(a), tuple(b), seat):
                n = -n
            pc = pc + n * 230
            H.rbox_f(el, 'FAB_LINEN', (pc[0], pc[1], 700), (d[0], d[1], 0), (n[0] * 0.95, n[1] * 0.95, -0.3), (0, 0, 1),
                     220, 70, 200, 65, 6)
    el.name = it.get('name') or 'Диван угловой'


def _bed(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    head = it.get('head', 'S')
    k = it['kind']
    hb = z[1] if isinstance(z, tuple) and z[1] > 600 else (1100 if k == 'bed' else 900)
    fab = fabric_mat(it['fabric_col']) if it.get('fabric_col') else 'FAB_GREY'
    if head in ('W', 'E'):
        L_, sg, h0 = x1 - x0, (1 if head == 'W' else -1), (x0 if head == 'W' else x1)
        wlo, whi = y0, y1
        eu, ew = (sg, 0, 0), (0, 1, 0)

        def C(u, w, zz):
            return (h0 + sg * u, w, zz)
    else:
        L_, sg, h0 = y1 - y0, (1 if head == 'S' else -1), (y0 if head == 'S' else y1)
        wlo, whi = x0, x1
        eu, ew = (0, sg, 0), (1, 0, 0)

        def C(u, w, zz):
            return (w, h0 + sg * u, zz)

    def RB(m, u0, u1, w0, w1, za, zb, rr, seg=5):
        H.rbox_f(el, m, C((u0 + u1) / 2, (w0 + w1) / 2, (za + zb) / 2), eu, ew, (0, 0, 1),
                 abs(u1 - u0) / 2, abs(w1 - w0) / 2, abs(zb - za) / 2, rr, seg)
    wm = (wlo + whi) / 2
    # ножки
    for u in (160, L_ - 80):
        for w in (wlo + 80, whi - 80):
            H.cone(el, 'BRASS', C(u, w, 0), C(u, w, 90), 16, 22, 20)
    RB(fab, 90, L_, wlo, whi, 90, 330, 30)                                 # царга
    RB('MATTRESS', 110, L_ - 15, wlo + 15, whi - 15, 330, 540, 45, 6)       # матрас
    RB('FAB_LINEN', 700, L_ + 10, wlo - 12, whi + 12, 470, 585, 50, 6)    # одеяло
    RB('FAB_LINEN', 700, 900, wlo - 14, whi + 14, 575, 600, 12, 4)       # отворот
    # изголовье: каретная / вертикальная стёжка каналами
    RB(fab, 0, 60, wlo - 30, whi + 30, 0, hb - 40, 12)
    nch = max(5, int((whi - wlo + 60) / 150))
    cw = (whi - wlo + 40) / nch
    for i in range(nch):
        a = wlo - 20 + i * cw
        RB(fab, 50, 105, a + 2, a + cw - 2, 320, hb, 26, 6)
    # подушки
    width = whi - wlo
    npl = 2 if width > 1200 else 1
    pw = (width - 120) / npl
    for i in range(npl):
        a = wlo + 60 + i * pw
        RB('MATTRESS', 130, 470, a + 15, a + pw - 15, 540, 690, 70, 6)
    if npl == 2:
        RB('FAB_LINEN', 380, 540, wm - 230, wm + 230, 560, 720, 70, 6)        # декоративная подушка
    el.props['Изголовье'] = f'мягкое, вертикальная стёжка, h={hb:.0f}'


def _bench(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    from ifc.scene3d import fmat
    m = fmat(it.get('mat'), 'WALNUT')
    fab = fabric_mat(it['fabric_col']) if it.get('fabric_col') else 'FAB_OLIVE'
    for px, py in ((x0 + 40, y0 + 40), (x1 - 40, y0 + 40), (x0 + 40, y1 - 40), (x1 - 40, y1 - 40)):
        H.cone(el, m, (px, py, 0), (px, py, 345), 13, 20, 20)
        H.lathe(el, 'BRASS', [(0, 0), (15, 0), (15, 25), (13, 30), (0, 30)], (px, py, 0), 20)
    H.rbox(el, m, x0, y0, 330, x1, y1, 380, 6)
    H.rbox(el, m, x0 + 50, y0 + 50, 130, x1 - 50, y1 - 50, 150, 4)
    H.rbox(el, fab, x0 + 8, y0 + 8, 378, x1 - 8, y1 - 8, 455, 30, 6)
    el.name = it.get('name') or 'Банкетка'


def _round(el, it, r, z, room, zf):
    c = it['c']; R = it['r']; zt = z[1]
    top = 'MARBLE' if it.get('pal') == 'marble' else 'OAK'
    H.lathe(el, top, [(0, zt - 25), (R - 6, zt - 25), (R, zt - 19), (R, zt - 6), (R - 6, zt), (0, zt)], (c[0], c[1], 0), 96,
            uv='planar')
    if R > 350:            # обеденный: пьедестал-тюльпан
        prof = [(0, 0), (260, 0), (262, 12), (200, 30), (120, 70), (70, 160), (55, 400), (60, zt - 120), (110, zt - 60),
                (160, zt - 30), (0, zt - 30)]
    else:
        prof = [(0, 0), (150, 0), (152, 10), (90, 30), (25, 80), (20, zt - 60), (60, zt - 30), (0, zt - 30)]
    H.lathe(el, 'BRASS', prof, (c[0], c[1], 0), 64)


def _tv(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    fr = front_of(r, room)
    H.rbox(el, 'BLACK', x0, y0, z[0], x1, y1, z[1], 6, 4)
    # экран
    if fr in ('+y', '-y'):
        yf = y1 if fr == '+y' else y0
        box(el, 'SCREEN', x0 + 10, min(yf, yf + (1 if fr == '+y' else -1)), z[0] + 10, x1 - 10, max(yf, yf + (1 if fr == '+y' else -1)), z[1] - 10)
    else:
        xf = x1 if fr == '+x' else x0
        box(el, 'SCREEN', min(xf, xf + (1 if fr == '+x' else -1)), y0 + 10, z[0] + 10, max(xf, xf + (1 if fr == '+x' else -1)), y1 - 10, z[1] - 10)


def _ac(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    fr = front_of(r, room)
    sd = front_sd(fr)
    face, (u0, u1), (w0, w1) = rect_local(r, sd)
    dep = u1 - u0
    h = z[1] - z[0]
    # профиль внутреннего блока (u — от стены, v — высота)
    prof = [(0, 0), (dep * 0.55, 0), (dep * 0.8, h * 0.06), (dep * 0.96, h * 0.25), (dep, h * 0.5), (dep * 0.97, h * 0.8),
            (dep * 0.85, h * 0.95), (dep * 0.6, h), (0, h)]
    eu, ew, ez = wall_frame(sd)
    eu, ew = np.asarray(eu, float), np.asarray(ew, float)
    base = np.array(list(lw(sd, face, 0, 0)) + [0.0])
    rings = []
    for wv in (w0, w1):
        rings.append([base + eu * u + ew * wv + np.array([0, 0, z[0] + v]) for u, v in prof])
    G = [list(x) for x in zip(*rings)]
    H.add_grid(el, 'WHITE', [rings[0], rings[1]], closed_u=True, orient='auto',
               center=base + eu * dep / 2 + ew * (w0 + w1) / 2 + np.array([0, 0, z[0] + h / 2]))
    H.cap(el, 'WHITE', rings[0], normal=-ew)
    H.cap(el, 'WHITE', rings[1], normal=ew)
    # жалюзи выдува
    for i in range(4):
        zz = z[0] + 18 + i * 9
        lrbox(el, 'GRAPHITE', sd, face, dep * 0.45, dep * 0.85, w0 + 60, w1 - 60, zz, zz + 3, 1, 2)
    el.name = (it.get('name') or 'Внутренний блок сплит-системы') + ' (существующий — проверить)'
    el.props['Статус'] = 'существующий, проверить'


def _towel(el, it, r, z, room, zf):
    from ifc.scene3d import side_of
    sd = side_of(r, room)
    face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
    w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))

    def P(u, w, zz):
        x, y = lw(sd, face, u, w)
        return (x, y, zz)
    for w in (w0 + 14, w1 - 14):
        H.pipe(el, 'NICKEL', [P(55, w, z[0]), P(55, w, z[1])], 14, n=20)
        H.sphere(el, 'NICKEL', P(55, w, z[1]), 14, 20)
        H.sphere(el, 'NICKEL', P(55, w, z[0]), 14, 20)
        for zz in (z[0] + 90, z[1] - 90):
            H.pipe(el, 'NICKEL', [P(0, w, zz), P(55, w, zz)], 9, n=14)
            fr = H.axis_frame(np.asarray(P(1, w, zz)) - np.asarray(P(0, w, zz)))
            H.lathe(el, 'NICKEL', [(0, 0), (28, 0), (28, 6), (14, 12), (0, 12)], P(0, w, zz), 24, frame=fr)
    zz = z[0] + 60
    while zz < z[1] - 40:
        H.pipe(el, 'NICKEL', [P(55, w0 + 14, zz), P(55, w1 - 14, zz)], 10, n=14, caps=False)
        zz += 95
    el.name = 'Полотенцесушитель электрический (сатин-никель)'


def _radiator(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    along_x = (x1 - x0) > (y1 - y0)
    L_ = (x1 - x0) if along_x else (y1 - y0)
    n = max(4, int(L_ / 80))
    for i in range(n):
        s = ((x0 if along_x else y0) + (i + 0.5) * L_ / n)
        for d in (0.3, 0.7):
            if along_x:
                q = (s, y0 + (y1 - y0) * d)
            else:
                q = (x0 + (x1 - x0) * d, s)
            H.pipe(el, 'WHITE', [(q[0], q[1], z[0] + 15), (q[0], q[1], z[1] - 15)], 13, n=14)
            H.sphere(el, 'WHITE', (q[0], q[1], z[1] - 15), 13, 14)
            H.sphere(el, 'WHITE', (q[0], q[1], z[0] + 15), 13, 14)
        # пластины секции
        if along_x:
            box(el, 'WHITE', s - 20, y0 + 25, z[0] + 40, s + 20, y1 - 25, z[1] - 40)
        else:
            box(el, 'WHITE', x0 + 25, s - 20, z[0] + 40, x1 - 25, s + 20, z[1] - 40)
    for zz in (z[0] + 30, z[1] - 30):
        if along_x:
            H.pipe(el, 'WHITE', [(x0, (y0 + y1) / 2, zz), (x1, (y0 + y1) / 2, zz)], 16, n=14)
        else:
            H.pipe(el, 'WHITE', [((x0 + x1) / 2, y0, zz), ((x0 + x1) / 2, y1, zz)], 16, n=14)
    el.props['Статус'] = 'существующий (система отопления дома)'


def _mirror(el, it, r, z, room, zf):
    from ifc.scene3d import _zone_code_at, fin_t
    fr0 = front_of(r, room)
    code = _zone_code_at(room, ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), (z[0] + z[1]) / 2)
    t0 = fin_t(code) if code and code != 'X' else 0
    sh = {'+x': (t0, 0), '-x': (-t0, 0), '+y': (0, t0), '-y': (0, -t0)}[fr0]
    r = (r[0] + sh[0], r[1] + sh[1], r[2] + sh[0], r[3] + sh[1])
    x0, y0, x1, y1 = r
    n_out = {'+x': (1, 0, 0), '-x': (-1, 0, 0), '+y': (0, 1, 0), '-y': (0, -1, 0)}[fr0]
    wet = D.ROOM[room].get('zone') == 'wet'
    # на буазери зеркало висит на дистанционных держателях поверх молдингов (молдинги не проходят сквозь стекло)
    so = 22 if (code and D.mat(code).get('style') == 'boiserie') else 0
    th = 6 if not wet else (x1 - x0 if (x1 - x0) < (y1 - y0) else y1 - y0)
    # плоскость стены (чистовая поверхность) и стекло
    if fr0 in ('+x', '-x'):
        wf = (r[0] if fr0 == '+x' else r[2])
        g0, g1 = wf + n_out[0] * so, wf + n_out[0] * (so + th)
        H.rbox(el, 'MIRROR', min(g0, g1), y0, z[0], max(g0, g1), y1, z[1], 1.5, 2)
    else:
        wf = (r[1] if fr0 == '+y' else r[3])
        g0, g1 = wf + n_out[1] * so, wf + n_out[1] * (so + th)
        H.rbox(el, 'MIRROR', x0, min(g0, g1), z[0], x1, max(g0, g1), z[1], 1.5, 2)
    if not wet:                                  # латунная багетная рама: от стены до лицевой плоскости стекла
        D_ = so + th + 8
        prof = [(-16, 0), (16, 0), (16, D_ - 7), (12, D_ - 2), (4, D_), (-6, D_ - 1), (-12, D_ - 4), (-16, D_ - 10)]
        if fr0 in ('+x', '-x'):
            path = [(wf, y0 - 12, z[0] - 12), (wf, y1 + 12, z[0] - 12), (wf, y1 + 12, z[1] + 12), (wf, y0 - 12, z[1] + 12)]
        else:
            path = [(x0 - 12, wf, z[0] - 12), (x1 + 12, wf, z[0] - 12), (x1 + 12, wf, z[1] + 12), (x0 - 12, wf, z[1] + 12)]
        H.sweep_up(el, 'BRASS', path, prof, n_out, closed_path=True, smooth=True)
        if so:
            el.props['Монтаж'] = f'на дистанционных держателях {so} мм поверх молдингов буазери'
    else:                                         # LED-подсветка по контуру (сзади)
        if (x1 - x0) < (y1 - y0):
            box(el, 'LED', x0, y0 + 30, z[0] + 30, x1, y0 + 34, z[1] - 30)
            box(el, 'LED', x0, y1 - 34, z[0] + 30, x1, y1 - 30, z[1] - 30)


def _desk(el, it, r, z, room, zf):
    from ifc.scene3d import fmat
    x0, y0, x1, y1 = r
    m = fmat(it.get('mat'), 'OAK')
    H.rbox(el, m, x0, y0, z[1] - 30, x1, y1, z[1], 4, 3)
    if (y1 - y0) >= (x1 - x0):
        H.rbox(el, m, x0 + 10, y0, 0, x1 - 10, y0 + 25, z[1] - 30, 3, 3)
        H.rbox(el, m, x0 + 10, y1 - 25, 0, x1 - 10, y1, z[1] - 30, 3, 3)
        H.rbox(el, m, x0 + 20, y0 + 25, z[1] - 180, x0 + 38, y1 - 25, z[1] - 30, 2, 2)
        # тумба с ящиками у одной опоры
        H.rbox(el, m, x0 + 20, y1 - 470, z[1] - 200, x1 - 20, y1 - 25, z[1] - 32, 3, 3)
        fr = front_of(r, room)
        xf = x1 if fr == '+x' else x0
        knob(el, 'BRASS', (xf, y1 - 247, z[1] - 115), (1 if fr == '+x' else -1, 0, 0), 26)
    else:
        H.rbox(el, m, x0, y0 + 10, 0, x0 + 25, y1 - 10, z[1] - 30, 3, 3)
        H.rbox(el, m, x1 - 25, y0 + 10, 0, x1, y1 - 10, z[1] - 30, 3, 3)
        H.rbox(el, m, x0 + 25, y0 + 20, z[1] - 180, x1 - 25, y0 + 38, z[1] - 30, 2, 2)
        fr = front_of(r, room)
        if fr in ('+y', '-y'):
            yf = y1 if fr == '+y' else y0
            H.rbox(el, m, x0 + 40, y0 + 40, z[1] - 140, x1 - 40, y1 - 40, z[1] - 32, 3, 3)
            knob(el, 'BRASS', ((x0 + x1) / 2, yf, z[1] - 85), (0, 1 if fr == '+y' else -1, 0), 26)


BUILD = {'chair': _chair, 'sofa': _sofa, 'bed': _bed, 'bed_single': _bed, 'bench': _bench, 'round': _round,
         'tv': _tv, 'ac': _ac, 'towel': _towel, 'radiator': _radiator, 'mirror': _mirror, 'desk': _desk}


# ---------------------------------------------------------------- сантехника
def _wc(el, it, r, z, room, zf):
    sd, face, ax = it['wall'], it['face'], it['axis']
    off = 10                                   # облицовка короба

    def P(u, w, zz):
        x, y = lw(sd, face, u + off, w + ax)
        return (x, y, zz)
    N = 72
    # внешняя чаша: кольца в плане (u — от короба, w — поперёк), форма «яйцо», низ — сужение
    def ring(a, b, uc, zz, e=2.4, egg=0.12):
        pts = []
        for i in range(N):
            t = 2 * math.pi * i / N
            ct, st = math.cos(t), math.sin(t)
            u = a * math.copysign(abs(ct) ** (2 / e), ct)
            w = b * math.copysign(abs(st) ** (2 / e), st) * (1 - egg * ct)
            pts.append(P(uc + u, w, zz))
        return pts
    outer = [ring(150, 115, 200, 280, 2.8), ring(215, 160, 265, 300), ring(255, 178, 290, 340), ring(268, 182, 300, 385),
             ring(270, 183, 300, 398)]
    rim = [ring(262, 176, 300, 404), ring(230, 150, 305, 405)]
    inner = [ring(222, 142, 307, 398), ring(190, 118, 315, 360), ring(120, 72, 330, 300), ring(55, 40, 340, 255)]
    H.add_grid(el, 'CERAMIC', outer + rim + inner, closed_u=True, orient='keep')
    H.cap(el, 'CERAMIC', outer[0], normal=(0, 0, -1))
    H.cap(el, 'CERAMIC', inner[-1], normal=(0, 0, 1))
    # хвостовик к коробу
    lrbox(el, 'CERAMIC', sd, face, off, off + 120, ax - 150, ax + 150, 290, 400, 30, 5)
    # сиденье и крышка (тонкие лофты)
    seat = [ring(268, 182, 300, 406), ring(268, 182, 300, 418), ring(200, 128, 310, 418), ring(200, 128, 310, 406)]
    H.add_grid(el, 'WHITE', seat + [seat[0]], closed_u=True, orient='keep')
    lid = [ring(262, 178, 302, 422), ring(266, 180, 302, 432), ring(258, 174, 302, 442), ring(180, 120, 302, 446)]
    H.add_grid(el, 'WHITE', lid, closed_u=True, orient='keep')
    H.cap(el, 'WHITE', lid[-1], normal=(0, 0, 1))
    # клавиша смыва (латунь матовая, две клавиши)
    lrbox(el, 'BRASS', sd, face, 0, off + 8, ax - 125, ax + 125, 1000, 1160, 3, 3)
    lrbox(el, 'BRASS', sd, face, off + 6, off + 12, ax - 115, ax - 3, 1012, 1148, 3, 3)
    lrbox(el, 'BRASS', sd, face, off + 6, off + 12, ax + 3, ax + 115, 1012, 1148, 3, 3)
    el.name = 'Унитаз подвесной безободковый с сиденьем микролифт; клавиша смыва — латунь матовая'


def _faucet(el, m, base, up_h, spout_L, dir_, lever=True):
    """Смеситель: корпус-цилиндр, излив-гусак (dir_ — направление излива в плане), рычаг."""
    base = np.asarray(base, float)
    d = np.asarray(list(dir_) + [0.0], float)
    d = d / np.linalg.norm(d)
    H.lathe(el, m, [(0, 0), (28, 0), (28, 4), (22, 8), (20, up_h * 0.55), (0, up_h * 0.55)], base, 32)
    p0 = base + np.array([0, 0, up_h * 0.5])
    p1 = base + np.array([0, 0, up_h])
    p2 = p1 + d * spout_L
    p3 = p2 - np.array([0, 0, 45])
    H.pipe(el, m, [p0, p1, p2, p3], 12, bend=60, n=20)
    H.lathe(el, m, [(0, -6), (13, -6), (13, 0), (0, 0)], p3, 20)
    if lever:
        side = np.array([-d[1], d[0], 0.0])
        q0 = base + np.array([0, 0, up_h * 0.35]) + side * 20
        H.pipe(el, m, [q0, q0 + side * 25, q0 + side * 25 - d * 70 + np.array([0, 0, 25])], 7, bend=20, n=12)


def _vanity(el, it, r, z, room, zf):
    from ifc.scene3d import fmat
    sd, face, ax_ = it['wall'], it['face'], it['axis']
    dep, wd = it.get('depth', 460), it.get('width', 600)
    vm = fmat(it.get('mat'), 'WALNUT')
    zt = z[1]
    lrbox(el, vm, sd, face, 0, dep - 20, ax_ - wd / 2, ax_ + wd / 2, z[0], zt - 160, 3, 3)      # корпус (под чашей — полость)
    for wa, wb in ((ax_ - wd / 2, ax_ - wd / 2 + 18), (ax_ + wd / 2 - 18, ax_ + wd / 2)):
        lrbox(el, vm, sd, face, 0, dep - 20, wa, wb, zt - 165, zt - 20, 2, 2)
    lrbox(el, vm, sd, face, 0, 18, ax_ - wd / 2, ax_ + wd / 2, zt - 165, zt - 20, 2, 2)
    zm = (z[0] + zt - 20) / 2
    for za, zb in ((z[0] + 3, zm - 2), (zm + 2, zt - 23)):
        lrbox(el, vm, sd, face, dep - 21, dep, ax_ - wd / 2 + 2, ax_ + wd / 2 - 2, za, zb, 3, 3)
        eu, ew, _ = wall_frame(sd)
        x, y = lw(sd, face, dep, ax_)
        bar_handle(el, 'BRASS', (x, y, zb - 45), ew, eu, L=160, h=26, r=5)
    # столешница с интегрированной чашей (литой мрамор/керамика)
    N = 96
    eu, ew, _ = wall_frame(sd)

    def ring(a, b, uc, zz, e):
        out = []
        for i in range(N):
            t = 2 * math.pi * i / N
            ct, st = math.cos(t), math.sin(t)
            u = a * math.copysign(abs(ct) ** (2 / e), ct)
            w = b * math.copysign(abs(st) ** (2 / e), st)
            x, y = lw(sd, face, uc + u, ax_ + w)
            out.append((x, y, zz))
        return out
    ho, wo = (dep + 10) / 2, wd / 2 + 5
    rings = [ring(ho, wo, ho, zt - 20, 14), ring(ho, wo, ho, zt - 3, 14), ring(ho - 3, wo - 3, ho, zt, 14),
             ring(ho - 75, wo - 90, ho + 20, zt, 6), ring(ho - 80, wo - 95, ho + 20, zt - 6, 6),
             ring(ho - 100, wo - 115, ho + 25, zt - 70, 4), ring(ho - 140, wo - 160, ho + 30, zt - 125, 3),
             ring(ho - 175, wo - 205, ho + 35, zt - 140, 2.5)]
    H.add_grid(el, 'CERAMIC', rings, closed_u=True, orient='keep')
    H.cap(el, 'CERAMIC', rings[0], normal=(0, 0, -1))
    H.cap(el, 'CERAMIC', rings[-1], normal=(0, 0, 1))
    x, y = lw(sd, face, ho + 35, ax_)
    H.lathe(el, 'NICKEL', [(0, 0), (22, 0), (22, 2), (0, 3)], (x, y, zt - 141), 32)
    # смеситель на столешнице
    xb, yb = lw(sd, face, 60, ax_)
    _faucet(el, 'NICKEL', (xb, yb, zt), 250, 150, (eu[0], eu[1]))
    el.name = 'Тумба подвесная с интегрированной раковиной, смеситель высокий (сатин-никель)'


def _bath(el, it, r, z, room, zf):
    from ifc.scene3d import mkey, _front_dir
    x0, y0, x1, y1 = r
    zt = z[1] if isinstance(z, tuple) else 600
    fr = _front_dir(r, room)
    ap = it.get('apron')
    am = mkey(ap) if ap and mkey(ap) in MATS else 'C1'
    # экран под плиткой с нишей для стоп
    if fr in ('+y', '-y'):
        yf = y1 if fr == '+y' else y0
        sg = 1 if fr == '+y' else -1
        box(el, am, x0, yf - sg * 30, 90, x1, yf, zt - 40)
        box(el, am, x0, yf - sg * 90, 0, x1, yf - sg * 60, 90)
        H.rbox(el, 'STEEL', (x0 + x1) / 2 + 400, yf, 130, (x0 + x1) / 2 + 700, yf + sg * 2, 330, 1, 2)
    else:
        xf = x1 if fr == '+x' else x0
        sg = 1 if fr == '+x' else -1
        box(el, am, xf - sg * 30, y0, 90, xf, y1, zt - 40)
        box(el, am, xf - sg * 90, y0, 0, xf - sg * 60, y1, 90)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    a, b = (x1 - x0) / 2, (y1 - y0) / 2
    N = 128
    de = it.get('drain', 'E')
    shift = 40 if de == 'E' else -40                       # чаша смещена от слива

    def ring(aa, bb, zz, e, sx=0.0):
        return H.superellipse(cx + sx, cy, aa, bb, e, N, zz)
    rings = [ring(a, b, zt - 40, 30), ring(a, b, zt - 3, 30), ring(a - 3, b - 3, zt, 30),
             ring(a - 70, b - 60, zt, 8, -shift * 0.3), ring(a - 78, b - 66, zt - 10, 7, -shift * 0.3),
             ring(a - 95, b - 85, zt - 120, 5, -shift * 0.5), ring(a - 140, b - 120, zt - 330, 4, -shift),
             ring(a - 230, b - 175, zt - 420, 3, -shift), ring(a - 300, b - 215, zt - 430, 2.6, -shift)]
    H.add_grid(el, 'ACRYL', rings, closed_u=True, orient='keep')
    H.cap(el, 'ACRYL', rings[-1], normal=(0, 0, 1))
    # слив-перелив и смеситель на борту у слива
    zb = zt - 430
    if de in ('E', 'W'):
        sgd = 1 if de == 'E' else -1
        xd = cx + sgd * (a - 160)
        H.lathe(el, 'NICKEL', [(0, 0), (35, 0), (35, 2), (0, 3)], (xd, cy, zb + 1), 32)
        xo = cx + sgd * (a - 92)
        fr_ = H.axis_frame((-sgd, 0, 0))
        H.lathe(el, 'NICKEL', [(0, 0), (34, 0), (34, 4), (0, 6)], (xo, cy, zt - 120), 32, frame=fr_)
        xm = x1 - 45 if de == 'E' else x0 + 45
        _faucet(el, 'NICKEL', (xm, cy, zt), 120, 170, (-sgd, 0), lever=False)
        for dy in (-115, 115):
            H.lathe(el, 'NICKEL', [(0, 0), (25, 0), (25, 3), (18, 8), (16, 55), (0, 58)], (xm, cy + dy, zt), 24)
            H.pipe(el, 'NICKEL', [(xm, cy + dy, zt + 50), (xm - sgd * 70, cy + dy, zt + 62)], 6, n=12)
        H.lathe(el, 'NICKEL', [(0, 0), (22, 0), (22, 5), (16, 15), (14, 160), (24, 185), (28, 215), (0, 222)], (xm, cy + 200, zt), 24)
    el.name = 'Ванна встроенная 1800×800, санитарный акрил; смеситель врезной на борт (3 отв. + лейка), экран под плитку с люком'
    el.props['Отметка борта'] = f'+{zt:.0f}'


def _shower(el, it, r, z, room, zf):
    from ifc.scene3d import _point_side
    cx, cy = it['c']
    sd = ({(1, 0): 'W', (-1, 0): 'E', (0, 1): 'S', (0, -1): 'N'}.get(tuple(it['n'])) if it.get('n')
          else _point_side(it['c'], room))
    face = cx if sd in ('W', 'E') else cy
    w = cy if sd in ('W', 'E') else cx
    zt = z[1] if isinstance(z, tuple) else 2150

    def P(u, ww, zz):
        x, y = lw(sd, face, u, ww)
        return (x, y, zz)
    eu, ew, _ = wall_frame(sd)
    # термостат: горизонтальный корпус с рукоятками
    H.pipe(el, 'NICKEL', [P(55, w - 150, 1100), P(55, w + 150, 1100)], 32, n=32)
    for ww, sg in ((w - 150, -1), (w + 150, 1)):
        fr = H.axis_frame(np.asarray(ew) * sg)
        H.lathe(el, 'NICKEL', [(0, 0), (34, 0), (36, 10), (36, 40), (30, 48), (0, 50)], P(55, ww, 1100), 32, frame=fr)
    for ww in (w - 110, w + 110):
        H.pipe(el, 'NICKEL', [P(0, ww, 1100), P(55, ww, 1100)], 14, n=16)
    # стойка, кронштейн, верхний душ
    H.pipe(el, 'NICKEL', [P(55, w, 1130), P(55, w, zt - 40), P(55, w, zt), P(330, w, zt)], 12, bend=40, n=20)
    H.pipe(el, 'NICKEL', [P(0, w, 1600), P(55, w, 1600)], 8, n=12)
    hx, hy = lw(sd, face, 330, w)
    H.lathe(el, 'NICKEL', [(0, zt - 30), (120, zt - 30), (125, zt - 26), (125, zt - 20), (110, zt - 14), (20, zt - 10), (0, zt - 10)],
            (hx, hy, 0), 64)
    for rr in (40, 70, 100):                                   # форсунки — кольцами
        n_ = int(2 * math.pi * rr / 14)
        for k_ in range(n_):
            a_ = 2 * math.pi * k_ / n_
            H.lathe(el, 'GRAPHITE', [(0, -1.2), (2.2, -1.2), (2.2, 0), (0, 0)], (hx + rr * math.cos(a_), hy + rr * math.sin(a_), zt - 30), 8)
    # ручная лейка на держателе + шланг
    H.lathe(el, 'NICKEL', [(0, 0), (20, 0), (24, 25), (40, 210), (38, 240), (0, 245)], P(95, w + 60, 1300), 32)
    H.pipe(el, 'GRAPHITE', [P(95, w + 60, 1300), P(140, w + 90, 1150), P(110, w + 110, 1040), P(60, w + 110, 1080)], 8, bend=80, n=12)
    el.name = 'Душевая система с термостатом, верхний душ Ø250, ручная лейка (сатин-никель)'


def _drain(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    H.rbox(el, 'NICKEL', x0, y0, zf - 2, x1, y1, zf + 0.5, 1, 2)
    box(el, 'STEEL', x0 + 15, y0 + 15, zf - 60, x1 - 15, y1 - 15, zf - 2)
    along_x = (x1 - x0) > (y1 - y0)
    L_ = max(x1 - x0, y1 - y0)
    n = int((L_ - 40) / 14)
    for i in range(n):
        s = (x0 if along_x else y0) + 20 + i * 14
        if along_x:
            box(el, 'GRAPHITE', s, y0 + 12, zf + 0.5, s + 6, y1 - 12, zf + 0.7)
        else:
            box(el, 'GRAPHITE', x0 + 12, s, zf + 0.5, x1 - 12, s + 6, zf + 0.7)
    el.name = 'Трап линейный пристенный ' + f'{L_:.0f}' + ' (решётка сатин)'


def _glass(el, it, r, z, room, zf):
    x0, y0, x1, y1 = r
    if (x1 - x0) < (y1 - y0):
        H.rbox(el, 'GLASS_SH', x0 + 3, y0 + 12, z[0] + 12, x1 - 3, y1, z[1], 2, 2)
        H.rbox(el, 'NICKEL', x0 - 6, y0, z[0], x1 + 6, y0 + 18, z[1], 2, 2)
        H.rbox(el, 'NICKEL', x0 - 4, y0 + 12, z[0], x1 + 4, y1, z[0] + 14, 2, 2)
    else:
        H.rbox(el, 'GLASS_SH', x0 + 12, y0 + 3, z[0] + 12, x1, y1 - 3, z[1], 2, 2)
        H.rbox(el, 'NICKEL', x0, y0 - 6, z[0], x0 + 18, y1 + 6, z[1], 2, 2)
        H.rbox(el, 'NICKEL', x0 + 12, y0 - 4, z[0], x1, y1 + 4, z[0] + 14, 2, 2)
    el.props['Описание'] = 'Стекло закалённое 8 мм, пристенный и нижний профиль, сатин-никель'


BUILD.update({'wc': _wc, 'vanity': _vanity, 'bath': _bath, 'shower': _shower, 'drain': _drain, 'glass': _glass})


# ---------------------------------------------------------------- светильники
def light(el, L, k, zc):
    """Многополигональные светильники; True — построено."""
    if k in ('spot', 'spot44', 'spot65'):
        x, y = L['p']
        m = 'BLACK' if k == 'spot' else 'WHITE'
        H.lathe(el, m, [(0, zc - 2), (44, zc - 2), (46, zc + 1), (40, zc + 2), (36, zc - 4), (30, zc - 30), (24, zc - 60),
                        (0, zc - 60)], (x, y, 0), 48)
        H.lathe(el, 'STEEL', [(0, zc - 50), (30, zc - 50), (34, zc - 8), (0, zc - 8)], (x, y, 0), 48, orient='flip')
        H.lathe(el, 'LED', [(0, zc - 46), (18, zc - 46), (16, zc - 44), (0, zc - 44)], (x, y, 0), 32)
        return True
    if k == 'ceil':
        x, y = L['p']
        H.lathe(el, 'BRASS', [(0, zc), (205, zc), (205, zc - 18), (198, zc - 22), (0, zc - 22)], (x, y, 0), 96)
        prof = [(196, zc - 20)]
        for i in range(1, 13):
            t = math.radians(90 * i / 12)
            prof.append((196 * math.cos(t) * 0.98 + 2, zc - 20 - 70 * math.sin(t)))
        prof.append((0, zc - 90))
        H.lathe(el, 'OPAL', prof, (x, y, 0), 96)
        return True
    if k == 'sconce':
        from ifc.scene3d import _point_side
        x, y = L['p']
        z = L.get('z', 1500)
        room = L['room']
        sd = _point_side(L['p'], room)
        face = x if sd in ('W', 'E') else y
        w = y if sd in ('W', 'E') else x
        eu, ew, _ = wall_frame(sd)
        fr = H.axis_frame(eu)
        from ifc.scene3d import _zone_code_at, fin_t
        cz = _zone_code_at(room, L['p'], z - 190)
        face = face + SIDE_N[sd][0] * fin_t(cz) + SIDE_N[sd][1] * fin_t(cz) if cz and cz != 'X' else face   # на чистовой поверхности
        bp = lw(sd, face, 0, w)
        # розетка-основание на стене
        H.lathe(el, 'BRASS', [(0, 0), (40, 0), (40, 6), (34, 14), (12, 18), (0, 18)], (bp[0], bp[1], z - 190), 48, frame=fr)
        # рожок: от стены горизонтально, затем вверх — в патрон по оси абажура
        uc = 210
        p0 = np.array(list(lw(sd, face, 16, w)) + [z - 190.0])
        p1 = np.array(list(lw(sd, face, uc, w)) + [z - 190.0])
        p2 = np.array(list(lw(sd, face, uc, w)) + [z - 90.0])
        H.pipe(el, 'BRASS', [p0, p1, p2], 7, bend=55, n=16)
        H.lathe(el, 'BRASS', [(0, 0), (22, 0), (22, 4), (14, 8), (14, 46), (18, 50), (0, 52)], p2, 32)        # чашка и патрон
        H.sphere(el, 'OPAL', p2 + np.array([0, 0, 90.0]), 32, 24, sz=1.2)                                     # лампа
        # абажур: открытый усечённый конус (низ Ø230, верх Ø160), каркас-«паук» к патрону
        shade = [(115, 10), (114, 14), (82, 160), (80, 162)]
        H.open_shell(el, 'FAB_LINEN', shade, p2, 72, t=1.6)
        H.ring(el, 'BRASS', p2, 78, 81, 158, 162, 64)
        H.ring(el, 'BRASS', p2, 113, 116, 10, 14, 64)
        for k_ in range(3):
            a_ = 2 * math.pi * k_ / 3
            H.pipe(el, 'BRASS', [p2 + np.array([0, 0, 52.0]), p2 + np.array([79 * math.cos(a_), 79 * math.sin(a_), 158.0])], 1.6, n=8)
        return True
    if k == 'linear':
        (xa, ya), (xb, yb) = L['a'], L['b']
        H.rbox_seg(el, 'WHITE', (xa, ya), (xb, yb), -28, 28, zc - 60, zc, 6, 4)
        H.rbox_seg(el, 'LED', (xa, ya), (xb, yb), -22, 22, zc - 63, zc - 57, 3, 3, inset=12)
        for t in (0.15, 0.85):
            px, py = xa + (xb - xa) * t, ya + (yb - ya) * t
            H.lathe(el, 'WHITE', [(0, zc - 2), (25, zc - 2), (25, zc), (0, zc)], (px, py, 0), 24)
        return True
    if k == 'pend':
        from ifc.scene3d import _pend_style
        _pendant_hp(el, L, zc, _pend_style(L))
        return True
    return False


def _pendant_hp(el, L, zc, style):
    x, y = L['p']
    zl = L.get('z', zc - 600)
    H.lathe(el, 'BRASS', [(0, zc - 30), (60, zc - 30), (62, zc - 26), (62, zc), (0, zc)], (x, y, 0), 48)
    if style == 'globes':
        H.pipe(el, 'BRASS', [(x, y, zc - 30), (x, y, zl + 300)], 6, n=12)
        H.sphere(el, 'BRASS', (x, y, zl + 300), 14, 20)
        ring = [(x + 400 * math.cos(2 * math.pi * i / 96), y + 400 * math.sin(2 * math.pi * i / 96), zl + 50) for i in range(96)]
        H.sweep_pt(el, 'BRASS', ring + [ring[0], ring[1]], H.circle(9, 16), caps=False)
        for i in range(3):
            a = 2 * math.pi * i / 3 + 0.4
            H.pipe(el, 'BRASS', [(x, y, zl + 300), (x + 398 * math.cos(a), y + 398 * math.sin(a), zl + 58)], 2.5, n=8)
        for i in range(8):
            a = 2 * math.pi * i / 8
            px, py = x + 400 * math.cos(a), y + 400 * math.sin(a)
            H.lathe(el, 'BRASS', [(0, -15), (18, -15), (16, 0), (0, 0)], (px, py, zl + 42), 24)
            H.sphere(el, 'OPAL', (px, py, zl - 60), 75, 40)
        el.name = 'Люстра подвесная над столом Ø800, стеклянные плафоны, латунь (02а)'
    elif style == 'crystal':
        H.pipe(el, 'BRASS', [(x, y, zc - 30), (x, y, zl + 450)], 8, n=14)
        for kk, (R, zz) in enumerate(((300, zl + 420), (230, zl + 260), (150, zl + 120))):
            ring = [(x + R * math.cos(2 * math.pi * i / 96), y + R * math.sin(2 * math.pi * i / 96), zz) for i in range(96)]
            H.sweep_pt(el, 'BRASS', ring + [ring[0], ring[1]], H.circle(7, 12), caps=False)
            n = int(2 * math.pi * R / 42)
            for i in range(n):
                a = 2 * math.pi * (i + 0.5 * kk) / n
                px, py = x + R * math.cos(a), y + R * math.sin(a)
                drop = [(0, 0), (6, -6), (12, -30), (13, -55), (9, -80), (0, -100)]
                H.lathe(el, 'CRYSTAL', drop, (px, py, zz - 8), 10)
            for i in range(4):
                a = 2 * math.pi * i / 4 + 0.3 * kk
                H.pipe(el, 'BRASS', [(x, y, zl + 450), (x + R * math.cos(a), y + R * math.sin(a), zz)], 2.5, n=8)
        H.lathe(el, 'CRYSTAL', [(0, 0), (20, -10), (45, -60), (40, -110), (15, -150), (0, -160)], (x, y, zl + 110), 24)
        el.name = 'Люстра хрустальная Ø600, латунь (04а)'
    else:
        H.pipe(el, 'BRASS', [(x, y, zc - 30), (x, y, zl + 120)], 10, n=16)
        H.lathe(el, 'BRASS', [(0, -60), (30, -55), (55, -20), (55, 10), (30, 40), (0, 45)], (x, y, zl + 120), 32)
        for i in range(6):
            a = 2 * math.pi * i / 6
            ca, sa = math.cos(a), math.sin(a)
            p0 = (x + 50 * ca, y + 50 * sa, zl + 110)
            p1 = (x + 220 * ca, y + 220 * sa, zl + 60)
            p2 = (x + 320 * ca, y + 320 * sa, zl + 110)
            p3 = (x + 320 * ca, y + 320 * sa, zl + 165)
            H.pipe(el, 'BRASS', [p0, p1, p2, p3], 8, bend=80, n=14)
            H.lathe(el, 'BRASS', [(0, 0), (32, 0), (32, 12), (22, 20), (0, 20)], p3, 24)
            H.open_shell(el, 'OPAL', [(55, 20), (55, 24), (56, 150), (55, 154)], p3, 48, t=2.5)
        el.name = 'Люстра потолочная многорожковая (6 плафонов), опал / латунь (03а)'


# ---------------------------------------------------------------- кухня (ред. 3): фасады, столешница с мойкой, техника
def _orient(G, want, r=0, c=0):
    """'keep' / 'flip' — чтобы нормаль ячейки (r, c) сетки смотрела по направлению want."""
    P = np.asarray(G, dtype=float)
    C = P.shape[1]
    p00, p01, p10 = P[r, c], P[r, (c + 1) % C], P[r + 1, c]
    n = np.cross(p01 - p00, p10 - p00)
    return 'keep' if float(np.dot(n, np.asarray(want, float))) >= 0 else 'flip'


def shaker(el, m, sd, face, uf, w0, w1, z0, z1, t=20, rail=62):
    """Фасад «шейкер»: рамка (стойки и перемычки) и утопленная филёнка; uf — плоскость лицевой грани (u от стены)."""
    if (w1 - w0) < 3 * rail or (z1 - z0) < 2.4 * rail:
        lrbox(el, m, sd, face, uf - t, uf, w0, w1, z0, z1, 2, 2)
        return
    lrbox(el, m, sd, face, uf - t, uf, w0, w0 + rail, z0, z1, 1.5, 2)
    lrbox(el, m, sd, face, uf - t, uf, w1 - rail, w1, z0, z1, 1.5, 2)
    lrbox(el, m, sd, face, uf - t, uf, w0 + rail - 1, w1 - rail + 1, z0, z0 + rail, 1.5, 2)
    lrbox(el, m, sd, face, uf - t, uf, w0 + rail - 1, w1 - rail + 1, z1 - rail, z1, 1.5, 2)
    lrbox(el, m, sd, face, uf - t, uf - 7, w0 + rail - 2, w1 - rail + 2, z0 + rail - 2, z1 - rail + 2, 1, 2)


def _hbar(el, sd, face, uf, wc, zc, L=160, m='BRASS'):
    eu, ew, _ = wall_frame(sd)
    x, y = lw(sd, face, uf, wc)
    bar_handle(el, m, (x, y, zc), ew, eu, L=L, h=28, r=6)


def _vbar(el, sd, face, uf, wc, zc, L=300, m='BRASS'):
    eu, ew, _ = wall_frame(sd)
    x, y = lw(sd, face, uf, wc)
    bar_handle(el, m, (x, y, zc), (0, 0, 1), eu, L=L, h=30, r=7)


def _ray_rect(cx, cy, t, x0, x1, y0, y1):
    dx, dy = math.cos(t), math.sin(t)
    ts = []
    if dx > 1e-9:
        ts.append((x1 - cx) / dx)
    if dx < -1e-9:
        ts.append((x0 - cx) / dx)
    if dy > 1e-9:
        ts.append((y1 - cy) / dy)
    if dy < -1e-9:
        ts.append((y0 - cy) / dy)
    tt = min(ts)
    return cx + dx * tt, cy + dy * tt


def _se_r(phi, A, B, e):
    """Полярный радиус суперэллипса (|x/A|^e + |y/B|^e = 1) в направлении phi."""
    c, s = abs(math.cos(phi)), abs(math.sin(phi))
    return 1.0 / ((c / A) ** e + (s / B) ** e) ** (1.0 / e)


def _planar_uv(m):
    tw, th = MATS[m].tile if m in MATS else (1000, 1000)
    return lambda M_, n_, p_: (p_[0] / tw, p_[1] / th)


def _top_piece(el, m, sd, face, a, b, U, z0, z1):
    """Участок столешницы — призма с единой плоской развёрткой фактуры (без швов между участками)."""
    poly = [lw(sd, face, 0, a), lw(sd, face, 0, b), lw(sd, face, U, b), lw(sd, face, U, a)]
    prism(el, m, poly, z0, z1, uvf=_planar_uv(m))


def _sink_top(el, top, sink_m, sd, face, a, b, U, z_bot, z_top, bw, bd, uc):
    """Участок столешницы над тумбой мойки с вырезом и подстольная чаша (нерж. сталь)."""
    wc = (a + b) / 2
    angs = [2 * math.pi * i / 96 for i in range(96)]
    for (cw, cu) in ((a, 0), (b, 0), (b, U), (a, U)):               # углы прямоугольника — точно
        angs.append(math.atan2(cu - uc, cw - wc) % (2 * math.pi))
    angs = sorted(set(round(x, 9) for x in angs))

    def P(w, u, z):
        x, y = lw(sd, face, u, w)
        return (x, y, z)

    def inner(phi, dA, dB, e, z):
        rr = _se_r(phi, bw / 2 + dA, bd / 2 + dB, e)
        return P(wc + rr * math.cos(phi), uc + rr * math.sin(phi), z)
    outer_b, outer_t, in_t, in_b = [], [], [], []
    for phi in angs:
        ow, ou = _ray_rect(wc, uc, phi, a, b, 0, U)
        outer_b.append(P(ow, ou, z_bot)); outer_t.append(P(ow, ou, z_top))
        in_t.append(inner(phi, 0, 0, 10, z_top)); in_b.append(inner(phi, 0, 0, 10, z_bot))
    G = [outer_b, outer_t, in_t, in_b, outer_b]
    tw, th = MATS[top].tile if top in MATS else (1000, 1000)
    Pg = np.asarray(G, dtype=float)
    H.add_grid(el, top, G, closed_u=True, orient=_orient(G, (0, 0, 1), r=1), sharp=True,
               uv=(Pg[..., 0] / tw, Pg[..., 1] / th))
    # чаша: фланец под столешницей, стенки с радиусом у дна, дно
    rings = []
    for dA, e, z in ((12, 10, z_bot - 1), (0, 10, z_bot - 1), (0, 10, z_bot - 12), (-2, 9, z_top - 150),
                     (-7, 6, z_top - 182), (-22, 4, z_top - 196), (-55, 3, z_top - 200)):
        rings.append([inner(phi, dA, dA, e, z) for phi in angs])
    cen = np.asarray(P(wc, uc, z_top - 100))
    H.add_grid(el, sink_m, rings, closed_u=True, orient=_orient(rings, cen - np.asarray(rings[3][0]), r=2))
    H.cap(el, sink_m, rings[-1], normal=(0, 0, 1))
    dx, dy = lw(sd, face, uc, wc)
    H.ring(el, 'NICKEL', (dx, dy, z_top - 200), 0, 42, 0.2, 2.2, 48)                 # сливная корзина
    H.ring(el, 'GRAPHITE', (dx, dy, z_top - 200), 16, 30, 2.2, 2.6, 32)


def _kitchen_run(el, it, r, z, room, zf):
    from ifc.scene3d import fmat, face_key, lbox as _lbox, SIDE_N as _SN
    sd = it.get('side', 'W')
    face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
    dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
    w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
    kf = fmat(it.get('front'), 'FRONT')
    top = 'MARBLE' if it.get('top') and D.mat(it['top']).get('tex') == 'marble' else fmat(it.get('top'), 'OAK')
    fk = face_key(_SN[sd])
    ZT, ZB = 900, 880                                       # столешница 20 мм
    lrbox(el, 'BLACK', sd, face, 0, dep - 60, w0, w1, 0, 100, 1, 2)                      # цоколь
    for a, b, kind in it['modules']:                                                      # корпуса (зазоры — тень)
        if kind == 'sink':                       # тумба мойки — без крышки: боковины, дно, задняя стенка (под чашей пусто)
            for wa, wb in ((a, a + 18), (b - 18, b)):
                _lbox(el, 'WHITE', sd, face, 0, dep - 22, wa, wb, 100, ZB)
            _lbox(el, 'WHITE', sd, face, 0, dep - 22, a + 18, b - 18, 100, 118)
            _lbox(el, 'WHITE', sd, face, 0, 18, a + 18, b - 18, 118, ZB)
        else:
            _lbox(el, kf, sd, face, 0, dep - 22, a, b, 100, ZB, fm={fk: 'BLACK'})
    uf = dep
    for a, b, kind in it['modules']:
        fa, fb = a + 1.5, b - 1.5
        if kind == 'blind':
            continue
        if kind in ('dw', 'sink', 'tech'):
            shaker(el, kf, sd, face, uf, fa, fb, 103, 877)
            _hbar(el, sd, face, uf, (a + b) / 2, 835, L=min(320, b - a - 120))
        elif kind == 'hob':                    # под варочной: духовой шкаф (appliances), сверху ящик
            lrbox(el, kf, sd, face, uf - 20, uf, fa, fb, 103, 148, 1.5, 2)
            shaker(el, kf, sd, face, uf, fa, fb, 752, 877, rail=40)
            _hbar(el, sd, face, uf, (a + b) / 2, 815, L=min(320, b - a - 120))
        else:                                   # ящики 3 шт.
            for za, zb in ((103, 330), (334, 600), (604, 877)):
                shaker(el, kf, sd, face, uf, fa, fb, za, zb, rail=48)
                _hbar(el, sd, face, uf, (a + b) / 2, zb - 40, L=min(160, b - a - 100))
    # столешница: участки, над мойкой — с вырезом и подстольной чашей
    U = dep + 10
    sinks = [(a, b) for a, b, kind in it['modules'] if kind == 'sink']
    cuts = sorted(sinks)
    pos = w0
    for a, b in cuts:
        if a - pos > 1:
            _top_piece(el, top, sd, face, pos, a, U, ZB, ZT)
        bw = min(500, (b - a) - 50)
        _sink_top(el, top, 'STEEL', sd, face, a, b, U, ZB, ZT, bw, 400, U - 80 - 200)
        # смеситель высокий (латунь мат.), дозатор, кран питьевого фильтра
        eu, ew, _ = wall_frame(sd)
        bx, by = lw(sd, face, 75, (a + b) / 2)
        _faucet(el, 'BRASS', (bx, by, ZT), 400, 230, (eu[0], eu[1]))
        sx, sy = lw(sd, face, 75, (a + b) / 2 + min(170, (b - a) / 2 - 20))
        H.lathe(el, 'BRASS', [(0, 0), (24, 0), (24, 6), (20, 10), (19, 75), (12, 82), (6, 120), (15, 128), (15, 134), (0, 136)],
                (sx, sy, ZT), 32)
        fx, fy = lw(sd, face, 75, (a + b) / 2 - min(170, (b - a) / 2 - 20))
        H.lathe(el, 'BRASS', [(0, 0), (20, 0), (20, 5), (12, 10), (10, 220), (0, 222)], (fx, fy, ZT), 24)
        p0 = np.array([fx, fy, ZT + 215.0])
        H.pipe(el, 'BRASS', [p0, p0 + np.array([0, 0, 50.0]), p0 + np.array([0, 0, 50.0]) + np.array([eu[0], eu[1], 0]) * 150,
                             p0 + np.array([eu[0], eu[1], 0]) * 150 + np.array([0, 0, 15.0])], 5, bend=30, n=12)
        pos = b
    if w1 - pos > 1:
        _top_piece(el, top, sd, face, pos, w1, U, ZB, ZT)
    el.props['Столешница'] = 'кварц/керамика под мрамор, 20 мм, +0,900'


def _upper(el, it, r, z, room, zf):
    from ifc.scene3d import fmat, face_key, lbox as _lbox, SIDE_N as _SN
    sd = it.get('side', 'W')
    face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
    dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
    w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
    fk = face_key(_SN[sd])
    zs = min(it.get('split', z[0] + 850), z[1])
    m_lo = fmat(it.get('front_low'), 'WALNUT') if it.get('front_low') else 'WALNUT'
    m_hi = fmat(it.get('front'), 'FRONT')
    _lbox(el, m_hi, sd, face, 0, dep - 20, w0, w1, z[0], z[1], fm={fk: 'BLACK'})
    n = max(1, int(round((w1 - w0) / 600)))
    w = (w1 - w0) / n
    hood = it.get('hood')
    for i in range(n):
        a = w0 + i * w
        b = a + w
        if hood and a >= hood[0] - 5 and b <= hood[1] + 5:          # над плитой — встроенная вытяжка + фасад над ней
            shaker(el, m_lo, sd, face, dep, a + 1.5, b - 1.5, z[0] + 60, zs - 2, rail=50)
            continue
        shaker(el, m_lo, sd, face, dep, a + 1.5, b - 1.5, z[0] + 2, zs - 2, rail=55)
        _hbar(el, sd, face, dep, (a + b) / 2, z[0] + 42, L=min(160, w - 120))
        if z[1] > zs + 10:
            shaker(el, m_hi, sd, face, dep, a + 1.5, b - 1.5, zs + 2, z[1] - 2, rail=50)
    if hood:
        h0, h1 = hood
        lrbox(el, 'STEEL', sd, face, 15, dep - 2, h0 + 10, h1 - 10, z[0], z[0] + 58, 2, 2)          # корпус вытяжки
        lrbox(el, 'BLACKGLASS', sd, face, dep - 160, dep - 4, h0 + 30, h1 - 30, z[0] - 6, z[0] + 4, 2, 2)   # козырёк
        for k_ in range(5):                                                                            # жалюзи фильтра
            lrbox(el, 'GRAPHITE', sd, face, 40 + k_ * 50, 70 + k_ * 50, h0 + 60, h1 - 60, z[0] - 1, z[0], 0.5, 1)
        el.props['Вытяжка'] = 'встроенная рециркуляционная 60 см (Т9)'


def _column(el, it, r, z, room, zf):
    from ifc.scene3d import fmat, face_key, lbox as _lbox, SIDE_N as _SN, side_of
    sd = side_of(r, room)
    face = {'W': r[0], 'E': r[2], 'S': r[1], 'N': r[3]}[sd]
    dep = (r[2] - r[0]) if sd in ('W', 'E') else (r[3] - r[1])
    w0, w1 = ((r[1], r[3]) if sd in ('W', 'E') else (r[0], r[2]))
    cf = fmat(it.get('front') or it.get('mat'), 'FRONT')
    fk = face_key(_SN[sd])
    lrbox(el, 'BLACK', sd, face, 0, dep - 60, w0 + 1, w1 - 1, 0, 100, 1, 2)
    _lbox(el, cf, sd, face, 0, dep - 22, w0, w1, 100, z[1], fm={fk: 'BLACK'})
    shaker(el, cf, sd, face, dep, w0 + 2, w1 - 2, 103, 1877)
    shaker(el, cf, sd, face, dep, w0 + 2, w1 - 2, 1881, z[1] - 3, rail=55)
    near_w1 = False
    for o in D.ITEMS:
        if o is it or o['room'] != room or o['kind'] != 'kitchen_run':
            continue
        q = D.item_rect(o)
        if sd in ('W', 'E') and abs(q[1] - w1) < 5 and q[0] < r[2] and q[2] > r[0]:
            near_w1 = True
        if sd in ('S', 'N') and abs(q[0] - w1) < 5 and q[1] < r[3] and q[3] > r[1]:
            near_w1 = True
    _vbar(el, sd, face, dep, (w1 - 45) if near_w1 else (w0 + 45), 1150, L=420)
    _hbar(el, sd, face, dep, (w0 + w1) / 2, 1925, L=160)
    el.props['Навеска'] = 'ручка — со стороны столешницы, дверь открывается к проёму'


BUILD.update({'kitchen_run': _kitchen_run, 'upper': _upper, 'column': _column})
