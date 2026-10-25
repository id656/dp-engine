# Данные объекта — справочник полей

Все файлы — Python-модули в `objects/<объект>/`. Образцы: полный — `objects/dp-01-2026-ai`, минимальный — `objects/_template`.
Единицы: мм; z — мм от ±0,000 (чистый пол жилых помещений). Координаты плана: **x — вниз по листу, y — вправо**.

## project.py
`PROJECT = dict(cipher, object, section, object_lines=(2 строки в штамп), city='г. …', year, date, rev, status)`.
Шифр: `ДП-NN-ГГГГ-АИ` (NN — номер объекта бюро). `rev` — строка редакции (номер берёт `tools/cover.py`).

## bureau/bureau.py (общий для всех объектов)
`stage` (ДП), `designer` (Демиденко Д.), `drafter` (Якубовский Н.), `author`, `logo` (в штамп и на титул),
`logo_cover` (на всю страницу), `logo_aspect`, контакты бюро. Объект может переопределить любое поле в `project.py`.

## obmer.py — существующее положение
| Поле | Формат | Примечание |
|---|---|---|
| `WALLS` | `[(x0, y0, x1, y1), …]` | прямоугольники стен; проёмы — разрывы; толщины реальные |
| `SHAFT` | `(x0, y0, x1, y1)` или `None` | шахта (крест на планах) |
| `ROOMS` | `{'01': dict(poly=[(x, y), …]), …}` | контуры помещений по граням стен, ортогональные |
| `poly_area` | функция | копировать из шаблона |
| `DOORS` | `{ключ: dict(h=(x, y), c=(dx, dy), o=(dx, dy), L=…)}` | существующие двери: h — петля, c — полотно закрыто (вдоль стены), o — сторона открывания |
| `OBMER_DOORS` | список ключей | двери на обмерном плане |
| `GLAZING` | список | необязательно: `('window', a, b, c_in, c_out[, 'x'])`, `('line', p, q, kw)`, `('rect', r, kw)` |
| `OUTER_DIMS`, `INNER_DIMS` | `[(ось, [значения], положение, выносные), …]` | необязательно; ось 'y' — цепочка по y (горизонтально на листе) на линии x = положение |

## design.py — решения (источник правды)
**Общее:** `FLOOR_BUILDUP` (пирог пола от чернового), `ROUGH_H`, `ROUGH_CEIL`, `WET_FLOOR`, `SILL`, `WIN_TOP`, `DOOR_H`,
`NCS = {'wall': …, 'accent': …, 'ceil': …}`.

**ROOM** `{'01': dict(...)}`: `name`, `ceil` (отметка потолка или None — существующий), `floor` (код покрытия),
`level` (отметка чистого пола или None — уточнить), `zone` ('day' | 'night' | 'wet' | 'out'), `ceil_code` ('Пт1'…),
`plinth` (True — плинтус ПЛ), необязательно: `finish_note`, `walls_note`, `params_note`, `elev_notes` (список),
`count` (False — не входит в площадь). Помещения 'out' (балкон/лоджия) в площадь квартиры не входят.
`AREA = {k: poly_area(v['poly']) for k, v in ROOMS.items()}`.

**Двери:** `DOORS` (проектные, формат как в обмере), `DOOR_LIST` (порядок), `DOOR_TYPES` (типы: mark, keys, name,
opening, leaf, finish, qty, note, col), `DOOR_MARK`, `DOOR_SCHED` (вычисляются как в образце; `_WHERE`, `_SWING` — словами).

**Окна:** `WINDOWS = {ключ: dict(room, wall=('x'|'y', координата грани), a, b, z0, z1)}`.
**OPENINGS** (необязательно; иначе выводится): `dict(kind='door'|'window'|'bdoor', key, axis, c0, c1, a, b, z0, z1, mark,
clad={'01': 'С3'})` — c0..c1 толщина стены, a..b проём вдоль стены; `clad` — полотно облицовано со стороны помещения.

