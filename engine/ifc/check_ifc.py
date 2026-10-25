# -*- coding: utf-8 -*-
"""Самопроверка IFC: синтаксис STEP, ссылки, число атрибутов, перечисления, обратные связи."""
import re
import sys
from collections import Counter, defaultdict

NATTR = {
    'IFCPERSON': 8, 'IFCORGANIZATION': 5, 'IFCPERSONANDORGANIZATION': 3, 'IFCAPPLICATION': 4, 'IFCOWNERHISTORY': 8,
    'IFCSIUNIT': 4, 'IFCUNITASSIGNMENT': 1, 'IFCCARTESIANPOINT': 1, 'IFCDIRECTION': 1, 'IFCAXIS2PLACEMENT3D': 3,
    'IFCGEOMETRICREPRESENTATIONCONTEXT': 6, 'IFCGEOMETRICREPRESENTATIONSUBCONTEXT': 10, 'IFCPROJECT': 9,
    'IFCLOCALPLACEMENT': 2, 'IFCSITE': 14, 'IFCBUILDING': 12, 'IFCBUILDINGSTOREY': 10, 'IFCRELAGGREGATES': 6,
    'IFCCOLOURRGB': 4, 'IFCSURFACESTYLERENDERING': 9, 'IFCIMAGETEXTURE': 6, 'IFCSURFACESTYLEWITHTEXTURES': 1,
    'IFCSURFACESTYLE': 3, 'IFCMATERIAL': 3, 'IFCSTYLEDITEM': 3, 'IFCSTYLEDREPRESENTATION': 4,
    'IFCMATERIALDEFINITIONREPRESENTATION': 4, 'IFCMATERIALCONSTITUENT': 5, 'IFCMATERIALCONSTITUENTSET': 3,
    'IFCPOLYLINE': 1, 'IFCARBITRARYCLOSEDPROFILEDEF': 3, 'IFCEXTRUDEDAREASOLID': 4, 'IFCCARTESIANPOINTLIST3D': 1,
    'IFCTRIANGULATEDFACESET': 5, 'IFCTEXTUREVERTEXLIST': 1, 'IFCINDEXEDTRIANGLETEXTUREMAP': 4,
    'IFCSHAPEREPRESENTATION': 4, 'IFCPRODUCTDEFINITIONSHAPE': 3, 'IFCSPACE': 11, 'IFCDOOR': 13, 'IFCWINDOW': 13,
    'IFCPROPERTYSINGLEVALUE': 4, 'IFCPROPERTYSET': 5, 'IFCRELDEFINESBYPROPERTIES': 6, 'IFCQUANTITYAREA': 5,
    'IFCQUANTITYLENGTH': 5, 'IFCELEMENTQUANTITY': 6, 'IFCRELCONTAINEDINSPATIALSTRUCTURE': 6, 'IFCRELCOVERSSPACES': 6,
    'IFCRELASSOCIATESMATERIAL': 6, 'IFCDISTRIBUTIONSYSTEM': 7, 'IFCRELASSIGNSTOGROUP': 7, 'IFCRELSERVICESBUILDINGS': 6,
}
for c in ('IFCWALL', 'IFCSLAB', 'IFCCOVERING', 'IFCFURNITURE', 'IFCSANITARYTERMINAL', 'IFCELECTRICAPPLIANCE',
          'IFCAUDIOVISUALAPPLIANCE', 'IFCLIGHTFIXTURE', 'IFCOUTLET', 'IFCSWITCHINGDEVICE', 'IFCUNITARYCONTROLELEMENT',
          'IFCSPACEHEATER', 'IFCUNITARYEQUIPMENT', 'IFCWASTETERMINAL', 'IFCPLATE', 'IFCBUILDINGELEMENTPROXY', 'IFCFAN',
          'IFCCOMMUNICATIONSAPPLIANCE', 'IFCAIRTERMINAL', 'IFCPIPESEGMENT', 'IFCPIPEFITTING', 'IFCDUCTSEGMENT',
          'IFCELECTRICDISTRIBUTIONBOARD', 'IFCVALVE', 'IFCFLOWMETER', 'IFCFILTER', 'IFCCABLESEGMENT'):
    NATTR[c] = 9

