# -*- coding: utf-8 -*-
"""Запись IFC4 (STEP, ISO 10303-21) без внешних библиотек.
Стены, плиты, помещения — экструзии; отделка, мебель, оборудование — IfcTriangulatedFaceSet
с IfcIndexedTriangleTextureMap (фактуры — IfcImageTexture, файлы в папке textures/).
У каждой поверхности есть цвет-заменитель (средний тон фактуры) для программ без поддержки текстур."""
import math
import time
import uuid

from ifc import m3d as M

NS = uuid.UUID('6f0f3a52-6c8e-4f43-9b1e-0d1a2b3c4d5e')
B64 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'


def guid(key):
    n = uuid.uuid5(NS, key).int
    out = []
    for _ in range(22):
        out.append(B64[n % 64])
        n //= 64
    return ''.join(reversed(out))


class Ref:
    __slots__ = ('n',)

    def __init__(s, n):
        s.n = n

    def __str__(s):
        return f'#{s.n}'


class E:
    """Перечисление .X."""
    def __init__(s, v):
        s.v = v

    def __str__(s):
        return f'.{s.v}.'


class Raw:
    def __init__(s, v):
        s.v = v

    def __str__(s):
        return s.v


STAR = Raw('*')


def sstr(t):
    """Строка STEP с кодированием не-ASCII через \\X2\\…\\X0\\."""
    out = []
    buf = []

    def flush():
        if buf:
            out.append('\\X2\\' + ''.join(f'{ord(c):04X}' for c in buf) + '\\X0\\')
            buf.clear()
    for ch in str(t):
        o = ord(ch)
        if 32 <= o < 127:
            flush()
            if ch == "'":
                out.append("''")
            elif ch == '\\':
                out.append('\\\\')
            else:
                out.append(ch)
        elif o < 32:
            flush()
            out.append(' ')
        else:
            buf.append(ch)
    flush()
    return "'" + ''.join(out) + "'"


def freal(v, nd=1):
    if abs(v - round(v)) < 10 ** (-nd - 1):
        return f'{int(round(v))}.'
    s = f'{v:.{nd}f}'.rstrip('0')
    return s if not s.endswith('.') else s


def fmt(a):
    if a is None:
        return '$'
    if isinstance(a, (Ref, E, Raw)):
        return str(a)
    if isinstance(a, bool):
        return '.T.' if a else '.F.'
    if isinstance(a, int):
        return str(a)
    if isinstance(a, float):
        return freal(a, 6)
    if isinstance(a, str):
        return sstr(a)
    if isinstance(a, (list, tuple)):
        return '(' + ','.join(fmt(x) for x in a) + ')'
    raise TypeError(type(a))


class Step:
    def __init__(s):
        s.lines = []

    def __call__(s, ent, *args):
        s.lines.append(f'{ent}(' + ','.join(fmt(a) for a in args) + ')')
        return Ref(len(s.lines))

    def raw(s, ent, argstr):
        s.lines.append(f'{ent}({argstr})')
        return Ref(len(s.lines))

    def text(s, fname, author, org):
        ts = time.strftime('%Y-%m-%dT%H:%M:%S')
        head = ['ISO-10303-21;', 'HEADER;',
                "FILE_DESCRIPTION(('ViewDefinition [NotAssigned]'),'2;1');",
                f"FILE_NAME({sstr(fname)},'{ts}',({sstr(author)}),({sstr(org)}),'ifcw.py','dp-engine ifcw.py','');",
                "FILE_SCHEMA(('IFC4'));", 'ENDSEC;', 'DATA;']
        body = [f'#{i + 1}={l};' for i, l in enumerate(s.lines)]
        return '\n'.join(head + body + ['ENDSEC;', 'END-ISO-10303-21;']) + '\n'


# классы с 9 атрибутами (… Tag, PredefinedType)
NINE = {'IfcWall', 'IfcSlab', 'IfcCovering', 'IfcFurniture', 'IfcSanitaryTerminal', 'IfcElectricAppliance',
        'IfcAudioVisualAppliance', 'IfcLightFixture', 'IfcOutlet', 'IfcSwitchingDevice', 'IfcUnitaryControlElement',
        'IfcSpaceHeater', 'IfcUnitaryEquipment', 'IfcWasteTerminal', 'IfcPlate', 'IfcBuildingElementProxy', 'IfcFan',
        'IfcCommunicationsAppliance', 'IfcAirTerminal', 'IfcPipeSegment', 'IfcPipeFitting', 'IfcDuctSegment',
        'IfcElectricDistributionBoard', 'IfcValve', 'IfcFlowMeter', 'IfcFilter', 'IfcCableSegment'}

