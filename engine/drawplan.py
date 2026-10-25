# -*- coding: utf-8 -*-
"""Отрисовка плана: стены, проёмы, двери, мебель по ITEMS (единая модель)."""
import math
from core import (Pen, View, rrect_pts, ell_pts, rot_pts, wall_union_edges, mdim, tw,
                  BLACK, DARK, MID, LIGHT, WHITE, WALLFILL, FILL_LT, Z_DAY, Z_NIGHT, Z_WET, Z_OUT)
import obmer as MV
import model as D

F = dict(lw=0.22, layer='A-FURN', color=DARK)
FT = dict(lw=0.13, layer='A-FURN', color=MID)
E = dict(lw=0.25, layer='A-EQPM', color=BLACK)
ET = dict(lw=0.15, layer='A-EQPM', color=DARK)
DASH = (2.0, 1.2)
FAINT = (0.70, 0.70, 0.70)
ZCOL = {'day': Z_DAY, 'night': Z_NIGHT, 'wet': Z_WET, 'out': Z_OUT}

def _plan_view():
    import annot as A
    return getattr(A, 'PLAN_VIEW', None)


VIEW = _plan_view()

# ---- цветной план (ред. Р3): элементы находятся глазами ----
COLORED = {'on': False, 'words': False}
PAL = {
    'built': (0.93, 0.90, 0.84),    # встроенная мебель в цвет стен
    'walnut': (0.86, 0.75, 0.62),   # шпон ореха
    'oak': (0.95, 0.89, 0.77),      # дуб, столы
    'soft': (0.86, 0.84, 0.82),     # мягкая мебель
    'olive': (0.82, 0.84, 0.70),    # банкетка
    'appl': (0.78, 0.88, 0.97),     # бытовая техника
    'sani': (0.86, 0.95, 1.00),     # сантехника
    'tv': (0.15, 0.15, 0.17),
}
KIND_COL = {'wardrobe': 'built', 'column': 'appl', 'filler': 'built', 'kitchen_run': 'built', 'table': 'oak',
            'chair': 'soft', 'sofa': 'soft', 'coffee': 'oak', 'tvconsole': 'walnut', 'bed': 'soft', 'bed_single': 'soft',
            'nightstand': 'walnut', 'desk': 'oak', 'shelving': 'oak', 'lounge': 'soft', 'round': 'oak', 'bench': 'olive',
            'console': 'walnut', 'wm_cab': 'appl', 'wc': 'sani', 'vanity': 'walnut', 'mini_basin': 'sani', 'towel': 'sani',
            'bath': 'sani'}


def _apply_palette():
    """Цвета групп мебели объекта: annot.PALETTE (дополняет/заменяет PAL), annot.KIND_COL (вид -> группа)."""
    try:
        import annot as A
    except ImportError:
        return
    PAL.update(getattr(A, 'PALETTE', {}) or {})
    KIND_COL.update(getattr(A, 'KIND_COL', {}) or {})


_apply_palette()


def _fc(k, default=WHITE, it=None):
    if COLORED['on'] and it is not None and it.get('pal') in PAL:
        return PAL[it['pal']]
    if COLORED['on'] and k in KIND_COL:
        return PAL[KIND_COL[k]]
    return default


def new_view():
    global VIEW
    if VIEW is None:
        VIEW = auto_view()
    return View(**VIEW)


def auto_view(box=(24.0, 100.0, 372.0, 283.0)):
    """Положение и масштаб плана: габарит стен + поля под размеры (сверху и слева) вписываются в поле box.
    Масштаб — 1:50, если помещается, иначе 1:75 или 1:100 (ГОСТ 2.302)."""
    xs, ys = D.wall_extent()
    top, left, bottom, right = 1500.0, 1500.0, 500.0, 600.0      # поля, мм модели (размерные цепочки — сверху и слева)
    x0, x1, y0, y1 = min(xs) - top, max(xs) + bottom, min(ys) - left, max(ys) + right
    bx0, by0, bx1, by1 = box
    for k in (50.0, 75.0, 100.0):
        w, h = (y1 - y0) / k, (x1 - x0) / k
        if w <= bx1 - bx0 and h <= by1 - by0:
            break
    # лист: X = X0 + y/k, Y = Y0 - x/k
    X0 = bx0 + ((bx1 - bx0) - w) / 2 - y0 / k
    Y0 = by1 - ((by1 - by0) - h) / 2 + x0 / k
    return dict(X0=X0, Y0=Y0, k=k)


def faint(style):
    d = dict(style)
    d['color'] = FAINT
    d['lw'] = min(d.get('lw', 0.2), 0.15)
    return d


