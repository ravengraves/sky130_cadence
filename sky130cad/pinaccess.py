"""Pin-access audit of a standard-cell LEF: can the router land a contact on every signal pin?

  python3 sky130.py pin-access [--lef FILE]

Routing starts at met1 (li1 is not a routing layer in this flow), so a router reaches an li1 pin
with an mcon inside the pin's li1 and a met1 landing pad around it. For every signal pin this
counts the mcon positions (10 nm grid) where
- the 0.17 x 0.17 mcon lies inside one of the pin's li1 rectangles (ct.4: li1 encloses mcon), and
- the met1 pad (mcon + 0.03 on two opposite sides, + 0.06 on the other two, either orientation;
  m1.4/m1.5) keeps 0.14 um (m1.2) from every other met1 shape of the cell: OBS, supply rails and
  other pins.
Pins with no position cannot be reached without a short; with only a few positions in one spot,
access depends on the router finding that exact spot. Pins already on met1 count as accessible.
"""
import re

MCON, ENC, ENC_ADJ, SPACE, STEP = 0.17, 0.03, 0.06, 0.14, 0.01


def macros(lef_text):
    out = {}
    for m in re.finditer(r'^MACRO (\S+)\n(.*?)^END \1', lef_text, re.S | re.M):
        name, body = m.group(1), m.group(2)
        size = re.search(r'SIZE\s+([\d.]+)\s+BY\s+([\d.]+)', body)
        pins = {}
        for pm in re.finditer(r'^\s*PIN (\S+)(.*?)^\s*END \1\s*$', body, re.S | re.M):
            use = re.search(r'USE\s+(\w+)', pm.group(2))
            rects, cur = [], None
            for line in pm.group(2).split('\n'):
                t = line.split()
                if t[:1] == ['LAYER']:
                    cur = t[1]
                elif t[:1] == ['RECT']:
                    rects.append((cur, tuple(float(x) for x in t[1:5])))
            pins[pm.group(1)] = (use.group(1) if use else 'SIGNAL', rects)
        obs, cur = [], None
        om = re.search(r'^\s*OBS\s*$(.*?)^\s*END\s*$', body, re.S | re.M)
        if om:
            for line in om.group(1).split('\n'):
                t = line.split()
                if t[:1] == ['LAYER']:
                    cur = t[1]
                elif t[:1] == ['RECT']:
                    obs.append((cur, tuple(float(x) for x in t[1:5])))
        out[name] = {'size': (float(size.group(1)), float(size.group(2))) if size else None, 'pins': pins, 'obs': obs}
    return out


def _gap(a, b):
    """Edge-to-edge distance between rectangles (0 if they touch or overlap)."""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


def access_points(m, pin):
    """mcon positions (x, y of the lower-left corner) usable for `pin` of macro m."""
    use, rects = m['pins'][pin]
    if any(layer == 'met1' for layer, _ in rects):
        return None                                   # already a met1 pin
    others = [r for layer, r in m['obs'] if layer == 'met1']
    for p, (u, rs) in m['pins'].items():
        if p != pin:
            others += [r for layer, r in rs if layer == 'met1']
    li = [r for layer, r in rects if layer == 'li1']
    if not li:
        return []
    # an mcon may straddle several of the pin's rectangles: test coverage by the union
    def covered(x0, y0, x1, y1):
        if any(r[0] - 1e-9 <= x0 and x1 <= r[2] + 1e-9 and r[1] - 1e-9 <= y0 and y1 <= r[3] + 1e-9 for r in li):
            return True
        n = 4
        for i in range(n + 1):
            for j in range(n + 1):
                px, py = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n
                if not any(r[0] - 1e-9 <= px <= r[2] + 1e-9 and r[1] - 1e-9 <= py <= r[3] + 1e-9 for r in li):
                    return False
        return True
    bx0, by0 = min(r[0] for r in li), min(r[1] for r in li)
    bx1, by1 = max(r[2] for r in li), max(r[3] for r in li)
    nx = int(round((bx1 - bx0 - MCON) / STEP)) + 1
    ny = int(round((by1 - by0 - MCON) / STEP)) + 1
    pts = []
    for i in range(max(nx, 0)):
        for j in range(max(ny, 0)):
            cx, cy = bx0 + i * STEP, by0 + j * STEP
            if not covered(cx, cy, cx + MCON, cy + MCON):
                continue
            for ex, ey in ((ENC_ADJ, ENC), (ENC, ENC_ADJ)):
                pad = (cx - ex, cy - ey, cx + MCON + ex, cy + MCON + ey)
                if all(_gap(pad, o) >= SPACE - 1e-9 for o in others):
                    pts.append((round(cx, 3), round(cy, 3)))
                    break
    return sorted(set(pts))


def audit(lef_path, few=4):
    """Returns rows (cell, pin, n_points, spread_um) for pins with fewer than `few` points."""
    rows = []
    for name, m in sorted(macros(open(lef_path).read()).items()):
        for pin, (use, rects) in m['pins'].items():
            if use in ('POWER', 'GROUND') or not rects:
                continue
            pts = access_points(m, pin)
            if pts is None:
                continue
            spread = 0.0
            if pts:
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                spread = max(max(xs) - min(xs), max(ys) - min(ys))
            if len(pts) < few:
                rows.append((name, pin, len(pts), spread))
    return rows
