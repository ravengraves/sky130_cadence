"""Every change this flow makes to upstream files, written as unified diffs for review.

  python3 sky130.py patches        -> WORK/patches/*.patch (+ summary)

The patches themselves are applied by the conversion code; this module only shows them
against the pristine upstream files:
1. tech-lef-licon.patch   sky130_fd_sc_hs.tlef: cut layer licon after pwell (Innovus IMPLF-121)
2. cell-lef-foreign.patch cell LEFs whose FOREIGN name is a pre-release scs8hs_* name
3. lvs-deck.patch         Cornell LVS deck: `lvs_black_box -grey` lines rejected by Pegasus 25.1
4. spectre-models.patch   sky130_fd_pr transistor files: subckt parameters for Spectre
5. spectre-netlist.patch  example cell netlist: number format Spectre misreads (1.12e+06u)
"""
import difflib
import glob
import os
import re
import shutil
import subprocess
import tempfile

from . import lvs, spectre_models, spectre_netlist, tech


def udiff(a_text, b_text, a_name, b_name):
    """Unified diff. Uses GNU `diff -u` when available: difflib takes minutes on the
    multi-megabyte model files where nearly every line changes."""
    if shutil.which('diff'):
        with tempfile.TemporaryDirectory() as t:
            fa, fb = os.path.join(t, 'a'), os.path.join(t, 'b')
            open(fa, 'w').write(a_text)
            open(fb, 'w').write(b_text)
            r = subprocess.run(['diff', '-u', '-U2', '--label', a_name, '--label', b_name, fa, fb],
                               stdout=subprocess.PIPE, text=True)
            return r.stdout
    return ''.join(difflib.unified_diff(a_text.splitlines(True), b_text.splitlines(True), a_name, b_name, n=2))


def write(work, lib='sky130_fd_sc_hs'):
    up = os.path.join(work, 'upstream')
    fdsc, fdpr = os.path.join(up, lib), os.path.join(up, 'sky130_fd_pr')
    out = os.path.join(work, 'patches')
    os.makedirs(out, exist_ok=True)
    summary = []

    tlef = os.path.join(fdsc, 'tech', lib + '.tlef')
    t = open(tlef).read()
    d = udiff(t, tech.patch_tlef(t), 'a/tech/%s.tlef' % lib, 'b/tech/%s_innovus.tlef' % lib)
    open(os.path.join(out, 'tech-lef-licon.patch'), 'w').write(d)
    summary.append('tech-lef-licon.patch: %d lines' % d.count('\n'))

    parts = []
    for f in sorted(glob.glob(os.path.join(fdsc, 'cells', '*', lib + '__*.lef'))):
        if f.endswith('.magic.lef'):
            continue
        text = open(f).read()
        m = re.search(r'^MACRO .*?^END %s__\S+\s*$' % lib, text, re.S | re.M)
        if not m:
            continue
        new, old = tech.fix_foreign(m.group(0))
        if old:
            rel = os.path.relpath(f, fdsc)
            parts.append(udiff(text, text.replace(m.group(0), new), 'a/' + rel, 'b/' + rel))
    open(os.path.join(out, 'cell-lef-foreign.patch'), 'w').write(''.join(parts))
    summary.append('cell-lef-foreign.patch: %d cell LEFs' % len(parts))

    deck = os.path.join(up, 'lvs', 'sky130.lvs.pvl')
    if os.path.exists(deck):
        tmp = os.path.join(out, '.lvs_patched.pvl')
        n = lvs.patch_deck(deck, tmp)
        d = udiff(open(deck).read(), open(tmp).read(), 'a/sky130.lvs.pvl', 'b/sky130.lvs.pvl')
        os.remove(tmp)
        open(os.path.join(out, 'lvs-deck.patch'), 'w').write(d)
        summary.append('lvs-deck.patch: %d lines commented' % n)

    parts = []
    for dev in ('nfet_01v8', 'nfet_01v8_lvt', 'pfet_01v8', 'pfet_01v8_hvt'):
        f = os.path.join(fdpr, 'cells', dev, 'sky130_fd_pr__%s__tt.pm3.spice' % dev)
        if os.path.exists(f):
            text = open(f).read()
            rel = os.path.relpath(f, fdpr)
            parts.append(udiff(text, spectre_models.patch_spice(text), 'a/' + rel, 'b/' + rel))
    open(os.path.join(out, 'spectre-models.patch'), 'w').write(''.join(parts))
    summary.append('spectre-models.patch: %d files shown (tt; every corner file gets the same change)' % len(parts))

    src = os.path.join(fdsc, 'cells', 'inv', lib + '__inv_1.spice')
    if os.path.exists(src):
        tmp = os.path.join(out, '.inv_1_spectre.spice')
        spectre_netlist.convert(src, tmp)
        d = udiff(open(src).read(), open(tmp).read(), 'a/cells/inv/%s__inv_1.spice' % lib,
                  'b/cells/inv/%s__inv_1.spice' % lib)
        os.remove(tmp)
        open(os.path.join(out, 'spectre-netlist.patch'), 'w').write(d)
        summary.append('spectre-netlist.patch: example (every cell netlist is converted the same way)')
    from . import cellfix
    t = open(os.path.join(work, 'tech', lib + '_cells.lef')).read() if os.path.exists(
        os.path.join(work, 'tech', lib + '_cells.lef')) else None
    if t is not None:
        lines = ['Layout fixes applied by `convert` (sky130cad/cellfix.py):', '']
        for cell, (bbox, rects, remove, add) in cellfix.FIXES.items():
            lines += ['%s: met1 polygon with bounding box %s (um) replaced by:' % (cell, bbox)]
            lines += ['  RECT %.3f %.3f %.3f %.3f' % r for r in rects]
            lines += ['LEF OBS met1 rectangles removed:'] + ['  RECT %.3f %.3f %.3f %.3f' % r for r in remove] + ['']
        open(os.path.join(out, 'cell-fixes.txt'), 'w').write('\n'.join(lines) + '\n')
        summary.append('cell-fixes.txt: %d cells (pin access)' % len(cellfix.FIXES))
    open(os.path.join(out, 'SUMMARY.txt'), 'w').write('\n'.join(summary) + '\n')
    return out, summary
