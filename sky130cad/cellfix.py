"""Layout fixes to SkyWater cells that block routing (applied by `convert`; see `pin-access`).

sky130_fd_sc_hs__xor3_1: an internal met1 strap (y 1.595-1.735 um, x 2.975-5.665) runs over input
pin B (li1, x 4.92-5.25, y 1.35-1.78). No mcon + met1 landing pad fits on B with 0.14 um met1
spacing to the strap (0 access points), so NanoRoute shorted to the strap on about half the
instances of a routed design. The fix re-routes only the strap's middle: from the left pad along
the original bar to x 4.75, up a 0.14 um riser to y 1.95-2.09, across to x 5.665 and down a
riser into the unchanged right pad. Same mcons, same net, every met1 spacing >= 0.145 um; pin B
then has 306 access points (`pin-access`), like other cells' pins. Device layers are untouched, so LVS and the Liberty timing
(transistor-level) are unchanged; the strap is 0.6 um longer.
"""
import struct

MET1 = (68, 20)

# cell: (bbox of the met1 polygon to replace (um), replacement rectangles (um),
#        LEF OBS met1 rectangles to remove, LEF OBS met1 rectangles to add)
FIXES = {
    'sky130_fd_sc_hs__xor3_1': (
        (2.975, 1.55, 5.665, 1.78),
        [(2.975, 1.55, 3.265, 1.78), (3.265, 1.595, 4.75, 1.735), (4.61, 1.595, 4.75, 2.09),
         (4.61, 1.95, 5.665, 2.09), (5.525, 1.78, 5.665, 2.09), (5.375, 1.55, 5.665, 1.78)],
        [(2.975, 1.55, 3.265, 1.595), (2.975, 1.595, 5.665, 1.735), (2.975, 1.735, 3.265, 1.78),
         (5.375, 1.55, 5.665, 1.595), (5.375, 1.735, 5.665, 1.78)],
        None,     # the LEF gets the replacement rectangles
    ),
}


def _rec(rt, dt, payload=b''):
    return struct.pack('>HBB', 4 + len(payload), rt, dt) + payload


def _boundary(layer, dtype, r, db):
    x0, y0, x1, y1 = (int(round(v * db)) for v in r)
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return (_rec(0x08, 0) + _rec(0x0D, 2, struct.pack('>h', layer)) + _rec(0x0E, 2, struct.pack('>h', dtype)) +
            _rec(0x10, 3, b''.join(struct.pack('>ii', x, y) for x, y in pts)) + _rec(0x11, 0))


def fix_gds(src, dst, cell):
    """Write src with the cell's met1 polygon replaced; returns the number of polygons replaced."""
    from .cell_array import struct_unpack_real8
    bbox, rects = FIXES[cell][0], FIXES[cell][1]
    data = open(src, 'rb').read()
    out, elem, i, db, replaced = [], [], 0, 1000.0, 0
    ln = dt = None
    in_boundary = False
    while i + 4 <= len(data):
        n, rt, _ = struct.unpack('>HBB', data[i:i + 4])
        raw, body = data[i:i + n], data[i + 4:i + n]
        i += n
        if n < 4:
            break
        if rt == 0x03:
            db = 1e-6 / struct_unpack_real8(body[8:16])
        if rt == 0x08:
            in_boundary, elem, ln, dt = True, [raw], None, None
            continue
        if in_boundary:
            elem.append(raw)
            if rt == 0x0D:
                ln = struct.unpack('>h', body)[0]
            elif rt == 0x0E:
                dt = struct.unpack('>h', body)[0]
            elif rt == 0x10:
                xy = struct.unpack('>%di' % (len(body) // 4), body)
                bb = (min(xy[0::2]) / db, min(xy[1::2]) / db, max(xy[0::2]) / db, max(xy[1::2]) / db)
            elif rt == 0x11:
                in_boundary = False
                if (ln, dt) == MET1 and all(abs(a - b) < 1e-4 for a, b in zip(bb, bbox)):
                    replaced += 1
                    out += [_boundary(MET1[0], MET1[1], r, db) for r in rects]
                else:
                    out += elem
            continue
        out.append(raw)
    if replaced != 1:
        raise SystemExit('%s: expected one met1 polygon at %s, found %d' % (cell, bbox, replaced))
    open(dst, 'wb').write(b''.join(out))
    return replaced


def fix_lef(lef_text):
    """Apply the OBS met1 changes of FIXES to a cell LEF text; returns (text, cells changed)."""
    import re
    changed = []
    for cell, (_, rects, remove, add) in FIXES.items():
        m = re.search(r'^MACRO %s\n.*?^END %s' % (cell, cell), lef_text, re.S | re.M)
        if not m:
            continue
        body = m.group(0)
        obs = re.search(r'^(\s*)OBS\s*\n(.*?)^\s*END\s*$', body, re.S | re.M)
        lines = obs.group(2).split('\n')
        out, layer = [], None
        fmt = lambda r: '      RECT %8.6f %8.6f %8.6f %8.6f ;' % r
        for line in lines:
            t = line.split()
            if t[:1] == ['LAYER']:
                if layer == 'met1':
                    out += [fmt(r) for r in (add or rects)]
                layer = t[1]
                out.append(line)
                continue
            if layer == 'met1' and t[:1] == ['RECT']:
                r = tuple(float(x) for x in t[1:5])
                if any(all(abs(a - b) < 1e-4 for a, b in zip(r, q)) for q in remove):
                    continue
            out.append(line)
        if layer == 'met1':
            # the met1 section ended the OBS block
            while out and not out[-1].strip():
                out.pop()
            out += [fmt(r) for r in (add or rects)] + ['']
        new_body = body[:obs.start(2)] + '\n'.join(out) + body[obs.end(2):]
        lef_text = lef_text.replace(body, new_body)
        changed.append(cell)
    return lef_text, changed
