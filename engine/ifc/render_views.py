# -*- coding: utf-8 -*-
"""Рендер контрольных видов модели (GLB) через Chromium/WebGL. python3 ifc/render_views.py <glb> <outdir> [view ...]"""
import functools
import http.server
import os
import shutil
import sys
import threading
import urllib.parse

from playwright.sync_api import sync_playwright

def views():
    """Контрольные виды: аксонометрия и план по габариту стен + вид в каждом помещении из точки камеры панорамы.
    Координаты GLB: (x, z, −y) в метрах."""
    import model as D
    from ifc import pbrt_export as PE
    xs = [r[0] for r in D.WALLS] + [r[2] for r in D.WALLS]
    ys = [r[1] for r in D.WALLS] + [r[3] for r in D.WALLS]
    cx, cy = (min(xs) + max(xs)) / 2000, (min(ys) + max(ys)) / 2000
    ext = max(max(xs) - min(xs), max(ys) - min(ys)) / 1000
    V = {
        'axo': dict(eye=f'{cx + ext * 1.2:.2f},{ext * 1.6:.2f},{-cy + ext * 1.2:.2f}', at=f'{cx:.2f},0,{-cy:.2f}',
                    ortho=f'{ext * 0.62:.2f}', clip='1.9', clipcls='Wall,Covering,Window,Door,Plate',
                    hide='над квартирой,Плита балкона,Потолок,LightFixture,Fan,Шторы,UnitaryEquipment', w=1800, h=1250),
        'plan': dict(eye=f'{cx:.2f},40,{-cy - 0.05:.2f}', at=f'{cx:.2f},0,{-cy:.2f}', ortho=f'{ext * 0.55:.2f}', clip='1.95',
                     hide='над квартирой,Плита балкона,Потолок', w=1600, h=1200),
    }
    import math
    for k, (x, y, yaw, name) in PE.cams().items():
        z = ((D.ROOM[k]['level'] or 0) + 1600) / 1000
        a = math.radians(yaw)
        tx, ty = x / 1000 + 3 * math.cos(a), y / 1000 + 3 * math.sin(a)
        V['r' + k] = dict(eye=f'{x / 1000:.2f},{z:.2f},{-y / 1000:.2f}', at=f'{tx:.2f},{z - 0.45:.2f},{-ty:.2f}', fov='78')
    return V


CAPS = {}


def main(glb, outdir, names=None):
    os.makedirs(outdir, exist_ok=True)
    srv_dir = os.path.join(outdir, '_srv')
    os.makedirs(srv_dir, exist_ok=True)
    shutil.copy(os.path.join(os.path.dirname(__file__), 'viewer.html'), os.path.join(srv_dir, 'viewer.html'))
    shutil.copy(glb, os.path.join(srv_dir, 'model.glb'))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=srv_dir)
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    out = []
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
                                     '--ignore-gpu-blocklist'])
        for name, v in views().items():
            if names and name not in names:
                continue
            v = dict(v)
            w, h = v.pop('w', 1600), v.pop('h', 1000)
            q = '&'.join(f'{k}={urllib.parse.quote(str(x))}' for k, x in v.items())
            pg = br.new_page(viewport=dict(width=w, height=h))
            pg.goto(f'http://127.0.0.1:{port}/viewer.html#{q}&w={w}&h={h}')
            pg.wait_for_function('window.__done === true', timeout=180000)
            err = pg.evaluate('window.__err || null')
            if err:
                print(name, 'ERROR', err)
            f = os.path.join(outdir, f'{name}.png')
            pg.screenshot(path=f)
            out.append(f)
            pg.close()
        br.close()
    httpd.shutdown()
    shutil.rmtree(srv_dir, ignore_errors=True)
    return out


if __name__ == '__main__':
    print(main(sys.argv[1], sys.argv[2], sys.argv[3:] or None))