**RWALLS** (необязательно): `{'02': [('А', pL, pR), …]}` — стены развёрток по часовой от входа; pL→pR слева направо при
взгляде изнутри (внутренняя нормаль справа от направления). `RWALLS_PARAMS` — стены только для привязок в md (балкон).

**ITEMS** — мебель и оборудование: `dict(key, room, kind, rect=(x0, y0, x1, y1) | c=(x, y), z=(низ, верх), pos, name, …)`.
Виды (kind) и доп. поля:
- шкафы/хранение: `wardrobe` (along='x'|'y', doors, mat='front'|'walnut'|'oak'), `shelving` (mat), `wallshelf` (shelves=2),
  `bench`, `console`, `nightstand`, `tvconsole`, `desk` (mat), `wm_cab` (label, words=(2 слова)), `box` (короб ГКЛ)
- кухня: `kitchen_run` (side='W'|'E'|'S'|'N' — у какой стены; modules=[(a, b, 'tech'|'sink'|'dw'|'hob'|'drawers')],
  a..b — вдоль стены), `upper` (side, hood=(a, b)), `column` (label, words, inner=[(z0, z1, 'холодильник'|'ДШ'|'СВЧ')]), `filler`
- мягкая мебель/столы: `bed` (head='N'|'S'|'W'|'E'), `bed_single`, `sofa` (back), `table`, `coffee`, `chair` (c, ang), `round` (c, r), `lounge`
- сантехника у стены: `wc`, `vanity` (width, depth), `mini_basin` — `wall='W'|'E'|'S'|'N'`, `face` (координата стены/короба),
  `axis` (ось вдоль стены); `towel`, `glass`, `drain`, `shower` (c — точка на стене), `mirror`, `mirror_oval`
- прочее: `tv` (label='ТВ 55"'), `radiator`, `ac` (pos='К1'), `rug`
Стороны W/E/S/N: W — стена с меньшим x (верх листа), E — с большим x (низ), S — меньший y (лево), N — больший y (право).

**LIGHTS:** `dict(room, kind, p=(x, y) | a=…, b=…, z, g='03а', note, wall='x'|'y', n=(…), style='bar')`;
kind: spot, spot44, spot65, pend, track (a, b), led (a, b, z), linear (a, b), sconce, wall44, fan, mirrorled.
**GROUPS** `{'03а': 'Помещение — назначение'}`; «сенсор»/«датчик» в описании — группа без выключателя.

**POINTS** (электроточки): `dict(id, room, kind, p (на грани стены), n (внутрь), z (низ рамки), g=[группы] для выключателей,
note, hidden=True — в мебели, tag='К' для выводов)`; kind: v1, v2, v1p, v2p, tr, r1, r2, r2u, r1w, r2w, pow, out, tvblock,
medblock, deskblock, shk, ssh, int. Терморегуляторы: `g=['ТП05']`.

**PLUMB:** `dict(room, kind='hvs'|'gvs'|'k50'|'k110'|'tap'|'sif', p, n (None — в полу), z, fx='С3 раковина', note, frame=True —
на раме инсталляции)`. `RISERS = [dict(kind, p, label)]`, `SEWER_ROUTES`, `PRESS_ROUTES`, `WATER_ROUTES` — `[(точки, подпись)]`.

**Отделка:** `FINISH {код: текст}`; `MATERIALS {код: dict(tex, col, tw, th, style, sw_real, elev_fill, short, reserve,
plan_axis, like, step, slat, gradient)}` — необязательно (иначе по тексту); `DOOR_LEAF_FINISH`;
`WALL_ZONES [(пом., стена, s0, s1, z0, z1, код)]` — 'X' = закрыто встроенной мебелью; `WALL_DEFAULT {пом.: код | None}`;
`EXTRA_WALL_AREAS [(пом., 'код (что)', м²)]`; `TILE_LAYOUT [(пом., стена, s0, s1, z0, z1, tw, th, s_начала, z_начала)]`;
`FLOOR_TILES [(пом., контур, tw, th, x0, y0)]`.

