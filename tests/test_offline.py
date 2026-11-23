"""Offline tests (no Cadence tools, no downloads): python3 -m unittest discover -s tests -v"""
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sky130cad import (abstract, cadence_setup, cell_array, charlib, drc_deck, drc_tests, gds_fix,  # noqa: E402
                       cellfix, cellrc, liberty_json, lvs, lvs_deck, mosgen, pinaccess, patches, release, smoke, sources, spectre_models, spectre_netlist,
                       tech)


class Tmp(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.dir = self._t.name

    def tearDown(self):
        self._t.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)


class TestGds(Tmp):
    def test_roundtrip_and_array(self):
        drc_tests.LAYERS.setdefault('met1', (68, 20))
        a, b = self.path('a.gds'), self.path('b.gds')
        drc_tests.write_gds(a, 'cell_a', [drc_tests.R('met1', 0, 0, 1, 2)])
        drc_tests.write_gds(b, 'cell_b', [drc_tests.R('met1', 0, 0, 3, 1)])
        units, structs = cell_array.read_lib(a)
        self.assertEqual(structs['cell_a'][1], (0, 0, 1000, 2000))
        self.assertAlmostEqual(cell_array.struct_unpack_real8(units[12:20]), 1e-9)
        out, tsv = self.path('arr.gds'), self.path('arr.tsv')
        cell_array.build(out, tsv, [a, b])
        rows = [l.split('\t') for l in open(tsv).read().split('\n') if l]
        self.assertEqual([r[0] for r in rows], ['cell_a', 'cell_b'])
        self.assertGreaterEqual(float(rows[1][1]) - float(rows[0][3]), cell_array.GAP - 1e-9)
        fixed = self.path('fixed.gds')
        self.assertEqual(gds_fix.main(out, fixed, [b]), 0)
        _, s2 = cell_array.read_lib(fixed)
        self.assertIn('cell_array', s2)


class TestLibertyJson(Tmp):
    def test_convert_minimal_library(self):
        lib = 'sky130_fd_sc_xx'
        os.makedirs(self.path('timing'))
        os.makedirs(self.path('cells/inv'))
        json.dump({'delay_model': 'table_lookup', 'time_unit': '1ns',
                   'lu_table_template,del_1_7_7': {'variable_1': 'input_net_transition',
                                                   'index_1': [0.01, 0.1]}},
                  open(self.path('timing/%s__common.lib.json' % lib), 'w'))
        json.dump({'nom_voltage': 1.6, 'comp_attribute,voltage_map': [['VPWR', 1.6], ['VGND', 0.0]]},
                  open(self.path('timing/%s__ss_150C_1v60.lib.json' % lib), 'w'))
        json.dump({'area': 3.6, 'pin,A': {'direction': 'input', 'capacitance': 0.002},
                   'pin,Y': {'direction': 'output', 'function': '(!A)',
                             'timing': [{'related_pin': 'A', 'timing_sense': 'negative_unate',
                                         'cell_rise,del_1_7_7': {'index_1': [0.01, 0.1], 'index_2': [0.0, 0.01],
                                                                 'values': [[0.1, 0.2], [0.15, 0.25]]}}]}},
                  open(self.path('cells/inv/%s__inv_1__ss_150C_1v60.lib.json' % lib), 'w'))
        out = self.path('out.lib')
        self.assertEqual(liberty_json.convert(self.dir, 'ss_150C_1v60', out, lib), 1)
        g = charlib.lib_cell(out, '%s__inv_1' % lib)
        t = charlib.ref_timings(g)
        i1, i2, vals = charlib.ref_table(t, ('Y', 'A', 'combinational'), 'cell_rise')
        self.assertEqual((i1, i2, vals), ([0.01, 0.1], [0.0, 0.01], [[0.1, 0.2], [0.15, 0.25]]))
        self.assertIn('voltage_map (VPWR, 1.6);', open(out).read())


