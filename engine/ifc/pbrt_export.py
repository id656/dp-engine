# -*- coding: utf-8 -*-
"""Экспорт сцены квартиры (scene3d) в pbrt-v4 для фотореалистичных 360°-панорам.
Метры, мир правый, z вверх. Камера — сферическая ODS (патч pbrt): eyepos/yaw/eye."""
import math
import os
import sys

import numpy as np
from PIL import Image

import model as D  # noqa: E402
from ifc import m3d as M  # noqa: E402

MM = 0.001

# ----------------------------------------------------------------- материалы
# kind: diffuse | coated | conductor | thin | transl ; rough; bump (м на единицу яркости)
MAT_SPEC = {
    'C1': ('diffuse', None, 0.0), 'C7': ('coated', 0.55, 0.0), 'CEIL': ('diffuse', None, 0.0),
    'FRONT': ('coated', 0.45, 0.0), 'PLASTER': ('diffuse', None, 0.0), 'SCREED': ('diffuse', None, 0.0),
    'C2': ('coated', 0.4, 0.0015), 'C4': ('coated', 0.22, 0.004), 'C5': ('coated', 0.25, 0.004),
    'WALNUT': ('coated', 0.28, 0.0015), 'OAK': ('coated', 0.3, 0.0015),
    'CONCRETE': ('diffuse', None, 0.002),
    'BLACK': ('coated', 0.35, 0.0), 'STEEL': ('conductor', 0.12, 0.0), 'CERAMIC': ('coated', 0.02, 0.0),
    'WHITE': ('coated', 0.18, 0.0), 'PVC': ('coated', 0.25, 0.0), 'GLASS_SH': ('thin', None, 0.0),
    'MIRROR': ('conductor', 0.0, 0.0), 'BLACKGLASS': ('coated', 0.01, 0.0), 'SCREEN': ('coated', 0.01, 0.0),
    'LED': ('diffuse', None, 0.0), 'GRAPHITE': ('coated', 0.3, 0.0), 'LINEN_SHEER': ('transl', None, 0.0),
    'BLIND': ('transl', None, 0.0), 'MATTRESS': ('diffuse', None, 0.0), 'ENTRY': ('coated', 0.35, 0.0),
    # детализация (многополигональная модель)
    'BRASS': ('conductor', 0.28, 0.0), 'NICKEL': ('conductor', 0.16, 0.0), 'COPPER': ('conductor', 0.3, 0.0),
    'ACRYL': ('coated', 0.04, 0.0), 'OPAL': ('transl', None, 0.0), 'CRYSTAL': ('glass', None, 0.0),
    'MARBLE': ('coated', 0.06, 0.0), 'MARBLE_SILL': ('coated', 0.12, 0.0), 'PP_GREY': ('coated', 0.35, 0.0),
    'PEX_BLUE': ('coated', 0.35, 0.0), 'PEX_RED': ('coated', 0.35, 0.0), 'DUCT': ('diffuse', None, 0.0),
    'HEATMAT': ('diffuse', None, 0.0), 'STEELFRAME': ('coated', 0.4, 0.0), 'GKL': ('diffuse', None, 0.0),
    'FAB_LINEN': ('diffuse', None, 0.0008), 'C1': ('diffuse', None, 0.0004), 'CEIL': ('diffuse', None, 0.0002),
}
METAL_COL = {'BRASS': (0.86, 0.70, 0.42), 'NICKEL': (0.74, 0.73, 0.71), 'COPPER': (0.90, 0.58, 0.42)}
FAB = ('diffuse', None, 0.002)
SKIP_MATS = {'GLASS', 'SPACE'}          # оконное стекло не рендерим (иначе свет неба не проходит в выборке)


