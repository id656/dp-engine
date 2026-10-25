# -*- coding: utf-8 -*-
"""3D-примитивы с текстурными координатами и библиотека материалов (фактуры генерируются из textures.py).
Единицы — мм; оси как в модели проекта: x, y — план (y к балкону), z — вверх от ±0,000."""
import math
import os
import sys

import numpy as np
from PIL import Image

import textures as T  # noqa: E402

TEXDIR = None   # задаётся при сборке


# ---------------------------------------------------------------- материалы
class Mat:
    def __init__(s, key, name, color, tex=None, tile=(1000, 1000), grain=False, transp=0.0, refl='MATT',
                 spec=0.15, unique=False, ifc_mat=None):
        s.key, s.name, s.color, s.tex, s.tile, s.grain = key, name, color, tex, tile, grain
        s.transp, s.refl, s.spec, s.unique = transp, refl, spec, unique
        s.ifc_mat = ifc_mat or name


MATS = {}


def mat(key, *a, **kw):
    MATS[key] = Mat(key, *a, **kw)
    return MATS[key]


def _save_tex(arr, fname, alpha=None):
    path = os.path.join(TEXDIR, fname)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr, 'RGB').save(path, quality=88, optimize=True)
    mean = arr.reshape(-1, 3).mean(0) / 255.0
    return fname, tuple(float(round(c, 3)) for c in mean)


def tileable(arr, oy, ox):
    """Бесшовная фактура: перекрёстное наложение краёв (oy, ox — ширина перехода в пикселях)."""
    A = np.asarray(arr, dtype=np.float32)
    H, W = A.shape[:2]
    if oy:
        out = A[:H - oy].copy()
        w = (np.arange(oy, dtype=np.float32) / oy)[:, None, None]
        out[:oy] = A[H - oy:] * (1 - w) + A[:oy] * w
        A = out
    if ox:
        H, W = A.shape[:2]
        out = A[:, :W - ox].copy()
        w = (np.arange(ox, dtype=np.float32) / ox)[None, :, None]
        out[:, :ox] = A[:, W - ox:] * (1 - w) + A[:, :ox] * w
        A = out
    return A


def tex_material(key, name, fname, arr, tile, grain=False, refl='MATT', spec=0.12, unique=False, ifc_mat=None):
    f, mean = _save_tex(arr, fname)
    return mat(key, name, mean, tex=f, tile=tile, grain=grain, refl=refl, spec=spec, unique=unique, ifc_mat=ifc_mat)


