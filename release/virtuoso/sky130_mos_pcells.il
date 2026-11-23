;; sky130 MOS PCells for Virtuoso, written by sky130cad/pcell.py (port of mosgen.generate).
;; Load with: load("sky130_mos_pcells.il") after defining the library sky130_mos.

pcDefinePCell(
  list(ddGetObj("sky130_mos") "nfet_01v8" "layout" "maskLayout")
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
      funcall(R "psdm" -125 tapBot - 125 tx1 + 125 tapTop + 125)
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
    funcall(R "nsdm" -125 -125 xlen + 125 W + 125)
    
    
    foreach(p pins
      px = caddr(p) py = cadddr(p)
      net = dbMakeNet(cv car(p))
      dbCreateTerm(net car(p) "inputOutput")
      fig = dbCreateRect(cv list(cadr(p) "pin") list((px - 5) * 0.001:(py - 5) * 0.001 (px + 5) * 0.001:(py + 5) * 0.001))
      dbCreatePin(net fig car(p))
      dbCreateLabel(cv list(cadr(p) "label") px * 0.001:py * 0.001 car(p) "centerCenter" "R0" "roman" 0.05))
    t))


let((cellId cdfId)
  cellId = ddGetObj("sky130_mos" "nfet_01v8")
  when(cdfGetBaseCellCDF(cellId) cdfDeleteCDF(cdfGetBaseCellCDF(cellId)))
  cdfId = cdfCreateBaseCellCDF(cellId)
  cdfCreateParam(cdfId ?name "model" ?prompt "Model" ?type "string" ?defValue "sky130_fd_pr__nfet_01v8"
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
                'componentName "nfet_01v8" 'modelName "nfet_01v8" 'namePrefix "M"))
  cdfSaveCDF(cdfId)
  schPinListToSymbol("sky130_mos" "nfet_01v8" "symbol"
    list(nil 'ports list(list(nil 'name "D" 'direction "inputOutput") list(nil 'name "G" 'direction "input")
                         list(nil 'name "S" 'direction "inputOutput") list(nil 'name "B" 'direction "inputOutput"))))
  printf("SKY130CAD_PCELL nfet_01v8 %L\n" ddGetObj("sky130_mos" "nfet_01v8" "layout") != nil))


pcDefinePCell(
  list(ddGetObj("sky130_mos") "nfet_01v8_lvt" "layout" "maskLayout")
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
      funcall(R "psdm" -125 tapBot - 125 tx1 + 125 tapTop + 125)
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
    funcall(R "nsdm" -125 -125 xlen + 125 W + 125)
    
    funcall(R "lvtn" -180 -180 xlen + 180 W + 180)
    foreach(p pins
      px = caddr(p) py = cadddr(p)
      net = dbMakeNet(cv car(p))
      dbCreateTerm(net car(p) "inputOutput")
      fig = dbCreateRect(cv list(cadr(p) "pin") list((px - 5) * 0.001:(py - 5) * 0.001 (px + 5) * 0.001:(py + 5) * 0.001))
      dbCreatePin(net fig car(p))
      dbCreateLabel(cv list(cadr(p) "label") px * 0.001:py * 0.001 car(p) "centerCenter" "R0" "roman" 0.05))
    t))


let((cellId cdfId)
  cellId = ddGetObj("sky130_mos" "nfet_01v8_lvt")
  when(cdfGetBaseCellCDF(cellId) cdfDeleteCDF(cdfGetBaseCellCDF(cellId)))
  cdfId = cdfCreateBaseCellCDF(cellId)
  cdfCreateParam(cdfId ?name "model" ?prompt "Model" ?type "string" ?defValue "sky130_fd_pr__nfet_01v8_lvt"
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
                'componentName "nfet_01v8_lvt" 'modelName "nfet_01v8_lvt" 'namePrefix "M"))
  cdfSaveCDF(cdfId)
  schPinListToSymbol("sky130_mos" "nfet_01v8_lvt" "symbol"
    list(nil 'ports list(list(nil 'name "D" 'direction "inputOutput") list(nil 'name "G" 'direction "input")
                         list(nil 'name "S" 'direction "inputOutput") list(nil 'name "B" 'direction "inputOutput"))))
  printf("SKY130CAD_PCELL nfet_01v8_lvt %L\n" ddGetObj("sky130_mos" "nfet_01v8_lvt" "layout") != nil))


