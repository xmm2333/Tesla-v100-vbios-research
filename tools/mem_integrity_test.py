"""VRAM integrity gate - the check 170tune insists on: "it did not crash" is not a result.

A memory overclock can return wrong bytes without a single Xid, hang or benchmark
failure, and it gets worse as the HBM heats up.  Bandwidth numbers cannot see that.
This fills the whole free VRAM with an index-derived pattern, reads every word back
and counts words that do not match.  Zero mismatches over several passes is the
minimum bar before trusting any memory operating point.

Same PTX-through-ctypes plumbing as mem_bw_test.py: no third-party packages.

Usage:
    python mem_integrity_test.py [--gib 12] [--passes 3]
"""
import argparse
import ctypes as C
import subprocess
import sys
import time

PTX = r"""
.version 6.4
.target sm_70
.address_size 64

.visible .entry vfill(
    .param .u64 p_dst,
    .param .u64 p_words,
    .param .u32 p_seed
)
{
    .reg .pred %p<2>;
    .reg .b32 %r<12>;
    .reg .b64 %rd<6>;
    ld.param.u64 %rd1, [p_dst];
    ld.param.u64 %rd2, [p_words];
    ld.param.u32 %r10, [p_seed];
    mov.u32 %r1, %ctaid.x;
    mov.u32 %r2, %ntid.x;
    mov.u32 %r3, %tid.x;
    mad.lo.u32 %r4, %r1, %r2, %r3;
    mov.u32 %r5, %nctaid.x;
    mul.lo.u32 %r6, %r5, %r2;
$L_loop:
    cvt.u64.u32 %rd3, %r4;
    setp.ge.u64 %p1, %rd3, %rd2;
    @%p1 bra $L_done;
    mul.wide.u32 %rd4, %r4, 4;
    add.s64 %rd5, %rd1, %rd4;
    xor.b32 %r7, %r4, %r10;
    shl.b32 %r8, %r7, 13;
    xor.b32 %r7, %r7, %r8;
    shr.u32 %r8, %r7, 17;
    xor.b32 %r7, %r7, %r8;
    shl.b32 %r8, %r7, 5;
    xor.b32 %r7, %r7, %r8;
    st.global.u32 [%rd5], %r7;
    add.u32 %r4, %r4, %r6;
    bra $L_loop;
$L_done:
    ret;
}

.visible .entry vcheck(
    .param .u64 p_src,
    .param .u64 p_words,
    .param .u32 p_seed,
    .param .u64 p_err
)
{
    .reg .pred %p<2>;
    .reg .b32 %r<12>;
    .reg .b64 %rd<7>;
    ld.param.u64 %rd1, [p_src];
    ld.param.u64 %rd2, [p_words];
    ld.param.u32 %r10, [p_seed];
    ld.param.u64 %rd6, [p_err];
    mov.u32 %r1, %ctaid.x;
    mov.u32 %r2, %ntid.x;
    mov.u32 %r3, %tid.x;
    mad.lo.u32 %r4, %r1, %r2, %r3;
    mov.u32 %r5, %nctaid.x;
    mul.lo.u32 %r6, %r5, %r2;
$L_loop:
    cvt.u64.u32 %rd3, %r4;
    setp.ge.u64 %p1, %rd3, %rd2;
    @%p1 bra $L_done;
    mul.wide.u32 %rd4, %r4, 4;
    add.s64 %rd5, %rd1, %rd4;
    xor.b32 %r7, %r4, %r10;
    shl.b32 %r8, %r7, 13;
    xor.b32 %r7, %r7, %r8;
    shr.u32 %r8, %r7, 17;
    xor.b32 %r7, %r7, %r8;
    shl.b32 %r8, %r7, 5;
    xor.b32 %r7, %r7, %r8;
    ld.global.u32 %r9, [%rd5];
    setp.ne.u32 %p1, %r9, %r7;
    @%p1 atom.global.add.u32 %r11, [%rd6], 1;
    add.u32 %r4, %r4, %r6;
    bra $L_loop;
$L_done:
    ret;
}
"""

CUDA = C.CDLL("nvcuda.dll")
for _n in ("cuMemAlloc_v2", "cuMemFree_v2", "cuCtxCreate_v2"):
    if not hasattr(CUDA, _n):
        raise RuntimeError(f"nvcuda.dll lacks {_n}")


