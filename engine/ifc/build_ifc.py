# -*- coding: utf-8 -*-
"""Сборка 3D-модели объекта: IFC4 с фактурами + GLB + OBJ -> objects/<объект>/out/ifc (через tools/model3d.py)."""
import os
import time


def name3d():
    from kit import PROJECT
    import gen_params as GP
    return GP.slug(PROJECT['cipher']).upper().replace('-', '-') + '_3D'


def main():
    import paths
    from kit import PROJECT
    from ifc import scene3d as S3, ifcw, expw
    out = paths.out('ifc')
    t = time.time()
    tex = os.path.join(out, 'textures')
    S = S3.build(tex)
    print('scene', len(S.elems), f'{time.time() - t:.1f}s')
    nm = name3d()
    r = ifcw.write(S, os.path.join(out, nm + '.ifc'), PROJECT['cipher'], PROJECT.get('author', ''),
                   PROJECT.get('studio', '') + ' · ' + PROJECT.get('studio_sub', ''))
    print('ifc', r)
    print('glb', expw.write_glb(S, os.path.join(out, nm + '.glb'), tex))
    print('obj', expw.write_obj(S, os.path.join(out, nm + '.obj')))
    return S
