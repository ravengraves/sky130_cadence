"""Pinned upstream sources and the parts of them this flow reads.

Nothing here is redistributed; `sky130.py download` fetches these at the pinned commits
(sparse checkouts, so only the needed files are transferred).
"""

FDSC = {
    'name': 'sky130_fd_sc_hs',
    'url': 'https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hs',
    'commit': '1d051f49bfe4e2fe9108d702a8bc2e9c081005a4',
    'license': 'Apache-2.0',
}

FDPR = {
    'name': 'sky130_fd_pr',
    'url': 'https://github.com/google/skywater-pdk-libs-sky130_fd_pr',
    'commit': 'f62031a1be9aefe902d6d54cddd6f59b57627436',
    'license': 'Apache-2.0',
}

# Oklahoma State University sky130_cds (Apache-2.0): Cadence setup for sky130 with the QRC
# technology file (PEX/qrcTechFile, compiled from sky130.ict) and a Virtuoso technology library
# (VirtuosoOA/sky130: layers, display, vias; no device PCells).
SKY130_CDS = {
    'name': 'sky130_cds',
    'url': 'https://github.com/stineje/sky130_cds',
    'commit': 'e7194f64aa375e540fa1e46ab23d8a10d917b83c',
    'license': 'Apache-2.0',
    'qrc_sha256': 'e919867f3670558ba0ed6fb32de63ed7a49a074e74f8043f14c53ae2442bc91e',
}


def cds_sparse_patterns():
    return ['/LICENSE', '/README.md', '/PEX/', '/VirtuosoOA/sky130/', '/VirtuosoOA/layer.map',
            '/VirtuosoOA/display.drf', '/VirtuosoOA/README.md']


# OSU 18-track standard cells (Apache-2.0): the sky130_osu_sc_t18 submodule of sky130_cds, at the
# commit sky130_cds pins. Optional second library (`download --osu`, `osu-check --patch`).
OSU18 = {
    'name': 'sky130_osu_sc_t18',
    'url': 'https://foss-eda-tools.googlesource.com/skywater-pdk/libs/sky130_osu_sc_t18',
    'commit': 'aa2b509f3c8f32ea94fdb55ac9768754667c1658',
    'license': 'Apache-2.0',
}
OSU_CORNERS = ['ss_1P60_150C', 'ss_1P60_-40C', 'tt_1P80_25C', 'ff_1P95_-40C']


def osu_sparse_patterns():
    pats = ['/LICENSE', '/README.md', '/sky130_osu_sc_18T.tlef', '/18T_hs/gds/', '/18T_hs/lef/', '/18T_hs/spice/']
    pats += ['/18T_hs/lib/sky130_osu_sc_18T_hs_%s.ccs.lib' % c for c in OSU_CORNERS]
    return pats


def required_cds():
    return ['LICENSE', 'PEX/qrcTechFile', 'PEX/sky130.ict', 'VirtuosoOA/sky130/tech.db', 'VirtuosoOA/layer.map']


# Cornell C2S2 SKY130_PDK: Cadence PDK (PAS) for sky130 with the Virtuoso device library
# sky130_fd_pr_main (parameterized transistor/resistor/capacitor cells with layout views),
# a Pegasus DRC deck, the Pegasus LVS deck and a Quantus setup. The repository has NO license
# (all rights reserved by default): fetch it for your own use, do not redistribute it.
CORNELL = {
    'name': 'cornell_sky130_pdk',
    'url': 'https://github.com/cornell-c2s2/SKY130_PDK',
    'commit': '7be5f297762929abe04e13510d7923f3e97204a7',
    'license': 'none (private use only)',
}


def cornell_sparse_patterns():
    return ['/sky130_release/libs/', '/sky130_release/cds.lib', '/sky130_release/display.drf',
            '/sky130_release/Sky130_DRC/', '/sky130_release/Sky130_LVS/', '/sky130_release/quantus/',
            '/sky130_release/doc/']


def required_cornell():
    return ['libs/sky130_fd_pr_main/tech.db', 'libs/sky130_fd_pr_main/nfet_01v8/layout/layout.oa',
            'libs/sky130_fd_pr_main/sky130_fd_pr_main.layermap', 'Sky130_DRC/sky130_rev_0.0_1.0.drc.pvl',
            'Sky130_LVS/sky130.lvs.pvl']


# Pegasus LVS deck for sky130 (from CORNELL); patched for Pegasus 25.1 by sky130cad.lvs.
LVS_DECK = {
    'url': ('https://raw.githubusercontent.com/cornell-c2s2/SKY130_PDK/'
            '7be5f297762929abe04e13510d7923f3e97204a7/sky130_release/Sky130_LVS/sky130.lvs.pvl'),
    'sha256': 'b30ff2d4c5bbe35906c7261f4d9cdaa573db20bde06852d7b1da5428d6025ca9',
}

# Liberty corners written by `convert` (name as in the upstream timing/ JSON files).
DEFAULT_CORNERS = ['ss_150C_1v60', 'ss_100C_1v60', 'ss_n40C_1v60_ccsnoise',
                   'tt_025C_1v80_ccsnoise', 'ff_n40C_1v95_ccsnoise']

# Transistor families used by standard cells (the Spectre model subset).
DEVICES = ('nfet_01v8', 'nfet_01v8_lvt', 'pfet_01v8', 'pfet_01v8_hvt')


def fdsc_sparse_patterns(corners, lib=FDSC['name']):
    pats = ['/LICENSE', '/README.rst', '/tech/', '/models/', '/timing/%s__common.lib.json' % lib]
    for c in corners:
        pats += ['/timing/%s__%s.lib.json' % (lib, c), '/cells/*/%s__*__%s.lib.json' % (lib, c)]
    for ext in ('gds', 'lef', 'spice', 'cdl', 'v'):
        pats.append('/cells/*/%s__*.%s' % (lib, ext))
    return pats


def fdpr_sparse_patterns():
    pats = ['/LICENSE', '/models/']
    pats += ['/cells/%s/' % d for d in DEVICES]
    return pats


def required_fdsc(corners, lib=FDSC['name']):
    """Relative paths (globs) that must exist in a usable fd_sc checkout."""
    req = ['tech/%s.tlef' % lib, 'timing/%s__common.lib.json' % lib, 'cells/inv/%s__inv_1.gds' % lib,
           'cells/inv/%s__inv_1.lef' % lib, 'cells/inv/%s__inv_1.spice' % lib, 'cells/inv/%s__inv_1.cdl' % lib]
    for c in corners:
        req += ['timing/%s__%s.lib.json' % (lib, c), 'cells/inv/%s__inv_1__%s.lib.json' % (lib, c)]
    return req


def required_fdpr():
    req = ['models/sky130.lib.spice', 'models/all.spice', 'models/parameters/lod.spice']
    req += ['cells/%s/sky130_fd_pr__%s__tt.corner.spice' % (d, d) for d in DEVICES]
    return req