def draw_zones(pen, which=None):
    for k, info in D.ROOM.items():
        if which and k not in which:
            continue
        pen.poly(D.ROOMS[k]['poly'], fill=ZCOL[info['zone']], stroke=False, layer='A-ZONE')


BEARFILL = (0.48, 0.48, 0.50)      # несущие стены (design.BEARING_MIN — толще этого, мм)


def is_bearing(r):
    bm = getattr(D, 'BEARING_MIN', None)
    return bm is not None and min(r[2] - r[0], r[3] - r[1]) > bm


def draw_walls(pen, fill=WALLFILL, shaft=True):
    bear = fill == WALLFILL and getattr(D, 'BEARING_MIN', None) is not None
    for r in D.WALLS:
        pen.rect(*r, fill=BEARFILL if bear and is_bearing(r) else fill, stroke=False, layer='A-WALL-FILL')
    for p in D.WALL_POLYS:                      # стены с наклонными гранями
        pen.poly(p, fill=BEARFILL if bear and getattr(D, 'BEARING_POLYS', False) else fill, stroke=False,
                 layer='A-WALL-FILL')
    from core import wall_outline
    for a, b in wall_outline(D.WALLS, D.WALL_POLYS):
        pen.line(a, b, lw=0.5, layer='A-WALL')
    if shaft:
        x0, y0, x1, y1 = D.SHAFT
        pen.rect(x0, y0, x1, y1, lw=0.25, layer='A-HATCH')
        pen.line((x0, y0), (x1, y1), lw=0.18, layer='A-HATCH')
        pen.line((x0, y1), (x1, y0), lw=0.18, layer='A-HATCH')


def door(pen, key, doors=None, faint_=False, color=None, fill=WHITE):
    d = (doors or D.DOORS)[key]
    hx, hy = d['h']
    cx, cy = d['c']
    ox, oy = d['o']
    L = d['L']
    t = 40
    col = color or (FAINT if faint_ else BLACK)
    p1 = (hx, hy)
    p2 = (hx + ox * L, hy + oy * L)
    p3 = (p2[0] + cx * t, p2[1] + cy * t)
    p4 = (hx + cx * t, hy + cy * t)
    pen.poly([p1, p2, p3, p4], lw=0.35 if not color else 0.45, layer='A-DOOR', fill=fill, color=col)
    a_open = math.degrees(math.atan2(oy, ox))
    a_closed = math.degrees(math.atan2(cy, cx))
    da = (a_closed - a_open) % 360
    if da <= 180:
        pen.arc((hx, hy), L, a_open, a_closed, lw=0.18, layer='A-DOOR', color=col)
    else:
        pen.arc((hx, hy), L, a_closed, a_open, lw=0.18, layer='A-DOOR', color=col)


def window_h(pen, x0, x1, yin, yout, frame=(0.45, 0.62)):
    """Окно в стене постоянного y: проём x0..x1, внутренняя грань yin, наружная yout."""
    t = yout - yin
    pen.line((x0, yin), (x1, yin), lw=0.18, layer='A-GLAZ')
    pen.line((x0, yout), (x1, yout), lw=0.18, layer='A-GLAZ')
    for f in frame:
        y = yin + t * f
        pen.line((x0, y), (x1, y), lw=0.25, layer='A-GLAZ')
    s = -1 if yout > yin else 1          # подоконник
    pen.rect(x0 - 30, yin, x1 + 30, yin + s * 60, lw=0.18, layer='A-GLAZ')


def window_v(pen, y0, y1, xin, xout, frame=(0.45, 0.62)):
    """Окно в стене постоянного x: проём y0..y1, внутренняя грань xin, наружная xout."""
    t = xout - xin
    pen.line((xin, y0), (xin, y1), lw=0.18, layer='A-GLAZ')
    pen.line((xout, y0), (xout, y1), lw=0.18, layer='A-GLAZ')
    for f in frame:
        x = xin + t * f
        pen.line((x, y0), (x, y1), lw=0.25, layer='A-GLAZ')
    s = -1 if xout > xin else 1
    pen.rect(xin, y0 - 30, xin + s * 60, y1 + 30, lw=0.18, layer='A-GLAZ')


def glazing():
    """Остекление для планов: obmer.GLAZING или (если не задано) окна из design.WINDOWS / OPENINGS."""
    g = getattr(MV, 'GLAZING', None)
    if g is not None:
        return g
    out = []
    for o in getattr(D, 'OPENINGS', []):
        if o['kind'] in ('window', 'bdoor'):
            out.append(('window', o['a'], o['b'], o.get('c_in', o['c0']), o.get('c_out', o['c1']), o['axis']))
    return out


