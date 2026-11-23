# Virtuoso layout, Spectre simulation and cell abstracts for sky130

This guide covers custom layout and simulation with the files in `release/`. The paths below
are relative to `release/`.

| Task | Files |
|---|---|
| Layout | `virtuoso/sky130/`: Virtuoso technology library (layers, display, vias). From sky130_cds, Apache-2.0. |
| GDS export | `virtuoso/layer.map` |
| DRC | `pegasus/sky130_full.pvl` |
| LVS | `pegasus/sky130_lvs.pvl` |
| Simulation | `spectre/models/`, `spectre/netlists/` |
| Characterization | `python3 sky130.py characterize` (repository scripts) |
| Cell LEF | `abstract/`: layer map, replay example |

| Transistors | `virtuoso/sky130_mos/`: PCells `nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8`, `pfet_01v8_hvt` with CDF and symbols |
| Standard cells | `library/oa/sky130_fd_sc_hs/`: layout views of all 390 cells |

**Not included:** resistor, capacitor, diode and bipolar devices (digital MOS only).
- **Optional private setup:** `python3 sky130.py download --cornell` fetches the Cornell
  `sky130_fd_pr_main` PCell library for private use. That library has no license, so it is
  not redistributed.

## 1. Set up

```sh
source /path/to/cadence/setup.sh
mkdir -p ~/sky130_layout && cd ~/sky130_layout
cat > cds.lib <<EOF
SOFTINCLUDE \$CDS_INST_DIR/share/cdssetup/cds.lib
DEFINE sky130 /path/to/release/virtuoso/sky130
DEFINE mylib ./mylib
EOF
virtuoso &
```

Create `mylib`: File → New → Library, then choose "Attach to an existing technology
library" → `sky130`.

To check the technology library in batch:

```sh
cat > check.il <<'EOF'
tf = techGetTechFile(ddGetObj("sky130"))
printf("layers %d vias %d\n" length(tf~>layers) length(tf~>viaDefs))
exit()
EOF
virtuoso -nograph -replay check.il -log check.log
```

## 2. Transistors

### PCells in Virtuoso

`virtuoso/cds.lib` defines `sky130_mos`. Place `sky130_mos` / `nfet_01v8` (or another device) /
`layout` and set its parameters:

| Parameter | Meaning |
|---|---|
| `w` | Finger width, in µm |
| `l` | Length, in µm |
| `nf` | Fingers |
| `tap` | Add a body tap |
| `tie` | Join the body to the source |

**Geometry:** the same as `python3 sky130.py mos` makes. `pcell-check` streams 12 instances
out and compares every shape and label with the generator.

**Schematics:** use the `symbol` view.
- **Spectre:** ADE netlists an instance as `sky130_fd_pr__<device>` with `w`, `l` in µm
  and `m` = fingers. Include `spectre/models/sky130_digital_<corner>.spice` as a model file.
- **CDL:** the device is netlisted as `M… <device>`.

### Generate them as GDS

`sky130cad/mosgen.py` writes a DRC-clean transistor as GDS, with a CDL netlist for LVS and a
Spectre subcircuit. It needs only Python:

```sh
python3 sky130.py mos --device pfet_01v8 --w 1.0 --l 0.15 --nf 2 --out mos/
# -> mos/pfet_01v8_w1_l0p15_nf2.gds, .cdl, .spice
```

Options:

| Option | Meaning |
|---|---|
| `--device` | `nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8` or `pfet_01v8_hvt` |
| `--w` | Width per finger, in µm |
| `--l` | Gate length, in µm |
| `--nf` | Number of fingers |
| `--tie` | Join the body to the source |
| `--no-tap` | Leave out the body tap |

What the layout contains:
- **Pins:** `D`, `G`, `S`, `B` as li1 labels. With two or more drain columns, `D` is on met1.
- **Gates:** joined by a poly strap with li1 on top.
- **Body tap:** the tap sits below the diffusion; pfets get an n-well around both.
- **Size check:** W and L are checked against the model bins when the models are downloaded.

`release/mos/` has twelve examples. To use one in Virtuoso, stream it in (File → Import →
Stream, layer map `virtuoso/layer.map`) and instantiate it, or copy its shapes.

**Validation:** `python3 sky130.py mos-check` builds those twelve and checks each one:
- **DRC:** 0 results with `sky130_full.pvl`.
- **Simulation:** Spectre finds a model bin and an operating point at 1.8 V.
- **LVS:** MATCH with `pegasus/sky130_lvs.pvl` for every transistor with a tap.
- **Private cross-check:** when the Cornell files are downloaded, the Cornell DRC deck also
  runs. That deck checks `poly.7`/`poly.8`, which ours lacks; the generator meets those
  rules by construction.

### Draw them by hand

These are the layers (purpose `drawing`) and GDS numbers:

