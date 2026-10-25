# -*- coding: utf-8 -*-
"""Ядро: листы, вид (поворот/масштаб), перо модели, размеры, рендер PDF и DXF R12."""
import math
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm as MM
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FD = '/usr/share/fonts/truetype/dejavu/'
for _n, _f in [('Reg', 'DejaVuSansCondensed.ttf'), ('Obl', 'DejaVuSansCondensed-Oblique.ttf'),
               ('Bold', 'DejaVuSansCondensed-Bold.ttf'), ('BoldObl', 'DejaVuSansCondensed-BoldOblique.ttf')]:
    pdfmetrics.registerFont(TTFont(_n, FD + _f))
import paths as _paths
_FP = _paths.FONTS + '/'
for _n, _f in [('GOST', 'osifont-gpl2fe.ttf'), ('CorUniL', 'CormorantUnicase-Light.ttf'),
               ('CorUni', 'CormorantUnicase-Regular.ttf'), ('MontSB', 'Montserrat-SemiBold.ttf'),
               ('MontM', 'Montserrat-Medium.ttf'), ('MontR', 'Montserrat-Regular.ttf')]:
    pdfmetrics.registerFont(TTFont(_n, _FP + _f))
CAP = 0.729  # высота прописной / кегль


def fs(h):
    return h / CAP


def tw(s, h, font='Obl'):
    return pdfmetrics.stringWidth(s, font, fs(h))


BLACK = (0, 0, 0)
DARK = (0.22, 0.22, 0.22)
MID = (0.42, 0.42, 0.42)
LIGHT = (0.62, 0.62, 0.62)
WHITE = (1, 1, 1)
WALLFILL = (0.70, 0.70, 0.70)
Z_DAY = (0.965, 0.945, 0.910)
Z_NIGHT = (0.914, 0.933, 0.918)
Z_WET = (0.890, 0.933, 0.953)
Z_OUT = (0.945, 0.945, 0.945)
FILL_LT = (0.86, 0.86, 0.86)


class Sheet:
    def __init__(s, key, title=''):
        s.key = key
        s.title = title
        s.items = []

    def line(s, a, b, lw=0.18, layer='A-ANNO', dash=None, color=BLACK):
        s.items.append(dict(t='line', a=a, b=b, lw=lw, layer=layer, dash=dash, color=color))

    def poly(s, pts, closed=True, lw=0.18, layer='A-ANNO', dash=None, fill=None, stroke=True, color=BLACK,
             alpha=None):
        s.items.append(dict(t='poly', pts=list(pts), closed=closed, lw=lw, layer=layer, dash=dash,
                            fill=fill, stroke=stroke, color=color, alpha=alpha))

    def rect(s, x0, y0, x1, y1, **kw):
        s.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], **kw)

    def arc(s, c, r, a0, a1, lw=0.18, layer='A-ANNO', dash=None, color=BLACK):
        s.items.append(dict(t='arc', c=c, r=r, a0=a0, a1=a1, lw=lw, layer=layer, dash=dash, color=color))

    def circle(s, c, r, lw=0.18, layer='A-ANNO', fill=None, stroke=True, dash=None, color=BLACK):
        s.items.append(dict(t='circle', c=c, r=r, lw=lw, layer=layer, fill=fill, stroke=stroke,
                            dash=dash, color=color))

    def image(s, path, x, y, w, h, clip=None, layer='A-TEX', alpha=False):
        s.items.append(dict(t='image', path=path, x=x, y=y, w=w, h=h, clip=list(clip) if clip else None, layer=layer,
                            alpha=alpha))

    def text(s, p, txt, h=2.5, layer='A-TEXT', ha='l', va='b', rot=0, font='Obl', color=BLACK, bg=False):
        s.items.append(dict(t='text', p=p, s=txt, h=h, layer=layer, ha=ha, va=va, rot=rot, font=font,
                            color=color, bg=bg))


class View:
    """Модель (мм, x вправо, y вверх как на обмере) -> лист (мм), поворот на 90° по часовой."""

    def __init__(v, X0, Y0, k=50.0):
        v.X0, v.Y0, v.k = X0, Y0, k

    def P(v, x, y):
        return (v.X0 + y / v.k, v.Y0 - x / v.k)

    def A(v, a):
        return a - 90.0


