#!/usr/bin/env python3
"""Write a Pegasus (PVL) DRC deck for SkyWater sky130 in the GPDK045 pvlDRC.rul style.

  python3 sky130.py drc-deck            -> WORK/drc/sky130_full.pvl
  pegasus -drc -dp 4 -gds X.gds -top_cell TOP WORK/drc/sky130_full.pvl

Rule names and values follow the SkyWater periphery rules as encoded in
efabless/mpw_precheck sky130A_mr.drc and open_pdks sky130.lydrc (sky130_drc/README.md).
Structure follows Cadence's GPDK045 pvs/pvlDRC.rul:
`rule NAME { caption ...; inte|exte|enc|area ... -output region -singular -abut lt 90; }`.
Not implemented (listed in the deck header): density, antenna, latch-up tap distance,
licon.12 (flagged NC, not checked, by SkyWater), area-id (core/sc/ce) relaxations and
resistor/varactor/ESD/HV-specific rules. nwell.4 is a block-level rule: standalone cells
without a tap fail it by design.
Validated by sky130cad/drc_tests.py (`sky130.py drc-validate`): one deliberate violation
per rule plus legal geometry at exact limits, and every fd_sc cell.
"""
import os

OPT = '-output region -singular -abut lt 90'

LAYERS = [  # name, gds layer, datatype
    ('dnwell', 64, 18), ('nwell', 64, 20), ('diff', 65, 20), ('tap', 65, 44),
    ('poly', 66, 20), ('licon', 66, 44), ('npc', 95, 20), ('nsdm', 93, 44), ('psdm', 94, 20),
    ('hvtp', 78, 44), ('lvtn', 125, 44), ('hvi', 75, 20), ('li1', 67, 20), ('mcon', 67, 44),
    ('met1', 68, 20), ('via', 68, 44), ('met2', 69, 20), ('via2', 69, 44), ('met3', 70, 20),
    ('via3', 70, 44), ('met4', 71, 20), ('via4', 71, 44), ('met5', 72, 20), ('pad', 76, 20),
    ('areaid_sc', 81, 4), ('areaid_ce', 81, 2),
]

DERIVED = [
    'or diff tap difftap',
    'and poly diff gate',
    'and diff psdm pdiff', 'and diff nsdm ndiff', 'and tap nsdm ntap', 'and tap psdm ptap',
    'and licon diff licon_diff', 'and licon tap licon_tap', 'and licon poly licon_poly',
    'not poly diff poly_field',
    'or poly difftap polydifftap',
    'and difftap nsdm ndifftap', 'and difftap psdm pdifftap',
    'or nsdm psdm npsdm', 'and nsdm psdm bothimp',
    'not diff gate sd',
]

# (name, caption, body-lines)
RULES = []


def r(name, caption, *body):
    RULES.append((name, caption, body))


def width(layer, value, name):
    r(name, '%s: min. %s width : %gum' % (name, layer, value), 'inte %s %s -lt %g %s' % (layer, layer, value, OPT))


def space(layer, value, name):
    r(name, '%s: min. %s spacing : %gum' % (name, layer, value), 'exte %s %s -lt %g %s' % (layer, layer, value, OPT))


def sep(a, b, value, name, what, opts=OPT):
    r(name, '%s: %s : %gum' % (name, what, value), 'exte %s %s -lt %g %s' % (a, b, value, opts))


def enc(inner, outer, value, name, what):
    r(name, '%s: %s : %gum' % (name, what, value), 'enc %s %s -lt %g %s -outside_also' % (inner, outer, value, OPT))


def area(layer, value, name):
    r(name, '%s: min. %s area : %gum2' % (name, layer, value), 'area %s -lt %g' % (layer, value))


def holes(layer, value, name):
    r(name, '%s: min. %s hole area : %gum2' % (name, layer, value), 'holes %s -lt %g' % (layer, value))


def covered(inner, outer, name, what):
    r(name, '%s: %s' % (name, what), 'not %s %s' % (inner, outer))


def wide_space(layer, w, value, name):
    # Spacing to metal wider than w (shrink/grow keeps only regions wider than w).
    h = w / 2.0
    r(name, '%s: min. spacing to %s wider than %gum : %gum' % (name, layer, w, value),
      'size %s -by -%g %s_n%s' % (layer, h, layer, name.replace('.', '_')),
      'size %s_n%s -by %g %s_w%s' % (layer, name.replace('.', '_'), h, layer, name.replace('.', '_')),
      'exte %s_w%s %s -lt %g %s' % (layer, name.replace('.', '_'), layer, value, OPT))


