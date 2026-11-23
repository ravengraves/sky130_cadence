"""Virtuoso transistor layouts: the Cornell sky130_fd_pr_main device library with PCells.

  python3 sky130.py virtuoso-setup     -> WORK/virtuoso/cds.lib (+ how-to in the output)
  python3 sky130.py xtor-check         instantiate transistor PCells in batch, stream out,
                                       check with the full DRC deck and Pegasus LVS

sky130_fd_pr_main (from the Cornell C2S2 SKY130_PDK, a Cadence PAS-generated PDK; NO license,
private use only) holds the sky130 technology (tech.db, display.drf, layer map) and
parameterized cells with symbol, layout, CDL, LVS and Spectre views for the sky130_fd_pr
devices. The 1.8 V transistors are nfet_01v8, nfet_01v8_lvt, pfet_01v8, pfet_01v8_hvt.
PCell parameters (layout view): l, fw (finger width), fingers, connectGates, connectSD,
sdMtlWidth, tap ("Detached" ...), leftTap/rightTap/topTap/bottomTap, ... ; total W = fw x fingers.
With connectGates/connectSD "None", a 2-finger device is two transistors sharing the middle
diffusion with separate gates and outer source/drain.

Validated 2026-11-17 (Virtuoso IC25.1, Pegasus 25.1): nfet_01v8 W 0.42 and 2x1.0 um,
nfet_01v8_lvt 0.74 um, pfet_01v8 1.12 and 2x1.5 um, pfet_01v8_hvt 1.0 um, L 0.15 um: all DRC
clean with the full deck (0 results) and LVS MATCH.
"""
import os
import re

from . import drc_deck, drc_tests, lvs, smoke, toolenv

LIB = 'sky130_fd_pr_main'
TEST_LIB = 'xtor_test'
CONFIGS = [  # cell, device, finger width um, fingers
    ('n_w042', 'nfet_01v8', 0.42, 1), ('n_w200_f2', 'nfet_01v8', 1.0, 2),
    ('nlvt_w074', 'nfet_01v8_lvt', 0.74, 1), ('p_w112', 'pfet_01v8', 1.12, 1),
    ('p_w300_f2', 'pfet_01v8', 1.5, 2), ('phvt_w100', 'pfet_01v8_hvt', 1.0, 1)]


def lib_path(work):
    return os.path.join(work, 'upstream', 'cornell_sky130_pdk', 'libs', LIB)


def setup(work):
    v = os.path.join(work, 'virtuoso')
    os.makedirs(v, exist_ok=True)
    lp = lib_path(work)
    if not os.path.exists(os.path.join(lp, 'tech.db')):
        raise SystemExit('missing %s: run download (Cornell PDK)' % lp)
    open(os.path.join(v, 'cds.lib'), 'w').write(
        '# Written by sky130cad/virtuoso.py. Start Virtuoso in this directory, or INCLUDE this file.\n'
        'SOFTINCLUDE $CDS_INST_DIR/share/cdssetup/cds.lib\n'
        'DEFINE %s %s\n' % (LIB, lp))
    return v


def skill(lib_dir, configs=CONFIGS):
    rows = '\n'.join('    list("%s" "%s" %ge-6 %d.0)' % c for c in configs)
    return '''let((cv ok)
  ddCreateLib("%(t)s" "%(d)s")
  techBindTechFile(ddGetObj("%(t)s") "%(lib)s")
  foreach(c list(
%(rows)s)
    cv = dbOpenCellViewByType("%(t)s" car(c) "layout" "maskLayout" "w")
    ok = dbCreateParamInstByMasterName(cv "%(lib)s" cadr(c) "layout" "M0" 0:0 "R0" 1
           list(list("fw" "float" caddr(c)) list("fingers" "float" cadddr(c)) list("l" "float" 1.5e-7)))
    printf("SKY130CAD_XTOR %%s %%L\\n" car(c) ok != nil)
    dbSave(cv) dbClose(cv)))
exit()
''' % {'t': TEST_LIB, 'd': lib_dir, 'lib': LIB, 'rows': rows}


def expected_cdl(name, dev, fw, fingers):
    """Topology the PCell draws with connectGates/connectSD None."""
    bulk = 'VPB' if dev.startswith('p') else 'VNB'
    if fingers == 1:
        return '.SUBCKT %s\nM0 D G S %s %s w=%g l=0.15\n.ENDS\n' % (name, bulk, dev, fw)
    return ('.SUBCKT %s\nM0 A G1 MID %s %s w=%g l=0.15\nM1 MID G2 B %s %s w=%g l=0.15\n.ENDS\n'
            % (name, bulk, dev, fw, bulk, dev, fw))


def xtor_check(work, env=None):
    import shutil
    v = setup(work)
    t = os.path.join(v, 'xtor_check')
    shutil.rmtree(t, ignore_errors=True)
    os.makedirs(os.path.join(t, 'gds'))
    lp = lib_path(work)
    open(os.path.join(t, 'cds.lib'), 'w').write('DEFINE %s %s\nDEFINE %s %s\n' % (LIB, lp, TEST_LIB, os.path.join(t, TEST_LIB)))
    open(os.path.join(t, 'mk.il'), 'w').write(skill(os.path.join(t, TEST_LIB)))
    toolenv.run(['virtuoso', '-nograph', '-replay', 'mk.il', '-log', 'mk.log'], t, os.path.join(t, 'mk.out'), env, 1200)
    log = open(os.path.join(t, 'mk.log')).read() if os.path.exists(os.path.join(t, 'mk.log')) else ''
    made = len(set(re.findall(r'SKY130CAD_XTOR (\w+) t\b', log)))   # the log also echoes the SKILL source
    deck = os.path.join(work, 'drc', 'sky130_full.pvl')
    if not os.path.exists(deck):
        drc_deck.write(deck)
    lvs_deck = lvs.deck_path(work)
    results = []
    for name, dev, fw, fingers in CONFIGS:
        gds = os.path.join(t, 'gds', name + '.gds')
        toolenv.run(['strmout', '-library', TEST_LIB, '-topCell', name, '-view', 'layout', '-strmFile', gds,
                     '-layerMap', os.path.join(lp, LIB + '.layermap'), '-logFile', gds + '.log'],
                    t, os.path.join(t, name + '.strmout.out'), env, 600)
        if not os.path.exists(gds):
            results.append((name, dev, fw * fingers, 'NO GDS', None, None))
            continue
        empty = [k for k, n in smoke.gds_structures(gds).items() if n == 0]
        d = os.path.join(t, 'checks', name)
        toolenv.run(['pegasus', '-drc', '-dp', '4', '-gds', gds, '-top_cell', name, deck], d + '/drc',
                    os.path.join(d, 'drc.out'), env, 600)
        rpt = os.path.join(d, 'drc', 'sky130_full.drc_errors.ascii')
        ndrc = len(drc_tests.read_errors(rpt)) if os.path.exists(rpt) else None
        open(os.path.join(d, 'src.cdl'), 'w').write(expected_cdl(name, dev, fw, fingers))
        res, _ = lvs.run(gds, name, os.path.join(d, 'src.cdl'), os.path.join(d, 'lvs'), lvs_deck, env)
        results.append((name, dev, fw * fingers, 'empty structures %s' % empty if empty else 'ok', ndrc, res))
    return made, results
