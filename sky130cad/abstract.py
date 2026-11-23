"""Cell LEF with the Virtuoso Abstract Generator (batch, no GUI).

  python3 sky130.py abstract --cells inv_1,mux2_1,dfxtp_1 [--liberty LIB]

Writes WORK/abstract/abs.replay and runs `abstract -nogui -replay`:
1. absImportLEF with ImportTechLef: a new OA library whose technology is the tech LEF
   (routing layers, vias, site).
2. absImportGDS of the cell GDS through a layer map limited to the routing and cut layers,
   their pin/label purposes, and the cell boundary marker areaid.sc (81/4) -> prBoundary.
3. absImportLogical of a Liberty file: pin directions and clock pins. For a custom cell, use
   the Liberty from `characterize`.
4. absPins, absExtract, absAbstract, absExportLEF.

Notes from validation against the shipped fd_sc LEF (inv_1, mux2_1, dfxtp_1):
- The abs* SKILL functions take no arguments; they read absSetOption values. The option
  names come from absExportOptions() and are not in the HTML documentation. Importing the
  Liberty needs both ImportLIBFiles and ImportLogicalFiles.
- PinsTextPinMap syntax is (textLPP geomLPP ...); fd_sc pin shapes use the `pin` purpose.
- Result: SIZE, CLASS, SITE, SYMMETRY, directions, USE CLOCK and every pin/OBS area identical
  to the shipped LEF. VPB/VNB are not created: the shipped LEF repeats them on the met1
  rails, while the GDS only labels the wells. Innovus ties them by globalNetConnect.
"""
import os
import re
import shutil

from . import toolenv

FDSC = {
    'routing': ['li1', 'met1', 'met2'], 'cuts': {'mcon': (67, 44), 'via': (68, 44)},
    'boundary': (81, 4), 'boundary_layers': 'prBoundary',
    'pinmap': '((li1 label) (li1 pin)) ((met1 label) (met1 pin))',
    'site': 'unit', 'power': '^(VPWR|VPB)$', 'ground': '^(VGND|VNB)$',
    'blockage': 'li1 mcon met1',
}
GDS_NUM = {'li1': 67, 'met1': 68, 'met2': 69, 'met3': 70, 'met4': 71, 'met5': 72}


def layer_map(s=FDSC):
    lines = []
    for layer in s['routing']:
        n = GDS_NUM[layer]
        lines += ['%s drawing %d 20' % (layer, n), '%s pin %d 16' % (layer, n), '%s label %d 5' % (layer, n)]
    for cut, (n, d) in s['cuts'].items():
        lines.append('%s drawing %d %d' % (cut, n, d))
    if s['boundary']:
        lines.append('prBoundary drawing %d %d' % s['boundary'])
    return '\n'.join(lines) + '\n'


def replay(tlef, libname, gds, maplef, out_lef, cells, liberty=None, s=FDSC):
    q = lambda v: '"%s"' % v
    r = ['absSetOption("LEFLibraryName" %s)' % q(libname),
         'absSetOption("ImportLefFiles" %s)' % q(tlef),
         'absSetOption("ImportTechLef" "true")',
         'absImportLEF()',
         'absSetLibrary(%s)' % q(libname),
         'absSetOption("DefaultBin" "Core")',
         'absSetOption("ImportGDSIIFiles" %s)' % q(' '.join(gds)),
         'absSetOption("ImportGDSIILayerMapFile" %s)' % q(maplef),
         'absImportGDS()',
         'absSetLibrary(%s)' % q(libname)]
    if liberty:
        r += ['absSetOption("ImportLogicalType" "LIB")',
              'absSetOption("ImportLIBFiles" %s)' % q(liberty),
              'absSetOption("ImportLogicalFiles" %s)' % q(liberty),
              'absImportLogical()',
              'absSetLibrary(%s)' % q(libname)]
    layers = ' '.join(s['routing'])
    r += ['absSetBinOption("Core" "PinsTextPinMap" %s)' % q(s['pinmap']),
          'absSetBinOption("Core" "PinsPowerNames" %s)' % q(s['power']),
          'absSetBinOption("Core" "PinsGroundNames" %s)' % q(s['ground']),
          'absSetBinOption("Core" "PinsBoundaryLayers" %s)' % q(s['boundary_layers']),
          'absSetBinOption("Core" "ExtractLayersSig" %s)' % q(layers),
          'absSetBinOption("Core" "ExtractLayersPwr" %s)' % q(layers),
          'absSetBinOption("Core" "ExtractPinLayersSig" %s)' % q(layers),
          'absSetBinOption("Core" "ExtractPinLayersPwr" %s)' % q(layers),
          'absSetBinOption("Core" "AbstractBlockageDetailedLayers" %s)' % q(s['blockage']),
          'absSetBinOption("Core" "AbstractSiteName" %s)' % q(s['site']),
          'absSelectBin("Core")', 'absSelectCells()', 'absPins()', 'absExtract()']
    r += ['absSetCellProp(%s "symmetry" "X Y")' % q(c) for c in cells]
    r += ['absAbstract()', 'absSetOption("ExportLEFFile" %s)' % q(out_lef),
          'absSetOption("ExportLEFBin" "Core")', 'absExportLEF()', 'absExit()']
    return '\n'.join(r) + '\n'


