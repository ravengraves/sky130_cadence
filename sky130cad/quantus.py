"""Layout parasitic extraction of cells with Pegasus LVS + Quantus, for characterization.

  python3 sky130.py extract --cells inv_1,mux2_1,dfxtp_1 [--temperature 150] [--qrc FILE]
  python3 sky130.py characterize --cells ... --netlist-dir WORK/quantus/netlists

Needs a QRC technology file (`convert --qrc` or `extract --qrc`); the sky130 one is not in
the public PDK (a course PDK ships one compiled from sky130.ict). Steps per cell, in
WORK/quantus/<cell>/:
1. Extraction deck WORK/quantus/sky130_pex.pvl: the patched LVS deck with a property block on
   the five 1.8 V MOS devices: W = perimeter_coincide(G, SD)/2, L = (perimeter(G) - 2W)/2,
   AS/AD = area(S/D), PS/PD = perimeter(S/D). The deck alone computes only W/L, so junction
   capacitance would be missing. A source/drain region shared by series transistors is
   counted fully for each device (junction capacitance overestimated at internal nodes).
2. `pegasus -lvs -qrc_data`: LVS must MATCH; writes the database Quantus reads.
3. Quantus (`input_db -type pegasus`) with
   - layer_setup: Pegasus layers -> ICT layers (poly->Poly, li1, met1..met5,
     nSourceDrain+pSourceDrain -> N_SOURCE_DRAIN, since the compiled tech file allows only
     one diffusion layer; both have 0.12 um / 15 ohm in the ICT; contacts licon1->CONT,
     poly_licon1->licon, mcon, via..via4);
   - technology command file: -canonical_res_caps -exclude_gate_res -length_units meters
     -cap_ground_layer pwell (a capacitance reference is required; pwell = VNB);
   - extract -type rc_coupled, SPICE output with schematic net names.
4. The SPICE netlist is converted for Spectre with the models from `spectre-models`
   (`.option scale=1.0u`): devices become X calls of sky130_fd_pr__* with sizes in microns,
   `$layer` comments are dropped.

Validation (2026-11-17, SS 150 C 1.60 V; mean difference to the shipped Liberty tables):
  cell / arc                 schematic netlist   extracted (this flow)
  dfxtp_1 CLK->Q rise/fall     -24 % / -33 %       +7 % / +5 %
  mux2_1  A0->X rise/fall      -15 % / -26 %      +11 % / +3 %
  mux2_1  S->X  rise/fall      -22 % / -23 %      +10 % / +7 %
  inv_1   A->Y  rise/fall       +6 % / -19 %      +23 % / -9 %
  input capacitance             15-45 % low         5-16 % high
  dfxtp_1 setup/hold            up to 0.2 ns        within 0.03-0.14 ns
Rising outputs remain ~10 % slow: the open sky130_fd_pr models are not the foundry models
behind the shipped tables, and shared diffusion is counted per device. Compare custom cells
with library cells characterized by this same flow, so the model bias cancels.
"""
import os
import re

from . import lvs, toolenv

MOS = {'nfet_01v8', 'nfet_01v8_lvt', 'pfet_01v8', 'pfet_01v8_lvt', 'pfet_01v8_hvt'}

LAYER_SETUP = '''# Pegasus LVS layer (ext_) -> sky130.ict layer (pro_); written by sky130cad/quantus.py
pro_layer=Poly ext_layer=poly
pro_layer=li1 ext_layer=li1
pro_layer=met1 ext_layer=met1
pro_layer=met2 ext_layer=met2
pro_layer=met3 ext_layer=met3
pro_layer=met4 ext_layer=met4
pro_layer=met5 ext_layer=met5
# the compiled tech file accepts one diffusion layer; P and N are identical in the ICT
pro_layer=N_SOURCE_DRAIN ext_layer=nSourceDrain,pSourceDrain
pro_cont=licon ext_cont=poly_licon1
pro_cont=CONT ext_cont=licon1
pro_cont=mcon ext_cont=mcon
pro_cont=via ext_cont=via
pro_cont=via2 ext_cont=via2
pro_cont=via3 ext_cont=via3
pro_cont=via4 ext_cont=via4
'''

TECH_CMD = '''-canonical_res_caps
-exclude_gate_res
-length_units meters
-cap_ground_layer pwell
'''


def pex_deck(lvs_deck, dst):
    """LVS deck + W/L/AS/AD/PS/PD property blocks on the 1.8 V MOS devices."""
    out, n = [], 0
    for line in open(lvs_deck).read().split('\n'):
        m = re.match(r'device M[NP] \((\w+)\) .*?(\w+) \(S\)', line)
        if m and m.group(1) in MOS:
            sd = m.group(2)
            line += (' [\n    property W, L, AS, AD, PS, PD\n'
                     '    W = perimeter_coincide(G, %s) / 2\n'
                     '    L = (perimeter(G) - perimeter_coincide(G, %s)) / 2\n'
                     '    AS = area(S)\n    AD = area(D)\n    PS = perimeter(S)\n    PD = perimeter(D)\n]' % (sd, sd))
            n += 1
        out.append(line)
    open(dst, 'w').write('// Extraction variant written by sky130cad/quantus.py\n' + '\n'.join(out))
    return n


SCALE = {'w': 1e6, 'l': 1e6, 'ad': 1e12, 'as': 1e12, 'pd': 1e6, 'ps': 1e6}


