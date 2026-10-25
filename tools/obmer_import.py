# -*- coding: utf-8 -*-
"""Оцифровка обмерного плана: PDF (векторный/скан) или DXF -> черновик obmer.py (WALLS, ROOMS) + превью + тексты.

    python3 tools/obmer_import.py plan.pdf --scale 50 [--page 1] [--rotate 90] [--out папка]
    python3 tools/obmer_import.py plan.dxf [--rotate 90]

Принцип (PDF): страница растрируется (1 px = 5 мм модели), стены — залитые/тёмные области толще 60 мм
(тонкие линии размеров и тексты отсекаются морфологией), стены разбиваются на прямоугольники, помещения —
связные области внутри наружного контура. Тексты (размеры, высоты, подписи) выгружаются с координатами.
Результат — ЧЕРНОВИК: обязательно сверить с размерами обмера (превью с сеткой 1 м) и поправить руками.
Координаты — в системе движка: x — вниз по листу, y — вправо; --rotate 90 поворачивает план по часовой
(чтобы длинная сторона шла по y)."""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MPP = 5.0          # мм модели на пиксель


def raster_pdf(path, page, scale, out):
    """Растр страницы так, чтобы 1 px = MPP мм модели (масштаб 1:scale)."""
    dpi = 25.4 * scale / MPP
    base = os.path.join(out, '_page')
    subprocess.run(['pdftoppm', '-r', f'{dpi:.2f}', '-f', str(page), '-l', str(page), '-png', '-singlefile', path, base],
                   check=True)
    return np.asarray(Image.open(base + '.png').convert('RGB')), dpi


def words_pdf(path, page, scale):
    try:
        import pdfplumber
    except ImportError:
        return []
    pdf = pdfplumber.open(path)
    pg = pdf.pages[page - 1]
    k = 25.4 / 72 * scale        # pt -> мм модели
    out = []
    for w in pg.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=['size']):
        out.append(dict(text=w['text'], u=(w['x0'] + w['x1']) / 2 * k, v=(w['top'] + w['bottom']) / 2 * k, size=w['size']))
    return out


def read_dxf(path):
    """Минимальный разбор ASCII DXF: LINE, LWPOLYLINE, TEXT/MTEXT (единицы — мм)."""
    lines = open(path, encoding='utf-8', errors='ignore').read().splitlines()
    pairs = [(lines[i].strip(), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]
    segs, texts = [], []
    ent, cur = None, {}

    def flush():
        if ent == 'LINE' and all(k in cur for k in ('10', '20', '11', '21')):
            segs.append((float(cur['10']), float(cur['20']), float(cur['11']), float(cur['21'])))
        elif ent == 'LWPOLYLINE' and cur.get('pts'):
            pts = cur['pts']
            closed = int(cur.get('70', '0')) & 1
            for a, b in zip(pts, pts[1:] + (pts[:1] if closed else [])):
                segs.append((a[0], a[1], b[0], b[1]))
        elif ent in ('TEXT', 'MTEXT') and '10' in cur:
            texts.append(dict(text=cur.get('1', ''), x=float(cur['10']), y=float(cur['20'])))
    in_ent = False
    for code, val in pairs:
        if code == '0':
            if in_ent:
                flush()
            ent, cur, in_ent = val, {}, val in ('LINE', 'LWPOLYLINE', 'TEXT', 'MTEXT')
            continue
        if not in_ent:
            continue
        if ent == 'LWPOLYLINE' and code in ('10', '20'):
            cur.setdefault('pts', [])
            if code == '10':
                cur['pts'].append([float(val), None])
            elif cur['pts']:
                cur['pts'][-1][1] = float(val)
        else:
            cur[code] = val
    if in_ent:
        flush()
    return segs, texts


def raster_dxf(segs, texts, out):
    """Растр DXF: стены — пространство между близкими параллельными линиями (заливка по чётности не надёжна) —
    линии рисуются толщиной 1 px, затем закрытие промежутков до 700 мм между парами линий."""
    xs = [v for s in segs for v in (s[0], s[2])]
    ys = [v for s in segs for v in (s[1], s[3])]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    W, H = int((x1 - x0) / MPP) + 40, int((y1 - y0) / MPP) + 40
    im = Image.new('L', (W, H), 255)
    dr = ImageDraw.Draw(im)
    for a, b, c, d in segs:
        dr.line([((a - x0) / MPP + 20, (y1 - b) / MPP + 20), ((c - x0) / MPP + 20, (y1 - d) / MPP + 20)], fill=0, width=1)
    words = [dict(text=t['text'], u=(t['x'] - x0) + 100, v=(y1 - t['y']) + 100, size=0) for t in texts]
    arr = np.asarray(im)
    return np.stack([arr] * 3, -1), words, True


def wall_mask(rgb, outline=False):
    """Маска залитых стен (заливка/штриховка/тёмная заливка); стены двумя линиями добавляются отдельно (double_bands)."""
    import cv2
    g = rgb.astype(np.int32)
    gray = g.mean(-1)
    sat = g.max(-1) - g.min(-1)
    m = ((gray < 200) | (sat > 40) & (gray < 245)).astype(np.uint8)
    if outline:     # DXF: контурные стены до ~350 мм
        k = int(350 / MPP) | 1
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, 1), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((1, k), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))      # штриховка -> заливка
    t = max(3, int(60 / MPP))                                              # тоньше 60 мм — не стена
    hor = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((t, 1), np.uint8))
    ver = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((1, t), np.uint8))
    mm = (hor & ver)
    mm = cv2.morphologyEx(mm, cv2.MORPH_OPEN, np.ones((t, t), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(mm, 8)
    keep = np.zeros_like(mm)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] * MPP * MPP > 0.05e6 and max(st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]) * MPP > 600:
            keep[lab == i] = 1
    return keep


