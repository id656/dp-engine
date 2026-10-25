# -*- coding: utf-8 -*-
"""Веб-просмотр панорам 360° на телефоне: out/pano/web/index.html + pano/*.jpg + thumb/*.jpg + img/logo.jpg.

Запуск — tools/model3d.py <объект> panoweb (после pano360). Страница — фрагмент HTML для публикации (Artifact):
без <html>/<head>/<body>, данные плана и помещений — inline JSON. Один источник правды — модель объекта:
стены и помещения (план точек съёмки), отделка (ROOM / FINISH), точки съёмки — vizcfg.PANO.
Короткие названия отделки — vizcfg.FINISH_SHORT (иначе первая часть строки FINISH)."""
import json
import math
import os
import re

import numpy as np
from PIL import Image

import model as D
import paths
import gen_params as GP
from kit import num, lvl, AREA_DEC, PROJECT
from ifc import pbrt_export as PE

TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pano_viewer.html')
# веб-версии панорамы: полная (телефоны с текстурой ≥ 3072), средняя (старые GPU), лёгкая (мгновенный показ)
SIZES = (('', 3072, 86), ('_m', 2048, 84), ('_s', 1024, 72))


def _vcfg(name, default):
    try:
        import vizcfg as V
        return getattr(V, name, default)
    except ImportError:
        return default


def short(code):
    if not code:
        return ''
    S = _vcfg('FINISH_SHORT', {})
    if code in S:
        return S[code]
    return re.split(r'[,;:]', D.FINISH.get(code, code))[0].strip()


def codes_in(note):
    """Коды отделки, упомянутые в примечании помещения («стена А — синий С2; стена Е — буазери С3»)."""
    out = []
    for m in re.finditer(r'(Пт\d+|ПЛ|П\d+|С\d+)', note or ''):
        c = m.group(1)
        if c in D.FINISH and c not in out:
            out.append(c)
    return out


def src(room):
    p = os.path.join(paths.out('pano', 'final'), f'{room}_{GP.slug(D.ROOM[room]["name"])}_360.jpg')
    return p if os.path.exists(p) else None


def rectilinear(eq, w, h, hfov_deg, lon=0.0, lat=0.0):
    """Плоский кадр из equirectangular (центр — направление камеры): для миниатюр."""
    a = np.asarray(eq)
    H, W = a.shape[:2]
    kx = math.tan(math.radians(hfov_deg) / 2)
    ky = kx * h / w
    xs = (np.arange(w) + 0.5) / w * 2 - 1
    ys = 1 - (np.arange(h) + 0.5) / h * 2
    X, Y = np.meshgrid(xs * kx, ys * ky)
    cl, sl, co, so = math.cos(lat), math.sin(lat), math.cos(lon), math.sin(lon)
    F = np.array([cl * co, cl * so, sl])
    R = np.array([-so, co, 0.0])
    U = np.array([-sl * co, -sl * so, cl])
    d = F[None, None, :] + X[..., None] * R + Y[..., None] * U
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    lo = np.arctan2(d[..., 1], d[..., 0])
    la = np.arcsin(np.clip(d[..., 2], -1, 1))
    u = ((lo / (2 * math.pi) + 0.5) % 1.0) * W
    v = (0.5 - la / math.pi) * H
    ui = np.clip(u.astype(int), 0, W - 1)
    vi = np.clip(v.astype(int), 0, H - 1)
    return Image.fromarray(a[vi, ui])


def plan_data():
    walls = [[int(round(v)) for v in r[:4]] for r in D.WALLS]
    polys = [[[int(round(a)), int(round(b))] for a, b in p] for p in D.WALL_POLYS]
    wins = []
    for o in getattr(D, 'OPENINGS', []):
        if o.get('kind') != 'window':
            continue
        c0, c1 = sorted((o['c0'], o['c1']))
        a, b = sorted((o['a'], o['b']))
        wins.append([c0, a, c1, b] if o['axis'] == 'x' else [a, c0, b, c1])
    xs, ys = D.wall_extent()
    return dict(walls=walls, polys=polys, windows=wins, ext=[min(xs), min(ys), max(xs), max(ys)])


