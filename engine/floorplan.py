# -*- coding: utf-8 -*-
"""Планы раскладки плитки пола санузлов (М 1:25)."""
import math
from core import View, Pen, mdim, tw, BLACK, DARK, MID, LIGHT, WHITE, WALLFILL
import model as D
import drawplan as DP
from kit import clip_seg_rect, section_title, level_box
from core import wall_union_edges

TILE_C = (0.40, 0.40, 0.40)


def wet_floor_extra(room):
    """Доп. элементы раскладки пола помещения: album.WET_FLOOR[room] (уклоны, размеры, отметки, подписи)."""
    try:
        import album as AL
        return getattr(AL, 'WET_FLOOR', {}).get(room, {})
    except ImportError:
        return {}


def wet_floor(sh, room, X, Y, k=25.0, title=True):
    poly = D.ROOMS[room]['poly']
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    # вид как на основных планах: y -> вправо, x -> вниз; (X, Y) — левый верхний угол помещения
    v = View(X - y0 / k, Y + x0 / k, k)
    pen = Pen(sh, v)
    clipr = (x0 - 220, y0 - 220, x1 + 220, y1 + 220)
    for r in D.WALLS:
        a0 = max(r[0], clipr[0]); b0 = max(r[1], clipr[1]); a1 = min(r[2], clipr[2]); b1 = min(r[3], clipr[3])
        if a1 > a0 and b1 > b0:
            pen.rect(a0, b0, a1, b1, fill=WALLFILL, stroke=False, layer='A-WALL-FILL')
    for a, b in wall_union_edges(D.WALLS):
        c = clip_seg_rect(a, b, clipr)
        if c:
            pen.line(c[0], c[1], lw=0.5, layer='A-WALL')
    pen.poly(poly, fill=(0.97, 0.96, 0.93), lw=0.1, layer='A-FLOOR', color=MID)
    # плитка
    import plans as PL
    for r_, ppoly, a, b, ox, oy in D.FLOOR_TILES:
        if r_ == room:
            PL.tile_grid(sh, v, ppoly, a, b, ox, oy, color=TILE_C, lw=0.15)
    for it in D.ITEMS:
        if it['room'] == room and it['kind'] not in ('mirror', 'mirror_oval', 'towel', 'wallshelf', 'shower'):
            DP.draw_item(pen, it, faint_=it['kind'] not in ('box', 'drain', 'glass'))
    E = wet_floor_extra(room)
    if E.get('shaft') and D.SHAFT:
        pen.rect(*D.SHAFT, lw=0.25, layer='A-HATCH')
    # уклоны к трапу
    for a_, b_ in E.get('slopes', []):
        a = v.P(*a_); b = v.P(*b_)
        sh.line(a, b, lw=0.25, layer='A-FLOOR', color=(0.1, 0.35, 0.7))
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        sh.poly([b, (b[0] - 1.6 * math.cos(ang - 0.4), b[1] - 1.6 * math.sin(ang - 0.4)),
                 (b[0] - 1.6 * math.cos(ang + 0.4), b[1] - 1.6 * math.sin(ang + 0.4))], layer='A-FLOOR',
                fill=(0.1, 0.35, 0.7), color=(0.1, 0.35, 0.7), lw=0.1)
    if E.get('slope_text'):
        P = v.P(*E['slope_text'][0])
        sh.text(P, E['slope_text'][1], h=1.7, ha='c', va='m', layer='A-TEXT', color=(0.1, 0.35, 0.7), bg=True)
    for d in E.get('dims', []):
        mdim(sh, v, d[0], d[1], d[2], ext=d[3] if len(d) > 3 else None, h=2.0)
    for p_, t_ in E.get('levels', []):
        level_box(sh, v.P(*p_), t_)
    for p_, t_, dx, dy in E.get('texts', []):
        P = v.P(*p_)
        sh.text((P[0] + dx, P[1] + dy), t_, h=1.6, layer='A-TEXT', bg=True)
    if title:
        tx = X
        ty = Y + (x0 - x0) / k + 9
        section_title(sh, tx, Y + 18, f"Раскладка плитки пола ({D.ROOM[room]['floor']}), пом. {room}", f'М 1:{int(k)}', h=2.5)
    return v
