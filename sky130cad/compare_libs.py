#!/usr/bin/env python3
"""Compare cell arc delays between Liberty files at one input slew and load.

Usage: python3 -I compare_libs.py SLEW_NS LOAD_PF LIB:CELL:FROM:TO [...]
Prints worst of cell_rise/cell_fall (bilinear interpolation) and the input pin
capacitance of FROM. For flops, use FROM=CK/CLK and TO=Q.
"""
import re
import sys

_cache = {}


def cell_text(lib, cell):
    if lib not in _cache:
        _cache[lib] = open(lib).read()
    t = _cache[lib]
    m = re.search(r'cell\s*\(\s*"?%s"?\s*\)\s*\{' % re.escape(cell), t)
    if not m:
        raise KeyError(cell)
    depth, i = 1, m.end()
    while depth:
        depth += {'{': 1, '}': -1}.get(t[i], 0)
        i += 1
    return t[m.end():i]


def group(text, kind, name):
    m = re.search(r'\b%s\s*\(\s*"?%s"?\s*\)\s*\{' % (kind, re.escape(name)), text)
    depth, i = 1, m.end()
    while depth:
        depth += {'{': 1, '}': -1}.get(text[i], 0)
        i += 1
    return text[m.end():i]


def interp(axis, x):
    if x <= axis[0]:
        return 0, 0.0
    for k in range(len(axis) - 1):
        if axis[k] <= x <= axis[k + 1]:
            return k, (x - axis[k]) / (axis[k + 1] - axis[k])
    return len(axis) - 2, 1.0


def table(body, kind):
    m = re.search(kind + r'\s*\([^)]*\)\s*\{\s*index_1\s*\("([^"]+)"\);\s*index_2\s*\("([^"]+)"\);'
                  r'\s*values\s*\(\s*\\?\s*((?:"[^"]+",?\s*\\?\s*)+)\)', body)
    if not m:
        return None
    i1 = [float(x) for x in m.group(1).split(',')]
    i2 = [float(x) for x in m.group(2).split(',')]
    rows = [[float(x) for x in r.split(',')] for r in re.findall(r'"([^"]+)"', m.group(3))]
    return i1, i2, rows


def lookup(tab, slew, load):
    i1, i2, v = tab
    a, fa = interp(i1, slew)
    b, fb = interp(i2, load)
    top = v[a][b] * (1 - fb) + v[a][b + 1] * fb
    bot = v[a + 1][b] * (1 - fb) + v[a + 1][b + 1] * fb
    return top * (1 - fa) + bot * fa


def main():
    slew, load = float(sys.argv[1]), float(sys.argv[2])
    for spec in sys.argv[3:]:
        lib, cell, frm, to = spec.split(':')
        try:
            c = cell_text(lib, cell)
            out = group(c, 'pin', to)
            worst = 0.0
            for tm in re.finditer(r'\btiming\s*\(\s*\)\s*\{', out):
                depth, i = 1, tm.end()
                while depth:
                    depth += {'{': 1, '}': -1}.get(out[i], 0)
                    i += 1
                body = out[tm.end():i]
                if not re.search(r'related_pin\s*:\s*"?%s"?\s*;' % re.escape(frm), body):
                    continue
                for kind in ('cell_rise', 'cell_fall'):
                    t = table(body, kind)
                    if t:
                        worst = max(worst, lookup(t, slew, load))
            cap = re.search(r'\bcapacitance\s*:\s*([\d.eE+-]+)', group(c, 'pin', frm))
            print('%-60s %-34s %4.0f ps  Cin %5.1f fF' % (lib.split('/')[-1], cell + ' ' + frm + '->' + to,
                                                        worst * 1000, float(cap.group(1)) * 1000 if cap else -1))
        except Exception as e:  # report and continue
            print('%-60s %-34s ERROR %s' % (lib.split('/')[-1], cell, e))


if __name__ == '__main__':
    main()