def draw_glazing(pen):
    for g in glazing():
        if g[0] == 'window':
            axis = g[5] if len(g) > 5 else 'y'
            (window_h if axis == 'y' else window_v)(pen, g[1], g[2], g[3], g[4])
        elif g[0] == 'line':
            kw = dict(layer='A-GLAZ'); kw.update(g[3] if len(g) > 3 else {})
            pen.line(g[1], g[2], **kw)
        elif g[0] == 'rect':
            kw = dict(layer='A-GLAZ'); kw.update(g[2] if len(g) > 2 else {})
            pen.rect(*g[1], **kw)


def draw_openings(pen, door_keys=None, doors=None, faint_doors=False):
    draw_glazing(pen)
    for k in (door_keys if door_keys is not None else D.DOOR_LIST):
        door(pen, k, doors, faint_=faint_doors)


# сокращённые наименования бытовой техники (стандарт бюро): на планах — сокращение, расшифровка — в блоке «Сокращения»
ABBR = [('ХЛ', 'холодильник'), ('ПММ', 'посудомоечная машина'), ('ВП', 'варочная панель'), ('ДШ', 'духовой шкаф'),
        ('ВТ', 'вытяжка'), ('МВ', 'микроволновая печь'), ('СМ', 'стиральная машина'), ('СШ', 'сушильная машина'),
        ('К', 'кондиционер, внутренний блок (К1, К2…)'), ('ТВ', 'телевизор')]


def abbr_used(sh):
    """Сокращения, встречающиеся в подписях листа (по словам: «ВП + ДШ», «К1», «ТВ 65"»)."""
    import re as _re
    words = set()
    for it in sh.items:
        if it.get('t') == 'text':
            for w in _re.findall(r'[А-ЯЁ]+', str(it.get('s', ''))):
                words.add(w)
            for w in _re.findall(r'\bК\d', str(it.get('s', ''))):
                words.add('К')
    return [(a, t) for a, t in ABBR if a in words]


def dims_list(sh, v, lst, **kw):
    """Размерные цепочки из данных: [(ось, значения, положение, выносные), ...]."""
    for d in lst:
        axis, vals, at = d[0], d[1], d[2]
        ext = d[3] if len(d) > 3 else None
        extra = dict(kw)
        if len(d) > 4:
            extra.update(d[4])
        mdim(sh, v, axis, vals, at, ext=ext, **extra)


def outer_dims(sh, v):
    dims_list(sh, v, getattr(MV, 'OUTER_DIMS', None) or auto_outer_dims())


def inner_dims(sh, v):
    dims_list(sh, v, getattr(MV, 'INNER_DIMS', None) or auto_inner_dims())


def auto_outer_dims():
    """Наружные размеры (если в obmer.py не заданы OUTER_DIMS): цепочка по стенам и проёмам + общий размер,
    сверху (по y) и слева (по x)."""
    xs = sorted({r[0] for r in D.WALLS} | {r[2] for r in D.WALLS})
    ys = sorted({r[1] for r in D.WALLS} | {r[3] for r in D.WALLS})
    x0, x1, y0, y1 = xs[0], xs[-1], ys[0], ys[-1]
    top = [r for r in D.WALLS if r[0] <= x0 + 1]                 # стены по верхнему краю
    left = [r for r in D.WALLS if r[1] <= y0 + 1]                # стены по левому краю
    ch_y = sorted({v for r in top for v in (r[1], r[3])})
    ch_x = sorted({v for r in left for v in (r[0], r[2])})
    out = []
    if len(ch_y) > 2:
        out.append(('y', ch_y, x0 - 800, x0))
    out.append(('y', [y0, y1], x0 - 1350, x0))
    if len(ch_x) > 2:
        out.append(('x', ch_x, y0 - 800, y0))
    out.append(('x', [x0, x1], y0 - 1350, y0))
    return out


def auto_inner_dims():
    """Внутренние размеры: ширина и длина каждого помещения по габариту (если не заданы INNER_DIMS)."""
    out = []
    for k, r in D.ROOMS.items():
        xs = [p[0] for p in r['poly']]; ys = [p[1] for p in r['poly']]
        out.append(('x', [min(xs), max(xs)], min(ys) + 0.15 * (max(ys) - min(ys)), None))
        out.append(('y', [min(ys), max(ys)], min(xs) + 0.15 * (max(xs) - min(xs)), None))
    return out


