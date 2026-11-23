"""Build the Cadence technology folder WORK/tech from the upstream fd_sc checkout.

  python3 sky130.py convert [--corners C ...] [--qrc QRC_TECH_FILE] [--jobs N]

Writes (LIB = sky130_fd_sc_hs):
- LIB__<corner>.lib       NLDM Liberty per corner, from the upstream JSON (liberty_json.py)
- LIB.tlef                upstream technology LEF, unchanged
- LIB_innovus.tlef        same with `LAYER licon TYPE CUT ; END licon` after pwell. Innovus 20.x
                          rejects the upstream file: "IMPLF-121: You need to have cut layer
                          after layer 'pwell'" (masterslice layers go straight to the li1
                          routing layer).
- LIB_cells.lef           every cell MACRO in one file (*.magic.lef skipped). Four macros
                          (diode_2, fill_diode_2/4/8) carry pre-release `FOREIGN scs8hs_*`
                          names; Innovus streamOut then references GDS structures that do not
                          exist and those cells lose all geometry. FOREIGN is set to the macro name.
- gds/                    links to the upstream cell GDS (for streamOut -merge); patched copies
                          for the cells in sky130cad/cellfix.py (xor3_1 pin access)
- streamOut.map           Innovus layer map (li1..met5 drawing 20, cuts 44)
- extraction.layermap     explicit LEF-to-QRC layer mapping (li1 is a routing layer here)
- qrcTechFile             link to --qrc if given (from your PDK; not public)
"""
import concurrent.futures as cf
import glob
import os
import re

from . import liberty_json

GDS = {'li1': 67, 'met1': 68, 'met2': 69, 'met3': 70, 'met4': 71, 'met5': 72}
CUTS = {'mcon': 67, 'via': 68, 'via2': 69, 'via3': 70, 'via4': 71}
TABLE_GROUPS = ('timing', 'internal_power', 'leakage_power', 'lu_table_template',
                'power_lut_template', 'operating_conditions')


def patch_tlef(text):
    if 'LAYER licon' in text:
        return text
    assert text.count('END pwell\n') == 1, 'unexpected tech LEF: no single "END pwell"'
    return text.replace('END pwell\n', 'END pwell\n\nLAYER licon\n  TYPE CUT ;\nEND licon\n', 1)


def fix_foreign(macro_text):
    """Return (text, old_name or None) with FOREIGN set to the MACRO name."""
    name = macro_text.split()[1]
    m = re.search(r'^(\s*FOREIGN\s+)(\S+)', macro_text, re.M)
    if m and m.group(2) != name:
        return macro_text[:m.start(2)] + name + macro_text[m.end(2):], m.group(2)
    return macro_text, None


def cell_lef(libdir, lib):
    lef = ['VERSION 5.7 ;', 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', '']
    renamed, n = [], 0
    for f in sorted(glob.glob(os.path.join(libdir, 'cells', '*', lib + '__*.lef'))):
        if f.endswith('.magic.lef'):
            continue
        m = re.search(r'^MACRO .*?^END %s__\S+\s*$' % lib, open(f).read(), re.S | re.M)
        if not m:
            continue
        text, old = fix_foreign(m.group(0))
        if old:
            renamed.append('%s (was %s)' % (text.split()[1], old))
        lef += [text, '']
        n += 1
    lef.append('END LIBRARY')
    return '\n'.join(lef) + '\n', n, renamed


def stream_map():
    lines = ['# Innovus streamOut map for sky130 (written by sky130cad/tech.py)']
    for layer, num in GDS.items():
        for purpose in ('NET', 'SPNET', 'PIN', 'FILL', 'VIA', 'VIAFILL'):
            lines.append('%s\t%s\t%d\t20' % (layer, purpose, num))
        lines += ['NAME\t%s/PIN\t%d\t20' % (layer, num), 'NAME\t%s/SPNET\t%d\t20' % (layer, num), '']
    for cut, num in CUTS.items():
        lines += ['%s\tVIA\t%d\t44' % (cut, num), '%s\tVIAFILL\t%d\t44' % (cut, num)]
    return '\n'.join(lines) + '\n'


def extraction_layermap():
    pairs = []
    cuts = list(CUTS)
    for i, layer in enumerate(GDS):
        pairs.append(layer)
        if i < len(cuts):
            pairs.append(cuts[i])
    return ('# Explicit LEF-to-QRC mapping (sky130cad/tech.py). Source this before extraction.\n'
            'extraction_setup \\\n    -technology_layer_map \\\n' +
            ' \\\n'.join('        %s %s' % (n, n) for n in pairs) + '\n')


def strip_group(text, name):
    out, i = [], 0
    pat = re.compile(r'\n(\s*)%s\s*\([^)]*\)\s*\{' % name)
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            return ''.join(out)
        out.append(text[i:m.start()])
        depth, j = 1, m.end()
        while depth:
            depth += {'{': 1, '}': -1}.get(text[j], 0)
            j += 1
        i = j


def functional(src, dst):
    """Liberty without timing/power tables (small; for logic-only tools)."""
    text = open(src).read()
    for g in TABLE_GROUPS:
        text = strip_group(text, g)
    open(dst, 'w').write(text)


def _lib_job(args):
    libdir, corner, out, lib = args
    return corner, liberty_json.convert(libdir, corner, out, lib)


def build(libdir, out, corners, lib='sky130_fd_sc_hs', qrc=None, jobs=4):
    os.makedirs(out, exist_ok=True)
    jobs_args = [(libdir, c, os.path.join(out, '%s__%s.lib' % (lib, c)), lib) for c in corners]
    with cf.ProcessPoolExecutor(max_workers=max(1, jobs)) as ex:
        for corner, n in ex.map(_lib_job, jobs_args):
            print('Liberty %s: %d cells' % (corner, n))
    tlef = open(os.path.join(libdir, 'tech', lib + '.tlef')).read()
    open(os.path.join(out, lib + '.tlef'), 'w').write(tlef)
    open(os.path.join(out, lib + '_innovus.tlef'), 'w').write(patch_tlef(tlef))
    text, n, renamed = cell_lef(libdir, lib)
    from . import cellfix
    text, fixed = cellfix.fix_lef(text)
    open(os.path.join(out, lib + '_cells.lef'), 'w').write(text)
    print('cell LEF: %d macros; FOREIGN fixed for %d: %s; pin-access layout fix: %s'
          % (n, len(renamed), ', '.join(renamed), ', '.join(fixed) or 'none'))
    gds = os.path.join(out, 'gds')
    os.makedirs(gds, exist_ok=True)
    count = 0
    for f in glob.glob(os.path.join(libdir, 'cells', '*', lib + '__*.gds')):
        d = os.path.join(gds, os.path.basename(f))
        if os.path.lexists(d):
            os.remove(d)
        cell = os.path.basename(f)[:-4]
        if cell in cellfix.FIXES:
            cellfix.fix_gds(f, d, cell)        # patched copy (sky130cad/cellfix.py)
        else:
            os.symlink(os.path.abspath(f), d)
        count += 1
    print('gds/: %d cell links' % count)
    open(os.path.join(out, 'streamOut.map'), 'w').write(stream_map())
    open(os.path.join(out, 'extraction.layermap'), 'w').write(extraction_layermap())
    q = os.path.join(out, 'qrcTechFile')
    if qrc:
        if os.path.lexists(q):
            os.remove(q)
        os.symlink(os.path.abspath(qrc), q)
        print('qrcTechFile ->', qrc)
    elif not os.path.exists(q):
        print('no --qrc given: Innovus will use its default extraction (no qrcTechFile)')
    print('tech folder ready:', out)
