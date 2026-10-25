# -*- coding: utf-8 -*-
"""Условные знаки (в мм листа): розетки, выключатели, светильники, сантехвыводы."""
import math
from core import BLACK, DARK, MID, WHITE, tw

BLUE = (0.0, 0.35, 0.85)
RED = (0.85, 0.12, 0.12)
BROWN = (0.45, 0.25, 0.10)
ORANGE = (0.95, 0.55, 0.0)
GREEN = (0.10, 0.55, 0.25)
VIOLET = (0.45, 0.20, 0.65)


def sheet_normal(n):
    """Нормаль модели -> нормаль листа (вид повёрнут на 90° по часовой)."""
    return (n[1], -n[0])


def _T(N):
    return (-N[1], N[0])


def _add(p, v, k=1.0):
    return (p[0] + v[0] * k, p[1] + v[1] * k)


def _ang(v):
    return math.degrees(math.atan2(v[1], v[0]))


def halfdisc(sh, c, N, r, layer, fill=None, lw=0.25, color=BLACK):
    T = _T(N)
    a0 = _ang(T)
    pts = [(c[0] + r * math.cos(math.radians(a0 - i * 180 / 16)), c[1] + r * math.sin(math.radians(a0 - i * 180 / 16)))
           for i in range(17)]
    # дуга от T через N к -T: угол убывает, если N = rot(T,-90)
    # проверим направление: N должна быть внутри дуги
    mid = pts[8]
    if (mid[0] - c[0]) * N[0] + (mid[1] - c[1]) * N[1] < 0:
        pts = [(c[0] + r * math.cos(math.radians(a0 + i * 180 / 16)), c[1] + r * math.sin(math.radians(a0 + i * 180 / 16)))
               for i in range(17)]
    sh.poly(pts, closed=True, lw=lw, layer=layer, fill=fill, color=color)
    return _add(c, N, r)


def outlet(sh, P, N, kind, layer='E-POWER'):
    """P — точка на грани стены (лист), N — внутренняя нормаль (лист)."""
    T = _T(N)
    if kind in ('r1', 'r1w'):
        c = _add(P, N, 0.25)
        ap = halfdisc(sh, c, N, 1.35, layer, fill=BLACK if kind == 'r1w' else WHITE)
        sh.line(ap, _add(ap, N, 0.9), lw=0.25, layer=layer)
        return _add(P, N, 2.6)
    if kind in ('r2', 'r2u', 'r2w', 'tvblock', 'medblock', 'deskblock'):
        n = 3 if kind == 'deskblock' else 2
        offs = [-1.25, 1.25] if n == 2 else [-2.4, 0, 2.4]
        for o in offs:
            c = _add(_add(P, N, 0.25), T, o)
            ap = halfdisc(sh, c, N, 1.15, layer, fill=BLACK if kind == 'r2w' else WHITE)
            sh.line(ap, _add(ap, N, 0.7), lw=0.22, layer=layer)
        tip = _add(P, N, 2.3)
        if kind == 'r2u':
            sh.text(_add(tip, N, 0.9), 'U', h=1.2, ha='c', va='m', layer=layer)
        if kind in ('tvblock', 'medblock', 'deskblock'):
            q = _add(_add(P, N, 0.2), T, (offs[-1] + 2.4))
            box = [_add(_add(q, T, -0.9), N, 0), _add(_add(q, T, 0.9), N, 0), _add(_add(q, T, 0.9), N, 1.8),
                   _add(_add(q, T, -0.9), N, 1.8)]
            sh.poly(box, lw=0.22, layer=layer, fill=WHITE)
            sh.text(_add(q, N, 0.9), 'RJ' if kind != 'tvblock' else 'TV', h=0.9, ha='c', va='m', layer=layer)
        return _add(P, N, 3.2)
    if kind == 'pow':
        c = _add(P, N, 1.4)
        sq = [_add(_add(c, T, -1.2), N, -1.2), _add(_add(c, T, 1.2), N, -1.2), _add(_add(c, T, 1.2), N, 1.2),
              _add(_add(c, T, -1.2), N, 1.2)]
        sh.poly(sq, lw=0.3, layer=layer, fill=WHITE)
        sh.line(sq[0], sq[2], lw=0.25, layer=layer)
        sh.line(sq[1], sq[3], lw=0.25, layer=layer)
        return _add(P, N, 3.0)
    if kind == 'out':
        a = _add(P, N, 0.2)
        tri = [_add(a, T, -1.1), _add(a, T, 1.1), _add(a, N, 1.9)]
        sh.poly(tri, lw=0.2, layer=layer, fill=BLACK)
        return _add(P, N, 2.6)
    if kind in ('shk', 'ssh'):
        a = _add(P, N, 0.2)
        w = 3.0 if kind == 'shk' else 2.4
        box = [_add(a, T, -w), _add(a, T, w), _add(_add(a, T, w), N, 1.8), _add(_add(a, T, -w), N, 1.8)]
        sh.poly(box, lw=0.3, layer=layer, fill=BLACK if kind == 'shk' else WHITE)
        if kind == 'ssh':
            sh.line(box[0], box[2], lw=0.2, layer=layer)
        return _add(P, N, 2.8)
    if kind == 'int':
        c = _add(P, N, 1.3)
        sq = [_add(_add(c, T, -1.1), N, -1.1), _add(_add(c, T, 1.1), N, -1.1), _add(_add(c, T, 1.1), N, 1.1),
              _add(_add(c, T, -1.1), N, 1.1)]
        sh.poly(sq, lw=0.25, layer=layer, fill=WHITE)
        sh.text(c, 'Д', h=1.2, ha='c', va='m', layer=layer)
        return _add(P, N, 2.8)
    return P


