"""Validate the OSU sky130_osu_sc_18T_hs cells (from sky130_cds, Apache-2.0) with this repository's
Pegasus decks, as a candidate second library.

  python3 sky130.py osu-check --osu DIR      (DIR: .../sky130_osu_sc_t18/18T_hs with gds/ spice/ lef/)

- DRC alone: every cell GDS in a spaced array (sky130cad.cell_array).
- DRC abutted: every cell between two inv_1 at its LEF width, in rows 10 um apart, so implant
  and well continuity across cell edges is checked as in a placed row.
- LVS: OSU ships extracted netlists only (<cell>.spice + .pex.spice + .pxi.spice). The source
  is rebuilt from them: every node of an x_PM_...%NET parasitic instance is the net NET; the
  NWDIODE well diode and the probe elements are dropped; NLOWVT/PSHORT/... map to the sky130
  device names (lvs.LEGACY).
"""
import collections
import glob
import os
import struct

from . import cell_array, drc_tests, lvs, toolenv

PREFIX = 'sky130_osu_sc_18T_hs__'


def lef_sizes(lef):
    sizes, cur = {}, None
    for line in open(lef):
        t = line.split()
        if t[:1] == ['MACRO']:
            cur = t[1]
        elif t[:1] == ['SIZE'] and cur:
            sizes[cur] = (float(t[1]), float(t[3]))
    return sizes


def schematic(spice_dir, cell, dst):
    """Collapse an OSU extracted netlist into a schematic CDL (returns the device count)."""
    main = open(os.path.join(spice_dir, cell + '.spice')).read()
    pxi = os.path.join(spice_dir, cell + '.pxi.spice')
    alias = {}
    if os.path.exists(pxi):
        text = open(pxi).read().replace('\n+', ' ')
        for line in text.split('\n'):
            t = line.split()
            if t and t[0].lower().startswith('x_pm') and '%' in t[0]:
                net = t[0].split('%', 1)[1]
                for node in t[1:-1]:
                    alias[node] = net
    lines, out, n = main.replace('\n+', ' ').split('\n'), ['*.SCALE MICRON'], 0
    for line in lines:
        t = line.split()
        if not t or t[0].startswith('*') or t[0].lower() == '.include':
            continue
        if t[0].lower() in ('.subckt', '.ends'):
            out.append(line.strip())
            continue
        if t[0][0] in 'mM' and len(t) > 5:
            model = lvs.LEGACY.get(t[5].lower(), t[5])
            nodes = [alias.get(x, x) for x in t[1:5]]
            params = [p for p in t[6:] if p.split('=')[0].upper() in ('W', 'L')]
            out.append(' '.join([t[0]] + nodes + [model] + [p.lower() for p in params]))
            n += 1
    open(dst, 'w').write('\n'.join(out) + '\n')
    return n


IMPLANTS = {(93, 44), (94, 20)}
NWELL = (64, 20)
NEAR = 0.38        # n/psdm.1 minimum spacing: an implant edge closer than this to a cell edge leaves a gap
NEAR_NWELL = 1.27  # nwell.2a spacing (horizontal only: the well band is the upper part of the row)
# Implant bands of the OSU 18T template (y, um), added to filler cells that have none, so the
# row's bands run through them: psdm (ptap), nsdm (nfets), psdm (pfets), nsdm (ntap).
FILL_BANDS = [((94, 20), 0.0, 0.43), ((93, 44), 0.45, 1.70), ((94, 20), 2.96, 6.21), ((93, 44), 6.23, 6.66)]


def _boundary(layer, dtype, pts):
    R = cell_array.rec
    return (R(0x08, 0) + R(0x0D, 2, struct.pack('>h', layer)) + R(0x0E, 2, struct.pack('>h', dtype)) +
            R(0x10, 3, b''.join(struct.pack('>ii', x, y) for x, y in pts)) + R(0x11, 0))


