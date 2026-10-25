# -*- coding: utf-8 -*-
"""Экспорт сцены в GLB (glTF 2.0, фактуры внутри файла) и OBJ+MTL (фактуры в папке textures/).
Метры, ось Y вверх (стандарт обоих форматов): (x, y, z)мм → (x, z, −y)/1000."""
import json
import math
import os
import struct

import numpy as np

from ifc import m3d as M

SKIP = {'IfcSpace'}


def _tri_normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    L = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
    return (n[0] / L, n[1] / L, n[2] / L)


def part_arrays(p):
    """Позиции (м, Y вверх), нормали, uv (по вершинам) и индексы части."""
    nv = len(p.v)
    pos = np.array(p.v, dtype=np.float64)
    nrm = np.zeros((nv, 3))
    uv = np.zeros((nv, 2))
    for t, tuv in zip(p.t, p.uv):
        n = _tri_normal(p.v[t[0]], p.v[t[1]], p.v[t[2]])
        for vi, q in zip(t, tuv):
            nrm[vi] = n
            uv[vi] = q
    for vi, n in getattr(p, 'vn', {}).items():
        nrm[vi] = n
    P = np.stack([pos[:, 0], pos[:, 2], -pos[:, 1]], 1) / 1000.0
    N = np.stack([nrm[:, 0], nrm[:, 2], -nrm[:, 1]], 1)
    idx = np.array(p.t, dtype=np.uint32).reshape(-1)
    return P.astype(np.float32), N.astype(np.float32), uv.astype(np.float32), idx


def _lin(c):
    return [float(round(x ** 2.2, 4)) for x in c]


def gl_material(m):
    rough = {'MATT': 0.85, 'PLASTIC': 0.45, 'METAL': 0.4, 'GLASS': 0.05, 'MIRROR': 0.03}.get(m.refl, 0.8)
    metal = {'METAL': 0.8, 'MIRROR': 1.0}.get(m.refl, 0.0)
    if m.key in ('BLACK', 'ENTRY', 'GRAPHITE'):
        metal, rough = 0.3, 0.55
    a = 1.0 - m.transp
    mat = dict(name=m.name, doubleSided=True,
               pbrMetallicRoughness=dict(baseColorFactor=([1, 1, 1] if m.tex else _lin(m.color)) + [a],
                                         metallicFactor=metal, roughnessFactor=rough))
    if a < 0.999:
        mat['alphaMode'] = 'BLEND'
    if m.key == 'LED':
        mat['emissiveFactor'] = [1.0, 0.85, 0.6]
    return mat


