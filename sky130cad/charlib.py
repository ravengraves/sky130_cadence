#!/usr/bin/env python3
"""Characterize standard cells with Spectre sweeps and write a Liberty file.

  python3 sky130.py characterize --cells inv_1,mux2_1,dfxtp_1 [--corner ss_150C_1v60] [--jobs N]
  (fd_sc cells: config built from the converted Liberty by fdsc_config(); the shipped tables
  are the reference, so compare.txt shows the agreement point by point)

Per cell (CONFIG "cells" list):
  name, netlist (Spectre-ready: spectre_netlist.py), supplies {pin: "vdd"|"0"},
  outputs {pin: Liberty function} for combinational outputs, optional
  ff {clock, data, q, qn} for a positive-edge flip-flop, optional reference {lib, cell}.
CONFIG "corner": {models, vdd, temp, name}; optional "pushout" (default 0.10),
"constraint_load_pf" (default 0.005), "defaults" {slews, loads, constraint_slews}.

Measurements (thresholds 50 % delay, 20-80 % slew, like the SkyWater and OSU libraries):
- Combinational arc IN->OUT: every side-input assignment that sensitizes the arc (from the
  function; at most 4 per arc, spread over the list) is one Spectre run sweeping input
  slew x load (`.data` sweep). Table value = worst over assignments; timing_sense from the
  function. Input capacitance = charge from the input source over one edge / VDD.
- Flip-flop: CLK->Q (and QN) delay/transition sweeping clock slew x load; setup_rising and
  hold_rising rise/fall constraints by bisection over the data-to-clock offset, all table
  points in each Spectre run. A point passes when the flop captures the expected value with
  CLK->Q at most (1 + pushout) x its value with a generous margin.
- Index grids come from the reference cell's tables when a reference is given (so the
  output can be compared point by point; `compare.txt`), else from "defaults".
Not characterized: power, min_pulse_width, recovery/removal, max_capacitance.
"""
import concurrent.futures as cf
import json
import os
import re
import shutil

from . import toolenv

# ---------------------------------------------------------------- Liberty reading


def _skip(t, i):
    while i < len(t):
        if t[i] in ' \t\r\n':
            i += 1
        elif t.startswith('/*', i):
            i = t.index('*/', i) + 2
        elif t.startswith('//', i):
            i = t.find('\n', i) + 1 or len(t)
        elif t[i] == '\\' and i + 1 < len(t) and t[i + 1] in '\r\n':
            i += 1
        else:
            break
    return i


def _until(t, i, stop):
    out, q = [], False
    while i < len(t):
        c = t[i]
        if c == '"':
            q = not q
        if not q and c in stop:
            break
        out.append(c)
        i += 1
    return ''.join(out), i


def parse_group(t, i=0):
    """Parse group body starting after '{'. Returns ({'attrs':{}, 'groups':[]}, index after '}')."""
    g = {'attrs': {}, 'groups': []}
    while True:
        i = _skip(t, i)
        if i >= len(t) or t[i] == '}':
            return g, i + 1
        m = re.compile(r'[A-Za-z_][\w.]*').match(t, i)
        if not m:
            i += 1
            continue
        name = m.group(0)
        i = _skip(t, m.end())
        if t[i] == ':':
            val, i = _until(t, i + 1, ';\n}')
            g['attrs'][name] = val.strip().strip('"')
            if i < len(t) and t[i] == ';':
                i += 1
        elif t[i] == '(':
            depth, j, q = 0, i, False
            while True:
                c = t[j]
                if c == '"':
                    q = not q
                elif not q and c == '(':
                    depth += 1
                elif not q and c == ')':
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            args = t[i + 1:j]
            i = _skip(t, j + 1)
            if i < len(t) and t[i] == '{':
                sub, i = parse_group(t, i + 1)
                g['groups'].append((name, args.strip().strip('"'), sub))
            else:
                g['attrs'].setdefault(name, args)
                if i < len(t) and t[i] == ';':
                    i += 1
        else:
            i += 1


def lib_cell(path, cell):
    t = open(path).read()
    m = re.search(r'cell\s*\(\s*"?%s"?\s*\)\s*\{' % re.escape(cell), t)
    if not m:
        raise KeyError('%s not in %s' % (cell, path))
    g, _ = parse_group(t, m.end())
    return g


