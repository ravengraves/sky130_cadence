"""Transistor layout generator for the sky130 1.8 V devices (GDS, CDL, Spectre), standard
library only.

  python3 sky130.py mos --device nfet_01v8 --w 1.0 --l 0.15 --nf 2 [--tie] [--no-tap] --out DIR
  python3 sky130.py mos-check                # generate a matrix, DRC (+ LVS if a deck is present)

Devices: nfet_01v8, nfet_01v8_lvt, pfet_01v8, pfet_01v8_hvt (SkyWater sky130_fd_pr models;
1.8 V nominal, the same devices the standard cells use). W is per finger, in um.

Layout (all coordinates on the 5 nm grid; values are SkyWater periphery rules):
- diff with nf vertical poly gates; source/drain columns alternate S, D, S, ...
  Inner S/D length 0.29 (licon 0.17 + 0.06 to each gate, licon.11 0.055), outer 0.30
  (>= poly.7 0.25; licon.5c 0.06 on the outer edge). Poly endcap 0.13 (poly.8).
- every S/D column: licons at 0.34 pitch (licon.1/.2), >= 0.04 inside diff (licon.5a), and a
  0.17 li1 strip extending 0.085 beyond the end licons (li.5, li.6 area).
- gates: joined by a poly strap 0.16 above diff (poly.4) with one licon per gate (licon.8/.8a,
  licon.14 0.19 to diff, licon.9 0.11 to psdm), npc 0.1 around (licon.15/.18), li1 bar: pin G.
- sources: with more than one source column, an li1 bar below diff joins them (pin S).
  drains: with more than one drain column, mcon + a met1 bar join them (pin D on met1).
- body tap (default on): a tap row below with licons and li1 (licon.16, nwell.4): pin B.
  --tie joins the source columns to the tap li1 (B = S).
- implants: nsdm/psdm 0.125 around diff and tap (n/psd.5a/b), 0.13+ apart (n/psd.7);
  pfet: nwell 0.18 around diff and tap (difftap.8/.10); lvt: lvtn, hvt: hvtp 0.18 around diff.
- labels: text on li1/met1 label purpose (67/5, 68/5) plus pin shapes (67/16, 68/16).

`model_bins` reads the W/L bins of the sky130_fd_pr model files; a size outside every bin
would not simulate (Spectre: "no matching model"), so `mos` checks it when the models exist.
"""
import math
import os
import re
import struct

from . import drc_tests

DEVICES = {  # device: (diff implant, tap implant, in nwell, Vt implant)
    'nfet_01v8': ('nsdm', 'psdm', False, None),
    'nfet_01v8_lvt': ('nsdm', 'psdm', False, 'lvtn'),
    'pfet_01v8': ('psdm', 'nsdm', True, None),
    'pfet_01v8_hvt': ('psdm', 'nsdm', True, 'hvtp'),
}
LAYERS = dict(drc_tests.LAYERS)
LAYERS.update({'li1_label': (67, 5), 'li1_pin': (67, 16), 'met1_label': (68, 5), 'met1_pin': (68, 16)})

# nm
LICON, LICON_SP, DIFF_ENC, LI_EXT = 170, 170, 40, 85
SD_IN, SD_END, ENDCAP = 290, 300, 130
STRAP_GAP, STRAP_H, POLY_ENC = 160, 330, 80
NPC_ENC, IMP_ENC, WELL_ENC, VT_ENC = 100, 125, 180, 180
TAP_H, TAP_ENC_X = 290, 120
MCON, M1_ENC, M1_ENC_ADJ = 170, 30, 60


def snap(v):
    """Nearest 5 nm, halves rounded up (the SKILL PCell rounds the same way)."""
    return int(math.floor(v / 5.0 + 0.5)) * 5


def nm(um):
    v = int(round(um * 1000))
    if v % 5:
        raise ValueError('%g um is off the 5 nm grid' % um)
    return v


