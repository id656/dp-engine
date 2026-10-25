# -*- coding: utf-8 -*-
"""Группировка точек на стенах (рамки, совмещённые выводы) и автоматические привязки вдоль стен."""
from core import mdim, tw
import model as D
import symbols as SY


def wall_key(P):
    n = P['n']
    x, y = P['p']
    if n[0] != 0:
        return (P['room'], 'x', round(x), n)
    return (P['room'], 'y', round(y), n)


def along(P):
    n = P['n']
    return P['p'][1] if n[0] != 0 else P['p'][0]


def clusters(points, gap=160):
    groups = {}
    for P in points:
        groups.setdefault(wall_key(P), []).append(P)
    out = []
    for k, lst in groups.items():
        lst = sorted(lst, key=along)
        cur = [lst[0]]
        for P in lst[1:]:
            if along(P) - along(cur[-1]) < gap:
                cur.append(P)
            else:
                out.append((k, cur))
                cur = [P]
        out.append((k, cur))
    return out


_LABEL_BOXES = []


def _free(bx, by):
    return all(bx[1] < q[0] or bx[0] > q[1] or by[1] < q[2] or by[0] > q[3] for q in _LABEL_BOXES)


def _place(sh, N, base_pt, along_c, lab, label_h, font, color, d0, step_d):
    """Подпись по нормали N от base_pt (по нормали) и along_c (по касательной); уходит дальше при наложении."""
    w = tw(lab, label_h, font) + 0.6
    for step in range(10):
        d = d0 + step * step_d
        if abs(N[0]) > 0.5:
            x0 = base_pt[0] + N[0] * d
            bx = (x0, x0 + w) if N[0] > 0 else (x0 - w, x0)
            by = (along_c - label_h / 2 - 0.3, along_c + label_h / 2 + 0.3)
        else:
            y0 = base_pt[1] + N[1] * d
            bx = (along_c - w / 2, along_c + w / 2)
            by = (y0, y0 + label_h) if N[1] > 0 else (y0 - label_h, y0)
        if _free(bx, by):
            break
    _LABEL_BOXES.append((bx[0], bx[1], by[0], by[1]))
    if abs(N[0]) > 0.5:
        sh.text((x0, along_c), lab, h=label_h, ha='l' if N[0] > 0 else 'r', va='m', layer='A-TEXT', bg=True,
                font=font, color=color)
        return abs(bx[1] - bx[0]) + d
    sh.text((along_c, y0), lab, h=label_h, ha='c', va='b' if N[1] > 0 else 't', layer='A-TEXT', bg=True,
            font=font, color=color)
    return label_h + d


LABEL_GAP = 0.6       # зазор между подписями одной рамки по нормали (мм); объект может увеличить (подложки не перекрываются)


def draw_clusters(sh, v, points, drawfn, labelfn, spacing=3.2, gap=160, label_h=1.4, colorfn=None, framefn=None,
                  merge_same=True, obstacles=None):
    """drawfn(sh, P_sheet, N_sheet, point) -> tip; labelfn(point) -> текст или '';
    framefn(cluster) -> подпись рамки (высота) или ''. Одинаковые подписи постов одной рамки — одна подпись."""
    _LABEL_BOXES.clear()
    _LABEL_BOXES.extend(obstacles or [])
    from core import BLACK
    font = 'BoldObl' if label_h > 1.5 else 'Obl'
    for k, cl in clusters(points, gap):
        n = cl[0]['n']
        N = SY.sheet_normal(n)
        T = (-N[1], N[0])
        cx = sum(P['p'][0] for P in cl) / len(cl)
        cy = sum(P['p'][1] for P in cl) / len(cl)
        C = v.P(cx, cy)
        m = len(cl)
        cl_sorted = sorted(cl, key=lambda P: (v.P(*P['p'])[0] - C[0]) * T[0] + (v.P(*P['p'])[1] - C[1]) * T[1])
        placed = []
        for i, P in enumerate(cl_sorted):
            off = (i - (m - 1) / 2) * spacing
            Ps = (C[0] + T[0] * off, C[1] + T[1] * off)
            if m == 1:
                Ps = v.P(*P['p'])
            tip = drawfn(sh, Ps, N, P)
            placed.append((i, P, Ps, tip))
        dmax = max((tp[0] - Ps[0]) * N[0] + (tp[1] - Ps[1]) * N[1] for _, _, Ps, tp in placed)
        labs = [labelfn(P) for _, P, _, _ in placed]
        horiz = abs(N[0]) > 0.5
        reach = 0.0
        if merge_same and m > 1 and labs and all(l_ == labs[0] for l_ in labs) and labs[0]:
            base = (C[0] + N[0] * dmax, C[1] + N[1] * dmax)
            col = colorfn(placed[0][1]) if colorfn else BLACK
            reach = _place(sh, N, base, C[1] if horiz else C[0], labs[0], label_h, font, col, 1.0, label_h + 0.6)
        else:
            for (i, P, Ps, tip), lab in zip(placed, labs):
                if not lab:
                    continue
                base = (Ps[0] + N[0] * dmax, Ps[1] + N[1] * dmax)
                col = colorfn(P) if colorfn else BLACK
                d0 = 1.0 if horiz else 1.2 + ((label_h + LABEL_GAP) if (m > 1 and i % 2 == 1 and len(lab) >= 3) else 0.0)
                r_ = _place(sh, N, base, Ps[1] if horiz else Ps[0], lab, label_h, font, col, d0,
                            1.2 if horiz else label_h + LABEL_GAP)
                reach = max(reach, r_)
        if framefn:
            fl = framefn(cl)
            if fl:
                base = (C[0] + N[0] * dmax, C[1] + N[1] * dmax)
                if horiz:
                    _place(sh, N, base, C[1], fl, label_h * 0.9, 'Obl', BLACK, reach + 1.2, 1.2)
                else:
                    _place(sh, N, base, C[0], fl, label_h * 0.9, 'Obl', BLACK, reach + LABEL_GAP, label_h + LABEL_GAP)


def room_edge_for(room, key):
    """Ребро многоугольника помещения на линии стены key -> (a, b) вдоль стены."""
    _, axis, coord, n = key
    poly = D.ROOMS[room]['poly']
    best = None
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if axis == 'x' and x0 == x1 and abs(x0 - coord) < 6:
            seg = (min(y0, y1), max(y0, y1))
        elif axis == 'y' and y0 == y1 and abs(y0 - coord) < 6:
            seg = (min(x0, x1), max(x0, x1))
        else:
            continue
        best = seg if best is None else (min(best[0], seg[0]), max(best[1], seg[1]))
    return best


def auto_wall_dims(sh, v, points, off=600, extra=None, skip_rooms=(), offs=None, skip_keys=()):
    groups = {}
    for P in points:
        if P['room'] in skip_rooms:
            continue
        groups.setdefault(wall_key(P), []).append(P)
    base_off = off
    for key, lst in groups.items():
        if key in skip_keys:
            continue
        off = (offs or {}).get(key, base_off)
        room, axis, coord, n = key
        edge = room_edge_for(room, key)
        vals = sorted({round(along(P)) for P in lst})
        if edge:
            vals = sorted(set([edge[0], edge[1]] + vals))
        if extra and key in extra:
            vals = sorted(set(vals + extra[key]))
        if len(vals) < 2:
            continue
        if axis == 'x':
            at = coord + n[0] * off
            mdim(sh, v, 'y', vals, at, ext=coord)
        else:
            at = coord + n[1] * off
            mdim(sh, v, 'x', vals, at, ext=coord)