def patch_implants(src, dst, width, height, near=NEAR, fill_bands=False):
    """Extend nsdm/psdm rectangles that stop within `near` of a cell edge to that edge (LEF size), and
    nwell rectangles within NEAR_NWELL of a side edge to that edge, so abutted and row-mirrored
    cells leave no gap; with fill_bands, give a cell without implants the FILL_BANDS. Returns
    (shapes changed or added, non-rectangular implants left alone)."""
    data = open(src, 'rb').read()
    out, i, ln, dt, kind, changed, poly = [], 0, None, None, None, 0, 0
    db = 1000.0
    while i + 4 <= len(data):
        n, rt, dtype = struct.unpack('>HBB', data[i:i + 4])
        raw = data[i:i + n]
        body = data[i + 4:i + n]
        i += n
        if n < 4:
            break
        if rt == 0x03:
            db = 1e-6 / cell_array.struct_unpack_real8(body[8:16])     # database units per um
        elif rt in (0x08, 0x0A, 0x0B, 0x0C, 0x09):
            kind = rt
        elif rt == 0x0D:
            ln = struct.unpack('>h', body)[0]
        elif rt == 0x0E:
            dt = struct.unpack('>h', body)[0]
        elif rt == 0x10 and kind == 0x08 and (ln, dt) == NWELL:
            xy = list(struct.unpack('>%di' % (len(body) // 4), body))
            xs, ys = xy[0::2], xy[1::2]
            if len(xs) == 5 and len(set(xs)) == 2 and len(set(ys)) == 2:
                x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
                W, d = round(width * db), round(NEAR_NWELL * db)
                nx0 = 0 if 0 < x0 < d else x0
                nx1 = W if W - d < x1 < W else x1
                if (nx0, nx1) != (x0, x1):
                    changed += 1
                    pts = [(nx0, y0), (nx1, y0), (nx1, y1), (nx0, y1), (nx0, y0)]
                    raw = struct.pack('>HBB', 4 + 40, 0x10, 3) + b''.join(struct.pack('>ii', x, y) for x, y in pts)
        elif rt == 0x10 and kind == 0x08 and (ln, dt) in IMPLANTS:
            xy = list(struct.unpack('>%di' % (len(body) // 4), body))
            xs, ys = xy[0::2], xy[1::2]
            if len(xs) != 5 or len(set(xs)) != 2 or len(set(ys)) != 2:
                poly += 1
            else:
                x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
                W, H, d = round(width * db), round(height * db), round(near * db)
                nx0 = 0 if 0 < x0 < d else x0
                nx1 = W if W - d < x1 < W else x1
                ny0 = 0 if 0 < y0 < d else y0
                ny1 = H if H - d < y1 < H else y1
                if (nx0, nx1, ny0, ny1) != (x0, x1, y0, y1):
                    changed += 1
                    pts = [(nx0, ny0), (nx1, ny0), (nx1, ny1), (nx0, ny1), (nx0, ny0)]
                    raw = struct.pack('>HBB', 4 + 40, 0x10, 3) + b''.join(struct.pack('>ii', x, y) for x, y in pts)
        if rt == 0x07 and fill_bands and not has_implant(out):
            W, H = round(width * db), round(height * db)
            for (layer, dtype), y0, y1 in FILL_BANDS:
                a0, a1 = round(y0 * db), min(round(y1 * db), H)
                out.append(_boundary(layer, dtype, [(0, a0), (W, a0), (W, a1), (0, a1), (0, a0)]))
                changed += 1
        out.append(raw)
    open(dst, 'wb').write(b''.join(out))
    return changed, poly


def has_implant(records):
    data = b''.join(records)
    i, ln = 0, None
    while i + 4 <= len(data):
        n, rt, _ = struct.unpack('>HBB', data[i:i + 4])
        if n < 4:
            break
        if rt == 0x0D:
            ln = struct.unpack('>h', data[i + 4:i + 6])[0]
        elif rt == 0x0E and (ln, struct.unpack('>h', data[i + 4:i + 6])[0]) in IMPLANTS:
            return True
        i += n
    return False


def patch_library(osu_dir, out_dir):
    """Patched copies of every cell GDS in out_dir; returns {cell: (changed, non-rectangles)}."""
    os.makedirs(out_dir, exist_ok=True)
    sizes = {}
    for f in glob.glob(os.path.join(osu_dir, 'lef', '*.lef')):
        sizes.update(lef_sizes(f))
    res = {}
    for f in sorted(glob.glob(os.path.join(osu_dir, 'gds', PREFIX + '*.gds'))):
        c = os.path.splitext(os.path.basename(f))[0]
        dst = os.path.join(out_dir, os.path.basename(f))
        if c in sizes:
            res[c] = patch_implants(f, dst, *sizes[c], fill_bands=c.startswith(PREFIX + 'fill_'))
        else:
            open(dst, 'wb').write(open(f, 'rb').read())
            res[c] = (0, 0)
    return res


def abut_array(gds_files, sizes, out_gds, out_tsv, neighbour='inv_1'):
    """Rows of  neighbour | cell | neighbour  at LEF widths (cells assumed at LEF origin 0 0)."""
    units, structs = None, {}
    for f in gds_files:
        u, ss = cell_array.read_lib(f)
        units = units or u
        for k, v in ss.items():
            structs.setdefault(k, v)
    dbu = 1e-6 / cell_array.struct_unpack_real8(units[12:20])
    nb = PREFIX + neighbour
    placed, y = [], 0.0
    for f in gds_files:
        c = os.path.splitext(os.path.basename(f))[0]
        if c not in sizes or c not in structs or nb not in sizes:
            continue
        x = 0.0
        row = []
        h = sizes[c][1]
        for name in (nb, c, nb):
            row.append((name, x, y, False))
            # the row above is mirrored (MX) and abuts at y + h, as rows flip in a placed block
            row.append((name, x, y + 2 * h, True))
            x += sizes[name][0]
        placed.append((c, row, 0.0, y, x, y + 2 * h))
        y += 2 * h + 10.0
    date = struct.pack('>12h', 2026, 11, 18, 0, 0, 0, 2026, 11, 18, 0, 0, 0)
    R, N = cell_array.rec, cell_array.name_rec
    out = [R(0x00, 2, struct.pack('>h', 600)), R(0x01, 2, date), N(0x02, 'osu_abut'), units]
    out += [s[0] for s in structs.values()]
    out += [R(0x05, 2, date), N(0x06, 'osu_abut')]
    for c, row, *_ in placed:
        for name, x, yy, mx in row:
            sref = [R(0x0A, 0), N(0x12, name)]
            if mx:
                sref.append(R(0x1A, 1, struct.pack('>H', 0x8000)))      # STRANS: reflect about x
            out += sref + [R(0x10, 3, struct.pack('>ii', int(round(x * dbu)), int(round(yy * dbu)))), R(0x11, 0)]
    out += [R(0x07, 0), R(0x04, 0)]
    open(out_gds, 'wb').write(b''.join(out))
    open(out_tsv, 'w').write(''.join('%s\t%.3f\t%.3f\t%.3f\t%.3f\n' % (c, x0, y0, x1, y1) for c, _, x0, y0, x1, y1 in placed))
    return len(placed)


def by_cell(tsv, errors):
    boxes = [l.split('\t') for l in open(tsv).read().split('\n') if l]
    per = collections.defaultdict(collections.Counter)
    for rule, x, y in drc_tests.read_errors(errors):
        for c, x0, y0, x1, y1 in boxes:
            if float(x0) - 0.5 <= x <= float(x1) + 0.5 and float(y0) - 0.5 <= y <= float(y1) + 0.5:
                per[c][rule] += 1
                break
        else:
            per['?'][rule] += 1
    return per


def check(work, osu_dir, deck, lvs_deck, env=None, jobs=4, gds_dir=None, tag='osu_check'):
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    gds = sorted(glob.glob(os.path.join(gds_dir or os.path.join(osu_dir, 'gds'), PREFIX + '*.gds')))
    lef = glob.glob(os.path.join(osu_dir, 'lef', '*.lef'))
    sizes = {}
    for f in lef:
        sizes.update(lef_sizes(f))
    res = {}
    for kind in ('alone', 'abut'):
        k = os.path.join(d, kind)
        os.makedirs(k, exist_ok=True)
        g, t = os.path.join(k, kind + '.gds'), os.path.join(k, kind + '.tsv')
        if kind == 'alone':
            cell_array.build(g, t, gds)
            top = 'cell_array'
        else:
            abut_array(gds, sizes, g, t)
            top = 'osu_abut'
        toolenv.run(['pegasus', '-drc', '-dp', str(jobs), '-gds', g, '-top_cell', top, deck], k, os.path.join(k, 'peg.out'),
                    env, 1800)
        rpt = os.path.join(k, 'sky130_full.drc_errors.ascii')
        res[kind] = by_cell(t, rpt) if os.path.exists(rpt) else None
    lv = {}
    from concurrent.futures import ThreadPoolExecutor

    def one(f):
        c = os.path.splitext(os.path.basename(f))[0]
        if not os.path.exists(os.path.join(osu_dir, 'spice', c + '.spice')):
            return c, 'NO NETLIST', ''
        out = os.path.join(d, 'lvs', c)
        os.makedirs(out, exist_ok=True)
        n = schematic(os.path.join(osu_dir, 'spice'), c, os.path.join(out, 'src.cdl'))
        if n == 0:
            return c, 'NO DEVICES', ''
        r, s = lvs.run(f, c, os.path.join(out, 'src.cdl'), out, lvs_deck, env)
        return c, r, s
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        for c, r, s in ex.map(one, gds):
            lv[c] = (r, s)
    return res, lv, sizes