def cut_size(layer, size, name):
    r(name + '_a', '%s_a: min. %s width : %gum' % (name, layer, size), 'inte %s %s -lt %g %s' % (layer, layer, size, OPT))
    r(name + '_b', '%s_b: %s must be a %gum square' % (name, layer, size), 'area -not %s -eq %g' % (layer, round(size * size, 6)))


def corner_enc(inner, outer, value, size, name, what):
    """SkyWater "enclosure by one of two adjacent edges": a cut corner fails when both edges
    meeting there have less than `value` enclosure next to that corner (efabless li.5
    form: deficient edge segments meeting at a corner). The 5 nm corner square of each cut
    (cut AND shifted copies) is grown `value` outward along each edge; both probes must
    lie inside `outer`. (Pegasus 25.1 `grow` takes no negative values.)
    """
    t = name.replace('.', '_')
    k = round(size - 0.005, 4)
    body = ['select -interact %s %s %s_in' % (inner, outer, t)]
    for side, dx, dy in (('b', 0, -k), ('t', 0, k), ('l', -k, 0), ('r', k, 0)):
        body += ['shift -xy %g %g %s_in %s_s%s' % (dx, dy, t, t, side),
                 'and %s_in %s_s%s %s_e%s' % (t, t, side, t, side)]  # 5 nm strip along `side`
    corners = []
    for v, h in (('b', 'l'), ('b', 'r'), ('t', 'l'), ('t', 'r')):
        c = '%s_%s%s' % (t, v, h)
        body.append('and %s_e%s %s_e%s %s_q' % (t, v, t, h, c))  # 5 nm corner square
        src = t + '_in'
        for n, side in enumerate((h, v)):
            direction = {'l': 'left', 'r': 'right', 'b': 'bottom', 't': 'top'}[side]
            dst = c if n else c + '_h'
            body += ['grow %s_q -%s %g %s_p%s' % (c, direction, value, c, side),
                     'select -inside -not %s_p%s %s %s_x%s' % (c, side, outer, c, side),
                     'select -interact %s %s_x%s %s' % (src, c, side, dst)]
            src = dst
        corners.append(c)
    body += ['or %s %s %s_o1' % (corners[0], corners[1], t), 'or %s %s %s_o2' % (corners[2], corners[3], t),
             'or %s_o1 %s_o2' % (t, t)]
    r(name, '%s: %s : %gum' % (name, what, value), *body)


# --- grid and angles (PVL captions run to the end of the line: one statement per line)
r('x.1b_offgrid', 'x.1b: OFFGRID vertex, 0.005um grid', 'layout_input -offgrid')
r('x.3a_angle', 'x.3a: non 45 degree angle', 'layout_input -skew')
r('x.acute', 'x.acute: acute angle', 'layout_input -acute')
for _l in ('diff', 'tap', 'poly', 'licon', 'mcon', 'via', 'via2', 'via3', 'via4'):
    r('x.2_' + _l, 'x.2: non 90 degree angle on ' + _l, 'angle %s -ltgt 0 90' % _l)
# --- FEOL: wells, diffusion, poly, implants --------------------------------------
width('nwell', 0.84, 'nwell.1'); space('nwell', 1.27, 'nwell.2a')
width('diff', 0.15, 'difftap.1'); width('tap', 0.15, 'difftap.1_c'); space('difftap', 0.27, 'difftap.3')
enc('pdiff', 'nwell', 0.18, 'difftap.8', 'min. p+diff enclosure by nwell')
sep('ndiff', 'nwell', 0.34, 'difftap.9', 'min. n+diff spacing to nwell')
enc('ntap', 'nwell', 0.18, 'difftap.10', 'min. n+tap enclosure by nwell')
sep('ptap', 'nwell', 0.13, 'difftap.11', 'min. p+tap spacing to nwell')
width('poly', 0.15, 'poly.1a'); space('poly', 0.21, 'poly.2')
# Field poly touches diff at every gate end: facing edges only, no -abut (open_pdks uses
# projection and drops zero-area results for the same reason).
sep('poly_field', 'diff', 0.075, 'poly.4', 'min. poly on field spacing to diff',
    '-metric opposite -output region -singular')