| Layer | GDS | Use |
|---|---|---|
| `nwell` | 64/20 | Well for PMOS |
| `diff` | 65/20 | Transistor active area |
| `tap` | 65/44 | Well and substrate contacts |
| `poly` | 66/20 | Gate |
| `licon1` | 66/44 | Contact from diff, tap or poly to li1 |
| `npc` | 95/20 | Required around poly contacts |
| `nsdm` | 93/44 | N+ implant |
| `psdm` | 94/20 | P+ implant |
| `lvtn` | 125/44 | Low-Vt implant |
| `hvtp` | 78/44 | High-Vt PMOS implant |
| `li1` | 67/20 | Local interconnect |
| `mcon` | 67/44 | Via from li1 to met1 |
| `met1` | 68/20 | Metal 1 |
| `via` | 68/44 | Via from met1 to met2 |
| `met2` | 69/20 | Metal 2 |

**Devices.** The transistor type is set by the layers that overlap the gate. W is the
`diff` width under the `poly`, and L is the `poly` width (0.15 µm minimum).

| Device | Gate layers |
|---|---|
| `nfet_01v8` | `diff` ∩ `poly` in `nsdm`, outside `nwell` |
| `nfet_01v8_lvt` | as nfet, plus `lvtn` |
| `pfet_01v8` | `diff` ∩ `poly` in `psdm`, inside `nwell` |
| `pfet_01v8_hvt` | as pfet, plus `hvtp` |

**Minimum sizes and spacings** (µm). The rule names are SkyWater's. "Deck" marks the rules
`pegasus/sky130_full.pvl` checks; `sky130cad/drc_deck.py` lists all of its checks.

| Rule | Value | Deck |
|---|---|---|
| difftap.1: diff width | 0.15 | yes |
| difftap.3: diff spacing | 0.27 | yes |
| W (diff under the gate) | ≥ 0.42 (smallest W in the models) | no |
| poly.1a / poly.2: poly width / spacing | 0.15 / 0.21 | yes |
| poly.8: poly extension past diff (endcap) | 0.13 | no |
| poly.7: diff extension past poly | 0.25 | no |
| licon.1 / licon.2: licon size / spacing | 0.17 × 0.17 / 0.17 | yes |
| licon.5: diff enclosure of licon | 0.04 | yes |
| licon.8: poly enclosure of licon | 0.05 | yes |
| licon.11a: diff licon to gate (std-cell value) | 0.05 | yes |
| licon.15: npc enclosure of poly licon | 0.1 | yes |
| licon.9: poly licon to psdm (no overlap) | 0.11 | yes |
| li.1 / li.3: li1 width / spacing | 0.17 / 0.17 | yes |
| li.5: li1 enclosure of licon on one of two adjacent edges | 0.08 | yes |
| n/psd.5a/5b: implant enclosure of diff/tap | 0.125, except where diff butts a tap of the opposite type | yes |
| nsdm/psdm width / spacing | 0.38 / 0.38 | yes |
| nsd.10a / psd.10b: implant area | 0.265 / 0.255 µm² | yes |
| difftap.8: nwell enclosure of p-diff | 0.18 | yes |
| difftap.9: nwell spacing to n-diff | 0.34 | yes |

**Contacts and taps.** Contact every source/drain region that has a gate on only one side.
A region between two series gates may stay uncontacted. Every n-well needs a contacted
n+ `tap` (in `nsdm`), and every tap needs a contact.

The fastest start is to copy a standard cell. Stream in a cell's GDS from `tech/gds/`
(File → Import → Stream, layer map `virtuoso/layer.map`). It shows a DRC-clean arrangement
of these layers.

## 3. Export GDS, run DRC and LVS

```sh
strmout -library mylib -topCell mycell -view layout -strmFile mycell.gds \
        -layerMap /path/to/release/virtuoso/layer.map
pegasus -drc -dp 4 -gds mycell.gds -top_cell mycell /path/to/release/pegasus/sky130_full.pvl
```

Results are in `result.sum` and `sky130_full.drc_errors.ascii`. Load them in Virtuoso with
Pegasus → DRC debug, or read the ASCII report. Every check's caption gives the SkyWater rule
number and value.

**Rules a standalone cell may fail:**
- `nwell.4` (n-well without a contacted tap) and implant minimum area apply to the whole
  block.
- Standard cells rely on tap cells and neighbouring cells for these, so they report them
  when checked alone.
- Check a cell with a tap next to it, or in a placed block.

**LVS:**

```sh
pegasus -lvs -gds mycell.gds -top_cell mycell -source_cdl mycell.cdl -source_top_cell mycell \
        /path/to/release/pegasus/sky130_lvs.pvl
```

- **Source netlist:** start the CDL with `*.SCALE MICRON`, and give W/L in µm.
- **Device names:** `nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8`, `pfet_01v8_lvt`,
  `pfet_01v8_hvt`.
- **Labels:** pin text on the `label` purpose (e.g. li1 67/5, met1 68/5). The body labels go
  on the wells: `VPB` on nwell (64/5), `VNB` on pwell (64/59).