class TestTech(unittest.TestCase):
    TLEF = 'LAYER nwell\n  TYPE MASTERSLICE ;\nEND nwell\n\nLAYER pwell\n  TYPE MASTERSLICE ;\nEND pwell\n\nLAYER li1\n'

    def test_licon_patch_once(self):
        p = tech.patch_tlef(self.TLEF)
        self.assertIn('END pwell\n\nLAYER licon\n  TYPE CUT ;\nEND licon\n', p)
        self.assertEqual(tech.patch_tlef(p), p)

    def test_foreign_fix(self):
        m = 'MACRO sky130_fd_sc_hs__diode_2\n  CLASS CORE ANTENNACELL ;\n  FOREIGN scs8hs_diode_2 ;\nEND sky130_fd_sc_hs__diode_2'
        text, old = tech.fix_foreign(m)
        self.assertEqual(old, 'scs8hs_diode_2')
        self.assertIn('FOREIGN sky130_fd_sc_hs__diode_2 ;', text)
        self.assertEqual(tech.fix_foreign(text)[1], None)

    def test_maps(self):
        sm = tech.stream_map()
        self.assertIn('met1\tNET\t68\t20', sm)
        self.assertIn('via4\tVIA\t71\t44', sm)
        lm = tech.extraction_layermap()
        order = re.findall(r'^\s+(\w+) \1', lm, re.M)
        self.assertEqual(order, ['li1', 'mcon', 'met1', 'via', 'met2', 'via2', 'met3', 'via3', 'met4', 'via4', 'met5'])


class TestSpectre(Tmp):
    def test_netlist_numbers_and_legacy(self):
        self.assertEqual(spectre_netlist.convert_line('X0 a b c d sky130_fd_pr__pfet_01v8 w=1.12e+06u l=150000u'),
                         'X0 a b c d sky130_fd_pr__pfet_01v8 w=1.12 l=150000u')
        c = spectre_netlist.convert_line('MM1 d g s b NLOWVT L=0.15 W=1 AD=0.2 M=1 R=6 $X=1')
        self.assertEqual(c, 'XMM1 d g s b sky130_fd_pr__nfet_01v8_lvt l=0.15 w=1 ad=0.2')
        self.assertIsNone(spectre_netlist.convert_line('pX3_noxref n A A PROBETYPE=1'))

    def test_model_patch(self):
        src = '.subckt  sky130_fd_pr__pfet_01v8 d g s b\n+ \n.param  l = 1 w = 1 nf = 1.0\nm1 d g s b mod l = {l} w = {w}\n.ends\n'
        out = spectre_models.patch_spice(src)
        self.assertIn('.subckt  sky130_fd_pr__pfet_01v8 d g s b l=1 w=1 nf=1.0\n', out)
        self.assertIn("l = 'l' w = 'w'", out)
        self.assertNotIn('.param', out)


class TestLvs(Tmp):
    def test_deck_patch_and_source(self):
        deck = self.path('d.pvl')
        open(deck, 'w').write('lvs_black_box -grey capA\nlvs_reduce yes\n')
        self.assertEqual(lvs.patch_deck(deck, self.path('o.pvl')), 1)
        self.assertIn('// [sky130cad', open(self.path('o.pvl')).read())
        net = self.path('n.cdl')
        open(net, 'w').write('.SUBCKT top\nM0 Y A gnd gnd nlowvt L=0.15 W=1\n+ m=1\nX2 gnd vdd Dpar a=1\n.ENDS\n')
        pins = self.path('p.spice')
        open(pins, 'w').write('.subckt top GND VDD A Y\n.ends\n')
        lvs.source_cdl(net, self.path('s.cdl'), 'top', lvs.subckt_pins(pins, 'top'))
        s = open(self.path('s.cdl')).read()
        self.assertTrue(s.startswith('*.SCALE MICRON'))
        self.assertIn('.SUBCKT top GND VDD A Y', s)
        self.assertIn('nfet_01v8_lvt', s)
        self.assertNotIn('Dpar a=1', s)