def switch(sh, P, N, kind, layer='E-SWITCH'):
    T = _T(N)
    c = _add(P, N, 1.5)
    if kind == 'tr':
        sq = [_add(_add(c, T, -1.15), N, -1.15), _add(_add(c, T, 1.15), N, -1.15), _add(_add(c, T, 1.15), N, 1.15),
              _add(_add(c, T, -1.15), N, 1.15)]
        sh.poly(sq, lw=0.25, layer=layer, fill=WHITE)
        sh.text(c, 't°', h=1.1, ha='c', va='m', layer=layer)
        return _add(P, N, 3.0)
    sh.circle(c, 1.0, lw=0.25, layer=layer, fill=BLACK)
    angs = {'v1': [45], 'v2': [30, 65], 'v1p': [45], 'v2p': [30, 65]}[kind]
    through = kind.endswith('p')
    for a in angs:
        d = (N[0] * math.cos(math.radians(a)) + T[0] * math.sin(math.radians(a)),
             N[1] * math.cos(math.radians(a)) + T[1] * math.sin(math.radians(a)))
        p1 = _add(c, d, 1.0)
        p2 = _add(c, d, 3.0)
        sh.line(p1, p2, lw=0.25, layer=layer)
        tick = (-d[1], d[0])
        sh.line(p2, _add(p2, tick, 0.8), lw=0.25, layer=layer)
        if through:
            q1 = _add(c, d, -1.0)
            q2 = _add(c, d, -3.0)
            sh.line(q1, q2, lw=0.25, layer=layer)
            sh.line(q2, _add(q2, tick, -0.8), lw=0.25, layer=layer)
    return _add(P, N, 4.0)


