"""Pegasus LVS deck for the sky130 1.8 V digital devices, written from SkyWater's (Apache-2.0)
layer definitions by this repository; no third-party deck text.

  python3 sky130.py lvs-deck       -> WORK/lvs/sky130_lvs.pvl

Recognition (GDS layer/datatype as in SkyWater's sky130 layer table):
- substrate `pwell` = chip extent NOT nwell (plus drawn pwell 64/44 and pwell pins 122/16);
- gate = poly AND diff; its type comes from the implant over it:
    gate AND nsdm, outside nwell     -> nfet_01v8, or nfet_01v8_lvt under lvtn
    gate AND psdm, inside nwell      -> pfet_01v8, pfet_01v8_lvt under lvtn, pfet_01v8_hvt under hvtp
- source/drain = diff NOT poly, split into nSourceDrain (nsdm) and pSourceDrain (psdm);
- taps: tap AND psdm = ptap (soft-connected to pwell), tap AND nsdm = ntap (to nwell);
  diffusion that butts a tap of the opposite type is connected to it;
- contacts: licon on diff/tap = licon1, licon on poly only = poly_licon1; mcon, via..via4.
- device properties W, L (compared with the source within 1 %%), and AS, AD, PS, PD for
  parasitic extraction:  W = perimeter_coincide(G, SD)/2,  L = (perimeter(G) - 2 W)/2.
- short markers (poly/li1/metal datatype 15, as in the tie cell conb): zero-ohm resistors of
  model `short` between the conductor pieces on either side, matching the netlists' `short`;
- labels: text on the label (5), pin (16) and drawing (20) purposes of poly, li1, met1..met5;
  VPB on nwell label (64/5), VNB on the pwell label (64/59). Pin shapes count as conductors.

- diode_pw2nd (antenna diodes): n+ diffusion in pwell under areaid.diode (81/23); A, P.

Not recognized (absent from digital cells): other diodes, resistors, capacitors, bipolar,
high-voltage and deep-n-well devices.
Layer names match sky130cad/quantus.py LAYER_SETUP, so the deck also drives extraction.
"""
import os

# name: (layer, datatype)
POLYGONS = [
    ('nwell_in', 64, 20), ('nwell_pin', 64, 16), ('dnwell', 64, 18), ('pwell_in', 64, 44),
    ('pwell_pin', 122, 16), ('diff', 65, 20), ('tap', 65, 44), ('poly_in', 66, 20), ('poly_pin', 66, 16),
    ('licon', 66, 44), ('li1_in', 67, 20), ('li1_pin', 67, 16), ('mcon', 67, 44),
    ('met1_in', 68, 20), ('met1_pin', 68, 16), ('via', 68, 44), ('met2_in', 69, 20), ('met2_pin', 69, 16),
    ('via2', 69, 44), ('met3_in', 70, 20), ('met3_pin', 70, 16), ('via3', 70, 44),
    ('met4_in', 71, 20), ('met4_pin', 71, 16), ('via4', 71, 44), ('met5_in', 72, 20), ('met5_pin', 72, 16),
    ('nsdm', 93, 44), ('psdm', 94, 20), ('lvtn', 125, 44), ('hvtp', 78, 44), ('hvi', 75, 20),
    ('areaid_diode', 81, 23),
]
CONDUCTORS = [('poly', 66), ('li1', 67), ('met1', 68), ('met2', 69), ('met3', 70), ('met4', 71), ('met5', 72)]
# MOS: (element, model, gate layer, s/d layer, bulk layer)
MOS = [
    ('MN', 'nfet_01v8', 'ngate_std', 'nSourceDrain', 'pwell'),
    ('MN', 'nfet_01v8_lvt', 'ngate_lvt', 'nSourceDrain', 'pwell'),
    ('MP', 'pfet_01v8', 'pgate_std', 'pSourceDrain', 'nwell'),
    ('MP', 'pfet_01v8_lvt', 'pgate_lvt', 'pSourceDrain', 'nwell'),
    ('MP', 'pfet_01v8_hvt', 'pgate_hvt', 'pSourceDrain', 'nwell'),
]


