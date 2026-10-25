# -*- coding: utf-8 -*-
"""Лист узлов (принципиальные разрезы)."""
import math
from core import Sheet, tw, BLACK, DARK, MID, LIGHT, WHITE, WALLFILL, mdim
from kit import frame, notes, poly_scan, section_title, wrap
from elev import EV, FV

BLUE = (0.1, 0.35, 0.8)


def hatch(sh, ev, pts, kind):
    P = [ev.P(*p) for p in pts]
    if kind == 'concrete':
        sh.poly(P, fill=(0.88, 0.88, 0.88), lw=0.3, layer='A-DET')
        for a, b in poly_scan(P, 45, 1.4):
            sh.line(a, b, lw=0.12, layer='A-DET', color=MID)
    elif kind == 'screed':
        sh.poly(P, fill=(0.94, 0.93, 0.90), lw=0.25, layer='A-DET')
        for a, b in poly_scan(P, 45, 1.0):
            sh.line(a, b, lw=0.08, layer='A-DET', color=LIGHT, dash=(0.5, 0.5))
    elif kind == 'brick':
        sh.poly(P, fill=(0.93, 0.86, 0.82), lw=0.3, layer='A-DET')
        for a, b in poly_scan(P, 45, 1.2):
            sh.line(a, b, lw=0.12, layer='A-DET', color=(0.6, 0.4, 0.35))
    elif kind == 'gkl':
        sh.poly(P, fill=(0.80, 0.80, 0.80), lw=0.25, layer='A-DET')
    elif kind == 'tile':
        sh.poly(P, fill=(0.30, 0.30, 0.30), lw=0.15, layer='A-DET')
    elif kind == 'wood':
        sh.poly(P, fill=(0.85, 0.72, 0.55), lw=0.25, layer='A-DET')
    elif kind == 'wool':
        sh.poly(P, fill=(0.98, 0.95, 0.78), lw=0.2, layer='A-DET')
        for a, b in poly_scan(P, 60, 1.0):
            sh.line(a, b, lw=0.06, layer='A-DET', color=(0.8, 0.7, 0.4))
    elif kind == 'metal':
        sh.poly(P, fill=(0.25, 0.25, 0.25), lw=0.2, layer='A-DET')
    elif kind == 'fill':
        sh.poly(P, fill=(0.96, 0.92, 0.86), lw=0.2, layer='A-DET')
        for a, b in poly_scan(P, 30, 1.6):
            sh.line(a, b, lw=0.08, layer='A-DET', color=LIGHT, dash=(0.4, 0.8))


def R(sh, ev, s0, z0, s1, z1, kind):
    hatch(sh, ev, [(s0, z0), (s1, z0), (s1, z1), (s0, z1)], kind)


def node_texts(name, items):
    """Тексты выносок узла: album.DETAILS['texts'][узел] = [текст1, текст2, ...] заменяет типовые по порядку."""
    try:
        import album as AL
        t = (getattr(AL, 'DETAILS', None) or {}).get('texts', {}).get(name)
    except ImportError:
        t = None
    if not t:
        return items
    return [(p, t[i] if i < len(t) and t[i] else txt) for i, (p, txt) in enumerate(items)]


def node_params(name, **dflt):
    """Размеры узла: album.DETAILS['params'][узел] поверх значений по умолчанию (реальные толщины объекта)."""
    try:
        import album as AL
        p = (getattr(AL, 'DETAILS', None) or {}).get('params', {}).get(name, {})
    except ImportError:
        p = {}
    d = dict(dflt)
    d.update(p)
    return d


def callouts(sh, ev, items, bx, by_top, step=4.2, list_x=None, list_y=None, width=110):
    """items: [(точка модели, текст)] — номера справа в столбец + список под узлом."""
    for i, (p, txt) in enumerate(items, 1):
        P = ev.P(*p)
        B = (bx, by_top - (i - 1) * step)
        sh.circle(P, 0.4, lw=0.1, layer='A-TEXT', fill=BLACK)
        sh.line(P, (B[0] - 1.8, B[1]), lw=0.15, layer='A-TEXT')
        sh.circle(B, 1.7, lw=0.25, layer='A-TEXT', fill=WHITE)
        sh.text(B, str(i), h=1.5, ha='c', va='m', layer='A-TEXT')
    if list_x is not None:
        y = list_y
        for i, (p, txt) in enumerate(items, 1):
            lines = wrap(txt, width - 5, 1.7)
            sh.text((list_x, y), f'{i}.', h=1.7, layer='A-TEXT')
            for ln in lines:
                sh.text((list_x + 4, y), ln, h=1.7, layer='A-TEXT')
                y -= 2.6
            y -= 0.3
        return y