def run(work, out_lef, gds, tlef, liberty=None, env=None):
    work = os.path.abspath(work)
    os.makedirs(work, exist_ok=True)
    libname = 'abs_fdsc'
    for stale in ('.abstract', libname):
        shutil.rmtree(os.path.join(work, stale), ignore_errors=True)
    open(os.path.join(work, 'cds.lib'), 'w').write('# libraries are created by the replay\n')
    lmap = os.path.join(work, 'layers.map')
    open(lmap, 'w').write(layer_map())
    cells = [os.path.splitext(os.path.basename(g))[0] for g in gds]
    rp = os.path.join(work, 'abs.replay')
    open(rp, 'w').write(replay(os.path.abspath(tlef), libname, [os.path.abspath(g) for g in gds], lmap,
                               os.path.abspath(out_lef), cells, liberty and os.path.abspath(liberty)))
    if os.path.exists(out_lef):
        os.remove(out_lef)
    rc = toolenv.run(['abstract', '-nogui', '-replay', rp], work, os.path.join(work, 'abstract.out'), env)
    errs = [l.rstrip() for l in open(os.path.join(work, 'abstract.out')) if re.search(r'\*Error\*|\bERROR\b', l)]
    return rc, errs, os.path.exists(out_lef)


def lef_macros(path):
    out = {}
    text = open(path).read()
    for m in re.finditer(r'^MACRO (\S+)(.*?)^END \1', text, re.S | re.M):
        body = m.group(2)
        size = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)', body)
        pins = {}
        for p in re.finditer(r'^\s*PIN (\S+)(.*?)^\s*END \1', body, re.S | re.M):
            pb = p.group(2)
            pins[p.group(1)] = (re.search(r'DIRECTION (\w+)', pb).group(1) if 'DIRECTION' in pb else '-',
                                re.search(r'USE (\w+)', pb).group(1) if 'USE' in pb else '-',
                                sorted(set(re.findall(r'LAYER (\S+)', pb))))
        obs = re.search(r'^\s*OBS(.*?)^\s*END', body, re.S | re.M)
        out[m.group(1)] = {'size': tuple(float(x) for x in size.groups()) if size else None, 'pins': pins,
                           'obs_layers': sorted(set(re.findall(r'LAYER (\S+)', obs.group(1)))) if obs else [],
                           'class': (re.search(r'CLASS ([\w ]+?) ;', body) or [None, None])[1],
                           'site': (re.search(r'SITE (\S+)', body) or [None, None])[1]}
    return out


def layer_rects(body):
    """{(pin or 'OBS', layer): [rects in 5 nm units]}"""
    out = {}
    blocks = [(p.group(1), p.group(2)) for p in re.finditer(r'^\s*PIN (\S+)(.*?)^\s*END \1', body, re.S | re.M)]
    o = re.search(r'^\s*OBS(.*?)^\s*END\s*$', body, re.S | re.M)
    if o:
        blocks.append(('OBS', o.group(1)))
    for name, text in blocks:
        layer = None
        for tok in re.finditer(r'LAYER (\S+)|RECT\s+([-\d.\s]+?)\s*;', text):
            if tok.group(1):
                layer = tok.group(1)
            else:
                x0, y0, x1, y1 = (int(round(float(v) / 0.005)) for v in tok.group(2).split())
                out.setdefault((name, layer), []).append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    return out


def raster(rects):
    cells = set()
    for x0, y0, x1, y1 in rects:
        for x in range(x0, x1):
            for y in range(y0, y1):
                cells.add((x, y))
    return cells


def compare(ref, ours):
    """Lines describing each generated macro against the reference LEF; geometry compared by
    covered area (rasterized at 5 nm), so different rectangle fracturing counts as equal."""
    lines = []
    r, o = lef_macros(ref), lef_macros(ours)
    rt, ot = open(ref).read(), open(ours).read()
    for cell in sorted(o):
        a, b = o[cell], r.get(cell)
        if not b:
            lines.append('%s: not in reference' % cell)
            continue
        same = lambda k: 'same' if a[k] == b[k] else 'ours %s ref %s' % (a[k], b[k])
        lines.append('%s: SIZE %s, CLASS %s, SITE %s, OBS layers %s' % (cell, same('size'), same('class'),
                                                                      same('site'), same('obs_layers')))
        for p in sorted(set(a['pins']) | set(b['pins'])):
            pa, pb = a['pins'].get(p), b['pins'].get(p)
            lines.append('   pin %-6s %s' % (p, 'same' if pa == pb else 'ours %s ref %s' % (pa, pb)))
        ma = re.search(r'^MACRO %s\b(.*?)^END %s' % (re.escape(cell), re.escape(cell)), ot, re.S | re.M)
        mb = re.search(r'^MACRO %s\b(.*?)^END %s' % (re.escape(cell), re.escape(cell)), rt, re.S | re.M)
        ga, gb = layer_rects(ma.group(1)), layer_rects(mb.group(1))
        geo = []
        for k in sorted(set(ga) | set(gb), key=str):
            d = len(raster(ga.get(k, [])) ^ raster(gb.get(k, []))) * 0.005 ** 2
            geo.append('%s/%s:%s' % (k[0], k[1], 'same' if not d else 'diff %.4f um2' % d))
        lines.append('   geometry ' + ' '.join(geo))
    return lines
