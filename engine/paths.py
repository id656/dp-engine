# -*- coding: utf-8 -*-
"""Пути движка. Объект задаётся сборщиком (build.py setup) или переменной окружения DP_OBJECT."""
import os

ENGINE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(ENGINE)
BUREAU = os.path.join(ROOT, 'bureau')
FONTS = os.path.join(BUREAU, 'fonts')
OBJ = os.environ.get('DP_OBJECT', '')
OUT = os.path.join(OBJ, 'out') if OBJ else os.path.join(ROOT, 'out')
PHOTOS = os.path.join(OBJ, 'photos') if OBJ else ''
EXT = os.environ.get('DP_EXT', '/home/claude/ext')      # внешние инструменты (pbrt-v4, OIDN) — для панорам


def set_object(obj_dir):
    global OBJ, OUT, PHOTOS
    OBJ = os.path.abspath(obj_dir)
    OUT = os.path.join(OBJ, 'out')
    PHOTOS = os.path.join(OBJ, 'photos')
    os.makedirs(OUT, exist_ok=True)


def out(*parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p) if os.path.splitext(p)[1] else p, exist_ok=True)
    return p
