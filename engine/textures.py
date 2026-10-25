# -*- coding: utf-8 -*-
"""Процедурные «фотореалистичные» текстуры отделки для развёрток и спецификаций.
Текстура строится в реальном масштабе (мм) и растеризуется под масштаб листа: mm_per_px = k * 25.4 / dpi.
Швы плитки/реек дорисовываются вектором поверх (на листе), здесь — только поверхность и тон каждого элемента."""
import os, hashlib, math
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

import paths as _paths
HQ = False          # фотореалистичные фактуры для 3D/рендера (листы альбома — без изменений)
CACHE = _paths.out('tex')
os.makedirs(CACHE, exist_ok=True)

# цвета (sRGB) материалов по умолчанию; цвета кодов отделки — design.MATERIALS[код]['col']
COL = {
    'front': (214, 207, 195),
    'walnut': (98, 66, 44),
    'oak': (198, 166, 124),
    'fabric': (178, 170, 158),
    'black': (24, 22, 21),
    'Пт': (242, 242, 240),
}


def _mat(code):
    try:
        import model as D
        return D.mat(code)
    except Exception:
        return {}


def _col(code, default=(200, 200, 200)):
    """Цвет кода отделки: MATERIALS[code]['col'] (или код-образец 'like'), затем COL."""
    m = _mat(code)
    if 'col' in m:
        return tuple(m['col'])
    if 'like' in m:
        return _col(m['like'], default)
    return COL.get(code, default)


def _rng(*key):
    h = hashlib.md5(repr(key).encode()).hexdigest()
    return np.random.default_rng(int(h[:12], 16))


def noise(h, w, cell, rng, octaves=4, persist=0.5):
    """fBm value noise: h×w, cell — размер крупной ячейки в пикселях."""
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    c = max(cell, 1.0)
    for _ in range(octaves):
        gh, gw = int(h / c) + 3, int(w / c) + 3
        g = rng.random((gh, gw)).astype(np.float32)
        z = ndimage.zoom(g, (c, c), order=3, mode='reflect', grid_mode=True)
        z = z[:h, :w]
        if z.shape != (h, w):
            z = np.pad(z, ((0, h - z.shape[0]), (0, w - z.shape[1])), mode='edge')
        out += amp * z
        tot += amp
        amp *= persist
        c = max(c / 2.0, 1.0)
    return out / tot


def _save(arr, key, alpha=None):
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    path = os.path.join(CACHE, hashlib.md5(repr(key).encode()).hexdigest()[:16] + ('.png' if alpha is not None else '.jpg'))
    if not os.path.exists(path):
        if alpha is not None:
            a = np.clip(alpha, 0, 255).astype(np.uint8)
            Image.fromarray(np.dstack([arr, a]), 'RGBA').save(path, optimize=True)
        else:
            Image.fromarray(arr, 'RGB').save(path, quality=86, optimize=True)
    return path


def _base(h, w, col):
    a = np.empty((h, w, 3), np.float32)
    a[:] = col
    return a


def _grid_px(W, H, mpp):
    return max(2, int(round(W / mpp))), max(2, int(round(H / mpp)))


def paint(W, H, mpp, col, seed=0, gradient=True):
    w, h = _grid_px(W, H, mpp)
    rng = _rng('paint', W, H, mpp, col, seed)
    a = _base(h, w, col)
    n = noise(h, w, 600 / mpp, rng, 3) - 0.5
    f = noise(h, w, 3, rng, 2) - 0.5
    lum = 7.0 * n + 3.0 * f
    if gradient:   # мягкий свет сверху и затенение к полу/углам
        yy = np.linspace(-1, 1, h)[:, None]
        xx = np.linspace(-1, 1, w)[None, :]
        lum = lum + 5.0 * (-yy) * 0.6 - 4.0 * (np.abs(xx) ** 3)
    a += lum[..., None]
    return a