class Pen:
    def __init__(p, sh, v):
        p.sh, p.v = sh, v

    def line(p, a, b, **kw):
        p.sh.line(p.v.P(*a), p.v.P(*b), **kw)

    def poly(p, pts, **kw):
        p.sh.poly([p.v.P(*q) for q in pts], **kw)

    def rect(p, x0, y0, x1, y1, **kw):
        p.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], **kw)

    def circle(p, c, r, **kw):
        p.sh.circle(p.v.P(*c), r / p.v.k, **kw)

    def arc(p, c, r, a0, a1, **kw):
        p.sh.arc(p.v.P(*c), r / p.v.k, p.v.A(a0), p.v.A(a1), **kw)

    def text(p, c, s, **kw):
        p.sh.text(p.v.P(*c), s, **kw)


# ---------- геометрические помощники (модель) ----------
def rrect_pts(x0, y0, x1, y1, r, n=4):
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = []
    for cx, cy, a0 in [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]:
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def ell_pts(cx, cy, rx, ry, n=36, a0=0, a1=360):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def rot_pts(pts, cx, cy, ang):
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    return [(cx + x * c - y * s, cy + x * s + y * c) for x, y in pts]


def wall_union_edges(rects):
    """Контур объединения прямоугольников (оси-параллельных): список отрезков."""
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})
    eps = 0.5

    def inside(px, py):
        for x0, y0, x1, y1 in rects:
            if x0 < px < x1 and y0 < py < y1:
                return True
        return False

    segs = set()
    for x0, y0, x1, y1 in rects:
        for yy in (y0, y1):
            cuts = [x for x in xs if x0 <= x <= x1]
            for a, b in zip(cuts, cuts[1:]):
                if b - a < 1e-6:
                    continue
                m = (a + b) / 2
                if inside(m, yy + eps) != inside(m, yy - eps):
                    segs.add(((a, yy), (b, yy)))
        for xx in (x0, x1):
            cuts = [y for y in ys if y0 <= y <= y1]
            for a, b in zip(cuts, cuts[1:]):
                if b - a < 1e-6:
                    continue
                m = (a + b) / 2
                if inside(xx + eps, m) != inside(xx - eps, m):
                    segs.add(((xx, a), (xx, b)))
    # слияние коллинеарных соседних отрезков
    hz, vt = {}, {}
    for (a, b) in segs:
        if a[1] == b[1]:
            hz.setdefault(a[1], []).append((min(a[0], b[0]), max(a[0], b[0])))
        else:
            vt.setdefault(a[0], []).append((min(a[1], b[1]), max(a[1], b[1])))
    out = []
    for y, lst in hz.items():
        lst.sort()
        cur = list(lst[0])
        for s0, s1 in lst[1:]:
            if abs(s0 - cur[1]) < 1e-6:
                cur[1] = s1
            else:
                out.append(((cur[0], y), (cur[1], y)))
                cur = [s0, s1]
        out.append(((cur[0], y), (cur[1], y)))
    for x, lst in vt.items():
        lst.sort()
        cur = list(lst[0])
        for s0, s1 in lst[1:]:
            if abs(s0 - cur[1]) < 1e-6:
                cur[1] = s1
            else:
                out.append(((x, cur[0]), (x, cur[1])))
                cur = [s0, s1]
        out.append(((x, cur[0]), (x, cur[1])))
    return out


def _pip(poly, px, py):
    """Точка внутри многоугольника (чётность пересечений)."""
    c = False
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if (ya > py) != (yb > py):
            xi = xa + (py - ya) * (xb - xa) / (yb - ya)
            if xi > px:
                c = not c
    return c


_OUTLINE_CACHE = {}


