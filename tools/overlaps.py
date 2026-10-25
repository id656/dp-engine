# -*- coding: utf-8 -*-
"""Самопроверка оформления: наложения надписей на листах альбома.

    python3 tools/overlaps.py objects/<объект>            — все листы
    python3 tools/overlaps.py objects/<объект> lgt,swi    — отдельные листы (ключи из build.py --list)

Для каждого листа строятся габариты всех надписей (как их рисует render_pdf: высота, выравнивание, поворот, подложка)
и выводятся пары надписей, перекрывающиеся (с зазором 0,35 мм) более чем на 10 % площади меньшей. Рамка и штамп (A-FRAME) не проверяются,
надписи внутри одной таблицы — тоже (ячейки не пересекаются). Отчёт — в out/overlaps.md."""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


PAD = 0.35          # мм: надписи ближе этого считаются слипшимися («475200»)


def text_box(it, pad=PAD):
    """Габарит надписи на листе: многоугольник (4 точки) как в render_pdf, расширенный на pad."""
    from reportlab.pdfbase import pdfmetrics
    from core import fs
    h = it['h']
    w = pdfmetrics.stringWidth(it['s'], it['font'], fs(h))
    dx = {'l': 0, 'c': -w / 2, 'r': -w}[it['ha']]
    dy = {'b': 0, 'm': -h / 2, 't': -h}[it['va']]
    x0, y0, x1, y1 = dx - pad, dy - pad, dx + w + pad, dy + h + pad
    a = math.radians(it['rot'] or 0)
    ca, sa = math.cos(a), math.sin(a)
    px, py = it['p']
    return [(px + x * ca - y * sa, py + x * sa + y * ca) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def _bbox(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _clip(subject, clip):
    """Пересечение выпуклых многоугольников (Сазерленд — Ходжмен)."""
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-9

    def inter(p, q, a, b):
        x1, y1 = p; x2, y2 = q; x3, y3 = a; x4, y4 = b
        d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(d) < 1e-12:
            return q
        t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    out = subject
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        inp, out = out, []
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


def _area(poly):
    if len(poly) < 3:
        return 0.0
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def _ccw(poly):
    a = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))
    return poly if a > 0 else poly[::-1]


def sheet_overlaps(sh, frac=0.10):
    texts = [it for it in sh.items if it['t'] == 'text' and it['layer'] != 'A-FRAME' and it['s'].strip()]
    boxes = [(_ccw(text_box(it)), it) for it in texts]
    bbs = [_bbox(b) for b, _ in boxes]
    res = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = bbs[i], bbs[j]
            if a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]:
                continue
            pa, ia = boxes[i]
            pb, ib = boxes[j]
            if ia['s'] == ib['s'] and abs(ia['p'][0] - ib['p'][0]) < 0.01 and abs(ia['p'][1] - ib['p'][1]) < 0.01:
                continue                                  # одна и та же надпись дважды (обводка)
            if (ia['rot'] or 0) == (ib['rot'] or 0) and abs(ia['p'][1] - ib['p'][1]) < 0.3 and not ia['rot']:
                pa, pb = _ccw(text_box(ia, 0.0)), _ccw(text_box(ib, 0.0))   # одна строка (номер пункта + текст)
            inter = _area(_clip(pa, pb))
            small = min(_area(pa), _area(pb))
            if small > 0 and inter / small > frac:
                res.append((inter / small, ia, ib))
    return res


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    import build
    build.setup(argv[1])
    import assemble
    only = argv[2].split(',') if len(argv) > 2 else None
    sheets, lst = assemble.build(only)
    out = ['# Наложения надписей', '']
    total = 0
    for sh in sheets:
        ov = sheet_overlaps(sh)
        if not ov:
            continue
        out.append(f'## Лист {sh.no:02d} — {sh.name}')
        for f, a, b in sorted(ov, key=lambda t: -t[0]):
            out.append(f'- {f * 100:.0f} %: «{a["s"]}» ({a["p"][0]:.0f}, {a["p"][1]:.0f}) × «{b["s"]}» ({b["p"][0]:.0f}, {b["p"][1]:.0f})')
            total += 1
        out.append('')
    out.append(f'Итого наложений: {total}')
    import paths
    with open(os.path.join(paths.OUT, 'overlaps.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