def _n1(x, rng, wl):
    """1D value noise по массиву координат x (мм), длина волны wl."""
    n = int((x.max() - x.min()) / wl) + 4
    g = rng.random(n)
    t = (x - x.min()) / wl
    i = np.floor(t).astype(int)
    f = t - i
    f = f * f * (3 - 2 * f)
    return g[i] * (1 - f) + g[np.minimum(i + 1, n - 1)] * f


def wood(h, w, col, rng, mpp, along='v', fig=1.0):
    """Шпон (радиальный/тангенциальный распил): почти прямые полосы волокон переменной плотности вдоль 'v' или 'h'."""
    if along == 'h':
        return np.transpose(wood(w, h, col, rng, mpp, 'v', fig), (1, 0, 2))
    xx = np.arange(w)[None, :] * mpp
    yy = np.arange(h)[:, None] * mpp
    warp = (noise(h, w, 900 / mpp, rng, 3) - 0.5) * 60 * fig + (noise(h, w, 160 / mpp, rng, 2) - 0.5) * 8
    xw = (xx + warp)
    flat = xw.ravel()
    s = 0.5 * _n1(flat, rng, 34) + 0.3 * _n1(flat, rng, 13) + 0.2 * _n1(flat, rng, 5)
    s = s.reshape(xw.shape)
    s = (s - s.mean()) / (s.std() + 1e-6)
    # тёмные «линии» поздней древесины
    late = np.exp(-((_n1(flat, rng, 9).reshape(xw.shape) - 0.5) / 0.06) ** 2)
    patches = noise(h, w, 1300 / mpp, rng, 2) - 0.5
    along_var = noise(h, w, 420 / mpp, rng, 2) - 0.5
    a = _base(h, w, col)
    lum = s * 11 - late * 16 * fig + patches * 20 + along_var * 6
    lum += (noise(h, w, 1.2, rng, 1) - 0.5) * 6
    # поры: короткие тёмные штрихи вдоль волокон
    if HQ:
        pr = noise(h, w, 1.0, rng, 1)
        pores = ndimage.uniform_filter1d((pr > 0.86).astype(np.float32), size=max(2, int(6 / mpp)), axis=0)
        lum -= pores * 22 * fig
    a[..., 0] += lum * 1.05
    a[..., 1] += lum * 0.82
    a[..., 2] += lum * 0.62
    return a


def slats(W, H, mpp, s0=0.0, step=60, slat=40, seed=0):
    """С3: рейки 40 мм шпон ореха с шагом 60 на чёрной подложке (s0 — реальная координата левого края)."""
    w, h = _grid_px(W, H, mpp)
    rng = _rng('slats', W, H, mpp, s0, seed)
    a = _base(h, w, COL['black'])
    a += (noise(h, w, 4, rng, 2)[..., None] - 0.5) * 6
    xs = np.arange(w) * mpp + s0
    k0 = int(math.floor(s0 / step)) - 1
    k1 = int(math.ceil((s0 + W) / step)) + 1
    for k in range(k0, k1):
        xa, xb = k * step, k * step + slat
        ia, ib = int(round((xa - s0) / mpp)), int(round((xb - s0) / mpp))
        ia2, ib2 = max(ia, 0), min(ib, w)
        if ib2 - ia2 < 1:
            continue
        r2 = _rng('slat', k, seed)
        tone = np.array(COL['walnut'], np.float32) * (0.9 + 0.22 * r2.random())
        sl = wood(h, ib - ia + 2, tuple(tone), r2, mpp, 'v', fig=0.6)
        sl = sl[:, (ia2 - ia):(ia2 - ia) + (ib2 - ia2)]
        # объём рейки: светлее середина, тень по краям
        prof = np.linspace(-1, 1, ib - ia + 2)[(ia2 - ia):(ia2 - ia) + (ib2 - ia2)]
        sl += (12 * (1 - prof ** 2) - 6)[None, :, None]
        a[:, ia2:ib2] = sl
    return a


