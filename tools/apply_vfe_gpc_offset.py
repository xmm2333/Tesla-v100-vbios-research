"""Apply a VFE curve offset to a VBIOS image.

The mechanism — locate the GPC curve root, follow its next link, and attach a
constant-MHz equation in a free slot — is **not** implemented here. It comes
from nvidia-vbios-vix-editor (`gpc_curve_slot` / `vfe_constant_mhz`), which
documented the VFE equation format in the first place. See
THIRD_PARTY_NOTICES.md §2.

A positive offset raises the curve (more clock at the same voltage); a negative
offset lowers it (more voltage at the same clock).

Usage:
    python -c "from apply_vfe_gpc_offset import apply_offset; \\
               apply_offset('in.rom', 'out.rom', -100)"
"""
import os
import sys
import struct

sys.path.insert(0, os.environ.get('NVBIOS_EDITOR_SRC', os.path.join(os.path.dirname(__file__), '..', 'nvidia-vbios-vix-editor-0.1.29', 'src')))
from nvidia_vbios.rom.structure import gpc_curve_slot, vfe_constant_mhz, scan_images

def apply_offset(input_rom, output_rom, offset_mhz):
    with open(input_rom, 'rb') as f:
        blob = bytearray(f.read())

    # VFE table pointer at P+0x20
    # In V100, VFE is at 0x3160e
    vfe = 0x3160e
    hs, c1, s1, esize = blob[vfe+1:vfe+5]
    vcount = blob[vfe+5]
    base = vfe + hs + c1 * s1
    
    # Root 9 is the GPC compare root node in V100
    slot_info = gpc_curve_slot(blob, base, esize, 1, vcount, 9)
    print(f"[{os.path.basename(input_rom)}] Current GPC curve offset: {slot_info['current']} MHz")

    if offset_mhz != 0:
        c_eq = vfe_constant_mhz(esize, slot_info['var'], float(offset_mhz))
        slot_off = slot_info['slot_offset']
        blob[slot_off : slot_off + esize] = c_eq
        blob[slot_info['link_offsets'][0]] = slot_info['slot']
    else:
        # Restore to 0 (clean free slot)
        blob[slot_info['slot_offset'] : slot_info['slot_offset'] + esize] = bytes(esize)
        blob[slot_info['link_offsets'][0]] = 0xFF

    verified_info = gpc_curve_slot(blob, base, esize, 1, vcount, 9)
    print(f"[{os.path.basename(output_rom)}] Verified GPC curve offset: {verified_info['current']} MHz (Slot {verified_info['slot']})")

    # Fix image checksums
    pci, ext, _ = scan_images(blob)
    images = [(p['start'], p['end']) for p in pci] + [(e['start'], e['end']) for e in ext]
    for s, e in images:
        current_sum = sum(blob[s:e-1]) & 0xFF
        needed_last = (256 - current_sum) & 0xFF
        blob[e-1] = needed_last
        assert sum(blob[s:e]) & 0xFF == 0

    with open(output_rom, 'wb') as f:
        f.write(blob)
    print(f"Saved {output_rom} successfully! Size: {len(blob)} bytes.")

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Apply a VFE curve offset to a VBIOS image.')
    ap.add_argument('--base', required=True, help='Input ROM image path')
    ap.add_argument('--offset', type=float, required=True, help='VFE curve offset in MHz (can be negative)')
    ap.add_argument('--out', required=True, help='Output ROM image path')
    args = ap.parse_args()
    apply_offset(args.base, args.out, args.offset)
