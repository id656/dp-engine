# -*- coding: utf-8 -*-
"""Сборка комплекта: все листы из единой модели -> PDF + DXF R12."""
import os, sys, zipfile
from core import render_pdf, write_dxf
import kit

import paths
OUT = paths.OUT

SHEETS = []   # (номер, ключ, наименование, функция)


def register():
    """Состав альбома: album.sheets() объекта или типовой (default_album)."""
    import tables as TB
    import album as AL
    lst = AL.sheets() if hasattr(AL, 'sheets') else default_album()
    full = list(lst)
    lst = [(k, n, (fn if fn else (lambda no, total, _l=full: TB.sheet_general(no, total, _l)))) for k, n, fn in lst]
    return lst


def common_sheets():
    """Общие листы: титул, общие данные, дизайн-проект, указания, планы и спецификации (по порядку)."""
    import plans as PL
    import tables as TB
    import viz as VZ
    return [
        ('01', 'Титульный лист', VZ.sheet_title),
        ('02', 'Общие данные. Ведомость листов, экспликация помещений, ссылочные документы', None),
        ('03', 'Дизайн-проект. Планировочное решение (цветной план, материалы)', TB.sheet_design),
        ('04', 'Общие указания. Сквозная проверка решений', TB.sheet_notes),
        ('obm', 'Обмерный план', PL.sheet_obmer),
        ('dem', 'План демонтажа', PL.sheet_demo),
        ('mnt', 'План монтажа перегородок и коробов', PL.sheet_mount),
        ('fur', 'План расстановки мебели и оборудования', PL.sheet_furniture),
        ('flr', 'План полов', PL.sheet_floors),
        ('hft', 'План тёплых полов', PL.sheet_heat),
        ('cei', 'План потолков', PL.sheet_ceiling),
        ('fin', 'Ведомость отделки помещений', TB.sheet_finish_schedule),
        ('mat', 'Спецификация отделочных материалов', TB.sheet_materials),
        ('lgt', 'План освещения', PL.sheet_lighting),
        ('lsp', 'Спецификация светильников', TB.sheet_lights),
        ('swi', 'План управления освещением', PL.sheet_switches),
        ('out', 'План розеток и выводов', PL.sheet_outlets),
        ('eui', 'Спецификация электроустановочных изделий', TB.sheet_eui),
        ('plb', 'План сантехники', PL.sheet_plumbing),
        ('ssp', 'Спецификация сантехники и бытовой техники', TB.sheet_sanitary),
        ('dor', 'План дверей. Ведомость дверей', PL.sheet_doors),
        ('ven', 'План вентиляции и кондиционирования', PL.sheet_vent),
    ]


def room_sheets(elev_sheets, viz_rooms=()):
    """Листы помещений: перед первым листом развёрток помещения — лист визуализации (если есть виды)."""
    import viz as VZ
    out = []
    done = set()
    for key, name, fn in elev_sheets:
        room = key[:2]
        if room in viz_rooms and room not in done:
            out.append(('v' + room, f'{VZ.NAMES[room]} {room}. Визуализация', VZ.sheet_viz_factory(room)))
        done.add(room)
        out.append(('e' + key, name, fn))
    return out


def default_album():
    """Типовой состав для нового объекта: общие листы + автоматические развёртки по помещениям + узлы."""
    import elev as EL
    import viz as VZ
    import details
    es = []
    for room in sorted(D_rooms_with_walls()):
        es += EL.auto_room_sheets(room)
    es.append(('det', 'Узлы', details.sheet_details))
    vr = [r for r in VZ.VIZ_ROOMS if VZ.VIEWS.get(r)] if VZ.has_photos() else []
    return common_sheets() + room_sheets(es, vr)


def D_rooms_with_walls():
    import model as D
    return [k for k in D.rooms_all() if k in getattr(D, 'RWALLS', {})]


def build(only=None):
    lst = register()
    total = len(lst)
    sheets = []
    for i, (key, name, fn) in enumerate(lst, 1):
        if only and key not in only:
            continue
        sh = fn(i, total)
        sh.no = i
        sh.name = name
        sheets.append(sh)
    return sheets, lst


def run(only=None, dxf=False, cover=True):
    import viz as VZ
    if VZ.has_photos():
        VZ.build_assets(only_missing=True)
    sheets, lst = build(only)
    pdf = os.path.join(OUT, f'{kit.PROJECT["cipher"]}_Рабочая_документация.pdf' if not only else 'preview.pdf')
    render_pdf(sheets, pdf, title=f'{kit.PROJECT["cipher"]} Дизайн-проект. Рабочая документация', author=kit.PROJECT['author'])
    if not only and dxf:
        dxfdir = os.path.join(OUT, 'dxf')
        os.makedirs(dxfdir, exist_ok=True)
        for sh in sheets:
            write_dxf(sh, os.path.join(dxfdir, f'{kit.PROJECT["cipher"]}_L{sh.no:02d}.dxf'))
        zp = os.path.join(OUT, f'{kit.PROJECT["cipher"]}_DXF_R12.zip')
        with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
            for f in sorted(os.listdir(dxfdir)):
                z.write(os.path.join(dxfdir, f), f)
    print('ok', pdf, len(sheets), 'sheets of', len(lst))
    return pdf
