#!/usr/bin/env python3
"""Write a GDS of DRC test cases for the deck from drc_deck.py and check Pegasus results.

  used by `sky130.py drc-validate`: write(OUT.gds, OUT_cases.tsv), then check(TSV, REPORT)

Each case sits in its own 12 um slot of one flat top cell `drc_tests`.
`f:<rule>` slots hold one deliberate violation of <rule>; `p:<name>` slots hold legal
geometry at exactly the rule limits and must be clean. `check` maps every reported
error to its slot and prints a pass/fail line per case. No third-party modules.
"""
import struct
import sys

LAYERS = {'dnwell': (64, 18), 'nwell': (64, 20), 'diff': (65, 20), 'tap': (65, 44),
          'poly': (66, 20), 'licon': (66, 44), 'npc': (95, 20), 'nsdm': (93, 44), 'psdm': (94, 20),
          'hvtp': (78, 44), 'lvtn': (125, 44), 'li1': (67, 20), 'mcon': (67, 44),
          'met1': (68, 20), 'via': (68, 44), 'met2': (69, 20), 'via2': (69, 44), 'met3': (70, 20),
          'via3': (70, 44), 'met4': (71, 20), 'via4': (71, 44), 'met5': (72, 20)}
PITCH = 12.0
COLS = 16