def write_glb(S, path, texdir):
    bin_ = bytearray()
    views, accessors, meshes, nodes, materials, images, textures = [], [], [], [], [], [], []
    mat_index, tex_index = {}, {}

    def view(data, target=None):
        while len(bin_) % 4:
            bin_.append(0)
        off = len(bin_)
        bin_.extend(data)
        v = dict(buffer=0, byteOffset=off, byteLength=len(data))
        if target:
            v['target'] = target
        views.append(v)
        return len(views) - 1

    def acc(arr, typ, comp, target, minmax=False):
        a = dict(bufferView=view(arr.tobytes(), target), componentType=comp, count=int(arr.shape[0] if arr.ndim > 1 else arr.size), type=typ)
        if minmax:
            a['min'] = [float(x) for x in arr.min(0)]
            a['max'] = [float(x) for x in arr.max(0)]
        accessors.append(a)
        return len(accessors) - 1

    def material(key):
        if key in mat_index:
            return mat_index[key]
        m = M.MATS[key]
        gm = gl_material(m)
        if m.tex:
            if m.tex not in tex_index:
                with open(os.path.join(texdir, m.tex), 'rb') as f:
                    iv = view(f.read())
                images.append(dict(bufferView=iv, mimeType='image/jpeg', name=m.tex))
                textures.append(dict(source=len(images) - 1, sampler=0))
                tex_index[m.tex] = len(textures) - 1
            gm['pbrMetallicRoughness']['baseColorTexture'] = dict(index=tex_index[m.tex])
        materials.append(gm)
        mat_index[key] = len(materials) - 1
        return mat_index[key]

    for i, el in enumerate(S.elems):
        if el.cls in SKIP or not el.parts:
            continue
        prims = []
        for mk, p in el.parts.items():
            if not p.t:
                continue
            P, N, UV, I = part_arrays(p)
            UVg = UV.copy()
            UVg[:, 1] = 1.0 - UVg[:, 1]
            attrs = dict(POSITION=acc(P, 'VEC3', 5126, 34962, True), NORMAL=acc(N, 'VEC3', 5126, 34962))
            if M.MATS[mk].tex:
                attrs['TEXCOORD_0'] = acc(UVg, 'VEC2', 5126, 34962)
            prims.append(dict(attributes=attrs, indices=acc(I, 'SCALAR', 5125, 34963), material=material(mk)))
        if not prims:
            continue
        meshes.append(dict(name=el.name, primitives=prims))
        extras = {'ifc_class': el.cls, 'room': el.room or ''}
        nodes.append(dict(name=f'{el.cls[3:]} | {el.name}', mesh=len(meshes) - 1, extras=extras))
    root = dict(name='Квартира — 3D-модель дизайн-проекта', children=list(range(len(nodes))))
    nodes.append(root)
    gltf = dict(asset=dict(version='2.0', generator='dp-engine expw.py'),
                scene=0, scenes=[dict(name='Квартира', nodes=[len(nodes) - 1])], nodes=nodes, meshes=meshes,
                materials=materials, accessors=accessors, bufferViews=views, buffers=[dict(byteLength=len(bin_))],
                images=images, textures=textures, samplers=[dict(magFilter=9729, minFilter=9987, wrapS=10497, wrapT=10497)])
    js = json.dumps(gltf, ensure_ascii=False).encode('utf-8')
    while len(js) % 4:
        js += b' '
    while len(bin_) % 4:
        bin_.append(0)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(js), 0x4E4F534A))
        f.write(js)
        f.write(struct.pack('<II', len(bin_), 0x004E4942))
        f.write(bin_)
    return dict(nodes=len(nodes) - 1, materials=len(materials), images=len(images), size=total)


def write_obj(S, path, texrel='textures'):
    base = os.path.splitext(os.path.basename(path))[0]
    mtl_path = os.path.join(os.path.dirname(path), base + '.mtl')
    used = []
    out = ['# квартира, 3D-модель по рабочей документации (dp-engine)', '# единицы — метры, ось Y вверх',
           f'mtllib {base}.mtl']
    vo = to = no = 0
    for i, el in enumerate(S.elems):
        if el.cls in SKIP or not el.parts:
            continue
        nm = f'{i:03d}_{el.cls[3:]}_{el.name}'.replace(' ', '_').replace('\n', '_')
        out.append(f'o {nm}')
        for mk, p in el.parts.items():
            if not p.t:
                continue
            P, N, UV, I = part_arrays(p)
            if mk not in used:
                used.append(mk)
            out.extend(f'v {a:.4f} {b:.4f} {c:.4f}' for a, b, c in P)
            out.extend(f'vt {u:.4f} {v:.4f}' for u, v in UV)
            out.extend(f'vn {a:.3f} {b:.3f} {c:.3f}' for a, b, c in N)
            out.append(f'usemtl {mk}')
            T3 = I.reshape(-1, 3)
            for a, b, c in T3:
                a1, b1, c1 = a + 1 + vo, b + 1 + vo, c + 1 + vo
                out.append(f'f {a1}/{a + 1 + to}/{a + 1 + no} {b1}/{b + 1 + to}/{b + 1 + no} {c1}/{c + 1 + to}/{c + 1 + no}')
            vo += len(P); to += len(UV); no += len(N)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    ml = ['# материалы 3D-модели (dp-engine)']
    for mk in used:
        m = M.MATS[mk]
        kd = (1.0, 1.0, 1.0) if m.tex else m.color
        ml += [f'newmtl {mk}', f'# {m.name}', 'Ka 0.000 0.000 0.000', f'Kd {kd[0]:.3f} {kd[1]:.3f} {kd[2]:.3f}',
               f'Ks {m.spec:.2f} {m.spec:.2f} {m.spec:.2f}', 'Ns 40', f'd {1 - m.transp:.2f}', 'illum 2']
        if m.key == 'LED':
            ml.append('Ke 1.000 0.850 0.600')
        if m.tex:
            ml.append(f'map_Kd {texrel}/{m.tex}')
        ml.append('')
    with open(mtl_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ml))
    return dict(materials=len(used))