def tiles(W, H, mpp, code, tw, th, so, zo, s0, z0, seed=0):
    """Плитка: тон каждой плитки + поверхность. so, zo — начало раскладки (реальные), s0, z0 — угол зоны."""
    w, h = _grid_px(W, H, mpp)
    rng = _rng('tiles', code, W, H, mpp, tw, th, so, zo, s0, z0, seed)
    col = _col(code)
    a = _base(h, w, col)
    xs = s0 + (np.arange(w) + 0.5) * mpp
    zs = z0 + H - (np.arange(h) + 0.5) * mpp          # строки сверху вниз
    ki = np.floor((xs - so) / tw).astype(int)[None, :]
    kj = np.floor((zs - zo) / th).astype(int)[:, None]
    tid = (ki * 7919 + kj * 104729 + seed * 31) % 100003
    hsh = np.sin(tid.astype(np.float64) * 12.9898 + 78.233) * 43758.5453
    u1 = hsh - np.floor(hsh)
    hsh2 = np.sin(tid.astype(np.float64) * 4.1414 + 11.17) * 24634.6345
    u2 = hsh2 - np.floor(hsh2)
    tv = ((u1 + u2 - 1.0) * 1.7).astype(np.float32)
    fx = ((xs - so) / tw) % 1.0
    fz = ((zs - zo) / th) % 1.0
    style = _mat(code).get('style')
    if style == 'relief':   # рельефная ручная плитка: перепады тона, «подушка», края
        lum = tv * 9.0
        edge = np.minimum(np.minimum(fx, 1 - fx)[None, :] * tw, np.minimum(fz, 1 - fz)[:, None] * th)
        lum = lum - 14 * np.exp(-edge / 6.0) + 5
        wav = noise(h, w, 40 / mpp, rng, 3) - 0.5
        lum = lum + wav * 16 + (noise(h, w, 1.5, rng, 1) - 0.5) * 8
        # лёгкий наклон каждой плитки (ручная работа)
        tilt = (((tid * 37) % 11) / 10.0 - 0.5).astype(np.float32)
        lum = lum + tilt * (fz[:, None] - 0.5) * 10
        a += lum[..., None]
        a[..., 0] += lum * 0.05
    elif style == 'porcelain':  # керамогранит: мягкие облака + мелкое зерно
        lum = tv * 3.0 + (noise(h, w, 520 / mpp, rng, 4) - 0.5) * 12 + (noise(h, w, 1.5, rng, 1) - 0.5) * 6
        edge = np.minimum(np.minimum(fx, 1 - fx)[None, :] * tw, np.minimum(fz, 1 - fz)[:, None] * th)
        lum = lum - 6 * np.exp(-edge / 4.0)
        a += lum[..., None]
    elif style == 'marble':   # керамогранит под мрамор: прожилки (непрерывные) + тон плитки + шов
        COL['marble'] = col
        a = marble(W, H, mpp, seed + int(abs(so) + abs(zo)) % 7)
        edge = np.minimum(np.minimum(fx, 1 - fx)[None, :] * tw, np.minimum(fz, 1 - fz)[:, None] * th)
        a += (tv * 1.5 - 7 * np.exp(-edge / 3.0))[..., None]
    elif style == 'octagon':  # октагон с чёрной вставкой-кабошоном в углах
        cut = _mat(code).get('cut', 0.293)
        dx_ = np.minimum(fx, 1 - fx)[None, :]
        dz_ = np.minimum(fz, 1 - fz)[:, None]
        ins = (dx_ + dz_) < cut * 0.98
        lum = tv * 2.0 + (noise(h, w, 260 / mpp, rng, 3) - 0.5) * 6
        a += lum[..., None]
        dark = np.array(_mat(code).get('insert_col', (28, 28, 30)), np.float32)
        a = np.where(ins[..., None], dark[None, None, :] + (lum * 0.3)[..., None], a)
        # шов по контуру октагона и вставки
        ed = np.minimum(np.abs((dx_ + dz_) - cut) * min(tw, th) / 1.41, np.minimum(dx_ * tw, dz_ * th))
        a -= (18 * np.exp(-ed / 2.5))[..., None]
    else:
        lum = tv * 4 + (noise(h, w, 300 / mpp, rng, 3) - 0.5) * 10
        a += lum[..., None]
    return a


