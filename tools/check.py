# -*- coding: utf-8 -*-
"""Автопроверка модели объекта (этап «сквозная проверка»): python3 tools/check.py objects/<объект>
Отчёт -> objects/<объект>/out/check.md; в консоль — сводка. Ошибки (E) — исправить в данных; предупреждения (W) —
решить и, если остаются, вынести в texts.CHECKS («уточнить» / «согласовать»)."""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

SW = ('v1', 'v2', 'v1p', 'v2p', 'tr')
SOCK = ('r1', 'r2', 'r2u', 'tvblock', 'medblock', 'deskblock')
SOCK_IP = ('r1w', 'r2w', 'out', 'pow')
SOFT_OVERLAP = {('rug', '*'), ('tv', 'tvconsole'), ('mirror', 'vanity'), ('mirror_oval', 'vanity'), ('mirror', 'console'),
                ('mirror', 'desk'), ('upper', 'kitchen_run'), ('wallshelf', '*'), ('ac', '*'), ('tv', '*'), ('radiator', 'desk'),
                ('radiator', '*'), ('shower', '*'), ('glass', '*'), ('drain', '*'), ('towel', '*'), ('chair', 'table'),
                ('chair', 'desk'), ('chair', 'round'), ('nightstand', 'bed'), ('nightstand', 'bed_single'), ('wc', 'box'), ('mirror', '*'),
                ('mirror_oval', '*'), ('console', '*'), ('column', 'upper')}


def inside(poly, p):
    c = False
    x, y = p
    for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
        if (ya > y) != (yb > y):
            xi = xa + (y - ya) * (xb - xa) / (yb - ya)
            if xi > x:
                c = not c
    return c


def dist_seg(p, a, b):
    ex, ey = b[0] - a[0], b[1] - a[1]
    L2 = ex * ex + ey * ey or 1
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / L2))
    return math.hypot(p[0] - a[0] - t * ex, p[1] - a[1] - t * ey)


def dist_edge(poly, p):
    return min(dist_seg(p, a, b) for a, b in zip(poly, poly[1:] + poly[:1]))


def r_overlap(a, b, gap=0):
    return a[0] < b[2] - gap and b[0] < a[2] - gap and a[1] < b[3] - gap and b[1] < a[3] - gap


def _segs_cross(p, q, a, b):
    def cr(o, u, w):
        return (u[0] - o[0]) * (w[1] - o[1]) - (u[1] - o[1]) * (w[0] - o[0])
    d1, d2, d3, d4 = cr(a, b, p), cr(a, b, q), cr(p, q, a), cr(p, q, b)
    return ((d1 > 1e-6 and d2 < -1e-6) or (d1 < -1e-6 and d2 > 1e-6)) and ((d3 > 1e-6 and d4 < -1e-6) or (d3 < -1e-6 and d4 > 1e-6))


def poly_overlap(P, Q):
    """Пересечение двух многоугольников (рёбра пересекаются или вершина одного внутри другого)."""
    for a, b in zip(P, P[1:] + P[:1]):
        for c, d in zip(Q, Q[1:] + Q[:1]):
            if _segs_cross(a, b, c, d):
                return True
    cx = sum(p[0] for p in P) / len(P); cy = sum(p[1] for p in P) / len(P)
    dx = sum(p[0] for p in Q) / len(Q); dy = sum(p[1] for p in Q) / len(Q)
    return inside(Q, (cx, cy)) or inside(P, (dx, dy)) or any(inside(Q, p) for p in P) or any(inside(P, q) for q in Q)


def rpoly(r, gap=0):
    return [(r[0] + gap, r[1] + gap), (r[2] - gap, r[1] + gap), (r[2] - gap, r[3] - gap), (r[0] + gap, r[3] - gap)]


def shrink(P, d):
    cx = sum(p[0] for p in P) / len(P); cy = sum(p[1] for p in P) / len(P)
    out = []
    for x, y in P:
        L = math.hypot(x - cx, y - cy) or 1
        out.append((x - (x - cx) / L * d, y - (y - cy) / L * d))
    return out


