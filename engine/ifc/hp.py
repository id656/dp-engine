# -*- coding: utf-8 -*-
"""Многополигональные примитивы (сглаженные нормали): скруглённые параллелепипеды, тела вращения,
протяжки профилей (молдинги, плинтусы, наличники), трубы со скруглёнными отводами, лофты (чаши ванн,
раковин, унитазов), подушки, ткани. Единицы — мм, оси модели (x, y — план, z — вверх)."""
import math

import numpy as np

from ifc.m3d import MATS


# ---------------------------------------------------------------- векторы
def _v(a):
    return np.asarray(a, dtype=float)


def _unit(a):
    a = _v(a)
    L = np.linalg.norm(a)
    return a / L if L > 1e-12 else a


# ---------------------------------------------------------------- сетка -> Part
def add_grid(el, m, G, closed_u=False, N=None, orient='auto', center=None, uv=None, sharp=False):
    """Поверхность по сетке точек G[строка][столбец] (строки — v, столбцы — u).
    N — нормали той же формы (иначе усреднение по соседним ячейкам). orient: 'auto' — наружу от центра,
    'keep' — как задано (du × dv), 'flip' — наоборот."""
    P = np.asarray(G, dtype=float)
    R, C = P.shape[:2]
    if R < 2 or C < 2:
        return
    # нормали ячеек
    cu = C if closed_u else C - 1
    Q = np.zeros((R - 1, cu, 3))
    for c in range(cu):
        c2 = (c + 1) % C
        du = P[:-1, c2] - P[:-1, c] + P[1:, c2] - P[1:, c]
        dv = P[1:, c] - P[:-1, c] + P[1:, c2] - P[:-1, c2]
        Q[:, c] = np.cross(du, dv)
    if N is None:
        Nv = np.zeros((R, C, 3))
        for c in range(cu):
            c2 = (c + 1) % C
            Nv[:-1, c] += Q[:, c]; Nv[1:, c] += Q[:, c]
            Nv[:-1, c2] += Q[:, c]; Nv[1:, c2] += Q[:, c]
        L = np.linalg.norm(Nv, axis=2, keepdims=True)
        L[L < 1e-12] = 1.0
        Nv = Nv / L
    else:
        Nv = np.asarray(N, dtype=float)
    flip = False
    if orient == 'flip':
        flip = True
    elif orient == 'auto':
        cen = _v(center) if center is not None else P.reshape(-1, 3).mean(0)
        d = (P - cen)
        s = float(np.sum(Nv * d))
        flip = s < 0
    if flip:
        Nv = -Nv
    # uv по длинам дуг
    if uv is None:
        tw, th = MATS[m].tile if m in MATS else (1000, 1000)
        su = np.zeros(C)
        su[1:] = np.cumsum(np.linalg.norm(np.diff(P, axis=1), axis=2).mean(0))
        sv = np.zeros(R)
        sv[1:] = np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=2).mean(1))
        U = np.broadcast_to(su[None, :] / tw, (R, C))
        V = np.broadcast_to(sv[:, None] / th, (R, C))
    else:
        U, V = uv
    part = el.part(m)
    if sharp:                         # плоские грани (жёсткие кромки)
        for r in range(R - 1):
            for c in range(cu):
                c2 = (c + 1) % C
                pts = [tuple(P[r, c]), tuple(P[r, c2]), tuple(P[r + 1, c2]), tuple(P[r + 1, c])]
                uvs = [(U[r, c], V[r, c]), (U[r, c2], V[r, c2]), (U[r + 1, c2], V[r + 1, c2]), (U[r + 1, c], V[r + 1, c])]
                if flip:
                    pts, uvs = pts[::-1], uvs[::-1]
                part.face(pts, uvs)
        return
    base = len(part.v)
    for r in range(R):
        for c in range(C):
            part.v.append(tuple(float(x) for x in P[r, c]))
            part.vn[base + r * C + c] = tuple(float(x) for x in Nv[r, c])
    for r in range(R - 1):
        for c in range(cu):
            c2 = (c + 1) % C
            a, b, d, e = base + r * C + c, base + r * C + c2, base + (r + 1) * C + c2, base + (r + 1) * C + c
            ua, ub, ud, ue = (U[r, c], V[r, c]), (U[r, c2], V[r, c2]), (U[r + 1, c2], V[r + 1, c2]), (U[r + 1, c], V[r + 1, c])
            if flip:
                part.t += [(a, d, b), (a, e, d)]
                part.uv += [(ua, ud, ub), (ua, ue, ud)]
            else:
                part.t += [(a, b, d), (a, d, e)]
                part.uv += [(ua, ub, ud), (ua, ud, ue)]