def spectre_netlist(src, dst):
    """Quantus SPICE -> Spectre netlist for the sky130_fd_pr models (sizes in microns)."""
    lines = []
    for raw in open(src).read().split('\n'):
        if raw.startswith('+') and lines:
            lines[-1] += ' ' + raw[1:].strip()
        else:
            lines.append(raw)
    out, devices, rc = [], 0, 0
    for line in lines:
        line = re.sub(r'\s\$\S*', '', line).rstrip()
        tok = line.split()
        if tok and tok[0][0] in 'mM' and len(tok) > 5 and tok[5] in MOS:
            params = []
            for t in tok[6:]:
                k, v = t.split('=', 1)
                if k.lower() in SCALE:
                    params.append('%s=%.6g' % (k.lower(), float(v) * SCALE[k.lower()]))
            line = ' '.join(['X' + tok[0]] + tok[1:5] + ['sky130_fd_pr__' + tok[5]] + params)
            devices += 1
        elif tok and tok[0][0] in 'rRcC' and not tok[0].startswith('.'):
            rc += 1
        out.append(line)
    open(dst, 'w').write('* Extracted by Quantus, converted by sky130cad/quantus.py\n' + '\n'.join(out) + '\n')
    return devices, rc


def extract_cell(gds, top, cdl, workdir, deck, techdir, temperature, env=None):
    """Returns (status, message, raw_spice_path)."""
    os.makedirs(workdir, exist_ok=True)
    res, summ = lvs.run(gds, top, cdl, workdir, deck, env, extra=['-qrc_data'])
    if res != 'MATCH':
        return 'LVS ' + res, summ, None
    open(os.path.join(workdir, 'layer_setup'), 'w').write(LAYER_SETUP)
    open(os.path.join(workdir, 'tech_cmd'), 'w').write(TECH_CMD)
    out = os.path.join(workdir, top + '_rc')
    ccl = ['input_db -type pegasus -directory_name %s -run_name %s' % (workdir, top),
           'process_technology -technology_directory %s -technology_command_file %s '
           '-technology_layer_setup_file %s -temperature %g'
           % (techdir, os.path.join(workdir, 'tech_cmd'), os.path.join(workdir, 'layer_setup'), temperature),
           'extract -selection all -type rc_coupled',
           'output_db -type spice -hierarchy_delimiter "/"',
           'output_setup -file_name %s -net_name_space schematic -temporary_directory_name qtmp' % out]
    open(os.path.join(workdir, 'extract.ccl'), 'w').write('\n'.join(ccl) + '\n')
    rc = toolenv.run(['quantus', '-cmd', 'extract.ccl'], workdir, os.path.join(workdir, 'quantus.out'), env)
    if rc or not os.path.exists(out):
        errs = [l.strip() for l in open(os.path.join(workdir, 'quantus.out')) if 'ERROR' in l]
        return 'QUANTUS ERROR', '; '.join(errs[:3]) or 'rc=%d' % rc, None
    return 'OK', summ, out


def main(a):
    """Driver for `sky130.py extract` (a: argparse namespace from sky130.py)."""
    import glob
    lib = 'sky130_fd_sc_hs'
    q = os.path.join(a.work, 'quantus')
    os.makedirs(q, exist_ok=True)
    which = getattr(a, 'deck', None) or 'sky130cad'
    lvs_deck = lvs.deck_path(a.work, which)
    if which == 'cornell':
        deck = os.path.join(q, 'cornell_pex.pvl')
        print('extraction deck %s: properties on %d MOS devices' % (deck, pex_deck(lvs_deck, deck)))
    else:
        deck = lvs_deck     # already computes W, L, AS, AD, PS, PD
        print('extraction deck %s' % deck)
    qrc = getattr(a, 'qrc', None) or os.path.join(a.work, 'tech', 'qrcTechFile')
    if not os.path.exists(qrc):
        raise SystemExit('no QRC tech file: give --qrc or run `convert --qrc FILE`')
    techdir = os.path.join(q, 'tech')
    os.makedirs(techdir, exist_ok=True)
    link = os.path.join(techdir, 'qrcTechFile')
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.realpath(qrc), link)
    netdir = os.path.join(q, 'netlists')
    os.makedirs(netdir, exist_ok=True)
    if a.cells == 'all':
        names = sorted(os.path.basename(g)[:-4] for g in glob.glob(os.path.join(a.work, 'upstream', lib, 'cells', '*',
                                                                                  lib + '__*.gds')))
    else:
        names = [c if c.startswith(lib) else '%s__%s' % (lib, c) for c in a.cells.split(',')]

    def one(name):
        find = lambda ext: glob.glob(os.path.join(a.work, 'upstream', lib, 'cells', '*', name + '.' + ext))
        if not find('gds') or not find('spice'):
            return name, 'NO SOURCE', '', None
        src = os.path.join(q, name + '.src.cdl')
        os.makedirs(q, exist_ok=True)
        lvs.spice_to_cdl(find('spice')[0], src)
        status, msg, raw = extract_cell(find('gds')[0], name, src, os.path.join(q, name), deck, techdir,
                                        a.temperature, a.env)
        if status != 'OK':
            return name, status, msg, None
        return name, 'OK', msg, spectre_netlist(raw, os.path.join(netdir, name + '.spice'))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max(1, getattr(a, 'jobs', 1) or 1)) as ex:
        rows = list(ex.map(one, names))
    bad = 0
    for name, status, msg, counts in rows:
        if status != 'OK':
            print('%-34s %s: %s' % (name, status, msg[:200]))
            bad += 1
        elif len(rows) <= 20:
            print('%-34s LVS MATCH, extracted: %d transistors, %d R/C elements' % (name, counts[0], counts[1]))
    print('extracted %d/%d cells -> %s' % (len(rows) - bad, len(rows), netdir))
    if bad:
        raise SystemExit(1)
