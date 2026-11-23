# OSU sky130_osu_sc_18T_hs (second library)

18-track (6.66 um row, site 18T 0.11 um) high-speed cells from Oklahoma State University,
`sky130_osu_sc_t18` at `aa2b509f3c8f` (Apache-2.0, `../licenses/sky130_osu_sc_t18.LICENSE`). They use
the same transistors as `sky130_fd_sc_hs` (nfet_01v8_lvt, pfet_01v8) but wider: inv_1 has a
1.0 um nfet and a 3.0 um pfet (SkyWater inv_1: 0.74 / 1.12 um), so x1 cells are faster and larger.

| Folder | Content |
|---|---|
| `lef/` | `sky130_osu_sc_18T.tlef` (technology), `sky130_osu_sc_18T_hs.lef` (cells) |
| `lib/` | Liberty (gzip): SS 1.60 V 150 C, SS 1.60 V -40 C, TT 1.80 V 25 C, FF 1.95 V -40 C |
| `gds/` | cell layouts with the implant patch below |
| `spice/` | OSU's extracted netlists (`.spice` + `.pex.spice` + `.pxi.spice`) |

The OSU rows cannot share placement rows with `sky130_fd_sc_hs` (different site, height and rail
order); use one library per block.

## Implant patch (`python3 sky130.py osu-check --patch`)

As shipped, the cells' top implant bands (pfet psdm, n-tap nsdm) stop short of the cell edges, so
abutted cells leave nsdm/psdm gaps narrower than the 0.38 um minimum (352 results in a test row of
every cell abutted to inv_1, with mirrored rows), and the 0.11/0.22 um fillers carry no implant.
`sky130cad/osu.py` extends every implant rectangle that ends within 0.38 um of a cell edge to the
edge, every nwell rectangle within 1.27 um of a side edge to the edge, and gives the filler cells the
row's implant bands: 154 shapes in 66 cells.

Validation with this repository's decks (Pegasus 25.1): abutted and mirrored rows 0 DRC results
(352 before); each cell alone is clean except the narrow fillers (implant width/area, never used
alone); LVS of the extracted netlists against the layouts 61/63 MATCH (dlat_1/dlat_l mismatch).

| Cell | Shapes changed |
|---|---:|
| addf_1 | 3 |
| addf_l | 3 |
| addh_1 | 2 |
| addh_l | 2 |
| and2_1 | 2 |
| and2_2 | 2 |
| and2_4 | 2 |
| and2_6 | 2 |
| and2_8 | 2 |
| and2_l | 2 |
| ant | 2 |
| antfill | 1 |
| aoi21_l | 2 |
| aoi22_l | 2 |
| buf_1 | 2 |
| buf_2 | 2 |
| buf_4 | 2 |
| buf_6 | 2 |
| buf_8 | 2 |
| buf_l | 2 |
| decap_1 | 2 |
| decap_l | 2 |
| dff_1 | 2 |
| dff_l | 2 |
| dffr_1 | 2 |
| dffr_l | 2 |
| dffs_1 | 2 |
| dffs_l | 2 |
| dffsr_1 | 2 |
| dffsr_l | 2 |
| dlat_1 | 6 |
| dlat_l | 7 |
| fill_1 | 4 |
| fill_16 | 4 |
| fill_2 | 4 |
| fill_32 | 4 |
| fill_4 | 4 |
| fill_8 | 4 |
| inv_1 | 2 |
| inv_10 | 2 |
| inv_2 | 2 |
| inv_3 | 2 |
| inv_4 | 2 |
| inv_6 | 2 |
| inv_8 | 2 |
| inv_l | 2 |
| mux2_1 | 2 |
| nand2_1 | 2 |
| nand2_l | 2 |
| nor2_1 | 2 |
| nor2_l | 2 |
| oai21_l | 2 |
| oai22_l | 2 |
| or2_1 | 2 |
| or2_2 | 2 |
| or2_4 | 2 |
| or2_8 | 2 |
| or2_l | 2 |
| tbufi_1 | 2 |
| tbufi_l | 2 |
| tiehi | 2 |
| tielo | 2 |
| tnbufi_1 | 2 |
| tnbufi_l | 2 |
| xnor2_l | 2 |
| xor2_l | 2 |