def check(rc, what):
    if rc != 0:
        raise RuntimeError(f"{what} failed: CUresult {rc}")


def smi(field):
    try:
        return subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={field}", "--format=csv,noheader,nounits"],
            encoding="utf-8", stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "?"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gib", type=float, default=12.0)
    ap.add_argument("--passes", type=int, default=3)
    a = ap.parse_args()

    check(CUDA.cuInit(0), "cuInit")
    dev = C.c_int()
    check(CUDA.cuDeviceGet(C.byref(dev), 0), "cuDeviceGet")
    ctx = C.c_void_p()
    check(CUDA.cuCtxCreate_v2(C.byref(ctx), 0, dev), "cuCtxCreate")
    check(CUDA.cuCtxSetCurrent(ctx), "cuCtxSetCurrent")

    mod = C.c_void_p()
    check(CUDA.cuModuleLoadDataEx(C.byref(mod), PTX.encode(), 0, None, None), "cuModuleLoadDataEx")
    fill = C.c_void_p()
    chk = C.c_void_p()
    check(CUDA.cuModuleGetFunction(C.byref(fill), mod, b"vfill"), "get vfill")
    check(CUDA.cuModuleGetFunction(C.byref(chk), mod, b"vcheck"), "get vcheck")

    block, grid = 256, 80 * 32
    words = int(a.gib * (1 << 30)) // 4
    p = C.c_uint64()
    rc = CUDA.cuMemAlloc_v2(C.byref(p), C.c_size_t(words * 4))
    if rc != 0:
        # WDDM budget may still be settling; retry smaller once.
        words = int(a.gib * (1 << 30)) // 8
        rc = CUDA.cuMemAlloc_v2(C.byref(p), C.c_size_t(words * 4))
    check(rc, "cuMemAlloc")

    err = C.c_uint64()
    check(CUDA.cuMemAlloc_v2(C.byref(err), C.c_size_t(4)), "cuMemAlloc(err)")

    print(f"buffer {words * 4 / 2**30:.2f} GiB, {a.passes} passes, "
          f"mem {smi('clocks.current.memory')} MHz, {smi('temperature.gpu')} C")

    bad_total, t0 = 0, time.time()
    for k in range(a.passes):
        seed = 0x9E3779B9 ^ (k * 0x85EBCA6B)
        args_f = (C.c_uint64 * 3)(p.value, words, seed)
        ptrs_f = (C.c_void_p * 3)(C.cast(C.byref(args_f, 0), C.c_void_p),
                                  C.cast(C.byref(args_f, 8), C.c_void_p),
                                  C.cast(C.byref(args_f, 16), C.c_void_p))
        CUDA.cuMemsetD32_v2(err, C.c_uint(0), C.c_size_t(1))
        check(CUDA.cuLaunchKernel(fill, grid, 1, 1, block, 1, 1, 0, None, ptrs_f, None), "launch fill")
        check(CUDA.cuCtxSynchronize(), "sync fill")

        args_c = (C.c_uint64 * 4)(p.value, words, seed, err.value)
        ptrs_c = (C.c_void_p * 4)(C.cast(C.byref(args_c, 0), C.c_void_p),
                                  C.cast(C.byref(args_c, 8), C.c_void_p),
                                  C.cast(C.byref(args_c, 16), C.c_void_p),
                                  C.cast(C.byref(args_c, 24), C.c_void_p))
        check(CUDA.cuLaunchKernel(chk, grid, 1, 1, block, 1, 1, 0, None, ptrs_c, None), "launch check")
        check(CUDA.cuCtxSynchronize(), "sync check")

        got = C.c_uint()
        check(CUDA.cuMemcpyDtoH_v2(C.byref(got), err, C.c_size_t(4)), "read err")
        bad_total += got.value
        print(f"  pass {k + 1}: {got.value} mismatched words   "
              f"(mem {smi('clocks.current.memory')} MHz, {smi('temperature.gpu')} C)")

    dt = time.time() - t0
    print("=" * 62)
    print(f"  total mismatches : {bad_total}")
    print(f"  data moved       : {2 * words * 4 * a.passes / 1e9:.1f} GB in {dt:.1f} s")
    print(f"  verdict          : {'PASS' if bad_total == 0 else 'FAIL - memory returns wrong data'}")
    print("=" * 62)
    CUDA.cuMemFree_v2(err)
    CUDA.cuMemFree_v2(p)
    return 0 if bad_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