def mat_spec(key):
    if key in MAT_SPEC:
        return MAT_SPEC[key]
    code = next((c for c in D.FINISH if c.replace('Пт', 'PT').replace('П', 'P').replace('С', 'C') == key), None)
    if code:
        tex = D.mat(code).get('tex')
        return {'tiles': ('coated', 0.22, 0.004), 'panels': ('coated', 0.4, 0.0015), 'marble': ('coated', 0.03, 0.0)}.get(
            tex, ('diffuse', None, 0.0))
    if key.startswith('FAB'):
        return FAB
    if key.startswith('FL'):
        code = D.ROOM[key[2:]]['floor']
        if D.mat(code).get('style') == 'marble':
            return ('coated', 0.14, 0.0008)      # лаппато: полуглянец, рельеф только от шва (прожилки — не канавки)
        return ('coated', 0.3, 0.003) if D.mat(code).get('tex') in ('herringbone', 'planks') else ('coated', 0.25, 0.004)
    if key.startswith('Z'):
        return ('coated', 0.03, 0.0)     # мрамор полированный
    return ('diffuse', None, 0.0)


def lin(c):
    return [round(float(x) ** 2.2, 4) for x in c]


def fl(a):
    return ' '.join(f'{x:.5g}' for x in a)


# ----------------------------------------------------------------- свет
LUM = {'spot': 550, 'spot44': 450, 'spot65': 450, 'track': 500, 'pend': 2200, 'linear': 1800, 'sconce': 350, 'ceil': 1800,
       'wall44': 500, 'mirror': 500}
LED_LM_PER_M = 900
WARM = 3000
NITS_SKY = 6500      # яркость «неба» в проёмах, кд/м² (пасмурный день, вид за окном)


class Writer:
    def __init__(s):
        s.L = []

    def __call__(s, line=''):
        s.L.append(line)


def build_textures(texdir, outdir):
    """PNG-копии фактур (pbrt читает png) и серые карты рельефа."""
    os.makedirs(outdir, exist_ok=True)
    done = {}
    for k, m in M.MATS.items():
        if not m.tex or m.tex in done:
            continue
        src = os.path.join(texdir, m.tex)
        base = os.path.splitext(m.tex)[0]
        im = Image.open(src).convert('RGB')
        im.save(os.path.join(outdir, base + '.png'))
        g = np.asarray(im.convert('L')).astype(np.float32) / 255.0
        Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8), 'L').save(os.path.join(outdir, base + '_b.png'))
        done[m.tex] = base
    return done


def write_materials(W, used, texnames, texrel):
    for k in sorted(used):
        m = M.MATS[k]
        kind, rough, bump = mat_spec(k)
        refl = None
        if m.tex:
            base = texnames[m.tex]
            W(f'Texture "t_{k}" "spectrum" "imagemap" "string filename" "{texrel}/{base}.png"')
            refl = f'"texture reflectance" "t_{k}"'
            if bump > 0:
                W(f'Texture "b_{k}" "float" "imagemap" "string filename" "{texrel}/{base}_b.png" "float scale" [{bump}]'
                  ' "string encoding" "linear"')
        else:
            refl = f'"rgb reflectance" [{fl(lin(m.color))}]'
        bp = f' "texture displacement" "b_{k}"' if (m.tex and bump > 0) else ''
        if kind == 'diffuse':
            W(f'MakeNamedMaterial "{k}" "string type" "diffuse" {refl}{bp}')
        elif kind == 'coated':
            W(f'MakeNamedMaterial "{k}" "string type" "coateddiffuse" {refl} "float roughness" [{rough}]'
              f' "float thickness" [0.005] "integer nsamples" [1] "integer maxdepth" [4]{bp}')
        elif kind == 'conductor':
            if k in METAL_COL:
                W(f'MakeNamedMaterial "{k}" "string type" "conductor" "rgb reflectance" [{fl(METAL_COL[k])}] "float roughness" [{rough}]')
            else:
                r = 0.92 if k == 'MIRROR' else 0.62
                W(f'MakeNamedMaterial "{k}" "string type" "conductor" "rgb reflectance" [{r} {r} {r}] "float roughness" [{rough}]')
        elif kind == 'glass':
            W(f'MakeNamedMaterial "{k}" "string type" "dielectric" "float eta" [1.55] "float roughness" [0]')
        elif kind == 'thin':
            W(f'MakeNamedMaterial "{k}" "string type" "thindielectric" "float eta" [1.5]')
        elif kind == 'transl':
            c = lin(m.color)
            W(f'MakeNamedMaterial "{k}" "string type" "diffusetransmission" "rgb reflectance" [{fl([x * 0.75 for x in c])}]'
              f' "rgb transmittance" [{fl([x * 0.35 for x in c])}]')