def build_library(D):
    """Повторяющиеся фактуры и цветовые материалы проекта: отделка стен — по кодам объекта (тип из MATERIALS)."""
    mpp = 1.0
    from ifc.scene3d import mkey
    codes = []
    for (r, lab, s0, s1, z0, z1, code) in D.WALL_ZONES:
        if code != 'X' and code not in codes:
            codes.append(code)
    for c in list(D.WALL_DEFAULT.values()) + [getattr(D, 'DOOR_LEAF_FINISH', None)]:
        if c and c not in codes:
            codes.append(c)
    paint0 = next((c for c in codes if D.mat(c).get('tex') == 'paint'), None)
    for i_, code in enumerate(codes, 1):
        m = D.mat(code)
        tex = m.get('tex', 'paint')
        key = mkey(code)
        name = code + ' ' + D.FINISH.get(code, '').split(',')[0][:60]
        if tex == 'paint':
            tex_material(key, name, key.lower() + '_paint.jpg',
                         T.paint(1000, 1000, mpp, T._col(code), i_, gradient=False), (1000, 1000), ifc_mat=name)
        elif tex == 'panels' and m.get('style') == 'boiserie':      # буазери: фон — окраска, молдинги — геометрией
            tex_material(key, name, key.lower() + '_paint.jpg',
                         T.paint(1000, 1000, mpp, T._col(code), i_, gradient=False), (1000, 1000), ifc_mat=name)
        elif tex == 'panels':
            tex_material(key, name, key.lower() + '_panels.jpg',
                         T.panels(1200, 1200, mpp, 0.0, step=m.get('step', 600), col=T._col(code)), (1200, 1200), ifc_mat=name)
        elif tex == 'tiles':
            tw_, th_ = m.get('tw', 600), m.get('th', 600)
            n = 4
            arr = T.tiles(tw_ * n, th_ * n, 0.75 if max(tw_, th_) < 400 else 1.0, code, tw_, th_, 0.0, 0.0, 0.0, 0.0, seed=5)
            tex_material(key, name, key.lower() + '_tiles.jpg', arr, (tw_ * n, th_ * n), ifc_mat=name)
    if 'C1' not in MATS:            # откосы и полотна по умолчанию — основной тон стен
        c0 = paint0 or 'С1'
        tex_material('C1', 'Окраска стен', 'c1_paint.jpg', T.paint(1000, 1000, mpp, T._col(c0, (221, 214, 203)), 1, gradient=False),
                     (1000, 1000), ifc_mat='Окраска стен')
    ceil_code = next((D.ROOM[k].get('ceil_code') for k in D.ROOM if D.ROOM[k].get('ceil_code')), 'Пт1')
    tex_material('CEIL', 'Окраска потолка ' + D.NCS.get('ceil', ''), 'ceiling.jpg',
                 T.paint(1000, 1000, mpp, T._col(ceil_code, T.COL['Пт']), 3, gradient=False), (1000, 1000), ifc_mat='Потолок ГКЛ, окраска')
    rng = T._rng('walnut3d')
    tex_material('WALNUT', 'Шпон ореха', 'walnut.jpg', tileable(T.wood(2700, 680, T.COL['walnut'], rng, 1.0, 'v'), 300, 80),
                 (600, 2400), grain=True, spec=0.25)
    rng = T._rng('oak3d')
    tex_material('OAK', 'Дуб, масло', 'oak.jpg', tileable(T.wood(2700, 680, T.COL['oak'], rng, 1.0, 'v', fig=0.8), 300, 80),
                 (600, 2400), grain=True, spec=0.2)
    tex_material('FRONT', 'Фасады мебели ' + D.NCS.get('wall', '') + ' мат.', 'front.jpg',
                 T.paint(800, 800, mpp, T.COL['front'], 7, gradient=False), (800, 800))
    for key, nm, col in (('FAB_TAUPE', 'Ткань тёплый серый (диван)', (168, 160, 150)), ('FAB_GREY', 'Ткань серо-бежевая (кровать)', (186, 178, 168)),
                         ('FAB_OLIVE', 'Ткань олива (банкетка)', (128, 132, 96)), ('FAB_LINEN', 'Лён светлый', (226, 220, 208)),
                         ('FAB_RUG', 'Ковёр шерсть, светлый', (205, 196, 182)), ('FAB_CHAIR', 'Ткань стульев', (150, 140, 128))):
        tex_material(key, nm, key.lower() + '.jpg', tileable(T.fabric(240, 240, 0.25, col, 3), 80, 80), (220, 220))
    tex_material('CONCRETE', 'Железобетон (плиты, существующие)', 'concrete.jpg', T.concrete_tex(1500, 1500, 3.0, 4), (1500, 1500))
    mat('PLASTER', 'Штукатурка (стены, сущ.)', (0.86, 0.84, 0.80))
    mat('SCREED', 'Сухая стяжка / основание пола', (0.74, 0.73, 0.71))
    mat('BLACK', 'Металл чёрный матовый RAL 9005', (0.07, 0.07, 0.07), refl='METAL', spec=0.3)
    mat('STEEL', 'Нержавеющая сталь', (0.72, 0.72, 0.72), refl='METAL', spec=0.6)
    mat('CERAMIC', 'Санфаянс белый', (0.96, 0.96, 0.95), refl='PLASTIC', spec=0.6)
    mat('WHITE', 'Белый матовый (техника, радиаторы)', (0.94, 0.94, 0.93), refl='PLASTIC', spec=0.2)
    mat('PVC', 'ПВХ белый (окна)', (0.96, 0.96, 0.95), refl='PLASTIC', spec=0.3)
    mat('GLASS', 'Стекло прозрачное', (0.72, 0.80, 0.82), transp=0.78, refl='GLASS', spec=0.8)
    mat('GLASS_SH', 'Стекло закалённое 8 мм (душ)', (0.80, 0.86, 0.86), transp=0.82, refl='GLASS', spec=0.8)
    mat('MIRROR', 'Зеркало', (0.78, 0.82, 0.84), refl='MIRROR', spec=0.9)
    mat('BLACKGLASS', 'Стекло чёрное (техника)', (0.04, 0.04, 0.05), refl='GLASS', spec=0.8)
    mat('SCREEN', 'Экран ТВ', (0.03, 0.03, 0.04), refl='GLASS', spec=0.7)
    mat('LED', 'Светодиодная лента (свечение)', (1.0, 0.93, 0.78))
    mat('GRAPHITE', 'ЭУИ графит', (0.22, 0.22, 0.23), refl='PLASTIC', spec=0.3)
    mat('LINEN_SHEER', 'Тюль лён', (0.93, 0.91, 0.86), transp=0.35)
    mat('BLIND', 'Рулонная штора блэкаут', (0.80, 0.77, 0.72))
    mat('MATTRESS', 'Постельное бельё белое', (0.95, 0.94, 0.92))
    mat('ENTRY', 'Входная дверь, металл графит', (0.22, 0.22, 0.24), refl='METAL', spec=0.3)
    mat('SPACE', 'Пространство помещения', (0.55, 0.75, 0.95), transp=0.85)
    # детализация: инженерия, декор, фурнитура
    mat('BRASS', 'Латунь матовая (фурнитура, декор светильников)', (0.71, 0.58, 0.34), refl='METAL', spec=0.55)
    mat('NICKEL', 'Сатин-никель (смесители, лейки)', (0.70, 0.70, 0.69), refl='METAL', spec=0.6)
    mat('PP_GREY', 'Полипропилен серый (канализация)', (0.55, 0.57, 0.58), refl='PLASTIC', spec=0.2)
    mat('PEX_BLUE', 'PEX в гофре — ХВС (синий)', (0.15, 0.35, 0.80), refl='PLASTIC', spec=0.2)
    mat('PEX_RED', 'PEX в гофре — ГВС (красный)', (0.80, 0.16, 0.14), refl='PLASTIC', spec=0.2)
    mat('COPPER', 'Медь (фреоновая трасса) в изоляции', (0.72, 0.45, 0.28), refl='METAL', spec=0.4)
    mat('DUCT', 'Воздуховод ПВХ Ø100', (0.90, 0.90, 0.88), refl='PLASTIC', spec=0.2)
    mat('HEATMAT', 'Нагревательный мат (тёплый пол)', (0.92, 0.45, 0.12))
    mat('OPAL', 'Опаловое стекло (плафоны)', (0.97, 0.96, 0.93), transp=0.0, refl='PLASTIC', spec=0.4)
    mat('CRYSTAL', 'Хрусталь', (0.92, 0.94, 0.96), transp=0.55, refl='GLASS', spec=0.9)
    mat('STEELFRAME', 'Сталь окрашенная (рама инсталляции)', (0.35, 0.38, 0.40), refl='METAL', spec=0.3)
    mat('GKL', 'ГКЛ / ГКЛВ (короба, ниши)', (0.88, 0.88, 0.86))
    mat('ACRYL', 'Ванна — санитарный акрил, белый глянец', (0.97, 0.97, 0.96), refl='PLASTIC', spec=0.7)
    T.COL['marble'] = T._col('С6', (242, 240, 236)) if 'С6' in D.FINISH else (242, 240, 236)
    tex_material('MARBLE', 'Кварц / керамика под мрамор Calacatta (столешница, фартук)', 'marble_top.jpg',
                 T.marble(1600, 1600, 0.8, 5), (1600, 1600), ifc_mat='Кварц под мрамор (столешница)')
    tex_material('MARBLE_SILL', 'Мрамор белый (пороги)', 'marble_sill.jpg', T.marble(600, 600, 2.0, 9), (600, 600),
                 ifc_mat='Мрамор (пороги)')
    for it in D.ITEMS:
        if it.get('fabric_col'):
            fabric_mat(it['fabric_col'])


