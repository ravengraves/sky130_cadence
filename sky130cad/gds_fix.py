#!/usr/bin/env python3
"""Replace cell structures in a layout GDS with the same-named structures from cell GDS files.

  python3 sky130.py fix-gds IN.gds OUT.gds CELL.gds [CELL.gds ...]

Used to repair layouts streamed with a stale LEF FOREIGN name (tech.py: FOREIGN fix):
the layout's `sky130_fd_sc_hs__diode_2` was a wrapper referencing the nonexistent
`scs8hs_diode_2`. Every structure of each CELL.gds replaces (or is added to) the layout;
everything else is copied unchanged. Reports structures still referenced but undefined.
"""
import struct
import sys


def records(data):
    i = 0
    while i + 4 <= len(data):
        n, rt, dt = struct.unpack('>HBB', data[i:i + 4])
        if n < 4:
            break
        yield rt, data[i + 4:i + n], data[i:i + n]
        i += n


def split(path):
    head, structs, order, tail, cur, name = [], {}, [], [], None, None
    for rt, p, raw in records(open(path, 'rb').read()):
        if rt == 0x05:
            cur, name = [raw], None
        elif cur is not None:
            cur.append(raw)
            if rt == 0x06 and name is None:
                name = p.rstrip(b'\0').decode()
            if rt == 0x07:
                structs[name] = b''.join(cur)
                order.append(name)
                cur = None
        elif not order:
            head.append(raw)
        else:
            tail.append(raw)
    return head, structs, order, tail


def refs(blob):
    return {p.rstrip(b'\0').decode() for rt, p, _ in records(blob) if rt == 0x12}


def main(src, dst, cells):
    head, structs, order, tail = split(src)
    for c in cells:
        _, cs, corder, _ = split(c)
        for n in corder:
            print('%s %s from %s' % ('replaced' if n in structs else 'added', n, c))
            if n not in structs:
                order.append(n)
            structs[n] = cs[n]
    missing = sorted(set().union(*(refs(b) for b in structs.values())) - set(structs))
    open(dst, 'wb').write(b''.join(head) + b''.join(structs[n] for n in order) + b''.join(tail))
    print('wrote %s; undefined references: %s' % (dst, missing or 'none'))
    return 1 if missing else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
