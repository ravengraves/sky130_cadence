"""Virtuoso PCells for the sky130 1.8 V MOS devices (cf. GPDK045 nmos1v/pmos1v), written as
SKILL by this module: a port of mosgen.generate, so layouts equal the generator's.

  python3 sky130.py pcells        -> WORK/pcells/sky130_mos (OA library: layout PCells, CDF,
                                     symbols) + sky130_mos_pcells.il (the SKILL source)
  python3 sky130.py pcell-check   -> instantiate mosgen.CHECK sizes, stream out, compare every
                                     shape and label with mosgen; DRC + LVS of each

Library `sky130_mos` (attached to technology library `sky130`): cells nfet_01v8,
nfet_01v8_lvt, pfet_01v8, pfet_01v8_hvt, each with
- layout: SKILL PCell, parameters w (finger width, um), l (um), nf (fingers), tap, tie;
  terminals D G S (B unless tie) as pins with labels;
- symbol: generated from the pin list (box symbol);
- CDF: w, l, nf, tap, tie, model (hidden), m = nf; simInfo for Spectre (subcircuit
  sky130_fd_pr__<device>, terminals D G S B, w/l in um as the models scale by 1e-6) and
  auCdl (M devices, model <device>).
"""
import os
import re

from . import drc_tests, lvs, mosgen, toolenv

LIB = 'sky130_mos'

BODY = r'''
pcDefinePCell(
  list(ddGetObj("%(lib)s") "%(dev)s" "layout" "maskLayout")
  ((w float 1.0) (l float 0.15) (nf int 1) (tap boolean t) (tie boolean nil))
  let((cv snap R colf W L cols gates x width xlen n0 licY liLo liHi src drn cx a b lx strapLo strapHi
       gc gy pins bar tapTop tapBot bot barLo barHi tx1 nts ty txs tliLo mid net fig px py)
    cv = pcCellView
    snap = lambda((v) 5 * floor(v / 5.0 + 0.5))
    R = lambda((lay x0 y0 x1 y1) dbCreateRect(cv list(lay "drawing") list(x0 * 0.001:y0 * 0.001 x1 * 0.001:y1 * 0.001)))
    colf = lambda((len enc) let((n span)
        n = max(1 floor((len - 2 * enc + 170) / 340.0))
        span = n * 170 + (n - 1) * 170
        list(n funcall(snap (len - span) / 2.0))))
    W = funcall(snap w * 1000.0)
    L = funcall(snap l * 1000.0)
    cols = nil gates = nil x = 0
    for(i 0 nf
      width = if(i == 0 || i == nf then 300 else 290)
      cols = append1(cols list(x x + width))
      x = x + width
      when(i < nf gates = append1(gates list(x x + L)) x = x + L))
    xlen = x
    funcall(R "diff" 0 0 xlen W)
    n0 = funcall(colf W 40)
    licY = nil
    for(k 0 car(n0) - 1 licY = append1(licY cadr(n0) + k * 340))
    liLo = car(licY) - 85
    liHi = car(last(licY)) + 170 + 85
    src = nil drn = nil
    for(i 0 nf if(evenp(i) then src = append1(src i) else drn = append1(drn i)))
    cx = makeTable("cx" nil)
    for(i 0 nf
      a = car(nth(i cols)) b = cadr(nth(i cols))
      lx = cond((i == 0 b - funcall(snap 60.0) - 170) (i == nf a + funcall(snap 60.0)) (t a + funcall(snap (b - a - 170) / 2.0)))
      cx[i] = lx
      foreach(y licY funcall(R "licon1" lx y lx + 170 y + 170)))
    strapLo = W + 160
    strapHi = strapLo + 330
    foreach(g gates funcall(R "poly" car(g) -130 cadr(g) strapLo))
    gc = mapcar(lambda((g) funcall(snap (car(g) + cadr(g)) / 2.0 - 85)) gates)
    funcall(R "poly" min(car(gc) - 80 car(car(gates))) strapLo max(car(last(gc)) + 170 + 80 cadr(car(last(gates)))) strapHi)
    gy = strapLo + 80
    foreach(g gc funcall(R "licon1" g gy g + 170 gy + 170))
    funcall(R "npc" car(gc) - 100 gy - 100 car(last(gc)) + 170 + 100 gy + 170 + 100)
    funcall(R "li1" car(gc) - 85 gy car(last(gc)) + 170 + 85 gy + 170)
    pins = list(list("G" "li1" floor((car(gc) + car(last(gc)) + 170) / 2.0) gy + 85))
    bar = length(src) > 1 && !tie
    tapTop = if(bar then -600 else -400)
    tapBot = tapTop - 290
    bot = makeTable("bot" nil)
    for(i 0 nf bot[i] = liLo)
    when(bar
      barHi = liLo - 185
      barLo = barHi - 170
      funcall(R "li1" cx[car(src)] barLo cx[car(last(src))] + 170 barHi)
      foreach(i src bot[i] = barLo))
    tx1 = max(xlen 410)
    when(tap
      funcall(R "tap" 0 tapBot tx1 tapTop)
      nts = funcall(colf tx1 120)
      ty = tapBot + funcall(snap 60.0)
      txs = nil
      for(k 0 car(nts) - 1 txs = append1(txs cadr(nts) + k * 340))
      foreach(t1 txs funcall(R "licon1" t1 ty t1 + 170 ty + 170))
      tliLo = ty
      funcall(R "li1" min(car(txs) - 85 cx[0]) tliLo max(car(last(txs)) + 170 + 85 cx[nf] + 170) ty + 170)
      unless(tie pins = append1(pins list("B" "li1" floor((car(txs) + car(last(txs)) + 170) / 2.0) ty + 85)))
      funcall(R "%(impt)s" -125 tapBot - 125 tx1 + 125 tapTop + 125)
      when(tie foreach(i src bot[i] = tliLo)))
    for(i 0 nf funcall(R "li1" cx[i] bot[i] cx[i] + 170 liHi))
    mid = funcall(snap (liLo + liHi) / 2.0 - 85)
    pins = append1(pins list("S" "li1" cx[car(src)] + 85 mid + 85))
    if(length(drn) > 1 then
      foreach(i drn funcall(R "mcon" cx[i] mid cx[i] + 170 mid + 170))
      funcall(R "met1" cx[car(drn)] - 60 mid - 30 cx[car(last(drn))] + 170 + 60 mid + 170 + 30)
      pins = append1(pins list("D" "met1" floor((cx[car(drn)] + cx[car(last(drn))] + 170) / 2.0) mid + 85))
    else
      pins = append1(pins list("D" "li1" cx[car(drn)] + 85 mid + 85)))
    funcall(R "%(impd)s" -125 -125 xlen + 125 W + 125)
    %(well)s
    %(vt)s
    foreach(p pins
      px = caddr(p) py = cadddr(p)
      net = dbMakeNet(cv car(p))
      dbCreateTerm(net car(p) "inputOutput")
      fig = dbCreateRect(cv list(cadr(p) "pin") list((px - 5) * 0.001:(py - 5) * 0.001 (px + 5) * 0.001:(py + 5) * 0.001))
      dbCreatePin(net fig car(p))
      dbCreateLabel(cv list(cadr(p) "label") px * 0.001:py * 0.001 car(p) "centerCenter" "R0" "roman" 0.05))
    t))
'''