def fabric_mat(col):
    key = 'FAB_%02X%02X%02X' % tuple(int(c) for c in col)
    if key not in MATS:
        tex_material(key, 'Ткань обивки RGB %d/%d/%d' % tuple(col), key.lower() + '.jpg',
                     tileable(T.fabric(240, 240, 0.25, tuple(col), 3), 80, 80), (220, 220), ifc_mat='Ткань обивки')
    return key


def unique_texture(key, name, fname, arr, ifc_mat):
    """Уникальная фактура (UV задаются явно 0..1) — полы помещений, плитка/мрамор по раскладке."""
    return tex_material(key, name, fname, arr, (1, 1), unique=True, ifc_mat=ifc_mat)


# ---------------------------------------------------------------- сетки
class Part:
    def __init__(s, mat_key):
        s.mat = mat_key
        s.v = []      # вершины
        s.t = []      # треугольники (индексы вершин)
        s.uv = []     # uv по углам треугольников: [(u,v),(u,v),(u,v)]
        s.vn = {}     # сглаженные нормали вершин (индекс -> (nx, ny, nz)) для многополигональных поверхностей

    def face(s, pts, uvs):
        """Плоский выпуклый многоугольник (вершины в порядке обхода против часовой при взгляде снаружи)."""
        base = len(s.v)
        s.v.extend(pts)
        for i in range(1, len(pts) - 1):
            s.t.append((base, base + i, base + i + 1))
            s.uv.append((uvs[0], uvs[i], uvs[i + 1]))


