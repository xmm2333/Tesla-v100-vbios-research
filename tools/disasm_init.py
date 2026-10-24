"""Volta (GV100) devinit / BIT init-script disassembler.

Opcode semantics follow the ``init_opcode[]`` table from nouveau's
``nvkm/subdev/bios/init.c``:

    Copyright 2012 Red Hat Inc.
    Authors: Ben Skeggs
    Licensed under the MIT licence — full text in THIRD_PARTY_NOTICES.md

The VBIOS PCI image carries a byte-code init script that devinit/PMU executes
at power-on; it writes GPU registers directly (opcode 0x7a init_zm_reg,
0x91 init_zm_reg_group, 0x6e init_nv_reg, 0x79 init_pll,
0x87 init_ram_restrict_pll, ...).  This sits below the data tables.

Usage:
    python disasm_init.py --rom <your_dump.rom> --start 0x7930 --count 60
"""
import argparse
import os
import struct
import sys

# opcode -> (name, fixed param bytes).  -1 = variable length, handled per opcode.
OPCODES = {
    0x32: ('io_restrict_prog', 10), 0x33: ('repeat', 1), 0x34: ('io_restrict_pll', 11),
    0x36: ('end_repeat', 0), 0x37: ('copy', 10), 0x38: ('not', 0),
    0x39: ('io_flag_condition', 1), 0x3a: ('generic_condition', 2),
    0x3b: ('io_mask_or', 1), 0x3c: ('io_or', 1),
    0x47: ('andn_reg', 8), 0x48: ('or_reg', 8), 0x49: ('idx_addr_latched', 17),
    0x4a: ('io_restrict_pll2', 10), 0x4b: ('pll2', 8),
    0x4c: ('i2c_byte', 3), 0x4d: ('zm_i2c_byte', 3), 0x4e: ('zm_i2c', 3),
    0x4f: ('tmds', 4), 0x50: ('zm_tmds_group', 2), 0x51: ('cr_idx_adr_latch', 4),
    0x52: ('cr', 3), 0x53: ('zm_cr', 2), 0x54: ('zm_cr_group', 1),
    0x56: ('condition_time', 2), 0x57: ('ltime', 2),
    0x58: ('zm_reg_sequence', 5), 0x59: ('pll_indirect', 6),
    0x5a: ('zm_reg_indirect', 6), 0x5b: ('sub_direct', 2), 0x5c: ('jump', 2),
    0x5e: ('i2c_if', 5), 0x5f: ('copy_nv_reg', 21),
    0x62: ('zm_index_io', 4), 0x63: ('compute_mem', 0), 0x65: ('reset', 12),
    0x66: ('configure_mem', 0), 0x67: ('configure_clk', 0), 0x68: ('configure_preinit', 0),
    0x69: ('io', 4), 0x6b: ('sub', 1), 0x6d: ('ram_condition', 2),
    0x6e: ('nv_reg', 12), 0x6f: ('macro', 1),
    0x71: ('done', 0), 0x72: ('resume', 0), 0x73: ('strap_condition', 8),
    0x74: ('time', 2), 0x75: ('condition', 1), 0x76: ('io_condition', 1),
    0x77: ('zm_reg16', 6), 0x78: ('index_io', 5), 0x79: ('pll', 6),
    0x7a: ('zm_reg', 8), 0x87: ('ram_restrict_pll', 1), 0x8c: ('reset_begun', 0),
    0x8d: ('reset_end', 0), 0x8e: ('gpio', 0), 0x8f: ('ram_restrict_zm_reg_group', 6),
    0x90: ('copy_zm_reg', 8), 0x91: ('zm_reg_group', 5), 0x92: ('reserved', 1),
    0x96: ('xlat', 16), 0x97: ('zm_mask_add', 12), 0x98: ('auxch', 5),
    0x99: ('zm_auxch', 5), 0x9a: ('i2c_long_if', 6), 0xa9: ('gpio_ne', 1),
    0xaa: ('reserved_aa', 3),
}


