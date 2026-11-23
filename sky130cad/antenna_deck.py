"""Pegasus antenna deck for sky130 (cf. GPDK045 pvs/pvlAnt.rul), from SkyWater's antenna rules
(docs/rules/antenna.rst, table Ig: S8P12-10R / S8PIR-10R, the sky130 process).

  python3 sky130.py antenna-deck      -> WORK/drc/sky130_antenna.pvl (+ tests in antenna-validate)

EGAR = EA / A_gate - K x A_diode - bonus <= MAX_EGAR, evaluated per net with the connectivity
that exists when each layer is etched (`incr_conn yes`, connects in process order):

  layer   EA                       MAX_EGAR   K    diode bonus
  poly    perimeter x 0.18 um      50         -    -
  licon   cut area (on poly)       3          -    -
  li1     perimeter x 0.10 um      75         450  -
  mcon    cut area                 3          18   -
  met1/2  perimeter x 0.35 um      400        400  2200
  via/2   cut area                 6          36   -
  met3/4  perimeter x 0.80 um      400        400  2200
  via3/4  cut area                 6          36   -
  met5    perimeter x 1.20 um      400        400  2200

- A_gate: gate (poly AND diff) area on the net.
- AntennaDiode = (diff OR tap) NOT (poly OR pAntennaShort); pAntennaShort = (tap NOT poly) NOT nwell.
- Nets connected to a pAntennaShort are not checked (ar.1).
- The diode bonus applies once any diode is on the net.
"""
import os

from .drc_deck import LAYERS

METALS = [  # (layer, below, cut, FLT um, cut layer for next, ...)
    ('met1', 'li1', 'mcon', 0.35), ('met2', 'met1', 'via', 0.35), ('met3', 'met2', 'via2', 0.80),
    ('met4', 'met3', 'via3', 0.80), ('met5', 'met4', 'via4', 1.20),
]


def text():
    L = ['// sky130 antenna checks for Pegasus, written by sky130cad/antenna_deck.py from SkyWater',
         '// antenna rules (table Ig, S8PIR-10R). Run on a full layout: pegasus -drc ... sky130_antenna.pvl',
         'results_db -drc "sky130_antenna.drc_errors.ascii" -ascii;', 'max_results -drc all;', 'unit -length u;',
         'text_depth -primary;', 'incr_conn yes;', '']
    for i, (name, layer, dt) in enumerate(LAYERS):
        L += ['layer_def %s %d;' % (name, 1000 + i), 'layer_map %d -datatype %d %d;' % (layer, dt, 1000 + i)]
    L += ['',
          'and poly diff gate;',
          'or diff tap difftap;',
          'not tap poly ptap_np;',
          'not ptap_np nwell pshort;',                      # pAntennaShort
          'or poly pshort poly_or_pshort;',
          'not difftap poly_or_pshort antdiode;',           # AntennaDiode
          'and licon difftap licon_d;',
          'not licon difftap licon_nd;',
          'and licon_nd poly licon_p;',
          '']
    excl = '!area(pshort) * '
    bonus = lambda: ' - 2200 * (1 - !area(antdiode))'
    L += ['rule ant.poly {',
          '    caption ant.poly: poly sidewall area (perimeter x 0.18) / gate area > 50;',
          '    connect poly gate;',
          '    antenna poly gate -gt 50 -expr "perimeter(poly) * 0.18 / area(gate)";',
          '}',
          'rule ant.licon {',
          '    caption ant.licon: poly licon area / gate area > 3;',
          '    connect poly licon_p;',
          '    antenna licon_p gate -gt 3 -expr "area(licon_p) / area(gate)";',
          '}',
          'rule ant.li {',
          '    caption ant.li: li1 sidewall (perimeter x 0.10) / gate - 450 x diode area > 75;',
          '    connect li1 poly -by licon_p;',
          '    connect li1 antdiode -by licon_d;',
          '    connect li1 pshort -by licon_d;',
          '    antenna li1 antdiode pshort gate -gt 75 -expr "%s(perimeter(li1) * 0.10 / area(gate) - 450 * area(antdiode))";'
          % excl,
          '}',
          'rule ant.mcon {',
          '    caption ant.mcon: mcon area / gate - 18 x diode area > 3;',
          '    connect li1 mcon;',
          '    antenna mcon antdiode pshort gate -gt 3 -expr "%s(area(mcon) / area(gate) - 18 * area(antdiode))";' % excl,
          '}']
    for metal, below, cut, flt in METALS:
        L += ['rule ant.%s {' % metal,
              '    caption ant.%s: %s sidewall (perimeter x %.2f) / gate - 400 x diode area - 2200 > 400;'
              % (metal, metal, flt),
              '    connect %s %s -by %s;' % (metal, below, cut),
              '    antenna %s antdiode pshort gate -gt 400 -expr "%s(perimeter(%s) * %.2f / area(gate) - 400 * area(antdiode)%s)";'
              % (metal, excl, metal, flt, bonus()),
              '}']
        nxt = {'met1': 'via', 'met2': 'via2', 'met3': 'via3', 'met4': 'via4'}.get(metal)
        if nxt:
            L += ['rule ant.%s {' % nxt,
                  '    caption ant.%s: %s area / gate - 36 x diode area > 6;' % (nxt, nxt),
                  '    connect %s %s;' % (metal, nxt),
                  '    antenna %s antdiode pshort gate -gt 6 -expr "%s(area(%s) / area(gate) - 36 * area(antdiode))";'
                  % (nxt, excl, nxt),
                  '}']
    return '\n'.join(L) + '\n'


