# -*- coding: utf-8 -*-
"""Превью, README и архив выпуска 3D-модели."""
import os
import sys
import zipfile

from PIL import Image, ImageDraw, ImageFont

from ifc import render_views as RV  # noqa: E402
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf'
FONTB = '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf'

def caps():
    import model as D
    c = {'axo': 'Аксонометрия (разрез по стенам на +1,900; потолки и перекрытие скрыты)', 'plan': 'План (вид сверху, разрез на +1,950)'}
    for k in D.ROOM:
        c['r' + k] = f'{k} {D.ROOM[k]["name"]}'
    return c


README = """{cipher} · 3D-модель квартиры по дизайн-проекту ({rev})
{studio} · {studio_sub} · {phone} · Telegram {tg}

СОСТАВ
  {n}.ifc   — IFC4 (BIM), основной файл модели.
  {n}.glb   — та же модель в glTF 2.0, фактуры внутри файла (Twinmotion, Blender, D5, просмотрщик Windows и др.).
  {n}.obj/.mtl — та же модель для 3ds Max / SketchUp / Cinema 4D; фактуры — в папке textures.
  textures/ — фактуры (JPG). Держать рядом с .ifc и .obj — пути к фактурам относительные.
  preview/  — контрольные виды модели.

ЕДИНИЦЫ И ОСИ
  IFC: миллиметры; X, Y — как в модели проекта (X — вниз по листам, Y — вправо), Z — вверх.
  ±0,000 — чистый пол жилых помещений (= черновой пол + {buildup}).
  GLB/OBJ: метры, ось Y вверх (стандарт этих форматов).

ЧТО ВНУТРИ IFC ({nel} элементов)
{classes}
  • Каждый элемент — набор свойств «ДП_Параметры» (помещение, коды отделки, отметки, группы света, марки, материалы);
    стены — Pset_WallCommon (LoadBearing, IsExternal); помещения — Qto_SpaceBaseQuantities и Pset_SpaceCommon;
    двери — Pset_DoorCommon (марка).
  • Инженерные системы (IfcDistributionSystem): {systems}.
  • Отделка связана с помещениями (IfcRelCoversSpaces); материалы с цветами и фактурами
    (IfcImageTexture + IfcIndexedTriangleTextureMap в реальном масштабе плитки и паркета).

ДЕТАЛИЗАЦИЯ (многополигональная модель, сглаженные нормали в IFC и GLB)
  Формы без упрощений: скруглённые кромки мебели и фасадов, точёные и конические ножки, мягкая мебель
  со скруглёнными подушками и стёжкой, чаши ванны, раковины и унитаза — лофтом по сечениям, смесители и
  душевая система — телами вращения и трубами с гибами, молдинги, плинтусы, галтели и наличники — протяжкой
  профилей с углами на ус, люстры с плафонами, кристаллами и изогнутыми рожками, шторы со складками,
  розетки с гнёздами и клавишами, трубопроводы со скруглёнными отводами.
  Стены (несущие — монолит, отдельно от перегородок), перекрытия, эркер; полы с раскладкой, стяжка; потолки ГКЛ
  с нишами карнизов и световыми нишами, потолочные галтели, ревизионные люки; отделка стен по зонам, буазери
  молдингами, пояс-разделитель, плинтус; откосы, подоконники, окна; двери с филёнками, коробками, наличниками,
  ручками, пороги; встроенная мебель с фасадами, молдингами и фурнитурой, кухня (фасады, столешница, мойка,
  встроенная техника, вытяжка), мебель, текстиль, шторы; сантехприборы (ванна со смесителем на борту, подвесные
  унитазы с рамами инсталляций, тумбы с раковинами, душевая система, трап, стекло), короба с полками,
  люк-невидимка; светильники по типам (споты, накладные, люстры, бра, ленты, линейные); ЭУИ по высотам,
  щиты ЩК и СЩ, ввод питающего кабеля; стояки, канализация с уклоном, подводки PEX к кухне, выводы приборов,
  краны / фильтры / счётчики / регуляторы в шахте; маты тёплого пола с датчиками; воздуховоды, клапаны
  притока, трассы фреона; помещения с площадями.

ТЕКСТУРЫ — ГДЕ ОНИ ВИДНЫ
  Текстуры в IFC поддерживают не все программы. Видны: Bonsai/BlenderBIM (Material Preview/Rendered),
  ряд веб-просмотрщиков IFC. Archicad, Revit, BIMvision и др. при импорте берут цвет и имя материала.
  Для визуализации с фактурами — GLB или OBJ.

ДОПУЩЕНИЯ МОДЕЛИ (уточнить по месту — как и в рабочей документации)
  • Перекрытия 220 мм, черновой потолок — по обмеру/условно.
  • Трассы сетей — по планам проекта (канализация — уклон 0,02 условно от отметки выпуска; подводки к приборам
    внутри коробов, электропроводка групп и каркасы ГКЛ не моделировались; ввод кабеля — трасса условная).
  • Оборудование шахты (краны, фильтры, счётчики, регуляторы) — схематично, по составу узла ввода.
  • Существующие элементы (радиаторы, кондиционеры, трассы фреона) — проверить по месту.
  • Фактуры условные, по палитре проекта; модели светильников, сантехники и мебели — обобщённые, в габаритах проекта.
"""