def ovl(it, r, zone, gap=0):
    """Пересечение предмета (прямоугольник или многоугольник 'pts') с прямоугольником zone."""
    if 'pts' in it and 'rect' not in it:
        return poly_overlap(shrink(list(it['pts']), gap), rpoly(zone))
    return r_overlap(zone, r, gap)


def soft(k1, k2):
    return any((x, y) in SOFT_OVERLAP or (x, '*') in SOFT_OVERLAP for x, y in ((k1, k2), (k2, k1)))


def main(obj):
    import build as B
    B.setup(obj)
    import model as D
    import elev as EL
    out = []

    def E(room, msg, fix=''):
        out.append(('E', room, msg, fix))

    def W(room, msg, fix=''):
        out.append(('W', room, msg, fix))

    rooms = D.ROOMS
    # ---- 1. предметы внутри помещений и пересечения
    rects = []
    for it in D.ITEMS:
        r = D.item_rect(it)
        room = it['room']
        poly = rooms[room]['poly']
        if r is None:
            if 'c' in it and not inside(poly, it['c']) and dist_edge(poly, it['c']) > 30:
                E(room, f"{it['key']}: точка предмета вне помещения {room}", 'проверить координаты c')
            continue
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        corners = [(r[0] + 5, r[1] + 5), (r[2] - 5, r[1] + 5), (r[2] - 5, r[3] - 5), (r[0] + 5, r[3] - 5)]
        if 'pts' in it and 'rect' not in it:
            corners = shrink(list(it['pts']), 5)
            cx, cy = sum(p[0] for p in corners) / len(corners), sum(p[1] for p in corners) / len(corners)
        if not inside(poly, (cx, cy)) or sum(not inside(poly, q) for q in corners) > 0 and it['kind'] not in ('tv', 'ac', 'mirror', 'radiator', 'glass', 'drain'):
            E(room, f"{it['key']} ({it['kind']}): габарит выходит за помещение {room}", 'проверить rect / привязку к стене')
        rects.append((it, r))
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            (a, ra), (b, rb) = rects[i], rects[j]
            if a['room'] != b['room'] or soft(a['kind'], b['kind']):
                continue
            za, zb = a.get('z', (0, 0)), b.get('z', (0, 0))
            if isinstance(za, tuple) and isinstance(zb, tuple) and (za[1] <= zb[0] or zb[1] <= za[0]):
                continue
            pa_ = 'pts' in a and 'rect' not in a
            pb_ = 'pts' in b and 'rect' not in b
            if pa_ or pb_:
                hit = poly_overlap(shrink(list(a['pts']), 5) if pa_ else rpoly(ra, 5),
                                   shrink(list(b['pts']), 5) if pb_ else rpoly(rb, 5))
            else:
                hit = r_overlap(ra, rb, gap=5)
            if hit:
                E(a['room'], f"{a['key']} и {b['key']} пересекаются в плане", 'развести предметы')
    # ---- 2. двери: проход, конфликт полотна с мебелью и выключателями
    for key in D.DOOR_LIST:
        d = D.DOORS[key]
        hx, hy = d['h']; cx, cy = d['c']; ox, oy = d['o']; L = d['L']
        if key != 'entry' and L - 40 < 700 and not key.startswith('balc'):
            W('—', f'дверь {key}: светлый проход ≈ {L - 40} мм < 700', 'полотно 800 или подтвердить допустимость')
        # сектор открывания
        sector = [(hx, hy)] + [(hx + L * (math.cos(t) * cx + math.sin(t) * ox), hy + L * (math.cos(t) * cy + math.sin(t) * oy))
                               for t in [i * math.pi / 2 / 12 for i in range(13)]]
        tip = (hx + ox * L / 2 + cx * L / 2, hy + oy * L / 2 + cy * L / 2)
        room = next((k for k in rooms if inside(rooms[k]['poly'], tip)), None)
        for it, r in rects:
            if it['room'] != room or it['kind'] in ('rug', 'ac', 'tv', 'mirror', 'radiator', 'drain'):
                continue
            z = it.get('z', (0, 0))
            if isinstance(z, tuple) and z[0] > 2050:
                continue
            if 'pts' in it and 'rect' not in it:
                hit_ = any(inside(list(it['pts']), p) for p in sector[1:] + [tip])
            else:
                hit_ = any(r[0] < p[0] < r[2] and r[1] < p[1] < r[3] for p in sector[1:]) or (r[0] < tip[0] < r[2] and r[1] < tip[1] < r[3])
            if hit_:
                E(room or '—', f'дверь {key}: полотно при открывании задевает {it["key"]}', 'перенавесить дверь или сдвинуть предмет')
        for P in D.POINTS:
            if P['kind'] not in SW or P['room'] != room:
                continue
            p = P['p']
            # выключатель за полотном: у стены петель, ближе L к петле со стороны полотна
            along = (p[0] - hx) * cx + (p[1] - hy) * cy
            perp = (p[0] - hx) * ox + (p[1] - hy) * oy
            if 0 < along < L and abs(perp) < 60:
                W(room, f'выключатель {P["id"]} закрывается полотном двери {key}', 'перенавесить дверь или перенести выключатель')
    # ---- 3. выключатели: высота и отступ от проёма
    zs = {P['z'] for P in D.POINTS if P['kind'] in SW}
    if len(zs) > 1:
        W('—', f'выключатели на разных высотах: {sorted(zs)}', 'единая высота по квартире (+900)')
    for P in D.POINTS:
        if P['kind'] not in SW:
            continue
        p = P['p']
        for o in EL.OPENINGS:
            if o['kind'] != 'door':
                continue
            if o['axis'] == 'x' and o['c0'] - 1 <= p[0] <= o['c1'] + 1:
                s = p[1]
            elif o['axis'] == 'y' and o['c0'] - 1 <= p[1] <= o['c1'] + 1:
                s = p[0]
            else:
                continue
            gap = max(o['a'] - s, s - o['b'])
            if -1 < gap < 100:
                E(P['room'], f'выключатель {P["id"]}: {gap:.0f} мм от проёма {o["key"]} (< 100)', 'сдвинуть на 150 от проёма')
            if o['a'] < s < o['b']:
                E(P['room'], f'выключатель {P["id"]} попадает в проём {o["key"]}', 'перенести')
    # ---- 4. точки на стенах своих помещений
    for P in D.POINTS:
        poly = rooms[P['room']]['poly']
        if dist_edge(poly, P['p']) > 8:
            E(P['room'], f'{P["id"]}: точка не на грани стены помещения ({dist_edge(poly, P["p"]):.0f} мм)', 'поставить на стену')
    # ---- 5. мокрые зоны: IP и расстояние от душа
    for P in D.POINTS:
        if D.ROOM[P['room']].get('zone') not in ('wet',) and D.ROOM[P['room']].get('zone') != 'out':
            continue
        if P['kind'] in SOCK and not P.get('hidden'):
            E(P['room'], f'{P["id"]}: розетка без IP44 в помещении {P["room"]}', 'r1w / r2w')
        for it in D.ITEMS:
            if it['room'] == P['room'] and it['kind'] == 'shower' and P['kind'] in SOCK + SOCK_IP + SW:
                dd = math.hypot(P['p'][0] - it['c'][0], P['p'][1] - it['c'][1])
                if dd < 1200:
                    E(P['room'], f'{P["id"]}: {dd:.0f} мм от душа — зона 1–2 (ГОСТ Р 50571.7.701)', 'не ближе 1,2 м от лейки / 0,6 м от стекла')
    # ---- 6. унитаз: зона перед прибором и по бокам; раковина — зона перед
    for it in D.ITEMS:
        if it['kind'] not in ('wc', 'vanity', 'mini_basin'):
            continue
        r = D.item_rect(it)
        wall, face, axis = it['wall'], it['face'], it['axis']
        dep = it.get('depth', 540) if it['kind'] != 'wc' else 540
        need = 600 if it['kind'] == 'wc' else 700
        half = 300 if it['kind'] == 'wc' else it.get('width', 400) / 2
        sgn = {'W': 1, 'E': -1, 'S': 1, 'N': -1}[wall]
        f0 = face + sgn * dep
        f1 = f0 + sgn * need
        if wall in ('W', 'E'):
            zone = (min(f0, f1), axis - half, max(f0, f1), axis + half)
        else:
            zone = (axis - half, min(f0, f1), axis + half, max(f0, f1))
        poly = rooms[it['room']]['poly']
        bad = [o['key'] for o, rr in rects if o is not it and o['room'] == it['room'] and ovl(o, rr, zone, 2)
               and o['kind'] not in ('rug', 'mirror', 'mirror_oval', 'towel', 'wallshelf', 'ac', 'tv', 'drain', 'shower')
               and not (isinstance(o.get('z'), tuple) and o['z'][0] >= 1200)]
        if any(not inside(poly, q) for q in ((zone[0] + 2, zone[1] + 2), (zone[2] - 2, zone[3] - 2))):
            bad.append('стена')
        if bad:
            E(it['room'], f'{it["key"]}: перед прибором нет свободной зоны {need} мм (мешает: {", ".join(bad)})',
              'сдвинуть прибор / мебель')
        if it['kind'] == 'wc':
            for side in (-1, 1):
                lat = None
                for o, rr in rects:
                    if o is it or o['room'] != it['room'] or o['kind'] in ('rug', 'box', 'mirror', 'mirror_oval', 'ac', 'tv'):
                        continue
                    if wall in ('W', 'E'):
                        ov = rr[0] < max(face, f0) and rr[2] > min(face, f0)
                        dist = (rr[1] - axis) if side > 0 else (axis - rr[3])
                    else:
                        ov = rr[1] < max(face, f0) and rr[3] > min(face, f0)
                        dist = (rr[0] - axis) if side > 0 else (axis - rr[2])
                    if ov and dist >= 0:
                        lat = dist if lat is None else min(lat, dist)
                wall_d = 9999
                lo, hi = min(face, f0), max(face, f0)
                for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]):
                    if wall in ('W', 'E') and ya == yb and min(xa, xb) < hi - 1 and max(xa, xb) > lo + 1 and (ya - axis) * side > 0:
                        wall_d = min(wall_d, abs(ya - axis))
                    if wall in ('S', 'N') and xa == xb and min(ya, yb) < hi - 1 and max(ya, yb) > lo + 1 and (xa - axis) * side > 0:
                        wall_d = min(wall_d, abs(xa - axis))
                lat = min(lat if lat is not None else 9999, wall_d)
                if lat < 300:
                    E(it['room'], f'{it["key"]}: от оси унитаза до препятствия {lat:.0f} мм (< 300)', 'сдвинуть ось / мебель')
    # ---- 7. кровать: проходы
    for it, r in rects:
        if it['kind'] not in ('bed',):
            continue
        poly = rooms[it['room']]['poly']
        head = it.get('head', 'S')
        sides = {'W': [('y0', -1), ('y1', 1), ('x1', 1)], 'E': [('y0', -1), ('y1', 1), ('x0', -1)],
                 'S': [('x0', -1), ('x1', 1), ('y1', 1)], 'N': [('x0', -1), ('x1', 1), ('y0', -1)]}[head]
        for edge, sg in sides:
            if edge in ('x0', 'x1'):
                x = r[0] if edge == 'x0' else r[2]
                band = (x - 600, r[1] + 100, x, r[3] - 100) if sg < 0 else (x, r[1] + 100, x + 600, r[3] - 100)
            else:
                y = r[1] if edge == 'y0' else r[3]
                band = (r[0] + 100, y - 600, r[2] - 100, y) if sg < 0 else (r[0] + 100, y, r[2] - 100, y + 600)
            blk = [o['key'] for o, rr in rects if o is not it and o['room'] == it['room'] and ovl(o, rr, band, 2)
                   and o['kind'] not in ('rug', 'nightstand', 'ac', 'tv', 'radiator', 'mirror', 'chair')]
            if any(not inside(poly, q) for q in ((band[0] + 2, band[1] + 2), (band[2] - 2, band[3] - 2))):
                blk.append('стена')
            if blk:
                W(it['room'], f'{it["key"]}: проход у кровати < 600 ({edge}; мешает: {", ".join(blk)})', 'развести мебель')
    # ---- 8. группы света
    lg = {L['g'] for L in D.LIGHTS}
    sg = {g for P in D.POINTS if P['kind'] in SW for g in P.get('g', []) if not g.startswith('ТП')}
    auto = {g for g, txt in D.GROUPS.items() if any(w in txt.lower() for w in ('сенсор', 'датчик'))}
    for g in sorted(lg - sg - auto):
        E('—', f'группа света {g} без выключателя', 'добавить выключатель / клавишу (или «сенсор» в описании группы)')
    for g in sorted(sg - lg):
        W('—', f'выключатель на группу {g}, светильников нет', 'проверить коды групп')
    for g in sorted(lg - set(D.GROUPS)):
        E('—', f'группа {g} не описана в GROUPS', 'добавить описание')
    for L in D.LIGHTS:
        p = L.get('p') or L.get('a')
        poly = rooms[L['room']]['poly']
        if not inside(poly, p) and dist_edge(poly, p) > 10:
            E(L['room'], f'светильник группы {L["g"]} вне помещения', 'проверить координаты')
    # ---- 9. тёплые полы: терморегуляторы
    ids = {P['id'] for P in D.POINTS}
    for h in D.HEAT:
        if h['tr'] not in ids:
            E(h['room'], f'тёплый пол {h["room"]}: нет терморегулятора {h["tr"]} в POINTS', 'добавить tr')
    # ---- 10. канализация: уклон 2 % в стяжке
    risers = [R for R in D.RISERS if R['kind'] in ('k110', 'k50')]
    build_up = getattr(D, 'FLOOR_BUILDUP', 150)
    for P in D.PLUMB:
        if P['kind'] != 'k50' or not risers or P.get('route') == 'wall':     # 'wall' — трасса над полом (в тумбе, коробе)
            continue
        dmin = min(abs(P['p'][0] - R['p'][0]) + abs(P['p'][1] - R['p'][1]) for R in risers)
        drop = dmin * 0.02 + 50
        if D.ROOM[P['room']].get('zone') != 'wet' and drop > build_up and 'КНС' not in str(P.get('note', '')) and 'КНС' not in str(P.get('fx', '')):
            W(P['room'], f'вывод К50 ({P.get("fx", "")}): до стояка ≈ {dmin / 1000:.1f} м, уклон 2 % требует {drop:.0f} мм > пирог {build_up}',
              'КНС (насосная установка), подиум или перенос прибора к стояку')
    # ---- 11. мокрые зоны над жилыми у соседей — напоминание
    for k in D.rooms_all():
        if D.ROOM[k].get('zone') == 'wet' or any(it['room'] == k and it['kind'] == 'kitchen_run' for it in D.ITEMS):
            W(k, f'{D.ROOM[k]["name"]}: проверить по поэтажному плану, что ниже не жилая комната (ПП РФ № 47, п. 24)', 'уточнить')
    # ---- отчёт
    import paths
    lines = ['# Автопроверка модели', '', f'Объект: {obj}', '',
             f'Ошибок: {sum(1 for x in out if x[0] == "E")}, предупреждений: {sum(1 for x in out if x[0] == "W")}', '',
             '| | Пом. | Проблема | Как решить |', '|---|---|---|---|']
    for t, room, msg, fix in sorted(out, key=lambda x: (x[0], x[1])):
        lines.append(f'| {t} | {room} | {msg} | {fix} |')
    rep = paths.out('check.md')
    open(rep, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    for t, room, msg, fix in sorted(out, key=lambda x: (x[0], x[1])):
        print(f'{t} [{room}] {msg}' + (f'  -> {fix}' if fix else ''))
    print(f'-- {sum(1 for x in out if x[0] == "E")} E, {sum(1 for x in out if x[0] == "W")} W; отчёт: {rep}')
    return out


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'objects/_template')