def detail_drain(sh, X, Y):
    k = 10.0
    ev = EV(X, Y, k)
    P = node_params('drain', bt=150, body=110)
    bt, body = P['bt'], P['body']
    R(sh, ev, -200, -bt - 50, 0, 450, 'brick')
    R(sh, ev, 0, -bt - 50, 600, -bt, 'concrete')
    hatch(sh, ev, [(0, -bt), (600, -bt), (600, 2), (110, -6), (110, -20), (0, -20)], 'screed')
    R(sh, ev, 20, -body, 100, -20, 'metal')
    R(sh, ev, 100, -body + 15, 170, -body + 50, 'metal')
    R(sh, ev, 15, -20, 105, 0, 'metal')
    hatch(sh, ev, [(110, -6), (600, 2), (600, 12), (110, 4)], 'tile')
    R(sh, ev, 0, 0, 10, 450, 'tile')
    sh.poly([ev.P(-4, 430), ev.P(-4, -22), ev.P(600, -8)], closed=False, lw=0.5, layer='A-DET', color=BLUE, dash=(1.2, 0.6))
    fv = FV(ev)
    mdim(sh, fv, 'x', [-bt - 50, -bt, -20, 0], 650, ext=600, h=1.7)
    items = [((-100, 250), 'Стена, штукатурка'), ((5, 350), 'Плитка С5 на клею'),
             ((-4, 150), 'Гидроизоляция обмазочная, лента в углу, на стены 200 (в душе до +2,000)'),
             ((60, -10), 'Решётка трапа (сталь чёрн. / под плитку)'), ((135, -body + 32), 'Трап линейный низкий, выпуск Ø50'),
             ((350, -bt * 0.4), 'Стяжка армированная, уклон 1,5–2 % к трапу'), ((400, 7), 'П4 600×600 R11 на клею'),
             ((400, -bt - 25), 'Плита перекрытия')]
    items = node_texts('drain', items)
    callouts(sh, ev, items, X + 72, Y + 40, list_x=X - 22, list_y=Y - 26, width=118)
    section_title(sh, X - 22, Y + 50, 'Узел 1. Линейный трап у стены', 'М 1:10', h=2.4)


def detail_curtain(sh, X, Y):
    k = 10.0
    ev = EV(X, Y, k)
    P = node_params('curtain', nd=150, nw=210)
    nd, sw = P['nd'], 240 + P['nw']
    R(sh, ev, -200, nd, sw + 200, nd + 150, 'concrete')
    R(sh, ev, sw, -500, sw + 200, nd, 'brick')
    R(sh, ev, -200, -12, 240, 0, 'gkl')
    R(sh, ev, -200, 0, 240, 28, 'metal')
    R(sh, ev, 228, -12, 240, nd, 'gkl')
    R(sh, ev, sw - 130, nd - 35, sw - 40, nd - 5, 'metal')
    for xx in (sw - 110, sw - 60):
        sh.line(ev.P(xx, nd - 35), ev.P(xx, -450), lw=0.4, layer='A-DET', color=(0.6, 0.5, 0.4), dash=(2.0, 1.0))
    R(sh, ev, 250, nd - 35, 300, nd - 10, 'metal')
    fv = FV(ev)
    mdim(sh, fv, 'y', [240, sw], -560, ext=-12, h=1.7)
    mdim(sh, fv, 'x', [0, nd], -270, ext=-200, h=1.7)
    items = [((0, nd + 70), 'Плита перекрытия, низ ≈ +3,150'), ((100, -6), 'ГКЛ 12,5 на подвесном каркасе, +3,000'),
             ((234, round(nd * 8 / 15)), 'Стенка ниши ГКЛ, окраска'), ((sw - 85, nd - 20), 'Скрытый карниз (2 ряда)'),
             ((275, nd - 22), 'LED-лента подсветки штор'), ((sw + 100, -250), 'Наружная стена, окно')]
    items = node_texts('curtain', items)
    callouts(sh, ev, items, X + 72, Y + 30, list_x=X - 22, list_y=Y - 62, width=118)
    section_title(sh, X - 22, Y + 40, 'Узел 2. Ниша для скрытого карниза', 'М 1:10', h=2.4)


