"""Decode the Image-3 clock table + P-State memory fields across ALL ROMs to
crack the flag semantics (0x4000 vs 0x8000 vs 0xC000) on the memory gear.

Hypothesis to test: bit15 marks a non-stock / factory-OC gear.  SXM3 (958) uses
0xC000-flagged memory fields everywhere; all 877 cards use 0x4000 only.  If
PG503 (1107 factory-OC) and/or TitanV also carry bit15, that confirms it.

Usage: python dump_img3_mems.py
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get('NVBIOS_EDITOR_SRC', os.path.join(ROOT, 'nvidia-vbios-vix-editor-0.1.29', 'src')))
from nvidia_vbios.rom.structure import scan_images

import argparse, glob
_ap = argparse.ArgumentParser()
_ap.add_argument('roms', nargs='*', help='ROM dumps to inspect (default: *.rom in the current directory)')
_args = _ap.parse_args()
_files = _args.roms or sorted(glob.glob('*.rom'))
ROMS = [(f, os.path.basename(f)) for f in _files]

MAGIC = bytes.fromhex('0f 08 ff')

for fname, label in ROMS:
    path = os.path.join(ROOT, fname)
    blob = open(path, 'rb').read()
    pci, ext, _ = scan_images(blob)
    # Image 3 = EXT1 in our naming (second NPDS image)
    regions = [(e['start'], e['end']) for e in ext] + [(p['start'], p['end']) for p in pci]
    at = None
    for s, e in regions:
        i = blob.find(MAGIC, s, e)
        if i != -1 and blob[i + 3:i + 9] != bytes(6):  # skip empty tables
            at = i
            break
    if at is None:
        print(f'== {label}: no image-3 clock table found')
        continue
    print(f'== {label}  clock table @ {at:#x}')
    for i in range(9):
        off = at + 3 + i * 6
        f0, f1, f2 = struct.unpack_from('<HHH', blob, off)
        flag1 = f1 & ~0x7FFF
        mark = '  <-- MEM' if 780 <= (f0 & 0x7FFF) <= 1200 and (f2 * 4) in range(780 * 4 - 8, 1200 * 4 + 8) else ''
        # better heuristic: third field *4 ≈ first field
        if abs(f2 * 4 - f0) <= 3 and 700 <= f0 <= 1200:
            mark = '  <-- MEM'
        print(f'   [{i}] @ {off:#06x}: {f0:5d}  flag1={flag1:#06x}  {f1:#06x}  {f2:5d}{mark}')
    # P-State rows: first at magic+0x5A, stride 0x29, mem field at +8
    print('   P-State mem fields (+8..+11 of each 41B row):')
    for k in range(7):
        row = at + 0x5A + k * 0x29
        m, r = struct.unpack_from('<HH', blob, row + 8)
        gpc = struct.unpack_from('<H', blob, row)[0]
        print(f'   row{k} @ {row:#06x}: gpc={gpc & 0x7FFF:5d}({gpc & 0xF000:#06x})  mem={m & 0x7FFF:5d} flag={m & 0xF000:#06x}  ratio={r}')
    print()