SYS_ENUM = {'К': 'SEWAGE', 'В1': 'DOMESTICCOLDWATER', 'Т3': 'DOMESTICHOTWATER', 'В': 'VENTILATION', 'Э': 'ELECTRICAL',
            'ЭО': 'LIGHTING', 'ТП': 'HEATING', 'КВ': 'REFRIGERATION', 'СС': 'DATA'}


def write(S, path, project_name, author, org, texrel='textures'):
    W = Step()
    person = W('IFCPERSON', None, 'Демиденко', 'Данил', None, None, None, None, None)
    orgr = W('IFCORGANIZATION', None, org, 'Проектирование и дизайн интерьеров. Тел. +7 990 033-96-48, Telegram @ind_656', None, None)
    po = W('IFCPERSONANDORGANIZATION', person, orgr, None)
    try:
        from kit import PROJECT as _P
    except Exception:  # noqa: BLE001
        _P = {}
    city = _P.get('city', 'Санкт-Петербург')
    rev = (_P.get('rev') or 'Р4').split(' — ')[0]
    app = W('IFCAPPLICATION', orgr, rev, 'dp-engine: генератор модели ' + project_name + ' (единая модель проекта)', 'DP-ENGINE')
    oh = W('IFCOWNERHISTORY', po, app, None, E('ADDED'), None, None, None, int(time.time()))
    units = [W('IFCSIUNIT', STAR, E('LENGTHUNIT'), E('MILLI'), E('METRE')),
             W('IFCSIUNIT', STAR, E('AREAUNIT'), None, E('SQUARE_METRE')),
             W('IFCSIUNIT', STAR, E('VOLUMEUNIT'), None, E('CUBIC_METRE')),
             W('IFCSIUNIT', STAR, E('PLANEANGLEUNIT'), None, E('RADIAN'))]
    ua = W('IFCUNITASSIGNMENT', units)
    org0 = W('IFCCARTESIANPOINT', (0., 0., 0.))
    zdir = W('IFCDIRECTION', (0., 0., 1.))
    xdir = W('IFCDIRECTION', (1., 0., 0.))
    wcs = W('IFCAXIS2PLACEMENT3D', org0, zdir, xdir)
    ctx = W('IFCGEOMETRICREPRESENTATIONCONTEXT', None, 'Model', 3, 0.01, wcs, None)
    body = W('IFCGEOMETRICREPRESENTATIONSUBCONTEXT', 'Body', 'Model', STAR, STAR, STAR, STAR, ctx, None, E('MODEL_VIEW'), None)
    proj = W('IFCPROJECT', guid('project'), oh, project_name, f'Дизайн-проект квартиры, {city}. 3D-модель по рабочей документации, {rev.lower()}',
             None, 'Квартира — дизайн-проект', 'Рабочая документация', [ctx], ua)
    pl_site = W('IFCLOCALPLACEMENT', None, wcs)
    site = W('IFCSITE', guid('site'), oh, 'Участок', None, None, pl_site, None, city, E('ELEMENT'),
             None, None, None, None, None)
    pl_bld = W('IFCLOCALPLACEMENT', pl_site, wcs)
    bld = W('IFCBUILDING', guid('building'), oh, 'Жилой дом', None, None, pl_bld, None, 'Жилой дом (адрес — по договору)',
            E('ELEMENT'), None, None, None)
    pl_st = W('IFCLOCALPLACEMENT', pl_bld, wcs)
    storey = W('IFCBUILDINGSTOREY', guid('storey'), oh, 'Квартира ±0,000', 'Отметки — от чистого пола жилых помещений (±0,000)',
               None, pl_st, None, 'Квартира', E('ELEMENT'), 0.)
    W('IFCRELAGGREGATES', guid('agg1'), oh, None, None, proj, [site])
    W('IFCRELAGGREGATES', guid('agg2'), oh, None, None, site, [bld])
    W('IFCRELAGGREGATES', guid('agg3'), oh, None, None, bld, [storey])

    # ---------------- стили и материалы
    styles, textures, matdefs = {}, {}, {}

    def style_of(key):
        if key in styles:
            return styles[key]
        m = M.MATS[key]
        col = W('IFCCOLOURRGB', None, float(m.color[0]), float(m.color[1]), float(m.color[2]))
        rend = W('IFCSURFACESTYLERENDERING', col, float(m.transp), col, None, None, None,
                 Raw(f'IFCNORMALISEDRATIOMEASURE({freal(m.spec, 3)})'), Raw('IFCSPECULAREXPONENT(32.)'), E(m.refl))
        items = [rend]
        if m.tex:
            tex = W('IFCIMAGETEXTURE', True, True, 'DIFFUSE', None, None, f'{texrel}/{m.tex}')
            textures[key] = tex
            items.append(W('IFCSURFACESTYLEWITHTEXTURES', [tex]))
        st = W('IFCSURFACESTYLE', m.name, E('BOTH'), items)
        styles[key] = st
        return st

    def material_of(key):
        m = M.MATS[key]
        nm = m.ifc_mat
        if nm in matdefs:
            return matdefs[nm]
        mt = W('IFCMATERIAL', nm, m.name, None)
        si = W('IFCSTYLEDITEM', None, [style_of(key)], None)
        sr = W('IFCSTYLEDREPRESENTATION', body, None, None, [si])
        W('IFCMATERIALDEFINITIONREPRESENTATION', None, None, [sr], mt)
        matdefs[nm] = mt
        return mt

    sets = {}

    def matset(keys):
        names = []
        for k in keys:
            if M.MATS[k].ifc_mat not in names:
                names.append(M.MATS[k].ifc_mat)
        mats = [material_of(k) for k in keys]
        uniq = []
        for mm in mats:
            if mm.n not in [u.n for u in uniq]:
                uniq.append(mm)
        if len(uniq) == 1:
            return uniq[0]
        sig = tuple(sorted(u.n for u in uniq))
        if sig in sets:
            return sets[sig]
        cons = [W('IFCMATERIALCONSTITUENT', None, None, u, None, None) for u in uniq]
        ms = W('IFCMATERIALCONSTITUENTSET', ' + '.join(names[:6]), None, cons)
        sets[sig] = ms
        return ms

    # ---------------- элементы
    contained, spaces_by_room, covers = [], {}, {}
    systems = {}
    mat_rel = {}
    n_tex_maps = 0
    for idx, el in enumerate(S.elems):
        if not el.parts and not el.extr:
            continue
        # начало локальной системы — минимум габарита
        xs, ys, zs = [], [], []
        if el.extr:
            for poly, z0, z1, mk in el.extr:
                xs += [p[0] for p in poly]; ys += [p[1] for p in poly]; zs += [z0, z1]
        else:
            for p in el.parts.values():
                for v in p.v:
                    xs.append(v[0]); ys.append(v[1]); zs.append(v[2])
        ox, oy, oz = math.floor(min(xs)), math.floor(min(ys)), math.floor(min(zs))
        pt = W('IFCCARTESIANPOINT', (float(ox), float(oy), float(oz)))
        pl = W('IFCLOCALPLACEMENT', pl_st, W('IFCAXIS2PLACEMENT3D', pt, None, None))
        items = []
        mkeys = []
        if el.extr:
            rtype = 'SweptSolid'
            for poly, z0, z1, mk in el.extr:
                pts = [W('IFCCARTESIANPOINT', (float(x - ox), float(y - oy))) for x, y in poly]
                curve = W('IFCPOLYLINE', pts + [pts[0]])
                prof = W('IFCARBITRARYCLOSEDPROFILEDEF', E('AREA'), None, curve)
                pos = W('IFCAXIS2PLACEMENT3D', W('IFCCARTESIANPOINT', (0., 0., float(z0 - oz))), None, None)
                sol = W('IFCEXTRUDEDAREASOLID', prof, pos, zdir, float(z1 - z0))
                W('IFCSTYLEDITEM', sol, [style_of(mk)], None)
                items.append(sol)
                mkeys.append(mk)
        else:
            rtype = 'Tessellation'
            for mk, p in el.parts.items():
                if not p.t:
                    continue
                coords = ','.join(f'({freal(v[0] - ox)},{freal(v[1] - oy)},{freal(v[2] - oz)})' for v in p.v)
                cl = W.raw('IFCCARTESIANPOINTLIST3D', f'({coords})')
                ci = ','.join(f'({a + 1},{b + 1},{c + 1})' for a, b, c in p.t)
                nst = '$'
                if getattr(p, 'vn', None):                 # сглаженные нормали многополигональных поверхностей
                    from ifc.expw import _tri_normal
                    nr = [None] * len(p.v)
                    for t in p.t:
                        fn = _tri_normal(p.v[t[0]], p.v[t[1]], p.v[t[2]])
                        for vi in t:
                            if nr[vi] is None:
                                nr[vi] = fn
                    for vi, n in p.vn.items():
                        nr[vi] = n
                    nst = '(' + ','.join(f'({n[0]:.3f},{n[1]:.3f},{n[2]:.3f})' if n else '(0.,0.,1.)' for n in nr) + ')'
                fs = W.raw('IFCTRIANGULATEDFACESET', f'{cl},{nst},$,({ci}),$')
                W('IFCSTYLEDITEM', fs, [style_of(mk)], None)
                if M.MATS[mk].tex:
                    uvs, uidx, look = [], [], {}
                    for tri in p.uv:
                        row = []
                        for (u, v) in tri:
                            key = (round(u, 4), round(v, 4))
                            if key not in look:
                                look[key] = len(uvs) + 1
                                uvs.append(key)
                            row.append(look[key])
                        uidx.append(row)
                    tvl = W.raw('IFCTEXTUREVERTEXLIST', '(' + ','.join(f'({freal(u, 4)},{freal(v, 4)})' for u, v in uvs) + ')')
                    W.raw('IFCINDEXEDTRIANGLETEXTUREMAP', f'({textures[mk]}),{fs},{tvl},(' +
                          ','.join(f'({a},{b},{c})' for a, b, c in uidx) + ')')
                    n_tex_maps += 1
                items.append(fs)
                mkeys.append(mk)
        if not items:
            continue
        rep = W('IFCSHAPEREPRESENTATION', body, 'Body', rtype, items)
        pds = W('IFCPRODUCTDEFINITIONSHAPE', None, None, [rep])
        gid = guid(f'el-{idx}-{el.cls}-{el.name}')
        desc = el.props.get('Описание')
        objtype = el.objtype
        if el.predef == 'USERDEFINED' and not objtype:
            objtype = el.name
        if el.cls == 'IfcSpace':
            ent = W('IFCSPACE', gid, oh, el.name, getattr(el, 'long_name', None), None, pl, pds,
                    getattr(el, 'long_name', None), E('ELEMENT'), E(el.predef), None)
            spaces_by_room[el.room] = ent
        elif el.cls == 'IfcDoor':
            h, w = getattr(el, 'door_dims', (None, None))
            ent = W('IFCDOOR', gid, oh, el.name, desc, objtype, pl, pds, el.tag, float(h) if h else None,
                    float(w) if w else None, E('DOOR'), E('NOTDEFINED'), None)
            contained.append(ent)
        elif el.cls == 'IfcWindow':
            h, w = getattr(el, 'win_dims', (None, None))
            ent = W('IFCWINDOW', gid, oh, el.name, desc, objtype, pl, pds, el.tag, float(h) if h else None,
                    float(w) if w else None, E('WINDOW'), E('NOTDEFINED'), None)
            contained.append(ent)
        elif el.cls in NINE:
            ent = W(el.cls.upper(), gid, oh, el.name, desc, objtype, pl, pds, el.tag, E(el.predef or 'NOTDEFINED'))
            contained.append(ent)
            if el.cls == 'IfcCovering' and el.room:
                covers.setdefault(el.room, []).append(ent)
        else:
            raise ValueError(el.cls)
        # материал
        if el.cls != 'IfcSpace':
            ms = matset(mkeys)
            mat_rel.setdefault(ms.n, (ms, []))[1].append(ent)
        # свойства
        props = []
        for k, v in el.props.items():
            if v is None or v == '':
                continue
            if isinstance(v, bool):
                val = Raw(f'IFCBOOLEAN({".T." if v else ".F."})')
            elif isinstance(v, int):
                val = Raw(f'IFCINTEGER({v})')
            elif isinstance(v, float):
                val = Raw(f'IFCREAL({freal(v, 3)})')
            else:
                v = str(v)
                val = Raw(('IFCTEXT(' if len(v) > 120 else 'IFCLABEL(') + sstr(v) + ')')
            props.append(W('IFCPROPERTYSINGLEVALUE', k, None, val, None))
        if el.parts:
            names = []
            for mk in el.parts:
                if M.MATS[mk].ifc_mat not in names:
                    names.append(M.MATS[mk].ifc_mat)
            props.append(W('IFCPROPERTYSINGLEVALUE', 'Материалы', None, Raw('IFCTEXT(' + sstr('; '.join(names)) + ')'), None))
        if props:
            ps = W('IFCPROPERTYSET', guid(f'ps-{idx}'), oh, 'ДП_Параметры', 'Параметры дизайн-проекта ' + project_name, props)
            W('IFCRELDEFINESBYPROPERTIES', guid(f'rdp-{idx}'), oh, None, None, [ent], ps)
        if el.cls == 'IfcSpace':
            area = float(el.props['Площадь, м²'])
            hgt = float(el.props['Высота до потолка'])
            q = [W('IFCQUANTITYAREA', 'NetFloorArea', 'Площадь пола по экспликации', None, area, None),
                 W('IFCQUANTITYLENGTH', 'Height', 'Высота до потолка', None, hgt, None)]
            eq = W('IFCELEMENTQUANTITY', guid(f'q-{idx}'), oh, 'Qto_SpaceBaseQuantities', None, None, q)
            W('IFCRELDEFINESBYPROPERTIES', guid(f'rdq-{idx}'), oh, None, None, [ent], eq)
            sp = [W('IFCPROPERTYSINGLEVALUE', 'Reference', None, Raw(f'IFCIDENTIFIER({sstr(el.name)})'), None),
                  W('IFCPROPERTYSINGLEVALUE', 'IsExternal', None, Raw(f'IFCBOOLEAN({".T." if el.predef == "EXTERNAL" else ".F."})'), None),
                  W('IFCPROPERTYSINGLEVALUE', 'NetPlannedArea', None, Raw(f'IFCAREAMEASURE({freal(area, 2)})'), None)]
            ps2 = W('IFCPROPERTYSET', guid(f'psc-{idx}'), oh, 'Pset_SpaceCommon', None, sp)
            W('IFCRELDEFINESBYPROPERTIES', guid(f'rdc-{idx}'), oh, None, None, [ent], ps2)
        for pn, pv in getattr(el, 'psets', {}).items():
            sp = []
            for k, v in pv.items():
                if isinstance(v, bool):
                    sp.append(W('IFCPROPERTYSINGLEVALUE', k, None, Raw(f'IFCBOOLEAN({".T." if v else ".F."})'), None))
                elif isinstance(v, (int, float)):
                    sp.append(W('IFCPROPERTYSINGLEVALUE', k, None, Raw(f'IFCPOSITIVELENGTHMEASURE({freal(float(v), 1)})'), None))
                else:
                    sp.append(W('IFCPROPERTYSINGLEVALUE', k, None, Raw('IFCLABEL(' + sstr(str(v)) + ')'), None))
            ps2 = W('IFCPROPERTYSET', guid(f'pss-{idx}-{pn}'), oh, pn, None, sp)
            W('IFCRELDEFINESBYPROPERTIES', guid(f'rds-{idx}-{pn}'), oh, None, None, [ent], ps2)
        if getattr(el, 'system', None):
            systems.setdefault(el.system, []).append(ent)
        if el.cls == 'IfcDoor' and el.tag:
            sp = [W('IFCPROPERTYSINGLEVALUE', 'Reference', None, Raw(f'IFCIDENTIFIER({sstr(el.tag)})'), None)]
            ps2 = W('IFCPROPERTYSET', guid(f'psd-{idx}'), oh, 'Pset_DoorCommon', None, sp)
            W('IFCRELDEFINESBYPROPERTIES', guid(f'rdd-{idx}'), oh, None, None, [ent], ps2)

    W('IFCRELAGGREGATES', guid('agg-spaces'), oh, 'Помещения', None, storey, list(spaces_by_room.values()))
    W('IFCRELCONTAINEDINSPATIALSTRUCTURE', guid('contain'), oh, 'Элементы квартиры', None, contained, storey)
    for room, cov in covers.items():
        if room in spaces_by_room:
            W('IFCRELCOVERSSPACES', guid(f'cov-{room}'), oh, None, None, spaces_by_room[room], cov)
    for sname, ents in systems.items():
        code = sname.split(' ')[0]
        pre = SYS_ENUM.get(code) or SYS_ENUM.get(code.rstrip('0123456789')) or 'USERDEFINED'
        sysent = W('IFCDISTRIBUTIONSYSTEM', guid(f'sys-{sname}'), oh, sname, None, sname if pre == 'USERDEFINED' else None,
                   sname, E(pre))
        W('IFCRELASSIGNSTOGROUP', guid(f'sysg-{sname}'), oh, None, None, ents, None, sysent)
        W('IFCRELSERVICESBUILDINGS', guid(f'syss-{sname}'), oh, None, None, sysent, [bld])
    for n, (ms, ents) in mat_rel.items():
        W('IFCRELASSOCIATESMATERIAL', guid(f'mat-{n}'), oh, None, None, ents, ms)
    txt = W.text(path.split('/')[-1], author, org)
    with open(path, 'w', encoding='ascii') as f:
        f.write(txt)
    return dict(entities=len(W.lines), elements=len(contained) + len(spaces_by_room), texmaps=n_tex_maps,
                textures=len(textures), styles=len(styles), materials=len(matdefs))