class TestCharlib(Tmp):
    def test_sensitization(self):
        s = charlib.sensitizations('(A0&!S) | (A1&S)', 'S', ['A0', 'A1', 'S'])
        self.assertEqual(sorted(x[1] for x in s), ['negative', 'positive'])
        self.assertEqual({x[1] for x in charlib.sensitizations('(A0 * !S0) + (A1 * S0)', 'A0', ['A0', 'A1', 'S0'])},
                         {'positive'})
        self.assertEqual(len(charlib.sensitizations('A^B', 'A', ['A', 'B'])), 2)

    def test_corner(self):
        self.assertEqual(charlib.corner_conditions('ss_150C_1v60'), ('ss', 150.0, 1.6))
        self.assertEqual(charlib.corner_conditions('ff_n40C_1v95_ccsnoise'), ('ff', -40.0, 1.95))

    def test_liberty_roundtrip_and_envelope(self):
        cfg = {'library': 't', 'corner': {'name': 'c', 'models': 'm', 'vdd': 1.6, 'temp': 150}}
        timing = [{'pin': 'Y', 'related_pin': 'A', 'timing_type': 'combinational', 'timing_sense': 'negative_unate',
                   'index_1': [0.01, 0.1], 'index_2': [0.001, 0.01],
                   'cell_rise': [[1, 2], [3, 4]], 'cell_fall': [[1, 2], [3, 4]],
                   'rise_transition': [[1, 2], [3, 4]], 'fall_transition': [[1, 2], [3, 4]]},
                  {'pin': 'D', 'related_pin': 'CK', 'timing_type': 'setup_rising', 'index_1': [0.1, 1.0],
                   'index_2': [], 'rise_constraint': [[0.2], [0.3]], 'fall_constraint': [[0.1], [0.2]]}]
        cell = {'name': 'c1', 'inputs': {'A': (0.002, 0.003), 'D': (0.001, 0.001)}, 'outputs': {'Y': '(!A)'},
                'timing': timing, 'ff': None, 'area': 1.0}
        out = self.path('o.lib')
        charlib.write_liberty(out, cfg, [cell])
        t = charlib.ref_timings(charlib.lib_cell(out, 'c1'))
        self.assertEqual(charlib.ref_table(t, ('Y', 'A', 'combinational'), 'cell_rise')[2], [[1, 2], [3, 4]])
        self.assertEqual(charlib.ref_table(t, ('D', 'CK', 'setup_rising'), 'rise_constraint')[2], [[0.2], [0.3]])
        groups = {('Y', 'S', 'combinational'): []}
        for v in ([[1, 5]], [[2, 4]]):
            g = {'attrs': {'when': 'x'}, 'groups': [('cell_rise', 't', {'attrs': {'index_1': '("1")', 'index_2': '("1, 2")',
                                                                              'values': '("%d, %d")' % tuple(v[0])}, 'groups': []})]}
            groups[('Y', 'S', 'combinational')].append(g)
        self.assertEqual(charlib.ref_table(groups, ('Y', 'S', 'combinational'), 'cell_rise')[2], [[2, 5]])


class TestQuantus(Tmp):
    def test_pex_deck_and_netlist(self):
        from sky130cad import quantus
        deck = self.path('lvs.pvl')
        open(deck, 'w').write('device MN (nfet_01v8_lvt) r g (G) nSourceDrain (S) nSourceDrain (D) pwell (B)\n'
                              'device MN (nfet_g5v0d10v5) r g (G) HV_sd (S) HV_sd (D) pwell (B)\n')
        self.assertEqual(quantus.pex_deck(deck, self.path('pex.pvl')), 1)
        t = open(self.path('pex.pvl')).read()
        self.assertIn('W = perimeter_coincide(G, nSourceDrain) / 2', t)
        self.assertIn('AS = area(S)', t)
        raw = self.path('raw.sp')
        open(raw, 'w').write('.SUBCKT c VNB A Y\nMMIN1\tY#3\tA#1\tVGND#4\tVNB\tnfet_01v8_lvt\tL=1.5e-07\n+ W=7.4e-07\n'
                             '+ AD=2.109e-13\tAS=2.627e-13\tPD=2.05e-06\tPS=2.19e-06\nRf1\tA#7\tA\t1.93\t$li1\n'
                             'C1\tA\tVNB\t3.4e-17\n.ENDS\n')
        self.assertEqual(quantus.spectre_netlist(raw, self.path('o.sp')), (1, 2))
        o = open(self.path('o.sp')).read()
        self.assertIn('XMMIN1 Y#3 A#1 VGND#4 VNB sky130_fd_pr__nfet_01v8_lvt l=0.15 w=0.74 ad=0.2109 as=0.2627 pd=2.05 ps=2.19', o)
        self.assertNotIn('$li1', o)


