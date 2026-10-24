"""Dump the FULL 27-byte entries of the clock programming table from all ROMs.

The gear entry (entry 3, HBM memory) has: 13-byte main item + 3x4-byte subitem1
+ 2x1-byte subitem2.  Previous experiments only patched the u16 MHz in the main
item; the subitems (likely the actual PLL programming params) were never
compared across modules.  This script dumps them for every reference ROM.

Usage: python dump_clkprog_all.py
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get('NVBIOS_EDITOR_SRC', os.path.join(ROOT, 'nvidia-vbios-vix-editor-0.1.29', 'src')))
from nvidia_vbios.rom.structure import scan_images, parse_bit

import argparse, glob
_ap = argparse.ArgumentParser()
_ap.add_argument('roms', nargs='*', help='ROM dumps to inspect (default: *.rom in the current directory)')
_args = _ap.parse_args()
_files = _args.roms or sorted(glob.glob('*.rom'))
ROMS = [(f, os.path.basename(f)) for f in _files]


def clkprog_table(blob):
    pci, _, _ = scan_images(blob)
    bit = parse_bit(blob, pci[0])
    at = pci[0]['start'] + struct.unpack_from('<I', blob, bit['C']['data'] + 0x0C)[0]
    ver, hs, esize, count, c1, s1, c2, s2 = blob[at:at + 8]
    stride = esize + c1 * s1 + c2 * s2
    return at, hs, stride, count, (c1, s1, c2, s2)


def hexrow(b):
    return ' '.join(f'{x:02x}' for x in b)


for fname, label in ROMS:
    path = os.path.join(ROOT, fname)
    if not os.path.exists(path):
        print(f'== {label}: MISSING {fname}')
        continue
    blob = open(path, 'rb').read()
    try:
        at, hs, stride, count, (c1, s1, c2, s2) = clkprog_table(blob)
    except Exception as exc:
        print(f'== {label}: FAIL {exc}')
        continue
    print(f'== {label}  ({fname})')
    print(f'   table @ {at:#x}  hdr={hexrow(blob[at:at+8])}  stride={stride}  count={count}')
    for i in range(min(count, 12)):
        e = at + hs + i * stride
        main = blob[e:e + 13]
        sub = blob[e + 13:e + 13 + c1 * s1 + c2 * s2]
        flags, freq = struct.unpack_from('<BH', blob, e)
        mark = ' <-- MEMORY GEAR' if flags == 0x81 else ''
        print(f'   [{i:2d}] @ {e:#06x}  {hexrow(main)}  | sub: {hexrow(sub)}  ({freq} MHz){mark}')
    print()