pcDefinePCell(
  list(ddGetObj("sky130_mos") "pfet_01v8" "layout" "maskLayout")
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
      funcall(R "nsdm" -125 tapBot - 125 tx1 + 125 tapTop + 125)
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
    funcall(R "psdm" -125 -125 xlen + 125 W + 125)
    funcall(R "nwell" -180 if(tap then tapBot else 0) - 180 max(xlen if(tap then tx1 else 0)) + 180 W + 180)
    
    foreach(p pins
      px = caddr(p) py = cadddr(p)
      net = dbMakeNet(cv car(p))
      dbCreateTerm(net car(p) "inputOutput")
      fig = dbCreateRect(cv list(cadr(p) "pin") list((px - 5) * 0.001:(py - 5) * 0.001 (px + 5) * 0.001:(py + 5) * 0.001))
      dbCreatePin(net fig car(p))
      dbCreateLabel(cv list(cadr(p) "label") px * 0.001:py * 0.001 car(p) "centerCenter" "R0" "roman" 0.05))
    t))


let((cellId cdfId)
  cellId = ddGetObj("sky130_mos" "pfet_01v8")
  when(cdfGetBaseCellCDF(cellId) cdfDeleteCDF(cdfGetBaseCellCDF(cellId)))
  cdfId = cdfCreateBaseCellCDF(cellId)
  cdfCreateParam(cdfId ?name "model" ?prompt "Model" ?type "string" ?defValue "sky130_fd_pr__pfet_01v8"
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
                'componentName "pfet_01v8" 'modelName "pfet_01v8" 'namePrefix "M"))
  cdfSaveCDF(cdfId)
  schPinListToSymbol("sky130_mos" "pfet_01v8" "symbol"
    list(nil 'ports list(list(nil 'name "D" 'direction "inputOutput") list(nil 'name "G" 'direction "input")
                         list(nil 'name "S" 'direction "inputOutput") list(nil 'name "B" 'direction "inputOutput"))))
  printf("SKY130CAD_PCELL pfet_01v8 %L\n" ddGetObj("sky130_mos" "pfet_01v8" "layout") != nil))


pcDefinePCell(
  list(ddGetObj("sky130_mos") "pfet_01v8_hvt" "layout" "maskLayout")
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
      funcall(R "nsdm" -125 tapBot - 125 tx1 + 125 tapTop + 125)
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
    funcall(R "psdm" -125 -125 xlen + 125 W + 125)
    funcall(R "nwell" -180 if(tap then tapBot else 0) - 180 max(xlen if(tap then tx1 else 0)) + 180 W + 180)
    funcall(R "hvtp" -180 -180 xlen + 180 W + 180)
    foreach(p pins
      px = caddr(p) py = cadddr(p)
      net = dbMakeNet(cv car(p))
      dbCreateTerm(net car(p) "inputOutput")
      fig = dbCreateRect(cv list(cadr(p) "pin") list((px - 5) * 0.001:(py - 5) * 0.001 (px + 5) * 0.001:(py + 5) * 0.001))
      dbCreatePin(net fig car(p))
      dbCreateLabel(cv list(cadr(p) "label") px * 0.001:py * 0.001 car(p) "centerCenter" "R0" "roman" 0.05))
    t))


let((cellId cdfId)
  cellId = ddGetObj("sky130_mos" "pfet_01v8_hvt")
  when(cdfGetBaseCellCDF(cellId) cdfDeleteCDF(cdfGetBaseCellCDF(cellId)))
  cdfId = cdfCreateBaseCellCDF(cellId)
  cdfCreateParam(cdfId ?name "model" ?prompt "Model" ?type "string" ?defValue "sky130_fd_pr__pfet_01v8_hvt"
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
                'componentName "pfet_01v8_hvt" 'modelName "pfet_01v8_hvt" 'namePrefix "M"))
  cdfSaveCDF(cdfId)
  schPinListToSymbol("sky130_mos" "pfet_01v8_hvt" "symbol"
    list(nil 'ports list(list(nil 'name "D" 'direction "inputOutput") list(nil 'name "G" 'direction "input")
                         list(nil 'name "S" 'direction "inputOutput") list(nil 'name "B" 'direction "inputOutput"))))
  printf("SKY130CAD_PCELL pfet_01v8_hvt %L\n" ddGetObj("sky130_mos" "pfet_01v8_hvt" "layout") != nil))