CDF = r'''
let((cellId cdfId)
  cellId = ddGetObj("%(lib)s" "%(dev)s")
  when(cdfGetBaseCellCDF(cellId) cdfDeleteCDF(cdfGetBaseCellCDF(cellId)))
  cdfId = cdfCreateBaseCellCDF(cellId)
  cdfCreateParam(cdfId ?name "model" ?prompt "Model" ?type "string" ?defValue "sky130_fd_pr__%(dev)s"
                 ?display "nil" ?editable "nil")
  cdfCreateParam(cdfId ?name "w" ?prompt "Finger width (um)" ?type "float" ?defValue 1.0)
  cdfCreateParam(cdfId ?name "l" ?prompt "Length (um)" ?type "float" ?defValue 0.15)
  cdfCreateParam(cdfId ?name "nf" ?prompt "Fingers" ?type "int" ?defValue 1)
  cdfCreateParam(cdfId ?name "m" ?prompt "Multiplier (= fingers)" ?type "string" ?defValue "iPar(\"nf\")"
                 ?parseAsNumber "yes" ?parseAsCEL "yes" ?display "nil")
  cdfCreateParam(cdfId ?name "tap" ?prompt "Body tap" ?type "boolean" ?defValue t)
  cdfCreateParam(cdfId ?name "tie" ?prompt "Body tied to source" ?type "boolean" ?defValue nil)
  cdfId->simInfo = list(nil
    'spectre list(nil 'termOrder '(D G S B) 'instParameters '(w l m) 'otherParameters '(model)
                  'componentName nil 'modelName nil)
    'auCdl list(nil 'netlistProcedure 'ansCdlCompPrim 'termOrder '(D G S B) 'instParameters '(w l m)
                'componentName "%(dev)s" 'modelName "%(dev)s" 'namePrefix "M"))
  cdfSaveCDF(cdfId)
  schPinListToSymbol("%(lib)s" "%(dev)s" "symbol"
    list(nil 'ports list(list(nil 'name "D" 'direction "inputOutput") list(nil 'name "G" 'direction "input")
                         list(nil 'name "S" 'direction "inputOutput") list(nil 'name "B" 'direction "inputOutput"))))
  printf("SKY130CAD_PCELL %(dev)s %%L\n" ddGetObj("%(lib)s" "%(dev)s" "layout") != nil))
'''