def detail_cove(sh, X, Y):
    k = 10.0
    ev = EV(X, Y, k)
    P = node_params('cove', cw=100, ch=110, void=150)
    cw, ch, vd = P['cw'], P['ch'], P['void']
    R(sh, ev, -250, vd, 600, vd + 150, 'concrete')
    R(sh, ev, -250, -550, 0, vd, 'brick')
    R(sh, ev, 0, -550, 18, 0, 'wood')
    R(sh, ev, cw, -12, 600, 0, 'gkl')
    R(sh, ev, cw, 0, 600, 28, 'metal')
    R(sh, ev, cw - 12, -12, cw, ch, 'gkl')
    R(sh, ev, 25, ch - 15, 65, ch + 5, 'metal')
    for dx in (-10, 80):
        sh.poly([ev.P(45, ch - 15), ev.P(dx, -350)], closed=False, lw=0.3, layer='A-DET', color=(1.0, 0.7, 0.2), dash=(1.0, 0.6))
    fv = FV(ev)
    mdim(sh, fv, 'y', [0, cw], -620, ext=-12, h=1.7)
    items = [((300, -6), 'ГКЛ потолок +3,000'), ((9, -300), 'Панели С2 (МДФ) / стена'),
             ((45, ch - 5), 'LED-лента в профиле с рассеивателем, 2700 K'), ((cw - 6, 50), 'Стенка ниши ГКЛ, окраска'),
             ((200, vd + 70), 'Плита перекрытия')]
    items = node_texts('cove', items)
    callouts(sh, ev, items, X + 72, Y + 30, list_x=X - 25, list_y=Y - 68, width=118)
    section_title(sh, X - 25, Y + 40, 'Узел 3. Световая ниша', 'М 1:10', h=2.4)


def detail_threshold(sh, X, Y):
    k = 10.0
    ev = EV(X, Y, k)
    P = node_params('threshold', slab=180, layers=[(-450, -180, 0, -40, 'fill'), (-450, -40, 0, -20, 'gkl'),
                                                    (-450, -20, -50, -10, 'screed'), (-450, -10, -50, 0, 'tile'),
                                                    (0, -180, 450, 5, 'screed'), (0, 5, 450, 20, 'tile')])
    sl = P['slab']
    R(sh, ev, -450, -sl - 150, 450, -sl, 'concrete')
    for x0_, z0_, x1_, z1_, kd in P['layers']:
        R(sh, ev, x0_, z0_, x1_, z1_, kd)
    R(sh, ev, -50, -20, 0, 20, 'tile')
    sh.poly([ev.P(450, -2), ev.P(0, -2), ev.P(0, -sl)], closed=False, lw=0.5, layer='A-DET', color=BLUE, dash=(1.2, 0.6))
    R(sh, ev, -25, 30, 15, 300, 'wood')
    fv = FV(ev)
    mdim(sh, fv, 'x', [-sl, 0, 20], 520, ext=450, h=1.7)
    items = [((-250, -5), 'П3 керамогранит, коридор ±0,000'), ((250, 12), 'П4, санузел +0,020'),
             ((-25, 10), 'Порог — фаска из плитки, перепад 20'),
             ((250, -round(sl * 5 / 9)), 'Стяжка армир. + гидроизоляция (на стены 200)'),
             ((-250, -round(sl * 2 / 3)), 'Сухая стяжка: засыпка + ГВЛ'),
             ((-5, 150), 'Полотно скрытой двери (условно)')]
    items = node_texts('threshold', items)
    callouts(sh, ev, items, X + 60, Y + 30, list_x=X - 45, list_y=Y - 42, width=118)
    section_title(sh, X - 45, Y + 40, 'Узел 4. Порог санузла', 'М 1:10', h=2.4)