class TestVirtuoso(Tmp):
    def test_skill_and_netlists(self):
        from sky130cad import virtuoso
        il = virtuoso.skill('/x/xtor_test')
        self.assertEqual(il.count('{'), il.count('}'))
        self.assertIn('list("n_w200_f2" "nfet_01v8" 1e-6 2.0)', il)
        self.assertIn('techBindTechFile(ddGetObj("xtor_test") "sky130_fd_pr_main")', il)
        self.assertIn('printf("SKY130CAD_XTOR %s %L\\n"', il)
        self.assertIn('M1 MID G2 B VPB pfet_01v8 w=1.5', virtuoso.expected_cdl('p', 'pfet_01v8', 1.5, 2))


class TestDrc(Tmp):
    def test_deck_and_cases(self):
        n = drc_deck.write(self.path('d.pvl'))
        text = open(self.path('d.pvl')).read()
        self.assertEqual(n, 127)
        self.assertEqual(text.count('{'), text.count('}'))
        for line in text.split('\n'):
            self.assertFalse(line.startswith('rule ') and line.rstrip().endswith('}'), 'one-line rule: ' + line)
        for v in re.findall(r'shift -xy (\S+) (\S+)', text):
            for x in v:
                self.assertAlmostEqual(float(x) / 0.005, round(float(x) / 0.005))
        rules = set(re.findall(r'^rule (\S+) \{', text, re.M))
        drc_tests.write(self.path('t.gds'), self.path('t.tsv'))
        expect = {l.split('\t')[2] for l in open(self.path('t.tsv')).read().split('\n') if l} - {'-'}
        self.assertFalse(expect - rules, 'test cases name rules not in the deck')
        self.assertGreaterEqual(len(expect), 100)


class TestLvsDeck(Tmp):
    def test_deck_text(self):
        t = lvs_deck.text()
        self.assertEqual(t.count('[') , t.count(']'))
        for m in ('nfet_01v8', 'nfet_01v8_lvt', 'pfet_01v8', 'pfet_01v8_lvt', 'pfet_01v8_hvt'):
            self.assertIn('(%s)' % m, t)
        self.assertIn('device R (short) poly_short poly poly [ 0 ]', t)
        self.assertIn('extent -outputlayer chip_extent', t)
        # every derived layer is defined before use
        defined = {l.split()[1] for l in t.splitlines() if l.startswith('layer_def')}
        for line in t.splitlines():
            tok = line.split()
            if '-outputlayer' in tok:
                defined.add(tok[tok.index('-outputlayer') + 1])
            elif tok and tok[0] in ('and', 'not', 'or'):
                for x in tok[1:]:
                    if not x.startswith('-'):
                        self.assertIn(x, defined, line)
        # names Quantus layer_setup refers to
        for name in ('nSourceDrain', 'pSourceDrain', 'poly_licon1', 'licon1', 'mcon', 'via4'):
            self.assertIn(name, defined | {'mcon', 'via4'})

    def test_spice_to_cdl(self):
        open(self.path('c.spice'), 'w').write(
            '.subckt c A VGND VNB VPB VPWR Y\nX0 VPWR A Y VPB sky130_fd_pr__pfet_01v8 w=1.12 l=150000u\n'
            'X1 VGND A Y VNB sky130_fd_pr__nfet_01v8_lvt w=740000u l=150000u\n'
            'X2 VNB A sky130_fd_pr__diode_pw2nd p=7.32 a=0.6417\nX3 HI VPWR VNB short w=510000u l=45000u\n.ends\n')
        lvs.spice_to_cdl(self.path('c.spice'), self.path('c.cdl'))
        t = open(self.path('c.cdl')).read()
        self.assertIn('M0 VPWR A Y VPB pfet_01v8 w=1.12 l=0.15', t)
        self.assertIn('M1 VGND A Y VNB nfet_01v8_lvt w=0.74 l=0.15', t)
        self.assertIn('D2 VNB A diode_pw2nd area=0.6417 pj=7.32', t)
        self.assertIn('R3 HI VPWR short', t)