ENUMS = {
    'IFCWALL': 'MOVABLE PARAPET PARTITIONING PLUMBINGWALL SHEAR SOLIDWALL STANDARD POLYGONAL ELEMENTEDWALL USERDEFINED NOTDEFINED',
    'IFCSLAB': 'FLOOR ROOF LANDING BASESLAB USERDEFINED NOTDEFINED',
    'IFCCOVERING': 'CEILING FLOORING CLADDING ROOFING MOLDING SKIRTINGBOARD INSULATION MEMBRANE SLEEVING WRAPPING USERDEFINED NOTDEFINED',
    'IFCFURNITURE': 'CHAIR TABLE DESK BED FILECABINET SHELF SOFA USERDEFINED NOTDEFINED',
    'IFCSANITARYTERMINAL': 'BATH BIDET CISTERN SHOWER SINK SANITARYFOUNTAIN TOILETPAN URINAL WASHHANDBASIN WCSEAT USERDEFINED NOTDEFINED',
    'IFCELECTRICAPPLIANCE': 'DISHWASHER ELECTRICCOOKER FREESTANDINGELECTRICHEATER FREESTANDINGFAN FREESTANDINGWATERHEATER '
                            'FREESTANDINGWATERCOOLER FREEZER FRIDGE_FREEZER HANDDRYER KITCHENMACHINE MICROWAVE PHOTOCOPIER '
                            'REFRIGERATOR TUMBLEDRYER VENDINGMACHINE WASHINGMACHINE USERDEFINED NOTDEFINED',
    'IFCAUDIOVISUALAPPLIANCE': 'AMPLIFIER CAMERA DISPLAY MICROPHONE PLAYER PROJECTOR RECEIVER SPEAKER SWITCHER TELEPHONE TUNER USERDEFINED NOTDEFINED',
    'IFCLIGHTFIXTURE': 'POINTSOURCE DIRECTIONSOURCE SECURITYLIGHTING USERDEFINED NOTDEFINED',
    'IFCOUTLET': 'AUDIOVISUALOUTLET COMMUNICATIONSOUTLET POWEROUTLET DATAOUTLET TELEPHONEOUTLET USERDEFINED NOTDEFINED',
    'IFCSWITCHINGDEVICE': 'CONTACTOR DIMMERSWITCH EMERGENCYSTOP KEYPAD MOMENTARYSWITCH SELECTORSWITCH STARTER SWITCHDISCONNECTOR TOGGLESWITCH USERDEFINED NOTDEFINED',
    'IFCUNITARYCONTROLELEMENT': 'ALARMPANEL CONTROLPANEL GASDETECTIONPANEL INDICATORPANEL MIMICPANEL HUMIDISTAT THERMOSTAT WEATHERSTATION USERDEFINED NOTDEFINED',
    'IFCSPACEHEATER': 'CONVECTOR RADIATOR USERDEFINED NOTDEFINED',
    'IFCUNITARYEQUIPMENT': 'AIRHANDLER AIRCONDITIONINGUNIT DEHUMIDIFIER SPLITSYSTEM ROOFTOPUNIT USERDEFINED NOTDEFINED',
    'IFCWASTETERMINAL': 'FLOORTRAP FLOORWASTE GULLYSUMP GULLYTRAP ROOFDRAIN WASTEDISPOSALUNIT WASTETRAP USERDEFINED NOTDEFINED',
    'IFCPLATE': 'CURTAIN_PANEL SHEET USERDEFINED NOTDEFINED',
    'IFCBUILDINGELEMENTPROXY': 'COMPLEX ELEMENT PARTIAL PROVISIONFORVOID PROVISIONFORSPACE USERDEFINED NOTDEFINED',
    'IFCFAN': 'CENTRIFUGALFORWARDCURVED CENTRIFUGALRADIAL CENTRIFUGALBACKWARDINCLINEDCURVED CENTRIFUGALAIRFOIL TUBEAXIAL VANEAXIAL PROPELLORAXIAL USERDEFINED NOTDEFINED',
    'IFCAIRTERMINAL': 'DIFFUSER GRILLE LOUVRE REGISTER USERDEFINED NOTDEFINED',
    'IFCPIPESEGMENT': 'CULVERT FLEXIBLESEGMENT RIGIDSEGMENT GUTTER SPOOL USERDEFINED NOTDEFINED',
    'IFCPIPEFITTING': 'BEND CONNECTOR ENTRY EXIT JUNCTION OBSTRUCTION TRANSITION USERDEFINED NOTDEFINED',
    'IFCDUCTSEGMENT': 'RIGIDSEGMENT FLEXIBLESEGMENT USERDEFINED NOTDEFINED',
    'IFCELECTRICDISTRIBUTIONBOARD': 'CONSUMERUNIT DISTRIBUTIONBOARD MOTORCONTROLCENTRE SWITCHBOARD USERDEFINED NOTDEFINED',
    'IFCVALVE': 'AIRRELEASE ANTIVACUUM CHANGEOVER CHECK COMMISSIONING DIVERTING DRAWOFFCOCK DOUBLECHECK DOUBLEREGULATING FAUCET '
                'FLUSHING GASCOCK GASTAP ISOLATING MIXING PRESSUREREDUCING PRESSURERELIEF REGULATING SAFETYCUTOFF STEAMTRAP STOPCOCK USERDEFINED NOTDEFINED',
    'IFCFLOWMETER': 'ENERGYMETER GASMETER OILMETER WATERMETER USERDEFINED NOTDEFINED',
    'IFCFILTER': 'AIRPARTICLEFILTER COMPRESSEDAIRFILTER ODORFILTER OILFILTER STRAINER WATERFILTER USERDEFINED NOTDEFINED',
    'IFCCABLESEGMENT': 'BUSBARSEGMENT CABLESEGMENT CONDUCTORSEGMENT CORESEGMENT USERDEFINED NOTDEFINED',
    'IFCCOMMUNICATIONSAPPLIANCE': 'ANTENNA COMPUTER FAX GATEWAY MODEM NETWORKAPPLIANCE NETWORKBRIDGE NETWORKHUB PRINTER REPEATER ROUTER SCANNER USERDEFINED NOTDEFINED',
}


