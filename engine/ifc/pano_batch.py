# -*- coding: utf-8 -*-
"""Пакетный рендер стерео-панорам (ODS, top-bottom) по помещениям; продолжает с места остановки.
Запуск — через tools/model3d.py <объект> pano [помещения]."""
import json
import math
import os
import subprocess
import time

import numpy as np
from PIL import Image

W, H, SPP = 4096, 2048, 16


def _dirs():
    import paths
    return paths.out('pano', 'work'), paths.out('pano', 'final')


def render(room, eye, w, h, spp):
    import paths
    from ifc import pbrt_export as PE
    work, _ = _dirs()
    name = f'{room}_{eye}'
    exr = os.path.join(work, name + '.exr')
    if not os.path.exists(exr):
        PE.write_camera(work, room, eye, w, h, spp, name=name)
        t = time.time()
        subprocess.run([os.path.join(paths.EXT, 'pbrt-v4', 'build', 'pbrt'), '--quiet', '--nthreads', str(os.cpu_count() or 2),
                        name + '.pbrt'], cwd=work, check=True)
        print(room, eye, f'{time.time() - t:.0f}s', flush=True)
    return exr


def process(room):
    from ifc import pano_post as PP
    import model as D
    import gen_params as GP
    work, out = _dirs()
    base = os.path.join(out, f'{room}_{GP.slug(D.ROOM[room]["name"])}')
    if os.path.exists(base + '_360_TB.jpg'):
        return
    L = PP.denoise(render(room, 'left', W, H, SPP), os.path.join(work, room + 'L'))
    wb = PP.auto_wb(L)
    a, lavg = PP.tonemap(L, wb=wb)
    PP.save_jpeg(a, base + '_360.jpg')
    R = PP.denoise(render(room, 'right', W, H, SPP), os.path.join(work, room + 'R'))
    b, _ = PP.tonemap(R, wb=wb, lavg=lavg)
    tb = np.concatenate([a, b], 0)
    PP.save_jpeg(tb, base + '_360_TB.jpg', pano_w=W, pano_h=H)
    Image.fromarray(a).resize((2048, 1024), Image.LANCZOS).save(base + '_preview.jpg', quality=88)
    print('done', room, flush=True)


def main(rooms=None):
    from ifc import pbrt_export as PE
    for r in (rooms or list(PE.cams())):
        process(r)


# ---------------------------------------------------------------- моно-панорамы (телефон, веб-просмотр)
MW, MH, MSPP = 3072, 1536, 16
EV = 0.2          # поправка экспозиции к автоэкспозиции (+0,4 давало пересвет белых потолков)


def process_mono(room, w=None, h=None, spp=None):
    """Обычная сферическая панорама 360° (equirectangular) + XMP GPano: открывается как 360° на телефоне."""
    from ifc import pano_post as PP
    import model as D
    import gen_params as GP
    work, out = _dirs()
    w, h, spp = w or MW, h or MH, spp or MSPP
    base = os.path.join(out, f'{room}_{GP.slug(D.ROOM[room]["name"])}')
    if os.path.exists(base + '_360.jpg'):
        return base + '_360.jpg'
    img = PP.denoise(render(room, 'mono', w, h, spp), os.path.join(work, room + 'M'))
    wb = PP.auto_wb(img, strength=0.5)
    a, lavg = PP.tonemap(img, wb=wb, ev=EV)
    with open(os.path.join(work, f'{room}_tone.json'), 'w') as f:      # тон панорамы — для видов листов того же помещения
        json.dump(dict(wb=list(wb), lavg=lavg, ev=EV), f)
    PP.save_jpeg(a, base + '_360.jpg', pano_w=w, pano_h=h)
    Image.fromarray(a).resize((2048, 1024), Image.LANCZOS).save(base + '_preview.jpg', quality=88)
    print('done', room, flush=True)
    return base + '_360.jpg'


def main_mono(rooms=None):
    from ifc import pbrt_export as PE
    return [process_mono(r) for r in (rooms or list(PE.cams()))]


# ---------------------------------------------------------------- виды для листов визуализаций и полосы титула
VW, VH, VSPP = 1200, 800, 16          # вид 3:2 — 150–180 dpi в рамках листа А3 (200 и 172 мм)
SW_, SH_ = 320, 1700                  # полоса титула 54×287 мм


def tone(room):
    """Баланс белого и экспозиция панорамы помещения (единый тон панорамы и видов листа)."""
    from ifc import pano_post as PP
    work, _ = _dirs()
    fn = os.path.join(work, f'{room}_tone.json')
    if os.path.exists(fn):
        with open(fn) as f:
            return json.load(f)
    img = PP.denoise(render(room, 'mono', MW, MH, MSPP), os.path.join(work, room + 'T'))
    wb = PP.auto_wb(img, strength=0.5)
    _, lavg = PP.tonemap(img, wb=wb, ev=EV)
    d = dict(wb=list(wb), lavg=lavg, ev=EV)
    with open(fn, 'w') as f:
        json.dump(d, f)
    return d


def _persp(room, name, az, frame, w, h, spp, dst):
    import paths
    from ifc import pbrt_export as PE, pano_post as PP
    work, _ = _dirs()
    exr = os.path.join(work, name + '.exr')
    if not os.path.exists(exr):
        ht, vt0, vt1 = frame
        PE.write_persp(work, room, name, az, ht, vt0, vt1, w, h, spp)
        t = time.time()
        subprocess.run([os.path.join(paths.EXT, 'pbrt-v4', 'build', 'pbrt'), '--quiet', '--nthreads', str(os.cpu_count() or 2),
                        name + '.pbrt'], cwd=work, check=True)
        print(name, f'{time.time() - t:.0f}s', flush=True)
    tn = tone(room)
    img = PP.denoise(exr, os.path.join(work, name + 'D'))
    a, _ = PP.tonemap(img, wb=tn['wb'], ev=tn['ev'], lavg=tn['lavg'])
    Image.fromarray(a).save(dst, quality=93)
    return dst


def views(rooms=None):
    """Кадры листов визуализаций (vizcfg.VIEWS) и полосы титула (vizcfg.STRIPS) — рендер с точек съёмки панорам
    в out/pano/views (viz.build_assets берёт их вместо вырезок из панорам)."""
    import paths
    import viz as VZ
    out = paths.out('pano', 'views')
    os.makedirs(out, exist_ok=True)
    done = []
    for room, vs in VZ.VIEWS.items():
        if rooms and room not in rooms:
            continue
        yc = VZ.CAMS[room][2]
        for i, v in enumerate(vs, 1):
            dst = os.path.join(out, f'view_{room}_{i}.jpg')
            if not os.path.exists(dst):
                _persp(room, f'{room}_v{i}', yc - v['yaw'], VZ.view_frame(v), VW, VH, VSPP, dst)
            done.append(dst)
    for k, (room, yaw) in enumerate(VZ.STRIPS, 1):
        if rooms and room not in rooms:
            continue
        dst = os.path.join(out, f'strip_{k}.jpg')
        if not os.path.exists(dst):
            _persp(room, f'strip{k}_{room}', VZ.CAMS[room][2] - yaw, VZ.strip_frame(), SW_, SH_, VSPP, dst)
        done.append(dst)
    return done