def mesh(W, part, emit_nits=None, temp=WARM, normal=None):
    P = np.array(part.v, dtype=np.float64) * MM
    I = np.array(part.t, dtype=np.int64)
    uv = np.zeros((len(P), 2))
    for t, tuv in zip(part.t, part.uv):
        for vi, q in zip(t, tuv):
            uv[vi] = q
    if emit_nits:
        W('AttributeBegin')
        W(f'AreaLightSource "diffuse" "blackbody L" [{temp}] "float scale" [{emit_nits:.6g}] "bool twosided" true')
    W(f'NamedMaterial "{part.mat}"')
    W('Shape "trianglemesh" "point3 P" [' + ' '.join(f'{x:.5f} {y:.5f} {z:.5f}' for x, y, z in P) + ']')
    W('  "point2 uv" [' + ' '.join(f'{u:.4f} {v:.4f}' for u, v in uv) + ']')
    if getattr(part, 'vn', None):                  # сглаженные нормали многополигональных поверхностей
        Nn = np.zeros((len(P), 3))
        for t in part.t:
            a_, b_, c_ = (np.array(part.v[i], dtype=np.float64) for i in t)
            fn = np.cross(b_ - a_, c_ - a_)
            L_ = np.linalg.norm(fn)
            if L_ > 0:
                for i in t:
                    if not Nn[i].any():
                        Nn[i] = fn / L_
        for i, n_ in part.vn.items():
            Nn[i] = n_
        Nn[~Nn.any(axis=1)] = (0, 0, 1)
        W('  "normal N" [' + ' '.join(f'{a:.4f} {b:.4f} {c:.4f}' for a, b, c in Nn) + ']')
    W('  "integer indices" [' + ' '.join(str(i) for i in I.reshape(-1)) + ']')
    if emit_nits:
        W('AttributeEnd')


def part_area(part):
    a = 0.0
    for t in part.t:
        p0, p1, p2 = (np.array(part.v[i]) * MM for i in t)
        a += 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0))
    return a


def led_lumens(el, part):
    k = el.props.get('Тип', '')
    if k == 'spot' or k.startswith('spot'):
        return LUM['spot'] * 0.25           # свечение линзы (основной поток — спот-источник)
    if k == 'pend':
        return LUM['pend']
    if k == 'linear':
        return LUM['linear']
    if k == 'sconce':
        return LUM['sconce'] * 2 / 2
    if k == 'ceil':
        return LUM['ceil']
    # ленты: по длине
    P = np.array(part.v) * MM
    L = float(np.ptp(P, axis=0).max())
    return LED_LM_PER_M * L