class Elem:
    def __init__(s, cls, name, room=None, predefined='NOTDEFINED', objtype=None, props=None, mat_names=None, tag=None):
        s.cls, s.name, s.room, s.predef, s.objtype = cls, name, room, predefined, objtype
        s.props = props or {}
        s.parts = {}
        s.extr = []          # (poly2d, z0, z1, mat) — экструзии (стены, плиты) для IFC
        s.tag = tag
        s.mat_names = mat_names

    def part(s, m):
        if m not in s.parts:
            s.parts[m] = Part(m)
        return s.parts[m]


def _norm(v):
    L = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2) or 1.0
    return (v[0] / L, v[1] / L, v[2] / L)


def default_uv(m, n, p, ext):
    """UV в долях фактуры (реальный размер плитки фактуры m.tile). ext — (du, dv) размеры грани для выбора направления волокон."""
    M = MATS[m]
    tw, th = M.tile
    ax = max(range(3), key=lambda i: abs(n[i]))
    if ax == 2:
        a, b = p[1], p[0]          # верх/низ: u — вдоль y, v — вдоль x
    elif ax == 0:
        a, b = p[1] * (1 if n[0] < 0 else -1), p[2]
    else:
        a, b = p[0] * (1 if n[1] > 0 else -1), p[2]
    if M.grain and ext is not None and ext[0] > ext[1]:
        a, b = b, a                # волокна (вдоль v) — по длинной стороне грани
    return (a / tw, b / th)


def box(el, m, x0, y0, z0, x1, y1, z1, fm=None, uvf=None):
    """Параллелепипед; fm — материалы граней {'+x','-x','+y','-y','+z','-z'}; uvf(mat, normal, point) -> (u, v)."""
    if x1 < x0: x0, x1 = x1, x0
    if y1 < y0: y0, y1 = y1, y0
    if z1 < z0: z0, z1 = z1, z0
    if min(x1 - x0, y1 - y0, z1 - z0) <= 0:
        return
    F = {
        '+x': ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0), (y1 - y0, z1 - z0)),
        '-x': ([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], (-1, 0, 0), (y1 - y0, z1 - z0)),
        '+y': ([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], (0, 1, 0), (x1 - x0, z1 - z0)),
        '-y': ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0), (x1 - x0, z1 - z0)),
        '+z': ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1), (y1 - y0, x1 - x0)),
        '-z': ([(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], (0, 0, -1), (y1 - y0, x1 - x0)),
    }
    for k, (pts, n, ext) in F.items():
        mm = (fm or {}).get(k, m)
        if mm is None:
            continue
        f = uvf or (lambda M_, n_, p_, e_=ext: default_uv(M_, n_, p_, e_))
        try:
            uvs = [f(mm, n, p) for p in pts]
        except TypeError:
            uvs = [f(mm, n, p, ext) for p in pts]
        el.part(mm).face(pts, uvs)