def wall_outline(rects, polys=()):
    """Контур объединения стен: прямоугольники + многоугольники (стены с наклонными гранями).
    Без многоугольников — ровно wall_union_edges (оси-параллельный случай)."""
    if not polys:
        return wall_union_edges(rects)
    key = (tuple(tuple(r) for r in rects), tuple(tuple(map(tuple, p)) for p in polys))
    if key in _OUTLINE_CACHE:
        return _OUTLINE_CACHE[key]
    shapes = [[(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])] for r in rects] + [list(p) for p in polys]

    def inside(px, py):
        return any(_pip(s, px, py) for s in shapes)
    edges = [(a, b) for s in shapes for a, b in zip(s, s[1:] + s[:1]) if a != b]
    segs = []
    eps = 0.6
    for (a, b) in edges:
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        ts = {0.0, 1.0}
        for (c, d) in edges:
            ex, ey = d[0] - c[0], d[1] - c[1]
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                if abs((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) < 1e-6 * L:
                    for q in (c, d):
                        t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / (L * L)
                        if 0 < t < 1:
                            ts.add(t)
                continue
            t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / den
            u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / den
            if -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                ts.add(min(1.0, max(0.0, t)))
        ts = sorted(ts)
        nx, ny = -dy / L, dx / L
        for t0, t1 in zip(ts, ts[1:]):
            if (t1 - t0) * L < 0.5:
                continue
            tm = (t0 + t1) / 2
            mx, my = a[0] + dx * tm, a[1] + dy * tm
            if inside(mx + nx * eps, my + ny * eps) != inside(mx - nx * eps, my - ny * eps):
                p = (a[0] + dx * t0, a[1] + dy * t0)
                q = (a[0] + dx * t1, a[1] + dy * t1)
                segs.append((p, q))
    # слияние коллинеарных смежных отрезков, без дублей
    lines = {}
    for p, q in segs:
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        if ux < -1e-9 or (abs(ux) <= 1e-9 and uy < 0):
            ux, uy = -ux, -uy
        off = round(p[0] * uy - p[1] * ux, 1)
        k = (round(ux, 4), round(uy, 4), off)
        t0, t1 = sorted((p[0] * ux + p[1] * uy, q[0] * ux + q[1] * uy))
        lines.setdefault(k, []).append((t0, t1))
    out = []
    for (ux, uy, off), lst in lines.items():
        lst.sort()
        cur = list(lst[0])
        res = []
        for t0, t1 in lst[1:]:
            if t0 <= cur[1] + 0.5:
                cur[1] = max(cur[1], t1)
            else:
                res.append(cur)
                cur = [t0, t1]
        res.append(cur)
        for t0, t1 in res:
            # точка на линии: p = t*u + off*n, n = (uy, -ux)
            out.append(((t0 * ux + off * uy, t0 * uy - off * ux), (t1 * ux + off * uy, t1 * uy - off * ux)))
    _OUTLINE_CACHE[key] = out
    return out


def adim(sh, v, p1, p2, off, txt=None, h=2.5, lw=0.18, layer='A-DIMS'):
    """Наклонный (параллельный) размер отрезка p1–p2 модели; off — отступ размерной линии, мм модели
    (+ — вправо от направления p1→p2 на листе). Засечки 45°, число над линией, читаемо слева направо."""
    A, B = v.P(*p1), v.P(*p2)
    dx, dy = B[0] - A[0], B[1] - A[1]
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return
    ux, uy = dx / L, dy / L
    nx, ny = uy, -ux
    o = off / v.k
    A2 = (A[0] + nx * o, A[1] + ny * o)
    B2 = (B[0] + nx * o, B[1] + ny * o)
    g = 1.0 if o >= 0 else -1.0
    for P, Q in ((A, A2), (B, B2)):
        sh.line((P[0] + nx * g * 1.0, P[1] + ny * g * 1.0), (Q[0] + nx * g * 1.5, Q[1] + ny * g * 1.5), lw=lw, layer=layer)
    sh.line((A2[0] - ux * 1.5, A2[1] - uy * 1.5), (B2[0] + ux * 1.5, B2[1] + uy * 1.5), lw=lw, layer=layer)
    wx, wy = (ux + nx) / math.sqrt(2), (uy + ny) / math.sqrt(2)
    for Q in (A2, B2):
        sh.line((Q[0] - wx * 1.27, Q[1] - wy * 1.27), (Q[0] + wx * 1.27, Q[1] + wy * 1.27), lw=0.35, layer=layer)
    rx, ry = (ux, uy) if (ux > 1e-9 or (abs(ux) <= 1e-9 and uy > 0)) else (-ux, -uy)
    upx, upy = -ry, rx
    M = ((A2[0] + B2[0]) / 2 + upx * 0.6, (A2[1] + B2[1]) / 2 + upy * 0.6)
    s = txt if txt is not None else fmt_dim(math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
    sh.text(M, s, h=h, ha='c', va='b', rot=math.degrees(math.atan2(ry, rx)), layer=layer)


# ---------- размеры ----------
DIM_BOXES = []   # габариты размерных чисел на листе (для обхода подписей)


def fmt_dim(v):
    return str(int(round(abs(v))))


def mdim(sh, v, axis, vals, at, ext=None, h=2.5, lw=0.18, layer='A-DIMS', over=1.5, gap=1.0, rows_allowed=None,
         prefer=None):
    """Размерная цепочка (ГОСТ 2.307 / ГОСТ Р 21.101): засечки 45°, числа над размерной линией.
    Если число не помещается: на крайнем отрезке — на продолжении размерной линии за выносной,
    на внутреннем — на полке линии-выноски.
    axis='y' — значения по модели y (на листе горизонтально), линия на модели x=at.
    axis='x' — значения по модели x (на листе вертикально), линия на модели y=at."""
    n = len(vals)
    if n < 2:
        return
    if ext is None:
        ext = [None] * n
    elif not isinstance(ext, (list, tuple)):
        ext = [ext] * n
    if axis == 'y':
        S = [v.P(at, y)[0] for y in vals]
        L = v.P(at, 0)[1]
        E = [None if e is None else v.P(e, 0)[1] for e in ext]
        horiz = True
    else:
        S = [v.P(x, at)[1] for x in vals]
        L = v.P(0, at)[0]
        E = [None if e is None else v.P(0, e)[0] for e in ext]
        horiz = False
    # упорядочим по листу
    order_idx = sorted(range(n), key=lambda i: S[i])
    S = [S[i] for i in order_idx]
    V = [vals[i] for i in order_idx]
    E = [E[i] for i in order_idx]

    def pt(s, l):
        return (s, l) if horiz else (l, s)

    def po(s, o):  # o — отступ в сторону текста (над линией / слева от вертикальной)
        return (s, L + o) if horiz else (L - o, s)

    for s, e in zip(S, E):
        if e is None or abs(e - L) < 0.3:
            continue
        d = 1 if L > e else -1
        sh.line(pt(s, e + d * gap), pt(s, L + d * 1.5), lw=lw, layer=layer)
    for s in S:
        a, b = pt(s - 0.9, L - 0.9), pt(s + 0.9, L + 0.9)
        sh.line(a, b, lw=0.35, layer=layer)
    smin, smax = S[0], S[-1]
    ext_lo, ext_hi = smin - over, smax + over
    boxes = []
    segs = []
    for i in range(n - 1):
        s0, s1 = S[i], S[i + 1]
        if abs(s1 - s0) < 1e-6:
            continue
        txt = fmt_dim(abs(V[i + 1] - V[i]))
        segs.append((i, s0, s1, txt, tw(txt, h)))

    def free(b):
        return all(b[1] + 0.4 < q[0] or b[0] - 0.4 > q[1] or b[3] + 0.3 < q[2] or b[2] - 0.3 > q[3] for q in boxes)

    def put_text(s_left, o, txt):
        w_ = tw(txt, h)
        if horiz:
            sh.text((s_left, L + o), txt, h=h, ha='l', va='b', layer=layer)
            DIM_BOXES.append((s_left, s_left + w_, L + o, L + o + h))
        else:
            sh.text((L - o, s_left), txt, h=h, ha='l', va='b', rot=90, layer=layer)
            DIM_BOXES.append((L - o - h, L - o, s_left, s_left + w_))

    pend = []
    for (i, s0, s1, txt, w) in segs:
        if s1 - s0 >= w + 0.8:
            b = ((s0 + s1) / 2 - w / 2, (s0 + s1) / 2 + w / 2, 0.6, 0.6 + h)
            boxes.append(b)
            put_text(b[0], 0.6, txt)
        else:
            pend.append((i, s0, s1, txt, w))
    last = n - 2
    pend.sort(key=lambda t: -(t[1] + t[2]))     # справа налево: левые выноски уходят выше и не пересекают правые
    for (i, s0, s1, txt, w) in pend:
        c = (s0 + s1) / 2
        done = False
        # крайние отрезки — на продолжении размерной линии
        cands = []
        if i == 0:
            cands.append(('L', (s0 - 1.2 - w, s0 - 1.2, 0.6, 0.6 + h)))
        if i == last:
            cands.append(('R', (s1 + 1.2, s1 + 1.2 + w, 0.6, 0.6 + h)))
        if prefer == 'R':
            cands.sort(key=lambda t: t[0] != 'R')
        for tag, b in cands:
            if free(b):
                boxes.append(b)
                put_text(b[0], 0.6, txt)
                if tag == 'L':
                    ext_lo = min(ext_lo, b[0] - 0.6)
                else:
                    ext_hi = max(ext_hi, b[1] + 0.6)
                done = True
                break
        if done:
            continue
        # внутренние — на полке линии-выноски
        for dr in (1, -1):              # сначала все полки в одну сторону (без перекрещивания выносок)
            for lev in range(1, 6):
                up = 0.6 + h + 1.2 + (lev - 1) * (h + 1.4)
                k = min(up * 0.55, 3.5)
                sx = c + dr * k
                if dr > 0:
                    b = (sx, sx + w + 0.8, up + 0.35, up + 0.35 + h)
                else:
                    b = (sx - w - 0.8, sx, up + 0.35, up + 0.35 + h)
                if free(b):
                    boxes.append(b)
                    sh.line(po(c, 0), po(sx, up), lw=lw, layer=layer)
                    sh.line(po(sx, up), po(sx + dr * (w + 0.8), up), lw=lw, layer=layer)
                    put_text(b[0] + 0.4, up + 0.35, txt)
                    done = True
                    break
            if done:
                break
        if not done:
            b = (c - w / 2, c + w / 2, -0.6 - h, -0.6)
            boxes.append(b)
            put_text(b[0], -0.6 - h, txt)
    sh.line(pt(ext_lo, L), pt(ext_hi, L), lw=lw, layer=layer)


# ---------- рендер PDF ----------
def _set_common(c, it):
    c.setLineWidth(it.get('lw', 0.18))
    col = it.get('color', BLACK)
    c.setStrokeColorRGB(*col)
    d = it.get('dash')
    c.setDash(d if d else [])


_IMG = {}


def _img(path):
    from reportlab.lib.utils import ImageReader
    if path not in _IMG:
        _IMG[path] = ImageReader(path)
    return _IMG[path]


def render_pdf(sheets, path, title='', author=''):
    c = canvas.Canvas(path, pagesize=(420 * MM, 297 * MM))
    c.setTitle(title)
    c.setAuthor(author)
    for sh in sheets:
        c.saveState()
        c.scale(MM, MM)
        c.setLineJoin(0)
        c.setLineCap(0)
        for it in sh.items:
            t = it['t']
            if t == 'line':
                _set_common(c, it)
                c.line(it['a'][0], it['a'][1], it['b'][0], it['b'][1])
            elif t == 'poly':
                _set_common(c, it)
                pts = it['pts']
                p = c.beginPath()
                p.moveTo(*pts[0])
                for q in pts[1:]:
                    p.lineTo(*q)
                if it['closed']:
                    p.close()
                fill = it.get('fill')
                if fill:
                    c.setFillColorRGB(*fill)
                    if it.get('alpha') is not None:
                        c.setFillAlpha(it['alpha'])
                c.drawPath(p, stroke=1 if it.get('stroke', True) else 0, fill=1 if fill else 0)
                if fill and it.get('alpha') is not None:
                    c.setFillAlpha(1)
            elif t == 'arc':
                _set_common(c, it)
                a0, a1 = it['a0'], it['a1']
                ext = (a1 - a0) % 360
                if ext == 0:
                    ext = 360
                cx, cy = it['c']
                r = it['r']
                p = c.beginPath()
                p.arc(cx - r, cy - r, cx + r, cy + r, startAng=a0, extent=ext)
                c.drawPath(p, stroke=1, fill=0)
            elif t == 'circle':
                _set_common(c, it)
                fill = it.get('fill')
                if fill:
                    c.setFillColorRGB(*fill)
                c.circle(it['c'][0], it['c'][1], it['r'], stroke=1 if it.get('stroke', True) else 0,
                         fill=1 if fill else 0)
            elif t == 'image':
                c.saveState()
                if it.get('clip'):
                    pts = it['clip']
                    p = c.beginPath()
                    p.moveTo(*pts[0])
                    for q in pts[1:]:
                        p.lineTo(*q)
                    p.close()
                    c.clipPath(p, stroke=0, fill=0)
                c.drawImage(_img(it['path']), it['x'], it['y'], it['w'], it['h'], mask='auto' if it.get('alpha') else None)
                c.restoreState()
            elif t == 'text':
                s = it['s']
                h = it['h']
                font = it['font']
                size = fs(h)
                w = pdfmetrics.stringWidth(s, font, size)
                dx = {'l': 0, 'c': -w / 2, 'r': -w}[it['ha']]
                dy = {'b': 0, 'm': -h / 2, 't': -h}[it['va']]
                c.saveState()
                c.translate(*it['p'])
                if it['rot']:
                    c.rotate(it['rot'])
                if it.get('bg'):
                    c.setFillColorRGB(1, 1, 1)
                    c.rect(dx - 0.6, dy - 0.8, w + 1.2, h + 1.6, stroke=0, fill=1)
                c.setFillColorRGB(*it['color'])
                c.setFont(font, size)
                c.drawString(dx, dy, s)
                c.restoreState()
        c.restoreState()
        c.showPage()
    c.save()


# ---------- DXF R12 ----------
LAYERS = {
    'A-WALL': 7, 'A-WALL-FILL': 8, 'A-DOOR': 4, 'A-GLAZ': 5, 'A-FURN': 8, 'A-EQPM': 6, 'A-DIMS': 3,
    'A-TEXT': 7, 'A-ANNO': 2, 'A-FRAME': 7, 'A-HATCH': 8, 'A-ZONE': 9, '0': 7,
    'A-DEMO': 1, 'A-NEW': 30, 'A-FLOOR': 42, 'A-TILE': 252, 'A-CEIL': 140, 'A-HEAT': 10,
    'E-LIGHT': 40, 'E-POWER': 1, 'E-SWITCH': 5, 'E-LINK': 9, 'P-WATER': 150, 'P-HOT': 10, 'P-SEWER': 32,
    'M-VENT': 120, 'A-ELEV': 7, 'A-DET': 7,
}
DXF_FILL_LAYERS = {'A-WALL-FILL'}
_REPL = {'²': '2', 'Ø': '%%c', '≈': '~', '≥': '>=', '≤': '<=', '…': '...', '×': 'x', '−': '-', '’': "'",
         '⌀': '%%c', '→': '->'}


def _dxf_txt(s):
    for a, b in _REPL.items():
        s = s.replace(a, b)
    return s


def write_dxf(sheet, path, K=50.0):
    out = []

    def g(code, val):
        if isinstance(val, float):
            val = f'{val:.4f}'
        out.append(f'{code}')
        out.append(f'{val}')

    # HEADER
    g(0, 'SECTION'); g(2, 'HEADER')
    g(9, '$ACADVER'); g(1, 'AC1009')
    g(9, '$DWGCODEPAGE'); g(3, 'ANSI_1251')
    g(9, '$INSBASE'); g(10, 0.0); g(20, 0.0); g(30, 0.0)
    g(9, '$EXTMIN'); g(10, 0.0); g(20, 0.0); g(30, 0.0)
    g(9, '$EXTMAX'); g(10, 420.0 * K); g(20, 297.0 * K); g(30, 0.0)
    g(9, '$LIMMIN'); g(10, 0.0); g(20, 0.0)
    g(9, '$LIMMAX'); g(10, 420.0 * K); g(20, 297.0 * K)
    g(9, '$LTSCALE'); g(40, 1.0)
    g(9, '$TEXTSTYLE'); g(7, 'GOST')
    g(0, 'ENDSEC')
    # TABLES
    g(0, 'SECTION'); g(2, 'TABLES')
    g(0, 'TABLE'); g(2, 'LTYPE'); g(70, 2)
    g(0, 'LTYPE'); g(2, 'CONTINUOUS'); g(70, 0); g(3, 'Solid line'); g(72, 65); g(73, 0); g(40, 0.0)
    g(0, 'LTYPE'); g(2, 'DASHED'); g(70, 0); g(3, '__ __ __'); g(72, 65); g(73, 2); g(40, 4.5 * K)
    g(49, 3.0 * K); g(49, -1.5 * K)
    g(0, 'ENDTAB')
    g(0, 'TABLE'); g(2, 'LAYER'); g(70, len(LAYERS))
    for name, col in LAYERS.items():
        g(0, 'LAYER'); g(2, name); g(70, 0); g(62, col); g(6, 'CONTINUOUS')
    g(0, 'ENDTAB')
    g(0, 'TABLE'); g(2, 'STYLE'); g(70, 2)
    g(0, 'STYLE'); g(2, 'STANDARD'); g(70, 0); g(40, 0.0); g(41, 1.0); g(50, 0.0); g(71, 0); g(42, 2.5 * K)
    g(3, 'txt'); g(4, '')
    g(0, 'STYLE'); g(2, 'GOST'); g(70, 0); g(40, 0.0); g(41, 0.85); g(50, 15.0); g(71, 0); g(42, 2.5 * K)
    g(3, 'arial.ttf'); g(4, '')
    g(0, 'ENDTAB')
    g(0, 'ENDSEC')
    # ENTITIES
    g(0, 'SECTION'); g(2, 'ENTITIES')

    def P(p):
        return (p[0] * K, p[1] * K)

    for it in sheet.items:
        t = it['t']
        layer = it.get('layer', '0')
        if layer == 'A-ZONE':
            continue
        lt = 'DASHED' if it.get('dash') else None
        if t == 'line':
            a, b = P(it['a']), P(it['b'])
            g(0, 'LINE'); g(8, layer)
            if lt:
                g(6, lt)
            g(10, a[0]); g(20, a[1]); g(30, 0.0); g(11, b[0]); g(21, b[1]); g(31, 0.0)
        elif t == 'poly':
            pts = [P(q) for q in it['pts']]
            if it.get('fill') and layer in DXF_FILL_LAYERS and len(pts) == 4:
                q = pts
                g(0, 'SOLID'); g(8, layer)
                g(10, q[0][0]); g(20, q[0][1]); g(30, 0.0)
                g(11, q[1][0]); g(21, q[1][1]); g(31, 0.0)
                g(12, q[3][0]); g(22, q[3][1]); g(32, 0.0)
                g(13, q[2][0]); g(23, q[2][1]); g(33, 0.0)
            if it.get('stroke', True):
                g(0, 'POLYLINE'); g(8, layer)
                if lt:
                    g(6, lt)
                g(66, 1); g(10, 0.0); g(20, 0.0); g(30, 0.0); g(70, 1 if it['closed'] else 0)
                for x, y in pts:
                    g(0, 'VERTEX'); g(8, layer); g(10, x); g(20, y); g(30, 0.0)
                g(0, 'SEQEND'); g(8, layer)
        elif t == 'arc':
            cx, cy = P(it['c'])
            g(0, 'ARC'); g(8, layer)
            if lt:
                g(6, lt)
            g(10, cx); g(20, cy); g(30, 0.0); g(40, it['r'] * K)
            g(50, float(it['a0'] % 360)); g(51, float(it['a1'] % 360))
        elif t == 'circle':
            if not it.get('stroke', True):
                continue
            cx, cy = P(it['c'])
            g(0, 'CIRCLE'); g(8, layer)
            if lt:
                g(6, lt)
            g(10, cx); g(20, cy); g(30, 0.0); g(40, it['r'] * K)
        elif t == 'text':
            x, y = P(it['p'])
            ha = {'l': 0, 'c': 1, 'r': 2}[it['ha']]
            va = {'b': 0, 'm': 2, 't': 3}[it['va']]
            g(0, 'TEXT'); g(8, layer); g(10, x); g(20, y); g(30, 0.0); g(40, it['h'] * K)
            g(1, _dxf_txt(it['s'])); g(50, float(it['rot'])); g(41, 0.85); g(7, 'GOST')
            if ha or va:
                g(72, ha); g(11, x); g(21, y); g(31, 0.0); g(73, va)
    g(0, 'ENDSEC')
    g(0, 'EOF')
    with open(path, 'w', encoding='cp1251', errors='replace', newline='\r\n') as f:
        f.write('\n'.join(out) + '\n')