def write_lights(W):
    """Точечные/спот-источники по модели проекта (группы — все включены)."""
    for L in D.LIGHTS:
        room = L['room']
        zc = (D.ROOM[room]['ceil'] or 2800) * MM
        k = L['kind']
        if k in ('spot', 'spot44', 'spot65'):
            x, y = (c * MM for c in L['p'])
            W(f'LightSource "spot" "blackbody I" [{WARM}] "float power" [{LUM[k]}] "point3 from" [{x} {y} {zc - 0.066}]'
              f' "point3 to" [{x} {y} 0] "float coneangle" [42] "float conedeltaangle" [18]')
        elif k == 'track':
            (xa, ya), (xb, yb) = L['a'], L['b']
            for i in range(4):
                yy = (min(ya, yb) + (i + 0.5) * abs(yb - ya) / 4) * MM
                x = xa * MM
                W(f'LightSource "spot" "blackbody I" [{WARM}] "float power" [{LUM["track"]}] "point3 from" [{x} {yy} {zc - 0.125}]'
                  f' "point3 to" [{x + 0.25} {yy} 0] "float coneangle" [30] "float conedeltaangle" [12]')
        elif k == 'sconce' and L.get('style') == 'legacy':
            from ifc.scene3d import _point_side, SIDE_N
            nx, ny = SIDE_N[_point_side(L['p'], room)]
            x, y = (c * MM for c in L['p'])
            z = L.get('z', 1500) * MM
            cx, cy = x + nx * 0.22, y + ny * 0.22
            W(f'LightSource "spot" "blackbody I" [2700] "float power" [{LUM["sconce"]}] "point3 from" [{cx} {cy} {z - 0.11}]'
              f' "point3 to" [{cx + nx * 0.15} {cy + ny * 0.15} 0] "float coneangle" [55] "float conedeltaangle" [20]')
        elif k == 'pend' and 'хрустал' in (L.get('note') or '').lower():
            x, y = (c * MM for c in L['p'])
            z = (L.get('z', 2200) + 220) * MM
            W(f'LightSource "point" "blackbody I" [2900] "float power" [{LUM["pend"]}] "point3 from" [{x} {y} {z}]')
        elif k == 'wall44':
            from ifc.scene3d import _point_side, SIDE_N
            nx, ny = SIDE_N[_point_side(L['p'], room)]
            x, y = (c * MM for c in L['p'])
            z = L.get('z', 1900) * MM
            W(f'LightSource "point" "blackbody I" [{WARM}] "float power" [{LUM["wall44"]}] "point3 from" [{x + nx * 0.13} {y + ny * 0.13} {z}]')


def sky_image(path, w=512, h=256):
    """Вид за окном: светлое небо с лёгкой дымкой и силуэтами домов (переэкспонировано, как на фото интерьера)."""
    yy = np.linspace(0, 1, h)[:, None]          # 0 — верх
    xx = np.linspace(0, 1, w)[None, :]
    sky = np.stack([0.80 + 0.15 * (1 - yy), 0.86 + 0.12 * (1 - yy), 0.95 + 0.05 * (1 - yy)], -1) * np.ones((h, w, 1))
    rng = np.random.default_rng(3)
    hor = 0.62
    bld = np.zeros(w)
    x = 0
    while x < w:
        ww = rng.integers(25, 70)
        bld[x:x + ww] = hor - rng.uniform(0.05, 0.22)
        x += ww + rng.integers(0, 12)
    mask = yy > bld[None, :]
    build = np.array([0.70, 0.72, 0.74])
    img = np.where(mask[..., None], build * (0.92 + 0.08 * xx[..., None]), sky)
    ground = yy > 0.85
    img = np.where(ground[..., None], np.array([0.55, 0.57, 0.56]), img)
    Image.fromarray((np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8), 'RGB').save(path)