def skill(lib_dir):
    parts = [';; sky130 MOS PCells for Virtuoso, written by sky130cad/pcell.py (port of mosgen.generate).',
             ';; Load with: load("sky130_mos_pcells.il") after defining the library %s.' % LIB]
    for dev, (impd, impt, nwell, vt) in mosgen.DEVICES.items():
        well = ('funcall(R "nwell" -180 if(tap then tapBot else 0) - 180 max(xlen if(tap then tx1 else 0)) + 180 W + 180)'
                if nwell else '')
        vtl = 'funcall(R "%s" -180 -180 xlen + 180 W + 180)' % vt if vt else ''
        parts.append(BODY % {'lib': LIB, 'dev': dev, 'impd': impd, 'impt': impt, 'well': well, 'vt': vtl})
        parts.append(CDF % {'lib': LIB, 'dev': dev})
    return '\n'.join(parts)


def build(work, env=None):
    """Create WORK/pcells/sky130_mos in batch Virtuoso. Returns (devices created, log path)."""
    d = os.path.join(work, 'pcells')
    os.makedirs(d, exist_ok=True)
    tech = os.path.join(work, 'upstream', 'sky130_cds', 'VirtuosoOA', 'sky130')
    open(os.path.join(d, 'cds.lib'), 'w').write('SOFTINCLUDE $CDS_INST_DIR/share/cdssetup/cds.lib\nDEFINE sky130 %s\n' % tech)
    open(os.path.join(d, 'sky130_mos_pcells.il'), 'w').write(skill(os.path.join(d, LIB)))
    open(os.path.join(d, 'build.il'), 'w').write(
        'ddCreateLib("%s" "%s")\ntechBindTechFile(ddGetObj("%s") "sky130")\n'
        'foreach(c list("schView" "selectSv") when(isFile(prependInstallPath(sprintf(nil "etc/context/%%s.cxt" c)))\n'
        '  loadContext(prependInstallPath(sprintf(nil "etc/context/%%s.cxt" c))) callInitProc(c)))\n'
        'load("sky130_mos_pcells.il")\nexit()\n' % (LIB, os.path.join(d, LIB), LIB))
    open(os.path.join(d, 'cds.lib'), 'a').write('DEFINE %s %s\n' % (LIB, os.path.join(d, LIB)))
    toolenv.run(['virtuoso', '-nograph', '-replay', 'build.il', '-log', 'build.log'], d, os.path.join(d, 'build.out'), env, 1200)
    log = open(os.path.join(d, 'build.log')).read() if os.path.exists(os.path.join(d, 'build.log')) else ''
    made = set(re.findall(r'^\\o SKY130CAD_PCELL (\w+) t\b', log, re.M)) | set(re.findall(r'^SKY130CAD_PCELL (\w+) t\b', log, re.M))
    return made, os.path.join(d, 'build.log')


# ---------------------------------------------------------------- check

