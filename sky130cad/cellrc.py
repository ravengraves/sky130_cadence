"""Per-cell drive and load figures from a Liberty file, for comparing a modified cell with the
original (e.g. a Liberty written by `sky130.py characterize` against the release Liberty).

  python3 sky130.py cell-rc --cells nand2_2,inv_2 [--lib FILE.lib[.gz]] [--slew 0.1]

For every input -> output arc, at the input slew nearest --slew:
- Cin: input pin capacitance (fF);
- R rise / R fall: d(delay)/d(C_load) over the two smallest loads (kOhm), the output drive;
- t0 rise / t0 fall: delay extrapolated to zero load (ps): the cell's own (intrinsic) delay,
  set mostly by its internal and output-node capacitance;
- FO4: t0 + R x 4 x Cin (ps, average of rise and fall), a single figure of merit.
Lower R at the same Cin means more drive per unit input capacitance; lower t0 means less
internal/parasitic capacitance.
"""
import gzip
import re


def _group(text, kw, name=None):
    pat = r'\b%s\s*\(\s*"?%s"?\s*\)\s*\{' % (kw, re.escape(name) if name else r'[^)]*')
    for m in re.finditer(pat, text):
        i, depth = m.end(), 1
        while depth:
            depth += {'{': 1, '}': -1}.get(text[i], 0)
            i += 1
        yield m.group(0), text[m.end():i - 1]


def _nums(s):
    return [float(x) for x in re.findall(r'[-\d.eE+]+', s)]


def _read(path):
    return (gzip.open(path, 'rt') if path.endswith('.gz') else open(path)).read()


def cell_rc(lib_text, cell, slew=0.1):
    """[(pin, out, cin_fF, r_rise, r_fall, t0_rise_ps, t0_fall_ps, fo4_ps)]"""
    body = next((b for _, b in _group(lib_text, 'cell', cell)), None)
    if body is None:
        return []
    pins = {}
    for head, pb in _group(body, 'pin'):
        name = re.search(r'\(\s*"?(\w+)"?\s*\)', head).group(1)
        d = re.search(r'direction\s*:\s*"?(\w+)', pb)
        c = re.search(r'\bcapacitance\s*:\s*([\d.eE+-]+)', pb)
        pins[name] = (d.group(1) if d else '', float(c.group(1)) * 1000 if c else None, pb)
    rows = []
    for out, (d, _, pb) in pins.items():
        if d != 'output':
            continue
        for _, tb in _group(pb, 'timing'):
            rp = re.search(r'related_pin\s*:\s*"?(\w+)', tb)
            if not rp or re.search(r'timing_type\s*:\s*"?(setup|hold|recovery|removal)', tb):
                continue
            res = {}
            for kind in ('cell_rise', 'cell_fall'):
                g = next((b for _, b in _group(tb, kind)), None)
                if g is None:
                    continue
                i1 = _nums(re.search(r'index_1\s*\(\s*"([^"]+)"', g).group(1))
                i2 = _nums(re.search(r'index_2\s*\(\s*"([^"]+)"', g).group(1))
                vals = [_nums(r) for r in re.findall(r'"([^"]+)"', g.split('values')[1])]
                row = vals[min(range(len(i1)), key=lambda k: abs(i1[k] - slew))]
                r = (row[1] - row[0]) / (i2[1] - i2[0])
                res[kind] = (r, (row[0] - r * i2[0]) * 1000)
            if len(res) == 2:
                cin = pins.get(rp.group(1), (None, None))[1]
                fo4 = None
                if cin:
                    fo4 = sum(res[k][1] + res[k][0] * 4 * cin for k in res) / 2
                rows.append((rp.group(1), out, cin, res['cell_rise'][0], res['cell_fall'][0],
                             res['cell_rise'][1], res['cell_fall'][1], fo4))
    return rows


def report(lib_path, cells, prefix='sky130_fd_sc_hs__', slew=0.1):
    text = _read(lib_path)
    lines = ['%-14s %-10s %7s %8s %8s %8s %8s %8s' % ('cell', 'arc', 'Cin fF', 'R rise', 'R fall', 't0 rise',
                                                      't0 fall', 'FO4 ps')]
    for c in cells:
        name = c if c.startswith(prefix) or '__' in c else prefix + c
        for pin, out, cin, rr, rf, tr, tf, fo4 in cell_rc(text, name, slew):
            lines.append('%-14s %-10s %7.2f %8.2f %8.2f %8.0f %8.0f %8.0f' % (
                name.replace(prefix, ''), '%s->%s' % (pin, out), cin or float('nan'), rr, rf, tr, tf,
                fo4 if fo4 is not None else float('nan')))
    return '\n'.join(lines)