def R(layer, x0, y0, x1, y1):
    return (layer, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


# ---------------------------------------------------------------- GDSII writer

def _rec(rtype, dtype, data=b''):
    return struct.pack('>HBB', 4 + len(data), rtype, dtype) + data


def _str(rtype, s):
    b = s.encode()
    if len(b) % 2:
        b += b'\0'
    return _rec(rtype, 6, b)


def _real8(x):
    if x == 0:
        return b'\0' * 8
    sign = 0x80 if x < 0 else 0
    x = abs(x)
    e = 64
    while x >= 1:
        x /= 16.0
        e += 1
    while x < 1 / 16.0:
        x *= 16.0
        e -= 1
    m = int(round(x * 2 ** 56))
    if m >= 2 ** 56:
        m //= 16
        e += 1
    return bytes([sign | e]) + m.to_bytes(7, 'big')


def write_gds(path, top, shapes):
    date = struct.pack('>12h', 2026, 11, 17, 0, 0, 0, 2026, 11, 17, 0, 0, 0)
    out = [_rec(0x00, 2, struct.pack('>h', 600)), _rec(0x01, 2, date), _str(0x02, 'drc_tests'),
           _rec(0x03, 5, _real8(1e-3) + _real8(1e-9)), _rec(0x05, 2, date), _str(0x06, top)]
    for layer, pts in shapes:
        ln, dt = LAYERS[layer]
        xy = [(int(round(x * 1000)), int(round(y * 1000))) for x, y in pts]
        xy.append(xy[0])
        out += [_rec(0x08, 0), _rec(0x0D, 2, struct.pack('>h', ln)), _rec(0x0E, 2, struct.pack('>h', dt)),
                _rec(0x10, 3, b''.join(struct.pack('>ii', x, y) for x, y in xy)), _rec(0x11, 0)]
    out += [_rec(0x07, 0), _rec(0x04, 0)]
    open(path, 'wb').write(b''.join(out))


# ---------------------------------------------------------------- test cases
CASES = []  # (label, expected rule or None, shapes in slot coordinates)


def case(label, expect, shapes):
    CASES.append((label, expect, shapes))


def f(rule, *shapes):
    case('f:' + rule, rule, list(shapes))


def p(name, *shapes):
    case('p:' + name, None, list(shapes))


def metal_pad(layer, cx, cy, size, elr, etb, min_area, min_w, tail_up=False):
    """Metal around a square cut at (cx, cy) with given enclosures, plus a tail for area."""
    w = max(size + 2 * elr, min_w)
    elr = (w - size) / 2.0
    h = size + 2 * etb
    tail = max(0.0, round((min_area * 1.3 / w - h) / 0.005) * 0.005 + 0.005)
    if tail_up:
        return R(layer, cx - elr, cy - etb, cx + size + elr, cy + size + etb + tail)
    return R(layer, cx - elr, cy - etb - tail, cx + size + elr, cy + size + etb)


E = 0.13  # implant enclosure used in legal cases (rule n/psd.5: 0.125)


def imp(layer, x0, y0, x1, y1, e=E):
    return R(layer, x0 - e, y0 - e, x1 + e, y1 + e)


def contact(x, y):
    """licon at (x, y) with li1 0.08 past it left/right and 0.1 top/bottom."""
    return [R('licon', x, y, x + 0.17, y + 0.17), R('li1', x - 0.08, y - 0.1, x + 0.25, y + 0.27)]


def ctap(x0, y0, x1, y1, implant):
    """Contacted tap: tap, implant, and a licon + li1 in its centre (licon.16, nwell.4)."""
    cx = round(((x0 + x1) / 2 - 0.085) / 0.005) * 0.005
    cy = round(((y0 + y1) / 2 - 0.085) / 0.005) * 0.005
    return [R('tap', x0, y0, x1, y1), imp(implant, x0, y0, x1, y1)] + contact(cx, cy)


def poly_contact(x, y, enc=0.1):
    """licon on poly with npc `enc` around it (licon.15/.18)."""
    return [R('licon', x, y, x + 0.17, y + 0.17), R('li1', x - 0.08, y - 0.1, x + 0.25, y + 0.27),
            R('npc', x - enc, y - enc, x + 0.17 + enc, y + 0.17 + enc)]


# Basic single-layer width/spacing rules.
for layer, w, s, wrule, srule in [
        ('nwell', 0.84, 1.27, 'nwell.1', 'nwell.2a'), ('poly', 0.15, 0.21, 'poly.1a', 'poly.2'),
        ('npc', 0.27, 0.27, 'npc.1', 'npc.2'), ('nsdm', 0.38, 0.38, 'nsdm.2', 'nsdm.1'),
        ('psdm', 0.38, 0.38, 'psdm.2', 'psdm.1'), ('hvtp', 0.38, 0.38, 'hvtp.1', 'hvtp.2'),
        ('lvtn', 0.38, 0.38, 'lvtn.1a', 'lvtn.2'), ('li1', 0.17, 0.17, 'li.1', 'li.3'),
        ('met1', 0.14, 0.14, 'm1.1', 'm1.2'), ('met2', 0.14, 0.14, 'm2.1', 'm2.2'),
        ('met3', 0.30, 0.30, 'm3.1', 'm3.2'), ('met4', 0.30, 0.30, 'm4.1', 'm4.2'),
        ('met5', 1.60, 1.60, 'm5.1', 'm5.2')]:
    L = 4.0 if layer != 'met5' else 6.0
    f(wrule, R(layer, 1, 1, 1 + w - 0.01, 1 + L))
    f(srule, R(layer, 1, 1, 3, 1 + L), R(layer, 3 + s - 0.01, 1, 5 + s, 1 + L))
    if layer == 'nwell':
        # each n-well also needs a contacted n+ tap (nwell.4)
        p('nwell_ws', R('nwell', 1, 1, 1.84, 5), R('nwell', 3.11, 1, 5.11, 5),
          *(ctap(1.18, 2, 1.66, 3, 'nsdm') + ctap(3.3, 2, 4.0, 3, 'nsdm')))
    elif layer == 'npc':
        # 0.27-wide arms; each npc also holds a poly contact (licon.15/.18) in a wider body
        p('npc_ws', R('npc', 1, 1, 1.27, 5), R('npc', 1, 4.4, 1.6, 5.0), R('poly', 1.13, 4.53, 1.47, 4.87),
          R('npc', 1.54, 1, 1.81, 3.9), R('npc', 1.54, 3.3, 2.14, 3.9), R('poly', 1.67, 3.43, 2.01, 3.77),
          *(poly_contact(1.215, 4.615, 0.215) + poly_contact(1.755, 3.515, 0.215)))
    else:
        p(layer + '_ws', R(layer, 1, 1, 1 + w, 1 + L), R(layer, 1 + w + s, 1, 3 + w + s, 1 + L))
f('difftap.1', R('diff', 1, 1, 1.14, 3))
f('difftap.1_c', R('tap', 1, 1, 1.14, 3))
f('difftap.3', R('diff', 1, 1, 2, 2), R('diff', 2.26, 1, 3.26, 2))
p('difftap_ws', R('diff', 1, 1, 1.15, 3), R('diff', 1.42, 1, 2.42, 3), imp('nsdm', 1, 1, 2.42, 3))
# Well / implant interactions.
f('difftap.8', R('nwell', 0.5, 0.5, 4.5, 4.5), R('diff', 0.6, 1, 1.6, 2), R('psdm', 0.5, 0.6, 2.1, 2.4))
f('difftap.9', R('nwell', 3, 0.5, 7, 4.5), R('diff', 1, 1, 2.67, 2), R('nsdm', 0.5, 0.6, 2.67, 2.4))
f('difftap.10', R('nwell', 0.5, 0.5, 4.5, 4.5), R('tap', 0.6, 1, 1.6, 2), R('nsdm', 0.5, 0.6, 2.1, 2.4))
f('difftap.11', R('nwell', 3, 0.5, 7, 4.5), R('tap', 1, 1, 2.88, 2), R('psdm', 0.5, 0.6, 2.88, 2.4))
p('well_implant', R('nwell', 0.5, 0.5, 4.5, 4.5), R('diff', 0.68, 1, 1.68, 2), R('psdm', 0.5, 0.6, 2.1, 2.4),
  *(ctap(2.5, 1, 3.5, 2, 'nsdm') + [R('diff', 4.84, 1, 5.84, 2), R('nsdm', 4.71, 0.87, 5.97, 2.13)] +
    ctap(4.63, 2.6, 5.63, 3.6, 'psdm')))
f('poly.4', R('diff', 1, 1, 3, 3), R('poly', 3.07, 1, 3.57, 3))
f('poly.5', R('tap', 1, 1, 3, 3), R('poly', 3.05, 1, 3.55, 3))
p('poly_field', R('diff', 1, 1, 3, 3), imp('nsdm', 1, 1, 3, 3), R('poly', 3.075, 1, 3.575, 3),
  *(ctap(5, 1, 7, 3, 'psdm') + [R('poly', 7.055, 1, 7.555, 3)]))


# Contacts on diffusion/poly: a legal licon at (x, y) on a 1x1 diff.
def licon_diff(x, y, size=(0.17, 0.17), li=True, diff=True):
    sx, sy = size
    s = [R('licon', x, y, x + sx, y + sy)]
    if diff:
        s.append(R('diff', x - 0.4, y - 0.4, x + sx + 0.4, y + sy + 0.4))
        s.append(imp('nsdm', x - 0.4, y - 0.4, x + sx + 0.4, y + sy + 0.4))
    if li:
        s.append(R('li1', x - 0.08, y - 0.1, x + sx + 0.08, y + sy + 0.1))
    return s


f('licon.1_a', *licon_diff(2, 2, (0.16, 0.16)))
f('licon.1_b', *licon_diff(2, 2, (0.17, 0.34)))
f('licon.2', *(licon_diff(2, 2) + licon_diff(2.33, 2)))
p('licon_pair', *(licon_diff(2, 2, li=False) + licon_diff(2.34, 2, li=False) +
                  [R('li1', 1.92, 1.9, 2.59, 2.27)]))
f('licon.4', *licon_diff(2, 2, li=False))
f('licon.4b', *licon_diff(2, 2, diff=False))
f('licon.5', R('diff', 1, 1, 2, 2), R('licon', 1.03, 1.4, 1.2, 1.57), R('li1', 0.95, 1.3, 1.28, 1.67))
p('licon.5', R('diff', 1, 1, 2, 2), imp('nsdm', 1, 1, 2, 2), R('licon', 1.04, 1.4, 1.21, 1.57),
  R('li1', 0.96, 1.3, 1.29, 1.67))
f('licon.8', R('poly', 1, 1, 1.25, 2), R('licon', 1.04, 1.4, 1.21, 1.57), R('li1', 0.96, 1.3, 1.29, 1.67))
p('licon.8', R('poly', 1, 1, 1.27, 2), *poly_contact(1.05, 1.4))
f('licon.11a', R('diff', 1, 1, 3, 2), R('poly', 1.5, 0.7, 1.65, 2.3), R('licon', 1.69, 1.4, 1.86, 1.57),
  R('li1', 1.61, 1.3, 1.94, 1.67))
p('licon.11a', R('diff', 1, 1, 3, 2), imp('nsdm', 1, 1, 3, 2), R('poly', 1.5, 0.7, 1.65, 2.3),
  *(contact(1.70, 1.4) + contact(1.2, 1.4)))
f('licon.14', R('poly', 1, 1, 1.42, 2), R('licon', 1.2, 1.4, 1.37, 1.57), R('li1', 1.12, 1.3, 1.45, 1.67),
  R('diff', 1.55, 1, 2.5, 2))
p('licon.14', R('poly', 1, 1, 1.42, 2), *(poly_contact(1.2, 1.4) +
                                         [R('diff', 1.56, 1, 2.5, 2), imp('nsdm', 1.56, 1, 2.5, 2)]))
f('li.6', R('li1', 1, 1, 1.17, 1.3))
p('li.6', R('li1', 1, 1, 1.17, 1.335))
f('li.5', R('diff', 1, 1, 3, 3), R('licon', 2, 2, 2.17, 2.17), R('li1', 2, 2, 2.25, 2.25))
p('li.5', R('diff', 1, 1, 3, 3), imp('nsdm', 1, 1, 3, 3), R('licon', 2, 2, 2.17, 2.17),
  R('li1', 1.92, 2, 2.25, 2.17), R('li1', 1.92, 1.8, 2.25, 2.0))

# li1 enclosure that is short only part-way along an edge (as in fd_sc_hs mux2i_1): legal.
p('li.5_partial', R('diff', 3.0, 0.2, 4.2, 1.2), imp('nsdm', 3.0, 0.2, 4.2, 1.2), R('licon', 3.43, 0.41, 3.6, 0.58),
  R('li1', 2.0, 0.35, 3.68, 0.52), R('li1', 3.395, 0.35, 3.68, 1.01))
# The same li1 without the bar: short left and bottom segments meet at the corner.
case('f:li.5_corner', 'li.5', [R('diff', 3.0, 0.2, 4.2, 1.2), R('licon', 3.43, 0.41, 3.6, 0.58),
                               R('li1', 3.395, 0.35, 3.68, 1.01)])

# Well taps (nwell.4), implants (n/psd.*), contact placement (licon.15/.16/.18).
f('nwell.4', R('nwell', 0.5, 0.5, 3.5, 3.5), R('diff', 1, 1, 2, 2), imp('psdm', 1, 1, 2, 2))
case('f:nsd.5a', 'nsd.5a', [R('diff', 1, 1, 2, 2), R('nsdm', 0.9, 0.87, 2.13, 2.13)])
p('nsd.5a', R('diff', 1, 1, 2, 2), R('nsdm', 0.875, 0.875, 2.125, 2.125))
case('f:psd.5a', 'psd.5a', [R('nwell', 0.3, 0.3, 4.5, 2.7), R('diff', 1, 1, 2, 2), R('psdm', 0.9, 0.87, 2.13, 2.13)]
     + ctap(3, 1, 3.6, 2, 'nsdm'))
p('psd.5a', R('nwell', 0.3, 0.3, 4.5, 2.7), R('diff', 1, 1, 2, 2), R('psdm', 0.875, 0.875, 2.125, 2.125),
  *ctap(3, 1, 3.6, 2, 'nsdm'))
case('f:nsd.5b', 'nsd.5b', [R('nwell', 0.5, 0.5, 2.5, 2.5), R('tap', 1, 1, 2, 2), R('nsdm', 0.9, 0.87, 2.13, 2.13)]
     + contact(1.415, 1.415))
p('nsd.5b', R('nwell', 0.5, 0.5, 2.5, 2.5), R('tap', 1, 1, 2, 2), R('nsdm', 0.875, 0.875, 2.125, 2.125),
  *contact(1.415, 1.415))
case('f:psd.5b', 'psd.5b', [R('tap', 1, 1, 2, 2), R('psdm', 0.9, 0.87, 2.13, 2.13)] + contact(1.415, 1.415))
p('psd.5b', R('tap', 1, 1, 2, 2), R('psdm', 0.875, 0.875, 2.125, 2.125), *contact(1.415, 1.415))
# butting p-diff / n-tap: implant enclosure 0 and implants touching at the shared edge (legal)
p('implant_butting', R('nwell', 0.5, 0.5, 3.6, 2.6), R('diff', 1, 1, 2, 2), R('psdm', 0.875, 0.875, 2.0, 2.125),
  R('tap', 2, 1, 3, 2), R('nsdm', 2.0, 0.875, 3.125, 2.125), *contact(2.415, 1.415))
f('nsd.7', R('diff', 1, 1, 2, 2), R('nsdm', 0.87, 0.87, 2.15, 2.13), R('tap', 2.27, 1, 3.27, 2),
  R('psdm', 2.15, 0.87, 3.4, 2.13), *contact(2.685, 1.415))
p('nsd.7', R('diff', 1, 1, 2, 2), R('nsdm', 0.87, 0.87, 2.14, 2.13), R('tap', 2.27, 1, 3.27, 2),
  R('psdm', 2.14, 0.87, 3.4, 2.13), *contact(2.685, 1.415))
f('psd.7', R('diff', 1, 1, 2, 2), R('nsdm', 0.87, 0.87, 2.13, 2.13), R('tap', 2.27, 1, 3.27, 2),
  R('psdm', 2.12, 0.87, 3.4, 2.13), *contact(2.685, 1.415))
f('npsd.8', R('diff', 1, 1, 2, 2), imp('nsdm', 1, 1, 2, 2), imp('psdm', 1, 1, 2, 2))
f('npsd.9', R('diff', 1, 1, 2, 2))
f('nsd.10a', R('nsdm', 1, 1, 1.4, 1.6))
p('nsd.10a', R('nsdm', 1, 1, 1.4, 1.7))
f('psd.10b', R('psdm', 1, 1, 1.4, 1.6))
p('psd.10b', R('psdm', 1, 1, 1.4, 1.65))
for impl, kind in (('nsdm', 'nsd'), ('psdm', 'psd')):
    f(kind + '.11', R(impl, 1, 1, 3, 1.8), R(impl, 1, 2.2, 3, 3), R(impl, 1, 1, 1.8, 3), R(impl, 2.2, 1, 3, 3))
    p(kind + '.11', R(impl, 1, 1, 3, 1.725), R(impl, 1, 2.275, 3, 3), R(impl, 1, 1, 1.725, 3), R(impl, 2.275, 1, 3, 3))
f('licon.15', R('poly', 1, 1, 1.27, 2), *poly_contact(1.05, 1.4, 0.09))
case('f:licon.16_tap', 'licon.16', [R('tap', 1, 1, 2, 2), imp('psdm', 1, 1, 2, 2)])
case('f:licon.16_sd', 'licon.16', [R('diff', 1, 1, 3, 2), imp('nsdm', 1, 1, 3, 2), R('poly', 1.9, 0.7, 2.05, 2.3)]
     + contact(2.3, 1.4))
# series stack: the node between two gates has no contact (legal); both end regions do
p('licon.16_series', R('diff', 1, 1, 4, 2), imp('nsdm', 1, 1, 4, 2), R('poly', 1.6, 0.7, 1.75, 2.3),
  R('poly', 2.6, 0.7, 2.75, 2.3), *(contact(1.2, 1.4) + contact(3.0, 1.4)))
f('licon.18', R('npc', 1, 1, 1.5, 1.5))
f('licon.9', R('poly', 1, 1, 1.27, 2), *(poly_contact(1.05, 1.4) + [R('psdm', 1.0, 1.67, 2.0, 2.3)]))
case('f:licon.9_overlap', 'licon.9', [R('poly', 1, 1, 1.27, 2), R('psdm', 0.6, 0.6, 1.6, 2.4)] + poly_contact(1.05, 1.4))
p('licon.9', R('poly', 1, 1, 1.27, 2), *(poly_contact(1.05, 1.4) + [R('psdm', 1.0, 1.68, 2.0, 2.3)]))

# Cut layers between metals: (cut, size, space, lower, lower enc, lower adj, upper, upper enc,
# upper adj, rule names).
MINS = {'li1': (0.0561, 0.17), 'met1': (0.083, 0.14), 'met2': (0.0676, 0.14), 'met3': (0.24, 0.3),
        'met4': (0.24, 0.3), 'met5': (4.0, 1.6)}
CUTS = [
    ('mcon', 0.17, 0.19, 'li1', 0.0, None, 'met1', 0.03, 0.06,
     dict(w='ct.1_a', sq='ct.1_b', sp='ct.2', lc='ct.4', uc='m1.4_a', ue='m1.4', ua='m1.5')),
    ('via', 0.15, 0.17, 'met1', 0.055, 0.085, 'met2', 0.055, 0.085,
     dict(w='via.1a_a', sq='via.1a_b', sp='via.2', lc='via.4a_a', le='via.4a', la='via.5a',
          uc='m2.4_a', ue='m2.4', ua='m2.5')),
    ('via2', 0.20, 0.20, 'met2', 0.04, 0.085, 'met3', 0.065, None,
     dict(w='via2.1a_a', sq='via2.1a_b', sp='via2.2', lc='via2.4_a', le='via2.4', la='via2.5',
          uc='m3.4_a', ue='m3.4')),
    ('via3', 0.20, 0.20, 'met3', 0.06, 0.09, 'met4', 0.065, None,
     dict(w='via3.1_a', sq='via3.1_b', sp='via3.2', lc='via3.4_a', le='via3.4', la='via3.5',
          uc='m4.3_a', ue='m4.3')),
    ('via4', 0.80, 0.80, 'met4', 0.19, None, 'met5', 0.31, None,
     dict(w='via4.1_a', sq='via4.1_b', sp='via4.2', lc='via4.4_a', le='via4.4', uc='m5.3_a', ue='m5.3')),
]


def stack(cut, x, y, size, lo, le, la, up, ue, ua, sx=None, sy=None, lo_lr=None, lo_tb=None,
          up_lr=None, up_tb=None, no_lo=False, no_up=False):
    """Legal cut + both metals; overrides let one test break one enclosure."""
    sx = sx or size
    sy = sy or size
    s = [R(cut, x, y, x + sx, y + sy)]
    big = max(sx, sy)
    if not no_lo:
        lr = lo_lr if lo_lr is not None else (la if la else le)
        tb = lo_tb if lo_tb is not None else le
        s.append(metal_pad(lo, x, y, big, lr, tb, *MINS[lo]))
    if not no_up:
        lr = up_lr if up_lr is not None else ue
        tb = up_tb if up_tb is not None else (ua if ua else ue)
        s.append(metal_pad(up, x, y, big, lr, tb, *MINS[up], tail_up=True))
    return s


for cut, size, space, lo, le, la, up, ue, ua, n in CUTS:
    base = dict(size=size, lo=lo, le=max(le, 0.0), la=la, up=up, ue=ue, ua=ua)
    x0 = 3.0
    p(cut + '_stack', *stack(cut, x0, x0, **base))
    f(n['w'], *stack(cut, x0, x0, **dict(base, size=size - 0.01)))
    f(n['sq'], *stack(cut, x0, x0, sy=2 * size, **base))
    pair = stack(cut, x0, x0, **base) + [R(cut, x0 + size + space - 0.01, x0, x0 + 2 * size + space - 0.01, x0 + size)]
    pair_ok = [R(cut, x0 + size + space, x0, x0 + 2 * size + space, x0 + size)]
    f(n['sp'], *pair)
    # Two legal cuts at minimum spacing inside shared metals.
    w2 = 2 * size + space
    p(cut + '_pair', R(cut, x0, x0, x0 + size, x0 + size), *pair_ok,
      metal_pad(lo, x0, x0, w2, (la or le), le, *MINS[lo]),
      metal_pad(up, x0, x0, w2, ue, (ua or ue), *MINS[up], tail_up=True))
    f(n['lc'], *stack(cut, x0, x0, no_lo=True, **base))
    f(n['uc'], *stack(cut, x0, x0, no_up=True, **base))
    if 'le' in n:
        f(n['le'], *stack(cut, x0, x0, lo_lr=le - 0.005, lo_tb=max(le, la or 0), **base))
    if 'la' in n:
        f(n['la'], *stack(cut, x0, x0, lo_lr=le, lo_tb=le, **base))
    f(n['ue'], *stack(cut, x0, x0, up_tb=ue - 0.005, up_lr=max(ue, ua or 0), **base))
    if 'ua' in n:
        f(n['ua'], *stack(cut, x0, x0, up_lr=ue, up_tb=ue, **base))

# Metal area, holes and wide-metal spacing.
for m, a, h, wide_s, s, w, pre in [('met1', 0.083, 0.14, 0.28, 0.14, 0.14, 'm1'),
                                   ('met2', 0.0676, 0.14, 0.28, 0.14, 0.14, 'm2'),
                                   ('met3', 0.24, 0.2, 0.4, 0.3, 0.3, 'm3'),
                                   ('met4', 0.24, 0.2, 0.4, 0.3, 0.3, 'm4')]:
    ln = round(a / w * 0.9 / 0.005) * 0.005
    f(pre + '.6', R(m, 1, 1, 1 + w, 1 + ln))
    p(pre + '.6', R(m, 1, 1, 1 + w, 1 + round(a / w * 1.05 / 0.005) * 0.005))
    hs = 0.30 if h < 0.15 else 0.40
    ring = [R(m, 1, 1, 3, 2 - hs / 2), R(m, 1, 2 + hs / 2, 3, 3), R(m, 1, 1, 2 - hs / 2, 3), R(m, 2 + hs / 2, 1, 3, 3)]
    f(pre + '.7', *ring)
    hb = 0.50
    p(pre + '.7', R(m, 1, 1, 3, 2 - hb / 2), R(m, 1, 2 + hb / 2, 3, 3), R(m, 1, 1, 2 - hb / 2, 3), R(m, 2 + hb / 2, 1, 3, 3))
    mid = round((s + wide_s) / 2 / 0.005) * 0.005
    f(pre + '.3ab', R(m, 1, 1, 5, 5), R(m, 5 + mid, 1, 6.5, 5))
    p(pre + '.3ab', R(m, 1, 1, 5, 5), R(m, 5 + wide_s, 1, 6.5, 5))
    # A narrow wire leaving a wide block, with a neighbour at normal spacing beyond the block.
    p(pre + '.3ab_junction', R(m, 1, 1, 5, 5), R(m, 5, 2.9, 8, 2.9 + w), R(m, 6.5, 2.9 + w + s, 8, 4.5))
f('m5.4', R('met5', 1, 1, 2.6, 3.4))
p('m5.4', R('met5', 1, 1, 2.6, 3.55))
# Grid, angle checks.
f('x.1b_offgrid', R('met1', 1.001, 1, 1.501, 2))
f('x.3a_angle', ('met1', [(1, 1), (3, 1), (3, 2), (2, 2), (1, 1.5)]))
f('x.2_diff', ('diff', [(1, 1), (3, 1), (3, 3), (1.5, 3), (1, 2.5)]))
p('x.45', ('met1', [(1, 1), (3, 1), (3, 2), (2, 2), (1.5, 1.5), (1, 1.5)]))


def write(gds, tsv):
    shapes = []
    rows = []
    for i, (label, expect, ss) in enumerate(CASES):
        ox, oy = (i % COLS) * PITCH, (i // COLS) * PITCH
        for layer, pts in ss:
            shapes.append((layer, [(x + ox, y + oy) for x, y in pts]))
        rows.append('%d\t%s\t%s\t%g\t%g' % (i, label, expect or '-', ox, oy))
    write_gds(gds, 'drc_tests', shapes)
    open(tsv, 'w').write('\n'.join(rows) + '\n')
    print('wrote', gds, len(CASES), 'cases', len(shapes), 'shapes')


def read_errors(path):
    """Parse a Pegasus ASCII DRC report into [(rule, x_um, y_um)] (first vertex of each result).

    Layout: '<top> <dbu/um>', then per rule: name; '<count> <count> <ntext> <date>';
    ntext text lines; then <count> records 'p <i> <nverts>' + vertices or 'e <i> [n]' + edges.
    """
    lines = open(path).read().split('\n')
    precision = int(lines[0].split()[-1])
    out = []
    i = 1
    while i < len(lines):
        name = lines[i].strip()
        if not name:
            i += 1
            continue
        hdr = lines[i + 1].split()
        count, ntext = int(hdr[0]), int(hdr[2])
        i += 2 + ntext
        for _ in range(count):
            t = lines[i].split()
            n = int(t[2]) if len(t) > 2 else 1
            x, y = lines[i + 1].split()[:2]
            out.append((name, int(x) / precision, int(y) / precision))
            i += 1 + n
    return out


def check(tsv, report):
    cases = [l.split('\t') for l in open(tsv).read().split('\n') if l]
    errs = read_errors(report)
    hits = {}
    for rule, x, y in errs:
        idx = int(y // PITCH) * COLS + int(x // PITCH)
        hits.setdefault(idx, {}).setdefault(rule, 0)
        hits[idx][rule] += 1
    bad = 0
    for idx, label, expect, _, _ in cases:
        got = hits.get(int(idx), {})
        if expect == '-':
            ok = not got
        else:
            ok = expect in got
        bad += not ok
        print('%-4s %-26s expect %-12s got %s' % ('ok' if ok else 'FAIL', label, expect,
                                                  ', '.join('%s:%d' % (r, got[r]) for r in sorted(got)) or '-'))
    print('%d cases, %d failed, %d errors total' % (len(cases), bad, len(errs)))
    return bad


if __name__ == '__main__':
    if sys.argv[1] == 'write':
        write(sys.argv[2], sys.argv[3])
    else:
        sys.exit(1 if check(sys.argv[2], sys.argv[3]) else 0)