def nums(s):
    return [float(x) for x in re.findall(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', s)]


def table_of(g):
    i1 = nums(g['attrs'].get('index_1', ''))
    i2 = nums(g['attrs'].get('index_2', ''))
    rows = re.findall(r'"([^"]*)"', g['attrs'].get('values', ''))
    vals = [nums(r) for r in rows]
    if not i2 and vals and len(vals) == 1 and len(vals[0]) == len(i1):
        vals = [[v] for v in vals[0]]
    return i1, i2, vals


def ref_timings(cellg):
    """{(pin, related_pin, timing_type): [timing group, ...]}"""
    out = {}
    for gt, gn, pg in cellg['groups']:
        if gt != 'pin':
            continue
        for tt, _, tg in pg['groups']:
            if tt == 'timing':
                key = (gn, tg['attrs'].get('related_pin', ''), tg['attrs'].get('timing_type', 'combinational'))
                out.setdefault(key, []).append(tg)
    return out


def ref_table(timings, key, kind):
    """Table of `kind` for key. Unconditional group if present; otherwise the element-wise
    maximum over the `when`-conditional groups (the worst case our single table models)."""
    groups = timings.get(key, [])
    plain = [tg for tg in groups if 'when' not in tg['attrs']]
    tabs = []
    for tg in (plain[:1] or groups):
        for k, _, g in tg['groups']:
            if k == kind:
                tabs.append(table_of(g))
    if not tabs:
        return None
    i1, i2, vals = tabs[0]
    for t in tabs[1:]:
        if t[0] == i1 and t[1] == i2:
            vals = [[max(x, y) for x, y in zip(r1, r2)] for r1, r2 in zip(vals, t[2])]
    return i1, i2, vals


def ref_pin_caps(cellg):
    caps = {}
    for gt, gn, pg in cellg['groups']:
        if gt == 'pin' and 'capacitance' in pg['attrs']:
            caps[gn] = float(pg['attrs']['capacitance'])
    return caps

# ---------------------------------------------------------------- boolean functions


def py_expr(f):
    f = f.replace('!', ' not ').replace('&', ' and ').replace('*', ' and ')
    f = f.replace('|', ' or ').replace('+', ' or ')
    f = re.sub(r"([A-Za-z_]\w*)'", r'(not \1)', f)
    return f


def evaluate(f, env):
    e = py_expr(f)
    if '^' in e:
        e = e.replace('^', ' != ')
    return bool(eval(e, {}, {k: bool(v) for k, v in env.items()}))


def sensitizations(f, pin, inputs):
    """[(side assignment, sense)] where the output depends on pin."""
    others = [p for p in inputs if p != pin]
    out = []
    for k in range(2 ** len(others)):
        env = {p: (k >> n) & 1 for n, p in enumerate(others)}
        lo = evaluate(f, dict(env, **{pin: 0}))
        hi = evaluate(f, dict(env, **{pin: 1}))
        if lo != hi:
            out.append((env, 'positive' if hi else 'negative'))
    if len(out) > 4:
        idx = sorted({round(i * (len(out) - 1) / 3) for i in range(4)})
        out = [out[i] for i in idx]
    return out

# ---------------------------------------------------------------- Spectre


class Spectre:
    def __init__(self, cfg, workdir, env=None):
        self.env = env
        self.c = dict(cfg['corner'])
        self.c['models'] = os.path.abspath(self.c['models'])   # decks run inside the work dir
        self.vdd = float(self.c['vdd'])
        self.dir = os.path.abspath(workdir)
        os.makedirs(workdir, exist_ok=True)

    def run(self, tag, body, columns, rows, measures, tstop):
        """One transient sweep over `rows` (list of dicts with `columns`). Returns list of dicts."""
        lines = ['simulator lang=spice',
                 '.include "%s"' % self.c['models']] + body
        # defaults = first sweep row: Spectre checks PWL time order with the defaults
        lines.append('.param vdd=%g %s' % (self.vdd, ' '.join('%s=%.6g' % (c, rows[0][c]) for c in columns)))
        lines.append('.temp %g' % float(self.c['temp']))
        lines.append('.data dtab ' + ' '.join(columns))
        for r in rows:
            lines.append(' '.join('%.6g' % r[c] for c in columns))
        lines.append('.enddata')
        lines.append('.tran 1p %.6g sweep data=dtab' % tstop)
        lines += measures
        lines.append('.end')
        scs = os.path.join(self.dir, tag + '.scs')
        open(scs, 'w').write('\n'.join(lines) + '\n')
        log = os.path.join(self.dir, tag + '.log')
        rc = toolenv.run(['spectre', '-64', '+escchars', '-format', 'psfxl', '=log', log,
                          '-raw', os.path.join(self.dir, tag + '.raw'), scs],
                         self.dir, os.path.join(self.dir, tag + '.out'), self.env)
        mt0 = os.path.join(self.dir, tag + '.mt0')
        if rc or not os.path.exists(mt0):
            raise RuntimeError('spectre failed for %s (see %s)' % (tag, log))
        shutil.rmtree(os.path.join(self.dir, tag + '.raw'), ignore_errors=True)
        # .mt0: header names, then values; both wrap at a fixed width, so read tokens.
        lines = open(mt0).read().split('\n')
        toks = ' '.join(l for l in lines if l and not l.startswith(('$', '.title'))).split()
        k = 0
        while k < len(toks) and not re.match(r'^[-+0-9.]', toks[k]):
            k += 1
        names, vals = toks[:k], toks[k:]
        res = []
        for start in range(0, len(vals) - len(names) + 1, len(names)):
            d = {}
            for n, v in zip(names, vals[start:start + len(names)]):
                try:
                    d[n] = float(v)
                except ValueError:
                    d[n] = None
            res.append(d)
        if len(res) != len(rows):
            raise RuntimeError('%s: %d result rows for %d sweep rows' % (tag, len(res), len(rows)))
        return res


def subckt_pins(netlist, cell):
    for line in open(netlist):
        t = line.split()
        if len(t) > 1 and t[0].lower() == '.subckt' and t[1] == cell:
            return t[2:]
    raise KeyError('subckt %s not in %s' % (cell, netlist))


def node(pin, supplies):
    s = supplies.get(pin)
    return s if s is not None else 'n_' + pin.lower()


def dut(cell, pins, supplies, netlist):
    return ['.include "%s"' % netlist, 'vdd vdd 0 vdd',
            'xdut %s %s' % (' '.join(node(p, supplies) for p in pins), cell)]

# ---------------------------------------------------------------- combinational


def comb_arc(sp, cell, pins, supplies, netlist, inputs, inp, out, func, slews, loads, tag):
    conds = sensitizations(func, inp, inputs)
    if not conds:
        return None
    rows = []
    for s in slews:
        for l in loads:
            half = 1.0 + 4 * s / 0.6 + 30 * l
            rows.append({'tr': s * 1e-9, 'cl': l * 1e-12, 't1': 0.3e-9, 't2': (0.3 + half) * 1e-9,
                         'w1': 0.25e-9, 'w2': (0.25 + half) * 1e-9})
    tstop = max(r['t2'] for r in rows) * 2 + 1e-9
    results = []
    for k, (env, sense) in enumerate(conds):
        ni, no = node(inp, supplies), node(out, supplies)
        body = dut(cell, pins, supplies, netlist)
        body.append("vin %s 0 pwl(0 0 't1' 0 't1+tr/0.6' vdd 't2' vdd 't2+tr/0.6' 0)" % ni)
        for p, v in env.items():
            body.append('vs_%s %s 0 %s' % (p.lower(), node(p, supplies), 'vdd' if v else '0'))
        body.append('cload %s 0 cl' % no)
        r_in, f_in = ('rise', 'fall') if sense == 'positive' else ('fall', 'rise')
        meas = [
            ".meas tran d_or trig v(%s) val='vdd/2' %s=1 targ v(%s) val='vdd/2' rise=1" % (ni, r_in, no),
            ".meas tran d_of trig v(%s) val='vdd/2' %s=1 targ v(%s) val='vdd/2' fall=1" % (ni, f_in, no),
            ".meas tran s_or trig v(%s) val='0.2*vdd' rise=1 targ v(%s) val='0.8*vdd' rise=1" % (no, no),
            ".meas tran s_of trig v(%s) val='0.8*vdd' fall=1 targ v(%s) val='0.2*vdd' fall=1" % (no, no),
            ".meas tran q_r integ i(vin) from='w1' to='w2'",
            ".meas tran q_f integ i(vin) from='w2' to='%.6g'" % tstop]
        res = sp.run('%s_c%d' % (tag, k), body, ['tr', 'cl', 't1', 't2', 'w1', 'w2'], rows, meas, tstop)
        results.append((env, sense, res))
    senses = {s for _, s, _ in results}
    sense = senses.pop() + '_unate' if len(senses) == 1 else 'non_unate'

    def tab(key):
        vals = []
        for i in range(len(slews)):
            row = []
            for j in range(len(loads)):
                v = [res[i * len(loads) + j][key] for _, _, res in results]
                v = [x for x in v if x is not None]
                row.append(max(v) * 1e9 if v else float('nan'))
            vals.append(row)
        return vals
    caps = []
    for _, _, res in results:
        caps += [abs(res[0]['q_r']) / sp.vdd * 1e12, abs(res[0]['q_f']) / sp.vdd * 1e12]
    return {'related_pin': inp, 'timing_sense': sense, 'timing_type': 'combinational',
            'conditions': [(e, s) for e, s, _ in results], 'index_1': slews, 'index_2': loads,
            'cell_rise': tab('d_or'), 'cell_fall': tab('d_of'),
            'rise_transition': tab('s_or'), 'fall_transition': tab('s_of'),
            'cap': (max(caps[0::2]), max(caps[1::2]))}

# ---------------------------------------------------------------- flip-flop


def ff_body(cell, pins, supplies, netlist, ff, extra_load=True):
    body = dut(cell, pins, supplies, netlist)
    c, d = node(ff['clock'], supplies), node(ff['data'], supplies)
    body.append("vclk %s 0 pwl(0 0 'c1' 0 'c1+trc/0.6' vdd 'c1+hp' vdd 'c1+hp+trc/0.6' 0 "
                "'c2' 0 'c2+trc/0.6' vdd 'c2+hp' vdd 'c2+hp+trc/0.6' 0 'c3' 0 'c3+trc/0.6' vdd)" % c)
    body.append("vd %s 0 pwl(0 'v0' 'd1' 'v0' 'd1+trd/0.6' 'v1' 'd2' 'v1' 'd2+trd/0.6' 'v2')" % d)
    for p in (ff['q'], ff.get('qn')):
        if p:
            body.append('cload_%s %s 0 cl' % (p.lower(), node(p, supplies)))
    return body


FF_COLS = ['trc', 'trd', 'cl', 'c1', 'c2', 'c3', 'hp', 'd1', 'd2', 'v0', 'v1', 'v2', 'c2m', 'tend']


def ff_row(sp, trc, trd, cl, d1_rel, d2_rel, vals, period):
    """Clock edges c1 (preload), c2 (measured), c3; data edges at c2 50 % + d*_rel (50 % points)."""
    c1 = 0.5
    c2 = c1 + period
    c3 = c2 + period
    c2m = c2 + 0.5 * trc / 0.6
    vdd = sp.vdd
    r = {'trc': trc * 1e-9, 'trd': trd * 1e-9, 'cl': cl * 1e-12, 'c1': c1 * 1e-9, 'c2': c2 * 1e-9,
         'c3': c3 * 1e-9, 'hp': period / 2 * 1e-9, 'c2m': c2m * 1e-9, 'tend': (c3 - 0.2) * 1e-9}
    r['d1'] = (c2m + d1_rel - 0.5 * trd / 0.6) * 1e-9
    r['d2'] = (c2m + d2_rel - 0.5 * trd / 0.6) * 1e-9
    r['v0'], r['v1'], r['v2'] = (vdd * v for v in vals)
    return r


def ff_clk_q(sp, cell, pins, supplies, netlist, ff, slews, loads, trd, tag):
    """Q rises at c2 (D 0->1 mid-cycle before), falls at c3 (D 1->0 mid-cycle after c2)."""
    rows = []
    for s in slews:
        for l in loads:
            period = 2 * (1.5 + 4 * s / 0.6 + 4 * trd / 0.6 + 30 * l)
            rows.append(ff_row(sp, s, trd, l, -period / 2, period / 2, (0, 1, 0), period))
    tstop = max(r['c3'] for r in rows) + max(r['hp'] for r in rows) * 1.5
    body = ff_body(cell, pins, supplies, netlist, ff)
    c = node(ff['clock'], supplies)
    meas = []
    for p, first, second in ((ff['q'], 'rise', 'fall'), (ff.get('qn'), 'fall', 'rise')):
        if not p:
            continue
        n, k = node(p, supplies), p.lower()
        meas += [".meas tran d_%s_r trig v(%s) val='vdd/2' td='c2' rise=1 targ v(%s) val='vdd/2' td='c2' %s=1"
                 % (k, c, n, first),
                 ".meas tran d_%s_f trig v(%s) val='vdd/2' td='c3' rise=1 targ v(%s) val='vdd/2' td='c3' %s=1"
                 % (k, c, n, second),
                 ".meas tran s_%s_r trig v(%s) val='%s' td='c2' %s=1 targ v(%s) val='%s' td='c2' %s=1"
                 % (k, n, '0.2*vdd' if first == 'rise' else '0.8*vdd', first, n,
                    '0.8*vdd' if first == 'rise' else '0.2*vdd', first),
                 ".meas tran s_%s_f trig v(%s) val='%s' td='c3' %s=1 targ v(%s) val='%s' td='c3' %s=1"
                 % (k, n, '0.2*vdd' if second == 'rise' else '0.8*vdd', second, n,
                    '0.8*vdd' if second == 'rise' else '0.2*vdd', second)]
    meas += [".meas tran q_clk integ i(vclk) from='c2-0.05e-9' to='c2+hp-0.05e-9'",
             ".meas tran q_d integ i(vd) from='d1-0.05e-9' to='d2-0.05e-9'"]
    res = sp.run(tag, body, FF_COLS, rows, meas, tstop)
    out = {}
    for p, rk, fk in ((ff['q'], 'r', 'f'), (ff.get('qn'), 'f', 'r')):
        if not p:
            continue
        k = p.lower()

        def tab(key):
            return [[(res[i * len(loads) + j][key] or float('nan')) * 1e9 for j in range(len(loads))]
                    for i in range(len(slews))]
        # for Q: output rise at c2 (d_q_r); for QN: output fall at c2 (d_qn_r) and rise at c3
        rise_key, fall_key = ('d_%s_r' % k, 'd_%s_f' % k) if p == ff['q'] else ('d_%s_f' % k, 'd_%s_r' % k)
        srise, sfall = ('s_%s_r' % k, 's_%s_f' % k) if p == ff['q'] else ('s_%s_f' % k, 's_%s_r' % k)
        out[p] = {'related_pin': ff['clock'], 'timing_sense': 'non_unate', 'timing_type': 'rising_edge',
                  'index_1': slews, 'index_2': loads, 'cell_rise': tab(rise_key), 'cell_fall': tab(fall_key),
                  'rise_transition': tab(srise), 'fall_transition': tab(sfall)}
    caps = {ff['clock']: abs(res[0]['q_clk']) / sp.vdd * 1e12, ff['data']: abs(res[0]['q_d']) / sp.vdd * 1e12}
    return out, caps


def ff_constraint(sp, cell, pins, supplies, netlist, ff, kind, edge, dslews, cslews, cl, pushout, tag):
    """Bisection of the data-to-clock offset for every (data slew, clock slew) point at once.
    setup: data reaches the new value `off` before the clock 50 % point.
    hold: data leaves the captured value `off` after the clock 50 % point."""
    if kind == 'setup':
        vals = (0, 1, 1) if edge == 'rise' else (1, 0, 0)
        expect, lo0, hi0 = vals[1], -1.0, 3.0     # small offset fails, large passes
    else:
        vals = (1, 0, 1) if edge == 'rise' else (0, 1, 0)
        expect, lo0, hi0 = vals[1], -2.0, 2.0
    q = node(ff['q'], supplies)
    c = node(ff['clock'], supplies)
    qedge = 'rise' if expect else 'fall'
    pts = [(ds, cs) for ds in dslews for cs in cslews]
    # Search range per point grows with the slews (a 10 ns data ramp moves hold by several ns).
    span = [(ds + cs) / 0.6 for ds, cs in pts]
    lo = [lo0 - 2 * sp_ for sp_ in span]
    hi = [hi0 + 2 * sp_ for sp_ in span]
    period = 2 * (2.0 + max(max(map(abs, lo)), max(hi)) + 4 * max(dslews + cslews) / 0.6)

    def rows_for(offs):
        rows = []
        for (ds, cs), off in zip(pts, offs):
            if kind == 'setup':
                rows.append(ff_row(sp, cs, ds, cl, -off, period / 2, vals, period))
            else:
                rows.append(ff_row(sp, cs, ds, cl, -period / 2, off, vals, period))
        return rows
    body = ff_body(cell, pins, supplies, netlist, ff)
    meas = [".meas tran cq trig v(%s) val='vdd/2' td='c2' rise=1 targ v(%s) val='vdd/2' td='c2' %s=1"
            % (c, q, qedge),
            ".meas tran qend find v(%s) at='tend'" % q]
    tstop = 0.5 + 2 * period + 0.1
    counter = [0]

    def evaluate_offs(offs):
        res = sp.run('%s_%s_%s_i%d' % (tag, kind, edge, counter[0]), body, FF_COLS, rows_for(offs), meas,
                     tstop * 1e-9)
        counter[0] += 1
        return [(r['cq'], r['qend']) for r in res]
    nom = [x[0] for x in evaluate_offs([h + 1.0 for h in hi])]

    def ok(r, k):
        cq, qend = r
        good_level = qend is not None and ((qend > sp.vdd / 2) == bool(expect))
        return cq is not None and good_level and nom[k] is not None and cq <= (1 + pushout) * nom[k]
    for widen in range(3):
        chk_hi, chk_lo = evaluate_offs(hi), evaluate_offs(lo)
        bad = [k for k in range(len(pts)) if not ok(chk_hi[k], k) or ok(chk_lo[k], k)]
        if not bad or widen == 2:
            break
        for k in bad:     # widen the range only where it failed to bracket
            if ok(chk_lo[k], k):
                lo[k] -= 2 + 2 * span[k]
            if not ok(chk_hi[k], k):
                hi[k] += 2 + 2 * span[k]
        period = 2 * (2.0 + max(max(map(abs, lo)), max(hi)) + 4 * max(dslews + cslews) / 0.6)
        tstop = 0.5 + 2 * period + 0.1
        nom = [x[0] for x in evaluate_offs([h + 1.0 for h in hi])]
    while max(h - l for h, l in zip(hi, lo)) > 0.002:
        mid = [(h + l) / 2 for h, l in zip(hi, lo)]
        r = evaluate_offs(mid)
        for k in range(len(pts)):
            if ok(r[k], k):
                hi[k] = mid[k]
            else:
                lo[k] = mid[k]
    vals_tab = [[hi[i * len(cslews) + j] for j in range(len(cslews))] for i in range(len(dslews))]
    # Never write NaN to Liberty: an unbracketed point takes its nearest bracketed neighbour.
    good = [k for k in range(len(pts)) if k not in bad]
    for k in bad:
        i, j = divmod(k, len(cslews))
        if good:
            n = min(good, key=lambda g: abs(g // len(cslews) - i) + abs(g % len(cslews) - j))
            vals_tab[i][j] = vals_tab[n // len(cslews)][n % len(cslews)]
    return vals_tab, len(bad), counter[0]


# ---------------------------------------------------------------- Liberty writing


def fmt_list(v):
    return '"%s"' % ', '.join('%.5g' % x for x in v)


def write_table(f, kind, tmpl, i1, i2, vals, ind='        '):
    f.write('%s%s (%s) {\n' % (ind, kind, tmpl))
    f.write('%s  index_1 (%s);\n' % (ind, fmt_list(i1)))
    if i2:
        f.write('%s  index_2 (%s);\n' % (ind, fmt_list(i2)))
        rows = [fmt_list(r) for r in vals]
    else:
        rows = [fmt_list([r[0] for r in vals])]
    f.write('%s  values (%s);\n' % (ind, (', \\\n' + ind + '    ').join(rows)))
    f.write('%s}\n' % ind)


def write_liberty(path, cfg, cells):
    c = cfg['corner']
    templates = {}

    def tmpl(i1, i2, var1, var2):
        key = (tuple(i1), tuple(i2), var1, var2)
        if key not in templates:
            templates[key] = 'tmpl_%d' % len(templates)
        return templates[key]
    # register templates first
    for cell in cells:
        for t in cell['timing']:
            if t['timing_type'] in ('setup_rising', 'hold_rising'):
                tmpl(t['index_1'], t['index_2'], 'constrained_pin_transition', 'related_pin_transition')
            else:
                tmpl(t['index_1'], t['index_2'], 'input_net_transition', 'total_output_net_capacitance')
    with open(path, 'w') as f:
        f.write('/* Generated by sky130cad/charlib.py with Spectre; corner %s: models %s, %g V, %g C.\n'
                '   Delay 50 %%, slew 20-80 %%; setup/hold: CLK->Q pushout %g %%. No power data. */\n'
                % (c.get('name', ''), c['models'], float(c['vdd']), float(c['temp']), 100 * cfg.get('pushout', 0.1)))
        f.write('library (%s) {\n' % cfg.get('library', 'charlib'))
        for k, v in [('delay_model', 'table_lookup'), ('time_unit', '"1ns"'), ('voltage_unit', '"1V"'),
                     ('current_unit', '"1mA"'), ('pulling_resistance_unit', '"1kohm"'),
                     ('input_threshold_pct_rise', 50), ('input_threshold_pct_fall', 50),
                     ('output_threshold_pct_rise', 50), ('output_threshold_pct_fall', 50),
                     ('slew_lower_threshold_pct_rise', 20), ('slew_lower_threshold_pct_fall', 20),
                     ('slew_upper_threshold_pct_rise', 80), ('slew_upper_threshold_pct_fall', 80),
                     ('slew_derate_from_library', 1.0), ('nom_process', 1.0), ('nom_voltage', c['vdd']),
                     ('nom_temperature', c['temp'])]:
            f.write('  %s : %s;\n' % (k, v))
        f.write('  capacitive_load_unit (1, pf);\n')
        f.write('  operating_conditions (%s) { process : 1; voltage : %s; temperature : %s; }\n'
                % (c.get('name', 'corner'), c['vdd'], c['temp']))
        f.write('  default_operating_conditions : %s;\n' % c.get('name', 'corner'))
        for (i1, i2, v1, v2), name in templates.items():
            f.write('  lu_table_template (%s) {\n    variable_1 : %s;\n' % (name, v1))
            if i2:
                f.write('    variable_2 : %s;\n' % v2)
            f.write('    index_1 (%s);\n' % fmt_list(i1))
            if i2:
                f.write('    index_2 (%s);\n' % fmt_list(i2))
            f.write('  }\n')
        for cell in cells:
            f.write('  cell (%s) {\n' % cell['name'])
            if cell.get('area'):
                f.write('    area : %g;\n' % cell['area'])
            if cell.get('ff'):
                ff = cell['ff']
                f.write('    ff (IQ, IQN) {\n      next_state : "%s";\n      clocked_on : "%s";\n    }\n'
                        % (ff['data'], ff['clock']))
            for pin, cap in cell['inputs'].items():
                f.write('    pin (%s) {\n      direction : input;\n' % pin)
                if cell.get('ff') and pin == cell['ff']['clock']:
                    f.write('      clock : true;\n')
                f.write('      capacitance : %.5g;\n      rise_capacitance : %.5g;\n      fall_capacitance : %.5g;\n'
                        % ((cap[0] + cap[1]) / 2, cap[0], cap[1]))
                for t in cell['timing']:
                    if t.get('pin') == pin:
                        write_timing(f, t, tmpl)
                f.write('    }\n')
            for pin, func in cell['outputs'].items():
                f.write('    pin (%s) {\n      direction : output;\n      function : "%s";\n' % (pin, func))
                for t in cell['timing']:
                    if t.get('pin') == pin:
                        write_timing(f, t, tmpl)
                f.write('    }\n')
            f.write('  }\n')
        f.write('}\n')


def write_timing(f, t, tmpl):
    f.write('      timing () {\n        related_pin : "%s";\n' % t['related_pin'])
    if t['timing_type'] != 'combinational':
        f.write('        timing_type : %s;\n' % t['timing_type'])
    if t.get('timing_sense'):
        f.write('        timing_sense : %s;\n' % t['timing_sense'])
    if t['timing_type'] in ('setup_rising', 'hold_rising'):
        name = tmpl(t['index_1'], t['index_2'], 'constrained_pin_transition', 'related_pin_transition')
        kinds = ('rise_constraint', 'fall_constraint')
    else:
        name = tmpl(t['index_1'], t['index_2'], 'input_net_transition', 'total_output_net_capacitance')
        kinds = ('cell_rise', 'rise_transition', 'cell_fall', 'fall_transition')
    for k in kinds:
        write_table(f, k, name, t['index_1'], t['index_2'], t[k])
    f.write('      }\n')

# ---------------------------------------------------------------- comparison


def compare(f, cell, ref, timings):
    for t in timings:
        key = (t['pin'], t['related_pin'], t['timing_type'])
        kinds = ('rise_constraint', 'fall_constraint') if 'constraint' in str(t.keys()) else \
            ('cell_rise', 'cell_fall', 'rise_transition', 'fall_transition')
        for k in kinds:
            if k not in t:
                continue
            r = ref_table(ref, key, k)
            if not r:
                f.write('%-28s %-22s %-16s no reference table\n' % (cell, '%s->%s %s' % (t['related_pin'], t['pin'], t['timing_type'][:5]), k))
                continue
            i1, i2, rv = r
            ours = t[k]
            diffs, rel = [], []
            for i in range(min(len(rv), len(ours))):
                for j in range(min(len(rv[i]), len(ours[i]))):
                    a, b = ours[i][j], rv[i][j]
                    if a != a:
                        continue
                    diffs.append(a - b)
                    if abs(b) > 0.02:
                        rel.append((a - b) / abs(b))
            if not diffs:
                continue
            mean_rel = sum(rel) / len(rel) if rel else 0
            maxabs = max(diffs, key=abs)
            f.write('%-28s %-22s %-16s mean %+6.1f %%  max |%%| %5.1f  max diff %+7.3f ns  (%d pts)\n'
                    % (cell, '%s->%s %s' % (t['related_pin'], t['pin'], t['timing_type'][:5]), k,
                       100 * mean_rel, 100 * max(map(abs, rel)) if rel else 0, maxabs, len(diffs)))

# ---------------------------------------------------------------- driver


def grid(ref, key, kind, default):
    if ref:
        r = ref_table(ref, key, kind)
        if r:
            return r[0], r[1]
    return default


def characterize(cfg, cellcfg, outdir, jobs, env=None):
    sp = Spectre(cfg, os.path.join(outdir, 'spectre', cellcfg['name']), env)
    name, netlist = cellcfg['name'], os.path.abspath(cellcfg['netlist'])
    pins = subckt_pins(netlist, name)
    supplies = cellcfg['supplies']
    ff = cellcfg.get('ff')
    outputs = dict(cellcfg.get('outputs', {}))
    ref = None
    refcell = None
    if cellcfg.get('reference'):
        refcell = lib_cell(cellcfg['reference']['lib'], cellcfg['reference']['cell'])
        ref = ref_timings(refcell)
    d = cfg.get('defaults', {})
    dslews = d.get('slews', [0.01, 0.03, 0.08, 0.2, 0.5, 1.0, 1.5])
    dloads = d.get('loads', [0.0005, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2])
    cslews = d.get('constraint_slews', [0.01, 0.06, 0.25, 0.75, 1.5])
    inputs = [p for p in pins if p not in supplies and p not in outputs and
              (not ff or p not in (ff['q'], ff.get('qn')))]
    timing, caps, log = [], {}, []
    tasks = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        for out, func in outputs.items():
            for inp in inputs:
                key = (out, inp, 'combinational')
                i1, i2 = grid(ref, key, 'cell_rise', (dslews, dloads))
                tasks[ex.submit(comb_arc, sp, name, pins, supplies, netlist, inputs, inp, out, func,
                                i1, i2, '%s_%s_%s' % (name, inp, out))] = ('comb', out, inp)
        if ff:
            key = (ff['q'], ff['clock'], 'rising_edge')
            i1, i2 = grid(ref, key, 'cell_rise', (dslews, dloads))
            tasks[ex.submit(ff_clk_q, sp, name, pins, supplies, netlist, ff, i1, i2, 0.05,
                            '%s_clkq' % name)] = ('clkq',)
            for kind in ('setup', 'hold'):
                key = (ff['data'], ff['clock'], kind + '_rising')
                c1, c2 = grid(ref, key, 'rise_constraint', (cslews, cslews))
                if not c2:
                    c2 = [grid(ref, (ff['q'], ff['clock'], 'rising_edge'), 'cell_rise', (dslews, dloads))[0][0]]
                for edge in ('rise', 'fall'):
                    tasks[ex.submit(ff_constraint, sp, name, pins, supplies, netlist, ff, kind, edge, c1, c2,
                                    cfg.get('constraint_load_pf', 0.005), cfg.get('pushout', 0.10),
                                    name)] = ('cons', kind, edge, c1, c2)
        cons = {}
        for fut in cf.as_completed(tasks):
            info = tasks[fut]
            r = fut.result()
            if info[0] == 'comb' and r:
                r['pin'] = info[1]
                timing.append(r)
                caps.setdefault(info[2], []).append(r['cap'])
                log.append('%s %s->%s %s conditions %s' % (name, info[2], info[1], r['timing_sense'],
                                                          ['%s:%s' % (e, s) for e, s in r['conditions']]))
            elif info[0] == 'clkq':
                outs, ffcaps = r
                for p, t in outs.items():
                    t['pin'] = p
                    timing.append(t)
                for p, cval in ffcaps.items():
                    caps.setdefault(p, []).append((cval, cval))
            elif info[0] == 'cons':
                vals, nbad, iters = r
                cons[(info[1], info[2])] = (vals, info[3], info[4])
                log.append('%s %s %s: %d Spectre runs, %d points without a pass/fail bracket'
                           % (name, info[1], info[2], iters, nbad))
    if ff:
        for kind in ('setup', 'hold'):
            r, f_ = cons[(kind, 'rise')], cons[(kind, 'fall')]
            timing.append({'pin': ff['data'], 'related_pin': ff['clock'], 'timing_type': kind + '_rising',
                           'index_1': r[1], 'index_2': r[2] if len(r[2]) > 1 else [],
                           'rise_constraint': r[0], 'fall_constraint': f_[0]})
            outputs.setdefault(ff['q'], 'IQ')
            if ff.get('qn'):
                outputs.setdefault(ff['qn'], 'IQN')
    incaps = {p: (max(c[0] for c in v), max(c[1] for c in v)) for p, v in caps.items()}
    area = None
    if refcell and 'area' in refcell['attrs']:
        area = float(refcell['attrs']['area'])
    cell = {'name': name, 'inputs': {p: incaps.get(p, (0, 0)) for p in inputs}, 'outputs': outputs,
            'timing': timing, 'ff': ff, 'area': area}
    return cell, ref, refcell, log


def compare_only(cfg_path, lib, out):
    """Re-run the reference comparison for an existing Liberty (no simulation)."""
    cfg = json.load(open(cfg_path))
    with open(out, 'w') as f:
        for cc in cfg['cells']:
            if not cc.get('reference'):
                continue
            ref_cell = lib_cell(cc['reference']['lib'], cc['reference']['cell'])
            ours = lib_cell(lib, cc['name'])
            rc = ref_pin_caps(ref_cell)
            for gt, gn, pg in ours['groups']:
                if gt == 'pin' and pg['attrs'].get('direction') == 'input':
                    f.write('%-28s pin %-5s capacitance ours %.5f pF  reference %s\n' % (
                        cc['name'], gn, float(pg['attrs']['capacitance']), '%.5f' % rc[gn] if gn in rc else '-'))
            tims = []
            for key, groups in ref_timings(ours).items():
                for tg in groups:
                    t = {'pin': key[0], 'related_pin': key[1], 'timing_type': key[2]}
                    for k, _, g in tg['groups']:
                        t[k] = table_of(g)[2]
                    tims.append(t)
            compare(f, cc['name'], ref_timings(ref_cell), tims)
    print(open(out).read())


def run_config(cfg, outdir, jobs=4, env=None, only=None):
    """Characterize every cell of `cfg` (dict); write OUTDIR/<library>.lib and compare.txt."""
    os.makedirs(outdir, exist_ok=True)
    cells = []
    with open(os.path.join(outdir, 'compare.txt'), 'w') as comp, \
            open(os.path.join(outdir, 'charlib.log'), 'w') as logf:
        for cc in cfg['cells']:
            if only and cc['name'] not in only:
                continue
            cell, ref, refcell, log = characterize(cfg, cc, outdir, jobs, env)
            cells.append(cell)
            for l in log:
                logf.write(l + '\n')
                print(l, flush=True)
            if ref:
                rc = ref_pin_caps(refcell)
                for p, (cr, cf_) in cell['inputs'].items():
                    comp.write('%-28s pin %-5s capacitance ours %.5f pF (rise %.5f, fall %.5f)  reference %s\n'
                               % (cell['name'], p, (cr + cf_) / 2, cr, cf_, '%.5f' % rc[p] if p in rc else '-'))
                compare(comp, cell['name'], ref, cell['timing'])
                comp.flush()
    lib = os.path.join(outdir, '%s.lib' % cfg.get('library', 'charlib'))
    write_liberty(lib, cfg, cells)
    return lib, os.path.join(outdir, 'compare.txt')


CORNER_RE = re.compile(r'^(tt|ss|ff|sf|fs)_(n?)(\d+)C_(\d)v(\d+)')


def corner_conditions(corner):
    """'ss_150C_1v60' -> ('ss', 150.0, 1.60); 'ff_n40C_1v95_ccsnoise' -> ('ff', -40.0, 1.95)."""
    m = CORNER_RE.match(corner)
    if not m:
        raise ValueError('cannot read process/temperature/voltage from corner %r' % corner)
    temp = float(m.group(3)) * (-1 if m.group(2) else 1)
    return m.group(1), temp, float('%s.%s' % (m.group(4), m.group(5)))


def fdsc_config(reference_lib, cells, netlist_dir, models_dir, corner, lib='sky130_fd_sc_hs'):
    """Config for fd_sc cells from the converted Liberty: functions, flip-flops, reference.
    Supported: combinational cells and positive-edge D flip-flops without set/reset/scan."""
    process, temp, vdd = corner_conditions(corner)
    cfg = {'library': 'charlib_%s__%s' % (lib, corner),
           'corner': {'name': corner, 'models': os.path.join(models_dir, 'sky130_digital_%s.spice' % process),
                      'vdd': vdd, 'temp': temp},
           'pushout': 0.10, 'constraint_load_pf': 0.005, 'cells': []}
    skipped = []
    for short in cells:
        name = short if short.startswith(lib) else '%s__%s' % (lib, short)
        g = lib_cell(reference_lib, name)
        pins = {gn: pg['attrs'] for gt, gn, pg in g['groups'] if gt == 'pin'}
        ffs = [(gn, sg['attrs']) for gt, gn, sg in g['groups'] if gt == 'ff']
        cc = {'name': name, 'netlist': os.path.join(netlist_dir, name + '.spice'),
              'supplies': {'VPWR': 'vdd', 'VPB': 'vdd', 'VGND': '0', 'VNB': '0'},
              'reference': {'lib': reference_lib, 'cell': name}}
        if ffs:
            names = [x.strip().strip('"') for x in ffs[0][0].split(',')]
            attrs = ffs[0][1]
            extra = set(attrs) - {'clocked_on', 'next_state', 'power_down_function'}
            clk, nxt = attrs.get('clocked_on', '').strip('"'), attrs.get('next_state', '').strip('"')
            if extra or not re.fullmatch(r'\w+', clk) or not re.fullmatch(r'\w+', nxt):
                skipped.append('%s (ff %s)' % (name, attrs))
                continue
            q = [p for p, a in pins.items() if a.get('direction') == 'output' and a.get('function') == names[0]]
            qn = [p for p, a in pins.items() if a.get('direction') == 'output' and len(names) > 1
                  and a.get('function') == names[1]]
            if not q:
                skipped.append('%s (no Q output)' % name)
                continue
            cc['ff'] = {'clock': clk, 'data': nxt, 'q': q[0], 'qn': qn[0] if qn else None}
        elif any(gt in ('latch', 'statetable') for gt, _, _ in g['groups']):
            skipped.append('%s (latch/statetable)' % name)
            continue
        else:
            outs = {p: a['function'] for p, a in pins.items() if a.get('direction') == 'output' and a.get('function')}
            if not outs:
                skipped.append('%s (no output function)' % name)
                continue
            cc['outputs'] = outs
        cfg['cells'].append(cc)
    return cfg, skipped
