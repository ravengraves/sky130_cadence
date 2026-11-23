#!/usr/bin/env python3
"""Run DRC on many standard cells at once: merge cell GDS files into one spaced array.

  used by `sky130.py drc-validate` (all fd_sc cells in one array)

`build` copies every structure (first copy of a name wins; differing duplicates are
reported) and places each file's top cell in rows with 6 um gaps, so cells do not
interact. `report` assigns each Pegasus error to the cell whose placement contains it
and prints per-cell and per-rule counts. Standard library only.
"""
import os
import struct
import sys

from .drc_tests import read_errors

GAP = 6.0
ROW_WIDTH = 400.0
SHAPE_ELEMENTS = (0x08, 0x09, 0x2D)  # BOUNDARY, PATH, BOX


def records(data):
    i = 0
    while i + 4 <= len(data):
        n, rt, dt = struct.unpack('>HBB', data[i:i + 4])
        if n < 4:
            break
        yield rt, data[i + 4:i + n], data[i:i + n]
        i += n


def rec(rt, dt, payload=b''):
    return struct.pack('>HBB', 4 + len(payload), rt, dt) + payload


def name_rec(rt, s):
    b = s.encode()
    if len(b) % 2:
        b += b'\0'
    return rec(rt, 6, b)


def read_lib(path):
    """Return (units_raw, {name: (raw_bytes, bbox_dbu, refs)})."""
    units = None
    structs = {}
    cur = None
    elem = None
    for rt, payload, raw in records(open(path, 'rb').read()):
        if rt == 0x03:
            units = raw
        elif rt == 0x05:
            cur = {'raw': [raw], 'bbox': None, 'refs': set(), 'name': None}
        elif cur is not None:
            cur['raw'].append(raw)
            if rt == 0x06 and cur['name'] is None:
                cur['name'] = payload.rstrip(b'\0').decode()
            elif rt in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x15, 0x2D):
                elem = rt
            elif rt == 0x12:
                cur['refs'].add(payload.rstrip(b'\0').decode())
            elif rt == 0x10 and elem in SHAPE_ELEMENTS:
                pts = struct.unpack('>%di' % (len(payload) // 4), payload)
                xs, ys = pts[0::2], pts[1::2]
                b = (min(xs), min(ys), max(xs), max(ys))
                o = cur['bbox']
                cur['bbox'] = b if o is None else (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
            elif rt == 0x07:
                structs[cur['name']] = (b''.join(cur['raw']), cur['bbox'], cur['refs'])
                cur = None
    return units, structs


def build(out_gds, out_tsv, files):
    units = None
    structs = {}
    tops = []
    for f in files:
        u, ss = read_lib(f)
        if units is None:
            units = u
        elif u != units:
            sys.exit('different UNITS in %s' % f)
        stem = os.path.splitext(os.path.basename(f))[0]
        referenced = set().union(*(s[2] for s in ss.values())) if ss else set()
        top = stem if stem in ss else next(n for n in ss if n not in referenced)
        for n, s in ss.items():
            if n in structs and structs[n][0] != s[0]:
                print('warning: differing duplicate structure %s in %s (kept first)' % (n, f))
            structs.setdefault(n, s)
        tops.append(top)
    dbu = 1e-6 / struct_unpack_real8(units[12:20])  # database units per um
    x = y = row_h = 0.0
    placed = []
    for t in tops:
        bb = structs[t][1]
        if bb is None:
            print('warning: %s has no shapes of its own; skipped' % t)
            continue
        w, h = (bb[2] - bb[0]) / dbu, (bb[3] - bb[1]) / dbu
        if x > 0 and x + w > ROW_WIDTH:
            x, y, row_h = 0.0, y + row_h + GAP, 0.0
        ox, oy = int(round(x * dbu)) - bb[0], int(round(y * dbu)) - bb[1]
        placed.append((t, ox, oy, x, y, x + w, y + h))
        x += w + GAP
        row_h = max(row_h, h)
    date = struct.pack('>12h', 2026, 11, 17, 0, 0, 0, 2026, 11, 17, 0, 0, 0)
    out = [rec(0x00, 2, struct.pack('>h', 600)), rec(0x01, 2, date), name_rec(0x02, 'cell_array'), units]
    out += [s[0] for s in structs.values()]
    out += [rec(0x05, 2, date), name_rec(0x06, 'cell_array')]
    for t, ox, oy, *_ in placed:
        out += [rec(0x0A, 0), name_rec(0x12, t), rec(0x10, 3, struct.pack('>ii', ox, oy)), rec(0x11, 0)]
    out += [rec(0x07, 0), rec(0x04, 0)]
    open(out_gds, 'wb').write(b''.join(out))
    open(out_tsv, 'w').write(''.join('%s\t%.3f\t%.3f\t%.3f\t%.3f\n' % (t, x0, y0, x1, y1)
                                     for t, _, _, x0, y0, x1, y1 in placed))
    print('wrote %s: %d cells, %d structures' % (out_gds, len(placed), len(structs)))


def struct_unpack_real8(b):
    e = (b[0] & 0x7F) - 64
    m = int.from_bytes(b[1:8], 'big') / 2 ** 56
    return (-1 if b[0] & 0x80 else 1) * m * 16 ** e


def report(tsv, errors_path):
    cells = [l.split('\t') for l in open(tsv).read().split('\n') if l]
    cells = [(c[0], *map(float, c[1:])) for c in cells]
    per_cell, per_rule, unassigned = {}, {}, 0
    for rule, x, y in read_errors(errors_path):
        best = None
        for name, x0, y0, x1, y1 in cells:
            d = max(x0 - x, 0, x - x1) + max(y0 - y, 0, y - y1)
            if d <= GAP / 2 and (best is None or d < best[0]):
                best = (d, name)
        if best is None:
            unassigned += 1
            continue
        per_cell.setdefault(best[1], {}).setdefault(rule, 0)
        per_cell[best[1]][rule] += 1
        per_rule[rule] = per_rule.get(rule, 0) + 1
    print('%d cells, %d with errors, %d unassigned errors' % (len(cells), len(per_cell), unassigned))
    for rule in sorted(per_rule, key=lambda r: -per_rule[r]):
        users = sorted(c for c in per_cell if rule in per_cell[c])
        print('%-14s %5d errors in %3d cells: %s' % (rule, per_rule[rule], len(users),
                                                     ' '.join(u.split('__')[-1] for u in users[:12])
                                                     + (' ...' if len(users) > 12 else '')))


if __name__ == '__main__':
    if sys.argv[1] == 'build':
        build(sys.argv[2], sys.argv[3], sys.argv[4:])
    else:
        report(sys.argv[2], sys.argv[3])
