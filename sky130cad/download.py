"""Fetch the upstream data at pinned commits into WORK/upstream (sparse checkouts).

  python3 sky130.py download [--corners C ...] [--fdsc-from DIR] [--fdpr-from DIR] [--cds-from DIR]
                             [--cornell | --cornell-from DIR]

- sky130_fd_sc_hs: tech LEF, timing headers, and per cell GDS/LEF/SPICE/CDL/Verilog plus the
  Liberty JSON of the selected corners: 1.1 GB for the 5 default corners (each *_ccsnoise
  corner carries ~250 MB of CCS-noise data; ss_150C_1v60 alone is 48 MB) instead of 2.4 GB.
  Measured 2026-11-17: 62 s; every fetched file byte-identical to a full checkout.
- sky130_fd_pr: models/ and the four 1.8 V transistor families standard cells use.
- sky130_cds (Oklahoma State, Apache-2.0): PEX/qrcTechFile (SHA-256 checked) and the Virtuoso
  technology library VirtuosoOA/sky130 with its layer map (33 MB).
- Only with --cornell (or --cornell-from): Cornell C2S2 SKY130_PDK (sky130_release/: Virtuoso
  device library with transistor PCells, Pegasus DRC and LVS decks; 55 MB). NO license:
  private use only, for comparisons (`lvs-check --deck cornell`, `drc --deck cornell`) and the
  PCell check `xtor-check`. No other step needs it: this repository has its own DRC and LVS
  decks and transistor generator. The LVS deck inside is SHA-256 checked;
  WORK/upstream/lvs/sky130.lvs.pvl links to it.

- Only with --osu (or --osu-from): OSU sky130_osu_sc_t18 (Apache-2.0; the submodule sky130_cds pins)
  18T_hs gds/, lef/, spice/ and the Liberty of four corners (77 MB): an optional second library.

`--*-from` uses an existing checkout or file instead (machines without GitHub access): it
is linked, not copied, and checked for the files later steps need.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request

from . import sources


def git(args, cwd):
    subprocess.run(['git'] + args, cwd=cwd, check=True, stdin=subprocess.DEVNULL)


def sparse_fetch(url, commit, dest, patterns):
    """Blob-filtered, depth-1 fetch of one commit with a non-cone sparse checkout."""
    if os.path.isdir(os.path.join(dest, '.git')):
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=dest, stdout=subprocess.PIPE, text=True).stdout.strip()
        if head == commit:
            print('%s already at %s' % (dest, commit[:12]))
            git(['sparse-checkout', 'set', '--no-cone'] + patterns, dest)
            return
        raise SystemExit('%s exists at %s, expected %s; remove it first' % (dest, head, commit))
    os.makedirs(dest)
    git(['init', '-q'], dest)
    git(['remote', 'add', 'origin', url], dest)
    git(['sparse-checkout', 'set', '--no-cone'] + patterns, dest)
    git(['fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin', commit], dest)
    git(['-c', 'advice.detachedHead=false', 'checkout', '-q', 'FETCH_HEAD'], dest)
    print('fetched %s at %s into %s' % (url, commit[:12], dest))


def check(root, required):
    import glob
    missing = [r for r in required if not glob.glob(os.path.join(root, r))]
    if missing:
        raise SystemExit('%s is missing %d required files, e.g. %s' % (root, len(missing), missing[:3]))


def link(src, dest):
    src = os.path.abspath(src)
    if os.path.lexists(dest):
        if os.path.islink(dest) and os.readlink(dest) == src:
            return
        raise SystemExit('%s exists; remove it to relink' % dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    os.symlink(src, dest)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def fetch_lvs_deck(dest, from_file=None):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if from_file:
        shutil.copyfile(from_file, dest)
    elif not os.path.exists(dest):
        urllib.request.urlretrieve(sources.LVS_DECK['url'], dest)
    got = sha256(dest)
    if got != sources.LVS_DECK['sha256']:
        raise SystemExit('LVS deck %s has SHA-256 %s, expected %s' % (dest, got, sources.LVS_DECK['sha256']))
    print('LVS deck', dest, 'SHA-256 ok')


def main(work, corners, fdsc_from=None, fdpr_from=None, lvs_from=None, cornell_from=None, cds_from=None,
         cornell=False, osu=False, osu_from=None):
    up = os.path.join(work, 'upstream')
    fdsc = os.path.join(up, sources.FDSC['name'])
    fdpr = os.path.join(up, sources.FDPR['name'])
    if fdsc_from:
        link(fdsc_from, fdsc)
    else:
        sparse_fetch(sources.FDSC['url'], sources.FDSC['commit'], fdsc, sources.fdsc_sparse_patterns(corners))
    check(fdsc, sources.required_fdsc(corners))
    if fdpr_from:
        link(fdpr_from, fdpr)
    else:
        sparse_fetch(sources.FDPR['url'], sources.FDPR['commit'], fdpr, sources.fdpr_sparse_patterns())
    check(fdpr, sources.required_fdpr())
    cds = os.path.join(up, sources.SKY130_CDS['name'])
    if cds_from:
        link(cds_from, cds)
    else:
        sparse_fetch(sources.SKY130_CDS['url'], sources.SKY130_CDS['commit'], cds, sources.cds_sparse_patterns())
    check(cds, sources.required_cds())
    got = sha256(os.path.join(cds, 'PEX', 'qrcTechFile'))
    if got != sources.SKY130_CDS['qrc_sha256']:
        raise SystemExit('qrcTechFile SHA-256 %s, expected %s' % (got, sources.SKY130_CDS['qrc_sha256']))
    print('sky130_cds qrcTechFile SHA-256 ok')
    if osu or osu_from:
        o = os.path.join(up, sources.OSU18['name'])
        if osu_from:
            link(osu_from, o)
        else:
            sparse_fetch(sources.OSU18['url'], sources.OSU18['commit'], o, sources.osu_sparse_patterns())
        check(o, ['LICENSE', 'sky130_osu_sc_18T.tlef', '18T_hs/lef/sky130_osu_sc_18T_hs.lef',
                  '18T_hs/gds/sky130_osu_sc_18T_hs__inv_1.gds'])
    want = cornell or cornell_from or lvs_from
    cornell = os.path.join(up, sources.CORNELL['name'])
    if cornell_from:
        link(cornell_from, cornell)
    elif want and not lvs_from:
        sparse_fetch(sources.CORNELL['url'], sources.CORNELL['commit'], cornell + '_git',
                     sources.cornell_sparse_patterns())
        link(os.path.join(cornell + '_git', 'sky130_release'), cornell)
    if want and os.path.exists(cornell):
        check(cornell, sources.required_cornell())
        lvs_from = os.path.join(cornell, 'Sky130_LVS', 'sky130.lvs.pvl')
    if want:
        fetch_lvs_deck(os.path.join(up, 'lvs', 'sky130.lvs.pvl'), lvs_from)
    else:
        print('Cornell SKY130_PDK skipped (not needed; --cornell fetches it for private comparisons)')
    print('upstream data ready in', up)


if __name__ == '__main__':
    sys.exit('run through sky130.py download')