def column(n_len, enc):
    """Number of 0.17 cuts at 0.34 pitch that fit in n_len with enc on both ends, and the start."""
    n = max(1, (n_len - 2 * enc + LICON_SP) // (LICON + LICON_SP))
    span = n * LICON + (n - 1) * LICON_SP
    return n, snap((n_len - span) / 2.0)


def generate(device, w, l, nf=1, tap=True, tie=False, name=None):
    """Returns (cell name, shapes [(layer, x0, y0, x1, y1) nm], labels [(layer, x, y, text)], pins)."""
    if device not in DEVICES:
        raise ValueError('device must be one of %s' % ', '.join(DEVICES))
    W, L = nm(w), nm(l)
    if L < 150:
        raise ValueError('L >= 0.15 um (poly.1a)')
    if W < 360:
        raise ValueError('W >= 0.36 um (narrowest model bin)')
    if nf < 1:
        raise ValueError('nf >= 1')
    if tie and not tap:
        raise ValueError('--tie needs the body tap')
    imp_d, imp_t, nwell, vt = DEVICES[device]
    name = name or '%s_w%s_l%s_nf%d%s' % (device, ('%g' % w).replace('.', 'p'), ('%g' % l).replace('.', 'p'), nf,
                                         '_tie' if tie else ('' if tap else '_notap'))
    S, Lb = [], []

    def rect(layer, x0, y0, x1, y1):
        S.append((layer, x0, y0, x1, y1))

    # columns and gates (x)
    cols, gates, x = [], [], 0
    for i in range(nf + 1):
        width = SD_END if i in (0, nf) else SD_IN
        cols.append((x, x + width))
        x += width
        if i < nf:
            gates.append((x, x + L))
            x += L
    xlen = x
    rect('diff', 0, 0, xlen, W)
    n, y0 = column(W, DIFF_ENC)
    lic_y = [y0 + k * (LICON + LICON_SP) for k in range(n)]
    li_lo, li_hi = lic_y[0] - LI_EXT, lic_y[-1] + LICON + LI_EXT
    src = [i for i in range(nf + 1) if i % 2 == 0]
    drn = [i for i in range(nf + 1) if i % 2 == 1]
    cx = {}
    for i, (a, b) in enumerate(cols):
        if i == 0:
            lx = b - snap((SD_IN - LICON) / 2.0) - LICON     # 0.06 to the gate, 0.07 to the outer edge
        elif i == nf:
            lx = a + snap((SD_IN - LICON) / 2.0)
        else:
            lx = a + snap((b - a - LICON) / 2.0)
        cx[i] = lx
        for y in lic_y:
            rect('licon', lx, y, lx + LICON, y + LICON)

    # gate poly, strap, contacts
    strap_lo = W + STRAP_GAP
    strap_hi = strap_lo + STRAP_H
    for a, b in gates:
        rect('poly', a, -ENDCAP, b, strap_lo)
    gc = [snap((a + b) / 2.0 - LICON / 2.0) for a, b in gates]
    rect('poly', min(gc[0] - POLY_ENC, gates[0][0]), strap_lo, max(gc[-1] + LICON + POLY_ENC, gates[-1][1]), strap_hi)
    gy = strap_lo + POLY_ENC
    for g in gc:
        rect('licon', g, gy, g + LICON, gy + LICON)
    rect('npc', gc[0] - NPC_ENC, gy - NPC_ENC, gc[-1] + LICON + NPC_ENC, gy + LICON + NPC_ENC)
    rect('li1', gc[0] - LI_EXT, gy, gc[-1] + LICON + LI_EXT, gy + LICON)
    pins = {'G': ('li1', (gc[0] + gc[-1] + LICON) // 2, gy + LICON // 2)}

    # tap row (below) and source bar
    bar = len(src) > 1 and not tie
    tap_top = -(600 if bar else 400)
    tap_bot = tap_top - TAP_H
    bot = {i: li_lo for i in range(nf + 1)}
    if bar:
        bar_hi, bar_lo = li_lo - 185, li_lo - 185 - 170
        rect('li1', cx[src[0]], bar_lo, cx[src[-1]] + LICON, bar_hi)
        for i in src:
            bot[i] = bar_lo
    if tap:
        tx0, tx1 = 0, max(xlen, LICON + 2 * TAP_ENC_X)
        rect('tap', tx0, tap_bot, tx1, tap_top)
        nt, ts = column(tx1 - tx0, TAP_ENC_X)
        ty = tap_bot + snap((TAP_H - LICON) / 2.0)
        txs = [tx0 + ts + k * (LICON + LICON_SP) for k in range(nt)]
        for tx in txs:
            rect('licon', tx, ty, tx + LICON, ty + LICON)
        tli_lo, tli_hi = ty, ty + LICON
        rect('li1', min(txs[0] - LI_EXT, cx[0]), tli_lo, max(txs[-1] + LICON + LI_EXT, cx[nf] + LICON), tli_hi)
        pins['B'] = ('li1', (txs[0] + txs[-1] + LICON) // 2, ty + LICON // 2)
        rect(imp_t, tx0 - IMP_ENC, tap_bot - IMP_ENC, tx1 + IMP_ENC, tap_top + IMP_ENC)
        if tie:
            for i in src:
                bot[i] = tli_lo
    for i in range(nf + 1):
        rect('li1', cx[i], bot[i], cx[i] + LICON, li_hi)
    mid = snap((li_lo + li_hi) / 2.0 - LICON / 2.0)
    pins['S'] = ('li1', cx[src[0]] + LICON // 2, mid + LICON // 2)
    if len(drn) > 1:
        for i in drn:
            rect('mcon', cx[i], mid, cx[i] + MCON, mid + MCON)
        rect('met1', cx[drn[0]] - M1_ENC_ADJ, mid - M1_ENC, cx[drn[-1]] + MCON + M1_ENC_ADJ, mid + MCON + M1_ENC)
        pins['D'] = ('met1', (cx[drn[0]] + cx[drn[-1]] + MCON) // 2, mid + MCON // 2)
    else:
        pins['D'] = ('li1', cx[drn[0]] + LICON // 2, mid + LICON // 2)
    if tie:
        del pins['B']

    # implants, well, Vt
    rect(imp_d, -IMP_ENC, -IMP_ENC, xlen + IMP_ENC, W + IMP_ENC)
    if nwell:
        top = W + WELL_ENC
        rect('nwell', -WELL_ENC, (tap_bot if tap else 0) - WELL_ENC, max(xlen, tx1 if tap else 0) + WELL_ENC, top)
    if vt:
        rect(vt, -VT_ENC, -VT_ENC, xlen + VT_ENC, W + VT_ENC)
    for pin, (layer, x, y) in pins.items():
        Lb.append((layer + '_label', x, y, pin))
        rect(layer + '_pin', x - 5, y - 5, x + 5, y + 5)
    return name, S, Lb, {'w': w, 'l': l, 'nf': nf, 'device': device, 'tie': tie, 'tap': tap}


# ---------------------------------------------------------------- output

def write_gds(path, cells):
    """cells: [(name, shapes, labels, ...)]: one structure each, coordinates in nm (1 nm db unit)."""
    R, Sx, f8 = drc_tests._rec, drc_tests._str, drc_tests._real8
    date = struct.pack('>12h', 2026, 11, 18, 0, 0, 0, 2026, 11, 18, 0, 0, 0)
    out = [R(0x00, 2, struct.pack('>h', 600)), R(0x01, 2, date), Sx(0x02, 'mosgen'), R(0x03, 5, f8(1e-3) + f8(1e-9))]
    for c in cells:
        name, shapes, labels = c[0], c[1], c[2]
        out += [R(0x05, 2, date), Sx(0x06, name)]
        for layer, x0, y0, x1, y1 in shapes:
            ln, dt = LAYERS[layer]
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            out += [R(0x08, 0), R(0x0D, 2, struct.pack('>h', ln)), R(0x0E, 2, struct.pack('>h', dt)),
                    R(0x10, 3, b''.join(struct.pack('>ii', x, y) for x, y in pts)), R(0x11, 0)]
        for layer, x, y, text in labels:
            ln, tt = LAYERS[layer]
            out += [R(0x0C, 0), R(0x0D, 2, struct.pack('>h', ln)), R(0x16, 2, struct.pack('>h', tt)),
                    R(0x10, 3, struct.pack('>ii', x, y)), Sx(0x19, text), R(0x11, 0)]
        out.append(R(0x07, 0))
    out.append(R(0x04, 0))
    open(path, 'wb').write(b''.join(out))


def netlists(name, p):
    """(CDL for LVS, Spectre-loadable SPICE subcircuit): one device per finger, in parallel."""
    bulk = 'S' if p['tie'] else 'B'
    ports = 'D G S' + ('' if p['tie'] else ' B')
    cdl = ['.SUBCKT %s %s' % (name, ports)]
    sp = ['.subckt %s %s' % (name, ports)]
    for i in range(p['nf']):
        cdl.append('M%d D G S %s %s w=%g l=%g' % (i, bulk, p['device'], p['w'], p['l']))
    # Spectre: sizes in um (the model files set .option scale=1.0u)
    for i in range(p['nf']):
        sp.append('X%d D G S %s sky130_fd_pr__%s w=%g l=%g' % (i, bulk, p['device'], p['w'], p['l']))
    return '\n'.join(cdl + ['.ENDS']) + '\n', '\n'.join(sp + ['.ends']) + '\n'


# ---------------------------------------------------------------- model bins

def model_bins(models_root, device):
    """[(lmin, lmax, wmin, wmax)] in um from sky130_fd_pr cells/<device>/*tt*.pm3.spice."""
    import glob
    files = glob.glob(os.path.join(models_root, 'cells', device, 'sky130_fd_pr__%s__tt.pm3.spice' % device))
    files = files or glob.glob(os.path.join(models_root, 'cells', device, '*tt*.pm3.spice'))
    if not files:
        return None
    text = open(files[0]).read()
    bins = []
    for block in re.split(r'(?im)^\s*\.model\s', text)[1:]:
        v = {}
        for k in ('lmin', 'lmax', 'wmin', 'wmax'):
            m = re.search(r'\b%s\s*=\s*([-+0-9.eE]+)' % k, block, re.I)
            if m:
                v[k] = float(m.group(1)) * 1e6
        if len(v) == 4:
            bins.append((v['lmin'], v['lmax'], v['wmin'], v['wmax']))
    return bins


def in_bin(bins, w, l, eps=1e-6):
    return any(lmin - eps <= l < lmax - eps and wmin - eps <= w < wmax - eps for lmin, lmax, wmin, wmax in bins)


def main(device, w, l, nf, tap, tie, out, models_root=None):
    os.makedirs(out, exist_ok=True)
    name, S, Lb, p = generate(device, w, l, nf, tap, tie)
    if models_root:
        bins = model_bins(models_root, device)
        if bins is not None and not in_bin(bins, w, l):
            ws = sorted({round(b[2], 3) for b in bins if b[0] - 1e-6 <= l < b[1] - 1e-6})
            raise SystemExit('%s W=%g L=%g is outside every model bin; widths at this L start at: %s'
                             % (device, w, l, ', '.join('%g' % x for x in ws) or 'none (L not binned)'))
    write_gds(os.path.join(out, name + '.gds'), [(name, S, Lb)])
    cdl, sp = netlists(name, p)
    open(os.path.join(out, name + '.cdl'), 'w').write(cdl)
    open(os.path.join(out, name + '.spice'), 'w').write(sp)
    return name


# ---------------------------------------------------------------- check

CHECK = [  # device, w, l, nf, tap, tie
    ('nfet_01v8', 0.42, 0.15, 1, True, False), ('nfet_01v8', 1.0, 0.15, 2, True, False),
    ('nfet_01v8', 0.65, 0.15, 4, True, True), ('nfet_01v8', 1.0, 0.5, 3, True, False),
    ('nfet_01v8_lvt', 0.65, 0.15, 1, True, False), ('nfet_01v8_lvt', 1.0, 0.15, 3, True, True),
    ('pfet_01v8', 0.55, 0.15, 1, True, False), ('pfet_01v8', 1.0, 0.15, 2, True, True),
    ('pfet_01v8', 1.65, 0.15, 5, True, False), ('pfet_01v8_hvt', 0.42, 0.15, 1, True, False),
    ('pfet_01v8_hvt', 1.0, 0.15, 4, True, True), ('nfet_01v8', 0.42, 0.15, 1, False, False),
]

SPECTRE_OP = """simulator lang=spice
.include "%(models)s"
.include "%(sub)s"
vd d 0 %(v)g
vg g 0 %(v)g
xdut d g 0 %(b)s%(name)s
.op
.end
"""


def check(work, env=None, jobs=4, cornell=True):
    """Generate CHECK; DRC each cell with the release deck; LVS and Cornell DRC when those decks
    are downloaded (private comparison only); Spectre operating point at 1.8 V, TT.
    Returns rows (name, bin ok, drc results, cornell drc {rule: n}, lvs, Id uA)."""
    import collections
    from . import drc_deck, lvs, toolenv
    d = os.path.join(work, 'mos')
    os.makedirs(d, exist_ok=True)
    deck = os.path.join(work, 'drc', 'sky130_full.pvl')
    if not os.path.exists(deck):
        drc_deck.write(deck)
    lvs_deck = lvs.deck_path(work)
    cornell_root = os.path.join(work, 'upstream', 'cornell_sky130_pdk', 'Sky130_DRC')
    fdpr = os.path.join(work, 'upstream', 'sky130_fd_pr')
    models = os.path.join(work, 'spectre', 'models', 'sky130_digital_tt.spice')
    rows = []
    for dev, w, l, nf, tap, tie in CHECK:
        name, S, Lb, p = generate(dev, w, l, nf, tap, tie)
        c = os.path.join(d, name)
        os.makedirs(c, exist_ok=True)
        gds = os.path.join(c, name + '.gds')
        write_gds(gds, [(name, S, Lb)])
        cdl, sp = netlists(name, p)
        open(os.path.join(c, name + '.cdl'), 'w').write(cdl)
        open(os.path.join(c, name + '.spice'), 'w').write(sp)
        bins = model_bins(fdpr, dev)
        binok = None if bins is None else in_bin(bins, w, l)
        dd = os.path.join(c, 'drc')
        os.makedirs(dd, exist_ok=True)
        toolenv.run(['pegasus', '-drc', '-dp', str(jobs), '-gds', gds, '-top_cell', name, deck], dd,
                    os.path.join(dd, 'peg.out'), env, 900)
        rpt = os.path.join(dd, 'sky130_full.drc_errors.ascii')
        drc = collections.Counter(e[0] for e in drc_tests.read_errors(rpt)) if os.path.exists(rpt) else None
        cdrc = None
        if cornell and os.path.exists(cornell_root):
            cd = os.path.join(c, 'drc_cornell')
            os.makedirs(cd, exist_ok=True)
            toolenv.run(['pegasus', '-drc', '-dp', str(jobs), '-gds', gds, '-top_cell', name,
                         os.path.join(cornell_root, 'sky130_rev_0.0_1.0.drc.pvl')], cd, os.path.join(cd, 'peg.out'),
                        toolenv.env_snippet(env) + '\nexport PEGASUS_DRC=%s' % cornell_root, 900)
            import glob
            hits = glob.glob(os.path.join(cd, '*.drc_errors.ascii'))
            cdrc = collections.Counter(e[0] for e in drc_tests.read_errors(hits[0])) if hits else 'failed'
        res = None
        if os.path.exists(lvs_deck) and tap:
            res, _ = lvs.run(gds, name, os.path.join(c, name + '.cdl'), os.path.join(c, 'lvs'), lvs_deck, env)
        idd = None
        if os.path.exists(models):
            v = -1.8 if dev.startswith('p') else 1.8
            open(os.path.join(c, 'op.scs'), 'w').write(SPECTRE_OP % {
                'models': models, 'sub': os.path.join(c, name + '.spice'), 'v': v, 'name': name,
                'b': '' if tie else '0 '})
            toolenv.run(['spectre', '-64', 'op.scs', '=log', 'op.log'], c, os.path.join(c, 'spectre.out'), env, 300)
            log = open(os.path.join(c, 'op.log')).read() if os.path.exists(os.path.join(c, 'op.log')) else ''
            m = re.search(r'I\(vd:p\)\s*=\s*(-?[0-9.]+)\s*([munp]?)A', log)
            if m:
                idd = abs(float(m.group(1))) * {'m': 1e3, 'u': 1, 'n': 1e-3, 'p': 1e-6, '': 1e6}[m.group(2)]
        rows.append((name, binok, drc, cdrc, res, idd))
    return rows
