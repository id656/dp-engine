# -*- coding: utf-8 -*-
"""Визуализации: перспективные виды из 360°-панорам (без искажений), титульный лист и листы визуализаций."""
import math
import os

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

import model as D

import paths as _paths
AS = _paths.out('viz')                 # производные изображения (виды, полосы)
SRC = _paths.PHOTOS                    # исходные фото/панорамы объекта
LOGO = os.path.join(_paths.BUREAU, 'logo.jpg')

def _cfg():
    try:
        import vizcfg as V
    except ImportError:
        V = None
    return V


_V = _cfg()
# точки съёмки панорам: vizcfg.PANO (рендеры 3D-модели) или vizcfg.CAMS (фото 360° с объекта)
CAMS = getattr(_V, 'PANO', None) or getattr(_V, 'CAMS', {})
VIEWS = getattr(_V, 'VIEWS', {})
STRIPS = getattr(_V, 'STRIPS', [])
VIZ_ROOMS = getattr(_V, 'VIZ_ROOMS', list(VIEWS))
NAMES = {k: D.ROOM[k]['name'] for k in D.ROOM}


def has_photos():
    return bool(STRIPS) and all(os.path.exists(os.path.join(SRC, f'src_{r}.jpg')) for r, _ in STRIPS)


def load_pano(room):
    im = Image.open(os.path.join(SRC, f'src_{room}.jpg')).convert('RGB')
    if abs(im.width / im.height - 2) > 0.02:          # приведение к 2:1 (полная сфера по ширине и высоте)
        im = im.resize((im.width, im.width // 2), Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def perspective(pano, yaw, htan, vt0, vt1, w, h):
    """Прямолинейная проекция: камера горизонтальна (вертикали прямые), сдвиг кадра через vt0..vt1 (tan)."""
    H, W = pano.shape[:2]
    xs = np.linspace(-htan, htan, w)
    ys = np.linspace(vt1, vt0, h)              # строки сверху вниз
    X, Y = np.meshgrid(xs, ys)
    lon = math.radians(yaw) + np.arctan2(X, 1.0)
    lat = np.arctan2(Y, np.sqrt(1.0 + X * X))
    u = (lon / (2 * math.pi) + 0.5) * W - 0.5
    v = (0.5 - lat / math.pi) * H - 0.5
    out = np.empty((h, w, 3), np.float32)
    for c in range(3):
        out[..., c] = ndimage.map_coordinates(pano[..., c], [v, u % W], order=3, mode='wrap')
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), 'RGB')
    return img.filter(ImageFilter.UnsharpMask(radius=2.2, percent=70, threshold=2))


def _fresh(dst, src):
    return os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src)


def view_frame(v):
    """Кадр вида листа визуализации: tan половины горизонтального угла и диапазон tan по вертикали (3:2, сдвиг вниз)."""
    ht = math.tan(math.radians(v['hfov'] / 2))
    vh = ht / 1.5
    sh = 0.12 * 2 * vh                  # сдвиг вниз — больше пола и мебели, вертикали прямые
    vt0, vt1 = v.get('vt', (-vh - sh, vh - sh))
    return ht, vt0, vt1


def strip_frame():
    """Кадр вертикальной полосы титула (54×287 мм): tan половины ширины и диапазон tan по вертикали."""
    vt = math.tan(math.radians(52))
    return vt * 54.0 / 287.0, -vt * 1.08, vt * 0.92


def rendered(name):
    """Кадр, отрендеренный прямо с точки съёмки (tools/model3d.py … vizviews): out/pano/views/<name>.jpg — резче,
    чем вырезка из панорамы; если его нет — вид строится из панорамы photos/src_<пом>.jpg."""
    p = _paths.out('pano', 'views', name + '.jpg')
    return p if os.path.exists(p) else None


def _from_render(src, dst, size):
    img = Image.open(src).convert('RGB')
    if img.size != size:
        img = img.resize(size, Image.LANCZOS)
    img.save(dst, quality=92)
    return dst


