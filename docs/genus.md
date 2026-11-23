# Genus synthesis with sky130_fd_sc_hs

This guide synthesizes RTL into SkyWater `sky130_fd_sc_hs` cells using the files in
`release/`. The paths below are relative to `release/`.

## Files used

| File | Content |
|---|---|
| `cadence/genus_fdsc.tcl` | `fdsc_read_libs CORNER` and `fdsc_dont_use` |
| `tech/sky130_fd_sc_hs__<corner>.lib.gz` | Liberty, one gzip file per corner (ns, pF, 376 cells with timing); `fdsc_read_libs` finds it |
| `examples/smoke/` | `smoke.v`, `smoke.sdc` and `genus.tcl`: a tested example |

The Tcl files find `tech/` relative to their own location. They work from any directory if
`cadence/` and `tech/` stay side by side.

### Corners

| Corner | Use |
|---|---|
| `ss_150C_1v60` | **Synthesis default.** Slowest corner: SS, 1.60 V, 150 °C. |
| `ss_100C_1v60` | SS, 1.60 V, 100 °C |
| `ss_n40C_1v60_ccsnoise` | SS, 1.60 V, −40 °C |
| `tt_025C_1v80_ccsnoise` | Typical: TT, 1.80 V, 25 °C |
| `ff_n40C_1v95_ccsnoise` | Hold analysis: FF, 1.95 V, −40 °C |

## Run the example

```sh
source /path/to/cadence/setup.sh        # puts genus on PATH
mkdir -p run && cd run
genus -no_gui -files ../release/examples/smoke/genus.tcl
```

The run writes these files to the current directory:
- `smoke_netlist.v`: the netlist;
- `genus_timing.rpt` and `genus_area.rpt`: the reports.

## Your own design

```tcl
source release/cadence/genus_fdsc.tcl
fdsc_read_libs ss_150C_1v60          ;# setup corner
read_hdl -language v2001 my.v
elaborate my_top
fdsc_dont_use
read_sdc my.sdc
set_db syn_generic_effort medium
set_db syn_map_effort high
set_db syn_opt_effort high
syn_generic
syn_map
syn_opt
report_timing -max_paths 10 > timing.rpt
report_area > area.rpt
write_hdl > my_netlist.v
write_sdc > my_out.sdc
```

`fdsc_dont_use` marks these cell types `dont_use`:

| Cells | Reason |
|---|---|
| Latches and clock gates | Not wanted in a flip-flop design |
| Scan and asynchronous set/reset flip-flops | Use synchronous reset in RTL |
| Tristate buffers | Not wanted in this flow |
| Delay cells | Innovus inserts them for hold fixing (`dlygate4sd*` stays usable there) |
| Tap, fill, decap and diode cells | Physical cells; Innovus places them |
| Full adders `fah*` | Failed legalization in Innovus |

The full pattern list is in `cadence/genus_fdsc.tcl`. `xor3_1` is usable: the release carries a
layout fix for its pin B (see `NOTICE.md`).

## Notes

- **Units:** the Liberty files use ns and pF. Write the SDC in those units.
- **Wire load:** the Liberty files define none. Genus timing therefore ignores wires; expect
  Innovus timing after routing to be slower.
- **Liberty source:** the Liberty files are generated from SkyWater's JSON timing data, with
  the CCS-noise groups removed. `NOTICE.md` lists every change made to upstream files.
- **Your own cells:** `python3 sky130.py characterize` writes Liberty for them. Read it with
  `read_libs` next to the corner file.