def portals():
    """Порталы неба: в окнах и балконных проёмах (с наружной грани) и над парапетами балконов.
    (a0, a1, c, z0, z1, n, ось): ось 'y' — плоскость y = c, 'x' — плоскость x = c; n — нормаль внутрь (+1/−1)."""
    from ifc import scene3d as S3
    out = []
    for o in S3.OPEN3D:
        k, ax, c0, c1, a, b, z0, z1 = o
        if S3.OKIND.get(k) != 'window':
            continue
        inner, frame = S3._inner_face(o)
        outer = c1 if inner == c0 else c0
        n = 1 if inner > outer else -1
        out.append((a, b, outer - n * 10, z0, z1, n, ax))
    for (x0, y0, x1, y1) in S3.parapets():
        along_y = (y1 - y0) > (x1 - x0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # нормаль внутрь — к центру ближайшего наружного помещения
        rooms_out = [k for k in D.ROOMS if not S3.indoor(k)]
        rc = None
        for k in rooms_out:
            P = D.ROOMS[k]['poly']
            rc = (sum(p[0] for p in P) / len(P), sum(p[1] for p in P) / len(P))
        if along_y:
            n = 1 if (rc and rc[0] > cx) else -1
            out.append((y0, y1, (x0 if n > 0 else x1) - n * 10, 900, S3.BALC_TOP, n, 'x'))
        else:
            n = 1 if (rc and rc[1] > cy) else -1
            out.append((x0, x1, (y0 if n > 0 else y1) - n * 10, 900, S3.BALC_TOP, n, 'y'))
    return out


def write_portals(W, texrel):
    W(f'Texture "sky" "spectrum" "imagemap" "string filename" "{texrel}/sky.png"')
    W('MakeNamedMaterial "SKYM" "string type" "diffuse" "rgb reflectance" [0 0 0]')
    for (x0, x1, y, z0, z1, n, ax) in portals():
        x0, x1, y, z0, z1 = x0 * MM - 0.05, x1 * MM + 0.05, y * MM, z0 * MM - 0.05, z1 * MM + 0.05
        if n < 0:
            pts = [(x1, y, z0), (x0, y, z0), (x0, y, z1), (x1, y, z1)]
        else:
            pts = [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
        nrm = f'0 {-1 if n < 0 else 1} 0'
        if ax == 'x':                         # плоскость x = c: оси (a, z) -> (y, z)
            pts = [(c_, a_, z_) for a_, c_, z_ in pts]
            nrm = f'{-1 if n < 0 else 1} 0 0'
        W('AttributeBegin')
        W(f'AreaLightSource "diffuse" "string filename" "{texrel}/sky.png" "float scale" [{NITS_SKY}]')
        W('NamedMaterial "SKYM"')
        W('Shape "trianglemesh" "point3 P" [' + ' '.join(f'{a:.4f} {b:.4f} {c:.4f}' for a, b, c in pts) + ']'
          ' "point2 uv" [0 0 1 0 1 1 0 1] "integer indices" [0 1 2 0 2 3]'
          f' "normal N" [' + ' '.join(nrm for _ in range(4)) + ']')
        W('AttributeEnd')


def export_scene(S, outdir, texrel='tex'):
    """Геометрия + материалы + свет (общий файл, включается в файлы камер)."""
    os.makedirs(outdir, exist_ok=True)
    texnames = build_textures(M.TEXDIR, os.path.join(outdir, texrel))
    sky_image(os.path.join(outdir, texrel, 'sky.png'))
    used = set()
    for el in S.elems:
        if el.cls == 'IfcSpace':
            continue
        if getattr(el, 'hide_top', False) and 'балкона' in el.name:
            pass
        for k in el.parts:
            if k not in SKIP_MATS:
                used.add(k)
    W = Writer()
    from kit import PROJECT
    W(f'# {PROJECT["cipher"]} — сцена для pbrt-v4 (генерируется из единой модели проекта)')
    write_materials(W, used, texnames, texrel)
    nlights = 0
    for el in S.elems:
        if el.cls == 'IfcSpace':
            continue
        for k, p in el.parts.items():
            if k in SKIP_MATS or not p.t:
                continue
            if k == 'LED' or (k == 'OPAL' and el.cls == 'IfcLightFixture'):
                lm = led_lumens(el, p)
                A = part_area(p)
                nits = lm / (math.pi * A * 2) if A > 0 else 0
                mesh(W, p, emit_nits=nits, temp=2700 if 'ниш' in el.name or el.props.get('Тип') == 'led' else WARM)
                nlights += 1
            else:
                mesh(W, p)
    write_lights(W)
    write_portals(W, texrel)
    with open(os.path.join(outdir, 'scene.pbrt'), 'w') as f:
        f.write('\n'.join(W.L) + '\n')
    return nlights


def cams():
    """Камеры панорам по помещениям: vizcfg.CAMS (x, y, направление) или точка, наиболее удалённая от стен."""
    try:
        import vizcfg as V
        C = dict(getattr(V, 'CAMS', {}))
    except ImportError:
        C = {}
    import drawplan as DP
    out = {}
    for k in sorted(D.ROOM):
        if k in C:
            x, y, yaw = C[k][:3]
        else:
            x, y = DP._poly_center(D.ROOMS[k]['poly'])
            far = max(D.ROOMS[k]['poly'], key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2)
            yaw = math.degrees(math.atan2(far[1] - y, far[0] - x))      # вид на самый дальний угол
        out[k] = (x, y, yaw, D.ROOM[k]['name'])
    return out


ROOMS_CAM = None


EYE_H = 1600


def pano_cams():
    """Точки съёмки панорам: vizcfg.PANO (x, y, направление) — центр свободной зоны помещения; иначе cams()."""
    try:
        import vizcfg as V
        P_ = dict(getattr(V, 'PANO', {}))
    except ImportError:
        P_ = {}
    out = cams()
    for k, v in P_.items():
        if k in out:
            out[k] = (v[0], v[1], v[2], out[k][3])
    return out


def write_camera(outdir, room, eye, w, h, spp, name=None):
    """eye: 'left' | 'right' — стерео ODS; 'mono' — обычная сферическая панорама (телефон, веб)."""
    x, y, yaw, _ = pano_cams()[room]
    z = (D.ROOM[room]['level'] or 0) + EYE_H
    name = name or f'{room}_{eye}'
    lines = [
        f'Film "gbuffer" "integer xresolution" [{w}] "integer yresolution" [{h}] "string filename" "{name}.exr"',
        '  "bool savefp16" false',
        'PixelFilter "gaussian" "float xradius" [1.2] "float yradius" [1.2]',
        f'Sampler "zsobol" "integer pixelsamples" [{spp}]',
        'Integrator "path" "integer maxdepth" [8] "bool regularize" true',
        f'Camera "spherical" "string mapping" "equirectangular" "bool ods" true "float eyepos" [{x * MM} {y * MM} {z * MM}]'
        f' "float yaw" [{yaw}] "float ipd" [0.064] "string eye" "{eye}"' if eye != 'mono' else
        f'Camera "spherical" "string mapping" "equirectangular" "bool ods" true "float eyepos" [{x * MM} {y * MM} {z * MM}]'
        f' "float yaw" [{yaw}] "float ipd" [0.0] "string eye" "left"',
        'WorldBegin',
        'Include "scene.pbrt"',
    ]
    fn = os.path.join(outdir, f'{name}.pbrt')
    with open(fn, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return fn


def write_persp(outdir, room, name, az, ht, vt0, vt1, w, h, spp):
    """Плоский кадр с точки съёмки панорамы (листы визуализаций, полосы титула): камера горизонтальна, кадр сдвинут
    окном экрана (вертикали прямые). az — направление в модели, град (от +x к +y); ht — tan половины горизонтального
    угла; vt0..vt1 — tan по вертикали. Scale −1 1 1 — переход к левой системе камеры pbrt (без зеркального кадра)."""
    x, y, _, _ = pano_cams()[room]
    z = (D.ROOM[room]['level'] or 0) + EYE_H
    a = math.radians(az)
    e = (x * MM, y * MM, z * MM)
    t = (e[0] + math.cos(a), e[1] + math.sin(a), e[2])
    lines = [
        'Scale -1 1 1',
        f'LookAt {e[0]:.5f} {e[1]:.5f} {e[2]:.5f}  {t[0]:.5f} {t[1]:.5f} {t[2]:.5f}  0 0 1',
        f'Film "gbuffer" "integer xresolution" [{w}] "integer yresolution" [{h}] "string filename" "{name}.exr"',
        '  "bool savefp16" false',
        'PixelFilter "gaussian" "float xradius" [1.2] "float yradius" [1.2]',
        f'Sampler "zsobol" "integer pixelsamples" [{spp}]',
        'Integrator "path" "integer maxdepth" [8] "bool regularize" true',
        f'Camera "perspective" "float fov" [90] "float screenwindow" [{-ht:.6f} {ht:.6f} {vt0:.6f} {vt1:.6f}]',
        'WorldBegin',
        'Include "scene.pbrt"',
    ]
    fn = os.path.join(outdir, f'{name}.pbrt')
    with open(fn, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    return fn