def vector_segments_pdf(path, page, scale):
    """Осевые отрезки страницы PDF в пикселях растра (u — вправо, v — вниз)."""
    import pdfplumber
    pdf = pdfplumber.open(path)
    pg = pdf.pages[page - 1]
    k = 25.4 / 72 * scale / MPP           # pt -> px
    segs = []
    for l in pg.lines:
        segs.append((l['x0'] * k, l['top'] * k, l['x1'] * k, l['bottom'] * k))
    for r in pg.rects:
        x0, t, x1, b = r['x0'] * k, r['top'] * k, r['x1'] * k, r['bottom'] * k
        segs += [(x0, t, x1, t), (x0, b, x1, b), (x0, t, x0, b), (x1, t, x1, b)]
    H = pg.height
    for c in pg.curves:
        pts = [(x * k, (H - y) * k) for x, y in c['pts']] if c.get('pts') else []
        for a, b in zip(pts, pts[1:]):
            segs.append((a[0], a[1], b[0], b[1]))
    out = []
    for a, b, c_, d in segs:
        if abs(b - d) < 0.4 and abs(c_ - a) * MPP >= 300:
            out.append(('h', min(a, c_), max(a, c_), (b + d) / 2))
        elif abs(a - c_) < 0.4 and abs(d - b) * MPP >= 300:
            out.append(('v', min(b, d), max(b, d), (a + c_) / 2))
    return out


def double_bands(segs, dark, words_px, fill_rects):
    """Стены, начерченные двумя параллельными линиями (50–260 мм), с пустым промежутком без текста.
    Полосы на одной линии между двумя залитыми участками стены той же толщины — это проёмы (окна), не стены."""
    bands, opens = [], []
    lo, hi = 50 / MPP, 260 / MPP
    for ori in ('h', 'v'):
        L = sorted([s for s in segs if s[0] == ori], key=lambda s: s[3])
        for i, a in enumerate(L):
            for b in L[i + 1:]:
                d = b[3] - a[3]
                if d < lo:
                    continue
                if d > hi:
                    break
                s0, s1 = max(a[1], b[1]), min(a[2], b[2])
                if (s1 - s0) * MPP < 300:
                    continue
                c0, c1 = int(round(a[3])), int(round(b[3]))
                if ori == 'h':
                    box = (c0, c1, int(s0), int(s1))        # v0, v1, u0, u1
                    inner = dark[c0 + 2:c1 - 1, int(s0) + 2:int(s1) - 2]
                else:
                    box = (int(s0), int(s1), c0, c1)
                    inner = dark[int(s0) + 2:int(s1) - 2, c0 + 2:c1 - 1]
                if inner.size == 0 or inner.mean() > 0.03:
                    continue
                if any(box[2] - 2 < w[0] < box[3] + 2 and box[0] - 2 < w[1] < box[1] + 2 for w in words_px):
                    continue
                # проём между залитыми участками той же толщины?
                is_open = False
                for r in fill_rects:
                    if ori == 'h' and abs(r[0] - box[0]) <= 4 and abs(r[1] - box[1]) <= 4 and (abs(r[3] - box[2]) <= 4 or abs(r[2] - box[3]) <= 4):
                        is_open = True
                    if ori == 'v' and abs(r[2] - box[2]) <= 4 and abs(r[3] - box[3]) <= 4 and (abs(r[1] - box[0]) <= 4 or abs(r[0] - box[1]) <= 4):
                        is_open = True
                (opens if is_open else bands).append(box)
    return bands, opens


