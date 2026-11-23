"""Pegasus LVS for sky130 cells: decks and runner.

  python3 sky130.py lvs-deck                      -> WORK/lvs/sky130_lvs.pvl (+ cornell_lvs.pvl)
  python3 sky130.py lvs CELL.gds TOP NETLIST [--pins-from NETLIST2] [--deck cornell]
  python3 sky130.py lvs-check [--cells all|inv_1,...] [--source spice|cdl] [--deck cornell]

Decks:
- sky130_lvs.pvl (default): this repository's deck, sky130cad/lvs_deck.py.
- cornell_lvs.pvl: the Cornell C2S2 sky130.lvs.pvl (no license; private comparison only),
  downloaded with a pinned SHA-256. Pegasus 25.1 stops on its `lvs_black_box -grey CELL` lines
  ("-grey option is deprecated" ERROR); they only name metal-finger capacitor cells, which
  digital cells never contain, and are commented out.

Source netlists for fd_sc cells: `spice` (default) converts the cell's .spice netlist, which
uses the current device names; the .cdl files still name some devices by legacy models
(decap: phighvt/nshort where the layout and .spice have pfet_01v8/nfet_01v8_lvt).

Source netlist preparation (written to OUTDIR/source.cdl):
- `*.SCALE MICRON` first: SkyWater CDL gives w/l in microns without a scale statement and the
  deck (`lvs_cdn_flow_options -cdl_use_scale`) otherwise reads w=0.74 as metres.
- legacy model names (nlowvt, nshort, pshort, phighvt; OSU-style netlists) mapped to the deck
  devices; extractor-only probe elements, NWDIODE well diodes, instances of empty
  `Dpar`/`Probe` subcircuits and `$` comments removed.
- `--pins-from`: copy the pin list when the netlist declares the top `.SUBCKT` without pins.
"""
import os
import re

from . import toolenv

STUBS = {'dpar', 'probe'}
LEGACY = {'nlowvt': 'nfet_01v8_lvt', 'nshort': 'nfet_01v8', 'pshort': 'pfet_01v8', 'phighvt': 'pfet_01v8_hvt'}


def deck_path(work, which='sky130cad'):
    """Path of the LVS deck; writes it if missing."""
    from . import lvs_deck
    if which == 'cornell':
        dst = os.path.join(work, 'lvs', 'cornell_lvs.pvl')
        if not os.path.exists(dst):
            patch_deck(os.path.join(work, 'upstream', 'lvs', 'sky130.lvs.pvl'), dst)
        return dst
    dst = os.path.join(work, 'lvs', 'sky130_lvs.pvl')
    lvs_deck.write(dst)          # generated, so always current
    return dst


SI = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'meg': 1e6, 'g': 1e9}


def number(v):
    m = re.match(r'^([-+0-9.eE]+)(meg|[fpnumkg])?$', v, re.I)
    if not m:
        raise ValueError(v)
    return float(m.group(1)) * (SI[m.group(2).lower()] if m.group(2) else 1.0)


def spice_to_cdl(src, dst):
    """SkyWater cell .spice (X calls of sky130_fd_pr__* subcircuits, sizes scaled by 1e-6) ->
    CDL with M devices and w/l in microns, D devices for diodes, R for `short`."""
    lines = []
    for raw in open(src).read().split('\n'):
        if raw.startswith('+') and lines:
            lines[-1] += ' ' + raw[1:].strip()
        else:
            lines.append(raw)
    out = []
    for line in lines:
        tok = line.split()
        if tok and tok[0][0] in 'xX' and len(tok) > 4 and tok[4] == 'short':
            line = ' '.join(['R' + tok[0][1:], tok[1], tok[2], 'short'])   # zero-ohm marker element
        elif tok and tok[0][0] in 'xX':
            model = next((t for t in tok[1:] if t.startswith('sky130_fd_pr__')), None)
            if model:
                dev = model[len('sky130_fd_pr__'):]
                i = tok.index(model)
                if dev.startswith('diode'):
                    # D anode cathode model area perimeter (a in um2, p in um after the 1e-6 scale)
                    kv = dict(t.split('=', 1) for t in tok[i + 1:] if '=' in t)
                    line = 'D%s %s %s %s area=%.6g pj=%.6g' % (tok[0][1:], tok[1], tok[2], dev,
                                                                number(kv.get('a', '0')), number(kv.get('p', '0')))
                    out.append(line)
                    continue
                params = []
                for t in tok[i + 1:]:
                    k, v = t.split('=', 1)
                    if k.lower() in ('w', 'l'):
                        params.append('%s=%.6g' % (k.lower(), number(v)))
                line = ' '.join(['M' + tok[0][1:]] + tok[1:i] + [dev] + params)
        out.append(line)
    open(dst, 'w').write('\n'.join(out) + '\n')


