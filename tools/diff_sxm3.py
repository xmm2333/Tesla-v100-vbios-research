"""Full structural diff of the PCI and NPDS images between two VBIOS dumps.

Blocks that are not explained by known tables (clock programming, clock table,
P-States, power table, VFE) are the interesting ones — they are candidates for
tables that are not yet characterised.

Usage:
    python diff_sxm3.py --a first.rom --b second.rom
"""
import argparse
import os
import struct
import sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get('NVBIOS_EDITOR_SRC', os.path.join(ROOT, 'nvidia-vbios-vix-editor-0.1.29', 'src')))
from nvidia_vbios.rom.structure import scan_images

_ap = argparse.ArgumentParser()
_ap.add_argument('--a', required=True, help='first ROM dump')
_ap.add_argument('--b', required=True, help='second ROM dump')
_args = _ap.parse_args()

SXM3 = open(_args.a, 'rb').read()
BASE = open(_args.b, 'rb').read()

def images(blob):
    pci, ext, _ = scan_images(blob)
    return {f'PCI{i}': (p['start'], p['end']) for i, p in enumerate(pci)}, \
           {f'EXT{i}': (e['start'], e['end']) for i, e in enumerate(ext)}

pa, ea = images(SXM3)
pb, eb = images(BASE)

print('--- flagged 958 sweep in SXM3 (be 43 / be 83 / be c3 / be 03) ---')
for flag_byte in (0x43, 0x83, 0xc3, 0x03):
    needle = bytes((0xbe, flag_byte))
    offs, o = [], SXM3.find(needle)
    while o != -1:
        offs.append(o); o = SXM3.find(needle, o + 1)
    if offs:
        print(f'  be {flag_byte:02x}: {len(offs)} hits @ ' + ' '.join(hex(x) for x in offs))
print()

def block_diff(name, a, a_off, b, b_off, label_a, label_b):
    """Diff a[a_off:a_off+n] vs b[b_off:b_off+n] where n = common length."""
    n = min(len(a) - a_off, len(b) - b_off)
    sa, sb = a[a_off:a_off + n], b[b_off:b_off + n]
    sm = SequenceMatcher(None, sb, sa, autojunk=False)
    blocks = sm.get_matching_blocks()
    print(f'=== {name}: {label_a}[{a_off:#x}:{a_off+n:#x}] vs {label_b}[{b_off:#x}:{b_off+n:#x}]  ({n} bytes)')
    pos = 0
    regions = []
    for mb in blocks:
        if mb.b > pos:  # gap in b (baseline) => differing region
            # region: baseline [pos, mb.b), SXM3 [pos + (mb.a - mb.b)? no--use same offsets]
            regions.append((pos, mb.b))
        pos = mb.b + mb.size
    if not regions:
        print('    identical')
    for s, e in regions:
        # show what each side has
        bs = bytes(sb[s:e])
        asx = bytes(sa[s:e])
        ndiff = sum(1 for x, y in zip(bs, asx) if x != y)
        print(f'    diff @ +{s:#06x}..+{e:#06x} len {e-s} ({ndiff} bytes differ)')
        # compress preview: first 32 bytes each side
        def hx(x): return ' '.join(f'{c:02x}' for c in x[:48])
        print(f'      BASE: {hx(bs)}')
        print(f'      SXM3: {hx(asx)}')
    print()

# Image 3 (EXT1) -- aligned at image start; internal layout confirmed aligned
# (clock table at EXT1+0x11C in both, mem entry at EXT1+0x12B in both).
block_diff('Image3/EXT1', SXM3, ea['EXT1'][0], BASE, eb['EXT1'][0], 'SXM3', 'BASE')

# Image 0 (PCI0) -- internal layout shifts by 0x10 in places; align on the
# clocks-table header magic as anchor.
magic_clk = bytes.fromhex('10 07 09 0a')
ax = SXM3.find(magic_clk, pa['PCI0'][0], pa['PCI0'][1])
bx = BASE.find(magic_clk, pb['PCI0'][0], pb['PCI0'][1])
print(f'anchor clocks table hdr: SXM3 {ax:#x}  BASE {bx:#x}  (delta {ax - bx:#x})')
# align from the anchor to end of PCI0
block_diff('Image0/PCI0 from clocks-table anchor', SXM3, ax, BASE, bx, 'SXM3', 'BASE')

# Also diff the region before the anchor (BIT headers etc.) with plain offset 0
n = min(ax, bx)
block_diff('Image0/PCI0 head (offset-aligned)', SXM3, pa['PCI0'][0], BASE, pb['PCI0'][0], 'SXM3', 'BASE')