def text():
    L = ['// sky130 LVS deck for Pegasus (1.8 V digital devices). Written by sky130cad/lvs_deck.py',
         '// from SkyWater sky130 layer definitions (Apache-2.0). See the module docstring.',
         '', 'abort_on_layout_error no', 'text_depth -primary', 'lvs_recognize_gates -none',
         'lvs_cdn_flow_options -cdl_use_scale', 'lvs_reduce yes -parallel_mos', 'lvs_reduce no -series_mos', '',
         '// ---- input layers']
    n = 1
    for name, layer, dtype in POLYGONS:
        L += ['layer_def %s %d' % (name, n), 'layer_map %d -datatype %d %d' % (layer, dtype, n)]
        n += 1
    labels = []
    for name, layer in CONDUCTORS:
        L.append('layer_def %s_label %d' % (name, n))
        for tt in (5, 16, 20):
            L.append('layer_map %d -texttype %d %d' % (layer, tt, n))
        labels.append(name + '_label')
        n += 1
    L += ['layer_def nwell_label %d' % n, 'layer_map 64 -texttype 5 %d' % n, 'layer_map 64 -texttype 16 %d' % n,
          'layer_def pwell_label %d' % (n + 1), 'layer_map 64 -texttype 59 %d' % (n + 1),
          'layer_map 122 -texttype 5 %d' % (n + 1), 'layer_map 122 -texttype 16 %d' % (n + 1)]
    labels += ['nwell_label', 'pwell_label']
    for name, layer in CONDUCTORS:   # short markers (datatype 15): zero-ohm `short` resistors
        L += ['layer_def %s_short %d' % (name, n), 'layer_map %d -datatype 15 %d' % (layer, n)]
        n += 1
    L += ['', '// ---- conductors (pin shapes count as drawn shapes; short markers cut them), wells']
    for name, _ in CONDUCTORS:
        L += ['or %s_in %s_pin -outputlayer %s_all' % (name, name, name),
              'not %s_all %s_short -outputlayer %s' % (name, name, name)]
    L += ['or nwell_in nwell_pin -outputlayer nwell',
          'extent -outputlayer chip_extent',
          'not chip_extent nwell -outputlayer substrate',
          'or substrate pwell_in pwell_pin -outputlayer pwell_all',
          'not pwell_all nwell -outputlayer pwell',
          '', '// ---- diffusion, gates, taps',
          'and poly diff -outputlayer gate',
          'not diff poly -outputlayer sd',
          '// diode_pw2nd: n+ diffusion in pwell under areaid.diode (antenna diode cells)',
          'and sd nsdm -outputlayer nsd_all',
          'and nsd_all areaid_diode -outputlayer ndiode_all',
          'not ndiode_all nwell -outputlayer ndiode',
          'not nsd_all ndiode -outputlayer nSourceDrain',
          'and sd psdm -outputlayer pSourceDrain',
          'and tap psdm -outputlayer ptap',
          'and tap nsdm -outputlayer ntap',
          'not gate hvi -outputlayer gate_lv',
          'and gate_lv nsdm -outputlayer ngate_all',
          'not ngate_all nwell -outputlayer ngate',
          'and ngate lvtn -outputlayer ngate_lvt',
          'not ngate lvtn -outputlayer ngate_std',
          'and gate_lv psdm -outputlayer pgate_all',
          'and pgate_all nwell -outputlayer pgate',
          'and pgate hvtp -outputlayer pgate_hvt',
          'not pgate hvtp -outputlayer pgate_nh',
          'and pgate_nh lvtn -outputlayer pgate_lvt',
          'not pgate_nh lvtn -outputlayer pgate_std',
          '', '// ---- contacts',
          'or diff tap -outputlayer difftap',
          'and licon difftap -outputlayer licon1',
          'not licon difftap -outputlayer licon_nd',
          'and licon_nd poly -outputlayer poly_licon1',
          '', '// ---- connectivity',
          'connect met5 met4 -by via4', 'connect met4 met3 -by via3', 'connect met3 met2 -by via2',
          'connect met2 met1 -by via', 'connect met1 li1 -by mcon',
          'connect li1 poly -by poly_licon1',
          'connect li1 nSourceDrain -by licon1', 'connect li1 pSourceDrain -by licon1',
          'connect li1 ntap -by licon1', 'connect li1 ptap -by licon1', 'connect li1 ndiode -by licon1',
          'connect nSourceDrain ptap', 'connect pSourceDrain ntap']
    for _, _, g, _, _ in MOS:
        L.append('connect poly %s' % g)
    L += ['sconnect ntap nwell', 'sconnect ptap pwell', '', '// ---- labels']
    for name, _ in CONDUCTORS:
        L.append('attach %s_label %s' % (name, name))
    L += ['attach nwell_label nwell', 'attach pwell_label pwell', 'port -text_layer ' + ' '.join(labels), '',
          '// ---- devices']
    for elem, model, gate, sd, bulk in MOS:
        L.append('device %s (%s) %s %s (G) %s (S) %s (D) %s (B) [' % (elem, model, gate, gate, sd, sd, bulk))
        L += ['    property W, L, AS, AD, PS, PD',
              '    W = perimeter_coincide(G, %s) / 2' % sd,
              '    L = (perimeter(G) - perimeter_coincide(G, %s)) / 2' % sd,
              '    AS = area(S)', '    AD = area(D)', '    PS = perimeter(S)', '    PD = perimeter(D)', ']']
    L += ['device D (diode_pw2nd) ndiode pwell (POS) ndiode (NEG) [',
          '    property A, P', '    A = area(ndiode)', '    P = perimeter(ndiode)', ']']
    for name, _ in CONDUCTORS:
        L.append('device R (short) %s_short %s %s [ 0 ]' % (name, name, name))
    L += ['', '// ---- comparison']
    for elem in ('MN', 'MP'):
        L += ['lvs_check_property %s W w' % elem, 'lvs_check_property %s L l' % elem]
    return '\n'.join(L) + '\n'


def write(dst):
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    open(dst, 'w').write(text())
    return len(MOS)