def marble(W, H, mpp, seed=0, vein_col=None):
    """Калакатта: крупные неровные прожилки (гребни шума с искажением домена) + мягкие вторичные.
    vein_col — цвет прожилок (RGB); по умолчанию золотисто-серый (Калакатта); серый — Статуарио."""
    w, h = _grid_px(W, H, mpp)
    rng = _rng('marble', W, H, mpp, seed)
    a = _base(h, w, COL['marble'])
    # искажение домена
    wx = (noise(h, w, 900 / mpp, rng, 4, 0.55) - 0.5) * 2
    wy = (noise(h, w, 900 / mpp, rng, 4, 0.55) - 0.5) * 2
    xx = np.arange(w)[None, :] * mpp
    yy = np.arange(h)[:, None] * mpp
    u = xx * 0.6 + yy * 0.8 + wx * 420
    v = -xx * 0.8 + yy * 0.6 + wy * 420
    # основные прожилки — гребни функции по u с низкочастотным шумом
    base = noise(h, w, 1400 / mpp, rng, 3, 0.5)
    f1 = np.sin(u / 1100 * 2 * math.pi + base * 6)
    ridge1 = (1 - np.abs(f1)) ** 14
    f2 = np.sin(v / 520 * 2 * math.pi + wx * 3 + base * 4)
    ridge2 = (1 - np.abs(f2)) ** 30
    det = noise(h, w, 30 / mpp, rng, 3, 0.6)
    # сеть тонких прожилок: «гребневый» фрактальный шум с искажением домена
    if HQ:
        rn = noise(h, w, 260 / mpp, rng, 5, 0.55)
        ridged = (1 - np.abs(2 * rn - 1)) ** 22
        rn2 = noise(h, w, 110 / mpp, rng, 4, 0.5)
        ridged2 = (1 - np.abs(2 * rn2 - 1)) ** 40
    if HQ:
        vein = np.clip(ridge1 * (0.55 + 0.6 * det) + ridge2 * 0.45 * det + ridged * 0.55 + ridged2 * 0.25, 0, 1)
    else:
        vein = np.clip(ridge1 * (0.55 + 0.6 * det) + ridge2 * 0.45 * det, 0, 1)
    halo = (1 - np.abs(f1)) ** 4 * 0.22
    cloud = (noise(h, w, 500 / mpp, rng, 4) - 0.5) * 9
    a = a + cloud[..., None]
    gold = np.array([176, 146, 104], np.float32)
    grey = np.array([120, 116, 112], np.float32)
    vc = gold * 0.6 + grey * 0.4 if vein_col is None else np.array(vein_col, np.float32)
    m = vein[..., None]
    a = a * (1 - m * 0.8) + vc * (m * 0.8)
    a = a - (halo * 14)[..., None]
    a[..., 2] -= halo * 6
    g = np.linspace(0, 1, w)[None, :] * 0.5 + np.linspace(1, 0, h)[:, None] * 0.5
    a += (g[..., None] - 0.5) * 7
    if HQ:                       # кристаллическое зерно камня
        sp = rng.random((h, w)).astype(np.float32)
        a += ((sp > 0.997) * -18 + (sp < 0.004) * 10)[..., None]
        a += ((noise(h, w, 2.0, rng, 1) - 0.5) * 4)[..., None]
    return a