def light(sh, P, kind, layer='E-LIGHT', N=None, a=None, b=None, scale=50.0):
    if kind in ('spot', 'spot44', 'spot65'):
        r = 1.25
        sh.circle(P, r, lw=0.25, layer=layer, fill=WHITE)
        d = r * 0.72
        sh.line((P[0] - d, P[1] - d), (P[0] + d, P[1] + d), lw=0.2, layer=layer)
        sh.line((P[0] - d, P[1] + d), (P[0] + d, P[1] - d), lw=0.2, layer=layer)
        if kind in ('spot44', 'spot65'):
            sh.circle(P, 1.8, lw=0.2, layer=layer)
        if kind == 'spot65':
            sh.circle(P, 0.45, lw=0.1, layer=layer, fill=BLACK)
    elif kind == 'ceil':                    # накладной потолочный светильник (плафон)
        sh.circle(P, 2.2, lw=0.3, layer=layer, fill=WHITE)
        sh.circle(P, 1.1, lw=0.2, layer=layer)
        for ang in (45, 135, 225, 315):
            q0 = (P[0] + 1.1 * math.cos(math.radians(ang)), P[1] + 1.1 * math.sin(math.radians(ang)))
            q1 = (P[0] + 2.2 * math.cos(math.radians(ang)), P[1] + 2.2 * math.sin(math.radians(ang)))
            sh.line(q0, q1, lw=0.15, layer=layer)
    elif kind == 'pend':
        sh.circle(P, 300 / scale, lw=0.2, layer=layer, dash=(1.0, 0.7))
        sh.circle(P, 2.0, lw=0.3, layer=layer, fill=WHITE)
        sh.circle(P, 0.9, lw=0.1, layer=layer, fill=BLACK)
    elif kind == 'track':
        sh.line(a, b, lw=0.9, layer=layer)
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        n = 5
        for i in range(n):
            t = (i + 0.5) / n
            q = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            sh.circle(q, 0.8, lw=0.2, layer=layer, fill=WHITE)
    elif kind == 'led':
        sh.line(a, b, lw=0.6, layer=layer, dash=(1.6, 0.8), color=ORANGE)
    elif kind == 'linear':
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        ux, uy = dx / L, dy / L
        nx, ny = -uy, ux
        w = 0.8
        pts = [(a[0] + nx * w, a[1] + ny * w), (b[0] + nx * w, b[1] + ny * w), (b[0] - nx * w, b[1] - ny * w),
               (a[0] - nx * w, a[1] - ny * w)]
        sh.poly(pts, lw=0.3, layer=layer, fill=DARK)
    elif kind in ('sconce', 'wall44'):
        c = _add(P, N, 0.2)
        halfdisc(sh, c, N, 1.4, layer, fill=BLACK)
        T = _T(N)
        for ang in (-50, 0, 50):
            d = (N[0] * math.cos(math.radians(ang)) + T[0] * math.sin(math.radians(ang)),
                 N[1] * math.cos(math.radians(ang)) + T[1] * math.sin(math.radians(ang)))
            sh.line(_add(c, d, 1.9), _add(c, d, 2.8), lw=0.2, layer=layer)
        if kind == 'wall44':
            sh.text(_add(c, N, 4.0), 'IP44', h=1.1, ha='c', va='m', layer=layer)
    elif kind == 'fan':
        sh.circle(P, 2.0, lw=0.3, layer=layer, fill=WHITE)
        for ang in (90, 210, 330):
            q = (P[0] + 1.3 * math.cos(math.radians(ang)), P[1] + 1.3 * math.sin(math.radians(ang)))
            sh.circle(q, 0.55, lw=0.18, layer=layer)
        sh.circle(P, 0.3, lw=0.1, layer=layer, fill=BLACK)
    elif kind == 'mirrorled':
        c = _add(P, N, 0.2)
        T = _T(N)
        tri = [_add(c, T, -1.1), _add(c, T, 1.1), _add(c, N, 1.9)]
        sh.poly(tri, lw=0.2, layer=layer, fill=BLACK)


def plumb(sh, P, kind, N=None, layer=None):
    if N is None:
        N = (0, 0)
    c = _add(P, N, 1.6) if N != (0, 0) else P
    if kind == 'hvs':
        sh.circle(c, 1.05, lw=0.25, layer='P-WATER', fill=BLUE, color=BLUE)
    elif kind == 'gvs':
        sh.circle(c, 1.05, lw=0.25, layer='P-HOT', fill=RED, color=RED)
    elif kind == 'k50':
        sh.circle(c, 1.35, lw=0.3, layer='P-SEWER', fill=WHITE, color=BROWN)
        sh.circle(c, 0.6, lw=0.1, layer='P-SEWER', fill=BROWN, color=BROWN)
    elif kind == 'k110':
        sh.circle(c, 1.9, lw=0.35, layer='P-SEWER', fill=WHITE, color=BROWN)
        sh.circle(c, 1.0, lw=0.1, layer='P-SEWER', fill=BROWN, color=BROWN)
    elif kind == 'tap':
        T = _T(N) if N != (0, 0) else (1, 0)
        tri = [_add(c, T, -1.1), _add(c, T, 1.1), _add(c, N, 1.5)]
        sh.poly(tri, lw=0.2, layer='P-WATER', fill=BLUE, color=BLUE)
    elif kind == 'sif':
        sq = [(c[0] - 1.0, c[1] - 1.0), (c[0] + 1.0, c[1] - 1.0), (c[0] + 1.0, c[1] + 1.0), (c[0] - 1.0, c[1] + 1.0)]
        sh.poly(sq, lw=0.25, layer='P-SEWER', fill=BROWN, color=BROWN)
    return c


