#!/usr/bin/env python3
"""SkyWater sky130_fd_sc_hs (Google) standard cells with Cadence tools.

Steps, in order. Everything is written under WORK (--work, $SKY130_WORK, default ~/sky130_work);
this repository holds only these scripts.

  download        pinned sparse checkouts of sky130_fd_sc_hs, sky130_fd_pr, sky130_cds (QRC file,
                  Virtuoso tech library) and the Cornell SKY130_PDK (Virtuoso device library,
                  DRC/LVS decks; no license: private use)
                  (--fdsc-from/--fdpr-from/--cds-from/--cornell-from: use existing copies)
  convert         Liberty from the upstream JSON, patched tech LEF, cell LEF (FOREIGN fix),
                  cell GDS links, streamOut map, QRC layer map           -> WORK/tech
  patches         every upstream change as a unified diff                -> WORK/patches
  cadence-setup   Genus / Innovus / MMMC setup Tcl                       -> WORK/cadence
  drc-deck        Pegasus DRC deck with the SkyWater rules (127 checks)  -> WORK/drc
  drc-validate    deck against 185 test layouts and every fd_sc cell (Pegasus)
  drc GDS TOP     run the deck on a layout (--deck cornell: the Cornell Pegasus deck instead)
  antenna-deck    Pegasus antenna deck (SkyWater antenna rules)         -> WORK/drc/sky130_antenna.pvl
  antenna-validate  antenna deck on its test layouts;  antenna GDS TOP: run it on a layout
  lvs-deck        Pegasus LVS deck patched for Pegasus 25.1               -> WORK/lvs
  lvs-check       LVS of fd_sc cells against their CDL (Pegasus)
  lvs GDS TOP NETLIST
  spectre-models  Spectre-loadable transistor models (digital subset)    -> WORK/spectre/models
  characterize    Spectre sweeps -> Liberty, compared with the shipped tables
  extract         Quantus parasitic extraction of cell layouts -> netlists for characterize
  abstract        cell LEF from GDS with the Virtuoso Abstract Generator, compared with the shipped LEF
  virtuoso-setup  cds.lib for the Virtuoso device library (transistor PCells for layout) -> WORK/virtuoso
  xtor-check      instantiate transistor PCells in batch, stream out, full DRC + LVS
  smoke           Genus -> Innovus -> Pegasus DRC on a small design
  mos             transistor layout generator: GDS + CDL + Spectre subcircuit (sky130cad/mosgen.py)
  mos-check       generate 12 transistors; DRC, Spectre (+ LVS / Cornell DRC if downloaded)
  pcells          Virtuoso PCell library sky130_mos (layout PCells, CDF, symbols) -> WORK/pcells
  pcell-check     instantiate the mos-check sizes; geometry must equal `mos`; DRC + LVS
  pin-access      audit: met1 access points on every signal pin of the cell LEF (route-ability)
  cell-rc         Cin, drive R, intrinsic delay, FO4 per arc from a Liberty (compare cell versions)
  library         library CDL, merged GDS, flat Verilog models, Virtuoso OA layout library
  ccs-libs        Liberty with CCS timing + CCS noise (ccsnoise corners)     -> WORK/tech/ccs
  lvs-block GDS TOP NETLIST.v  full-chip LVS of a routed block (Innovus netlist with P/G pins)
  fix-gds IN OUT CELL.gds...   replace cell structures in a layout GDS
  all             download .. smoke in order
  release         publishable files (Apache-2.0 sources + generated; no Cornell files) -> release/
  package         release/ -> dist/sky130_fd_sc_hs_cadence-VERSION.tar.gz (+ .sha256), reproducible
  release-check   use the release as published: checksums, DRC tests, Spectre, Virtuoso tech
                  library, Genus -> Innovus -> Pegasus example        -> WORK/release_check

Cadence tools (Pegasus, Spectre, Genus, Innovus, Abstract, Quantus) are found through --env or
$SKY130_TOOL_ENV, a shell snippet such as 'source /opt/cadence/setup.sh'.
Each module in sky130cad/ documents what it does and why in its docstring.

Validated 2026-11-17 on a fresh WORK (Pegasus 25.1, Spectre 25.1, Genus 25.1, Innovus 20.16,
Virtuoso/Abstract 25.1, Quantus 25.1; `python3 -m unittest discover -s tests` offline):
  download        sparse fetch 62 s; all 2709 fd_sc and 289 fd_pr files byte-identical to full checkouts
  convert         5 Liberty corners, tech/cell LEF byte-identical to the files used in production runs
  drc-validate    185/185 test cases correct; 390/390 fd_sc cells clean (block-level rules aside)
  lvs-check       8/8 cells MATCH (inv, nand2, xor2, mux2, mux4, fa, dfxtp_1/_4)
  characterize    schematic netlists 15-33 % faster than the shipped tables; extracted netlists
                  (extract) within about +12 % (rise) / +-7 % (fall) on mux2_1 and dfxtp_1 CLK->Q
  abstract        pins, OBS, SIZE, SITE, CLASS identical to the shipped LEF (VPB/VNB not generated)
  smoke           Genus -> Innovus -> Pegasus: Innovus DRC/connectivity clean, 0 Pegasus results
Site notes: Innovus 20.x needs its own OpenAccess while Virtuoso 25.x needs the default one, so
set OA_HOME only for Innovus: SKY130_ENV_INNOVUS='export OA_HOME=...' (see sky130cad/toolenv.py).
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sky130cad import (abstract, cadence_setup, cell_array, charlib, download, drc_deck, drc_tests,  # noqa: E402
                       antenna_deck, cellrc, gds_fix, library, lvs, lvs_deck, mosgen, osu, pcell, pinaccess, patches, release, smoke, sources, spectre_models, spectre_netlist, tech,
                       toolenv, virtuoso)

LIB = sources.FDSC['name']
VALIDATION_CELLS = 'inv_1,nand2_1,xor2_1,mux2_1,mux4_1,fa_1,dfxtp_1,dfxtp_4'
CHAR_CELLS = 'inv_1,mux2_1,dfxtp_1'


def P(a, *parts):
    return os.path.join(a.work, *parts)


def full(name):
    return name if name.startswith(LIB) else '%s__%s' % (LIB, name)


def cell_file(a, name, ext):
    hits = glob.glob(P(a, 'upstream', LIB, 'cells', '*', full(name) + '.' + ext))
    if not hits:
        raise SystemExit('no %s for %s in %s' % (ext, name, P(a, 'upstream', LIB)))
    return hits[0]


def pegasus_drc(a, gds, top, outdir):
    os.makedirs(outdir, exist_ok=True)
    deck = P(a, 'drc', 'sky130_full.pvl')
    if not os.path.exists(deck):
        drc_deck.write(deck)
    rc = toolenv.run(['pegasus', '-drc', '-dp', str(a.jobs), '-gds', os.path.abspath(gds), '-top_cell', top,
                      os.path.abspath(deck)], outdir, os.path.join(outdir, 'peg.out'), a.env)
    ascii_ = os.path.join(outdir, 'sky130_full.drc_errors.ascii')
    if rc or not os.path.exists(ascii_):
        raise SystemExit('pegasus failed (rc=%d); see %s/peg.out' % (rc, outdir))
    return ascii_, os.path.join(outdir, 'result.sum')


# ------------------------------------------------------------------ steps

def do_download(a):
    download.main(a.work, a.corners, a.fdsc_from, a.fdpr_from, a.lvs_from, a.cornell_from, a.cds_from, a.cornell,
                  a.osu_lib, a.osu_from)


def do_convert(a):
    qrc = a.qrc or (P(a, 'upstream', 'sky130_cds', 'PEX', 'qrcTechFile')
                    if os.path.exists(P(a, 'upstream', 'sky130_cds', 'PEX', 'qrcTechFile')) else None)
    tech.build(P(a, 'upstream', LIB), P(a, 'tech'), a.corners, LIB, qrc, a.jobs)


def do_patches(a):
    out, summary = patches.write(a.work, LIB)
    print('\n'.join(summary))
    print('patch files in', out)


def do_cadence_setup(a):
    for f in cadence_setup.write(P(a, 'tech'), P(a, 'cadence')):
        print('wrote', f)


def do_drc_deck(a):
    print('wrote %s (%d rules)' % (P(a, 'drc', 'sky130_full.pvl'), drc_deck.write(P(a, 'drc', 'sky130_full.pvl'))))


def do_drc_validate(a):
    d = P(a, 'drc', 'validate')
    os.makedirs(d, exist_ok=True)
    tests_gds, tests_tsv = os.path.join(d, 'drc_tests.gds'), os.path.join(d, 'drc_tests_cases.tsv')
    drc_tests.write(tests_gds, tests_tsv)
    ascii_, _ = pegasus_drc(a, tests_gds, 'drc_tests', os.path.join(d, 'tests'))
    bad = drc_tests.check(tests_tsv, ascii_)
    arr_gds, arr_tsv = os.path.join(d, 'cells.gds'), os.path.join(d, 'cells.tsv')
    cell_array.build(arr_gds, arr_tsv, sorted(glob.glob(P(a, 'tech', 'gds', '*.gds'))))
    ascii_, _ = pegasus_drc(a, arr_gds, 'cell_array', os.path.join(d, 'cells'))
    cell_array.report(arr_tsv, ascii_)
    all_errs = drc_tests.read_errors(ascii_)
    # Block-level rules, expected on standalone cells: nwell.4 (an n-well gets its contacted tap
    # from separate tap cells) and implant minimum area (the tap cells' small implant patches
    # merge with their neighbours). `smoke` checks them on a placed and routed block.
    block = ('nwell.4', 'nsd.10a', 'psd.10b', 'nsd.11', 'psd.11')
    errs = [e for e in all_errs if e[0] not in block]
    print('DRC validation: %d test cases failed; %d errors on fd_sc cells (+%d block-level results on '
          'standalone cells: %s)' % (bad, len(errs), len(all_errs) - len(errs), ', '.join(block)))
    if bad or errs:
        sys.exit(1)


def do_antenna_deck(a):
    print('wrote %s (%d rules)' % (P(a, 'drc', 'sky130_antenna.pvl'), antenna_deck.write(P(a, 'drc', 'sky130_antenna.pvl'))))


def run_antenna(a, gds, top, outdir):
    deck = P(a, 'drc', 'sky130_antenna.pvl')
    antenna_deck.write(deck)
    os.makedirs(outdir, exist_ok=True)
    rc = toolenv.run(['pegasus', '-drc', '-dp', str(a.jobs), '-gds', os.path.abspath(gds), '-top_cell', top, deck],
                     outdir, os.path.join(outdir, 'peg.out'), a.env)
    rpt = os.path.join(outdir, 'sky130_antenna.drc_errors.ascii')
    if rc or not os.path.exists(rpt):
        raise SystemExit('pegasus failed (rc=%d); see %s/peg.out' % (rc, outdir))
    return rpt


def do_antenna_validate(a):
    d = P(a, 'drc', 'antenna_validate')
    os.makedirs(d, exist_ok=True)
    gds, tsv = os.path.join(d, 'antenna_tests.gds'), os.path.join(d, 'antenna_tests.tsv')
    antenna_deck.write_tests(gds, tsv)
    bad = antenna_deck.check(tsv, run_antenna(a, gds, 'antenna_tests', os.path.join(d, 'run')))
    print('antenna validation: %d cases wrong' % bad)
    sys.exit(1 if bad else 0)


def do_antenna(a):
    import collections
    errs = drc_tests.read_errors(run_antenna(a, a.gds, a.top, P(a, 'drc', 'antenna_runs', a.top)))
    print('%s: %d antenna results %s' % (a.top, len(errs), dict(collections.Counter(e[0] for e in errs))))
    sys.exit(1 if errs else 0)


def do_drc(a):
    if a.deck == 'cornell':
        d = P(a, 'drc', 'runs_cornell', a.top)
        os.makedirs(d, exist_ok=True)
        root = P(a, 'upstream', sources.CORNELL['name'], 'Sky130_DRC')
        env = toolenv.env_snippet(a.env) + '\nexport PEGASUS_DRC=%s' % root
        toolenv.run(['pegasus', '-drc', '-dp', str(a.jobs), '-gds', os.path.abspath(a.gds), '-top_cell', a.top,
                     os.path.join(root, 'sky130_rev_0.0_1.0.drc.pvl')], d, os.path.join(d, 'peg.out'), env)
        hits = glob.glob(os.path.join(d, '*.drc_errors.ascii'))
        if not hits:
            raise SystemExit('pegasus failed; see %s/peg.out' % d)
        errs = drc_tests.read_errors(hits[0])
        import collections
        print('%s: %d results with the Cornell deck: %s' % (a.top, len(errs), collections.Counter(e[0] for e in errs).most_common(10)))
        return
    ascii_, summ = pegasus_drc(a, a.gds, a.top, P(a, 'drc', 'runs', a.top))
    errs = drc_tests.read_errors(ascii_)
    print('%s: %d DRC results (%s)' % (a.top, len(errs), summ))


def do_lvs_deck(a):
    print('wrote %s (%d MOS devices)' % (P(a, 'lvs', 'sky130_lvs.pvl'), lvs_deck.write(P(a, 'lvs', 'sky130_lvs.pvl'))))
    src = P(a, 'upstream', 'lvs', 'sky130.lvs.pvl')
    if os.path.exists(src):
        n = lvs.patch_deck(src, P(a, 'lvs', 'cornell_lvs.pvl'))
        print('wrote %s (Cornell, private comparison; %d -grey lines commented)' % (P(a, 'lvs', 'cornell_lvs.pvl'), n))


def lvs_one(a, deck, name):
    """LVS of one fd_sc cell; returns (name, result, summary)."""
    c = name[len(LIB) + 2:]
    out = P(a, 'lvs', 'runs_' + a.deck, name)
    if a.source == 'spice':
        os.makedirs(out, exist_ok=True)
        src = os.path.join(out, name + '.src.cdl')
        lvs.spice_to_cdl(cell_file(a, c, 'spice'), src)
    else:
        src = cell_file(a, c, 'cdl')
    res, summ = lvs.run(cell_file(a, c, 'gds'), name, src, out, deck, a.env)
    return name, res, summ


def do_lvs_check(a):
    deck = lvs.deck_path(a.work, a.deck)
    if a.cells == 'all':
        names = sorted(os.path.basename(g)[:-4] for g in glob.glob(P(a, 'upstream', LIB, 'cells', '*', LIB + '__*.gds')))
    else:
        names = [full(c) for c in a.cells.split(',')]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, a.jobs)) as ex:
        rows = list(ex.map(lambda n: lvs_one(a, deck, n), names))
    bad = [r for r in rows if r[1] != 'MATCH']
    for name, res, summ in (rows if len(rows) <= 20 else bad):
        print('%-34s %-9s %s' % (name, res, summ[:300]))
    print('LVS (%s deck, %s source): %d/%d cells MATCH' % (a.deck, a.source, len(rows) - len(bad), len(rows)))
    sys.exit(1 if bad else 0)


def do_lvs(a):
    res, summ = lvs.run(a.gds, a.top, a.netlist, P(a, 'lvs', 'runs', a.top), lvs.deck_path(a.work, a.deck),
                        a.env, a.pins_from)
    print(a.top, res, summ)
    sys.exit(0 if res == 'MATCH' else 1)


def do_spectre_models(a):
    spectre_models.main(P(a, 'upstream', 'sky130_fd_pr', 'models'), P(a, 'spectre', 'models'),
                        ['tt', 'ss', 'ff', 'sf', 'fs'])


def do_characterize(a):
    netdir = a.netlist_dir or P(a, 'spectre', 'netlists')
    cells = a.cells.split(',')
    if not a.netlist_dir:
        os.makedirs(netdir, exist_ok=True)
        for c in cells:
            spectre_netlist.convert(cell_file(a, c, 'spice'), os.path.join(netdir, full(c) + '.spice'))
    cfg, skipped = charlib.fdsc_config(P(a, 'tech', '%s__%s.lib' % (LIB, a.corner)), cells, netdir,
                                       P(a, 'spectre', 'models'), a.corner, LIB)
    for s in skipped:
        print('skipped (not supported):', s)
    out = a.out or P(a, 'char', a.corner + ('_' + os.path.basename(a.netlist_dir.rstrip('/')) if a.netlist_dir else ''))
    lib, comp = charlib.run_config(cfg, out, a.jobs, a.env)
    print(open(comp).read())
    print('Liberty:', lib)


def do_extract(a):
    from sky130cad import quantus
    quantus.main(a)


def do_abstract(a):
    gds = [cell_file(a, c, 'gds') for c in a.cells.split(',')]
    out = P(a, 'abstract', 'fdsc_abstract.lef')
    rc, errs, ok = abstract.run(P(a, 'abstract'), out, gds, P(a, 'tech', LIB + '_innovus.tlef'),
                                a.liberty or P(a, 'tech', '%s__ss_150C_1v60.lib' % LIB), a.env)
    print('abstract rc=%d, %d error lines, LEF %s' % (rc, len(errs), out if ok else 'NOT WRITTEN'))
    for e in errs[:10]:
        print('  ' + e[:200])
    if ok:
        print('\n'.join(abstract.compare(P(a, 'tech', LIB + '_cells.lef'), out)))
    sys.exit(0 if ok and not errs else 1)


def do_virtuoso_setup(a):
    v = virtuoso.setup(a.work)
    print('wrote %s/cds.lib (library sky130_fd_pr_main). Start Virtuoso there: cd %s; virtuoso &' % (v, v))


def do_xtor_check(a):
    made, results = virtuoso.xtor_check(a.work, a.env)
    print('PCell instances created: %d of %d' % (made, len(virtuoso.CONFIGS)))
    bad = made != len(virtuoso.CONFIGS)
    for name, dev, w, geo, ndrc, res in results:
        print('%-10s %-14s W=%-5g %-6s DRC results=%s LVS=%s' % (name, dev, w, geo, ndrc, res))
        bad |= geo != 'ok' or ndrc != 0 or res != 'MATCH'
    sys.exit(1 if bad else 0)


def do_smoke(a):
    for f in (P(a, 'cadence', 'innovus_fdsc.tcl'), P(a, 'drc', 'sky130_full.pvl')):
        if not os.path.exists(f):
            raise SystemExit('missing %s: run cadence-setup and drc-deck first' % f)
    cdl = P(a, 'library', LIB + '.cdl')
    if not os.path.exists(cdl):
        os.makedirs(P(a, 'library'), exist_ok=True)
        library.write_cdl(P(a, 'upstream', LIB), cdl)
    r = smoke.run(a.work, a.env, lvs_deck=lvs.deck_path(a.work), lib_cdl=cdl)
    for k, v in r.items():
        print('%-18s %s' % (k, v))
    ok = (r.get('innovus') and r.get('innovus_drc') and r.get('connectivity') and not r.get('empty_structures')
          and r.get('pegasus_results') == 0 and r.get('lvs') == 'MATCH')
    print('SMOKE', 'PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


def do_release(a):
    out = os.path.abspath(a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'release'))
    r = release.build(a.work, out, os.path.dirname(os.path.abspath(__file__)), a.env, a.version)
    print('release %s: %d files, %.1f MB, DRC deck %d rules, %d Spectre netlists, %d files with paths scrubbed; '
          'largest %s (%.1f MB)' % (out, r['files'], r['MB'], r['drc_rules'], r['netlists'], r['scrubbed'],
                                    r['largest'][1], r['largest'][0] / 1e6))


def do_package(a):
    root = os.path.dirname(os.path.abspath(__file__))
    rel = os.path.abspath(a.release or os.path.join(root, 'release'))
    archive, digest = release.package(rel, os.path.abspath(a.dist or os.path.join(root, 'dist')))
    print('%s (%.1f MB)\nsha256 %s' % (archive, os.path.getsize(archive) / 1e6, digest))


def do_release_check(a):
    rel = os.path.abspath(a.release or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'release'))
    res = release.check(rel, P(a, 'release_check'), a.env, a.jobs, not a.no_smoke)
    for k, (ok, detail) in res.items():
        print('%-14s %-4s %s' % (k, 'ok' if ok else 'FAIL', detail))
    sys.exit(0 if all(ok for ok, _ in res.values()) else 1)


def do_mos(a):
    fdpr = P(a, 'upstream', 'sky130_fd_pr')
    name = mosgen.main(a.device, a.w, a.l, a.nf, not a.no_tap, a.tie, a.out or P(a, 'mos'),
                       fdpr if os.path.exists(fdpr) else None)
    print('wrote %s.gds/.cdl/.spice in %s' % (name, a.out or P(a, 'mos')))


def do_mos_check(a):
    rows = mosgen.check(a.work, a.env, a.jobs)
    bad = 0
    for name, binok, drc, cdrc, res, idd in rows:
        expect_tapless = name.endswith('_notap')
        drc_ok = drc is not None and (not drc or (expect_tapless and set(drc) <= {'nwell.4'}))
        ok = drc_ok and binok is not False and res in (None, 'MATCH') and (idd is None or idd > 0)
        bad += not ok
        print('%-4s %-34s bin=%-5s DRC=%-14s Cornell DRC=%-28s LVS=%-8s Id=%s' % (
            'ok' if ok else 'FAIL', name, binok, dict(drc) if drc else drc, dict(cdrc) if isinstance(cdrc, dict) else cdrc,
            res, '%.0f uA' % idd if idd else idd))
    sys.exit(1 if bad else 0)


def do_pcells(a):
    made, log = pcell.build(a.work, a.env)
    print('PCells created: %s (%d of %d); log %s' % (', '.join(sorted(made)), len(made), len(mosgen.DEVICES), log))
    sys.exit(0 if len(made) == len(mosgen.DEVICES) else 1)


def do_pcell_check(a):
    bad = 0
    for name, inst, geo, drc, res in pcell.check(a.work, a.env):
        ok = inst and geo == 'equal' and drc is not None and not drc and res in (None, 'MATCH')
        bad += not ok
        print('%-4s %-34s instance=%-5s geometry=%-24s DRC=%-10s LVS=%s' % ('ok' if ok else 'FAIL', name, inst, geo,
                                                                             dict(drc) if drc else drc, res))
    sys.exit(1 if bad else 0)


def do_library(a):
    fdsc = P(a, 'upstream', LIB)
    d = P(a, 'library')
    os.makedirs(d, exist_ok=True)
    print('CDL: %d cells' % library.write_cdl(fdsc, os.path.join(d, LIB + '.cdl')))
    print('GDS: %d structures' % library.write_gds(fdsc, os.path.join(d, LIB + '.gds')))
    n, black = library.write_verilog(P(a, 'tech', '%s__ss_150C_1v60.lib' % LIB), os.path.join(d, LIB + '.v'))
    print('Verilog: %d functional models (black boxes, statetable cells: %s)' % (n, ', '.join(black) or 'none'))
    tech_lib = P(a, 'upstream', 'sky130_cds', 'VirtuosoOA', 'sky130')
    if os.path.exists(tech_lib):
        rc, views = library.write_oa(os.path.join(d, LIB + '.gds'), tech_lib,
                                     P(a, 'upstream', 'sky130_cds', 'VirtuosoOA', 'layer.map'), os.path.join(d, 'oa'), a.env)
        print('OA library: strmin rc=%d, %d layout views' % (rc, views))
        made, total = library.write_symbols(os.path.join(d, 'oa'), P(a, 'tech', LIB + '_cells.lef'), a.env)
        print('OA library: %d of %d symbol views' % (made, total))


def do_lvs_block(a):
    cdl = P(a, 'library', LIB + '.cdl')
    if not os.path.exists(cdl):
        library.write_cdl(P(a, 'upstream', LIB), cdl)
    res, summ, warn = library.block_lvs(a.gds, a.top, a.netlist, cdl, a.out or P(a, 'lvs', 'block', a.top),
                                        lvs.deck_path(a.work, a.deck), a.env)
    for w in warn[:10]:
        print('warning:', w)
    print(a.top, res, summ[:400])
    sys.exit(0 if res == 'MATCH' else 1)


def do_osu_check(a):
    import collections
    a.osu = a.osu or P(a, 'upstream', 'sky130_osu_sc_t18', '18T_hs')
    deck = P(a, 'drc', 'sky130_full.pvl')
    drc_deck.write(deck)
    gds_dir, tag = None, 'osu_check'
    if a.patch:
        gds_dir, tag = P(a, 'osu_patched', 'gds'), 'osu_check_patched'
        r = osu.patch_library(a.osu, gds_dir)
        print('implant patch: %d rectangles extended in %d cells (%d non-rectangular implants left alone)'
              % (sum(v[0] for v in r.values()), len([v for v in r.values() if v[0]]), sum(v[1] for v in r.values())))
    res, lv, sizes = osu.check(a.work, a.osu, deck, lvs.deck_path(a.work), a.env, a.jobs, gds_dir, tag)
    for kind in ('alone', 'abut'):
        per = res.get(kind)
        if per is None:
            print('DRC %s: pegasus failed' % kind)
            continue
        tot = collections.Counter()
        for c in per.values():
            tot.update(c)
        print('DRC %-5s: %d cells with results, %d results: %s' % (kind, len([c for c in per if per[c]]), sum(tot.values()),
                                                                  dict(tot.most_common(12))))
    m = collections.Counter(r for r, _ in lv.values())
    print('LVS: %s' % dict(m))
    for c, (r, s) in sorted(lv.items()):
        if r != 'MATCH':
            print('  %-36s %s %s' % (c, r, s[:150]))


def do_ccs_libs(a):
    """Liberty with CCS timing and CCS noise kept (cf. gsclib045 ccs/noise views), for the
    corners whose upstream JSON carries them; large files, written to WORK/tech/ccs."""
    from sky130cad import liberty_json
    out = P(a, 'tech', 'ccs')
    os.makedirs(out, exist_ok=True)
    for c in (a.ccs_corner or [x for x in a.corners if 'ccsnoise' in x]):
        f = os.path.join(out, '%s__%s.lib' % (LIB, c))
        liberty_json.convert(P(a, 'upstream', LIB), c, f, LIB, keep_ccs=True)
        print('wrote %s (%.0f MB)' % (f, os.path.getsize(f) / 1e6))


def do_cell_rc(a):
    lib = a.lib or P(a, 'tech', '%s__ss_n40C_1v60_ccsnoise.lib' % LIB)
    print('%s (input slew %.3f ns)' % (lib, a.slew))
    print(cellrc.report(lib, a.cells.split(','), slew=a.slew))


def do_pin_access(a):
    lef = a.lef or P(a, 'tech', LIB + '_cells.lef')
    rows = pinaccess.audit(lef, few=a.few)
    for r in rows:
        print('%-36s %-6s %4d access points  (spread %.3f um)' % r)
    zero = [r for r in rows if r[2] == 0]
    print('%s: %d signal pins with fewer than %d access points, %d with none' % (lef, len(rows), a.few, len(zero)))
    sys.exit(1 if zero else 0)


def do_fix_gds(a):
    sys.exit(gds_fix.main(a.gds_in, a.gds_out, a.cell_gds))


def do_all(a):
    for step in (do_download, do_convert, do_patches, do_cadence_setup, do_drc_deck, do_drc_validate,
                 do_lvs_deck, do_spectre_models):
        print('==', step.__name__[3:])
        step(a)
    steps = [do_lvs_check, do_mos_check, do_characterize, do_abstract, do_smoke]
    if os.path.exists(P(a, 'tech', 'qrcTechFile')):
        steps.insert(3, do_extract)
    if os.path.exists(virtuoso.lib_path(a.work)):
        steps.append(do_xtor_check)
    for step in steps:
        print('==', step.__name__[3:])
        try:
            step(a)
        except SystemExit as e:
            if e.code:
                raise


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--work', default=os.environ.get('SKY130_WORK', os.path.expanduser('~/sky130_work')))
    p.add_argument('--env', default=None, help='shell snippet putting Cadence tools on PATH (default $SKY130_TOOL_ENV)')
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--corners', nargs='+', default=sources.DEFAULT_CORNERS)
    sub = p.add_subparsers(dest='step', required=True)
    s = sub.add_parser('download')
    s.add_argument('--fdsc-from'); s.add_argument('--fdpr-from'); s.add_argument('--lvs-from'); s.add_argument('--cornell-from')
    s.add_argument('--cds-from'); s.add_argument('--cornell', action='store_true', help='also fetch the unlicensed Cornell PDK')
    s.add_argument('--osu', dest='osu_lib', action='store_true', help='also fetch the OSU 18T cells (second library)')
    s.add_argument('--osu-from')
    s = sub.add_parser('convert'); s.add_argument('--qrc', help='QRC tech file (default: the downloaded sky130_cds one)')
    for name in ('patches', 'cadence-setup', 'drc-deck', 'drc-validate', 'lvs-deck', 'spectre-models', 'smoke',
                 'virtuoso-setup', 'xtor-check'):
        sub.add_parser(name)
    sub.add_parser('antenna-deck'); sub.add_parser('antenna-validate')
    s = sub.add_parser('antenna'); s.add_argument('gds'); s.add_argument('top')
    s = sub.add_parser('drc'); s.add_argument('gds'); s.add_argument('top')
    s.add_argument('--deck', choices=['sky130cad', 'cornell'], default='sky130cad')
    s = sub.add_parser('lvs-check'); s.add_argument('--cells', default=VALIDATION_CELLS, help="'all' or a list")
    s.add_argument('--deck', choices=['sky130cad', 'cornell'], default='sky130cad')
    s.add_argument('--source', choices=['spice', 'cdl'], default='spice')
    s = sub.add_parser('lvs'); s.add_argument('gds'); s.add_argument('top'); s.add_argument('netlist')
    s.add_argument('--pins-from'); s.add_argument('--deck', choices=['sky130cad', 'cornell'], default='sky130cad')
    s = sub.add_parser('characterize'); s.add_argument('--cells', default=CHAR_CELLS)
    s.add_argument('--corner', default='ss_150C_1v60'); s.add_argument('--netlist-dir'); s.add_argument('--out')
    s = sub.add_parser('extract'); s.add_argument('--cells', default=CHAR_CELLS, help="'all' or a list")
    s.add_argument('--temperature', type=float, default=150.0); s.add_argument('--qrc')
    s = sub.add_parser('abstract'); s.add_argument('--cells', default=CHAR_CELLS); s.add_argument('--liberty')
    s = sub.add_parser('mos'); s.add_argument('--device', default='nfet_01v8', choices=sorted(mosgen.DEVICES))
    s.add_argument('--w', type=float, default=1.0, help='per-finger width, um'); s.add_argument('--l', type=float, default=0.15)
    s.add_argument('--nf', type=int, default=1); s.add_argument('--no-tap', action='store_true')
    s.add_argument('--tie', action='store_true', help='body tied to source'); s.add_argument('--out')
    sub.add_parser('mos-check')
    sub.add_parser('library')
    s = sub.add_parser('cell-rc'); s.add_argument('--cells', required=True); s.add_argument('--lib')
    s.add_argument('--slew', type=float, default=0.1)
    s = sub.add_parser('pin-access'); s.add_argument('--lef'); s.add_argument('--few', type=int, default=4)
    s = sub.add_parser('ccs-libs'); s.add_argument('--corner', dest='ccs_corner', action='append',
                                                   help='upstream corner (repeatable); default: the *_ccsnoise corners')
    s = sub.add_parser('osu-check'); s.add_argument('--osu', help='.../sky130_osu_sc_t18/18T_hs (default: downloaded)')
    s.add_argument('--patch', action='store_true', help='extend implants to the cell edges first (WORK/osu_patched)')
    sub.add_parser('pcells')
    sub.add_parser('pcell-check')
    s = sub.add_parser('lvs-block'); s.add_argument('gds'); s.add_argument('top'); s.add_argument('netlist'); s.add_argument('--out')
    s.add_argument('--deck', choices=['sky130cad', 'cornell'], default='sky130cad')
    s = sub.add_parser('fix-gds'); s.add_argument('gds_in'); s.add_argument('gds_out'); s.add_argument('cell_gds', nargs='+')
    s = sub.add_parser('release'); s.add_argument('--out', help='default: <repository>/release')
    s.add_argument('--version', help='release version (default: today, YYYY.MM.DD)')
    s = sub.add_parser('package'); s.add_argument('--release', help='default: <repository>/release')
    s.add_argument('--dist', help='default: <repository>/dist')
    s = sub.add_parser('release-check'); s.add_argument('--release', help='default: <repository>/release')
    s.add_argument('--no-smoke', action='store_true')
    s = sub.add_parser('all'); s.add_argument('--fdsc-from'); s.add_argument('--fdpr-from'); s.add_argument('--lvs-from')
    s.add_argument('--cornell-from'); s.add_argument('--cds-from'); s.add_argument('--cornell', action='store_true')
    s.add_argument('--qrc')
    a = p.parse_args()
    a.work = os.path.abspath(os.path.expanduser(a.work))
    for k, v in (('qrc', None), ('fdsc_from', None), ('fdpr_from', None), ('lvs_from', None), ('cornell_from', None),
                 ('cds_from', None),
                 ('cells', None),
                 ('netlist_dir', None), ('out', None), ('liberty', None), ('corner', 'ss_150C_1v60'),
                 ('deck', 'sky130cad'), ('source', 'spice'), ('cornell', False), ('osu_lib', False), ('osu_from', None)):
        if not hasattr(a, k):
            setattr(a, k, v)
    if a.step == 'all':
        a.cells = CHAR_CELLS
        a.temperature = 150.0
    globals()['do_' + a.step.replace('-', '_')](a)


if __name__ == '__main__':
    main()