def build_assets(only_missing=False):
    """Виды для листов визуализаций (view_<пом>_<i>.jpg) и полосы титула (strip_<k>.jpg) из панорам photos/src_<пом>.jpg
    (или готовых кадров рендера out/pano/views)."""
    os.makedirs(AS, exist_ok=True)
    paths = {}
    cache = {}
    for room, views in VIEWS.items():
        src = os.path.join(SRC, f'src_{room}.jpg')
        if not os.path.exists(src):
            continue
        for i, v in enumerate(views, 1):
            p = os.path.join(AS, f'view_{room}_{i}.jpg')
            r = rendered(f'view_{room}_{i}')
            if only_missing and _fresh(p, r or src):
                continue
            if r:
                paths[(room, i)] = _from_render(r, p, (1800, 1200))
                continue
            if room not in cache:
                cache[room] = load_pano(room)
            ht, vt0, vt1 = view_frame(v)
            img = perspective(cache[room], v['yaw'], ht, vt0, vt1, 1800, 1200)
            img.save(p, quality=92)
            paths[(room, i)] = p
    for k, (room, yaw) in enumerate(STRIPS, 1):
        src = os.path.join(SRC, f'src_{room}.jpg')
        p = os.path.join(AS, f'strip_{k}.jpg')
        r = rendered(f'strip_{k}')
        if only_missing and _fresh(p, r or src):
            continue
        if r:
            paths[('strip', k)] = _from_render(r, p, (640, 3400))
            continue
        pano = cache.get(room) if room in cache else load_pano(room)
        ht, vt0, vt1 = strip_frame()
        img = perspective(pano, yaw, ht, vt0, vt1, 640, 3400)
        img.save(p, quality=92)
        paths[('strip', k)] = p
    return paths


# ------------------------------------------------------------------ листы
def sheet_title(no, total):
    from core import Sheet, tw
    from kit import PROJECT
    sh = Sheet('01', 'Титульный лист')
    if has_photos():
        # четыре вертикальные полосы-фото (как в образце бюро)
        x = 20.0
        for k in range(1, 5):
            sh.image(os.path.join(AS, f'strip_{k}.jpg'), x, 5.0, 54.0, 287.0)
            x += 56.5
    else:
        title_plan(sh)
    cx = 333.0
    # логотип в рамке
    bw, bh = 66.0, 35.0
    lw_, lh_ = 60.0, 60.0 / PROJECT.get('logo_aspect', 2484 / 1197)
    sh.rect(cx - bw / 2, 239, cx + bw / 2, 239 + bh, lw=0.3, color=(0.55, 0.55, 0.55), layer='A-TEXT')
    sh.image(PROJECT.get('logo', LOGO), cx - lw_ / 2, 239 + (bh - lh_) / 2, lw_, lh_)
    grey = (0.45, 0.45, 0.45)
    t = 'дизайн проект'          # Cormorant Unicase: строчные дают «уникейс»-форму, как в образце бюро
    h = 12.0
    sh.text((cx, 205), t, h=h, ha='c', font='CorUniL', color=grey)
    sh.line((258, 200), (408, 200), lw=0.25, color=(0.6, 0.6, 0.6), layer='A-TEXT')
    tot = D.total_area()
    sh.text((cx, 192), PROJECT.get('city', '').upper() + ',', h=2.9, ha='c', font='MontSB', color=grey)
    sh.text((cx, 186.5), f'КВАРТИРА {tot:.1f} М²'.replace('.', ','), h=2.9, ha='c', font='MontSB', color=grey)
    sh.text((cx, 22), PROJECT['cipher'] + ' · РАБОЧАЯ ДОКУМЕНТАЦИЯ', h=2.0, ha='c', font='MontM', color=(0.6, 0.6, 0.6))
    sh.text((cx, 14), f"{PROJECT.get('year', '')} г.", h=2.9, ha='c', font='MontSB', color=grey)
    return sh


def title_plan(sh, box=(20.0, 5.0, 246.0, 292.0)):
    """Титул без фото: цветной план с мебелью, вписанный в левую часть листа."""
    from core import View, Pen
    import drawplan as DP
    xs, ys = D.wall_extent()
    W_, H_ = max(ys) - min(ys), max(xs) - min(xs)          # на листе: ширина — по y, высота — по x
    bx0, by0, bx1, by1 = box
    k = max(W_ / (bx1 - bx0 - 16), H_ / (by1 - by0 - 16))
    X0 = bx0 + ((bx1 - bx0) - W_ / k) / 2 - min(ys) / k
    Y0 = by1 - ((by1 - by0) - H_ / k) / 2 + min(xs) / k
    v = View(X0, Y0, k)
    pen = Pen(sh, v)
    DP.draw_zones(pen)
    DP.COLORED['on'] = True
    try:
        DP.draw_items(pen, skip=('rug',))
    finally:
        DP.COLORED['on'] = False
    DP.draw_walls(pen, fill=(0.30, 0.30, 0.32))
    DP.draw_openings(pen)


def view_dirs(room):
    x, y, yc = CAMS[room]
    return [(x, y, yc - v['yaw'], v['hfov']) for v in VIEWS[room]]