def detail_joint(sh, X, Y):
    k = 10.0
    ev = EV(X, Y, k)
    P = node_params('joint', slab=180, dims=[-180, -40, 0],
                    layers=[(-450, -180, 450, -40, 'fill'), (-450, -40, 450, -20, 'gkl'), (-450, -20, -4, -10, 'screed'),
                            (-450, -10, -4, 0, 'tile'), (4, -20, 450, -15, 'screed'), (4, -15, 450, 0, 'wood')])
    sl = P['slab']
    R(sh, ev, -450, -sl - 150, 450, -sl, 'concrete')
    for x0_, z0_, x1_, z1_, kd in P['layers']:
        R(sh, ev, x0_, z0_, x1_, z1_, kd)
    R(sh, ev, -4, -30, 4, 0, 'metal')
    fv = FV(ev)
    mdim(sh, fv, 'x', P['dims'], 520, ext=450, h=1.7)
    items = [((-250, -5), 'П3 керамогранит на клею'), ((250, -7), 'П1/П2 инженерная доска 15 на клею'),
             ((0, -15), 'Т-профиль в уровень по оси полотна'), ((-250, -round(sl * 5 / 9)), 'Сухая стяжка: засыпка + ГВЛ 2×10'),
             ((300, -sl - 80), 'Плита перекрытия')]
    items = node_texts('joint', items)
    callouts(sh, ev, items, X + 60, Y + 30, list_x=X - 45, list_y=Y - 42, width=118)
    section_title(sh, X - 45, Y + 40, 'Узел 5. Стык покрытий в проёме', 'М 1:10', h=2.4)


def detail_box(sh, X, Y):
    k = 20.0
    ev = EV(X, Y, k)
    P = node_params('box', t=400, d=200, L=1340)
    t, d, L = P['t'], P['d'], P['L']
    m = L / 2
    c = P.get('c', m - 230)                 # ось унитаза (канализация Ø110) от начала короба
    R(sh, ev, -t, 0, 0, L, 'brick')
    R(sh, ev, 0, 0, d - 25, L, 'wool')
    for zz in (0, m - 30, L - 50):
        R(sh, ev, d - 80, zz, d - 30, zz + 50, 'metal')
    R(sh, ev, d - 25, 0, d, L, 'gkl')
    R(sh, ev, d, 0, d + 10, L, 'tile')
    R(sh, ev, 30, c - 250, 140, c + 250, 'metal')
    sh.circle(ev.P(85, c), 55 / k, lw=0.3, layer='A-DET', fill=WHITE)
    fv = FV(ev)
    mdim(sh, fv, 'y', [-t, 0, d], -150, ext=0, h=1.7)
    items = [((85, c + 160), 'Рама инсталляции, крепление к стене'), ((90, m + 330), 'Звукоизоляция минвата 50'),
             ((d - 12, m + 480), 'ГКЛВ 2×12,5 + гидроизоляция'), ((d + 5, m - 370), 'Плитка С4/С5'),
             ((85, c), 'Канализация Ø110 к стояку'), ((-t / 2, m + 230), 'Наружная стена')]
    items = node_texts('box', items)
    callouts(sh, ev, items, X + 30, Y + 66, list_x=X + 40, list_y=Y + 66, width=78)
    section_title(sh, X - 22, Y + 78, 'Узел 6. Короб инсталляции (план)', 'М 1:20', h=2.4)


NODES = {'drain': detail_drain, 'curtain': detail_curtain, 'cove': detail_cove, 'threshold': detail_threshold,
         'joint': detail_joint, 'box': detail_box}
DETAILS_DEFAULT = dict(
    nodes=[('drain', 48, 236), ('curtain', 175, 246), ('cove', 305, 246), ('threshold', 70, 110), ('joint', 205, 110),
           ('box', 312, 72)],
    notes=['Узлы — принципиальные; толщины слоёв уточняются по выбранным системам (сухая стяжка, трап, профили, карнизы).'],
)


def sheet_details(no, total):
    try:
        import album as AL
        cfg = getattr(AL, 'DETAILS', None) or DETAILS_DEFAULT
    except ImportError:
        cfg = DETAILS_DEFAULT
    sh = Sheet('25', 'Узлы')
    for name, x, y in cfg['nodes']:
        NODES[name](sh, x, y)
    notes(sh, 25, 28, 195, 'Примечания', cfg.get('notes', []), h=1.8, lead=2.7)
    frame(sh, no, total, 'Узлы')
    return sh