def prism(el, m, poly, z0, z1, top=True, bottom=True, side=True, uvf=None):
    """Призма по многоугольнику (против часовой в плане)."""
    a = 0
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        a += xa * yb - xb * ya
    if a < 0:
        poly = poly[::-1]
    f = uvf or (lambda M_, n_, p_: default_uv(M_, n_, p_, None))
    if side:
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            pts = [(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)]
            n = _norm((yb - ya, -(xb - xa), 0))
            L = math.hypot(xb - xa, yb - ya)
            uvs = [(0, z0 / MATS[m].tile[1]), (L / MATS[m].tile[0], z0 / MATS[m].tile[1]),
                   (L / MATS[m].tile[0], z1 / MATS[m].tile[1]), (0, z1 / MATS[m].tile[1])] if not MATS[m].unique else [f(m, n, p) for p in pts]
            el.part(m).face(pts, uvs)
    tris = ear_clip(poly)
    for z, n, up in ((z1, (0, 0, 1), True), (z0, (0, 0, -1), False)):
        if (up and not top) or (not up and not bottom):
            continue
        for (i, j, k) in tris:
            pts = [(poly[i][0], poly[i][1], z), (poly[j][0], poly[j][1], z), (poly[k][0], poly[k][1], z)]
            if not up:
                pts = pts[::-1]
            el.part(m).face(pts, [f(m, n, p) for p in pts])


