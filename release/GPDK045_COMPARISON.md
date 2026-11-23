# Comparison with Cadence GPDK045 / gsclib045

Cadence's generic 45 nm kit (GPDK045 v6.0 with the gsclib045 v4.8 libraries) is the reference
for "what a complete Cadence kit contains". This table lists each of its parts and the matching file in `release/`.

| GPDK045 / gsclib045 | This release | Status |
|---|---|---|
| Virtuoso technology library (`gpdk045/`: layers, display, vias, layer map) | `virtuoso/sky130/`, `virtuoso/layer.map`, `virtuoso/display.drf` (from sky130_cds) | equal |
| Device PCells with CDF, symbols (`nmos1v`, `pmos1v`, `*_lvt`, `*_hvt`, resistors, caps, diodes, BJTs, inductors) | `virtuoso/sky130_mos/`: PCells with CDF (Spectre, CDL) and symbols for `nfet_01v8`, `nfet_01v8_lvt`, `pfet_01v8`, `pfet_01v8_hvt`; `mos/` GDS generator | **partial**: MOS only; box symbols; no R/C/diode/BJT/inductor |
| Spectre models with corners (`models/spectre/gpdk045.scs`: tt/ff/ss/fs/sf) | `spectre/models/sky130_digital_{tt,ss,ff,sf,fs}.spice` | equal for the digital MOS devices |
| PVS/Pegasus DRC (`pvs/pvlDRC.rul`) | `pegasus/sky130_full.pvl` (127 checks, 185 test layouts) | equal (density: see fill) |
| PVS/Pegasus LVS (`pvs/pvlLVS.rul`) | `pegasus/sky130_lvs.pvl` (own deck): 5 MOS types, antenna diode `diode_pw2nd`, `short`; 390/390 cells match | equal for digital; no R/C/BJT devices |
| Antenna deck (`pvs/pvlAnt.rul`) | `pegasus/sky130_antenna.pvl`: SkyWater antenna rules (table Ig, S8PIR-10R), per-layer staged connectivity, diode credit; 5 test layouts | equal |
| Fill deck (`pvs/pvlFILL.rul`) | none. SkyWater's aluminium-stack density rules are recommended only (`m*.pd.1`), and the max-density rules apply to the copper option | **gap** (by choice) |
| QRC tech files: `qrc/{rcworst,typical,rcbest}` + ICT files | `tech/qrcTechFile` + `tech/sky130.ict` (one, nominal) | **partial**: no RC corners (no public process-variation data for the sky130 stack) |
| Extraction rules for Quantus (`extview.rul`) | `pegasus/sky130_lvs.pvl` computes W, L, AS, AD, PS, PD; `quantus/layer_setup`, `quantus/tech_cmd` | equal |
| Cap tables (`soce/*.CapTbl`) | not needed: Innovus uses the QRC file | n/a (legacy) |
| Several standard-cell libraries (gsclib045 svt/lvt/hvt) | `sky130_fd_sc_hs` (main) and `osu18t_hs/` (OSU 18-track, wider transistors, implant-patched) | equal in kind (different row heights: one library per block) |
| Standard-cell Liberty, several PVT corners | `tech/*.lib.gz`: SS 150 C, SS 100 C, SS −40 C, TT 25 C, FF −40 C | equal |
| Cell LEF + tech LEF | `tech/sky130_fd_sc_hs_cells.lef`, `tech/sky130_fd_sc_hs_innovus.tlef` | equal |
| Cell GDS | `tech/gds/` (per cell), `library/sky130_fd_sc_hs.gds` (merged) | equal |
| Cell CDL (`cdl/gsclib045.cdl`) | `library/sky130_fd_sc_hs.cdl` | equal |
| Cell Verilog models | `library/sky130_fd_sc_hs.v`: zero-delay models generated from the Liberty functions (370 cells; 6 clock gates as black boxes). SkyWater's own models at the pinned commit do not compile. | equal (no timing checks/specify) |
| OA cell library (layout, abstract, symbol views) | `library/oa/sky130_fd_sc_hs`: layout and symbol views of all 390 cells | equal except abstract/schematic views (the LEF covers abstracts) |
| Extracted cell netlists (`spectre/gsclib045_extracted`) | `spectre/extracted/` (Quantus, all cells) | equal |
| Per-cell SPEF/DSPF | extracted SPICE only | partial |
| Noise libraries (`celtic/*.cdb`) | `python3 sky130.py ccs-libs`: Liberty with SkyWater's CCS-noise data kept (3,081 groups at TT; Genus reads all 376 cells). 122 MB per corner, so generated, not shipped | equal (generated on demand) |
| Full-chip LVS of routed blocks | `python3 sky130.py lvs-block` | equal |
| Tutorials (`solutions/`) | `docs/genus.md`, `docs/innovus.md`, `docs/virtuoso.md`, `examples/` | equal |
