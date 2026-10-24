"""Probe NVAPI P-State 20 clock-offset windows on the Tesla V100.

Reads NV_GPU_PERF_PSTATES20_INFO through NvAPI_GPU_GetPstates20 and prints, per
P-State, each clock domain with its frequency and the delta the driver reports.
Used to tell whether the VBIOS clock table really exposes a memory offset window
(Titan V ships 0..+550 MHz on the DRAM row, Tesla ships 0..0).

Usage:
    python nvapi_pstates.py --scan          # find the struct size the driver accepts
    python nvapi_pstates.py                 # dump P-State 20
"""
import argparse
import ctypes as C
import struct
import sys

NVAPI_OK = 0
ID_INIT = 0x0150E828
ID_ENUM_PHYS = 0xE5AC921F
ID_GET_PSTATES20 = 0x6FF81213
ID_SET_PSTATES20 = 0x0F4DAE6B

DOMAIN_NAMES = {0: 'GPC', 1: 'XBAR', 2: 'DRAM', 3: 'SYS', 4: 'HUB', 5: 'VID', 6: 'DISP', 7: 'PCIEGEN'}


class NvApi:
    def __init__(self):
        self.lib = C.CDLL('nvapi64.dll')
        self.lib.nvapi_QueryInterface.restype = C.c_void_p
        self.lib.nvapi_QueryInterface.argtypes = [C.c_uint]

    def __call__(self, func_id, restype, *argtypes):
        ptr = self.lib.nvapi_QueryInterface(func_id)
        if not ptr:
            raise RuntimeError(f'NvAPI id {func_id:#x} not exported')
        return C.CFUNCTYPE(restype, *argtypes)(ptr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scan', action='store_true', help='scan struct sizes instead of using the known one')
    ap.add_argument('--size', type=lambda s: int(s, 0), default=0x2C0C)
    a = ap.parse_args()

    nv = NvApi()
    if nv(ID_INIT, C.c_int)() != NVAPI_OK:
        raise SystemExit('NvAPI_Initialize failed')
    handles = (C.c_void_p * 64)()
    count = C.c_uint()
    rc = nv(ID_ENUM_PHYS, C.c_int, C.POINTER(C.c_void_p), C.POINTER(C.c_uint))(handles, C.byref(count))
    if rc != NVAPI_OK or not count.value:
        raise SystemExit(f'no physical GPU (rc={rc})')

    get = nv(ID_GET_PSTATES20, C.c_int, C.c_void_p, C.c_void_p)
    buf = C.create_string_buffer(0x8000)

    if a.scan:
        good = []
        for size in range(0x1000, 0x6000, 4):
            struct.pack_into('<I', buf, 0, size | (1 << 16))
            if get(handles[0], buf) == NVAPI_OK:
                good.append(size)
        print('sizes returning NVAPI_OK:', [hex(s) for s in good], f'({len(good)})')
        if not good:
            return 1
        size = good[0]
    else:
        size = a.size

    struct.pack_into('<I', buf, 0, size | (1 << 16))
    rc = get(handles[0], buf)
    print(f'GetPstates20 rc={rc} struct size={size:#x}')
    if rc != NVAPI_OK:
        return 1

    raw = buf.raw[:size]
    np_, nc, nb = struct.unpack_from('<III', raw, 8)
    print(f'numPstates={np_} numClocks={nc} numBaseVoltages={nb}')
    for i in range(min(np_, 8)):
        off = 20 + i * 376
        pid, edit = struct.unpack_from('<II', raw, off)
        print(f'  pstate {pid} (editable={edit})')
        for k in range(8):
            c = off + 8 + k * 36
            dom, typ, ed, freq, delta = struct.unpack_from('<IIIII', raw, c)
            if dom == 0 and freq == 0 and delta == 0:
                continue
            print(f'    dom={dom}({DOMAIN_NAMES.get(dom, "?")}) type={typ} editable={ed} '
                  f'freq={freq/1000:.0f} MHz delta={delta/1000:+.0f} MHz')
    return 0


if __name__ == '__main__':
    sys.exit(main())