def boiserie(W, H, mpp, s0=0.0, step=900, seed=0, col=(236, 230, 220), margin=130, mold=40):
    """Стеновые панели «буазери»: рамки из молдингов по окраске (нижний пояс до 1/3 высоты, верхние рамки)."""
    a = paint(W, H, mpp, col, seed, gradient=True)
    h, w = a.shape[:2]
    xs = s0 + (np.arange(w) + 0.5) * mpp
    zs = H - (np.arange(h) + 0.5) * mpp
    fx = np.mod(xs, step)
    zb = H * 0.33
    shade = np.zeros((h, w), np.float32)
    for lo, hi in ((margin, zb - margin * 0.6), (zb + margin * 0.6, H - margin)):
        if hi - lo < 3 * mold:
            continue
        inz = (zs >= lo) & (zs <= hi)
        inx = (fx >= margin) & (fx <= step - margin)
        # кольцо рамки шириной mold: светлая верхняя/левая грань, тень снизу/справа
        dx = np.minimum(fx - margin, step - margin - fx)
        dz = np.minimum(zs - lo, hi - zs)
        ring = (inz[:, None] & inx[None, :]) & ((dx[None, :] < mold) | (dz[:, None] < mold))
        lit = ring & ((fx - margin)[None, :] < (step - margin - fx)[None, :])
        shade += np.where(ring, np.where(lit, 10.0, -12.0), 0.0)
        edge = (inz[:, None] & inx[None, :]) & ((np.abs(dx[None, :] - mold) < mpp * 0.8) | (np.abs(dz[:, None] - mold) < mpp * 0.8))
        shade += np.where(edge, -16.0, 0.0)
    a += shade[..., None]
    return a


def panels(W, H, mpp, s0=0.0, step=600, seed=0, col=(176, 163, 149)):
    """Окрашенные панели МДФ с V-швами по вертикали."""
    a = paint(W, H, mpp, col, seed, gradient=True)
    h, w = a.shape[:2]
    xs = s0 + (np.arange(w) + 0.5) * mpp
    d = ((xs - 0) % step)
    dist = np.minimum(d, step - d)
    groove = np.exp(-(dist / max(4.0, mpp * 0.9)) ** 2)
    side = np.sign(((xs % step) - step / 2))
    a -= (groove * 28)[None, :, None]
    a += (np.exp(-((dist - 6) / max(3.0, mpp)) ** 2) * 8 * (side > 0))[None, :, None]
    return a


def veneer_front(W, H, mpp, along='h', col=None, seed=0):
    w, h = _grid_px(W, H, mpp)
    rng = _rng('veneer', W, H, mpp, along, seed)
    return wood(h, w, col or COL['walnut'], rng, mpp, along)


def fabric(W, H, mpp, col=None, seed=0):
    w, h = _grid_px(W, H, mpp)
    rng = _rng('fabric', W, H, mpp, seed)
    a = _base(h, w, col or COL['fabric'])
    xx = np.arange(w)[None, :] * mpp
    yy = np.arange(h)[:, None] * mpp
    pitch = 1.6                                         # шаг нитей, мм
    wx = np.sin(xx / pitch * math.pi) ** 2
    wy = np.sin(yy / pitch * math.pi) ** 2
    cell = ((np.floor(xx / pitch) + np.floor(yy / pitch)) % 2).astype(np.float32)
    weave_p = np.where(cell > 0, wx, wy) * 10 - 5      # саржевое переплетение
    slub = (noise(h, w, 25 / mpp, rng, 2) - 0.5) * 9    # неровность пряжи
    weave = weave_p + slub + (noise(h, w, 1.2, rng, 1) - 0.5) * 8 + (noise(h, w, 80 / mpp, rng, 3) - 0.5) * 10
    if not HQ:
        rng = _rng('fabric', W, H, mpp, seed)
        weave = (noise(h, w, 1.2, rng, 1) - 0.5) * 14 + (noise(h, w, 80 / mpp, rng, 3) - 0.5) * 10
    a += weave[..., None]
    yy = np.linspace(-1, 1, h)[:, None]
    a += (-yy * 6)[..., None]
    return a


