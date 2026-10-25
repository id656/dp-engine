# -*- coding: utf-8 -*-
"""Вспомогательные построения: штриховки, отсечение, таблицы, тексты, рамка/основная надпись."""
import math
import os
import paths as _paths
from core import tw, BLACK, DARK, MID, LIGHT, WHITE

def _project():
    """Паспорт объекта = настройки бюро (bureau/bureau.py) + объект (objects/<объект>/project.py)."""
    import sys
    sys.path.insert(0, _paths.BUREAU)
    try:
        from bureau import BUREAU
    finally:
        sys.path.remove(_paths.BUREAU)
    import project as _prj
    d = dict(BUREAU)
    d.update(_prj.PROJECT)
    return d


PROJECT = _project()


# ---------------- геометрия ----------------
def poly_scan(pts, angle_deg, spacing, offset=0.0):
    """Параллельные линии внутри многоугольника (любой формы). Возвращает список отрезков."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    # поворот на -angle: линии становятся горизонтальными
    rp = [(x * ca + y * sa, -x * sa + y * ca) for x, y in pts]
    ys = [p[1] for p in rp]
    y0, y1 = min(ys), max(ys)
    segs = []
    n0 = math.floor((y0 - offset) / spacing)
    n1 = math.ceil((y1 - offset) / spacing)
    for k in range(n0, n1 + 1):
        yy = offset + k * spacing
        if yy <= y0 or yy >= y1:
            continue
        xs = []
        for (xa, ya), (xb, yb) in zip(rp, rp[1:] + rp[:1]):
            if (ya <= yy < yb) or (yb <= yy < ya):
                t = (yy - ya) / (yb - ya)
                xs.append(xa + t * (xb - xa))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            u0, u1 = xs[i], xs[i + 1]
            if u1 - u0 < 1e-6:
                continue
            p0 = (u0 * ca - yy * sa, u0 * sa + yy * ca)
            p1 = (u1 * ca - yy * sa, u1 * sa + yy * ca)
            segs.append((p0, p1))
    return segs


def clip_poly_convex(subject, clip):
    """Сазерленд–Ходжман: отсечение многоугольника выпуклым многоугольником (обход против часовой)."""
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

    def inter(p, q, a, b):
        x1, y1 = p; x2, y2 = q; x3, y3 = a; x4, y4 = b
        den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(den) < 1e-12:
            return q
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))

    out = list(subject)
    for a, b in zip(clip, clip[1:] + clip[:1]):
        inp = out
        out = []
        if not inp:
            break
        s = inp[-1]
        for e in inp:
            if inside(e, a, b):
                if not inside(s, a, b):
                    out.append(inter(s, e, a, b))
                out.append(e)
            elif inside(s, a, b):
                out.append(inter(s, e, a, b))
            s = e
    return out


def clip_seg_rect(p, q, r):
    """Отсечение отрезка прямоугольником r=(x0,y0,x1,y1) (Лианг–Барски)."""
    x0, y0, x1, y1 = r
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if abs(pp) < 1e-12:
            if qq < 0:
                return None
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    if t0 > t1:
        return None
    return ((p[0] + t0 * dx, p[1] + t0 * dy), (p[0] + t1 * dx, p[1] + t1 * dy))


def subtract_intervals(base, cuts):
    """base=(a,b), cuts=[(c,d)...] -> список оставшихся интервалов."""
    res = [base]
    for c, d in cuts:
        nr = []
        for a, b in res:
            if d <= a or c >= b:
                nr.append((a, b))
            else:
                if c > a:
                    nr.append((a, c))
                if d < b:
                    nr.append((d, b))
        res = nr
    return [(a, b) for a, b in res if b - a > 1e-6]


def rect_minus(r, holes):
    """Прямоугольник минус прямоугольники -> список непересекающихся прямоугольников (по полосам)."""
    x0, y0, x1, y1 = r
    ys = sorted({y0, y1} | {h[1] for h in holes if y0 < h[1] < y1} | {h[3] for h in holes if y0 < h[3] < y1})
    out = []
    for ya, yb in zip(ys, ys[1:]):
        ym = (ya + yb) / 2
        cuts = [(h[0], h[2]) for h in holes if h[1] <= ym <= h[3]]
        for a, b in subtract_intervals((x0, x1), cuts):
            out.append((a, ya, b, yb))
    return out


def area_rects(rs):
    return sum((r[2] - r[0]) * (r[3] - r[1]) for r in rs)


# ---------------- оформление ----------------
def num(v, d=1):
    return f'{v:.{d}f}'.replace('.', ',')


def AREA_DEC():
    """Знаков после запятой для площадей в экспликациях: project.PROJECT['area_dec'] (по умолчанию 1)."""
    return PROJECT.get('area_dec', 1)


def lvl(v):
    """Отметка в метрах: +0,020 / ±0,000 / −0,050."""
    if abs(v) < 0.5:
        return '±0,000'
    s = f'{abs(v) / 1000:.3f}'.replace('.', ',')
    return ('+' if v > 0 else '−') + s


def wrap(s, width, h, font='Obl'):
    out = []
    for para in s.split('\n'):
        words = para.split(' ')
        cur = ''
        for w_ in words:
            test = (cur + ' ' + w_).strip()
            if tw(test, h, font) <= width:
                cur = test
            else:
                if cur:
                    out.append(cur)
                cur = w_
        out.append(cur)
    return out


def text_block(sh, x, y, width, s, h=2.2, lead=3.3, font='Obl', layer='A-TEXT', color=BLACK):
    for ln in wrap(s, width, h, font):
        sh.text((x, y), ln, h=h, font=font, layer=layer, color=color)
        y -= lead
    return y


def notes(sh, x, y, width, title, items, h=2.1, lead=3.15, numbered=True, title_h=2.6):
    if title:
        sh.text((x, y), title, h=title_h, layer='A-TEXT', font='BoldObl')
        y -= title_h + 2.2
    for i, it in enumerate(items, 1):
        pre = f'{i}. ' if numbered else '— '
        ind = tw(pre, h)
        lines = wrap(it, width - ind, h)
        sh.text((x, y), pre, h=h, layer='A-TEXT')
        for ln in lines:
            sh.text((x + ind, y), ln, h=h, layer='A-TEXT')
            y -= lead
        y -= 0.6
    return y


def table(sh, x, ytop, cols, header, rows, row_h=5.0, head_h=8.0, h=2.0, aligns=None, title=None,
          title_h=2.8, wraps=None, head_font='Obl', min_row_h=None):
    """Таблица. rows — списки строк; ячейка может переноситься (wraps[i]=True). Возвращает низ таблицы."""
    L = 'A-TEXT'
    W = sum(cols)
    if title:
        sh.text((x + W / 2, ytop + 2.0), title, h=title_h, ha='c', va='b', layer=L, font='BoldObl')
    aligns = aligns or ['c'] * len(cols)
    wraps = wraps or [False] * len(cols)
    # высоты строк с учётом переносов
    lines_rows = []
    hs = []
    for r in rows:
        cells = []
        nmax = 1
        imgh = 0.0
        for w, t, wr in zip(cols, r, wraps):
            if isinstance(t, dict):          # ячейка-изображение: dict(img=path, w=мм, h=мм)
                cells.append((t, False))
                imgh = max(imgh, t.get('h', w - 2) + 1.6)
                continue
            bold = isinstance(t, str) and t.startswith('**')
            tt = t.strip('*') if isinstance(t, str) else str(t)
            lines = wrap(tt, w - 2.0, h) if wr else [tt]
            cells.append((lines, bold))
            nmax = max(nmax, len(lines))
        lines_rows.append(cells)
        hs.append(max(row_h, nmax * (h + 1.1) + 1.6, imgh))
    ybot = ytop - head_h - sum(hs)
    sh.rect(x, ybot, x + W, ytop, lw=0.5, layer=L)
    sh.line((x, ytop - head_h), (x + W, ytop - head_h), lw=0.5, layer=L)
    xx = x
    for w in cols[:-1]:
        xx += w
        sh.line((xx, ybot), (xx, ytop), lw=0.35, layer=L)
    y = ytop - head_h
    for hh in hs[:-1]:
        y -= hh
        sh.line((x, y), (x + W, y), lw=0.18, layer=L)
    xx = x
    for w, t in zip(cols, header):
        lines = t.split('\n')
        yc = ytop - head_h / 2 + (len(lines) - 1) * 1.35
        for ln in lines:
            sh.text((xx + w / 2, yc), ln, h=1.8, ha='c', va='m', layer=L, font=head_font)
            yc -= 2.7
        xx += w
    y = ytop - head_h
    for cells, hh in zip(lines_rows, hs):
        xx = x
        for w, (lines, bold), a in zip(cols, cells, aligns):
            if isinstance(lines, dict):
                iw, ih = lines.get('w', w - 2), lines.get('h', w - 2)
                ix, iy = xx + (w - iw) / 2, y - hh / 2 - ih / 2
                sh.image(lines['img'], ix, iy, iw, ih)
                sh.rect(ix, iy, ix + iw, iy + ih, lw=0.18, layer=L)
                xx += w
                continue
            n = len(lines)
            yc = y - hh / 2 + (n - 1) * (h + 1.1) / 2
            for ln in lines:
                f = 'BoldObl' if bold else 'Obl'
                if a == 'l':
                    sh.text((xx + 1.0, yc), ln, h=h, va='m', layer=L, font=f)
                elif a == 'r':
                    sh.text((xx + w - 1.0, yc), ln, h=h, ha='r', va='m', layer=L, font=f)
                else:
                    sh.text((xx + w / 2, yc), ln, h=h, ha='c', va='m', layer=L, font=f)
                yc -= h + 1.1
            xx += w
        y -= hh
    return ybot


def table_height(cols, rows, row_h=5.0, head_h=8.0, h=2.0, wraps=None):
    wraps = wraps or [False] * len(cols)
    tot = head_h
    for r in rows:
        nmax = 1
        imgh = 0.0
        for w, t, wr in zip(cols, r, wraps):
            if isinstance(t, dict):
                imgh = max(imgh, t.get('h', w - 2) + 1.6)
                continue
            tt = t.strip('*') if isinstance(t, str) else str(t)
            if wr:
                nmax = max(nmax, len(wrap(tt, w - 2.0, h)))
        tot += max(row_h, nmax * (h + 1.1) + 1.6, imgh)
    return tot


def frame(sh, sheet_no, total, sheet_title, fmt='А3'):
    """Рамка и основная надпись по образцу бюро: 185×30, шрифт чертёжный, логотип PORTFOLIO."""
    P = PROJECT
    L = 'A-FRAME'
    F = 'GOST'
    sh.rect(20, 5, 415, 292, lw=0.7, layer=L)
    x0, y0 = 230.0, 5.0
    xm, xr = x0 + 65, x0 + 135
    sh.rect(x0, y0, 415, y0 + 30, lw=0.7, fill=(1, 1, 1), layer=L)
    # левый блок: 4 графы × 6 строк по 5 мм
    for dx in (20, 40, 55):
        sh.line((x0 + dx, y0), (x0 + dx, y0 + 30), lw=0.35, layer=L)
    for k in range(1, 6):
        sh.line((x0, y0 + 5 * k), (xm, y0 + 5 * k), lw=0.35 if k != 3 else 0.5, layer=L)
    sh.line((xm, y0), (xm, y0 + 30), lw=0.7, layer=L)
    sh.line((xr, y0), (xr, y0 + 30), lw=0.7, layer=L)
    sh.line((xm, y0 + 15), (415, y0 + 15), lw=0.7, layer=L)
    # Стадия / Лист / Листов
    sh.line((xr, y0 + 25), (415, y0 + 25), lw=0.35, layer=L)
    for dx in (15, 30):
        sh.line((xr + dx, y0 + 15), (xr + dx, y0 + 30), lw=0.35, layer=L)
    for t, cx in (('Стадия', xr + 7.5), ('Лист', xr + 22.5), ('Листов', xr + 40)):
        sh.text((cx, y0 + 27.5), t, h=2.3, ha='c', va='m', layer=L, font=F)
    sh.text((xr + 7.5, y0 + 20), P['stage'], h=2.8, ha='c', va='m', layer=L, font=F)
    sh.text((xr + 22.5, y0 + 20), f'{sheet_no:02d}', h=2.8, ha='c', va='m', layer=L, font=F)
    sh.text((xr + 40, y0 + 20), str(total), h=2.8, ha='c', va='m', layer=L, font=F)
    # разработчики
    for row, (a, b) in ((1, ('Дизайнер', P['designer'])), (0, ('Чертил', P['drafter']))):
        yy = y0 + 2.5 + 5 * row
        sh.text((x0 + 10, yy), a, h=2.3, ha='c', va='m', layer=L, font=F)
        sh.text((x0 + 30, yy), b, h=2.0, ha='c', va='m', layer=L, font=F)
    # объект и наименование листа
    ol = P['object_lines']
    for i, ln in enumerate(ol):
        sh.text((xm + 35, y0 + 22.5 + (len(ol) - 1) * 1.9 - i * 3.8), ln, h=2.5, ha='c', va='m', layer=L, font=F)
    lines = sheet_title.split('\n')
    step = 3.8 if len(lines) <= 2 else 3.1
    hh = 2.5 if len(lines) <= 2 else 2.2
    yy = y0 + 7.5 + (len(lines) - 1) * step / 2
    for ln in lines:
        sh.text((xm + 35, yy), ln, h=hh, ha='c', va='m', layer=L, font=F)
        yy -= step
    # логотип бюро
    lh = 13.0
    lw_ = lh * P.get('logo_aspect', 2484 / 1197)
    sh.image(P['logo'], xr + 25 - lw_ / 2, y0 + 1.0, lw_, lh)
    sh.text((415, 2.0), f'Формат {fmt}', h=1.8, ha='r', va='m', layer=L, font=F)


def legend_box(sh, x, y, items, width=34, title='Условные обозначения', h=1.9, sym_w=8):
    """items: [(drawfn(sh, cx, cy) | None, text)]. Возвращает низ."""
    if title:
        lines = wrap(title, width + sym_w, 2.4, 'BoldObl')
        for ln in lines:
            sh.text((x, y), ln, h=2.4, layer='A-TEXT', font='BoldObl')
            y -= 3.4
        y -= 2.2
    for fn, txt in items:
        lines = wrap(txt, width, h)
        if fn:
            fn(sh, x + sym_w / 2, y)
        yy = y
        for ln in lines:
            sh.text((x + sym_w + 1.5, yy), ln, h=h, va='m', layer='A-TEXT')
            yy -= h + 0.9
        y = yy - 2.6
    return y


def leader(sh, p_from, p_to, txt, h=2.0, ha='l', layer='A-TEXT', shelf=True, dot=True):
    """Выноска: точка на объекте -> полка с текстом."""
    if dot:
        sh.circle(p_from, 0.45, lw=0.1, layer=layer, fill=BLACK)
    sh.line(p_from, p_to, lw=0.18, layer=layer)
    w = tw(txt, h)
    if ha == 'l':
        if shelf:
            sh.line(p_to, (p_to[0] + w + 1.0, p_to[1]), lw=0.18, layer=layer)
        sh.text((p_to[0] + 0.5, p_to[1] + 0.6), txt, h=h, layer=layer)
    else:
        if shelf:
            sh.line(p_to, (p_to[0] - w - 1.0, p_to[1]), lw=0.18, layer=layer)
        sh.text((p_to[0] - 0.5, p_to[1] + 0.6), txt, h=h, ha='r', layer=layer)


def bubble(sh, c, s, r=2.1, h=1.7, layer='A-TEXT', fill=WHITE, lw=0.25):
    sh.circle(c, r, lw=lw, layer=layer, fill=fill)
    sh.text(c, s, h=h, ha='c', va='m', layer=layer)


def section_title(sh, x, y, txt, scale=None, h=3.0, underline=True):
    full = txt + (f'  {scale}' if scale else '')
    sh.text((x, y), full, h=h, layer='A-TEXT', font='BoldObl')
    if underline:
        w = tw(full, h, 'BoldObl')
        sh.line((x, y - 1.0), (x + w, y - 1.0), lw=0.35, layer='A-TEXT')


def level_box(sh, p, txt, h=1.8, layer='A-TEXT'):
    """Отметка уровня на плане — в прямоугольнике (ГОСТ Р 21.101-2020, рис. 6)."""
    X, Y = p
    w = tw(txt, h) + 1.8
    sh.rect(X - w / 2, Y - h / 2 - 1.0, X + w / 2, Y + h / 2 + 1.0, fill=WHITE, lw=0.25, layer=layer)
    sh.text((X, Y), txt, h=h, ha='c', va='m', layer=layer)


def mask_draw(sh, v, m, color, fill, hatch_ang=30, hatch_sp=1.6, lw=0.4):
    """Зона по растровой маске (клетки): заливка + штриховка по строкам + контур по границе клеток."""
    x0, y0, c, cells = m['x0'], m['y0'], m['cell'], m['cells']
    # прямоугольники по столбцам i (вдоль y — сливаем соседние клетки)
    cols = {}
    for (i, j) in cells:
        cols.setdefault(i, []).append(j)
    rects = []
    for i, js in cols.items():
        js.sort()
        a = js[0]; prev = a
        for j in js[1:] + [None]:
            if j is None or j != prev + 1:
                rects.append((i, a, prev))
                if j is not None:
                    a = j
            if j is not None:
                prev = j
    # слить одинаковые соседние столбцы
    rects.sort()
    merged = []
    for (i, a, b) in rects:
        if merged and merged[-1][1] == i - 1 + 0 and merged[-1][2] == a and merged[-1][3] == b:
            mi0, mi1, ma, mb = merged[-1]
            merged[-1] = (mi0, i, ma, mb)
        else:
            merged.append((i, i, a, b))
    for (i0, i1, a, b) in merged:
        X0, Y0, X1, Y1 = x0 + i0 * c, y0 + a * c, x0 + (i1 + 1) * c, y0 + (b + 1) * c
        pts = [v.P(X0, Y0), v.P(X1, Y0), v.P(X1, Y1), v.P(X0, Y1)]
        sh.poly(pts, stroke=False, fill=fill, layer='A-HEAT')
    # штриховка: глобальные параллельные линии, отсечённые по прямоугольникам
    for (i0, i1, a, b) in merged:
        X0, Y0, X1, Y1 = x0 + i0 * c, y0 + a * c, x0 + (i1 + 1) * c, y0 + (b + 1) * c
        pts = [v.P(X0, Y0), v.P(X1, Y0), v.P(X1, Y1), v.P(X0, Y1)]
        for p, q in poly_scan(pts, hatch_ang, hatch_sp, offset=0.0):
            sh.line(p, q, lw=0.12, layer='A-HEAT', color=color)
    # контур
    edges = []
    for (i, j) in cells:
        for di, dj, e in ((-1, 0, ((i, j), (i, j + 1))), (1, 0, ((i + 1, j), (i + 1, j + 1))),
                          (0, -1, ((i, j), (i + 1, j))), (0, 1, ((i, j + 1), (i + 1, j + 1)))):
            if (i + di, j + dj) not in cells:
                edges.append(e)
    for (a, b) in edges:
        sh.line(v.P(x0 + a[0] * c, y0 + a[1] * c), v.P(x0 + b[0] * c, y0 + b[1] * c), lw=lw, layer='A-HEAT', color=color)
    return merged


def mask_center(m):
    """Точка внутри маски, ближайшая к её центру тяжести (для датчика пола)."""
    cells = m['cells']
    ci = sum(i for i, j in cells) / len(cells)
    cj = sum(j for i, j in cells) / len(cells)
    i, j = min(cells, key=lambda t: (t[0] - ci) ** 2 + (t[1] - cj) ** 2)
    return (m['x0'] + (i + 0.5) * m['cell'], m['y0'] + (j + 0.5) * m['cell'])