# ---- образцы для легенд: fn(sh, cx, cy) ----
def lg_outlet(kind):
    return lambda sh, x, y: outlet(sh, (x, y - 1.3), (0, 1), kind)


def lg_switch(kind):
    return lambda sh, x, y: switch(sh, (x - 2.0, y - 1.5), (0, 1), kind)


def lg_light(kind):
    def f(sh, x, y):
        if kind in ('track', 'led', 'linear'):
            light(sh, None, kind, a=(x - 3.5, y), b=(x + 3.5, y))
        elif kind in ('sconce', 'wall44', 'mirrorled'):
            light(sh, (x, y - 1.2), kind, N=(0, 1))
        else:
            light(sh, (x, y), kind)
    return f


def lg_plumb(kind):
    return lambda sh, x, y: plumb(sh, (x, y), kind, N=(0, 0)) if kind not in ('tap',) else plumb(sh, (x, y - 1.6), kind, N=(0, 1))


# ---- цветные знаки (ред. Р3): светильники и розетки — красные, выключатели — синие, терморегуляторы — оранжевые ----
EL_RED = (0.86, 0.10, 0.10)
SW_BLUE = (0.05, 0.30, 0.80)
TR_ORANGE = (0.90, 0.45, 0.0)
LOW_GREEN = (0.0, 0.55, 0.35)


class Tint:
    """Обёртка листа: чёрные линии/заливки знаков перекрашиваются в цвет col."""

    def __init__(s, sh, col):
        s.sh, s.col = sh, col

    def _k(s, kw):
        c = kw.get('color', BLACK)
        if c == BLACK or c == DARK:
            kw['color'] = s.col
        if kw.get('fill') in (BLACK, DARK):
            kw['fill'] = s.col
        return kw

    def line(s, a, b, **kw):
        s.sh.line(a, b, **s._k(kw))

    def poly(s, pts, **kw):
        s.sh.poly(pts, **s._k(kw))

    def rect(s, x0, y0, x1, y1, **kw):
        s.sh.rect(x0, y0, x1, y1, **s._k(kw))

    def circle(s, c, r, **kw):
        s.sh.circle(c, r, **s._k(kw))

    def arc(s, c, r, a0, a1, **kw):
        s.sh.arc(c, r, a0, a1, **s._k(kw))

    def text(s, p, txt, **kw):
        s.sh.text(p, txt, **s._k(kw))

    def __getattr__(s, name):
        return getattr(s.sh, name)


def outlet_c(sh, P, N, kind, layer='E-POWER'):
    col = LOW_GREEN if kind in ('ssh', 'int') else EL_RED
    return outlet(Tint(sh, col), P, N, kind, layer)


def switch_c(sh, P, N, kind, layer='E-SWITCH'):
    return switch(Tint(sh, TR_ORANGE if kind == 'tr' else SW_BLUE), P, N, kind, layer)


def light_c(sh, P, kind, layer='E-LIGHT', N=None, a=None, b=None, scale=50.0, col=None):
    return light(Tint(sh, col or EL_RED), P, kind, layer, N=N, a=a, b=b, scale=scale)


def lg_outlet_c(kind):
    return lambda sh, x, y: outlet_c(sh, (x, y - 1.3), (0, 1), kind)


def lg_switch_c(kind):
    return lambda sh, x, y: switch_c(sh, (x - 2.0, y - 1.5), (0, 1), kind)


def lg_light_c(kind):
    def f(sh, x, y):
        if kind in ('track', 'led', 'linear'):
            light_c(sh, None, kind, a=(x - 3.5, y), b=(x + 3.5, y))
        elif kind in ('sconce', 'wall44', 'mirrorled'):
            light_c(sh, (x, y - 1.2), kind, N=(0, 1))
        else:
            light_c(sh, (x, y), kind)
    return f