**Тёплые полы:** `HEAT [dict(room, w=Вт/м², tr='id терморегулятора', excl=[прямоугольники])]`.
**Потолки:** `CEIL_FEATURES [dict(kind='niche'|'cove'|'hatch', room, rect, note)]`, `TRACKS [dict(room, rect, note)]`.
**Вентиляция:** `VENT [dict(kind='duct', pts, d, note) | dict(kind='valve', p, n, room, note) | dict(kind='acroute', pts, room, note)]`, `HOOD`.

## annot.py — оформление планов (всё необязательно)
`PLAN_VIEW = dict(X0, Y0[, k])`, `SCHEME_VIEW`, `TAG_NONAME`, `TAGS = {'default'|'fur'|'cei'|'lgt'|'swi'|'out'|'plb'|'dor'|'design': {пом.: (x, y)}}`,
листы: `OBMER` (labels, names, tags, expl, notes, subtitle), `DEMO` (doors, areas, openings, bubbles, rows, notes),
`MOUNT` (boxes, openings, narrow, dims, bubbles, rows, notes), `FURN` (words: (точка, текст, h, 'rod'|'eq', поворот), notes),
`FLOORS` (fill, patterns, excl, thresholds, levels, axes, dirs, code_pos, legend_names, notes_build, notes_layout),
`HEATS` (labels, notes), `CEIL` (fill, labels, bubbles, vent_labels, builtin_labels, dims, subtitle, notes_marks, notes),
`LIGHT` (dims, notes, legend), `SWITCH` (dims, notes_extra), `OUTLET` (wall_off, offs, skip, dims, rows, notes_extra),
`PLUMB_SHEET` (draw — упорядоченный список ('label'|'dim'|'bubble'|'level'|'line'|'rect', …), frag, frag_labels, frag_dims,
frag_text, notes), `DOORS_SHEET` (marks, notes), `VENT_SHEET` (labels, marks, rows, notes), `ELEC_NOTES`.
Подпись: `(точка, текст, h[, dict(color='brown', ha='l', rot=90, font=…)])`.

## texts.py — тексты (всё необязательно)
`DESIGN_MATERIALS [(код, подпись)]`, `STYLE`, `GENERAL` (общие указания), `CHECKS [(проверка, решение, статус)]`,
`REFS`, `FINISH_NOTES`, `MATERIALS_NOTES`, `SANT [(поз., пом., наименование, кол.)]`, `SANT_OUTPUTS`, `SANT_NOTES`,
`LTYPES [(вид, (марка, наименование, ед.))]`, `LIGHTS_NOTES`, `EUI_NOTES`, `COMMON_MD` (шаблон 00-obshchee.md;
плейсхолдеры — ключи NCS и `{finishes}`).

## album.py — состав и листы помещений
`sheets()` → список `(ключ, наименование, функция(no, total) -> Sheet)`; без неё — типовой состав.
Помощники движка: `assemble.common_sheets()`, `assemble.room_sheets(ELEV_SHEETS, VIZ_ROOMS)`,
`elev.auto_room_sheets(room)`, `elev.elevation(sh, room, 'А', X0, Y0, k, levels='right'|'left'|None, vdim_off)`,
`elev.key_plan`, `elev.finish_legend`, `elev.elev_legend`, `floorplan.wet_floor`, `kit.notes`, `kit.frame`.
`KEYPLAN_OFF {пом.: отступ букв}`, `WET_FLOOR {пом.: dict(slopes, slope_text, dims, levels, texts, shaft)}`,
`DETAILS = dict(nodes=[(узел, x, y)], notes=[…], texts={узел: [тексты выносок]})`; узлы: drain, curtain, cove, threshold, joint, box.

## vizcfg.py — визуализации
`CAMS {пом.: (x, y, направление центра панорамы, град)}`, `VIEWS {пом.: [dict(yaw, hfov, vt=(низ, верх), cap)] ×3}`,
`STRIPS [(пом., yaw) ×4]` — полосы титула (без балкона), `VIZ_ROOMS` — помещения с листами визуализаций.
Исходники: `photos/src_<пом>.jpg` — равнопромежуточные панорамы 2:1 (свои рендеры или фото заказчика).