def mirror(W, H, mpp, seed=0):
    w, h = _grid_px(W, H, mpp)
    rng = _rng('mirror', W, H, mpp, seed)
    a = _base(h, w, (196, 206, 212))
    xx = np.linspace(0, 1, w)[None, :]
    yy = np.linspace(0, 1, h)[:, None]
    g = (xx * 0.6 + (1 - yy) * 0.4)
    a += (g * 38 - 12)[..., None]
    band = np.exp(-((xx - yy * 0.8 - 0.15) / 0.07) ** 2) * 26 + np.exp(-((xx - yy * 0.8 - 0.42) / 0.03) ** 2) * 16
    a += band[..., None]
    a[..., 2] += 6
    return a


def screen(W, H, mpp, seed=0):
    w, h = _grid_px(W, H, mpp)
    a = _base(h, w, (18, 19, 22))
    xx = np.linspace(0, 1, w)[None, :]
    yy = np.linspace(0, 1, h)[:, None]
    a += (np.exp(-((xx + yy * 0.6 - 0.55) / 0.12) ** 2) * 26)[..., None]
    return a


def glass(W, H, mpp, seed=0):
    w, h = _grid_px(W, H, mpp)
    a = _base(h, w, (214, 228, 232))
    xx = np.linspace(0, 1, w)[None, :]
    yy = np.linspace(0, 1, h)[:, None]
    band = np.exp(-((xx - yy * 0.7 - 0.1) / 0.05) ** 2) + 0.6 * np.exp(-((xx - yy * 0.7 - 0.3) / 0.02) ** 2)
    a += (band * 30)[..., None]
    alpha = np.full((h, w), 70.0) + band * 90
    return a, alpha


def boards(W, H, mpp, polys, col, seed=0, along_of=None):
    """Доски по многоугольникам (мм): тон каждой доски + волокна; швы — тёмные."""
    from PIL import ImageDraw
    w, h = _grid_px(W, H, mpp)
    rng = _rng('boards', W, H, mpp, seed, len(polys))
    if along_of is not None:   # ёлочка: волокна вдоль досок под ±45°
        dg = int(math.hypot(w, h)) + 4
        big = wood(dg, dg, col, rng, mpp, 'h', fig=0.7)
        def rot(arr, ang):
            im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).rotate(ang, resample=Image.BICUBIC)
            r = np.asarray(im, np.float32)
            y0, x0 = (dg - h) // 2, (dg - w) // 2
            return r[y0:y0 + h, x0:x0 + w]
        base = rot(big, -45)      # ori 0: доски «вниз-вправо»
        base2 = rot(wood(dg, dg, col, _rng('b2', seed), mpp, 'h', fig=0.7), 45)   # ori 1: «вверх-вправо»
    else:
        base = wood(h, w, col, rng, mpp, 'h', fig=0.7)
        base2 = base
    tone = Image.new('L', (w, h), 128)
    orient = Image.new('L', (w, h), 0)
    dr = ImageDraw.Draw(tone)
    do = ImageDraw.Draw(orient)
    r2 = _rng('btone', seed)
    for i, pg in enumerate(polys):
        pts = [(x / mpp, h - y / mpp) for x, y in pg]
        dr.polygon(pts, fill=int(128 + r2.normal(0, 1) * 16))
        if along_of is not None:
            do.polygon(pts, fill=255 if along_of(i) else 0)
    tv = (np.asarray(tone, np.float32) - 128)
    if along_of is not None:
        m = (np.asarray(orient, np.float32) / 255.0)[..., None]
        a = base * (1 - m) + base2 * m
    else:
        a = base
    a = a + tv[..., None] * 0.9
    # швы
    seams = Image.new('L', (w, h), 0)
    ds = ImageDraw.Draw(seams)
    for pg in polys:
        pts = [(x / mpp, h - y / mpp) for x, y in pg]
        ds.line(pts + [pts[0]], fill=255, width=1)
    sm = np.asarray(seams, np.float32) / 255.0
    a = a - sm[..., None] * 38
    return a