def rev_short():
    m = re.search(r'[Рр]ед\.\s*(\d+)', PROJECT.get('rev', '') or '')
    return f'ред. {m.group(1)}' if m else ''


def room_data(k, cam):
    R = D.ROOM[k]
    x, y, yaw, _ = cam
    wall = (getattr(D, 'WALL_DEFAULT', {}) or {}).get(k)
    note = R.get('finish_note', '') or ''
    return dict(
        id=k, name=R['name'], area=num(D.AREA[k], AREA_DEC()),
        ceil=lvl(R['ceil']) if R.get('ceil') else '', level=lvl(R.get('level') or 0),
        floor=[R.get('floor'), short(R.get('floor'))] if R.get('floor') else None,
        wall=[wall, short(wall)] if wall else None, note=note,
        legend=[[c, short(c)] for c in codes_in(note) if c != wall],
        ceiling=[R.get('ceil_code'), short(R.get('ceil_code'))] if R.get('ceil_code') else None,
        cam=[int(round(x)), int(round(y)), round(float(yaw), 2)], eye=PE.EYE_H,
        poly=[[int(round(a)), int(round(b))] for a, b in D.ROOMS[k]['poly']],
        img=f'pano/{k}.jpg', mid=f'pano/{k}_m.jpg', low=f'pano/{k}_s.jpg', thumb=f'thumb/{k}.jpg')


def logo(out):
    p = PROJECT.get('logo')
    if not p or not os.path.exists(p):
        return None
    im = Image.open(p).convert('RGB')
    W, H = im.size
    im = im.crop((int(W * 0.12), int(H * 0.20), int(W * 0.86), int(H * 0.94)))   # знак по центру, без полей
    im = im.resize((300, int(300 * im.height / im.width)), Image.LANCZOS)
    fn = os.path.join(out, 'img', 'logo.jpg')
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    im.save(fn, quality=84, optimize=True, progressive=True)
    return 'img/logo.jpg'


def main(rooms=None):
    out = paths.out('pano', 'web')
    cams = PE.pano_cams()
    data_rooms = []
    for k in (rooms or D.rooms_all()):
        s = src(k)
        if not s:
            print('нет панорамы', k)
            continue
        im = Image.open(s).convert('RGB')
        for suf, w, q in SIZES:
            fn = os.path.join(out, 'pano', f'{k}{suf}.jpg')
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            (im if im.width == w else im.resize((w, w // 2), Image.LANCZOS)).save(fn, quality=q, optimize=True,
                                                                                   progressive=True)
        th = rectilinear(im, 480, 360, 84, lat=math.radians(-6)).resize((240, 180), Image.LANCZOS)
        os.makedirs(os.path.join(out, 'thumb'), exist_ok=True)
        th.save(os.path.join(out, 'thumb', f'{k}.jpg'), quality=80, optimize=True)
        data_rooms.append(room_data(k, cams[k]))
    start = _vcfg('PANO_START', None)
    data = dict(
        cipher=PROJECT.get('cipher', ''), rev=rev_short(), city=PROJECT.get('city', ''),
        object=PROJECT.get('object', ''), studio=PROJECT.get('studio', ''), logo=logo(out),
        start=start if any(r['id'] == start for r in data_rooms) else (data_rooms[0]['id'] if data_rooms else None),
        rooms=data_rooms, plan=plan_data())
    with open(TPL, encoding='utf-8') as f:
        html = f.read()
    js = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    html = html.replace('/*__DATA__*/null', js).replace('__CIPHER__', data['cipher'])
    fn = os.path.join(out, 'index.html')
    with open(fn, 'w', encoding='utf-8') as f:
        f.write(html)
    print('web ->', fn, 'помещений:', len(data_rooms))
    return fn
