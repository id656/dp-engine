# -*- coding: utf-8 -*-
"""Развёртки стен по помещениям (стены А, Б, В… по часовой от входа) — из единой модели."""
import math
from core import Sheet, mdim, tw, rrect_pts, BLACK, DARK, MID, LIGHT, WHITE, FILL_LT, WALLFILL
import model as D
import symbols as SY
from kit import frame, notes, table, legend_box, bubble, num, lvl, section_title, subtract_intervals, poly_scan

TAUPE = (0.80, 0.74, 0.68)
PANEL = (0.86, 0.82, 0.77)
MARBLE = (0.97, 0.96, 0.94)
TILE_L = (0.95, 0.93, 0.89)
WALNUT = (0.55, 0.40, 0.28)

def derive_openings():
    """Проёмы из модели, если в design.py нет OPENINGS: двери — разрыв стен у петли, окна — из WINDOWS."""
    out = []
    for key in D.DOOR_LIST:
        d = D.DOORS[key]
        hx, hy = d['h']; cx, cy = d['c']
        axis = 'x' if cx == 0 else 'y'           # полотно в закрытом положении вдоль стены
        best = None
        for r in D.WALLS:
            if axis == 'y' and r[1] - 1 <= hy <= r[3] + 1 and (r[3] - r[1]) <= 450:
                band = (r[1], r[3])
            elif axis == 'x' and r[0] - 1 <= hx <= r[2] + 1 and (r[2] - r[0]) <= 450:
                band = (r[0], r[2])
            else:
                continue
            best = band if best is None else best
        if best is None:
            continue
        lo, hi = -1e9, 1e9
        along = hx if axis == 'y' else hy
        for r in D.WALLS:
            b = (r[1], r[3]) if axis == 'y' else (r[0], r[2])
            if b != best:
                continue
            a0, a1 = (r[0], r[2]) if axis == 'y' else (r[1], r[3])
            if a1 <= along + 1:
                lo = max(lo, a1)
            if a0 >= along - 1:
                hi = min(hi, a0)
        L = d['L']
        tip = along + (cx if axis == 'y' else cy) * L
        if lo < -1e8:
            lo = min(along, tip) - 40
        if hi > 1e8:
            hi = max(along, tip) + 40
        out.append(dict(kind='bdoor' if (d.get('kind') == 'balcony' or key.startswith('balc')) else 'door', key=key, axis=axis, c0=best[0], c1=best[1], a=lo, b=hi,
                        z0=0, z1=getattr(D, 'DOOR_H', 2100), mark=D.DOOR_MARK.get(key, '')))
    for key, w in getattr(D, 'WINDOWS', {}).items():
        ax, c = w['wall']
        band = None
        for r in D.WALLS:
            if ax == 'y' and (abs(r[1] - c) < 2 or abs(r[3] - c) < 2) and r[0] <= w['b'] and r[2] >= w['a']:
                band = (r[1], r[3])
            if ax == 'x' and (abs(r[0] - c) < 2 or abs(r[2] - c) < 2) and r[1] <= w['b'] and r[3] >= w['a']:
                band = (r[0], r[2])
        band = band or (c, c + 300)
        out.append(dict(kind='window', key=key, axis=ax, c0=band[0], c1=band[1], a=w['a'], b=w['b'], z0=w['z0'], z1=w['z1'],
                        c_in=c, c_out=band[1] if abs(band[0] - c) < 2 else band[0]))
    return out


OPENINGS = getattr(D, 'OPENINGS', None) or derive_openings()


class EV:
    def __init__(self, X0, Y0, k):
        self.X0, self.Y0, self.k = X0, Y0, k

    def P(self, s, z):
        return (self.X0 + s / self.k, self.Y0 + z / self.k)


class FV:
    """Вид для mdim: P(a, b) = (X0 + b/k, Y0 + a/k)."""
    def __init__(self, ev):
        self.ev = ev
        self.k = ev.k

    def P(self, a, b):
        return (self.ev.X0 + b / self.ev.k, self.ev.Y0 + a / self.ev.k)


def wall_geom(room, label):
    for lab, pL, pR in D.RWALLS[room]:
        if lab == label:
            dx, dy = pR[0] - pL[0], pR[1] - pL[1]
            L = math.hypot(dx, dy)
            d = (dx / L, dy / L)
            n = (d[1], -d[0])
            return dict(pL=pL, pR=pR, d=d, n=n, L=L)
    raise KeyError(label)


def proj(W, P):
    rx, ry = P[0] - W['pL'][0], P[1] - W['pL'][1]
    return rx * W['d'][0] + ry * W['d'][1], rx * W['n'][0] + ry * W['n'][1]


def item_rect(it):
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
    return None


def mod_pt(it, a):
    """Точка модели для координаты модуля кухни a (вдоль стены гарнитура: W/E — по y, N/S — по x)."""
    return (0, a) if it.get('side', 'W') in ('W', 'E') else (a, 0)


