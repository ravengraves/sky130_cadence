# Innovus place and route with sky130_fd_sc_hs

This guide takes a Genus netlist (see `genus.md`) through floorplan, power, placement, clock
tree, routing and GDS export, then checks the GDS with the Pegasus DRC deck. The paths below
are relative to `release/`. The settings were validated with Innovus 20.16.

## Files used

| File | Content |
|---|---|
| `cadence/innovus_fdsc.tcl` | `fdsc_init_lef_file` and the `fdsc_*` procedures below |
| `cadence/mmmc_fdsc.tcl` | MMMC views. Setup: SS 150 °C, SS −40 °C (slower for these cells: temperature inversion) and TT 25 °C. Hold: FF −40 °C. Set `fdsc_sdc` before `init_design`. |
| `tech/sky130_fd_sc_hs_innovus.tlef` | Technology LEF, with `licon` added (Innovus 20 rejects the upstream file) |
| `tech/sky130_fd_sc_hs_cells.lef` | Cell LEF: all 390 macros, with the diode/fill `FOREIGN` fix |
| `tech/qrcTechFile` | Quantus RC technology. From sky130_cds, Apache-2.0. |
| `tech/extraction.layermap` | LEF layer to QRC layer map |
| `tech/streamOut.map`, `tech/gds/*.gds` | GDS layer map and cell layouts, merged at stream-out |
| `examples/smoke/innovus.tcl` | Complete tested script |

## Run the example

Run Genus first, in the same directory (`genus.md`):

```sh
innovus -64 -no_gui -files ../release/examples/smoke/innovus.tcl -log innovus
pegasus -drc -dp 4 -gds smoke.gds -top_cell smoke ../release/pegasus/sky130_full.pvl
```

Expected results:
- **Innovus:** `smoke_geometry.rpt` and `smoke_connectivity.rpt` report no violations.
- **Pegasus:** `result.sum` shows 0 results.
- **Reference:** `examples/smoke/results/` holds the reports and GDS from the validation run.

## The flow

```tcl
source release/cadence/innovus_fdsc.tcl
set fdsc_sdc [file normalize my_out.sdc]       ;# read by mmmc_fdsc.tcl
set init_verilog my_netlist.v
set init_lef_file $fdsc_init_lef_file
set init_top_cell my_top
set init_pwr_net vdd
set init_gnd_net gnd
set init_mmmc_file release/cadence/mmmc_fdsc.tcl
init_design

fdsc_route_settings          ;# route on met1..met5; li1 is LEF routing layer 1
fdsc_dont_use
fdsc_connect_power           ;# VPWR/VPB -> vdd, VGND/VNB -> gnd
fdsc_floorplan 0.45 12       ;# utilization, core margin (um)
fdsc_power_grid              ;# met4/met5 core rings, met4 stripes every 100 um
fdsc_welltaps                ;# tapvpwrvgnd_1 every 13 um
fdsc_connect_power

place_opt_design
fdsc_ties
fdsc_connect_power
fdsc_sroute                  ;# met1 rails on the cell rows, connected to the grid

fdsc_cts_settings
ccopt_design
fdsc_post_cts_settings       ;# useful skew off
optDesign -postCTS -hold

fdsc_antenna
routeDesign -globalDetail
fdsc_post_route_settings     ;# OCV + QRC extraction (avoids IMPOPT-6080)
optDesign -postRoute -setup -hold

fdsc_fillers
fdsc_connect_power
set_verify_drc_mode -report geometry.rpt
verify_drc
verifyConnectivity -type all -report connectivity.rpt
report_timing > timing.rpt
saveNetlist my_top_routed.v
fdsc_stream_out my_top.gds my_top   ;# merges tech/gds/*.gds
```

## Notes from validation runs

- **Utilization:** at 60 % some cells were left unplaced. 45–50 % works.
- **Useful skew:** leave post-CTS `optDesign` useful skew off. With it on, `FE_USKC`
  clock-buffer chains moved output-register clocks by about 7 ns.
- **Layer numbering:** `li1` is LEF routing layer 1, so met1..met5 are layers 2..6.
  `fdsc_route_settings` keeps signal routing on met1..met5.
- **Well taps:** tap cells are part of the layout. Without them, every n-well fails `nwell.4`
  (no contacted tap) in Pegasus.
- **Delay cells:** `dlygate4sd*` stay usable in Innovus for hold fixing.
- **Pin access:** `python3 sky130.py pin-access` checks that every signal pin has met1 access.
  SkyWater's `xor3_1` had none on pin B (an internal met1 strap covered it; NanoRoute shorted
  to the strap on about half the instances). The release's `xor3_1` layout re-routes that strap;
  every pin now has 10 or more access points except `a22o_4` A2 (9, routable).
- **After post-route optimization**, repeat `verify_drc` / `ecoRoute -fix_drc` until clean, and
  run `fdsc_connect_power` again: NanoRoute's antenna diodes are inserted after the first one.
- **Final DRC:** sign off with `pegasus/sky130_full.pvl` on the streamed GDS. Innovus
  `verify_drc` checks only LEF rules.

## Full-chip LVS

```tcl
saveNetlist my_top_pg.v -includePowerGround -includePhysicalInst   ;# supply pins, decap/tap cells
fdsc_stream_out my_top.gds my_top
```

```sh
python3 sky130.py lvs-block my_top.gds my_top my_top_pg.v      # uses pegasus/sky130_lvs.pvl
```

`lvs-block` writes the source CDL (library subcircuits + the block netlist) and runs Pegasus
with the cells as matching hierarchy:
- **Supplies:** nets on cell supply pins (`vdd`/`gnd`) become ports, matching the labeled
  layout pins.
- **Physical-only cells:** device-free cells (fillers, taps) are left out.

The example in `examples/smoke/` matches, and so does the routed 2-cycle maf32 (≈20,000 nets).

## Not covered

- **Missing DRC rules:** the DRC deck does not check density, antenna (use Innovus
  `verifyProcessAntenna`) or latch-up tap distance.