def split_args(s):
    out, depth, cur, i, instr = [], 0, [], 0, False
    while i < len(s):
        ch = s[i]
        if instr:
            cur.append(ch)
            if ch == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    cur.append("'"); i += 1
                else:
                    instr = False
        elif ch == "'":
            instr = True; cur.append(ch)
        elif ch == '(':
            depth += 1; cur.append(ch)
        elif ch == ')':
            depth -= 1; cur.append(ch)
        elif ch == ',' and depth == 0:
            out.append(''.join(cur)); cur = []
        else:
            cur.append(ch)
        i += 1
    out.append(''.join(cur))
    if depth != 0 or instr:
        raise ValueError('unbalanced')
    return out


def main(path):
    txt = open(path, encoding='ascii').read()
    assert txt.startswith('ISO-10303-21;') and txt.rstrip().endswith('END-ISO-10303-21;')
    data = txt.split('DATA;', 1)[1].rsplit('ENDSEC;', 1)[0]
    ents = {}
    errors = []
    for line in data.strip().split('\n'):
        m = re.match(r'#(\d+)=([A-Z0-9_]+)\((.*)\);$', line)
        if not m:
            errors.append('syntax: ' + line[:80]); continue
        n, ent, args = int(m.group(1)), m.group(2), m.group(3)
        try:
            a = split_args(args)
        except ValueError:
            errors.append(f'#{n} parens'); continue
        ents[n] = (ent, a, args)
    cnt = Counter(e for e, a, s in ents.values())
    refd = Counter()
    for n, (ent, a, s) in ents.items():
        if ent in NATTR and len(a) != NATTR[ent]:
            errors.append(f'#{n} {ent}: {len(a)} attrs, expected {NATTR[ent]}')
        if ent not in NATTR:
            errors.append(f'#{n} {ent}: unknown entity in check table')
        body = re.sub(r"'(?:[^']|'')*'", "''", s)
        for r in re.findall(r'#(\d+)', body):
            r = int(r)
            refd[r] += 1
            if r not in ents:
                errors.append(f'#{n} -> #{r} missing')
        if ent in ENUMS:
            pre = a[-1].strip('.')
            if pre not in ENUMS[ent].split():
                errors.append(f'#{n} {ent} bad PredefinedType {pre}')
            if pre == 'USERDEFINED' and a[4] == '$':
                errors.append(f'#{n} {ent} USERDEFINED without ObjectType')
    # треугольники: индексы в пределах
    for n, (ent, a, s) in ents.items():
        if ent == 'IFCTRIANGULATEDFACESET':
            cl = int(a[0][1:])
            npts = ents[cl][2].count('),(') + 1
            idx = [int(x) for x in re.findall(r'\d+', a[3])]
            if max(idx) > npts or min(idx) < 1:
                errors.append(f'#{n} index out of range {max(idx)} > {npts}')
        if ent == 'IFCINDEXEDTRIANGLETEXTUREMAP':
            fs = int(a[1][1:]); tv = int(a[2][1:])
            ntri = ents[fs][1][3].count('),(') + 1
            ntc = ents[tv][2].count('),(') + 1
            idx = [int(x) for x in re.findall(r'\d+', a[3])]
            if a[3].count('),(') + 1 != ntri:
                errors.append(f'#{n} texmap tri count mismatch')
            if max(idx) > ntc:
                errors.append(f'#{n} tex index out of range')
    # каждый продукт в пространственной структуре
    contained = set()
    for n, (ent, a, s) in ents.items():
        if ent == 'IFCRELCONTAINEDINSPATIALSTRUCTURE':
            contained |= {int(x) for x in re.findall(r'#(\d+)', a[4])}
        if ent == 'IFCRELAGGREGATES':
            contained |= {int(x) for x in re.findall(r'#(\d+)', a[5])}
    prods = [n for n, (ent, a, s) in ents.items() if ent in ENUMS or ent in ('IFCDOOR', 'IFCWINDOW', 'IFCSPACE')]
    lost = [n for n in prods if n not in contained]
    if lost:
        errors.append(f'{len(lost)} products not contained')
    guids = [a[0] for n, (ent, a, s) in ents.items() if a and re.match(r"^'[0-9A-Za-z_$]{22}'$", a[0])]
    if len(guids) != len(set(guids)):
        errors.append('duplicate GlobalIds')
    print('entities', len(ents), 'errors', len(errors))
    for e in errors[:40]:
        print('  ', e)
    print(sorted(cnt.items(), key=lambda x: -x[1])[:60])
    return errors


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1]) else 0)
