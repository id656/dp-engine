# -*- coding: utf-8 -*-
"""3D-модель и панорамы объекта.

    python3 tools/model3d.py objects/<объект> ifc            — IFC4 + GLB + OBJ (out/ifc)
    python3 tools/model3d.py objects/<объект> pack           — контрольные виды (Chromium/WebGL) + README + zip
    python3 tools/model3d.py objects/<объект> pbrt           — сцена pbrt-v4 (out/pano/work/scene.pbrt)
    python3 tools/model3d.py objects/<объект> pano [01 02…]  — стерео-панорамы 360° (нужны pbrt и OIDN: engine/ifc/pbrt/setup_tools.sh)
    python3 tools/model3d.py objects/<объект> pano360 [01 02…] — моно-панорамы 360° для телефона (equirectangular + GPano)
    python3 tools/model3d.py objects/<объект> panoweb        — веб-просмотр панорам для телефона (out/pano/web: index.html + изображения)
    python3 tools/model3d.py objects/<объект> vizviews [01…] — кадры листов визуализаций и полосы титула рендером (vizcfg.VIEWS/STRIPS)
Готовые панорамы out/pano/final/<пом>_<название>_360.jpg можно положить в photos/src_<пом>.jpg — для титула и листов визуализаций."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    import build as B
    B.setup(argv[1])
    cmd = argv[2]
    if cmd == 'ifc':
        from ifc import build_ifc
        build_ifc.main()
    elif cmd == 'pack':
        from ifc import pack_ifc
        pack_ifc.main()
    elif cmd == 'panoweb':
        from ifc import pano_web
        pano_web.main(argv[3:] or None)
    elif cmd == 'vizviews':
        from ifc import pano_batch
        print('\n'.join(pano_batch.views(argv[3:] or None)))
    elif cmd in ('pbrt', 'pano', 'pano360'):
        import paths
        from ifc import scene3d as S3, pbrt_export as PE
        work = paths.out('pano', 'work')
        if not os.path.exists(os.path.join(work, 'scene.pbrt')) or cmd == 'pbrt':
            S = S3.build(paths.out('ifc', 'textures'))
            n = PE.export_scene(S, work)
            print('scene.pbrt ->', work, 'светящихся элементов:', n)
        if cmd == 'pano':
            from ifc import pano_batch
            pano_batch.main(argv[3:] or None)
        if cmd == 'pano360':
            from ifc import pano_batch
            pano_batch.main_mono(argv[3:] or None)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