# ---------------- мебель ----------------
def _to_model(wall, face, axis, u, w):
    """Локальные координаты предмета у стены: u — от стены внутрь, w — вдоль стены."""
    if wall == 'W':
        return (face + u, axis + w)
    if wall == 'E':
        return (face - u, axis - w)
    if wall == 'S':
        return (axis + w, face + u)
    if wall == 'N':
        return (axis - w, face - u)


to_model = _to_model


def draw_item(pen, it, faint_=False):
    k = it['kind']
    f = faint(F) if faint_ else F
    ft = faint(FT) if faint_ else FT
    e = faint(E) if faint_ else E
    et = faint(ET) if faint_ else ET
    r = it.get('rect')
    if 'pts' in it and r is None:              # предмет произвольного контура (напр. угловой диван в эркере)
        pen.poly(it['pts'], fill=_fc(k, it=it), **f)
        for ln in it.get('lines', []):
            pen.poly(ln, closed=False, **ft)
        return
    if k == 'wardrobe':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **f)
        if it.get('along', 'x') == 'x':
            ym = (y0 + y1) / 2
            pen.line((x0 + 40, ym), (x1 - 40, ym), dash=DASH, **ft)
            x = x0 + 120
            while x < x1 - 80:
                pen.line((x - 30, ym - 160), (x + 30, ym + 160), **ft)
                x += 180
        else:
            xm = (x0 + x1) / 2
            pen.line((xm, y0 + 40), (xm, y1 - 40), dash=DASH, **ft)
            y = y0 + 120
            while y < y1 - 80:
                pen.line((xm - 160, y - 30), (xm + 160, y + 30), **ft)
                y += 180
    elif k == 'bench':
        x0, y0, x1, y1 = r
        pen.poly(rrect_pts(x0, y0, x1, y1, 50), fill=_fc(k, it=it), **f)
        pen.poly(rrect_pts(x0 + 40, y0 + 30, x1 - 40, y1 - 40, 40), **ft)
    elif k == 'wallshelf':
        pen.rect(*r, dash=DASH, **ft)
    elif k == 'console':
        pen.rect(*r, dash=DASH, fill=_fc(k, it=it), **f)
    elif k in ('mirror', 'mirror_round', 'mirror_oval'):
        pen.rect(*r, fill=FILL_LT, **ft)
    elif k == 'column':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **e)
        pen.line((x0, y0), (x1, y1), **et)
        if not faint_ and pen.v.k <= 60:
            lab = it.get('words', it.get('label', '')) if COLORED['words'] else it.get('label', '')
            pen.text(((x0 + x1) / 2, (y0 + y1) / 2), lab, h=1.3 if COLORED['words'] else 1.5, ha='c', va='m',
                     layer='A-TEXT', color=DARK, bg=True)
    elif k == 'filler':
        pen.rect(*r, **et)
    elif k == 'kitchen_run':
        x0, y0, x1, y1 = r
        side = it.get('side', 'W')
        along_y = side in ('W', 'E')            # гарнитур вдоль стены постоянного x (W/E) или y (N/S)
        wx = {'W': x0, 'E': x1, 'S': y0, 'N': y1}[side]          # координата стены
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **e)
        for a, b, kind in it['modules']:
            if COLORED['on'] and kind in ('hob', 'dw', 'sink'):
                rr_ = (x0, a, x1, b) if along_y else (a, y0, b, y1)
                pen.rect(*rr_, fill=PAL['appl'] if kind != 'sink' else PAL['sani'], stroke=False, layer='A-FURN')
            pen.line(*(((x0, a), (x1, a)) if along_y else ((a, y0), (a, y1))), **et)
            cy = (a + b) / 2
            if kind == 'sink':
                hw_ = min(240, (b - a) / 2 - 25)          # чаша в пределах модуля (тумба 450 — чаша 400)
                pts = rrect_pts(80, -hw_, 480, hw_, 50)
                pen.poly([_to_model(side, wx, cy, u, w) for u, w in pts], **e)
                pen.circle(_to_model(side, wx, cy, 280, 0), 30, **et)
                pen.circle(_to_model(side, wx, cy, 45, 0), 22, **et)
            elif kind == 'hob':
                pts = [(40, -280), (560, -280), (560, 280), (40, 280)]
                pen.poly([_to_model(side, wx, cy, u, w) for u, w in pts], **e)
                for u, w, rr in [(175, -135, 95), (175, 135, 75), (425, -135, 75), (425, 135, 95)]:
                    pen.circle(_to_model(side, wx, cy, u, w), rr, **et)
            elif kind == 'dw' and not faint_:
                pen.text(_to_model(side, wx, cy, 300, 0), 'ПММ', h=1.4, ha='c', va='m', layer='A-TEXT', color=DARK)
            if COLORED['words'] and kind == 'hob' and it.get('hob_words'):      # подписи объекта (напр. «+ духовка»)
                hw = it['hob_words']
                for i_, w_ in enumerate(hw):
                    if along_y:                       # гарнитур вдоль y: строки — поперёк (по u)
                        u_ = 300 + (len(hw) - 1) * 75 - i_ * 150
                        pt_ = _to_model(side, wx, cy, u_, 0)
                    else:                             # гарнитур вдоль x: строки — вдоль модуля (по w), сверху вниз
                        w_off = (len(hw) - 1) * 75 - i_ * 150
                        pt_ = _to_model(side, wx, cy, 300, w_off if side == 'N' else -w_off)
                    pen.text(pt_, w_, h=1.25, ha='c', va='m', layer='A-TEXT', color=BLACK, bg=True)
            elif COLORED['words'] and kind == 'hob':
                pen.text(_to_model(side, wx, cy, 300, 0), 'ВП', h=1.4, ha='c', va='m', layer='A-TEXT', color=BLACK, bg=True)
            if COLORED['words'] and kind == 'sink':
                pen.text(_to_model(side, wx, cy, 420, 0), 'мойка', h=1.25, ha='c', va='m', layer='A-TEXT', color=BLACK, bg=True)
            elif kind == 'tech' and not faint_:
                pen.text(_to_model(side, wx, cy, 300, 0), 'тех.', h=1.3, ha='c', va='m', layer='A-TEXT', color=MID)
    elif k == 'upper':
        x0, y0, x1, y1 = r
        side = it.get('side', 'W')
        hy = it.get('hood')
        if side in ('W', 'E'):
            if side == 'W':
                pen.line((x1, y0 + 650), (x1, y1), dash=DASH, **et)
                hx0, hx1 = x0, x0 + 480
            else:
                pen.line((x0, y0 + 650), (x0, y1), dash=DASH, **et)
                hx0, hx1 = x1 - 480, x1
            if hy:
                pen.rect(hx0, hy[0], hx1, hy[1], dash=DASH, **et)     # вытяжка
        else:
            yy = y1 if side == 'S' else y0
            pen.line((x0, yy), (x1, yy), dash=DASH, **et)
            if hy:
                hy0, hy1 = (y0, y0 + 480) if side == 'S' else (y1 - 480, y1)
                pen.rect(hy[0], hy0, hy[1], hy1, dash=DASH, **et)
    elif k == 'table':
        pen.rect(*r, fill=_fc(k, it=it), **f)
    elif k == 'chair':
        c = it['c']
        ang = it['ang']
        w_, d_ = 440, 460
        pts = rrect_pts(-d_ / 2, -w_ / 2, d_ / 2, w_ / 2, 70)
        pen.poly(rot_pts(pts, c[0], c[1], ang), fill=_fc(k, it=it), **f)
        back = [(-d_ / 2 + 70, -w_ / 2 + 30), (-d_ / 2 + 70, w_ / 2 - 30)]
        pen.line(*rot_pts(back, c[0], c[1], ang), **ft)
    elif k == 'sofa':
        x0, y0, x1, y1 = r
        back = it.get('back', 'E')
        pen.poly(rrect_pts(x0, y0, x1, y1, 60), fill=_fc(k, it=it), **f)
        if back in ('E', 'W'):
            bx0, bx1 = (x1 - 220, x1) if back == 'E' else (x0, x0 + 220)
            pen.rect(bx0, y0 + 200, bx1, y1 - 200, fill=FILL_LT, **ft)
            pen.rect(x0, y0, x1, y0 + 200, **ft)
            pen.rect(x0, y1 - 200, x1, y1, **ft)
            sx0, sx1 = (x0, x1 - 220) if back == 'E' else (x0 + 220, x1)
            pen.line((sx0, (y0 + y1) / 2), (sx1, (y0 + y1) / 2), **ft)
        else:
            by0, by1 = (y1 - 220, y1) if back == 'N' else (y0, y0 + 220)
            pen.rect(x0 + 200, by0, x1 - 200, by1, fill=FILL_LT, **ft)
            pen.rect(x0, y0, x0 + 200, y1, **ft)
            pen.rect(x1 - 200, y0, x1, y1, **ft)
    elif k == 'coffee':
        pen.poly(rrect_pts(*r, 40), fill=_fc(k, it=it), **f)
    elif k == 'tvconsole':
        pen.rect(*r, fill=_fc(k, it=it), dash=DASH, **f)
    elif k == 'tv':
        pen.rect(*r, fill=DARK, lw=0.2, layer='A-FURN', color=DARK if not faint_ else FAINT)
    elif k == 'rug':
        pen.rect(*r, dash=(1.0, 0.8), **ft)
    elif k == 'radiator':
        pen.rect(*r, dash=(1.2, 0.8), **ft)
    elif k == 'bed':
        x0, y0, x1, y1 = r
        head = it.get('head', 'S')
        # локальная система: u — от изголовья по длине, w — поперёк
        if head == 'S':
            M = lambda u, w: (x0 + w, y0 + u); Lb, Wb = y1 - y0, x1 - x0
        elif head == 'N':
            M = lambda u, w: (x1 - w, y1 - u); Lb, Wb = y1 - y0, x1 - x0
        elif head == 'W':
            M = lambda u, w: (x0 + u, y1 - w); Lb, Wb = x1 - x0, y1 - y0
        else:
            M = lambda u, w: (x1 - u, y0 + w); Lb, Wb = x1 - x0, y1 - y0
        R = lambda u0, w0, u1, w1: [M(u0, w0), M(u1, w0), M(u1, w1), M(u0, w1)]
        pen.poly(R(0, 0, Lb, Wb), fill=_fc(k, it=it), **f)
        pen.poly(R(0, 0, 80, Wb), fill=FILL_LT, **f)
        mid = Wb / 2
        for w0, w1 in ((80, mid - 30), (mid + 30, Wb - 80)):
            pts = rrect_pts(130, w0, 530, w1, 70)
            pen.poly([M(u, w) for u, w in pts], **ft)
        pen.line(M(700, 0), M(700, Wb), **ft)
        pen.line(M(780, 0), M(780, Wb), **ft)
        pen.line(M(Lb, Wb - 420), M(Lb - 420, Wb), **ft)
    elif k == 'bed_single' and it.get('head', 'N') != 'N':
        # односпальная кровать с изголовьем у стены S / W / E (локальная система: u — от изголовья, w — поперёк)
        x0, y0, x1, y1 = r
        head = it['head']
        if head == 'S':
            M = lambda u, w: (x0 + w, y0 + u); Lb, Wb = y1 - y0, x1 - x0
        elif head == 'W':
            M = lambda u, w: (x0 + u, y1 - w); Lb, Wb = x1 - x0, y1 - y0
        else:
            M = lambda u, w: (x1 - u, y0 + w); Lb, Wb = x1 - x0, y1 - y0
        R_ = lambda u0, w0, u1, w1: [M(u0, w0), M(u1, w0), M(u1, w1), M(u0, w1)]
        pen.poly(R_(0, 0, Lb, Wb), fill=_fc(k, it=it), **f)
        pen.poly(R_(0, 0, 80, Wb), fill=FILL_LT, **f)
        pen.poly([M(u, w) for u, w in rrect_pts(130, 100, 480, Wb - 100, 60)], **ft)
        pen.line(M(650, 0), M(650, Wb), **ft)
        pen.line(M(Lb, Wb - 420), M(Lb - 420, Wb), **ft)
    elif k == 'bed_single':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **f)
        pen.rect(x0, y1 - 80, x1, y1, fill=FILL_LT, **f)
        pen.poly(rrect_pts(x0 + 100, y1 - 480, x1 - 100, y1 - 130, 60), **ft)
        pen.line((x0, y1 - 650), (x1, y1 - 650), **ft)
        pen.line((x1, y0 + 420), (x1 - 420, y0), **ft)
    elif k == 'bath':
        # ванна прямоугольная: борт, чаша, слив (у торца drain='W'|'E'|'S'|'N', по умолчанию — у большего x)
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **e)
        b = 70
        pen.poly(rrect_pts(x0 + b, y0 + b, x1 - b, y1 - b, min(x1 - x0, y1 - y0) / 2 - b), **et)
        dr = it.get('drain', 'E' if (x1 - x0) >= (y1 - y0) else 'N')
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dp = {'E': (x1 - 220, cy), 'W': (x0 + 220, cy), 'N': (cx, y1 - 220), 'S': (cx, y0 + 220)}[dr]
        pen.circle(dp, 30, **et)
    elif k == 'nightstand':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), dash=DASH, **f)
    elif k == 'desk':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **f)
    elif k == 'shelving':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **f)
        for y in range(int(y0) + 500, int(y1), 500):
            pen.line((x0, y), (x1, y), **ft)
    elif k == 'ac':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, dash=(1.6, 0.8), **ft)
        if not faint_ and not COLORED['words']:
            pen.text(((x0 + x1) / 2, (y0 + y1) / 2), it['pos'], h=1.5, ha='c', va='m', layer='A-TEXT', color=DARK)
    elif k == 'lounge':
        x0, y0, x1, y1 = r
        pen.poly(rrect_pts(x0, y0, x1, y1, 80), fill=_fc(k, it=it), **f)
        pen.line((x0 + 40, y0 + 120), (x1 - 40, y0 + 120), **ft)
    elif k == 'round':
        pen.circle(it['c'], it['r'], fill=_fc(k, it=it), **f)
    elif k == 'box':
        pen.rect(*r, fill=FILL_LT, **et)
    elif k == 'wc':
        wall, face, axis = it['wall'], it['face'], it['axis']
        L, W = 540, 360
        pts = [(0, -W / 2), (190, -W / 2)]
        pts += [(190 + (L - 190) * math.cos(math.radians(a)), (W / 2) * math.sin(math.radians(a))) for a in range(-90, 91, 10)]
        pts += [(190, W / 2), (0, W / 2)]
        pen.poly([_to_model(wall, face, axis, u, w) for u, w in pts], fill=_fc(k, it=it), **e)
        inner = [(L * 0.55 + (L * 0.30) * math.cos(math.radians(a)), (W * 0.30) * math.sin(math.radians(a))) for a in range(0, 361, 15)]
        pen.poly([_to_model(wall, face, axis, u, w) for u, w in inner], **et)
    elif k == 'vanity':
        wall, face, axis, width, depth = it['wall'], it['face'], it['axis'], it['width'], it['depth']
        pts = [(0, -width / 2), (depth, -width / 2), (depth, width / 2), (0, width / 2)]
        pen.poly([_to_model(wall, face, axis, u, w) for u, w in pts], fill=_fc(k, it=it), **e)
        rx = min(width * 0.34, 280)
        bas = [(depth * 0.55 + 140 * math.cos(math.radians(a)), rx * math.sin(math.radians(a))) for a in range(0, 361, 12)]
        pen.poly([_to_model(wall, face, axis, u, w) for u, w in bas], **et)
        pen.circle(_to_model(wall, face, axis, 60, 0), 25, **et)
    elif k == 'mini_basin':
        wall, face, axis, width, depth = it['wall'], it['face'], it['axis'], it['width'], it['depth']
        pts = [(0, -width / 2), (depth, -width / 2), (depth, width / 2), (0, width / 2)]
        pen.poly([_to_model(wall, face, axis, u, w) for u, w in pts], fill=_fc(k, it=it), **e)
        bas = [(depth * 0.55 + 80 * math.cos(math.radians(a)), (width * 0.33) * math.sin(math.radians(a))) for a in range(0, 361, 15)]
        pen.poly([_to_model(wall, face, axis, u, w) for u, w in bas], **et)
    elif k == 'wm_cab':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, fill=_fc(k, it=it), **e)
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        pen.circle(c, 210, **et)
        if not faint_ and COLORED['words']:
            w1, w2 = it.get('words', ('СМ', '+ СШ'))
            pen.text((c[0] - 70, c[1]), w1, h=1.2, ha='c', va='m', layer='A-TEXT', color=BLACK, bg=True)
            pen.text((c[0] + 70, c[1]), w2, h=1.2, ha='c', va='m', layer='A-TEXT', color=BLACK, bg=True)
        elif not faint_:
            pen.text(c, it.get('label', 'СМ+СШ'), h=1.3, ha='c', va='m', layer='A-TEXT', color=DARK)
    elif k == 'towel':
        pen.rect(*r, fill=FILL_LT, **et)
    elif k == 'glass':
        pen.rect(*r, fill=DARK if not faint_ else FAINT, lw=0.3, layer='A-EQPM', color=BLACK if not faint_ else FAINT)
    elif k == 'drain':
        x0, y0, x1, y1 = r
        pen.rect(x0, y0, x1, y1, **e)
        for yy in (y0 + 25, y0 + 45):
            pen.line((x0 + 30, yy), (x1 - 30, yy), **et)
    elif k == 'shower':
        cx, cy = it['c']
        nx, ny = it.get('n', (0, 1))              # направление от стены (по умолчанию — от стены постоянного y внутрь +y)
        tx, ty = ny, -nx
        hc = (cx + nx * 140, cy + ny * 140)
        pen.circle(hc, 110, **et)
        pen.line((hc[0] - tx * 110, hc[1] - ty * 110), (hc[0] + tx * 110, hc[1] + ty * 110), **et)
        pen.line((cx + nx * 30, cy + ny * 30), (cx + nx * 250, cy + ny * 250), **et)


