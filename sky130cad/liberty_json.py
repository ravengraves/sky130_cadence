#!/usr/bin/env python3
"""Write an NLDM Liberty file for a SkyWater fd_sc library from the upstream JSON views.

The upstream repositories ship timing only as JSON: timing/<lib>__common.lib.json,
timing/<lib>__<corner>.lib.json and cells/*/<cell>__<corner>.lib.json.

Library = timing/<lib>__common.lib.json + timing/<lib>__CORNER.lib.json, then every
cells/*/<cell>__CORNER.lib.json as a cell group. CCS-noise groups (ccsn_*) are dropped;
delay, transition, constraint, capacitance, function and power data are kept.
"""
import glob
import json
import os
import re

LIB = 'sky130_fd_sc_hs'
DROP_GROUPS = {'ccsn_first_stage', 'ccsn_last_stage', 'output_current_rise',
               'output_current_fall', 'receiver_capacitance', 'receiver_capacitance1_rise',
               'receiver_capacitance1_fall', 'receiver_capacitance2_rise',
               'receiver_capacitance2_fall'}
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def num(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    return repr(float(v)) if not float(v).is_integer() else ('%d' % v if abs(v) < 1e15 else repr(v))


def scalar(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return num(v)
    s = str(v)
    return s if IDENT.match(s) else '"' + s.replace('"', '\\"') + '"'


def emit(out, key, val, ind, drop=DROP_GROUPS):
    pad = '  ' * ind
    parts = key.split(',')
    kind = parts[0]
    if kind in drop:
        return
    if kind == 'comp_attribute':
        name = parts[1]
        if name == 'voltage_map':
            return  # written once by the library header
        items = val if isinstance(val, list) else [val]
        out.append('%s%s (%s);' % (pad, name, ', '.join(scalar(x) for x in items)))
        return
    if isinstance(val, dict):
        args = ', '.join('"%s"' % p for p in parts[1:])
        out.append('%s%s (%s) {' % (pad, kind, args))
        for k, v in val.items():
            emit(out, k, v, ind + 1, drop)
        out.append('%s}' % pad)
        return
    if isinstance(val, list) and val and isinstance(val[0], dict):
        for item in val:
            emit(out, key, item, ind, drop)
        return
    if isinstance(val, list) and val and all(isinstance(x, str) for x in val):
        # statetable rows: table : "row, row, ...";
        rows = ', \\\n'.join('%s  %s' % (pad, x) for x in val)
        out.append('%s%s : " \\\n%s";' % (pad, key, rows))
        return
    if isinstance(val, list):
        if key == 'values' and val and isinstance(val[0], list):
            rows = ', \\\n'.join('%s  "%s"' % (pad, ', '.join(num(x) for x in r)) for r in val)
            out.append('%svalues ( \\\n%s);' % (pad, rows))
        else:
            out.append('%s%s ("%s");' % (pad, key, ', '.join(num(x) for x in val)))
        return
    out.append('%s%s : %s;' % (pad, key, scalar(val)))


def convert(libdir, corner, output, lib=LIB, keep_ccs=False):
    """keep_ccs: also write the CCS timing and CCS-noise groups (DROP_GROUPS)."""
    drop = set() if keep_ccs else DROP_GROUPS
    """libdir: checkout of google/skywater-pdk-libs-<lib>; corner e.g. ss_150C_1v60."""
    common = json.load(open(os.path.join(libdir, 'timing', lib + '__common.lib.json')))
    head = json.load(open(os.path.join(libdir, 'timing', '%s__%s.lib.json' % (lib, corner))))
    vmap = {}
    for src in (common.get('comp_attribute,voltage_map'), head.get('comp_attribute,voltage_map')):
        if isinstance(src, dict):
            vmap.update(src)
        elif isinstance(src, list):
            vmap.update({k: v for k, v in src})
    out = ['library ("%s__%s") {' % (lib, corner)]
    for k, v in common.items():
        emit(out, k, v, 1, drop)
    for name, volt in vmap.items():
        out.append('  voltage_map (%s, %s);' % (name, num(volt)))
    for k, v in head.items():
        emit(out, k, v, 1, drop)
    cells = 0
    for path in sorted(glob.glob(os.path.join(libdir, 'cells', '*', '%s__*__%s.lib.json' % (lib, corner)))):
        cell = os.path.basename(path)[:-len('__%s.lib.json' % corner)]
        out.append('  cell ("%s") {' % cell)
        for k, v in json.load(open(path)).items():
            emit(out, k, v, 2, drop)
        out.append('  }')
        cells += 1
    out.append('}')
    with open(output, 'w') as f:
        f.write('\n'.join(out) + '\n')
    return cells
