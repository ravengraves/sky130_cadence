#!/usr/bin/env python3
"""Convert standard-cell SPICE netlists so Spectre can simulate them with the models from
spectre_models.py (which set `.option scale=1.0u`: sizes are in microns).

  used by `sky130.py characterize` (and spectre_netlist.convert(IN, OUT))

- Numbers with an exponent and a scale suffix (`w=1.12e+06u`, SkyWater fd_sc netlists)
  are misread by Spectre (SFE: geometry outside every model bin); they are rewritten as
  plain numbers (`1.12`).
- OSU netlists use legacy primitive models `nlowvt`, `nshort`, `pshort`, `phighvt` on
  `M` lines. They become `X` calls of the SkyWater subcircuits (nfet_01v8_lvt, nfet_01v8,
  pfet_01v8, pfet_01v8_hvt) keeping only parameters those subcircuits accept.
- Extractor-only elements are dropped: `p` probe elements and `NWDIODE` well diodes
  (nwell-substrate junction; not part of the switching path). `$...` comments are removed.
- `.include` files are converted too, next to OUT with an `_spectre` suffix.
"""
import os
import re
import sys

SUFFIX = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3, 'g': 1e9, 'meg': 1e6}
LEGACY = {'nlowvt': 'sky130_fd_pr__nfet_01v8_lvt', 'nshort': 'sky130_fd_pr__nfet_01v8',
          'pshort': 'sky130_fd_pr__pfet_01v8', 'phighvt': 'sky130_fd_pr__pfet_01v8_hvt'}
SUBCKT_PARAMS = {'l', 'w', 'ad', 'as', 'pd', 'ps', 'nrd', 'nrs', 'sa', 'sb', 'sd', 'nf'}
NUM = re.compile(r'(?<![\w.])([0-9]*\.?[0-9]+[eE][+-]?[0-9]+)(meg|[fpnumkg])(?![a-z])', re.I)


def plain(m):
    return '%.9g' % (float(m.group(1)) * SUFFIX[m.group(2).lower()])


def join_continuations(lines):
    out = []
    for line in lines:
        if line.startswith('+') and out:
            out[-1] += ' ' + line[1:].strip()
        else:
            out.append(line.rstrip('\n'))
    return out


def convert_line(line):
    line = re.sub(r'\s\$.*$', '', line)
    s = line.strip()
    if not s or s.startswith('*'):
        return line
    if s[0] in 'pP' and not s.lower().startswith(('.param', '.')):
        return None
    tok = s.split()
    if s[0] in 'dD' and len(tok) > 3 and tok[3].lower() == 'nwdiode':
        return None
    if s[0] in 'mM' and len(tok) > 5 and tok[5].lower() in LEGACY:
        params, mult = [], None
        for t in tok[6:]:
            if '=' not in t:
                continue
            k, v = t.split('=', 1)
            if k.lower() in SUBCKT_PARAMS:
                params.append('%s=%s' % (k.lower(), v))
            elif k.lower() in ('m', 'mult') and v not in ('1', '1.0'):
                mult = v
        if mult:
            params.append('m=%s' % mult)
        return ' '.join(['X' + tok[0]] + tok[1:5] + [LEGACY[tok[5].lower()]] + params)
    return NUM.sub(plain, line)


def convert(src, dst):
    lines = join_continuations(open(src).readlines())
    out = []
    for line in lines:
        m = re.match(r'\s*\.include\s+"?([^"\s]+)"?', line, re.I)
        if m:
            child = os.path.join(os.path.dirname(src), m.group(1))
            stem, ext = os.path.splitext(os.path.basename(m.group(1)))
            child_dst = os.path.join(os.path.dirname(dst), stem + '_spectre' + ext)
            convert(child, child_dst)
            out.append('.include "%s"' % os.path.abspath(child_dst))
            continue
        c = convert_line(line)
        if c is not None:
            out.append(c)
    open(dst, 'w').write('\n'.join(out) + '\n')


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
    print('wrote', sys.argv[2])