def draw_items(pen, rooms=None, faint_=False, skip=()):
    for it in D.ITEMS:
        if rooms and it['room'] not in rooms:
            continue
        if it['kind'] in skip:
            continue
        draw_item(pen, it, faint_=faint_)


def item_center(it):
    if 'rect' in it:
        x0, y0, x1, y1 = it['rect']
        return ((x0 + x1) / 2, (y0 + y1) / 2)
    if 'c' in it:
        return it['c']
    if 'pts' in it:
        return (sum(p[0] for p in it['pts']) / len(it['pts']), sum(p[1] for p in it['pts']) / len(it['pts']))
    if it['kind'] in ('wc', 'vanity', 'mini_basin'):
        wall, face, axis = it['wall'], it['face'], it['axis']
        d = it.get('depth', 540) / 2 + (40 if it['kind'] == 'wc' else 0)
        return _to_model(wall, face, axis, d, 0)
    return (0, 0)


def room_tag(sh, v, p, num_, name, area, h=2.0, small=False):
    from kit import num
    X, Y = v.P(*p)
    lines = [ln for ln in name.split('\n') if ln] if name else []
    a = num(area)
    ha = 2.2 if not small else 1.9
    wa = tw(a, ha, 'BoldObl')
    wn = max([tw(ln, h) for ln in lines] + [wa, 4.6])
    hh = 5.2 + len(lines) * 2.8 + 3.4
    top = Y + hh / 2
    sh.rect(X - wn / 2 - 0.9, top - hh - 0.5, X + wn / 2 + 0.9, top + 0.3, fill=WHITE, stroke=False, layer='A-ZONE')
    cy = top - 2.3
    sh.circle((X, cy), 2.1, lw=0.25, layer='A-TEXT', fill=WHITE)
    sh.text((X, cy), num_, h=1.7, ha='c', va='m', layer='A-TEXT')
    yy = cy - 3.5
    for ln in lines:
        sh.text((X, yy), ln, h=h, ha='c', va='t', layer='A-TEXT')
        yy -= 2.8
    sh.text((X, yy - 0.2), a, h=ha, ha='c', va='t', layer='A-TEXT', font='BoldObl')
    sh.line((X - wa / 2 - 0.4, yy - 2.9), (X + wa / 2 + 0.4, yy - 2.9), lw=0.25, layer='A-TEXT')