- **From the repository:** `python3 sky130.py lvs mycell.gds mycell mycell.cdl` does the
  same and prints a summary.

**Deck tests:** `pegasus/tests/drc_tests.gds` holds 185 small layouts. Each layout either
violates one rule or is legal, and `drc_tests_cases.tsv` lists the expected result. Run the
deck on it to see what each rule catches.

## 4. Simulate with Spectre

```sh
cd release/spectre
spectre inverter_ss.scs        # inv_1 at SS / 150 C / 1.6 V -> inverter_ss.measure:
                               # tpd_fall 68 ps, tpd_rise 99 ps (validation run)
```

In your own netlists:

```spice
simulator lang=spice
.include "/path/to/release/spectre/models/sky130_digital_tt.spice"   * tt ss ff sf fs
.include "/path/to/release/spectre/netlists/sky130_fd_sc_hs__nand2_1.spice"
xm1 d g s b sky130_fd_pr__nfet_01v8 w=0.65 l=0.15     * sizes in microns
```

**Models:**
- The model files hold the 1.8 V digital devices: `nfet_01v8`, `nfet_01v8_lvt`,
  `pfet_01v8` and `pfet_01v8_hvt`.
- They come from SkyWater's `sky130_fd_pr`, with the subcircuit parameters rearranged so
  Spectre reads them (`patches/spectre-models.patch`).
- `.option scale=1.0u` is set, so W and L are in microns.

**Netlists:** `spectre/netlists/` has every `sky130_fd_sc_hs` cell. Pin order follows each
`.subckt` line, e.g. `A VGND VNB VPB VPWR Y`.

## 5. Optimizing a standard cell

A cell's delay is about R x (C_self + C_load). R is the channel resistance of the driving
transistors (set by W/L); C_self is the cell's own drain-diffusion and internal-wiring capacitance;
C_load is the next cells' input capacitance plus wire. Widening transistors lowers R but raises
both the cell's input capacitance (which slows the previous cell) and its own C_self, so the aim is
**more drive per unit capacitance**:

- **Simple gates (inv, nand2/3/4):** the pull-up is the weak side (rise R is 1.4-1.7x fall R at
  SS -40 C). Prefer fewer, wider fingers (>= 1.0 um nfet, ~1.5 um pfet): in Spectre, the same P/N
  ratio built from 1.0 um instead of 0.74 um fingers is about 8 % faster at equal loading, because
  narrow devices have less drive per um. Share the output drain between finger pairs, keep source/
  drain at the minimum length (0.29 um) and the output li1 strap short; no met1 inside the cell.
- **Series stacks (nand3/nand4):** widen the stacked nfets; leave the series nodes as minimum
  diffusion without contacts.
- **Two-stage cells (and2, buf) and flip-flops:** their delay is mostly intrinsic (zero-load):
  minimise internal-node capacitance (short internal wiring, small internal stages) and spend width
  only on the output stage. Layout parasitics add about 30 % to the dfxtp clock-to-Q.
- Keep the 3.33 um height, 0.48 um site, rails and pin positions, and check the result with
  `python3 sky130.py pin-access` so the router can still reach every pin.

**Measuring a change:** characterize the original and the modified cell from their extracted
layouts with the same flow, then compare them with

```sh
python3 sky130.py cell-rc --cells nand2_2 --lib characterization/<run>/charlib_...lib
```

which prints per arc the input capacitance, rise/fall drive resistance, zero-load delay and an FO4
delay. The release Liberty gives the reference values, e.g. at SS -40 C: nand2_2 A->Y Cin 5.1 fF,
R 5.4/3.7 kOhm, t0 71/45 ps, FO4 151 ps; dfxtp_2 CLK->Q t0 350/379 ps.

## 6. Characterize and abstract a custom cell

From the repository:

```sh
python3 sky130.py characterize --cells mycell ...    # Spectre sweeps -> Liberty (see sky130cad/charlib.py)
python3 sky130.py abstract --cells mycell --liberty mycell.lib   # GDS -> LEF with Abstract
```

**Characterization:**
- **Output:** delay and transition tables, input capacitance, and setup/hold for flip-flops.
- **Accuracy:** schematic netlists come out 15–33 % faster than the shipped tables. Extracted
  netlists come within about 10 %.
- **Extraction:** `python3 sky130.py extract` runs Pegasus LVS with `pegasus/sky130_lvs.pvl`
  and then Quantus; `spectre/extracted/` holds the result for every library cell.
- **Comparison:** compare a custom cell against library cells characterized by the same
  flow (`characterization/` in the release).

**Abstract:** `abstract/abs.replay.example` shows the batch replay for `inv_1`:
- Liberty pin directions are read with `ImportLIBFiles` and `ImportLogicalFiles`.
- The pin map is `abstract/layers.map`.

The generated LEF matches the shipped LEF in pins, OBS, SIZE, SITE and CLASS.
`abstract/fdsc_abstract.lef` is the result for `inv_1`, `mux2_1` and `dfxtp_1`.