def herringbone_polys(x0, y0, x1, y1, bw=90, bl=600, axis='y'):
    """Английская ёлочка: прямоугольные доски bl×bw, решётка t1=(bw,bw), t2=(bl,-bl), поворот на 45°.
    axis — направление «хребта» ёлочки ('y' или 'x'). Возвращает [(poly, ori)], ori 0/1 — направление волокон."""
    W, L = bw, bl
    ca = math.cos(math.radians(45)); sa = math.sin(math.radians(45))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    R = math.hypot(x1 - x0, y1 - y0) / 2 + L

    def tr(p):   # локальные (u, v) -> модель: поворот на 45° так, чтобы t1 шёл вдоль оси
        u, v = p
        if axis == 'x':
            X, Y = u * ca + v * sa, -u * sa + v * ca
        else:
            X, Y = -u * sa + v * ca, u * ca + v * sa
        return (cx + X, cy + Y)
    out = []
    n1 = int(2 * R / W) + 2
    n2 = int(2 * R / L) + 2
    for i in range(-n1, n1 + 1):
        for j in range(-n2, n2 + 1):
            ox, oy = i * W + j * L, i * W - j * L
            if abs(ox) > 2 * R + L or abs(oy) > 2 * R + L:
                continue
            H = [(ox, oy), (ox + L, oy), (ox + L, oy + W), (ox, oy + W)]
            V = [(ox + L, oy + W - L), (ox + L + W, oy + W - L), (ox + L + W, oy + W), (ox + L, oy + W)]
            for pg, ori in ((H, 0), (V, 1)):
                P = [tr(p) for p in pg]
                xs = [p[0] for p in P]; ys = [p[1] for p in P]
                if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
                    continue
                out.append((P, ori))
    return out


def herringbone_tex(W, H, mpp, seed=0, bw=90, bl=600, axis='y'):
    hp = herringbone_polys(0, 0, W, H, bw, bl, axis=axis)
    polys = [p for p, o in hp]
    ori = [o for p, o in hp]
    return boards(W, H, mpp, polys, COL['oak'], seed, along_of=lambda i: ori[i] == 1)


def planks_tex(W, H, mpp, seed=0, bw=180, bl=1800):
    polys = []
    x = 0
    i = 0
    while x < W:
        off = (i * 600) % bl
        y = -off
        while y < H:
            polys.append([(y, x), (y + bl, x), (y + bl, x + bw), (y, x + bw)])
            y += bl
        x += bw
        i += 1
    # доски вдоль горизонтали образца: меняем оси
    polys = [[(p[0], p[1]) for p in pg] for pg in polys]
    return boards(W, H, mpp, polys, (196, 162, 118), seed)


def concrete_tex(W, H, mpp, seed=0):
    w, h = _grid_px(W, H, mpp)
    rng = _rng('concrete', W, H, mpp, seed)
    a = _base(h, w, (203, 200, 195))
    a += ((noise(h, w, 500 / mpp, rng, 5, 0.6) - 0.5) * 26)[..., None]
    a += ((noise(h, w, 30 / mpp, rng, 3) - 0.5) * 10)[..., None]
    a += ((noise(h, w, 1.2, rng, 1) - 0.5) * 8)[..., None]
    return a