def proj_rect(W, r):
    x0, y0, x1, y1 = r
    pts = [proj(W, p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    ss = [p[0] for p in pts]; ds = [p[1] for p in pts]
    return min(ss), max(ss), min(ds), max(ds)


def item_proj(W, it, r):
    """Проекция предмета на стену: s0, s1 (вдоль), d0, d1 (от стены). Предмет-многоугольник — по вершинам контура."""
    if 'pts' in it and 'rect' not in it:
        pts = [proj(W, p) for p in it['pts']]
        ss = [p[0] for p in pts]; ds = [p[1] for p in pts]
        return min(ss), max(ss), min(ds), max(ds)
    return proj_rect(W, r)


# ---------------- отрисовка элементов на развёртке ----------------
LW = dict(lw=0.25, layer='A-ELEV', color=BLACK)
LT = dict(lw=0.13, layer='A-ELEV', color=DARK)
LF = dict(lw=0.1, layer='A-ELEV', color=MID)


def R(sh, ev, s0, z0, s1, z1, fill=None, dash=None, style=LW):
    a, b = ev.P(s0, z0), ev.P(s1, z1)
    sh.rect(a[0], a[1], b[0], b[1], fill=fill, dash=dash, **style)


def Ln(sh, ev, s0, z0, s1, z1, style=LT, dash=None):
    sh.line(ev.P(s0, z0), ev.P(s1, z1), dash=dash, **style)


TEXTURES = True


def TX(sh, ev, s0, z0, s1, z1, kind, clip=None, **kw):
    """Фотореалистичная текстура материала в прямоугольнике развёртки (реальные мм)."""
    if not TEXTURES or s1 - s0 < 4 or z1 - z0 < 4:
        return
    import textures as T
    p = T.make(kind, s1 - s0, z1 - z0, ev.k, **kw)
    a, b = ev.P(s0, z0), ev.P(s1, z1)
    if clip is not None:
        clip = [ev.P(*q) for q in clip]
    sh.image(p, min(a[0], b[0]), min(a[1], b[1]), abs(b[0] - a[0]), abs(b[1] - a[1]), clip=clip, alpha=(kind == 'glass'))


def tile_params(room, label, s0, s1, code):
    m = D.mat(code)
    size = sorted((m.get('tw', 600), m.get('th', 1200)))
    for (r, lab, a0, a1, z0, z1, tw_, th_, so, zo) in D.TILE_LAYOUT:
        if r == room and lab == label and a0 < s1 and a1 > s0 and sorted((tw_, th_)) == size:
            return dict(tw=tw_, th=th_, so=so, zo=zo)
    return dict(tw=m.get('tw', 600), th=m.get('th', 1200), so=s0, zo=D.ROOM[room]['level'] or 0)


def draw_item_elev(sh, ev, it, s0, s1, W, room):
    k = it['kind']
    z0, z1 = it.get('z', (0, 0))
    if k == 'wardrobe':
        R(sh, ev, s0, z0, s1, z1, fill=WHITE)
        if it.get('mat', 'front') == 'walnut':
            TX(sh, ev, s0, 100, s1, z1, 'walnut', along='v')
        else:
            TX(sh, ev, s0, 100, s1, z1, it.get('mat', 'front'))
        n = it.get('doors') or max(1, round((s1 - s0) / 600))
        w = (s1 - s0) / n
        for i in range(1, n):
            Ln(sh, ev, s0 + i * w, z0 + 100, s0 + i * w, z1)
        Ln(sh, ev, s0, 100, s1, 100)
        R(sh, ev, s0, z0, s1, z1)
    elif k == 'bench':
        R(sh, ev, s0, 0, s1, 450, fill=WHITE)
        TX(sh, ev, s0, 0, s1, 300, it.get('mat', 'walnut'), along='h')
        TX(sh, ev, s0 + 30, 300, s1 - 30, 450, 'fabric', col=it.get('fabric_col', (150, 156, 120)))
        R(sh, ev, s0, 0, s1, 450)
        R(sh, ev, s0 + 30, 300, s1 - 30, 450, style=LT)
    elif k == 'wallshelf':
        R(sh, ev, s0, z0, s1, z1 if z1 - z0 > 25 else z0 + 40, fill=WHITE)
        if it.get('shelves'):
            R(sh, ev, s0, z0 + 250, s1, z0 + 280, fill=DARK)
            R(sh, ev, s0, z0, s1, z0 + 30, fill=DARK)
    elif k == 'console':
        R(sh, ev, s0, z0, s1, z1, fill=(0.80, 0.70, 0.60))
        TX(sh, ev, s0, z0, s1, z1, it.get('mat', 'walnut'), along='h')
        R(sh, ev, s0, z0, s1, z1)
        Ln(sh, ev, s0 + 20, (z0 + z1) / 2, s1 - 20, (z0 + z1) / 2)
    elif k == 'mirror':
        R(sh, ev, s0, z0, s1, z1, fill=(0.90, 0.93, 0.95))
        TX(sh, ev, s0, z0, s1, z1, 'mirror')
        R(sh, ev, s0, z0, s1, z1)
        Ln(sh, ev, s0 + (s1 - s0) * 0.15, z0 + (z1 - z0) * 0.55, s0 + (s1 - s0) * 0.45, z0 + (z1 - z0) * 0.85, style=LF)
        Ln(sh, ev, s0 + (s1 - s0) * 0.25, z0 + (z1 - z0) * 0.45, s0 + (s1 - s0) * 0.6, z0 + (z1 - z0) * 0.8, style=LF)
    elif k == 'mirror_round':
        c = ev.P((s0 + s1) / 2, (z0 + z1) / 2)
        sh.circle(c, (z1 - z0) / 2 / ev.k, fill=(0.90, 0.93, 0.95), **LW)
        rr = (z1 - z0) / 2
        cs, cz = (s0 + s1) / 2, (z0 + z1) / 2
        TX(sh, ev, cs - rr, z0, cs + rr, z1, 'mirror',
           clip=[(cs + rr * math.cos(t / 24 * 2 * math.pi), cz + rr * math.sin(t / 24 * 2 * math.pi)) for t in range(24)])
        sh.circle(c, (z1 - z0) / 2 / ev.k, **LW)
    elif k == 'mirror_oval':
        w = s1 - s0
        pts = rrect_pts(s0, z0, s1, z1, w / 2, n=10)
        sh.poly([ev.P(*p) for p in pts], fill=(0.90, 0.93, 0.95), **LW)
        TX(sh, ev, s0, z0, s1, z1, 'mirror', clip=pts)
        sh.poly([ev.P(*p) for p in pts], **LW)
        pts2 = rrect_pts(s0 - 15, z0 - 15, s1 + 15, z1 + 15, w / 2 + 15, n=10)
        sh.poly([ev.P(*p) for p in pts2], lw=0.4, layer='A-ELEV', color=(1.0, 0.75, 0.3), dash=(0.8, 0.6))
    elif k == 'column':
        R(sh, ev, s0, 0, s1, z1, fill=WHITE)
        TX(sh, ev, s0, 100, s1, z1, it.get('front', 'front'))
        Ln(sh, ev, s0, 100, s1, 100)
        tops = [100]
        for a, b, lab in it.get('inner', []):
            if lab == 'холодильник':
                R(sh, ev, s0 + 15, a, s1 - 15, b, style=LT)
                Ln(sh, ev, s1 - 80, a + 900, s1 - 80, a + 1300, style=dict(lw=0.6, layer='A-ELEV', color=BLACK))
            else:
                R(sh, ev, s0 + 15, a, s1 - 15, b, fill=(0.20, 0.20, 0.20) if lab == 'ДШ' else (0.25, 0.25, 0.25), style=LT)
                R(sh, ev, s0 + 60, a + 60, s1 - 60, b - 80, fill=(0.35, 0.35, 0.38), style=LF)
            sh.text(ev.P((s0 + s1) / 2, (a + b) / 2), {'холодильник': 'ХЛ'}.get(lab, lab), h=1.5, ha='c', va='m', layer='A-TEXT',
                    color=WHITE if lab != 'холодильник' else DARK)
            tops.append(b)
        mx = max(tops)
        Ln(sh, ev, s0, mx + 3, s1, mx + 3)
        Ln(sh, ev, s0, 2270, s1, 2270)
        if any(lab == 'ДШ' for a, b, lab in it.get('inner', [])):
            R(sh, ev, s0 + 15, 110, s1 - 15, 845, style=LT)
    elif k == 'filler':
        R(sh, ev, s0, 100, s1, 860, style=LT)
    elif k == 'kitchen_run':
        if s1 - s0 > 900:
            R(sh, ev, s0, 0, s1, 860, fill=WHITE)
            TX(sh, ev, s0, 100, s1, 860, it.get('front', 'front'))
            Ln(sh, ev, s0, 100, s1, 100)
            R(sh, ev, s0, 0, s1, 860)
            R(sh, ev, s0 - 10, 860, s1, 900, fill=it.get('top_fill', (0.78, 0.66, 0.50)))
            TX(sh, ev, s0 - 10, 860, s1, 900, it.get('top', 'oak'), along='h')
            R(sh, ev, s0 - 10, 860, s1, 900)
            for a, b, kind in it['modules']:
                pa, _ = proj(W, mod_pt(it, a)); pb, _ = proj(W, mod_pt(it, b))
                pa, pb = sorted((pa, pb))
                Ln(sh, ev, pa, 100, pa, 860)
                if kind in ('sink', 'tech'):
                    if kind == 'sink':
                        Ln(sh, ev, (pa + pb) / 2, 100, (pa + pb) / 2, 860, style=LF)
                    hw_ = min(240, (pb - pa) / 2 - 25)
                    R(sh, ev, (pa + pb) / 2 - hw_, 660, (pa + pb) / 2 + hw_, 860, dash=(1.0, 0.6), style=LF) if kind == 'sink' else None
                elif kind in ('hob', 'drawers'):
                    for zz in (330, 600):
                        Ln(sh, ev, pa, zz, pb, zz)
                    if kind == 'hob':
                        R(sh, ev, pa + 30, 900, pb - 30, 915, fill=BLACK, style=LT)
                elif kind == 'dw':
                    sh.text(ev.P((pa + pb) / 2, 480), 'ПММ', h=1.4, ha='c', va='m', layer='A-TEXT', color=DARK)
            # смеситель мойки
            for a, b, kind in it['modules']:
                if kind == 'sink':
                    pa, _ = proj(W, mod_pt(it, a)); pb, _ = proj(W, mod_pt(it, b))
                    c = (pa + pb) / 2
                    sh.poly([ev.P(c - 25, 900), ev.P(c - 25, 1230), ev.P(c + 120, 1230), ev.P(c + 120, 1160)], closed=False,
                            lw=0.5, layer='A-ELEV', color=BLACK)
        else:
            # торец (вид сбоку) на смежной стене
            R(sh, ev, s0, 0, s1, 860, fill=WHITE)
            TX(sh, ev, s0, 100, s1, 860, it.get('front', 'front'))
            R(sh, ev, s0, 0, s1, 860)
            R(sh, ev, s0, 860, s1, 900, fill=it.get('top_fill', (0.78, 0.66, 0.50)))
            TX(sh, ev, s0, 860, s1, 900, it.get('top', 'oak'), along='h')
            R(sh, ev, s0, 860, s1, 900)
            Ln(sh, ev, s0 + 50, 100, s1, 100)
    elif k == 'upper':
        if s1 - s0 > 900:
            spl = it.get('split', 2270)
            R(sh, ev, s0, z0, s1, z1, fill=WHITE)
            TX(sh, ev, s0, spl, s1, z1, it.get('front', 'front'))
            R(sh, ev, s0, z0, s1, spl, fill=(0.80, 0.68, 0.55), style=LW)
            TX(sh, ev, s0, z0, s1, spl, it.get('front_low', 'walnut'), along='v')
            R(sh, ev, s0, z0, s1, spl, style=LW)
            R(sh, ev, s0, z0, s1, z1)
            base = next((b for b in D.ITEMS if b['room'] == it['room'] and b['kind'] == 'kitchen_run'
                         and b.get('side', 'W') == it.get('side', 'W')), None)
            bnds = [m[1] for m in base['modules'][:-1]] if base else []
            for a in bnds:
                pa, _ = proj(W, mod_pt(it, a))
                Ln(sh, ev, pa, z0, pa, z1)
            hy = it.get('hood')
            if hy:
                pa, _ = proj(W, mod_pt(it, hy[0])); pb, _ = proj(W, mod_pt(it, hy[1]))
                sh.text(ev.P((pa + pb) / 2, z0 + 150), 'вытяжка', h=1.3, ha='c', va='m', layer='A-TEXT', bg=True)
            R(sh, ev, s0, z0 - 20, s1, z0, fill=(1.0, 0.75, 0.3), style=LF)
        else:
            R(sh, ev, s0, z0, s1, z1, fill=WHITE)
            if it.get('side_tex'):                      # боковая панель в отделке фасадов (вид сбоку)
                TX(sh, ev, s0, z0, s1, z1, it.get('front', 'front'))
                R(sh, ev, s0, z0, s1, z1)
            Ln(sh, ev, s0, it.get('split', 2270), s1, it.get('split', 2270))
    elif k == 'table':
        R(sh, ev, s0, 720, s1, 750, fill=(0.80, 0.68, 0.52))
        TX(sh, ev, s0, 720, s1, 750, it.get('mat', 'oak'), along='h')
        R(sh, ev, s0, 720, s1, 750)
        for x in (s0 + 40, s1 - 80):
            R(sh, ev, x, 0, x + 40, 720, fill=WHITE, style=LT)
    elif k == 'sofa':
        R(sh, ev, s0, 0, s1, 800, fill=WHITE)
        TX(sh, ev, s0, 80, s1, 800, 'fabric', **({'col': it['fabric_col']} if 'fabric_col' in it else {}))
        R(sh, ev, s0, 0, s1, 800)
        R(sh, ev, s0, 0, s0 + 200, 600, style=LT)
        R(sh, ev, s1 - 200, 0, s1, 600, style=LT)
        Ln(sh, ev, s0 + 200, 420, s1 - 200, 420)
        Ln(sh, ev, s0, 80, s1, 80, style=LF)
    elif k == 'coffee':
        R(sh, ev, s0, 0, s1, 400, fill=WHITE)
    elif k == 'tvconsole':
        R(sh, ev, s0, z0, s1, z1, fill=(0.80, 0.70, 0.60))
        TX(sh, ev, s0, z0, s1, z1, it.get('mat', 'walnut'), along='h')
        R(sh, ev, s0, z0, s1, z1)
        for i in (1, 2):
            x = s0 + (s1 - s0) * i / 3
            Ln(sh, ev, x, z0, x, z1)
    elif k == 'tv':
        R(sh, ev, s0, z0, s1, z1, fill=(0.12, 0.12, 0.12))
        TX(sh, ev, s0, z0, s1, z1, 'screen')
        R(sh, ev, s0, z0, s1, z1)
        sh.text(ev.P((s0 + s1) / 2, (z0 + z1) / 2), it.get('label', 'ТВ'), h=1.6, ha='c', va='m',
                layer='A-TEXT', color=WHITE)
    elif k == 'radiator':
        R(sh, ev, s0, z0, s1, z1, dash=(1.2, 0.8), style=LT)
        x = s0 + 50
        while x < s1:
            Ln(sh, ev, x, z0 + 30, x, z1 - 30, style=LF)
            x += 80
    elif k == 'bed':
        R(sh, ev, s0, 0, s1, z1, fill=(0.85, 0.82, 0.78))
        TX(sh, ev, s0, 0, s1, z1, 'fabric', col=it.get('fabric_col', (168, 158, 146)))
        R(sh, ev, s0, 0, s1, z1)
        for i in range(1, 4):
            x = s0 + (s1 - s0) * i / 4
            Ln(sh, ev, x, 300, x, z1 - 40, style=LF)
        R(sh, ev, s0 + 20, 0, s1 - 20, 280, fill=WHITE, style=LT)
        R(sh, ev, s0 + 20, 280, s1 - 20, 520, fill=WHITE, style=LT)
    elif k == 'bed_single':
        R(sh, ev, s0, 0, s1, 450, fill=WHITE)
        Ln(sh, ev, s0, 250, s1, 250)
        if (s1 - s0) < 1000:
            R(sh, ev, s0, 0, s1, 900, style=LT)
    elif k == 'nightstand':
        R(sh, ev, s0, z0, s1, z1, fill=(0.80, 0.70, 0.60))
        TX(sh, ev, s0, z0, s1, z1, it.get('mat', 'walnut'), along='h')
        R(sh, ev, s0, z0, s1, z1)
        Ln(sh, ev, s0 + 20, (z0 + z1) / 2, s1 - 20, (z0 + z1) / 2)
    elif k == 'desk':
        R(sh, ev, s0, 720, s1, 750, fill=(0.80, 0.70, 0.60))
        TX(sh, ev, s0, 720, s1, 750, it.get('mat', 'oak'), along='h')
        R(sh, ev, s0, 720, s1, 750)
        R(sh, ev, s0, 0, s0 + 30, 720, fill=WHITE, style=LT)
        R(sh, ev, s1 - 30, 0, s1, 720, fill=WHITE, style=LT)
        R(sh, ev, s0 + 30, 560, s1 - 30, 720, style=LT)
    elif k == 'shelving':
        R(sh, ev, s0, 0, s1, z1, fill=WHITE)
        TX(sh, ev, s0, 0, s1, z1, it.get('mat', 'walnut'), along='h')
        R(sh, ev, s0, 0, s1, z1)
        for zz in range(400, int(z1), 400):
            Ln(sh, ev, s0, zz, s1, zz)
    elif k == 'ac':
        R(sh, ev, s0, z0, s1, z1, fill=WHITE)
        Ln(sh, ev, s0 + 40, z0 + 60, s1 - 40, z0 + 60)
        sh.text(ev.P((s0 + s1) / 2, (z0 + z1) / 2 + 30), it['pos'], h=1.4, ha='c', va='m', layer='A-TEXT')
    elif k == 'lounge':
        R(sh, ev, s0, 0, s1, 750, fill=WHITE)
    elif k == 'box':
        if it.get('_section'):
            a, b = ev.P(s0, 0), ev.P(s1, z1)
            sh.rect(a[0], a[1], b[0], b[1], fill=(0.85, 0.85, 0.85), lw=0.3, layer='A-ELEV')
            for p, q in poly_scan([a, (b[0], a[1]), b, (a[0], b[1])], 45, 1.2):
                sh.line(p, q, lw=0.1, layer='A-ELEV', color=MID)
        elif it.get('elev_outline'):                     # короб перед стеной: контур и полка
            R(sh, ev, s0, z0, s1, z1, style=LW)
            R(sh, ev, s0, z1 - 20, s1, z1, fill=(0.93, 0.93, 0.92), style=LT)
    elif k == 'hatch_wall':                              # люк-невидимка в стене
        R(sh, ev, s0, z0, s1, z1, dash=(1.2, 0.8), style=LW)
        sh.text(ev.P((s0 + s1) / 2, (z0 + z1) / 2), it.get('label', 'люк'), h=1.4, ha='c', va='m', layer='A-TEXT', bg=True)
    elif k == 'wc':
        c = (s0 + s1) / 2
        pts = [(c - 180, 420), (c + 180, 420), (c + 170, 330), (c + 110, 140), (c - 110, 140), (c - 170, 330)]
        sh.poly([ev.P(*p) for p in pts], fill=WHITE, **LW)
        R(sh, ev, c - 185, 420, c + 185, 445, fill=WHITE, style=LT)
        R(sh, ev, c - 125, 1000, c + 125, 1160, fill=(0.12, 0.12, 0.12), style=LT)
        Ln(sh, ev, c, 1010, c, 1150, style=dict(lw=0.15, layer='A-ELEV', color=(0.6, 0.6, 0.6)))
    elif k == 'vanity':
        vz0, vz1 = it['z']
        R(sh, ev, s0, vz0, s1, vz1, fill=(0.62, 0.58, 0.54))
        TX(sh, ev, s0, vz0, s1, vz1, it.get('mat', 'walnut'), along='h')
        R(sh, ev, s0, vz0, s1, vz1)
        Ln(sh, ev, s0 + 20, (vz0 + vz1) / 2, s1 - 20, (vz0 + vz1) / 2, style=dict(lw=0.15, layer='A-ELEV', color=WHITE))
        R(sh, ev, s0 - 10, vz1 - 30, s1 + 10, vz1 + 10, fill=WHITE, style=LT)
        c = (s0 + s1) / 2
        sh.poly([ev.P(c - 15, vz1 + 10), ev.P(c - 15, vz1 + 230), ev.P(c + 90, vz1 + 230)], closed=False, lw=0.5,
                layer='A-ELEV', color=BLACK)
    elif k == 'bath':
        bz0, bz1 = it.get('z', (0, 600))
        fr = it.get('apron')                       # экран ванны: код отделки (плитка) или None — фронт ванны
        if fr:
            R(sh, ev, s0, 0, s1, bz1 - 40, fill=WHITE)
            TX(sh, ev, s0, 0, s1, bz1 - 40, fr, orig_s=float(s0))
            R(sh, ev, s0, 0, s1, bz1 - 40)
            R(sh, ev, s0 + 60, 20, s0 + 360, 220, style=LT)      # ревизионный люк в экране
        else:
            R(sh, ev, s0, 0, s1, bz1 - 40, fill=WHITE)
        R(sh, ev, s0 - 10, bz1 - 40, s1 + 10, bz1, fill=WHITE, style=LW)
    elif k == 'mini_basin':
        bz0, bz1 = it['z']
        R(sh, ev, s0, bz0, s1, bz1, fill=WHITE)
        c = (s0 + s1) / 2
        sh.poly([ev.P(c - 10, bz1), ev.P(c - 10, bz1 + 150), ev.P(c + 70, bz1 + 150)], closed=False, lw=0.45,
                layer='A-ELEV', color=BLACK)
    elif k == 'wm_cab':
        R(sh, ev, s0, 0, s1, z1, fill=WHITE)
        TX(sh, ev, s0, 100, s1, z1, it.get('mat', 'walnut'), along='v')
        R(sh, ev, s0, 0, s1, z1)
        Ln(sh, ev, s0, 1850, s1, 1850)
        Ln(sh, ev, s0, 100, s1, 100)
        R(sh, ev, s0 + 25, 120, s1 - 25, 960, dash=(1.0, 0.6), style=LF)
        R(sh, ev, s0 + 25, 980, s1 - 25, 1820, dash=(1.0, 0.6), style=LF)
        sh.circle(ev.P((s0 + s1) / 2, 540), 200 / ev.k, dash=(1.0, 0.6), **LF)
        sh.circle(ev.P((s0 + s1) / 2, 1400), 200 / ev.k, dash=(1.0, 0.6), **LF)
        sh.text(ev.P((s0 + s1) / 2, 540), 'СМ', h=1.4, ha='c', va='m', layer='A-TEXT', color=MID)
        sh.text(ev.P((s0 + s1) / 2, 1400), 'СУШ', h=1.4, ha='c', va='m', layer='A-TEXT', color=MID)
    elif k == 'towel':
        R(sh, ev, s0, z0, s1, z1, style=LT)
        if s1 - s0 < 150:   # вид сбоку (у смежной стены) — без перекладин
            Ln(sh, ev, s0 + 30, z0, s0 + 30, z1, style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
            Ln(sh, ev, s1 - 10, z0 + 40, s1 - 10, z1 - 40, style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
            return
        zz = z0 + 40
        while zz < z1 - 20:
            Ln(sh, ev, s0, zz, s1, zz, style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
            zz += 90
    elif k == 'glass':
        TX(sh, ev, s0, z0, s1, z1, 'glass')
        R(sh, ev, s0, z0, s1, z1, style=dict(lw=0.4, layer='A-ELEV', color=BLACK))
        Ln(sh, ev, s0 + (s1 - s0) * 0.2, z0 + 400, s0 + (s1 - s0) * 0.55, z0 + 1000, style=LF)
        Ln(sh, ev, s0 + (s1 - s0) * 0.3, z0 + 300, s0 + (s1 - s0) * 0.7, z0 + 1000, style=LF)
    elif k == 'drain':
        R(sh, ev, s0, -60, s1, 20, fill=DARK, style=LT)
    elif k in ('chair', 'round', 'rug'):
        pass


def draw_shower_elev(sh, ev, s):
    """Душевая система открытого монтажа: термостат +1100, верхний душ +2150."""
    R(sh, ev, s - 170, 1060, s + 170, 1140, fill=(0.12, 0.12, 0.12), style=LT)
    Ln(sh, ev, s + 120, 1140, s + 120, 2150, style=dict(lw=0.7, layer='A-ELEV', color=BLACK))
    Ln(sh, ev, s + 120, 2150, s - 180, 2150, style=dict(lw=0.6, layer='A-ELEV', color=BLACK))
    R(sh, ev, s - 300, 2100, s - 60, 2140, fill=(0.12, 0.12, 0.12), style=LT)
    R(sh, ev, s + 100, 1450, s + 140, 1600, fill=(0.12, 0.12, 0.12), style=LT)


# ---------------- отделка ----------------
def openings_on(W, room):
    res = []
    for o in OPENINGS:
        pL = W['pL']
        if o['axis'] == 'x' and abs(W['d'][0]) < 1e-6:
            if o['c0'] - 1 <= pL[0] <= o['c1'] + 1:
                a, _ = proj(W, (pL[0], o['a'])); b, _ = proj(W, (pL[0], o['b']))
                res.append(dict(o, s0=min(a, b), s1=max(a, b)))
        elif o['axis'] == 'y' and abs(W['d'][1]) < 1e-6:
            if o['c0'] - 1 <= pL[1] <= o['c1'] + 1:
                a, _ = proj(W, (o['a'], pL[1])); b, _ = proj(W, (o['b'], pL[1]))
                res.append(dict(o, s0=min(a, b), s1=max(a, b)))
    return [o for o in res if o['s1'] > 0 and o['s0'] < W['L']]


def zone_lines(sh, ev, s0, s1, z0, z1, ops, vert=None, horz=None, style=None):
    style = style or dict(lw=0.1, layer='A-TILE', color=(0.45, 0.45, 0.45))
    for s in (vert or []):
        if s0 < s < s1:
            cuts = [(o['z0'], o['z1']) for o in ops if o['s0'] < s < o['s1']]
            for a, b in subtract_intervals((z0, z1), cuts):
                sh.line(ev.P(s, a), ev.P(s, b), **style)
    for z in (horz or []):
        if z0 < z < z1:
            cuts = [(o['s0'], o['s1']) for o in ops if o['z0'] < z < o['z1']]
            for a, b in subtract_intervals((s0, s1), cuts):
                sh.line(ev.P(a, z), ev.P(b, z), **style)


def draw_finishes(sh, ev, room, label, W, zc, zf, ops, scale_detail=True):
    tags = []
    dflt = D.WALL_DEFAULT.get(room)
    if dflt:
        TX(sh, ev, 0, zf, W['L'], zc, dflt, seed=(ord(room[1]) * 7 + ord(label)) % 97)
    for (r, lab, s0, s1, z0, z1, code) in D.WALL_ZONES:
        if r != room or lab != label:
            continue
        z1 = min(z1, zc)
        if code == 'X':
            continue
        tex = D.mat(code).get('tex')
        efill = D.mat(code).get('elev_fill')
        if tex == 'slats':
            TX(sh, ev, s0, z0, s1, z1, code, orig_s=float(s0))
            if not TEXTURES:
                step = 60 if ev.k <= 25 else 120
                x = s0 + 20
                while x < s1:
                    sh.line(ev.P(x, z0), ev.P(x, z1), lw=0.12, layer='A-ELEV', color=WALNUT)
                    x += step
            tags.append((code, (s0 + s1) / 2, z1 - 260))
        elif tex == 'panels':
            a, b = ev.P(s0, z0), ev.P(s1, z1)
            sh.rect(a[0], a[1], b[0], b[1], fill=efill or PANEL, stroke=False, layer='A-ELEV')
            TX(sh, ev, s0, z0, s1, z1, code, orig_s=0.0)
            step = D.mat(code).get('step', 600)
            x = s0 + step
            while x < s1 - 50 and D.mat(code).get('style') != 'boiserie':
                sh.line(ev.P(x, z0), ev.P(x, z1), lw=0.1, layer='A-ELEV', color=MID)
                x += step
            tags.append((code, s0 + min(260, (s1 - s0) / 2), z1 - 260))
        elif tex == 'marble':
            a, b = ev.P(s0, z0), ev.P(s1, z1)
            sh.rect(a[0], a[1], b[0], b[1], fill=efill or MARBLE, stroke=False, layer='A-ELEV')
            TX(sh, ev, s0, z0, s1, z1, code, seed=int(s0) % 13)
            sh.rect(a[0], a[1], b[0], b[1], lw=0.15, layer='A-ELEV', color=MID)
            tags.append((code, (s0 + s1) / 2, (z0 + z1) / 2))
        elif tex == 'tiles':
            a, b = ev.P(s0, z0), ev.P(s1, z1)
            sh.rect(a[0], a[1], b[0], b[1], fill=efill or TILE_L, stroke=False, layer='A-ELEV')
            tp = tile_params(room, label, s0, s1, code)
            TX(sh, ev, s0, z0, s1, z1, code, orig_s=float(s0), orig_z=float(z0), **tp)
            tags.append((code, (s0 + s1) / 2, z1 - 220))
        else:
            TX(sh, ev, s0, z0, s1, z1, code)
            tags.append((code, (s0 + s1) / 2, z1 - 220))
    # раскладка плитки
    for (r, lab, s0, s1, z0, z1, tw_, th_, so, zo) in D.TILE_LAYOUT:
        if r != room or lab != label:
            continue
        vs = []
        k0 = math.floor((s0 - so) / tw_) - 1
        k1 = math.ceil((s1 - so) / tw_) + 1
        for k in range(k0, k1 + 1):
            vs.append(so + k * tw_)
        hs = []
        k0 = math.floor((z0 - zo) / th_) - 1
        k1 = math.ceil((z1 - zo) / th_) + 1
        for k in range(k0, k1 + 1):
            hs.append(zo + k * th_)
        st = dict(lw=0.08 if tw_ < 200 else 0.14, layer='A-TILE', color=(0.40, 0.36, 0.32) if tw_ < 200 else (0.45, 0.45, 0.45))
        zone_lines(sh, ev, s0, s1, z0, min(z1, zc), ops, vert=vs, horz=hs, style=st)
    return tags


def draw_opening(sh, ev, o, room, W):
    s0, s1, z0, z1 = o['s0'], o['s1'], o['z0'], o['z1']
    if o['kind'] == 'door':
        slat_door = room in o.get('clad', {})
        R(sh, ev, s0, z0, s1, z1 + 40, fill=WHITE if not slat_door else None, style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
        if not slat_door:
            TX(sh, ev, s0 + 15, z0 + 10, s1 - 15, z1, D.WALL_DEFAULT.get(room) or door_leaf_finish(), seed=7)
            R(sh, ev, s0, z0, s1, z1 + 40, style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
        R(sh, ev, s0 + 15, z0 + 10, s1 - 15, z1, style=LT)
        d = D.DOORS[o['key']]
        hx, hy = d['h']; cx, cy = d['c']
        latch = (hx + cx * d['L'], hy + cy * d['L'])
        sh_, _ = proj(W, (hx, hy)); sl, _ = proj(W, latch)
        # линии открывания: вершина — сторона петель; сплошные — открывание на смотрящего, штрих — от него
        o_ = d['o']
        toward = (o_[0] * W['n'][0] + o_[1] * W['n'][1]) > 0
        sh.poly([ev.P(sl, z1), ev.P(sh_, (z0 + z1) / 2), ev.P(sl, z0 + 10)], closed=False, lw=0.12 if not toward else 0.18,
                layer='A-ELEV', color=MID if not toward else DARK, dash=None if toward else (1.4, 0.9))
        hxs = sl + (60 if sl < sh_ else -60)
        R(sh, ev, min(hxs, hxs + (130 if sl < sh_ else -130)), 990, max(hxs, hxs + (130 if sl < sh_ else -130)), 1020,
          fill=BLACK, style=LT)
        sh.text(ev.P((s0 + s1) / 2, z1 - 250), o.get('mark', ''), h=1.8, ha='c', va='m', layer='A-TEXT', bg=True)
    elif o['kind'] == 'window':
        R(sh, ev, s0, z0, s1, z1, fill=(0.93, 0.96, 0.98), style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
        R(sh, ev, s0 + 60, z0 + 60, s1 - 60, z1 - 60, style=LT)
        Ln(sh, ev, (s0 + s1) / 2, z0 + 60, (s0 + s1) / 2, z1 - 60)
        R(sh, ev, s0 - 40, z0 - 40, s1 + 40, z0, fill=WHITE, style=LT)
    elif o['kind'] == 'bdoor':
        R(sh, ev, s0, z0, s1, z1, fill=(0.93, 0.96, 0.98), style=dict(lw=0.35, layer='A-ELEV', color=BLACK))
        R(sh, ev, s0 + 60, z0 + 60, s1 - 60, z1 - 60, style=LT)
        R(sh, ev, s0 + 60, z0 + 60, s1 - 60, 900, style=LT)


def door_leaf_finish():
    """Отделка полотна скрытой двери в помещении без основного тона стен."""
    c = getattr(D, 'DOOR_LEAF_FINISH', None)
    if c:
        return c
    return next((k for k in D.FINISH if D.mat(k).get('tex') == 'paint'), 'С1')


def point_symbol(sh, ev, P, kind, s, z):
    """Электро/сантех знаки на развёртке (в масштабе рамок 80×80); розетки — красные, выключатели — синие."""
    if kind in ('r1', 'r2', 'r2u', 'r1w', 'r2w', 'tvblock', 'medblock', 'deskblock', 'pow', 'out', 'shk', 'mirrorled'):
        sh = SY.Tint(sh, SY.EL_RED)
    elif kind in ('v1', 'v2', 'v1p', 'v2p'):
        sh = SY.Tint(sh, SY.SW_BLUE)
    elif kind == 'tr':
        sh = SY.Tint(sh, SY.TR_ORANGE)
    elif kind in ('int', 'ssh'):
        sh = SY.Tint(sh, SY.LOW_GREEN)
    k = ev.k
    w = 80 / k
    c = ev.P(s, z + 40)
    def box(cx, cy, ww=w, hh=w, fill=WHITE, col=BLACK):
        sh.rect(cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2, fill=fill, lw=0.2, layer='E-POWER', color=col)
    if kind in ('r1', 'r1w', 'int'):
        box(*c)
        if kind == 'int':
            sh.text(c, 'Д', h=1.1, ha='c', va='m', layer='E-POWER')
        else:
            sh.circle(c, w * 0.28, lw=0.15, layer='E-POWER', fill=BLACK if kind == 'r1w' else None)
    elif kind in ('r2', 'r2u', 'r2w'):
        for dx in (-w / 2, w / 2):
            box(c[0] + dx, c[1])
            sh.circle((c[0] + dx, c[1]), w * 0.28, lw=0.15, layer='E-POWER', fill=BLACK if kind == 'r2w' else None)
    elif kind in ('tvblock', 'medblock', 'deskblock'):
        n = {'tvblock': 4, 'medblock': 3, 'deskblock': 4}[kind]
        for i in range(n):
            dx = (i - (n - 1) / 2) * w
            box(c[0] + dx, c[1])
            if i < (2 if kind != 'deskblock' else 3):
                sh.circle((c[0] + dx, c[1]), w * 0.28, lw=0.15, layer='E-POWER')
            else:
                sh.text((c[0] + dx, c[1]), 'RJ' if (kind != 'tvblock' or i == n - 1) else 'TV', h=0.8, ha='c', va='m',
                        layer='E-POWER')
    elif kind == 'pow':
        box(*c)
        sh.line((c[0] - w / 2, c[1] - w / 2), (c[0] + w / 2, c[1] + w / 2), lw=0.15, layer='E-POWER')
        sh.line((c[0] - w / 2, c[1] + w / 2), (c[0] + w / 2, c[1] - w / 2), lw=0.15, layer='E-POWER')
    elif kind == 'out':
        sh.poly([(c[0] - w / 2, c[1] - w / 2), (c[0] + w / 2, c[1] - w / 2), (c[0], c[1] + w / 2)], lw=0.15,
                layer='E-POWER', fill=BLACK)
    elif kind in ('shk', 'ssh'):
        ww = (300 if kind == 'shk' else 220) / k
        hh = (500 if kind == 'shk' else 300) / k
        cc = ev.P(s, z + (250 if kind == 'shk' else 150))
        sh.rect(cc[0] - ww / 2, cc[1] - hh / 2, cc[0] + ww / 2, cc[1] + hh / 2, lw=0.25, layer='E-POWER',
                fill=(0.85, 0.85, 0.85))
        sh.text(cc, 'ЩК' if kind == 'shk' else 'СЩ', h=1.3, ha='c', va='m', layer='E-POWER')
    elif kind in ('v1', 'v2', 'v1p', 'v2p', 'tr'):
        box(*c)
        if kind == 'tr':
            sh.text(c, 't°', h=1.0, ha='c', va='m', layer='E-SWITCH')
        else:
            n = 2 if kind in ('v2', 'v2p') else 1
            for i in range(n):
                x = c[0] + (i - (n - 1) / 2) * w * 0.42
                sh.line((x, c[1] - w * 0.3), (x, c[1] + w * 0.3), lw=0.15, layer='E-SWITCH')
    elif kind in ('hvs', 'gvs', 'k50', 'k110', 'tap', 'sif'):
        cc = ev.P(s, z)
        col = {'hvs': SY.BLUE, 'gvs': SY.RED, 'tap': SY.BLUE}.get(kind, SY.BROWN)
        r = {'k110': 55, 'k50': 30}.get(kind, 12) / k + 0.5
        sh.circle(cc, r, lw=0.25, layer='P-WATER', color=col, fill=col if kind in ('hvs', 'gvs', 'tap') else WHITE)
    elif kind in ('sconce', 'wall44'):
        if P.get('style') == 'bar':
            R(sh, ev, s - 20, 1500, s + 20, 2000, fill=BLACK, style=LT)
            R(sh, ev, s - 35, 1500, s + 35, 1515, fill=(1.0, 0.8, 0.4), style=LF)
        else:
            cc = ev.P(s, z)
            sh.circle(cc, 70 / k + 0.3, lw=0.25, layer='E-LIGHT', fill=(1.0, 0.85, 0.5))
            sh.line((cc[0], cc[1] + 70 / k + 0.3), (cc[0], cc[1] + 200 / k), lw=0.3, layer='E-LIGHT')
    elif kind == 'mirrorled':
        cc = ev.P(s, z)
        sh.poly([(cc[0] - w / 2, cc[1] - w / 2), (cc[0] + w / 2, cc[1] - w / 2), (cc[0], cc[1] + w / 2)], lw=0.15,
                layer='E-POWER', fill=BLACK)


ELEV_PLUMB = False        # выводы воды/канализации на развёртках (стандарт бюро — не показывать)


def points_on(W, room):
    res = []
    for P in D.POINTS:
        if P['room'] != room:
            continue
        s, dd = proj(W, P['p'])
        if abs(dd) < 6 and -1 <= s <= W['L'] + 1:
            res.append((P, P['kind'], s, P['z']))
    for P in (D.PLUMB if ELEV_PLUMB else []):      # стандарт бюро: на развёртках — только электрика и мебель
        if P['room'] != room or not P['n']:
            continue
        s, dd = proj(W, P['p'])
        if abs(dd) < 6 and -1 <= s <= W['L'] + 1:
            res.append((dict(P, room=room), P['kind'], s, P['z']))
        elif P.get('frame') and abs(dd) < 260 and -1 <= s <= W['L'] + 1 and dd > 0:
            # выводы на раме инсталляции (в коробе) — проецируем на стену короба
            res.append((dict(P, room=room), P['kind'], s, P['z']))
    for L in D.LIGHTS:
        if L['room'] != room or 'z' not in L or 'p' not in L:
            continue
        s, dd = proj(W, L['p'])
        if abs(dd) < 80 and -1 <= s <= W['L'] + 1:
            res.append((L, L['kind'], s, L['z']))
    return res


FLOOR_BAND = (0.93, 0.90, 0.84)
CEIL_BAND = (0.90, 0.92, 0.95)


def buildup_bands(sh, ev, L, zf, zc, ceil_t=150):
    """Пирог пола (от чернового пола до чистого) и потолка (условно 150) — полосатая штриховка."""
    for z0, z1, col, ang in ((-D.FLOOR_BUILDUP, zf, FLOOR_BAND, 45), (zc, zc + ceil_t, CEIL_BAND, -45)):
        a, b = ev.P(0, z0), ev.P(L, z1)
        pts = [(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1])]
        sh.poly(pts, fill=col, lw=0.15, layer='A-ELEV', color=MID)
        for p, q in poly_scan(pts, ang, 0.9):
            sh.line(p, q, lw=0.08, layer='A-ELEV', color=(0.45, 0.42, 0.38))


def elevation(sh, room, label, X0, Y0, k=25.0, title_txt=None, show_tags=True, dims=True, levels='right', vdim_off=380):
    W = wall_geom(room, label)
    L = W['L']
    zf = D.ROOM[room]['level'] or 0
    zc = D.ROOM[room]['ceil']
    ev = EV(X0, Y0, k)
    fv = FV(ev)
    ops = openings_on(W, room)
    # контур стены
    a, b = ev.P(0, zf), ev.P(L, zc)
    sh.rect(a[0], a[1], b[0], b[1], fill=WHITE, stroke=False, layer='A-ELEV')
    tags = draw_finishes(sh, ev, room, label, W, zc, zf, ops)
    for o in ops:
        draw_opening(sh, ev, o, room, W)
    # предметы у стены
    seen_upper = False
    for it in D.ITEMS:
        if it['room'] != room:
            continue
        r = item_rect(it)
        if it.get('elev_only') and label not in it['elev_only']:     # предмет показывается только на этих развёртках
            continue
        if it['kind'] == 'shower':
            s, dd = proj(W, it['c'])
            if abs(dd) < 6:
                draw_shower_elev(sh, ev, s)
            continue
        if r is None:
            continue
        s0, s1, d0, d1 = item_proj(W, it, r)
        if s1 <= 0 or s0 >= L:
            continue
        lim = 1000 if it['kind'] == 'glass' else 60
        if it['kind'] in ('wc', 'vanity', 'mini_basin'):
            mn = {'W': (1, 0), 'E': (-1, 0), 'S': (0, 1), 'N': (0, -1)}[it['wall']]
            if (mn[0], mn[1]) == (round(W['n'][0]), round(W['n'][1])) and d0 <= 260:
                lim = 260
        if d0 > lim:
            continue
        if it['kind'] == 'glass' and d1 - d0 > 100:
            continue
        s0c, s1c = max(s0, 0), min(s1, L)
        if it['kind'] == 'box':
            depth_room = max(proj(W, p)[1] for p in D.ROOMS[room]['poly'])
            it = dict(it, _section=(d1 - d0) > (s1 - s0) and d1 >= depth_room - 10)
        draw_item_elev(sh, ev, it, s0c, s1c, W, room)
    # точки
    pts = points_on(W, room)
    for P, kind, s, z in pts:
        if P.get('hidden'):
            c = ev.P(s, z + 40)
            w = 80 / ev.k
            point_symbol(sh, ev, P, kind, s, z)
            sh.rect(c[0] - w * 0.9, c[1] - w * 0.9, c[0] + w * 0.9, c[1] + w * 0.9, lw=0.2, layer='A-ELEV',
                    color=(0.5, 0.5, 0.5), dash=(0.6, 0.5))
        else:
            point_symbol(sh, ev, P, kind, s, z)
    # контур поверх
    sh.rect(a[0], a[1], b[0], b[1], lw=0.5, layer='A-ELEV')
    # смежные стены в разрезе
    for s_edge, sgn in ((0, -1), (L, 1)):
        p0 = ev.P(s_edge, zf - 150)
        p1 = ev.P(s_edge + sgn * 120, zc + 150)
        sh.rect(min(p0[0], p1[0]), p0[1], max(p0[0], p1[0]), p1[1], fill=WALLFILL, lw=0.3, layer='A-ELEV')
    # пол и потолок: пирог — условно, полосатой штриховкой
    buildup_bands(sh, ev, L, zf, zc)
    pf0, pf1 = ev.P(-120, zf), ev.P(L + 120, zf)
    sh.line(pf0, pf1, lw=0.6, layer='A-ELEV')
    sh.line(ev.P(0, zc), ev.P(L, zc), lw=0.5, layer='A-ELEV')
    # ниши в потолке у стены
    for f in D.CEIL_FEATURES:
        if f['room'] != room or f['kind'] not in ('niche', 'cove'):
            continue
        s0, s1, d0, d1 = proj_rect(W, f['rect'])
        if d0 <= 5 and s1 > 0 and s0 < L:
            if d1 - d0 < 300:
                # вдоль стены — ниша над стеной
                p0 = ev.P(max(s0, 0), zc); p1 = ev.P(min(s1, L), D.ROUGH_CEIL - 10)
                sh.rect(p0[0], p0[1], p1[0], p1[1], fill=(1.0, 0.95, 0.80) if f['kind'] == 'cove' else (0.85, 0.89, 0.95),
                        lw=0.2, layer='A-ELEV', color=MID)
    # бирки отделки
    if show_tags:
        used = []
        for code, s, z in tags:
            _tag(sh, ev, code, s, z)
            used.append((s, z))
        dflt = D.WALL_DEFAULT.get(room)
        if dflt:
            covered = [(z0, z1, s0, s1) for (r, lab, s0, s1, z0, z1, c) in D.WALL_ZONES if r == room and lab == label]
            blockers = []
            for it2 in D.ITEMS:
                if it2['room'] != room:
                    continue
                r2 = item_rect(it2)
                if not r2:
                    continue
                a2, b2, d02, d12 = item_proj(W, it2, r2)
                z2 = it2.get('z', (0, 0))
                if d02 <= 260 and isinstance(z2, tuple):
                    blockers.append((a2 - 150, b2 + 150, z2[0] - 150, z2[1] + 150))
            for s in (L * 0.12, L * 0.5, L * 0.88, L * 0.3, L * 0.7, L * 0.2, L * 0.6):
                z = zc - 260
                if any(s0 <= s <= s1 and z0 <= z <= z1 for z0, z1, s0, s1 in covered):
                    continue
                if any(a2 <= s <= b2 and c2 <= z <= e2 for a2, b2, c2, e2 in blockers):
                    continue
                if any(o['s0'] - 100 <= s <= o['s1'] + 100 and o['z1'] > z - 200 for o in ops):
                    continue
                _tag(sh, ev, dflt, s, z)
                break
    # размеры
    if dims:
        edges = {0.0, L}
        for o in ops:
            edges |= {round(o['s0']), round(o['s1'])}
        for it in D.ITEMS:
            if it['room'] != room or it['kind'] in ('chair', 'rug', 'round', 'shower', 'drain', 'glass', 'box', 'wallshelf'):
                continue
            r = item_rect(it)
            if not r:
                continue
            s0, s1, d0, d1 = item_proj(W, it, r)
            if d0 <= 60 and s1 > 0 and s0 < L:
                if it['kind'] in ('kitchen_run',) and s1 - s0 > 900:
                    for a_, b_, kind in it['modules']:
                        pa, _ = proj(W, mod_pt(it, a_))
                        edges.add(round(pa))
                edges |= {round(max(s0, 0)), round(min(s1, L))}
        ev_ = sorted(e for e in edges if -1 <= e <= L + 1)
        ev_ = _dedupe(ev_, 15)
        mdim(sh, fv, 'y', ev_, zf - 330, ext=zf, h=1.9 if k <= 25 else 1.7)
        # привязка рамок — по оси группы (посты одной рамки на одной высоте с шагом ≤ 130 — одна привязка)
        byz = {}
        for P, kind, s, z in pts:
            byz.setdefault(round(z), []).append(s)
        centers = set()
        edges_ = [0.0, L] + [o['s0'] for o in ops] + [o['s1'] for o in ops]

        def pick(grp):
            # привязка рамки — до оси крайнего поста со стороны ближайшего проёма/угла
            if len(grp) == 1:
                return round(grp[0])
            dl = min(abs(grp[0] - e_) for e_ in edges_)
            dr = min(abs(grp[-1] - e_) for e_ in edges_)
            return round(grp[0] if dl <= dr else grp[-1])
        for z, ss in byz.items():
            ss = sorted(ss)
            grp = [ss[0]]
            for s_ in ss[1:]:
                if s_ - grp[-1] <= 130:
                    grp.append(s_)
                else:
                    centers.add(pick(grp))
                    grp = [s_]
            centers.add(pick(grp))
        ps = sorted(centers | {0, round(L)})
        ps = _dedupe(ps, 8)
        if len(ps) > 2:
            mdim(sh, fv, 'y', ps, zf - 620, ext=zf, h=1.8 if k <= 25 else 1.6)
        zs = {zf, zc}
        for o in ops:
            zs |= {o['z0'], o['z1']}
        for it in D.ITEMS:
            if it['room'] != room:
                continue
            r = item_rect(it)
            if not r or it['kind'] in ('chair', 'rug', 'round', 'box', 'radiator', 'coffee', 'sofa', 'bed', 'bed_single',
                                       'wallshelf', 'drain', 'glass', 'lounge'):
                continue
            s0, s1, d0, d1 = item_proj(W, it, r)
            if d0 <= 60 and s1 > 0 and s0 < L:
                zz = it.get('z', (0, 0))
                zs |= {zz[0], zz[1]}
        zs = sorted(z for z in zs if zf - 1 <= z <= zc + 1)
        zs = _dedupe(zs, 25)
        mdim(sh, fv, 'x', zs, L + vdim_off, ext=L, h=1.9 if k <= 25 else 1.7)
        # высоты приборов — на горизонтальной выноске (180°), одна подпись на рамку
        hboxes = []
        groups = {}
        for P, kind, s, z in pts:
            if kind in ('sconce', 'wall44'):
                continue
            fam = 'P' if kind in ('hvs', 'gvs', 'k50', 'k110', 'tap', 'sif') else 'E'
            groups.setdefault((fam, z), []).append((s, kind))
        frames = []
        for (fam, z), lst in groups.items():
            lst.sort()
            cur = [lst[0]]
            for it_ in lst[1:]:
                if it_[0] - cur[-1][0] <= (160 if fam == 'P' else 130):
                    cur.append(it_)
                else:
                    frames.append((fam, z, cur))
                    cur = [it_]
            frames.append((fam, z, cur))
        th = 1.3 if k <= 25 else 1.15
        half = 40 / k
        for fam, z, fr in sorted(frames, key=lambda t: (t[1], t[2][0][0])):
            s_lo, s_hi = fr[0][0], fr[-1][0]
            zz = z + 40 if fam == 'E' else z
            if fam == 'E' and any(kk in ('tvblock', 'deskblock') for _, kk in fr):
                s_hi += 120
            txt = '+' + str(z) if z else '±0'
            tw_ = tw(txt, th) + 0.8
            done = False
            for side in (1, -1):
                for lead in (2.5, 5.0, 8.0, 11.0):
                    ps = ev.P(s_hi, zz) if side > 0 else ev.P(s_lo, zz)
                    x0 = ps[0] + side * (half + 0.3)
                    x1 = x0 + side * lead
                    x2 = x1 + side * tw_
                    bx = (min(x1, x2), max(x1, x2), ps[1] - 0.2, ps[1] + th + 0.6)
                    wall_l, wall_r = ev.P(0, 0)[0], ev.P(L, 0)[0]
                    if bx[0] < wall_l - 0.5 or bx[1] > wall_r + 0.5:
                        continue
                    if all(bx[1] < q[0] or bx[0] > q[1] or bx[3] < q[2] or bx[2] > q[3] for q in hboxes):
                        sh.line((x0, ps[1]), (x2, ps[1]), lw=0.15, layer='A-TEXT', color=DARK)
                        sh.circle((x0, ps[1]), 0.25, lw=0.1, layer='A-TEXT', fill=DARK, color=DARK)
                        sh.text(((x1 + x2) / 2, ps[1] + 0.35), txt, h=th, ha='c', va='b', layer='A-TEXT', color=BLACK,
                                bg=True)
                        hboxes.append(bx)
                        done = True
                        break
                if done:
                    break
        # отметки
        for zz in ((zf, zc) if levels else ()):
            if levels == 'right':
                p = ev.P(L, zz)
                p = (p[0] + 20.0, p[1])
                sh.poly([(p[0] - 1.2, p[1] + 1.4), (p[0] + 1.2, p[1] + 1.4), (p[0], p[1])], lw=0.2, layer='A-TEXT', fill=WHITE)
                sh.line((p[0] - 1.6, p[1]), (p[0] + 9.5, p[1]), lw=0.2, layer='A-TEXT')
                sh.text((p[0] + 1.6, p[1] + 0.6), lvl(zz), h=1.7, layer='A-TEXT')
            else:
                p = ev.P(0, zz)
                p = (p[0] - 8.0, p[1])
                sh.poly([(p[0] - 1.2, p[1] + 1.4), (p[0] + 1.2, p[1] + 1.4), (p[0], p[1])], lw=0.2, layer='A-TEXT', fill=WHITE)
                sh.line((p[0] + 1.6, p[1]), (p[0] - 10.5, p[1]), lw=0.2, layer='A-TEXT')
                sh.text((p[0] - 1.6, p[1] + 0.6), lvl(zz), h=1.7, ha='r', layer='A-TEXT')
    # заголовок
    tt = title_txt or f'Стена {label}'
    p = ev.P(0, zc + 330)
    if D.CORNER_LETTERS:            # стандарт бюро: буквы — у углов на схеме, развёртка — «А–Б»
        sh.text((p[0], p[1]), f'Развёртка {D.wall_span(room, label)}  М 1:{int(k)}', h=2.6, layer='A-TEXT', font='BoldObl')
    else:
        sh.circle((p[0] + 2.4, p[1] + 1.1), 2.4, lw=0.35, layer='A-TEXT')
        sh.text((p[0] + 2.4, p[1] + 1.1), label, h=2.4, ha='c', va='m', layer='A-TEXT', font='BoldObl')
        sh.text((p[0] + 6.0, p[1]), f'Развёртка стены {label}  М 1:{int(k)}', h=2.6, layer='A-TEXT', font='BoldObl')
    return ev


def _dedupe(vals, tol):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
        elif v == vals[-1]:
            out[-1] = v
    return out


def _tag(sh, ev, code, s, z):
    c = ev.P(s, z)
    w = tw(code, 1.9, 'BoldObl') + 2.0
    sh.rect(c[0] - w / 2, c[1] - 1.5, c[0] + w / 2, c[1] + 1.5, fill=WHITE, lw=0.3, layer='A-TEXT')
    sh.text(c, code, h=1.9, ha='c', va='m', layer='A-TEXT', font='BoldObl')


def keyplan_off(room):
    """Отступ букв стен на схеме помещения от стены (мм модели): album.KEYPLAN_OFF или −380 (внутрь)."""
    try:
        import album as AL
        return getattr(AL, 'KEYPLAN_OFF', {}).get(room, -380)
    except ImportError:
        return -380


def key_plan(sh, room, X, Y, k=100.0, title='Схема помещения'):
    """Мини-план помещения с обозначением углов (стандарт бюро) или стен."""
    from core import View, Pen
    import drawplan as DP
    poly = D.ROOMS[room]['poly']
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    v = View(X + cy / k, Y + cx / k, k)
    # смещение: центр помещения в (X, Y)
    v = View(X - cy / k, Y + cx / k, k)
    pen = Pen(sh, v)
    pen.poly(poly, fill=(0.97, 0.97, 0.97), lw=0.4, layer='A-TEXT')
    for it in D.ITEMS:
        if it['room'] == room:
            DP.draw_item(pen, it, faint_=True)
    for lab, pL, pR in D.RWALLS[room]:
        sh.line(v.P(*pL), v.P(*pR), lw=0.7, layer='A-TEXT')
    if D.CORNER_LETTERS:            # стандарт бюро: буквы — углам (снаружи угла, по биссектрисе)
        placed = []
        for lab, c in D.corners(room):
            P0 = v.P(*c)
            # направление «наружу»: от центра помещения к углу (в координатах листа)
            C0 = v.P(cx, cy)
            dx, dy = P0[0] - C0[0], P0[1] - C0[1]
            L_ = math.hypot(dx, dy) or 1.0
            a0 = math.atan2(dy, dx)
            P = None
            for d in (3.4, 4.6, 5.8):              # близкие углы (короткая стена) — поворот вокруг угла до свободного места
                for da in (0, 25, -25, 50, -50, 75, -75, 100, -100):
                    a = a0 + math.radians(da)
                    Q = (P0[0] + math.cos(a) * d, P0[1] + math.sin(a) * d)
                    if all(math.hypot(Q[0] - q[0], Q[1] - q[1]) >= 4.4 for q in placed):
                        P = Q
                        break
                if P:
                    break
            P = P or (P0[0] + dx / L_ * 3.4, P0[1] + dy / L_ * 3.4)
            placed.append(P)
            dd = math.hypot(P[0] - P0[0], P[1] - P0[1]) or 1.0
            sh.line(P0, (P[0] - (P[0] - P0[0]) / dd * 2.0, P[1] - (P[1] - P0[1]) / dd * 2.0), lw=0.15, layer='A-TEXT')
            sh.circle(P0, 0.5, lw=0.2, layer='A-TEXT', fill=BLACK)
            sh.circle(P, 2.0, lw=0.3, layer='A-TEXT', fill=WHITE)
            sh.text(P, lab, h=1.8, ha='c', va='m', layer='A-TEXT', font='BoldObl')
    else:
        for lab, pL, pR in D.RWALLS[room]:
            m = ((pL[0] + pR[0]) / 2, (pL[1] + pR[1]) / 2)
            dx, dy = pR[0] - pL[0], pR[1] - pL[1]
            Ld = math.hypot(dx, dy)
            n = (dy / Ld, -dx / Ld)
            off = keyplan_off(room)
            q = (m[0] + n[0] * off, m[1] + n[1] * off)
            P = v.P(*q)
            sh.circle(P, 2.0, lw=0.3, layer='A-TEXT', fill=WHITE)
            sh.text(P, lab, h=1.8, ha='c', va='m', layer='A-TEXT', font='BoldObl')
    tx = X - (max(ys) - min(ys)) / k / 2
    sh.text((tx, Y + (max(xs) - min(xs)) / k / 2 + 6), title + f'  М 1:{int(k)}', h=2.2, layer='A-TEXT', font='BoldObl')


FIN_TXT = lambda codes: [(None, f'{c} — {D.FINISH[c]}') for c in codes]


def finish_legend(sh, x, y, codes, width=160, title='Отделка (см. ведомость отделки)', sw=7.0):
    sh.text((x, y), title, h=2.4, layer='A-TEXT', font='BoldObl')
    y -= 4.2
    from kit import wrap
    import textures as T
    for c in codes:
        lines = wrap(D.FINISH[c], width - sw - 14, 1.8)
        hh = max(sw, len(lines) * 2.8)
        top = y
        if TEXTURES:
            sh.image(T.swatch_for(c, sw), x, top - sw, sw, sw)
        sh.rect(x, top - sw, x + sw, top, lw=0.2, layer='A-TEXT')
        _tag(sh, type('E', (), {'P': staticmethod(lambda s, z: (s, z))})(), c, x + sw + 5, top - 2.2)
        yy = top - 2.2
        for ln in lines:
            sh.text((x + sw + 11, yy - 0.6), ln, h=1.8, layer='A-TEXT')
            yy -= 2.8
        y = top - hh - 2.0
    return y


def _band_sample(s, x, y, col, ang):
    pts = [(x - 3.5, y - 1.0), (x + 3.5, y - 1.0), (x + 3.5, y + 1.0), (x - 3.5, y + 1.0)]
    s.poly(pts, fill=col, lw=0.15, color=MID)
    for p, q in poly_scan(pts, ang, 0.9):
        s.line(p, q, lw=0.08, color=(0.45, 0.42, 0.38))


def elev_legend(sh, x, y):
    items = [
        (lambda s, xx, yy: (s.rect(xx - 1.6, yy - 1.6, xx + 1.6, yy + 1.6, lw=0.2, layer='E-POWER', fill=WHITE, color=SY.EL_RED),
                            s.circle((xx, yy), 0.9, lw=0.15, layer='E-POWER', color=SY.EL_RED)), 'Розетка (рамка 80×80)'),
        (lambda s, xx, yy: (s.rect(xx - 1.6, yy - 1.6, xx + 1.6, yy + 1.6, lw=0.2, layer='E-SWITCH', fill=WHITE, color=SY.SW_BLUE),
                            s.line((xx, yy - 1), (xx, yy + 1), lw=0.15, layer='E-SWITCH', color=SY.SW_BLUE)), 'Выключатель'),
        (lambda s, xx, yy: (s.rect(xx - 1.6, yy - 1.6, xx + 1.6, yy + 1.6, lw=0.2, layer='E-SWITCH', fill=WHITE, color=SY.TR_ORANGE),
                            s.text((xx, yy), 't°', h=1.0, ha='c', va='m', color=SY.TR_ORANGE)), 'Терморегулятор'),
    ] + ([
        (lambda s, xx, yy: s.circle((xx, yy), 1.0, lw=0.2, layer='P-WATER', color=SY.BLUE, fill=SY.BLUE), 'ХВС'),
        (lambda s, xx, yy: s.circle((xx, yy), 1.0, lw=0.2, layer='P-HOT', color=SY.RED, fill=SY.RED), 'ГВС'),
        (lambda s, xx, yy: s.circle((xx, yy), 1.3, lw=0.25, layer='P-SEWER', color=SY.BROWN, fill=WHITE), 'Канализация'),
    ] if ELEV_PLUMB else []) + [
        (lambda s, xx, yy: s.poly([(xx - 1.4, yy - 1.2), (xx + 1.4, yy - 1.2), (xx, yy + 1.2)], lw=0.15, layer='E-POWER',
                                  fill=SY.EL_RED, color=SY.EL_RED), 'Вывод кабеля'),
        (lambda s, xx, yy: (s.line((xx - 4.0, yy), (xx + 2.0, yy), lw=0.15, color=DARK),
                            s.text((xx - 0.6, yy + 0.3), '+900', h=1.1, ha='c', layer='A-TEXT')), 'Высота до низа рамки'),
        (lambda s, xx, yy: _band_sample(s, xx, yy, FLOOR_BAND, 45), 'Пирог пола (условно)'),
        (lambda s, xx, yy: _band_sample(s, xx, yy, CEIL_BAND, -45), 'Пирог потолка (условно)'),
    ]
    return legend_box(sh, x, y, items, width=30, h=1.8, title='Обозначения')


# ---------------- листы ----------------
def _sheet(key, ttl):
    return Sheet(key, ttl)


# ---------------- автоматическая компоновка листов развёрток (новый объект) ----------------
ELEV_BOX = (30.0, 122.0, 410.0, 282.0)       # поле развёрток на листе: x0, y0, x1, y1 (мм)


def _elev_size(L, H, k, right_levels):
    title_w = 6.0 + tw(f'Развёртка стены Ж  М 1:{int(k)}', 2.6, 'BoldObl') + 4
    w = max(120 / k + L / k + 330 / k + 9, title_w) + (31 if right_levels else 0)
    h = 330 / k + 7 + H / k + 150 / k + 620 / k + 6
    return w, h


def _pack(room, walls, k):
    """Раскладка стен по рядам и листам при масштабе 1:k -> [[(label, X0, Y0, levels), ...], ...] по листам."""
    zf = D.ROOM[room]['level'] or 0
    zc = D.ROOM[room]['ceil'] or 2700
    H = zc - zf
    x0b, y0b, x1b, y1b = ELEV_BOX
    sheets, cur, rows = [], [], []
    y_top = y1b
    row, x = [], x0b
    for lab in walls:
        L = wall_geom(room, lab)['L']
        w, h = _elev_size(L, H, k, True)
        if row and x + w > x1b:
            rows.append(row)
            row, x = [], x0b
        row.append((lab, x, w, h))
        x += _elev_size(L, H, k, False)[0]
    if row:
        rows.append(row)
    for r in rows:
        hmax = max(e[3] for e in r)
        if cur and y_top - hmax < y0b:
            sheets.append(cur)
            cur, y_top = [], y1b
        for i, (lab, xx, w, h) in enumerate(r):
            X0 = xx + 120 / k + 2
            Y0 = y_top - 330 / k - 7 - zc / k
            cur.append((lab, X0, Y0, 'right' if i == len(r) - 1 else None))
        y_top -= hmax + 4
    if cur:
        sheets.append(cur)
    return sheets


def auto_room_sheets(room, notes_items=None):
    """Листы развёрток помещения: масштаб 1:25 (санузлы и малые) или 1:40, раскладка по рядам, схема, легенда отделки."""
    walls = [lab for lab, a, b in D.RWALLS[room]]
    name = D.ROOM[room]['name']
    wet = D.ROOM[room].get('zone') == 'wet'
    best = None
    for k in ((25.0, 40.0) if wet else (40.0, 25.0, 50.0)):
        pk = _pack(room, walls, k)
        if best is None or len(pk) < len(best[1]) or (len(pk) == len(best[1]) and k < best[0] and wet):
            best = (k, pk)
        if len(pk) == 1:
            best = (k, pk)
            break
    k, packs = best
    if len(packs) > 1:                      # равномерное деление стен по листам (2+2, а не 3+1)
        n = len(packs)
        per = -(-len(walls) // n)
        groups = [walls[i:i + per] for i in range(0, len(walls), per)]
        alt = [_pack(room, g, k) for g in groups]
        if all(len(a) == 1 for a in alt):
            packs = [a[0] for a in alt]
    codes = []
    for (r, lab, s0, s1, z0, z1, code) in D.WALL_ZONES:
        if r == room and code != 'X' and code not in codes:
            codes.append(code)
    dflt = D.WALL_DEFAULT.get(room)
    if dflt and dflt not in codes:
        codes.insert(0, dflt)
    codes.append(D.ROOM[room]['floor'])
    notes_items = notes_items if notes_items is not None else D.ROOM[room].get('elev_notes', [])
    out = []
    for i, pk in enumerate(packs):
        labs = [e[0] for e in pk]
        suffix = '' if len(packs) == 1 else 'abcdefgh'[i]

        def fn(no, total, pk=pk, labs=labs):
            sh = Sheet('E' + room, f'{name}. Развёртки')
            for lab, X0, Y0, lv in pk:
                elevation(sh, room, lab, X0, Y0, k, levels=lv, vdim_off=330)
            finish_legend(sh, 25, 114, codes, width=195)
            key_plan(sh, room, 262, 74, 100, f'{name} {room}')
            elev_legend(sh, 300, 114)
            if notes_items:
                notes(sh, 340, 114, 72, 'Примечания', notes_items, h=1.7, lead=2.55)
            frame(sh, no, total, f"{name} {room}.\nРазвёртки {D.wall_spans(room, labs)}")
            return sh
        out.append((room + suffix, f"{name} {room}. Развёртки {D.wall_spans(room, labs)}", fn))
    return out