def _poly_center(poly):
    """Точка для бирки: центр наибольшего вписанного прямоугольника по сетке (для Г-образных — внутри)."""
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    best, bc = -1, ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    from kit import poly_scan  # noqa
    def inside(px, py):
        c = False
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            if (ya > py) != (yb > py):
                xi = xa + (py - ya) * (xb - xa) / (yb - ya)
                if xi > px:
                    c = not c
        return c
    def dist(px, py):
        d = 1e9
        for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
            ex, ey = xb - xa, yb - ya
            L2 = ex * ex + ey * ey or 1
            t = max(0.0, min(1.0, ((px - xa) * ex + (py - ya) * ey) / L2))
            d = min(d, ((px - xa - t * ex) ** 2 + (py - ya - t * ey) ** 2) ** 0.5)
        return d
    n = 24
    for i in range(1, n):
        for j in range(1, n):
            px = min(xs) + (max(xs) - min(xs)) * i / n
            py = min(ys) + (max(ys) - min(ys)) * j / n
            if inside(px, py):
                d = dist(px, py)
                if d > best:
                    best, bc = d, (round(px / 10) * 10, round(py / 10) * 10)
    return bc


def auto_tag_pos():
    return {k: _poly_center(D.ROOMS[k]['poly']) for k in sorted(D.ROOM)}


def _tag_noname():
    import annot as A
    t = getattr(A, 'TAG_NONAME', None)
    if t is not None:
        return t
    return tuple(k for k in D.ROOM if D.AREA[k] < 2.0 or D.ROOM[k].get('zone') == 'out')


def room_tags(sh, v, pos=None, names=True, small_rooms_noname=True):
    if pos is None:
        import annot as A
        pos = (getattr(A, 'TAGS', {}) or {}).get('default') or auto_tag_pos()
    nn = _tag_noname()
    for k, p in pos.items():
        nm = D.ROOM[k]['name'] if names else ''
        if k in nn and small_rooms_noname:
            nm = ''
        room_tag(sh, v, p, k, nm, D.AREA[k])