class TestCellFix(Tmp):
    LEF = """MACRO sky130_fd_sc_hs__xor3_1
  SIZE 9.120000 BY 3.330000 ;
  PIN B
    DIRECTION INPUT ;
    USE SIGNAL ;
    PORT
      LAYER li1 ;
        RECT 4.920000 1.350000 5.250000 1.780000 ;
    END
  END B
  OBS
    LAYER li1 ;
      RECT 0.000000 -0.085000 9.120000 0.085000 ;
    LAYER met1 ;
      RECT 2.975000 1.550000 3.265000 1.595000 ;
      RECT 2.975000 1.595000 5.665000 1.735000 ;
      RECT 2.975000 1.735000 3.265000 1.780000 ;
      RECT 5.375000 1.550000 5.665000 1.595000 ;
      RECT 5.375000 1.735000 5.665000 1.780000 ;
  END
END sky130_fd_sc_hs__xor3_1
"""

    def test_xor3_1_access(self):
        before = pinaccess.macros(self.LEF)['sky130_fd_sc_hs__xor3_1']
        self.assertEqual(len(pinaccess.access_points(before, 'B')), 0)
        text, changed = cellfix.fix_lef(self.LEF)
        self.assertEqual(changed, ['sky130_fd_sc_hs__xor3_1'])
        after = pinaccess.macros(text)['sky130_fd_sc_hs__xor3_1']
        self.assertGreater(len(pinaccess.access_points(after, 'B')), 100)
        self.assertEqual(len([r for l, r in after['obs'] if l == 'met1']), 6)

    def test_xor3_1_gds(self):
        from sky130cad import drc_tests
        drc_tests.write_gds(self.path('x.gds'), 'sky130_fd_sc_hs__xor3_1',
                            [drc_tests.R('met1', 2.975, 1.55, 5.665, 1.78), drc_tests.R('li1', 4.92, 1.35, 5.25, 1.78)])
        self.assertEqual(cellfix.fix_gds(self.path('x.gds'), self.path('y.gds'), 'sky130_fd_sc_hs__xor3_1'), 1)
        from sky130cad import pcell
        rects, _ = pcell.gds_shapes(self.path('y.gds'))
        met1 = sorted(r[2:] for r in rects if r[:2] == (68, 20))
        self.assertEqual(len(met1), 6)
        self.assertIn((4610, 1950, 5665, 2090), met1)


class TestCellRc(unittest.TestCase):
    LIB = """library (t) { cell ("x__inv_1") {
      pin ("A") { direction : "input"; capacitance : 0.002; }
      pin ("Y") { direction : "output"; function : "!A";
        timing () { related_pin : "A";
          cell_rise ("t") { index_1 ("0.01, 0.1"); index_2 ("0.001, 0.011"); values ("0.05, 0.10", "0.06, 0.11"); }
          cell_fall ("t") { index_1 ("0.01, 0.1"); index_2 ("0.001, 0.011"); values ("0.03, 0.06", "0.04, 0.07"); }
        } } } }"""

    def test_rc(self):
        rows = cellrc.cell_rc(self.LIB, 'x__inv_1', slew=0.1)
        self.assertEqual(len(rows), 1)
        pin, out, cin, rr, rf, tr, tf, fo4 = rows[0]
        self.assertEqual((pin, out), ('A', 'Y'))
        self.assertAlmostEqual(cin, 2.0)
        self.assertAlmostEqual(rr, 5.0)          # (0.11 - 0.06) ns / 0.01 pF
        self.assertAlmostEqual(rf, 3.0)
        self.assertAlmostEqual(tr, 55.0)         # 60 ps - 5 kOhm x 1 fF
        self.assertAlmostEqual(fo4, (55 + 5 * 8 + 37 + 3 * 8) / 2)


class TestMosgen(Tmp):
    def test_generate_all(self):
        cells = []
        for dev, w, l, nf, tap, tie in mosgen.CHECK:
            name, shapes, labels, p = mosgen.generate(dev, w, l, nf, tap, tie)
            for layer, x0, y0, x1, y1 in shapes:
                self.assertTrue(x1 > x0 and y1 > y0, (name, layer))
                self.assertTrue(all(v % 5 == 0 for v in (x0, y0, x1, y1)), (name, layer))
            pins = {t for _, _, _, t in labels}
            self.assertEqual(pins, {'D', 'G', 'S'} | (set() if tie or not tap else {'B'}), name)
            gates = [s for s in shapes if s[0] == 'poly' and s[2] < 0]
            self.assertEqual(len(gates), nf)
            self.assertEqual(any(s[0] == 'nwell' for s in shapes), dev.startswith('p'))
            cdl, sp = mosgen.netlists(name, p)
            self.assertEqual(cdl.count('\nM'), nf)
            cells.append((name, shapes, labels))
        mosgen.write_gds(self.path('m.gds'), cells)
        self.assertGreater(os.path.getsize(self.path('m.gds')), 1000)
        with self.assertRaises(ValueError):
            mosgen.generate('nfet_01v8', 0.3, 0.15)
        self.assertTrue(mosgen.in_bin([(0.15, 0.18, 0.42, 0.55)], 0.42, 0.15))
        self.assertFalse(mosgen.in_bin([(0.15, 0.18, 0.42, 0.55)], 0.6, 0.15))