# ---------------- публичный интерфейс ----------------
def make(kind, W, H, k, dpi=220, **kw):
    """Путь к файлу текстуры. W, H — реальные размеры зоны, мм; k — знаменатель масштаба листа."""
    mpp = k * 25.4 / dpi
    key = (kind, round(W, 1), round(H, 1), k, dpi, tuple(sorted((a, (round(b, 2) if isinstance(b, float) else b))
                                                               for a, b in kw.items())))
    if kind == 'glass':
        a, al = glass(W, H, mpp)
        return _save(a, key, al)
    m = _mat(kind) if kind not in COL and kind not in ('mirror', 'screen') else {}
    tex = m.get('tex')
    if tex == 'paint':
        a = paint(W, H, mpp, _col(kind), kw.get('seed', 0), gradient=m.get('gradient', True)) if m.get('gradient', True) \
            else paint(W, H, mpp, _col(kind), gradient=False)
    elif tex == 'panels' and m.get('style') == 'boiserie':
        a = boiserie(W, H, mpp, kw.get('orig_s', 0.0), step=m.get('step', 900), col=_col(kind),
                     margin=m.get('margin', 130), mold=m.get('mold', 40))
    elif tex == 'panels':
        a = panels(W, H, mpp, kw.get('orig_s', 0.0), step=m.get('step', 600), col=_col(kind))
    elif tex == 'slats':
        a = slats(W, H, mpp, kw.get('orig_s', 0.0), step=m.get('step', 60), slat=m.get('slat', 40))
    elif tex == 'tiles':
        if 'tw' in kw:
            a = tiles(W, H, mpp, kind, kw['tw'], kw['th'], kw['so'], kw['zo'], kw.get('orig_s', 0.0), kw.get('orig_z', 0.0))
        else:
            a = tiles(W, H, mpp, m.get('like', kind), m.get('tw', 600), m.get('th', 600), 0, 0, 0.0, 0.0)
    elif tex == 'marble':
        COL['marble'] = _col(kind, (241, 237, 231))
        a = marble(W, H, mpp, kw.get('seed', 0))
    elif tex == 'herringbone':
        a = herringbone_tex(W, H, mpp, kw.get('seed', 0), axis=kw.get('axis', 'y'))
    elif tex == 'planks':
        a = planks_tex(W, H, mpp, kw.get('seed', 0))
    elif tex == 'concrete':
        a = concrete_tex(W, H, mpp, kw.get('seed', 0))
    elif tex == 'plinth':
        a = paint(W, H, mpp, _col(kind, (40, 40, 42)), gradient=False)
    elif kind == 'walnut':
        a = veneer_front(W, H, mpp, kw.get('along', 'h'), seed=kw.get('seed', 0))
    elif kind == 'oak':
        a = veneer_front(W, H, mpp, kw.get('along', 'h'), col=COL['oak'], seed=kw.get('seed', 0))
    elif kind == 'front':
        a = paint(W, H, mpp, COL['front'], kw.get('seed', 0), gradient=False)
    elif kind == 'fabric':
        a = fabric(W, H, mpp, kw.get('col'), kw.get('seed', 0))
    elif kind == 'mirror':
        a = mirror(W, H, mpp)
    elif kind == 'screen':
        a = screen(W, H, mpp)
    else:
        a = paint(W, H, mpp, (200, 200, 200))
    return _save(a, key)


def swatch(kind, size_mm=60, k=10, **kw):
    """Образец материала для спецификации (квадрат size_mm на листе при масштабе 1:k)."""
    return make(kind, size_mm * k, size_mm * k, k, dpi=200, **kw)


# реальный размер показываемого фрагмента для образцов (мм) по типу материала; точно — MATERIALS[код]['sw_real']
SW_BY_TEX = {'herringbone': 1300, 'planks': 1800, 'concrete': 1300, 'paint': 600, 'panels': 1300, 'slats': 420,
             'marble': 900, 'plinth': 300}


def swatch_for(code, size_mm=10.0):
    """Образец отделки по коду (квадрат size_mm на листе)."""
    m = _mat(code)
    tw_, th_ = m.get('tw', 600), m.get('th', 600)
    real = m.get('sw_real') or SW_BY_TEX.get(m.get('tex'), min(1300, max(640, 4 * max(tw_, th_))))
    k = real / size_mm
    kw = {}
    if m.get('tex') == 'tiles' and 'like' not in m:
        kw = dict(tw=tw_, th=th_, so=(tw_ / 2 if tw_ % 2 else tw_ // 2), zo=0)
    return make(code, real, real, k, dpi=max(150, int(size_mm * 25)), **kw)
