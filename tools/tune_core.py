"""Parameterised tuner for clock-related fields in a V100 VBIOS image.

Fields written (all in the NPDS image; offsets are those observed in the dump
used during the original research and may differ on other images):

    A0      factory clock offset        (s32, kHz)
    GPC     P-State header + row1       (reported core clock)
    XBAR    P-State row0 +0x21          (fabric clock field)
    SYS     P-State row2 +0x21          (system clock field)
    P38     P+0x38 target clock         (0 = leave unchanged)

Always keep a copy of the input image, and verify the result on hardware before
relying on it — see docs/SAFETY.md.

Usage:
    python tune_core.py --base <your_dump.rom> --a0 <n> --gpc <n> --xbar <n> \
                        --sys <n> --out <output.rom>

Image scanning uses nvidia-vbios-vix-editor (`scan_images`). The table layouts
written here were established from that project's BIT token interpretation —
see THIRD_PARTY_NOTICES.md §2.2.
"""
import argparse
import os
import struct
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get('NVBIOS_EDITOR_SRC', os.path.join(ROOT, 'nvidia-vbios-vix-editor-0.1.29', 'src')))
from nvidia_vbios.rom.structure import scan_images

A0_OFF = 0x33220
ENTRY0_Q = 0x30B23
PSTATE_HDR = 0x30B6E
PSTATE_R1 = 0x30BC0
PSTATE_XBAR = 0x30B97
PSTATE_SYS = 0x30BE9
P38_A = 0x384A9
P38_B = 0x387FB


def fix_checksums(blob):
    pci, ext, issues = scan_images(blob)
    assert not issues, f'Scan issues: {issues}'
    for s, e in [(p['start'], p['end']) for p in pci] + [(x['start'], x['end']) for x in ext]:
        blob[e - 1] = (256 - (sum(blob[s:e - 1]) & 0xFF)) & 0xFF
        assert sum(blob[s:e]) & 0xFF == 0, f'checksum error in [{s:x}:{e:x}]'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True, help='input ROM dump')
    ap.add_argument('--a0', type=int, required=True, help='factory clock offset MHz')
    ap.add_argument('--gpc', type=int, required=True, help='GPC report MHz (kept low to avoid pwr/thrm)')
    ap.add_argument('--xbar', type=int, required=True, help='XBAR MHz')
    ap.add_argument('--sys', type=int, default=None, help='SYS MHz (default: leave unchanged)')
    ap.add_argument('--p38', type=int, default=0, help='P+0x38 target MHz (0 = leave at stock 1388)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()

    blob = bytearray(open(a.base, 'rb').read())

    struct.pack_into('<i', blob, A0_OFF, a.a0 * 1000)
    struct.pack_into('<H', blob, ENTRY0_Q, a.gpc // 4)
    struct.pack_into('<HH', blob, PSTATE_HDR, a.gpc, a.gpc // 4)
    struct.pack_into('<HH', blob, PSTATE_R1, a.gpc, a.gpc // 4)
    struct.pack_into('<HH', blob, PSTATE_XBAR, a.xbar | 0x8000, a.xbar // 4)
    if a.sys is not None:
        struct.pack_into('<HH', blob, PSTATE_SYS, a.sys | 0x8000, a.sys // 4)
    if a.p38:
        struct.pack_into('<H', blob, P38_A, a.p38)
        struct.pack_into('<H', blob, P38_B, a.p38)

    fix_checksums(blob)
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    open(out, 'wb').write(blob)
    print(f'[OK] {out}')
    print(f'     A0=+{a.a0}  GPC={a.gpc}  XBAR={a.xbar}  SYS={a.sys if a.sys is not None else "unchanged"}  P38={a.p38 or "stock 1388"}')


if __name__ == '__main__':
    main()