def patch_deck(src, dst):
    out, n = [], 0
    for line in open(src).read().split('\n'):
        if re.match(r'\s*lvs_black_box\s+-grey\b', line):
            out.append('// [sky130cad: -grey rejected by Pegasus 25.1] ' + line)
            n += 1
        else:
            out.append(line)
    os.makedirs(os.path.dirname(dst) or '.', exist_ok=True)
    open(dst, 'w').write('// Patched by sky130cad/lvs.py from %s\n' % src + '\n'.join(out))
    return n


def subckt_pins(path, top):
    m = re.search(r'^\.subckt\s+%s\b([^\n]*)' % re.escape(top), open(path).read(), re.I | re.M)
    return m.group(1).split() if m else None


def source_cdl(src, dst, top=None, pins=None):
    lines = []
    for raw in open(src).read().split('\n'):
        if raw.startswith('+') and lines:
            lines[-1] += ' ' + raw[1:].strip()
        else:
            lines.append(raw)
    out = ['*.SCALE MICRON']
    for line in lines:
        line = re.sub(r'\s\$.*$', '', line)
        tok = line.split()
        if tok and tok[0][0] in 'pP' and not tok[0].startswith('.'):
            continue
        if tok and tok[0][0] in 'dD' and len(tok) > 3 and tok[3].lower() == 'nwdiode':
            continue
        cell = [t for t in tok[1:] if '=' not in t][-1:] if tok and tok[0][0] in 'xX' else []
        if cell and cell[0].lower() in STUBS:
            continue
        if pins and len(tok) == 2 and tok[0].lower() == '.subckt' and tok[1] == top:
            line = ' '.join(tok + pins)
        if tok and tok[0][0] in 'mM' and len(tok) > 5 and tok[5].lower() in LEGACY:
            tok[5] = LEGACY[tok[5].lower()]
            line = ' '.join(tok)
        out.append(line)
    open(dst, 'w').write('\n'.join(out) + '\n')


def run(gds, top, netlist, outdir, deck, env=None, pins_from=None, extra=None):
    """Returns (result, summary) with result MATCH, MISMATCH or ERROR."""
    os.makedirs(outdir, exist_ok=True)
    cdl = os.path.join(outdir, 'source.cdl')
    source_cdl(netlist, cdl, top, subckt_pins(pins_from, top) if pins_from else None)
    cmd = ['pegasus', '-lvs'] + list(extra or []) + ['-gds', os.path.abspath(gds), '-top_cell', top,
           '-source_cdl', os.path.abspath(cdl), '-source_top_cell', top, os.path.abspath(deck)]
    rc = toolenv.run(cmd, outdir, os.path.join(outdir, 'peg.out'), env)
    rpt = os.path.join(outdir, top + '.lvsrpt.cls')
    if rc or not os.path.exists(rpt):
        return 'ERROR', 'pegasus rc=%d; see %s/peg.out' % (rc, outdir)
    text = open(rpt).read()
    m = re.search(r'Run Result\s*:\s*(\S+)', text)
    summary = re.findall(r'\[(?:ERROR|WARN|INFO)\]\s*([^\n]+)', text)
    dev = re.findall(r'^\s*((?:M[NP]|R|D|C)\(\S+\))\s*\|\s*(\d+)\s*:\s*(\d+)', text, re.M)
    return (m.group(1) if m else 'UNKNOWN',
            '%s; devices %s' % ('; '.join(s.strip() for s in summary[:3]), ', '.join('%s %s:%s' % d for d in dev)))
