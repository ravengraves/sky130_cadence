# sky130 for Cadence

Scripts that turn SkyWater's open sky130 standard cells (`sky130_fd_sc_hs`, the "Google" library)
into a working Cadence setup: Liberty, LEF, GDS, Genus/Innovus setup, Pegasus DRC and LVS decks,
Spectre models, Spectre characterization, Quantus extraction, Abstract Generator LEF, and
Virtuoso transistor layouts.

- **Ready-to-use files:** `release/` holds the generated Cadence files, with relative paths,
  licenses and checksums (see [Release](#release)).
- **Guides:** [docs/genus.md](docs/genus.md), [docs/innovus.md](docs/innovus.md),
  [docs/virtuoso.md](docs/virtuoso.md).
- **Scripts:** the Python in `sky130cad/` regenerates everything. Downloads and intermediate
  files go to a work directory (`--work`, `$SKY130_WORK`, default `~/sky130_work`).

## Requirements

- Python 3.8+ and git (standard library only; no pip packages).
- Cadence tools on `PATH` through `$SKY130_TOOL_ENV`, a shell snippet. Validated with Pegasus
  25.1, Spectre 25.1, Genus 25.1, Innovus 20.16, Virtuoso/Abstract IC25.1 and Quantus 25.1.
- Innovus 20.x needs an older OpenAccess than Virtuoso 25.x. Set it for Innovus only, because a
  global `OA_HOME` makes Abstract crash ("symbol lookup error ... liboaPrivateCDS.so"):

```sh
export SKY130_TOOL_ENV='source /opt/cadence/setup.sh'                 # your site's setup
export SKY130_ENV_INNOVUS='export OA_HOME=/opt/cadence/INNOVUS201/oa_v22.60.057'
export SKY130_WORK=~/sky130_work
```

- The QRC technology file comes from Oklahoma State's `sky130_cds` (Apache-2.0).
  `download` fetches it and checks its SHA-256; `convert --qrc FILE` uses another one.

## Quick start

```sh
python3 sky130.py download                  # GitHub access needed (or --fdsc-from/--fdpr-from/--cds-from/--cornell-from DIR)
python3 sky130.py convert
python3 sky130.py cadence-setup
python3 sky130.py drc-deck && python3 sky130.py lvs-deck && python3 sky130.py spectre-models
python3 sky130.py smoke                     # Genus -> Innovus -> Pegasus on a small design
python3 sky130.py all                       # every step, including the checks below
python3 sky130.py release                   # -> release/ (publishable files only)
python3 sky130.py release-check             # run the tools on release/ as published
python3 -m unittest discover -s tests       # offline tests, no Cadence needed
```

`python3 sky130.py --help` lists every step; each module in `sky130cad/` explains what it does
and why in its docstring.

| Step | Output | Validated (2026-11-17, on a fresh work directory) |
|---|---|---|
| `download` | `upstream/` sparse checkouts at pinned commits | 62 s; files byte-identical to full checkouts |
| `convert` | `tech/` | identical to the files used in production place-and-route |
| `patches` | `patches/*.patch` | every change to upstream files, as diffs |
| `cadence-setup` | `cadence/*.tcl` | used by `smoke` |
| `drc-deck`, `drc-validate` | `drc/sky130_full.pvl` | 185/185 test cases; 390/390 cells clean (block-level rules aside) |
| `lvs-deck`, `lvs-check` | `lvs/sky130_lvs.pvl` (own deck) | 390/390 cells match |
| `spectre-models`, `characterize` | `spectre/models`, `char/<corner>/` | see [Characterization](#characterization) |
| `extract` | `quantus/netlists/` | 3/3 cells: LVS match, RC netlists |
| `abstract` | `abstract/fdsc_abstract.lef` | pins and OBS identical to the shipped LEF |
| `virtuoso-setup`, `xtor-check` | `virtuoso/cds.lib` | 6/6 transistor PCells: DRC clean, LVS match |
| `smoke` | `smoke/` | Innovus DRC/connectivity clean; 0 Pegasus results |
| `mos`, `mos-check` | `mos/<cell>.gds/.cdl/.spice` | 12/12 transistors: 0 DRC results, Spectre operating point; LVS match (private check) |
| `antenna-deck`, `antenna-validate`, `antenna` | `drc/sky130_antenna.pvl` | 5/5 antenna test layouts; 0 results on the smoke layout |
| `pin-access` | report | every signal pin reachable from met1 (xor3_1 B: 0 → 306 points after the cell fix, like other cells' pins) |
| `cell-rc --cells ...` | report | input C, drive R, intrinsic delay, FO4 per arc (compare cell versions) |
| `library` | `library/`: CDL, merged GDS, Verilog models, OA library (layout + symbol views) | 390 cells; Verilog compiles (iverilog); strmin 0 errors |
| `pcells`, `pcell-check` | `pcells/sky130_mos` (Virtuoso PCells, CDF, symbols) | 12/12 instances equal to `mos`, DRC clean, LVS match |
| `download --osu`, `osu-check [--patch]` | `upstream/sky130_osu_sc_t18`, `osu_check*/` | OSU 18T cells with our decks: patched cells abut with 0 DRC results (352 before); LVS 61/63 |
| `ccs-libs` | `tech/ccs/*.lib` (CCS noise) | 3 corners; Genus reads all 376 cells |
| `release`, `release-check` | `release/`, `release_check/` | see [Release](#release) |

## Work directory layout

```
upstream/   sky130_fd_sc_hs, sky130_fd_pr, sky130_cds (QRC file, Virtuoso tech library),
            cornell_sky130_pdk (Virtuoso PCells, decks), lvs/
tech/       sky130_fd_sc_hs__<corner>.lib (5 corners; release: .lib.gz), sky130_fd_sc_hs.tlef,
            sky130_fd_sc_hs_innovus.tlef, sky130_fd_sc_hs_cells.lef, gds/, streamOut.map,
            extraction.layermap, qrcTechFile
cadence/    genus_fdsc.tcl, innovus_fdsc.tcl, mmmc_fdsc.tcl
drc/        sky130_full.pvl (Pegasus DRC), validate/, runs/
lvs/        sky130_lvs.pvl (Pegasus LVS), runs/
spectre/    models/sky130_digital_<tt|ss|ff|sf|fs>.spice, netlists/
char/       <corner>/charlib_*.lib, compare.txt
quantus/    sky130_pex.pvl, netlists/, <cell>/ (layer_setup, tech_cmd, extract.ccl)
abstract/   fdsc_abstract.lef, abs.replay, layers.map
virtuoso/   cds.lib, xtor_check/
patches/    *.patch
smoke/      example design, scripts, netlists, smoke.gds, reports
```

## Using the files

Paths below are relative to the work directory (or the snapshot directory).

### Genus

```tcl
source cadence/genus_fdsc.tcl
fdsc_read_libs ss_150C_1v60       ;# or tt_025C_1v80_ccsnoise, ff_n40C_1v95_ccsnoise, ...
read_hdl -language v2001 my.v
elaborate my_top
fdsc_dont_use                     ;# latches, scan/async flops, tristates, delay cells, fah*
read_sdc my.sdc
syn_generic; syn_map; syn_opt
write_hdl > my_netlist.v
```

### Innovus

`smoke/innovus.tcl` is a complete, tested example. The essentials:

```tcl
source cadence/innovus_fdsc.tcl
set fdsc_sdc my.sdc                          ;# read by mmmc_fdsc.tcl
set init_verilog my_netlist.v
set init_lef_file $fdsc_init_lef_file        ;# patched tech LEF + cell LEF
set init_top_cell my_top
set init_pwr_net vdd
set init_gnd_net gnd
set init_mmmc_file cadence/mmmc_fdsc.tcl     ;# SS 150 C, SS -40 C, TT 25 C setup; FF -40 C hold
init_design
fdsc_route_settings; fdsc_dont_use; fdsc_connect_power
fdsc_floorplan 0.45 12                       ;# site "unit"; keep utilization <= ~0.5
fdsc_power_grid; fdsc_welltaps; fdsc_connect_power
place_opt_design
fdsc_ties; fdsc_connect_power; fdsc_sroute
fdsc_cts_settings; ccopt_design; fdsc_post_cts_settings
optDesign -postCTS -hold
fdsc_antenna; routeDesign -globalDetail
fdsc_post_route_settings                     ;# OCV analysis + QRC extraction (IMPOPT-6080 otherwise)
optDesign -postRoute -setup -hold
fdsc_fillers; fdsc_connect_power
fdsc_stream_out my_top.gds my_top            ;# merges the cell GDS
```

Notes from real runs:
- `li1` is LEF routing layer 1, so met1..met5 are layers 2..6.
- Power pins: `VPWR`/`VPB` to `vdd`, `VGND`/`VNB` to `gnd`.
- Well taps every 13 µm.
- Keep the post-CTS `optDesign` useful skew off: with it on, long clock-buffer chains moved
  output registers' clocks by about 7 ns.
- Full adders `fah*` are don't-use because they failed legalization.
- High utilization (60 %) left cells unplaced; 45–50 % works.

### DRC (Pegasus)

```sh
pegasus -drc -dp 4 -gds my_top.gds -top_cell my_top drc/sky130_full.pvl   # or: python3 sky130.py drc my_top.gds my_top
```

- **Coverage:** `sky130_full.pvl` has 127 checks. The base set (110 checks) merges the
  efabless and open_pdks KLayout decks: widths, spacings, enclosures, areas, holes,
  wide-metal spacing, cut sizes, grid and angles. Seventeen more checks come from SkyWater's
  periphery rules:
  - n-well taps (`nwell.4`);
  - implants (`n/psd.5a`, `.5b`, `.7`, `.8`, `.9`, `.10a/.10b`, `.11`);
  - contact placement (`licon.9`, `.15`, `.16`, `.18`).
- **Block-level rules:** `nwell.4` and implant area apply to whole blocks. Standalone cells
  fail them, because their taps and implant neighbours come from other cells. `drc-validate`
  reports them separately; on placed blocks (`smoke`) they must be clean.
- **Not covered:**
  - `licon.12` (SkyWater marks it NC, not checked);
  - poly endcap and diffusion extension (`poly.7`, `poly.8`);
  - density, antenna and latch-up tap distance;
  - high-voltage, resistor and capacitor rules.
- **Cornell deck:** `python3 sky130.py drc --deck cornell ...` runs the Cornell Pegasus deck
  (279 checks, private use). It misses 17 of the 102 base violations in the test set:
  contact/via coverage, via sizes, hole areas, grid and angle. It also reports false results
  on SkyWater's own cells (`licon.12`, and whole-edge `li.5`).

### LVS (Pegasus)

```sh
python3 sky130.py lvs my_cell.gds my_cell my_cell.cdl            # one cell: MATCH / MISMATCH + summary
python3 sky130.py lvs-check --cells all                          # all 390 fd_sc cells
python3 sky130.py lvs-block my_top.gds my_top my_top_pg.v        # routed block vs Innovus netlist
```

- **Deck:** `sky130_lvs.pvl` is written by `sky130cad/lvs_deck.py` from SkyWater's layer
  definitions. No third-party deck text is used.
  - **Device types** come from the implant layers: `nsdm`/`psdm` set n or p, `lvtn`/`hvtp`
    set the threshold variant. The body is the n-well or the substrate.
  - **Devices:** `nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8`, `pfet_01v8_lvt`,
    `pfet_01v8_hvt`, and the zero-ohm `short` element that the tie cell `conb` uses.
  - **Properties:** W, L, AS, AD, PS and PD, so the same deck drives Quantus extraction.
- **Source netlists:** by default the cell's `.spice` netlist. Its device names match the
  layout; the `.cdl` files still use legacy names for some cells.
- **Full-chip LVS:**
  - Save the Innovus netlist with `saveNetlist x.v -includePowerGround -includePhysicalInst`.
  - `lvs-block` converts it to CDL against `library/sky130_fd_sc_hs.cdl` and compares it
    with the cells as matching hierarchy.
- **Cornell deck:** `--deck cornell` runs it for comparison (download with `--cornell`).
- `lvs.py` prepares a source netlist: `*.SCALE MICRON`, legacy device names, no
  extraction-only elements.

### Spectre

```spice
simulator lang=spice
.include "spectre/models/sky130_digital_ss.spice"     * tt ss ff sf fs; sizes in microns
.include "spectre/netlists/sky130_fd_sc_hs__inv_1.spice"
```

The files as shipped need these changes for Spectre:
- **Library:** `sky130.lib.spice` does not load in Spectre as shipped. `spectre-models` writes
  a digital subset (nfet_01v8, nfet_01v8_lvt, pfet_01v8, pfet_01v8_hvt) with the subcircuit
  parameters moved for Spectre.
- **Cell netlists:** these write sizes like `1.12e+06u`, which Spectre misreads.
  `sky130cad/spectre_netlist.py` converts them.

### Characterization

```sh
python3 sky130.py characterize --cells inv_1,mux2_1,dfxtp_1 [--corner ss_150C_1v60]
python3 sky130.py extract --cells inv_1,mux2_1,dfxtp_1          # Quantus RC netlists
python3 sky130.py characterize --cells inv_1,mux2_1,dfxtp_1 --netlist-dir $SKY130_WORK/quantus/netlists
```

- **Output:** delay and transition tables (input slew × load), input capacitance, CLK→Q, and
  setup/hold found by bisection with a 10 % CLK→Q push-out criterion. Written as Liberty that
  Genus loads, with a point-by-point comparison against the shipped tables.
- **Extracted vs schematic netlists** (mean difference from the shipped Liberty):

| Arc | Schematic netlist | Extracted netlist |
|---|---:|---:|
| `dfxtp_1` CLK→Q rise / fall | −24 % / −33 % | +7 % / +5 % |
| `mux2_1` A0→X rise / fall | −15 % / −26 % | +11 % / +3 % |
| input capacitance | 15–45 % low | 5–16 % high |

- **Remaining offset:** the open transistor models are not the foundry models behind the
  shipped tables. Compare a custom cell with library cells characterized by the same flow.
- **Other cells:** `sky130cad/charlib.py` takes a JSON config of netlist, supplies, functions
  or flip-flop pins, and an optional reference.

### Cell LEF (Abstract Generator)

```sh
python3 sky130.py abstract --cells my_cell --liberty my_cells.lib     # GDS -> LEF, batch
```

- **Method:** Abstract runs in batch from a replay file (`abstract/abs.replay`). It reads the
  tech LEF, the cell GDS and a Liberty file for pin directions.
- **Result:** pins, OBS, SIZE, SITE and CLASS are identical to the shipped LEF. `VPB`/`VNB` are
  not generated, because they are only labels on the wells.

### Virtuoso layout with sky130 transistors

The transistors are SkyWater's devices (`nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8`,
`pfet_01v8_hvt`), simulated with Google's `sky130_fd_pr` models. Google publishes no Cadence
layout generators for them, so the PCells come from the Cornell `sky130_fd_pr_main` library
(Cadence PDK Automation System; no license, private use).

```sh
python3 sky130.py virtuoso-setup        # writes $SKY130_WORK/virtuoso/cds.lib
cd $SKY130_WORK/virtuoso && virtuoso &
```

1. Create a library attached to the technology of `sky130_fd_pr_main`
   (File → New → Library → "Attach to an existing technology library").
2. Place `sky130_fd_pr_main` / `nfet_01v8` (or `pfet_01v8`, `_lvt`, `_hvt`) / `layout`.
   - Parameters: `l`, `fw` (finger width), `fingers`, `connectGates`, `connectSD`, and taps.
   - Total W = fw × fingers.
   - With `connectSD`/`connectGates` set to "None", fingers are separate transistors that
     share diffusion.
3. Stream out with the library's layer map:
   `strmout -library MYLIB -topCell CELL -view layout -strmFile CELL.gds -layerMap
   <work>/upstream/cornell_sky130_pdk/libs/sky130_fd_pr_main/sky130_fd_pr_main.layermap`.
4. Check: `python3 sky130.py drc CELL.gds CELL` and `python3 sky130.py lvs CELL.gds CELL CELL.cdl`.

`python3 sky130.py xtor-check` does steps 1–4 in batch for six sizes: nfet 0.42 µm and
2×1 µm, nfet_lvt 0.74 µm, pfet 1.12 µm and 2×1.5 µm, pfet_hvt 1 µm. All are DRC-clean, and
LVS reports MATCH.

## Upstream changes (`python3 sky130.py patches`)

| Change | Why |
|---|---|
| tech LEF: `LAYER licon TYPE CUT` after `pwell` | Innovus 20 rejects the upstream file (IMPLF-121) |
| cell LEF: `FOREIGN` name of `diode_2`, `fill_diode_2/4/8` | pre-release `scs8hs_*` names left those cells without geometry in streamed layouts |
| `xor3_1` GDS + LEF OBS: internal met1 strap re-routed over pin B (`cellfix.py`) | pin B had no met1 access; routed designs shorted to the strap |
| Liberty | generated from the upstream JSON (no Liberty is shipped) |
| LVS deck: `lvs_black_box -grey` commented out | Pegasus 25.1 rejects it; only capacitor cells use it |
| Spectre models: subcircuit parameters, `{}` → `''` | Spectre rejects the ngspice form |
| cell netlists: `1.12e+06u` → `1.12` | Spectre misreads exponent + unit suffix |

## Sources and licenses

| Source | Pinned | License |
|---|---|---|
| google/skywater-pdk-libs-sky130_fd_sc_hs | `1d051f49` | Apache-2.0 |
| google/skywater-pdk-libs-sky130_fd_pr | `f62031a1` | Apache-2.0 |
| cornell-c2s2/SKY130_PDK (Virtuoso library, Pegasus DRC/LVS decks) | `7be5f297` | none: private use, do not redistribute |
| stineje/sky130_cds (QRC tech file, Virtuoso tech library) | `e7194f64` | Apache-2.0 |
| sky130_osu_sc_t18 (OSU 18-track cells; second library) | `aa2b509f` | Apache-2.0 |

This repository's code, documentation and the files it writes from its own rules (DRC, LVS and
antenna decks, Cadence setup, generated transistors) are MIT-licensed (`LICENSE`). Files derived
from an upstream source keep that source's license, as `release/NOTICE.md` lists. `release/`
holds only Apache-2.0 sources and this repository's own output; the Cornell files are fetched
for private comparison only and are never published.

## Release

`python3 sky130.py release` writes `release/` from the work directory. Everything in it is
either generated by this repository or copied unchanged from an Apache-2.0 source.

```
release/
  README.md            contents and quick start (the release stands alone)
  VERSION              release version and the pinned upstream commits
  NOTICE.md            sources, pinned commits, licenses, every change to upstream files
  MANIFEST.sha256      checksums (sha256sum -c MANIFEST.sha256)
  GPDK045_COMPARISON.md  what each GPDK045/gsclib045 part maps to here
  licenses/            Apache-2.0 texts of sky130_fd_sc_hs, sky130_fd_pr, sky130_cds, sky130_osu_sc_t18
  tech/                Liberty *.lib.gz (5 corners, gzip), tech LEF (+ Innovus variant), cell LEF,
                       gds/, streamOut.map, extraction.layermap, qrcTechFile, sky130.ict
  tech/ccs/            Liberty with CCS noise for the 3 *_ccsnoise corners (gzip)
  cadence/             genus_fdsc.tcl, innovus_fdsc.tcl, mmmc_fdsc.tcl, mmmc_fdsc_genus.tcl
                       (find tech/ relatively; read .lib or .lib.gz)
  pegasus/             sky130_full.pvl (DRC, 127 checks), sky130_lvs.pvl (LVS), sky130_antenna.pvl,
                       tests/ (185 DRC + 5 antenna test layouts with expected results)
  library/             sky130_fd_sc_hs.cdl, .gds (merged), .v (functional models),
                       oa/sky130_fd_sc_hs (Virtuoso layout + symbol views, 390 cells)
  virtuoso/            sky130/ (technology library), sky130_mos/ (MOS PCells, CDF, symbols),
                       sky130_mos_pcells.il, layer.map, display.drf, cds.lib
  mos/                 generated transistors (GDS, CDL, Spectre), sky130cad/mosgen.py
  spectre/             models/ (tt ss ff sf fs, relative includes), netlists/ (390 cells),
                       extracted/ (Quantus RC netlists of all 390 cells), inverter_ss.scs
  characterization/    Spectre-characterized Liberty for inv_1, mux2_1, dfxtp_1 + comparisons
  quantus/             layer_setup, tech_cmd
  abstract/            Abstract-generated LEF, layer map, replay example
  examples/smoke/      Genus + Innovus scripts, RTL, SDC; results/ from the validation run
  patches/             diffs against the Apache-2.0 upstream files
  osu18t_hs/           second library: OSU 18-track high-speed cells (LEF, Liberty .lib.gz for
                       4 corners, implant-patched GDS, netlists; see its README)
```

**Nothing from the Cornell repository** (no license) is in the release. The DRC, LVS and
antenna decks are this repository's own, and transistors come from `mos`/`pcells`.
`download --cornell` fetches the Cornell files for private comparison only.

**Size:** about 253 MB in 3,600 files. Liberty is compressed (the largest file is 33 MB, below
GitHub's 50 MB warning limit); Genus and Innovus read `.lib.gz` directly.

`python3 sky130.py release-check` uses `release/` as published, from a fresh run directory:
- checksums;
- the DRC deck and the antenna deck on their test layouts;
- LVS of published cells and generated transistors;
- the Spectre example;
- the Virtuoso technology library;
- Genus → Innovus → stream-out → Pegasus DRC → full-chip LVS on the example design.

Validated 2026-11-18: every check passes (example design: 0 DRC results, LVS MATCH).

## Release archive

```sh
python3 sky130.py release --version 2026.11.18    # optional; the default version is today's date
python3 sky130.py release-check                   # the tools on the release as published
python3 sky130.py package                         # dist/sky130_fd_sc_hs_cadence-<VERSION>.tar.gz + .sha256
```

`package` writes the archive reproducibly (sorted members, fixed owner and time), so the same
`release/` always gives the same checksum. Attach the archive and its `.sha256` to a source
release, or unpack it anywhere: `sha256sum -c MANIFEST.sha256` inside checks every file.

## Not covered

- Power tables, minimum pulse width and recovery/removal in characterization.
- `VPB`/`VNB` pins in Abstract LEF.
- A fill deck and RC corners (no public process-variation data for the sky130 stack).
- Resistors, capacitors and bipolar devices in LVS and PCells (MOS and the antenna diode only).
  See [docs/gpdk045_comparison.md](docs/gpdk045_comparison.md) for all gaps against GPDK045.