sep('poly_field', 'tap', 0.055, 'poly.5', 'min. poly on field spacing to tap')
width('npc', 0.27, 'npc.1'); space('npc', 0.27, 'npc.2')
width('nsdm', 0.38, 'nsdm.2'); space('nsdm', 0.38, 'nsdm.1')
width('psdm', 0.38, 'psdm.2'); space('psdm', 0.38, 'psdm.1')
width('hvtp', 0.38, 'hvtp.1'); space('hvtp', 0.38, 'hvtp.2')
width('lvtn', 0.38, 'lvtn.1a'); space('lvtn', 0.38, 'lvtn.2')
# --- licon -------------------------------------------------------------------
cut_size('licon', 0.17, 'licon.1'); space('licon', 0.17, 'licon.2')
covered('licon', 'li1', 'licon.4', 'licon must be covered by li1')
covered('licon', 'polydifftap', 'licon.4b', 'licon must be on poly, diff or tap')
enc('licon_diff', 'diff', 0.04, 'licon.5', 'min. diff enclosure of licon')
enc('licon_poly', 'poly', 0.05, 'licon.8', 'min. poly enclosure of licon')
sep('licon_diff', 'gate', 0.05, 'licon.11a', 'min. licon spacing to gate (std-cell value)')
sep('licon_poly', 'difftap', 0.19, 'licon.14', 'min. poly licon spacing to difftap')
r('licon.9', 'licon.9: min. poly licon spacing to psdm, no overlap : 0.11um',
  'exte licon_poly psdm -lt 0.11 %s licon_9_s' % OPT, 'and licon_poly psdm licon_9_o', 'or licon_9_s licon_9_o')
# --- well taps, implants, contact placement (SkyWater periphery rules) --------------
# nwell.4: every n-well must contain a metal-contacted tap (the rule checks licon on tap).
# Standalone standard cells fail it by design: their taps are in separate tap cells.
r('nwell.4', 'nwell.4: every nwell must contain a contacted tap (licon on tap)',
  'select -interact -not nwell licon_tap')
# n/psd.5a/5b: implant enclosure of diff/tap 0.125 except at butting edges (an edge touching
# diff/tap of the opposite implant); n/psd.7: implant to opposite-implant diff/tap 0.13
# (touching, i.e. butting, edges are not measured).
for imp, kind, diffl, tapl, opp in (('nsdm', 'nsd', 'ndiff', 'ntap', 'pdifftap'),
                                    ('psdm', 'psd', 'pdiff', 'ptap', 'ndifftap')):
    for sub, inner, what in (('5a', diffl, 'diff'), ('5b', tapl, 'tap')):
        name = '%s.%s' % (kind, sub)
        tmp = name.replace('.', '_') + '_e'
        r(name, '%s: min. %s enclosure of %s except butting edges : 0.125um' % (name, imp, what),
          'enc %s %s -lt 0.125 %s -outside_also %s' % (inner, imp, OPT, tmp),
          'select -interact -not %s %s' % (tmp, opp))
    r(kind + '.7', '%s.7: min. %s spacing to opposite-implant diff/tap : 0.13um' % (kind, imp),
      'exte %s %s -lt 0.13 -output region -singular' % (imp, opp))
r('npsd.8', 'n/psd.8: nsdm and psdm must not overlap diff/tap of opposite doping', 'and bothimp difftap')
r('npsd.9', 'n/psd.9: diff and tap must be enclosed by nsdm or psdm', 'not difftap npsdm')
area('nsdm', 0.265, 'nsd.10a')
area('psdm', 0.255, 'psd.10b')
holes('nsdm', 0.265, 'nsd.11')
holes('psdm', 0.265, 'psd.11')
# licon.15/.16/.18. licon.12 (max S/D width without licon) is flagged NC (not checked) by
# SkyWater and is not implemented. licon.16 for diffusion: a source/drain region next to
# exactly one gate (an end region) must hold a licon; regions between two gates are
# series-stack nodes, which standard cells leave uncontacted.
enc('licon_poly', 'npc', 0.1, 'licon.15', 'min. npc enclosure of poly licon')
r('licon.16', 'licon.16: every tap and every end source/drain region must enclose a licon',
  'select -interact -not tap licon licon_16_t', 'select -interact sd gate -eq 1 licon_16_e',
  'select -interact -not licon_16_e licon licon_16_s', 'or licon_16_t licon_16_s')
r('licon.18', 'licon.18: npc must enclose a poly licon', 'select -interact -not npc licon_poly')
# --- li1 / mcon ----------------------------------------------------------------
width('li1', 0.17, 'li.1'); space('li1', 0.17, 'li.3'); area('li1', 0.0561, 'li.6')
corner_enc('licon', 'li1', 0.08, 0.17, 'li.5', 'min. li enclosure of licon on one of 2 adjacent edges')
cut_size('mcon', 0.17, 'ct.1'); space('mcon', 0.19, 'ct.2')
covered('mcon', 'li1', 'ct.4', 'mcon must be covered by li1')
covered('mcon', 'met1', 'm1.4_a', 'mcon must be enclosed by met1')
enc('mcon', 'met1', 0.03, 'm1.4', 'min. met1 enclosure of mcon')
corner_enc('mcon', 'met1', 0.06, 0.17, 'm1.5', 'min. met1 enclosure of mcon on one of 2 adjacent edges')
# --- metals and vias -----------------------------------------------------------
for m, w, s, wide, ws, a, h, prefix in [
        ('met1', 0.14, 0.14, 3.0, 0.28, 0.083, 0.14, 'm1'),
        ('met2', 0.14, 0.14, 3.0, 0.28, 0.0676, 0.14, 'm2'),
        ('met3', 0.30, 0.30, 3.0, 0.40, 0.240, 0.20, 'm3'),
        ('met4', 0.30, 0.30, 3.0, 0.40, 0.240, 0.20, 'm4')]:
    width(m, w, prefix + '.1'); space(m, s, prefix + '.2')
    wide_space(m, wide, ws, prefix + '.3ab')
    area(m, a, prefix + '.6'); holes(m, h, prefix + '.7')