def ear_clip(poly):
    """Триангуляция простого многоугольника (против часовой)."""
    idx = list(range(len(poly)))
    tris = []

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        n = len(idx)
        for k in range(n):
            i, j, l = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i], poly[j], poly[l]
            if cross(a, b, c) <= 1e-9:
                continue
            if any(inside(poly[m], a, b, c) for m in idx if m not in (i, j, l)):
                continue
            tris.append((i, j, l))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def ellipse(cx, cy, rx, ry, n=32, a0=0.0):
    return [(cx + rx * math.cos(a0 + 2 * math.pi * i / n), cy + ry * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]


def cyl(el, m, cx, cy, r, z0, z1, n=24):
    prism(el, m, ellipse(cx, cy, r, r, n), z0, z1)


def vquad(el, m, a, b, z0, z1, n, uv_rect=None):
    """Вертикальный прямоугольник по отрезку a–b (план), нормаль n (в плане). uv_rect=(u0,v0,u1,v1) для уникальных фактур."""
    (xa, ya), (xb, yb) = a, b
    pts = [(xa, ya, z0), (xb, yb, z0), (xb, yb, z1), (xa, ya, z1)]
    nn = (n[0], n[1], 0)
    cr = (xb - xa) * n[1] - (yb - ya) * n[0]
    if cr > 0:      # порядок обхода — против часовой при взгляде с нормали
        pts = [pts[1], pts[0], pts[3], pts[2]]
    if uv_rect:
        u0, v0, u1, v1 = uv_rect
        uvs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        if cr > 0:
            uvs = [uvs[0], uvs[1], uvs[2], uvs[3]]
    else:
        uvs = [default_uv(m, nn, p, None) for p in pts]
    el.part(m).face(pts, uvs)


def rect_cells(poly, holes=(), extra_x=(), extra_y=()):
    """Разбиение многоугольника (ортогонального) минус прямоугольные отверстия на прямоугольники."""
    xs = sorted({p[0] for p in poly} | {h[0] for h in holes} | {h[2] for h in holes} | set(extra_x))
    ys = sorted({p[1] for p in poly} | {h[1] for h in holes} | {h[3] for h in holes} | set(extra_y))

    def inpoly(px, py):
        c = False
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            if (ya > py) != (yb > py):
                xi = xa + (py - ya) * (xb - xa) / (yb - ya)
                if xi > px:
                    c = not c
        return c
    grid = {}
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if not inpoly(cx, cy):
                continue
            if any(h[0] <= cx <= h[2] and h[1] <= cy <= h[3] for h in holes):
                continue
            grid[(i, j)] = True
    # слияние по y, затем по x
    rects = []
    used = set()
    for i in range(len(xs) - 1):
        j = 0
        while j < len(ys) - 1:
            if (i, j) in grid and (i, j) not in used:
                j2 = j
                while (i, j2 + 1) in grid and (i, j2 + 1) not in used:
                    j2 += 1
                i2 = i
                while all((i2 + 1, jj) in grid and (i2 + 1, jj) not in used for jj in range(j, j2 + 1)):
                    i2 += 1
                for ii in range(i, i2 + 1):
                    for jj in range(j, j2 + 1):
                        used.add((ii, jj))
                rects.append((xs[i], ys[j], xs[i2 + 1], ys[j2 + 1]))
                j = j2 + 1
            else:
                j += 1
    return rects


def box_minus(b, holes):
    """3D: параллелепипед минус параллелепипеды -> список параллелепипедов."""
    x0, y0, z0, x1, y1, z1 = b
    hs = []
    for h in holes:
        hx0, hy0, hz0, hx1, hy1, hz1 = max(h[0], x0), max(h[1], y0), max(h[2], z0), min(h[3], x1), min(h[4], y1), min(h[5], z1)
        if hx1 > hx0 and hy1 > hy0 and hz1 > hz0:
            hs.append((hx0, hy0, hz0, hx1, hy1, hz1))
    if not hs:
        return [b]
    X = sorted({x0, x1} | {h[0] for h in hs} | {h[3] for h in hs})
    Y = sorted({y0, y1} | {h[1] for h in hs} | {h[4] for h in hs})
    Z = sorted({z0, z1} | {h[2] for h in hs} | {h[5] for h in hs})
    out = []
    for i in range(len(X) - 1):
        for j in range(len(Y) - 1):
            for k in range(len(Z) - 1):
                c = ((X[i] + X[i + 1]) / 2, (Y[j] + Y[j + 1]) / 2, (Z[k] + Z[k + 1]) / 2)
                if any(h[0] < c[0] < h[3] and h[1] < c[1] < h[4] and h[2] < c[2] < h[5] for h in hs):
                    continue
                out.append((X[i], Y[j], Z[k], X[i + 1], Y[j + 1], Z[k + 1]))
    return out


# ---------------------------------------------------------------- доп. примитивы (произвольная ориентация)
def _basis(d):
    """Два единичных вектора, перпендикулярных d."""
    dx, dy, dz = d
    L = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    d = (dx / L, dy / L, dz / L)
    a = (0.0, 0.0, 1.0) if abs(d[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = (d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0])
    Lu = math.sqrt(sum(c * c for c in u))
    u = tuple(c / Lu for c in u)
    v = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    return d, u, v


def tube(el, m, p0, p1, r, n=12, caps=True):
    """Цилиндр между точками p0, p1 (3D) радиуса r — трубы, стойки, штанги."""
    d = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    if math.sqrt(sum(c * c for c in d)) < 0.5:
        return
    d, u, v = _basis(d)
    ring = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    A = [tuple(p0[k] + r * (c * u[k] + s * v[k]) for k in range(3)) for c, s in ring]
    B = [tuple(p1[k] + r * (c * u[k] + s * v[k]) for k in range(3)) for c, s in ring]
    P = el.part(m)
    for i in range(n):
        j = (i + 1) % n
        P.face([A[i], A[j], B[j], B[i]], [(i / n, 0), ((i + 1) / n, 0), ((i + 1) / n, 1), (i / n, 1)])
    if caps:
        P.face(B, [(0.5 + 0.5 * c, 0.5 + 0.5 * s) for c, s in ring])
        P.face(A[::-1], [(0.5 + 0.5 * c, 0.5 + 0.5 * s) for c, s in ring[::-1]])


def polytube(el, m, pts, r, n=12):
    """Трубопровод по ломаной (3D) с шаровыми «отводами» в изломах."""
    for a, b in zip(pts, pts[1:]):
        tube(el, m, a, b, r, n)
    for p in pts[1:-1]:
        sphere(el, m, p, r * 1.15, 6, n)


def sphere(el, m, c, r, nlat=8, nlon=16, sz=1.0):
    """Сфера (эллипсоид при sz≠1) — плафоны, кристаллы, отводы."""
    P = el.part(m)
    for i in range(nlat):
        t0 = math.pi * i / nlat - math.pi / 2
        t1 = math.pi * (i + 1) / nlat - math.pi / 2
        for j in range(nlon):
            f0 = 2 * math.pi * j / nlon
            f1 = 2 * math.pi * (j + 1) / nlon

            def q(t, f):
                return (c[0] + r * math.cos(t) * math.cos(f), c[1] + r * math.cos(t) * math.sin(f), c[2] + r * sz * math.sin(t))
            pts = [q(t0, f0), q(t0, f1), q(t1, f1), q(t1, f0)]
            uv = [(j / nlon, i / nlat), ((j + 1) / nlon, i / nlat), ((j + 1) / nlon, (i + 1) / nlat), (j / nlon, (i + 1) / nlat)]
            if i == 0:
                P.face([pts[0], pts[2], pts[3]], [uv[0], uv[2], uv[3]])
            elif i == nlat - 1:
                P.face([pts[0], pts[1], pts[2]], [uv[0], uv[1], uv[2]])
            else:
                P.face(pts, uv)


def seg_prism(el, m, a, b, w, z0, z1, off=0.0, uvf=None):
    """Брусок вдоль отрезка a–b (план) шириной w, смещённый по нормали на off — ленты, профили, плинтус на косых стенах."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    p = [(a[0] + nx * off, a[1] + ny * off), (b[0] + nx * off, b[1] + ny * off),
         (b[0] + nx * (off + w), b[1] + ny * (off + w)), (a[0] + nx * (off + w), a[1] + ny * (off + w))]
    prism(el, m, p, z0, z1, uvf=uvf)


def clip_rect(poly, rect):
    """Сазерленд — Ходжмен: многоугольник poly ∩ прямоугольник rect (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = rect
    out = list(poly)
    for k, lim, keep in ((0, x0, lambda v, l: v >= l), (0, x1, lambda v, l: v <= l),
                         (1, y0, lambda v, l: v >= l), (1, y1, lambda v, l: v <= l)):
        inp, out = out, []
        if not inp:
            break
        for i in range(len(inp)):
            P, Q = inp[i - 1], inp[i]
            pin, qin = keep(P[k], lim), keep(Q[k], lim)
            if qin:
                if not pin:
                    t = (lim - P[k]) / (Q[k] - P[k])
                    out.append(tuple(P[c] + t * (Q[c] - P[c]) for c in range(2)))
                out.append(Q)
            elif pin:
                t = (lim - P[k]) / (Q[k] - P[k])
                out.append(tuple(P[c] + t * (Q[c] - P[c]) for c in range(2)))
    ded = []
    for q in out:
        q = (float(q[0]), float(q[1]))
        if not ded or abs(q[0] - ded[-1][0]) + abs(q[1] - ded[-1][1]) > 0.01:
            ded.append(q)
    if len(ded) > 1 and abs(ded[0][0] - ded[-1][0]) + abs(ded[0][1] - ded[-1][1]) <= 0.01:
        ded.pop()
    return ded


def parea(p):
    return 0.5 * sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(p, p[1:] + p[:1]))


def poly_cells(poly, holes=()):
    """Многоугольник (в т. ч. с косыми сторонами) минус прямоугольные отверстия:
    (прямоугольники целых ячеек, многоугольники ячеек у косых сторон)."""
    xs = sorted({p[0] for p in poly} | {h[0] for h in holes} | {h[2] for h in holes})
    ys = sorted({p[1] for p in poly} | {h[1] for h in holes} | {h[3] for h in holes})
    full, part = set(), []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            r = (xs[i], ys[j], xs[i + 1], ys[j + 1])
            cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            if any(h[0] <= cx <= h[2] and h[1] <= cy <= h[3] for h in holes):
                continue
            c = clip_rect(poly, r)
            if len(c) < 3:
                continue
            a = abs(parea(c))
            ca = (r[2] - r[0]) * (r[3] - r[1])
            if a < 1.0:
                continue
            if abs(a - ca) < 1.0:
                full.add((i, j))
            else:
                part.append(c)
    rects, used = [], set()
    for i in range(len(xs) - 1):
        j = 0
        while j < len(ys) - 1:
            if (i, j) in full and (i, j) not in used:
                j2 = j
                while (i, j2 + 1) in full and (i, j2 + 1) not in used:
                    j2 += 1
                i2 = i
                while all((i2 + 1, jj) in full and (i2 + 1, jj) not in used for jj in range(j, j2 + 1)):
                    i2 += 1
                for ii in range(i, i2 + 1):
                    for jj in range(j, j2 + 1):
                        used.add((ii, jj))
                rects.append((xs[i], ys[j], xs[i2 + 1], ys[j2 + 1]))
                j = j2 + 1
            else:
                j += 1
    return rects, part