def write(dst):
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    t = text()
    open(dst, 'w').write(t)
    return t.count('\nrule ')


# ---------------------------------------------------------------- test layouts

def cases():
    """[(label, expected rule or None, shapes)] using drc_tests.R rectangles (um)."""
    from .drc_tests import R

    def nfet(x, y):          # 0.15 x 0.42 gate (0.063 um2): diff, implant, poly crossing
        return [R('diff', x, y, x + 0.8, y + 0.42), R('nsdm', x - 0.13, y - 0.13, x + 0.93, y + 0.55),
                R('poly', x + 0.325, y - 0.13, x + 0.475, y + 0.9)]
    out = []
    # poly: 0.15 x 9 um poly arm on the gate -> perimeter 18.3 um x 0.18 / 0.063 = 52 > 50
    out.append(('f:ant.poly', 'ant.poly', nfet(1, 1) + [R('poly', 1.325, 1.8, 1.475, 10.8)]))
    out.append(('p:ant.poly', None, nfet(1, 1) + [R('poly', 1.325, 1.8, 1.475, 7.0)]))
    # met1: 0.14 x 40 um met1 line on the gate (poly pad + licon + li + mcon)
    pad = lambda x, y: [R('poly', x + 0.2, y + 0.9, x + 0.6, y + 1.3), R('licon', x + 0.315, y + 1.015, x + 0.485, y + 1.185),
                        R('npc', x + 0.215, y + 0.915, x + 0.585, y + 1.285), R('li1', x + 0.23, y + 0.93, x + 0.57, y + 1.27),
                        R('mcon', x + 0.315, y + 1.015, x + 0.485, y + 1.185)]
    m1 = lambda x, y, length: [R('met1', x + 0.25, y + 0.95, x + 0.25 + length, y + 1.25)]
    out.append(('f:ant.met1', 'ant.met1', nfet(1, 1) + pad(1, 1) + m1(1, 1, 40)))
    out.append(('p:ant.met1', None, nfet(1, 1) + pad(1, 1) + m1(1, 1, 30)))
    # the same 40 um line with a 1 um2 antenna diode (n+ diff, licon, li to the line): legal
    diode = [R('diff', 3, 3, 4, 4), R('nsdm', 2.87, 2.87, 4.13, 4.13), R('licon', 3.415, 3.415, 3.585, 3.585),
             R('li1', 3.3, 2.0, 3.7, 3.7), R('li1', 1.23, 2.0, 3.7, 2.27), R('li1', 1.23, 1.93, 1.57, 2.27)]
    out.append(('p:ant.met1_diode', None, nfet(1, 1) + pad(1, 1) + m1(1, 1, 40) + diode))
    return out


def write_tests(gds, tsv):
    """One case per 50 um slot; returns the case list."""
    from . import drc_tests
    shapes, rows = [], []
    for i, (label, expect, sh) in enumerate(cases()):
        ox = i * 50.0
        for layer, pts in sh:
            shapes.append((layer, [(x + ox, y) for x, y in pts]))
        rows.append('%d\t%s\t%s\t%g\t%g' % (i, label, expect or '-', ox, 0))
    drc_tests.write_gds(gds, 'antenna_tests', shapes)
    open(tsv, 'w').write('\n'.join(rows) + '\n')
    return cases()


def check(tsv, errors):
    from . import drc_tests
    errs = drc_tests.read_errors(errors)
    hits = {}
    for rule, x, y in errs:
        hits.setdefault(int(x // 50.0), set()).add(rule)
    bad = 0
    for line in open(tsv).read().split('\n'):
        if not line:
            continue
        i, label, expect, _, _ = line.split('\t')
        got = hits.get(int(i), set())
        ok = (not got) if expect == '-' else (expect in got)
        bad += not ok
        print('%-4s %-22s expect %-10s got %s' % ('ok' if ok else 'FAIL', label, expect, ', '.join(sorted(got)) or '-'))
    return bad