def cap(el, m, ring, normal=None, center=None):
    """Плоская крышка по кольцу точек (веер от центра)."""
    ring = [tuple(map(float, p)) for p in ring]
    c = tuple(np.mean(np.asarray(ring), 0)) if center is None else tuple(map(float, center))
    n = len(ring)
    if normal is not None:
        nrm = _unit(normal)
        a = np.cross(_v(ring[0]) - c, _v(ring[1 % n]) - c)
        if np.linalg.norm(a) > 1e-9 and np.dot(a, nrm) < 0:
            ring = ring[::-1]
    part = el.part(m)
    tw, th = MATS[m].tile if m in MATS else (1000, 1000)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        part.face([c, a, b], [(c[0] / tw, c[1] / th), (a[0] / tw, a[1] / th), (b[0] / tw, b[1] / th)])


# ---------------------------------------------------------------- скруглённый параллелепипед
def rbox_f(el, m, c, ex, ey, ez, hx, hy, hz, r, seg=4):
    """Скруглённый параллелепипед в локальной системе (c — центр, ex/ey/ez — оси, h — полуразмеры, r — радиус кромок)."""
    r = max(0.0, min(r, hx - 0.01, hy - 0.01, hz - 0.01))
    c, ex, ey, ez = _v(c), _unit(ex), _unit(ey), _unit(ez)
    ax, ay, az = hx - r, hy - r, hz - r
    lons = []
    for q, (sx, sy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        for i in range(seg + 1):
            a = math.radians(q * 90 + i * 90.0 / seg)
            lons.append((a, sx, sy))
    lats = []
    for sz, rng in ((-1, range(0, seg + 1)), (1, range(0, seg + 1))):
        for i in rng:
            b = math.radians(-90 + i * 90.0 / seg) if sz < 0 else math.radians(i * 90.0 / seg)
            lats.append((b, sz))
    G, N = [], []
    for b, sz in lats:
        row, nrow = [], []
        for a, sx, sy in lons:
            n = np.array([math.cos(b) * math.cos(a), math.cos(b) * math.sin(a), math.sin(b)])
            loc = np.array([sx * ax, sy * ay, sz * az]) + r * n
            row.append(c + loc[0] * ex + loc[1] * ey + loc[2] * ez)
            nrow.append(n[0] * ex + n[1] * ey + n[2] * ez)
        G.append(row); N.append(nrow)
    add_grid(el, m, G, closed_u=True, N=N, orient='auto', center=c)
    for sz in (-1, 1):
        ring = [c + sx * ax * ex + sy * ay * ey + sz * hz * ez for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
        if ax > 0.01 and ay > 0.01:
            cap(el, m, ring, normal=sz * ez)


def rbox(el, m, x0, y0, z0, x1, y1, z1, r, seg=4):
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    z0, z1 = min(z0, z1), max(z0, z1)
    rbox_f(el, m, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (1, 0, 0), (0, 1, 0), (0, 0, 1),
           (x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2, r, seg)


def rbox_plan(el, m, c, ang, u0, v0, u1, v1, z0, z1, r, seg=4):
    """Скруглённый брусок в осях предмета, повёрнутого в плане на ang (град)."""
    a = math.radians(ang)
    ex = (math.cos(a), math.sin(a), 0)
    ey = (-math.sin(a), math.cos(a), 0)
    uc, vc = (u0 + u1) / 2, (v0 + v1) / 2
    cc = (c[0] + uc * ex[0] + vc * ey[0], c[1] + uc * ex[1] + vc * ey[1], (z0 + z1) / 2)
    rbox_f(el, m, cc, ex, ey, (0, 0, 1), abs(u1 - u0) / 2, abs(v1 - v0) / 2, abs(z1 - z0) / 2, r, seg)


def rbox_seg(el, m, a, b, w0, w1, z0, z1, r, seg=4, inset=0.0):
    """Скруглённый брусок вдоль отрезка a–b в плане (w — смещение по левой нормали)."""
    d = _unit((b[0] - a[0], b[1] - a[1], 0))
    n = np.array([-d[1], d[0], 0])
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    mid = (_v((a[0], a[1], 0)) + _v((b[0], b[1], 0))) / 2 + n * (w0 + w1) / 2
    cc = (mid[0], mid[1], (z0 + z1) / 2)
    rbox_f(el, m, cc, d, n, (0, 0, 1), L / 2 - inset, abs(w1 - w0) / 2, abs(z1 - z0) / 2, r, seg)


# ---------------------------------------------------------------- тела вращения
def lathe(el, m, prof, c, n=48, frame=None, orient='auto', caps=True, uv=None):
    """Тело вращения: профиль [(r, h)] снизу вверх, ось через c по ez (frame=(ex, ey, ez)).
    caps=False — без торцевых дисков (открытые абажуры, кольца с замкнутым профилем).
    uv='planar' — плоская развёртка фактуры по XY (камень, дерево столешниц: без радиального «веера» прожилок)."""
    ex, ey, ez = frame or ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    ex, ey, ez, c = _unit(ex), _unit(ey), _unit(ez), _v(c)
    G = []
    for rr, hh in prof:
        row = []
        for i in range(n):
            a = 2 * math.pi * i / n
            row.append(c + ez * hh + rr * (math.cos(a) * ex + math.sin(a) * ey))
        G.append(row)
    cen = c + ez * (sum(h for _, h in prof) / len(prof))
    UV = None
    if uv == 'planar':
        tw, th = MATS[m].tile if m in MATS else (1000, 1000)
        P_ = np.asarray(G, dtype=float)
        UV = (P_[..., 0] / tw, P_[..., 1] / th)
    add_grid(el, m, G, closed_u=True, orient=orient, center=cen, uv=UV)
    # торцы, если профиль не сходится к оси
    for rr, hh, sg in ((prof[0][0], prof[0][1], -1), (prof[-1][0], prof[-1][1], 1)):
        if rr > 0.01 and caps:
            ring = [c + ez * hh + rr * (math.cos(2 * math.pi * i / n) * ex + math.sin(2 * math.pi * i / n) * ey) for i in range(n)]
            cap(el, m, ring, normal=sg * ez)


def sphere(el, m, c, r, n=32, sz=1.0):
    prof = [(r * math.sin(math.pi * i / (n // 2)), -r * sz * math.cos(math.pi * i / (n // 2))) for i in range(n // 2 + 1)]
    lathe(el, m, prof, c, n)


def axis_frame(d):
    """Ортонормированная система с ez вдоль d."""
    ez = _unit(d)
    a = np.array([0, 0, 1.0]) if abs(ez[2]) < 0.9 else np.array([1.0, 0, 0])
    ex = _unit(np.cross(a, ez))
    ey = np.cross(ez, ex)
    return ex, ey, ez


def cone(el, m, p0, p1, r0, r1, n=24, caps=True):
    """Усечённый конус между точками (ножки, штанги)."""
    p0, p1 = _v(p0), _v(p1)
    L = np.linalg.norm(p1 - p0)
    if L < 0.1:
        return
    fr = axis_frame(p1 - p0)
    prof = [(r0, 0.0), (r1, L)] if caps else [(r0, 0.0), (r1, L)]
    lathe(el, m, prof, p0, n, frame=fr)


# ---------------------------------------------------------------- протяжки
def _fillet_path(pts, rb, steps=8):
    """Скругление изломов ломаной (квадратичная кривая в каждом изломе)."""
    pts = [_v(p) for p in pts]
    if len(pts) < 3 or rb <= 0:
        return pts
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, p, b = pts[i - 1], pts[i], pts[i + 1]
        da, db = p - a, b - p
        La, Lb = np.linalg.norm(da), np.linalg.norm(db)
        if La < 1e-6 or Lb < 1e-6:
            continue
        da, db = da / La, db / Lb
        cosang = float(np.clip(np.dot(da, db), -1, 1))
        if cosang > 0.9995:
            out.append(p)
            continue
        th = math.acos(cosang)
        t = min(rb * math.tan(th / 2), La * 0.45, Lb * 0.45)
        q0, q1 = p - da * t, p + db * t
        for k in range(steps + 1):
            s = k / steps
            out.append((1 - s) ** 2 * q0 + 2 * (1 - s) * s * p + s ** 2 * q1)
    out.append(pts[-1])
    # убрать совпадающие точки
    res = [out[0]]
    for q in out[1:]:
        if np.linalg.norm(q - res[-1]) > 0.05:
            res.append(q)
    return res


def sweep_pt(el, m, path, prof, closed_prof=True, caps=True, orient='auto', sharp=False):
    """Протяжка профиля [(u, v)] по пространственной ломаной с параллельным переносом рамки (трубы, гибы)."""
    P = [_v(p) for p in path]
    if len(P) < 2:
        return
    T = []
    for i in range(len(P)):
        if i == 0:
            t = P[1] - P[0]
        elif i == len(P) - 1:
            t = P[-1] - P[-2]
        else:
            t = _unit(P[i] - P[i - 1]) + _unit(P[i + 1] - P[i])
        T.append(_unit(t))
    ex, ey, _ = axis_frame(T[0])
    G = []
    prof2 = list(prof) + ([prof[0]] if False else [])
    for i in range(len(P)):
        if i > 0:                                  # перенос рамки
            v = np.cross(T[i - 1], T[i])
            s = np.linalg.norm(v)
            if s > 1e-9:
                ang = math.atan2(s, float(np.dot(T[i - 1], T[i])))
                k = v / s

                def rot(x):
                    return x * math.cos(ang) + np.cross(k, x) * math.sin(ang) + k * np.dot(k, x) * (1 - math.cos(ang))
                ex, ey = rot(ex), rot(ey)
        G.append([P[i] + u * ex + w * ey for u, w in prof2])
    add_grid(el, m, [list(r) for r in zip(*G)] if False else G, closed_u=closed_prof, orient=orient,
             center=None, sharp=sharp)
    if caps and closed_prof:
        cap(el, m, G[0], normal=-T[0])
        cap(el, m, G[-1], normal=T[-1])


def circle(r, n=16):
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def pipe(el, m, path, r, bend=None, n=16, caps=True):
    """Труба по ломаной со скруглёнными отводами (радиус гиба bend, по умолчанию 3r)."""
    pts = _fillet_path(path, bend if bend is not None else 3 * r)
    sweep_pt(el, m, pts, circle(r, n), caps=caps, orient='auto')
    # сглаженную трубу ориентируем по оси: проверка «наружу» по центру масс для изогнутых труб ненадёжна —
    # материалы двусторонние, нормали усреднены по сетке


def sweep_up(el, m, path, prof, up, closed_path=False, caps=True, smooth=False):
    """Протяжка профиля [(u, v)] по плоской ломаной с постоянной нормалью плоскости up (молдинги, наличники,
    плинтусы, карнизы): u — в плоскости, влево от направления пути; v — вдоль up. Углы — на ус (миттер)."""
    P = [_v(p) for p in path]
    up = _unit(up)
    if closed_path and np.linalg.norm(P[0] - P[-1]) < 1e-6:
        P = P[:-1]
    nP = len(P)
    segs = nP if closed_path else nP - 1
    S = []
    for k in range(segs):
        d = _unit(P[(k + 1) % nP] - P[k])
        S.append(_unit(np.cross(up, d)))
    G = []
    for i in range(nP):
        if closed_path:
            sa, sb = S[(i - 1) % segs], S[i % segs]
        else:
            sa = S[max(0, i - 1)]
            sb = S[min(i, segs - 1)]
        mv = (sa + sb) / (1.0 + float(np.dot(sa, sb)))
        pr = list(prof) + [prof[0]]
        G.append([P[i] + u * mv + v * up for u, v in pr])
    if closed_path:
        G.append(G[0])
    rows = [list(col) for col in zip(*G)]       # строки — точки профиля, столбцы — путь
    add_grid(el, m, rows, closed_u=False, orient='keep', sharp=not smooth)
    if caps and not closed_path:
        cap(el, m, G[0], normal=-(_unit(P[1] - P[0])))
        cap(el, m, G[-1], normal=_unit(P[-1] - P[-2]))


# ---------------------------------------------------------------- лофт
def superellipse(cx, cy, a, b, e=4.0, n=64, z=0.0, a0=0.0):
    """Кольцо «скруглённый прямоугольник» (e>2) / эллипс (e=2) с согласованной параметризацией."""
    pts = []
    for i in range(n):
        t = a0 + 2 * math.pi * i / n
        ct, st = math.cos(t), math.sin(t)
        x = a * math.copysign(abs(ct) ** (2.0 / e), ct)
        y = b * math.copysign(abs(st) ** (2.0 / e), st)
        pts.append((cx + x, cy + y, z))
    return pts


def loft(el, m, rings, closed=True, cap0=False, cap1=False, orient='auto', center=None):
    add_grid(el, m, rings, closed_u=closed, orient=orient, center=center)
    if cap0:
        cap(el, m, rings[0], normal=_v(rings[0][0]) * 0 + _v((0, 0, -1)))
    if cap1:
        cap(el, m, rings[-1], normal=(0, 0, 1))


# ---------------------------------------------------------------- ткани
def drape(el, m, a, b, z0, z1, depth=60, folds=None, nz=6):
    """Штора/ткань со складками: волна вдоль отрезка a–b (план), от z0 до z1."""
    a, b = _v((a[0], a[1], 0)), _v((b[0], b[1], 0))
    L = np.linalg.norm(b - a)
    d = (b - a) / max(L, 1e-6)
    n = np.array([-d[1], d[0], 0])
    k = folds or max(3, int(L / 110))
    nu = k * 8 + 1
    G = []
    for j in range(nz + 1):
        z = z0 + (z1 - z0) * j / nz
        amp = depth / 2 * (0.75 + 0.25 * (1 - j / nz))
        row = []
        for i in range(nu):
            s = i / (nu - 1)
            p = a + d * L * s + n * amp * math.sin(2 * math.pi * k * s)
            row.append((p[0], p[1], z))
        G.append(row)
    add_grid(el, m, G, closed_u=False, orient='keep')


def ring(el, m, c, r0, r1, h0, h1, n=48, frame=None):
    """Кольцо (шайба) прямоугольного сечения r0…r1 × h0…h1 — ободки, разметка зон, форсунки."""
    prof = [(r0, h0), (r1, h0), (r1, h1), (r0, h1), (r0, h0)]
    lathe(el, m, prof, c, n, frame=frame, orient='keep', caps=False)


def open_shell(el, m, prof, c, n=64, t=1.5, frame=None):
    """Тонкостенная открытая оболочка вращения (абажур, плафон-цилиндр): наружная и внутренняя поверхности + торцы."""
    outer = list(prof)
    inner = [(max(r - t, 0.0), h) for r, h in prof[::-1]]
    closed = outer + inner + [outer[0]]
    lathe(el, m, closed, c, n, frame=frame, orient='keep', caps=False)