def gds_shapes(path):
    """{(layer, datatype, x0, y0, x1, y1)} rectangles and {(layer, texttype, x, y, text)} labels, nm."""
    import struct
    data = open(path, 'rb').read()
    i, rects, texts, kind, ln, dt, xy = 0, set(), set(), None, None, None, None
    units = 1.0
    while i + 4 <= len(data):
        n, rt, _ = struct.unpack('>HBB', data[i:i + 4])
        body = data[i + 4:i + n]
        i += n
        if n < 4:
            break
        if rt == 0x03:
            # db unit in metres -> nm factor
            uu = drc_tests_real8(body[8:16])
            units = uu / 1e-9
        elif rt in (0x08, 0x0C):
            kind = rt
        elif rt == 0x0D:
            ln = struct.unpack('>h', body)[0]
        elif rt in (0x0E, 0x16):
            dt = struct.unpack('>h', body)[0]
        elif rt == 0x10:
            xy = struct.unpack('>%di' % (len(body) // 4), body)
        elif rt == 0x19:
            texts.add((ln, dt, round(xy[0] * units), round(xy[1] * units), body.rstrip(b'\0').decode()))
        elif rt == 0x11 and kind == 0x08 and xy:
            xs, ys = xy[0::2], xy[1::2]
            rects.add((ln, dt, round(min(xs) * units), round(min(ys) * units), round(max(xs) * units),
                       round(max(ys) * units)))
            kind = None
    return rects, texts


def drc_tests_real8(b):
    sign = -1 if b[0] & 0x80 else 1
    exp = (b[0] & 0x7F) - 64
    mant = int.from_bytes(b[1:8], 'big') / float(1 << 56)
    return sign * mant * 16.0 ** exp


INST = '''let((cv ok)
  cv = dbOpenCellViewByType("pcell_test" "%(name)s" "layout" "maskLayout" "w")
  ok = dbCreateParamInstByMasterName(cv "%(lib)s" "%(dev)s" "layout" "I0" 0:0 "R0" 1
         list(list("w" "float" %(w)g) list("l" "float" %(l)g) list("nf" "int" %(nf)d)
              list("tap" "boolean" %(tap)s) list("tie" "boolean" %(tie)s)))
  printf("SKY130CAD_INST %(name)s %%L\\n" ok != nil)
  dbSave(cv) dbClose(cv))
'''


def check(work, env=None):
    """Returns rows (name, instantiated, geometry equal to mosgen, DRC results, LVS)."""
    import collections
    import shutil
    d = os.path.join(work, 'pcells')
    t = os.path.join(d, 'check')
    shutil.rmtree(t, ignore_errors=True)
    os.makedirs(os.path.join(t, 'gds'))
    tech = os.path.join(work, 'upstream', 'sky130_cds', 'VirtuosoOA', 'sky130')
    lmap = os.path.join(work, 'upstream', 'sky130_cds', 'VirtuosoOA', 'layer.map')
    open(os.path.join(t, 'cds.lib'), 'w').write('DEFINE sky130 %s\nDEFINE %s %s\nDEFINE pcell_test %s\n'
                                                % (tech, LIB, os.path.join(d, LIB), os.path.join(t, 'pcell_test')))
    cmds = ['ddCreateLib("pcell_test" "%s")' % os.path.join(t, 'pcell_test'),
            'techBindTechFile(ddGetObj("pcell_test") "sky130")']
    names = []
    for dev, w, l, nf, tap, tie in mosgen.CHECK:
        name = mosgen.generate(dev, w, l, nf, tap, tie)[0]
        names.append((name, dev, w, l, nf, tap, tie))
        cmds.append(INST % {'name': name, 'lib': LIB, 'dev': dev, 'w': w, 'l': l, 'nf': nf,
                            'tap': 't' if tap else 'nil', 'tie': 't' if tie else 'nil'})
    open(os.path.join(t, 'inst.il'), 'w').write('\n'.join(cmds) + '\nexit()\n')
    toolenv.run(['virtuoso', '-nograph', '-replay', 'inst.il', '-log', 'inst.log'], t, os.path.join(t, 'inst.out'), env, 1200)
    log = open(os.path.join(t, 'inst.log')).read() if os.path.exists(os.path.join(t, 'inst.log')) else ''
    made = set(re.findall(r'SKY130CAD_INST (\w+) t\b', log))
    deck = os.path.join(work, 'drc', 'sky130_full.pvl')
    lvs_deck = lvs.deck_path(work)
    rows = []
    for name, dev, w, l, nf, tap, tie in names:
        gds = os.path.join(t, 'gds', name + '.gds')
        toolenv.run(['strmout', '-library', 'pcell_test', '-topCell', name, '-view', 'layout', '-strmFile', gds,
                     '-layerMap', lmap, '-flattenPcells', '-logFile', gds + '.log'], t, gds + '.out', env, 600)
        if not os.path.exists(gds):
            rows.append((name, name in made, 'no GDS', None, None))
            continue
        ref = os.path.join(t, 'gds', name + '_mosgen.gds')
        nm, S, Lb, p = mosgen.generate(dev, w, l, nf, tap, tie)
        mosgen.write_gds(ref, [(nm, S, Lb)])
        r1, t1 = gds_shapes(gds)
        r2, t2 = gds_shapes(ref)
        same = (r1 == r2 and t1 == t2)
        diff = '' if same else 'rects +%d -%d, labels +%d -%d' % (len(r1 - r2), len(r2 - r1), len(t1 - t2), len(t2 - t1))
        dd = os.path.join(t, 'drc', name)
        os.makedirs(dd, exist_ok=True)
        toolenv.run(['pegasus', '-drc', '-dp', '4', '-gds', gds, '-top_cell', name, deck], dd, os.path.join(dd, 'peg.out'),
                    env, 600)
        rpt = os.path.join(dd, 'sky130_full.drc_errors.ascii')
        ndrc = collections.Counter(e[0] for e in drc_tests.read_errors(rpt)) if os.path.exists(rpt) else None
        res = None
        if tap:
            cdl = os.path.join(t, name + '.cdl')
            open(cdl, 'w').write(mosgen.netlists(name, p)[0])
            res = lvs.run(gds, name, cdl, os.path.join(t, 'lvs', name), lvs_deck, env)[0]
        rows.append((name, name in made, 'equal' if same else diff, ndrc, res))
    return rows
