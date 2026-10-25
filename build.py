# -*- coding: utf-8 -*-
"""Сборка альбома дизайн-проекта из движка и данных объекта.

    python3 build.py objects/<объект> all            — весь альбом (PDF) + обложка
    python3 build.py objects/<объект> all --dxf      — плюс DXF R12 по листам (zip)
    python3 build.py objects/<объект> fur,flr        — отдельные листы -> out/preview.pdf
    python3 build.py objects/<объект> --params       — файлы параметров помещений (md) -> out/params
    python3 build.py objects/<объект> --list         — состав альбома (ключи листов)
"""
import os
import sys


def setup(obj_dir):
    obj_dir = os.path.abspath(obj_dir)
    root = os.path.dirname(os.path.abspath(__file__))
    os.environ['DP_OBJECT'] = obj_dir
    eng = os.path.join(root, 'engine')
    for p in (eng, obj_dir):
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, eng)
    sys.path.insert(0, obj_dir)          # данные объекта перекрывают одноимённые модули движка
    import paths
    paths.set_object(obj_dir)
    return obj_dir


def build(only=None):
    import assemble
    return assemble.build(only)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    setup(argv[1])
    import assemble
    args = argv[2:]
    if '--params' in args:
        import gen_params
        gen_params.main()
        return 0
    if '--list' in args:
        for i, (k, n, f) in enumerate(assemble.register(), 1):
            print(f'{i:02d}  {k:6s} {n}')
        return 0
    keys = [a for a in args if not a.startswith('--')]
    only = None if (not keys or keys[0] == 'all') else keys[0].split(',')
    assemble.run(only, dxf='--dxf' in args, cover='--no-cover' not in args)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