class TestGenerated(Tmp):
    def test_cadence_tcl_and_abstract_replay(self):
        for f in cadence_setup.write(self.path('tech'), self.path('cad')):
            t = open(f).read()
            self.assertEqual(t.count('{'), t.count('}'), f)
        t = open(self.path('cad/innovus_fdsc.tcl')).read()
        self.assertIn('sky130_fd_sc_hs__diode_2', t)
        self.assertIn('*__fah*', t)
        r = abstract.replay('t.tlef', 'abs', ['a.gds'], 'm.map', 'o.lef', ['a'], 'x.lib')
        self.assertIn('absSetOption("ImportLogicalFiles" "x.lib")', r)
        self.assertTrue(r.rstrip().endswith('absExit()'))
        self.assertIn('prBoundary drawing 81 4', abstract.layer_map())

    def test_sources(self):
        pats = sources.fdsc_sparse_patterns(['ss_150C_1v60'])
        self.assertIn('/cells/*/sky130_fd_sc_hs__*__ss_150C_1v60.lib.json', pats)
        self.assertEqual(len(sources.FDSC['commit']), 40)
        self.assertIn('/cells/nfet_01v8_lvt/', sources.fdpr_sparse_patterns())

    def test_relocatable(self):
        # Tcl setup and the example reach tech/ and cadence/ relatively; no absolute paths.
        cadence_setup.write(self.path('rel/tech'), self.path('rel/cadence'))
        smoke.write_example(self.path('rel/examples/smoke'), self.path('rel/cadence'))
        for f in ('cadence/genus_fdsc.tcl', 'cadence/mmmc_fdsc.tcl', 'examples/smoke/innovus.tcl'):
            t = open(self.path('rel/' + f)).read()
            self.assertNotIn(self.dir, t, f)
            self.assertIn('info script', t)
        self.assertIn('{../tech}', open(self.path('rel/cadence/innovus_fdsc.tcl')).read())
        self.assertIn('../../cadence', open(self.path('rel/examples/smoke/genus.tcl')).read())
        # Spectre model includes are relative to the including file.
        m = self.path('fd_pr/models')   # upstream layout: models/ next to cells/<device>/
        os.makedirs(self.path('fd_pr/cells/nfet_01v8'))
        os.makedirs(os.path.join(m, 'parameters'))
        open(os.path.join(m, 'all.spice'), 'w').write('.option scale=1.0u\n.include "parameters/lod.spice"\n')
        open(os.path.join(m, 'parameters', 'lod.spice'), 'w').write('.param x=1\n')
        open(self.path('fd_pr/cells/nfet_01v8/a.spice'), 'w').write('.include "b.spice"\n')
        open(self.path('fd_pr/cells/nfet_01v8/b.spice'), 'w').write('* b\n')
        open(os.path.join(m, 'sky130.lib.spice'), 'w').write(
            '.lib tt\n.include "../cells/nfet_01v8/a.spice"\n.endl tt\n')
        spectre_models.main(m, self.path('out'), ['tt'])
        top = open(self.path('out/sky130_digital_tt.spice')).read()
        self.assertIn('.include "fd_pr/lod.spice"', top)
        self.assertIn('.include "fd_pr/a.spice"', top)
        self.assertNotIn(self.dir, top)
        self.assertEqual(open(self.path('out/fd_pr/a.spice')).read().strip(), '.include "b.spice"')
        self.assertIn('lvs-deck.patch', open(release.__file__).read())   # excluded from the release

    def test_cds_source(self):
        self.assertEqual(len(sources.SKY130_CDS['commit']), 40)
        self.assertEqual(sources.SKY130_CDS['license'], 'Apache-2.0')
        self.assertIn('/PEX/', sources.cds_sparse_patterns())

    def test_udiff(self):
        d = patches.udiff('a\nb\n', 'a\nc\n', 'x', 'y')
        self.assertIn('-b\n+c\n', d)


if __name__ == '__main__':
    unittest.main()
