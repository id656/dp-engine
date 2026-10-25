# -*- coding: utf-8 -*-
"""Проверка движка на эталоне: содержимое всех листов objects/dp-01-2026-ai сравнивается со снимком.
python3 tools/regress.py            — сравнить;   python3 tools/regress.py --update — обновить снимок (после намеренных правок)"""
import math
import os
import pickle
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OBJ = os.path.join(ROOT, 'objects', 'dp-01-2026-ai')
BASE = os.path.join(ROOT, 'tools', 'baseline_dp-01-2026-ai.pkl')


def snapshot():
    import build as B
    B.setup(OBJ)
    import assemble
    sheets, lst = assemble.build()
    data = []
    for sh in sheets:
        items = []
        for it in sh.items:
            d = dict(it)
            if 'path' in d:
                d['path'] = os.path.basename(d['path'])
            items.append(d)
        data.append(dict(no=sh.no, name=sh.name, items=items))
    return data


def eq(x, y):
    if isinstance(x, float) or isinstance(y, float):
        try:
            return abs(float(x) - float(y)) <= 1e-6 * max(1, abs(float(x)))
        except (TypeError, ValueError):
            return False
    if isinstance(x, (list, tuple)) and isinstance(y, (list, tuple)):
        return len(x) == len(y) and all(eq(p, q) for p, q in zip(x, y))
    if isinstance(x, dict) and isinstance(y, dict):
        return x.keys() == y.keys() and all(eq(x[k], y[k]) for k in x)
    return x == y


def main():
    cur = snapshot()
    if '--update' in sys.argv or not os.path.exists(BASE):
        pickle.dump(cur, open(BASE, 'wb'))
        print('снимок обновлён:', BASE, len(cur), 'листов')
        return 0
    base = pickle.load(open(BASE, 'rb'))
    bad = 0
    if len(base) != len(cur):
        print('число листов', len(base), '->', len(cur))
        bad += 1
    for a, b in zip(base, cur):
        if a['name'] != b['name'] or len(a['items']) != len(b['items']) or not all(eq(p, q) for p, q in zip(a['items'], b['items'])):
            n = sum(1 for p, q in zip(a['items'], b['items']) if not eq(p, q))
            print(f"лист {a['no']:02d} {a['name'][:50]}: элементов {len(a['items'])} -> {len(b['items'])}, отличий {n}")
            bad += 1
    print('OK: эталон собирается без изменений' if not bad else f'ОТЛИЧИЯ в {bad} листах')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