def rd32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def rd16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def disasm(blob, start, count, base=0):
    off = start
    for _ in range(count):
        if off >= len(blob):
            print('EOF')
            return
        op = blob[off]
        ent = OPCODES.get(op)
        if ent is None:
            print(f'{base+off:#07x}: {op:02x}                ; UNKNOWN (skip 1)')
            off += 1
            continue
        name, n = ent
        p = blob[off + 1:off + 1 + n]
        txt = p.hex(' ')
        extra = ''
        if name == 'zm_reg' and len(p) == 8:
            extra = f'  R[{rd32(p,0):#010x}] = {rd32(p,4):#010x}'
        elif name == 'nv_reg' and len(p) == 12:
            extra = f'  R[{rd32(p,0):#010x}] = (R & {rd32(p,4):#010x}) | {rd32(p,8):#010x}'
        elif name == 'andn_reg' and len(p) == 8:
            extra = f'  R[{rd32(p,0):#010x}] &= ~{rd32(p,4):#010x}'
        elif name == 'or_reg' and len(p) == 8:
            extra = f'  R[{rd32(p,0):#010x}] |= {rd32(p,4):#010x}'
        elif name == 'zm_reg16' and len(p) == 6:
            extra = f'  R16[{rd32(p,0):#010x}] = {rd16(p,4):#06x}'
        elif name == 'pll' and len(p) == 6:
            extra = f'  PLL[{rd32(p,0):#010x}] = {rd16(p,4)*10} kHz'
        elif name == 'zm_reg_group' and len(p) >= 5:
            addr, cnt = rd32(p, 0), p[4]
            vals = [rd32(blob, off + 6 + 4 * i) for i in range(cnt)]
            extra = f'  R[{addr:#010x}..] = ' + ' '.join(f'{v:#010x}' for v in vals)
            n = 5 + 4 * cnt
            txt = p[:5].hex(' ')
        elif name == 'zm_reg_sequence' and len(p) >= 5:
            addr, cnt = rd32(p, 0), p[4]
            vals = [rd32(blob, off + 6 + 4 * i) for i in range(cnt)]
            extra = f'  R[{addr:#010x}..+{cnt*4:#x}] = ' + ' '.join(f'{v:#010x}' for v in vals[:8])
            n = 5 + 4 * cnt
            txt = p[:5].hex(' ')
        elif name == 'condition' and len(p) == 1:
            extra = f'  cond={p[0]:#04x}'
        elif name == 'time' and len(p) == 2:
            extra = f'  delay {rd16(p,0)} us'
        elif name == 'ltime' and len(p) == 2:
            extra = f'  delay {rd16(p,0)} ms'
        elif name == 'strap_condition' and len(p) == 8:
            extra = f'  strap: (R[0x101000] & {rd32(p,0):#x}) == {rd32(p,4):#x}'
        elif name == 'ram_condition' and len(p) == 2:
            extra = f'  ram: (R[0x100000] & {p[0]:#x}) == {p[1]:#x}'
        elif name in ('sub_direct', 'jump') and len(p) == 2:
            extra = f'  -> {rd16(p,0):#06x}'
        elif name == 'sub' and len(p) == 1:
            extra = f'  sub#{p[0]}'
        print(f'{base+off:#07x}: {op:02x} {txt:<26s} ; {name}{extra}')
        off += 1 + n


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True)
    ap.add_argument('--start', type=lambda x: int(x, 0), required=True)
    ap.add_argument('--count', type=int, default=50)
    a = ap.parse_args()
    path = a.rom if os.path.isabs(a.rom) else os.path.join(os.path.dirname(os.path.abspath(__file__)), a.rom)
    blob = open(path, 'rb').read()
    print(f'== {os.path.basename(path)}  from {a.start:#x}')
    disasm(blob, a.start, a.count)