width('met5', 1.6, 'm5.1'); space('met5', 1.6, 'm5.2'); area('met5', 4.0, 'm5.4')
cut_size('via', 0.15, 'via.1a'); space('via', 0.17, 'via.2')
covered('via', 'met1', 'via.4a_a', 'via must be enclosed by met1')
enc('via', 'met1', 0.055, 'via.4a', 'min. met1 enclosure of via')
corner_enc('via', 'met1', 0.085, 0.15, 'via.5a', 'min. met1 enclosure of via on one of 2 adjacent edges')
covered('via', 'met2', 'm2.4_a', 'via must be enclosed by met2')
enc('via', 'met2', 0.055, 'm2.4', 'min. met2 enclosure of via')
corner_enc('via', 'met2', 0.085, 0.15, 'm2.5', 'min. met2 enclosure of via on one of 2 adjacent edges')
cut_size('via2', 0.20, 'via2.1a'); space('via2', 0.20, 'via2.2')
covered('via2', 'met2', 'via2.4_a', 'via2 must be enclosed by met2')
enc('via2', 'met2', 0.04, 'via2.4', 'min. met2 enclosure of via2')
corner_enc('via2', 'met2', 0.085, 0.2, 'via2.5', 'min. met2 enclosure of via2 on one of 2 adjacent edges')
covered('via2', 'met3', 'm3.4_a', 'via2 must be enclosed by met3')
enc('via2', 'met3', 0.065, 'm3.4', 'min. met3 enclosure of via2')
cut_size('via3', 0.20, 'via3.1'); space('via3', 0.20, 'via3.2')
covered('via3', 'met3', 'via3.4_a', 'via3 must be enclosed by met3')
enc('via3', 'met3', 0.06, 'via3.4', 'min. met3 enclosure of via3')
corner_enc('via3', 'met3', 0.09, 0.2, 'via3.5', 'min. met3 enclosure of via3 on one of 2 adjacent edges')
covered('via3', 'met4', 'm4.3_a', 'via3 must be enclosed by met4')
enc('via3', 'met4', 0.065, 'm4.3', 'min. met4 enclosure of via3')
cut_size('via4', 0.80, 'via4.1'); space('via4', 0.80, 'via4.2')
covered('via4', 'met4', 'via4.4_a', 'via4 must be enclosed by met4')
enc('via4', 'met4', 0.19, 'via4.4', 'min. met4 enclosure of via4')
covered('via4', 'met5', 'm5.3_a', 'via4 must be enclosed by met5')
enc('via4', 'met5', 0.31, 'm5.3', 'min. met5 enclosure of via4')


def write(dst):
    lines = ['// SkyWater sky130 DRC for Pegasus, generated by sky130cad/drc_deck.py.',
           '// Values: SkyWater periphery rules via efabless sky130A_mr.drc / open_pdks sky130.lydrc.',
           '// Style: Cadence GPDK045 pvs/pvlDRC.rul.',
           '// Not implemented: density, antenna, latch-up tap distance, licon.12 (NC), area-id',
           '// relaxations, resistor/varactor/ESD/HV rules. nwell.4 applies to blocks, not lone cells.',
           'results_db -drc "sky130_full.drc_errors.ascii" -ascii;',
           'max_results -drc all;', 'grid 5;', 'unit -length u;', 'text_depth -primary;', 'flag -nonsimple yes;', '',
           '']
    for i, (name, layer, dt) in enumerate(LAYERS):
        lines += ['layer_def %s %d;' % (name, 1000 + i), 'layer_map %d -datatype %d %d;' % (layer, dt, 1000 + i)]
    lines.append('')
    lines += [d + ';' for d in DERIVED]
    lines.append('')
    for name, caption, body in RULES:
        lines.append('rule %s {' % name)
        lines.append('    caption %s;' % caption.replace(';', ','))
        lines += ['    %s;' % b for b in body]
        lines.append('}')
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    open(dst, 'w').write('\n'.join(lines) + '\n')
    return len(RULES)