def ray_len(poly, px, py, a, rmax):
    """Расстояние от точки съёмки до стены помещения по направлению a (град), не более rmax."""
    dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
    best = rmax
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        den = dx * ey - dy * ex
        if abs(den) < 1e-9:
            continue
        t = ((x1 - px) * ey - (y1 - py) * ex) / den
        s = ((x1 - px) * dy - (y1 - py) * dx) / den
        if t > 1e-6 and -1e-9 <= s <= 1 + 1e-9:
            best = min(best, t)
    return best


def sheet_viz_factory(room):
    def fn(no, total):
        from core import Sheet, View, Pen, WHITE, BLACK
        from kit import frame, section_title, notes
        import drawplan as DP
        sh = Sheet('V' + room, 'Визуализация')
        name = NAMES[room]
        section_title(sh, 28, 284, f'Визуализация. {name} {room}', h=3.0)
        boxes = [(28, 141, 200.0), (236, 160, 172.0), (28, 4.5, 200.0)]
        for i, (x0, y0, w) in enumerate(boxes, 1):
            hgt = w / 1.5
            yb = y0 if i != 3 else 6.0
            if i == 1:
                yb = 279 - hgt
            if i == 2:
                yb = 279 - hgt
            if i == 3:
                yb = 6.0
            sh.image(os.path.join(AS, f'view_{room}_{i}.jpg'), x0, yb, w, hgt)
            sh.rect(x0, yb, x0 + w, yb + hgt, lw=0.2, layer='A-TEXT')
            sh.circle((x0 + 5, yb + hgt - 5), 3.0, lw=0.3, fill=WHITE, layer='A-TEXT')
            sh.text((x0 + 5, yb + hgt - 5), str(i), h=2.6, ha='c', va='m', font='BoldObl', layer='A-TEXT')
            boxes[i - 1] = (x0, yb, w, hgt)
        # подписи видов (справа от вида 3 и под видом 2)
        x2, y2, w2, h2 = boxes[1]
        caps = [v['cap'] for v in VIEWS[room]]
        notes(sh, 236, y2 - 6, 172, 'Виды', caps, h=1.9, lead=2.8)
        # схема: точка съёмки и направления видов
        poly = D.ROOMS[room]['poly']
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        cxm, cym = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span = max(max(ys) - min(ys), (max(xs) - min(xs)) * 1.0)
        k = 25.0 if span <= 3200 else 50.0          # малые помещения — крупнее
        X, Y = 322.0, 80.0
        v = View(X - cym / k, Y + cxm / k, k)
        pen = Pen(sh, v)
        pen.poly(poly, fill=(0.97, 0.96, 0.94), lw=0.5, layer='A-TEXT')
        for it in D.ITEMS:
            if it['room'] == room:
                DP.draw_item(pen, it, faint_=True)
        cx, cy, _ = CAMS[room]
        P0 = v.P(cx, cy)
        # поля зрения ограничены стенами помещения; рисуются полупрозрачной заливкой поверх плана
        dirs = view_dirs(room)
        for i, (px, py, az, hf) in enumerate(dirs, 1):
            pts = [(px, py)]
            for a in np.linspace(az - hf / 2, az + hf / 2, 40):
                r = ray_len(poly, px, py, a, 6000.0)
                pts.append((px + r * math.cos(math.radians(a)), py + r * math.sin(math.radians(a))))
            pen.poly(pts, fill=(0.99, 0.88, 0.74), lw=0.25, color=(0.80, 0.45, 0.15), layer='A-TEXT', alpha=0.45)
        for i, (px, py, az, hf) in enumerate(dirs, 1):
            # стрелка-направление и номер вида
            r = ray_len(poly, px, py, az, 6000.0)
            rr = max(450.0, r * 0.62)
            tip = (px + rr * math.cos(math.radians(az)), py + rr * math.sin(math.radians(az)))
            pen.line((px, py), tip, lw=0.35, color=(0.80, 0.45, 0.15), layer='A-TEXT')
            T = v.P(*tip)
            sh.circle(T, 2.3, lw=0.3, fill=WHITE, layer='A-TEXT')
            sh.text(T, str(i), h=2.0, ha='c', va='m', font='BoldObl', layer='A-TEXT')
        sh.circle(P0, 1.4, lw=0.3, fill=BLACK, layer='A-TEXT')
        top = Y + (max(xs) - min(xs)) / k / 2
        sh.text((X - (max(ys) - min(ys)) / k / 2, top + 4), f'Точка съёмки и направления видов  М 1:{int(k)}', h=2.0,
                font='BoldObl', layer='A-TEXT')
        frame(sh, no, total, f'{name} {room}.\nВизуализация')
        return sh
    return fn