def bridges(rects, gap_max=2600):
    """Перемычки в проёмах: два участка стены одной толщины на одной линии с разрывом <= gap_max."""
    out = []
    g = gap_max / MPP
    hz = [r for r in rects if (r[3] - r[2]) > (r[1] - r[0])]
    vt = [r for r in rects if (r[1] - r[0]) >= (r[3] - r[2])]
    for a in hz:
        for b in hz:
            if b is a or abs(a[0] - b[0]) > 3 or abs(a[1] - b[1]) > 3:
                continue
            gap = b[2] - a[3]
            if 0 < gap <= g:
                out.append((min(a[0], b[0]), max(a[1], b[1]), a[3], b[2]))
    for a in vt:
        for b in vt:
            if b is a or abs(a[2] - b[2]) > 3 or abs(a[3] - b[3]) > 3:
                continue
            gap = b[0] - a[1]
            if 0 < gap <= g:
                out.append((a[1], b[0], min(a[2], b[2]), max(a[3], b[3])))
    return out


def rects_from_mask(m):
    """Разбиение маски на прямоугольники: горизонтальные отрезки строк, слияние одинаковых по вертикали."""
    H, W = m.shape
    open_ = {}
    out = []
    for v in range(H + 1):
        runs = set()
        if v < H:
            row = m[v]
            d = np.diff(np.concatenate([[0], row, [0]]))
            st, en = np.where(d == 1)[0], np.where(d == -1)[0]
            runs = set(zip(st.tolist(), en.tolist()))
        for r in list(open_):
            if r not in runs:
                out.append((open_.pop(r), v, r[0], r[1]))          # (v0, v1, u0, u1)
        for r in runs:
            if r not in open_:
                open_[r] = v
    return out