def preview_sheet(files, path):
    W, M = 1800, 30
    fnt = ImageFont.truetype(FONT, 22)
    fntb = ImageFont.truetype(FONTB, 30)
    tiles = [k for k in sorted(files) if k not in ('axo', 'plan')]
    CAPS = caps()
    cw = (W - 3 * M) // 2
    ch = int(cw * 0.625)
    axo = Image.open(files['axo']).convert('RGB')
    import numpy as np
    a = np.asarray(axo).astype(int)
    bg = a[2, 2]
    mask = (np.abs(a - bg).sum(2) > 12)
    ys, xs = np.nonzero(mask)
    pad = 40
    axo = axo.crop((max(0, xs.min() - pad), max(0, ys.min() - pad), min(axo.width, xs.max() + pad), min(axo.height, ys.max() + pad)))
    ah = int(axo.height * (W - 2 * M) / axo.width)
    axo = axo.resize((W - 2 * M, ah), Image.LANCZOS)
    rows = (len(tiles) + 1) // 2
    H = 115 + ah + 50 + rows * (ch + 50) + M
    sheet = Image.new('RGB', (W, H), (250, 249, 246))
    d = ImageDraw.Draw(sheet)
    from kit import PROJECT as P_
    d.text((M, 24), f"{P_['cipher']} · 3D-модель квартиры (IFC4) — контрольные виды", font=fntb, fill=(30, 30, 30))
    sub = P_.get('studio', '') + ' · ' + P_.get('studio_sub', '')
    d.text((M, 68), sub, font=fnt, fill=(90, 90, 90))
    y = 115
    sheet.paste(axo, (M, y))
    d.text((M, y + ah + 10), CAPS['axo'], font=fnt, fill=(60, 60, 60))
    y += ah + 50
    for i, k in enumerate(tiles):
        im = Image.open(files[k]).convert('RGB').resize((cw, ch), Image.LANCZOS)
        x = M + (i % 2) * (cw + M)
        yy = y + (i // 2) * (ch + 50)
        sheet.paste(im, (x, yy))
        d.text((x, yy + ch + 10), CAPS[k], font=fnt, fill=(60, 60, 60))
    sheet.save(path, quality=88)
    return path


def main():
    import paths
    from kit import PROJECT as P_
    from ifc.build_ifc import name3d
    OUT = paths.out('ifc')
    NAME = name3d()
    ZIP = os.path.join(paths.OUT, f"{P_['cipher']}_3D-модель_IFC.zip")
    import model as D
    pv = os.path.join(OUT, 'preview')
    os.makedirs(pv, exist_ok=True)
    pngs = RV.main(os.path.join(OUT, NAME + '.glb'), pv)
    files = {}
    for f in pngs:
        k = os.path.splitext(os.path.basename(f))[0]
        jpg = os.path.join(pv, f'{k}.jpg')
        Image.open(f).convert('RGB').save(jpg, quality=88)
        os.remove(f)
        files[k] = jpg
    sheet = preview_sheet(files, os.path.join(OUT, f"{P_['cipher']}_3D_превью.jpg"))
    with open(os.path.join(OUT, 'README.txt'), 'w', encoding='utf-8-sig') as f:
        import re
        from collections import Counter
        txt = open(os.path.join(OUT, NAME + '.ifc'), encoding='ascii').read()
        CL = {'IFCWALL': 'IfcWall', 'IFCSLAB': 'IfcSlab', 'IFCSPACE': 'IfcSpace', 'IFCCOVERING': 'IfcCovering', 'IFCDOOR': 'IfcDoor',
              'IFCWINDOW': 'IfcWindow', 'IFCFURNITURE': 'IfcFurniture', 'IFCSANITARYTERMINAL': 'IfcSanitaryTerminal',
              'IFCWASTETERMINAL': 'IfcWasteTerminal', 'IFCELECTRICAPPLIANCE': 'IfcElectricAppliance',
              'IFCAUDIOVISUALAPPLIANCE': 'IfcAudioVisualAppliance', 'IFCLIGHTFIXTURE': 'IfcLightFixture', 'IFCOUTLET': 'IfcOutlet',
              'IFCSWITCHINGDEVICE': 'IfcSwitchingDevice', 'IFCUNITARYCONTROLELEMENT': 'IfcUnitaryControlElement',
              'IFCSPACEHEATER': 'IfcSpaceHeater', 'IFCUNITARYEQUIPMENT': 'IfcUnitaryEquipment', 'IFCFAN': 'IfcFan',
              'IFCPLATE': 'IfcPlate', 'IFCBUILDINGELEMENTPROXY': 'IfcBuildingElementProxy', 'IFCAIRTERMINAL': 'IfcAirTerminal',
              'IFCPIPESEGMENT': 'IfcPipeSegment', 'IFCPIPEFITTING': 'IfcPipeFitting', 'IFCDUCTSEGMENT': 'IfcDuctSegment',
              'IFCVALVE': 'IfcValve', 'IFCFILTER': 'IfcFilter', 'IFCFLOWMETER': 'IfcFlowMeter',
              'IFCELECTRICDISTRIBUTIONBOARD': 'IfcElectricDistributionBoard', 'IFCCABLESEGMENT': 'IfcCableSegment',
              'IFCCOMMUNICATIONSAPPLIANCE': 'IfcCommunicationsAppliance'}
        cnt = Counter(m.group(1) for m in re.finditer(r'^#\d+=([A-Z]+)\(', txt, re.M))
        items = [f'{CL[k]} — {cnt[k]}' for k in CL if cnt.get(k)]
        lines, cur = [], '  • '
        for it in items:
            if len(cur) + len(it) > 110:
                lines.append(cur.rstrip(', ')); cur = '    '
            cur += it + ', '
        lines.append(cur.rstrip(', '))
        def dec(t):
            return re.sub(r'\\X2\\([0-9A-F]+)\\X0\\',
                          lambda m: ''.join(chr(int(m.group(1)[i:i + 4], 16)) for i in range(0, len(m.group(1)), 4)), t)
        sy = sorted(set(dec(x) for x in re.findall(r"IFCDISTRIBUTIONSYSTEM\('[^']*',#\d+,'([^']*)'", txt)))
        f.write(README.format(n=NAME, cipher=P_['cipher'], rev=P_.get('rev', ''), studio=P_.get('studio', ''),
                              studio_sub=P_.get('studio_sub', ''), phone=P_.get('phone', ''), tg=P_.get('tg', ''),
                              buildup=getattr(D, 'FLOOR_BUILDUP', 150), nel=sum(cnt[k] for k in CL),
                              classes='\n'.join(lines), systems=(';\n    '.join(sy) or '—')))
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for fn in (NAME + '.ifc', NAME + '.glb', NAME + '.obj', NAME + '.mtl', 'README.txt'):
            z.write(os.path.join(OUT, fn), fn)
        for fn in sorted(os.listdir(os.path.join(OUT, 'textures'))):
            z.write(os.path.join(OUT, 'textures', fn), 'textures/' + fn)
        for k, f in files.items():
            z.write(f, f'preview/{os.path.basename(f)}')
        z.write(sheet, f'preview/{NAME}_preview.jpg')
    print(ZIP, os.path.getsize(ZIP))
    return sheet


if __name__ == '__main__':
    main()