def snap(v, s=5):
    return int(round(v / s) * s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('--scale', type=float, default=50.0)
    ap.add_argument('--page', type=int, default=1)
    ap.add_argument('--rotate', type=int, default=0, choices=(0, 90, 180, 270))
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.src)), 'obmer_import')
    os.makedirs(out, exist_ok=True)
    if a.src.lower().endswith('.dxf'):
        segs, texts = read_dxf(a.src)
        rgb, words, outline = raster_dxf(segs, texts, out)
    else:
        rgb, _ = raster_pdf(a.src, a.page, a.scale, out)
        words = words_pdf(a.src, a.page, a.scale)
        outline = False
    if a.rotate:
        k = {90: -1, 180: 2, 270: 1}[a.rotate]       # по часовой
        rgb = np.rot90(rgb, k).copy()
        H0, W0 = (rgb.shape[1], rgb.shape[0]) if a.rotate in (90, 270) else rgb.shape[:2]
        for w in words:
            u, v = w['u'], w['v']
            if a.rotate == 90:
                w['u'], w['v'] = H0 * MPP - v, u
            elif a.rotate == 180:
                w['u'], w['v'] = W0 * MPP - u, H0 * MPP - v
            else:
                w['u'], w['v'] = v, W0 * MPP - u
    m = wall_mask(rgb, outline)
    import cv2
    opens = []
    if not a.src.lower().endswith('.dxf') and not a.rotate:
        try:
            segs = vector_segments_pdf(a.src, a.page, a.scale)
            g = rgb.astype(np.int32).mean(-1)
            dark = (g < 160).astype(np.float32)
            wpx = [(w_['u'] / MPP, w_['v'] / MPP) for w_ in words]
            bands, opens = double_bands(segs, dark, wpx, rects_from_mask(m))
            H_, W_ = m.shape

            def wall_at(v, u):
                return 0 <= v < H_ and 0 <= u < W_ and m[v, u]
            for _ in range(3):                    # перегородки примыкают к стенам торцами (Т-узлы), не вдоль
                left = []
                for (v0_, v1_, ua, ub) in bands:
                    hz = (ub - ua) >= (v1_ - v0_)
                    if hz:
                        vm = (v0_ + v1_) // 2
                        ends = wall_at(vm, ua - 3) or wall_at(vm, ub + 3)
                        side = np.mean([wall_at(v0_ - 3, u) or wall_at(v1_ + 3, u) for u in range(ua, ub, 3)] or [0])
                    else:
                        um = (ua + ub) // 2
                        ends = wall_at(v0_ - 3, um) or wall_at(v1_ + 3, um)
                        side = np.mean([wall_at(v, ua - 3) or wall_at(v, ub + 3) for v in range(v0_, v1_, 3)] or [0])
                    if ends and side < 0.5:
                        m[v0_:v1_ + 1, ua:ub] = 1
                    else:
                        left.append((v0_, v1_, ua, ub))
                bands = left
            opens = opens + bands         # отклонённые полосы — только для замыкания помещений
        except Exception as e:            # нет векторов (скан) — только заливки
            print('векторы не прочитаны:', e)
    rects = rects_from_mask(m)
    closed = m.copy()
    for v0_, v1_, ua, ub in bridges(rects) + opens:      # проёмы закрываются для поиска помещений
        closed[v0_:v1_ + 1, ua:ub + 1] = 1
    # наружный контур и помещения
    free = (1 - closed).astype(np.uint8)
    ff = free.copy()
    h, w = ff.shape
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 2)
    inner = (ff == 1).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(inner, 4)
    rooms = []
    for i in range(1, n):
        area = st[i, cv2.CC_STAT_AREA] * MPP * MPP / 1e6
        if area < 0.8:
            continue
        comp = (lab == i).astype(np.uint8)
        cs, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        c = max(cs, key=cv2.contourArea)
        ap_ = cv2.approxPolyDP(c, 4, True)[:, 0, :]
        rooms.append(dict(area=round(area, 1), poly=[(int(p[0]), int(p[1])) for p in ap_]))
    # начало координат — верхний левый угол помещений
    if rooms:
        u0 = min(p[0] for r in rooms for p in r['poly'])
        v0 = min(p[1] for r in rooms for p in r['poly'])
    else:
        v0, u0 = 0, 0

    def X(v):
        return snap((v - v0) * MPP)

    def Y(u):
        return snap((u - u0) * MPP)
    walls = sorted({(X(v0_), Y(ua), X(v1_), Y(ub)) for v0_, v1_, ua, ub in rects if (v1_ - v0_) * (ub - ua) * MPP * MPP > 0.004e6})
    room_polys = []
    for r in sorted(rooms, key=lambda r: (min(p[1] for p in r['poly']), min(p[0] for p in r['poly']))):
        pts = [(X(p[1]), Y(p[0])) for p in r['poly']]
        # ортогонализация: соседние вершины с почти равной координатой — выровнять
        for i in range(len(pts)):
            (xa, ya), (xb, yb) = pts[i - 1], pts[i]
            if abs(xa - xb) < 30:
                pts[i] = (xa, yb)
            elif abs(ya - yb) < 30:
                pts[i] = (xb, ya)
        room_polys.append(dict(area=r['area'], poly=pts))
    for wd in words:
        wd['x'], wd['y'] = snap(wd['v'] - v0 * MPP), snap(wd['u'] - u0 * MPP)
    # файлы
    py = ['# -*- coding: utf-8 -*-', '"""ЧЕРНОВИК obmer.py из ' + os.path.basename(a.src) +
          ' — СВЕРИТЬ с размерами обмера и поправить."""', '', 'WALLS = [']
    py += [f'    {w_},' for w_ in walls] + [']', '', 'ROOMS = {']
    for i, r in enumerate(room_polys, 1):
        py.append(f"    '{i:02d}': dict(poly={r['poly']}),   # {r['area']} м²")
    py += ['}', '']
    open(os.path.join(out, 'obmer_draft.py'), 'w', encoding='utf-8').write('\n'.join(py))
    json.dump([dict(text=w_['text'], x=w_['x'], y=w_['y']) for w_ in words], open(os.path.join(out, 'texts.json'), 'w',
              encoding='utf-8'), ensure_ascii=False, indent=0)
    # превью: исходник + стены (красным) + помещения (номера) + сетка 1 м
    pv = Image.fromarray(rgb).convert('RGB')
    dr = ImageDraw.Draw(pv, 'RGBA')
    for v0_, v1_, ua, ub in rects:
        dr.rectangle([ua, v0_, ub - 1, v1_ - 1], fill=(255, 0, 0, 70))
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 18)
    except OSError:
        font = None
    for i, r in enumerate(room_polys, 1):
        P = [(p[1] / MPP + u0, p[0] / MPP + v0) for p in r['poly']]
        dr.line(P + [P[0]], fill=(0, 90, 255, 255), width=2)
        cx, cy = sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P)
        dr.text((cx - 20, cy - 10), f'{i:02d} {r["area"]}', fill=(0, 60, 200, 255), font=font)
    step = int(1000 / MPP)
    for gx in range(int(u0) % step, pv.width, step):
        dr.line([(gx, 0), (gx, pv.height)], fill=(0, 160, 0, 60))
        dr.text((gx + 2, 2), f'y={snap((gx - u0) * MPP)}', fill=(0, 120, 0, 255), font=font)
    for gy in range(int(v0) % step, pv.height, step):
        dr.line([(0, gy), (pv.width, gy)], fill=(0, 160, 0, 60))
        dr.text((2, gy + 2), f'x={snap((gy - v0) * MPP)}', fill=(0, 120, 0, 255), font=font)
    pv.save(os.path.join(out, 'preview.png'))
    print(f'стен: {len(walls)}, помещений: {len(room_polys)} '
          f"({', '.join(str(r['area']) for r in room_polys)} м²), текстов: {len(words)}")
    print('->', out, ': obmer_draft.py, preview.png, texts.json')


if __name__ == '__main__':
    main()
