"""V100 HBM2 bandwidth benchmark via CUDA Driver API + runtime-JIT PTX.

No third-party packages: ctypes talks to nvcuda.dll directly and the driver's PTX
JIT compiles the kernel below at load time.  A grid-stride float4 copy is
memory-bandwidth bound, so GB/s tracks the HBM2 PHY frequency directly - unlike a
GEMM, which is Tensor-Core bound and blind to memory clocks.

Usage:
    python mem_bw_test.py [--gib 2] [--iters 30] [--seconds 6]
"""
import argparse
import ctypes as C
import json
import subprocess
import sys
import time

PTX = r"""
.version 6.4
.target sm_70
.address_size 64

.visible .entry vcopy(
    .param .u64 p_src,
    .param .u64 p_dst,
    .param .u64 p_bytes
)
{
    .reg .pred %p<2>;
    .reg .b32 %r<8>;
    .reg .b64 %rd<24>;
    .reg .f32 %f<17>;

    ld.param.u64 %rd1, [p_src];
    ld.param.u64 %rd2, [p_dst];
    ld.param.u64 %rd3, [p_bytes];

    mov.u32 %r1, %ctaid.x;
    mov.u32 %r2, %ntid.x;
    mov.u32 %r3, %tid.x;
    mad.lo.s32 %r4, %r1, %r2, %r3;
    cvta.to.global.u64 %rd4, %rd1;
    cvta.to.global.u64 %rd5, %rd2;
    mul.wide.s32 %rd6, %r4, 16;
    mov.u32 %r5, %nctaid.x;
    mul.lo.s32 %r6, %r5, %r2;
    mul.wide.s32 %rd7, %r6, 16;
    add.s64 %rd8, %rd7, %rd7;
    add.s64 %rd9, %rd8, %rd7;
    add.s64 %rd10, %rd9, %rd7;

    add.s64 %rd11, %rd4, %rd6;
    add.s64 %rd12, %rd11, %rd7;
    add.s64 %rd13, %rd12, %rd7;
    add.s64 %rd14, %rd13, %rd7;
    add.s64 %rd15, %rd5, %rd6;
    add.s64 %rd16, %rd15, %rd7;
    add.s64 %rd17, %rd16, %rd7;
    add.s64 %rd18, %rd17, %rd7;
    add.s64 %rd19, %rd4, %rd3;

$L_loop:
    setp.ge.u64 %p1, %rd11, %rd19;
    @%p1 bra $L_done;
    ld.global.nc.v4.f32 {%f1, %f2, %f3, %f4}, [%rd11];
    ld.global.nc.v4.f32 {%f5, %f6, %f7, %f8}, [%rd12];
    ld.global.nc.v4.f32 {%f9, %f10, %f11, %f12}, [%rd13];
    ld.global.nc.v4.f32 {%f13, %f14, %f15, %f16}, [%rd14];
    st.global.v4.f32 [%rd15], {%f1, %f2, %f3, %f4};
    st.global.v4.f32 [%rd16], {%f5, %f6, %f7, %f8};
    st.global.v4.f32 [%rd17], {%f9, %f10, %f11, %f12};
    st.global.v4.f32 [%rd18], {%f13, %f14, %f15, %f16};
    add.s64 %rd11, %rd11, %rd10;
    add.s64 %rd12, %rd12, %rd10;
    add.s64 %rd13, %rd13, %rd10;
    add.s64 %rd14, %rd14, %rd10;
    add.s64 %rd15, %rd15, %rd10;
    add.s64 %rd16, %rd16, %rd10;
    add.s64 %rd17, %rd17, %rd10;
    add.s64 %rd18, %rd18, %rd10;
    bra $L_loop;

$L_done:
    ret;
}
"""

CUDA = C.CDLL("nvcuda.dll")
# Windows exports both the legacy 32-bit-size entry points and the _v2 ones;
# ctypes binds by name, so the legacy cuMemAlloc would truncate 64-bit sizes.
for _name in ("cuMemAlloc_v2", "cuMemFree_v2", "cuMemsetD8_v2", "cuCtxCreate_v2"):
    if not hasattr(CUDA, _name):
        raise RuntimeError(f"nvcuda.dll lacks {_name}")


def check(rc, what):
    if rc != 0:
        raise RuntimeError(f"{what} failed: CUresult {rc}")


def smi(fields):
    try:
        out = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            encoding="utf-8", stderr=subprocess.DEVNULL).strip()
        return [x.strip() for x in out.split(",")]
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gib", type=float, default=2.0, help="buffer size per side")
    ap.add_argument("--iters", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=0.0, help="run batches for this long instead of --iters")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    check(CUDA.cuInit(0), "cuInit")
    dev = C.c_int()
    check(CUDA.cuDeviceGet(C.byref(dev), 0), "cuDeviceGet")
    ctx = C.c_void_p()
    check(CUDA.cuCtxCreate_v2(C.byref(ctx), 0, dev), "cuCtxCreate")
    check(CUDA.cuCtxSetCurrent(ctx), "cuCtxSetCurrent")

    module = C.c_void_p()
    check(CUDA.cuModuleLoadDataEx(C.byref(module), PTX.encode(), 0, None, None), "cuModuleLoadDataEx")
    func = C.c_void_p()
    check(CUDA.cuModuleGetFunction(C.byref(func), module, b"vcopy"), "cuModuleGetFunction")

    block = 256
    grid = 80 * 32
    chunk = grid * block * 64                      # one full unrolled pass
    nbytes = int(a.gib * (1 << 30)) // chunk * chunk

    # WDDM shrinks the CUDA budget right after a boot or while the driver is
    # re-initialising, so a 2 GiB request can fail once and succeed a second
    # later.  Retry, then halve, instead of dying on the first refusal.
    src_p, dst_p = C.c_uint64(), C.c_uint64()
    for attempt in range(12):
        if nbytes < chunk:
            raise SystemExit("could not allocate buffers (budget too small)")
        if CUDA.cuMemAlloc_v2(C.byref(src_p), C.c_size_t(nbytes)) == 0:
            if CUDA.cuMemAlloc_v2(C.byref(dst_p), C.c_size_t(nbytes)) == 0:
                break
            CUDA.cuMemFree_v2(src_p)
        if attempt % 2 == 1:
            nbytes = nbytes // 2 // chunk * chunk
        time.sleep(0.5)
    else:
        raise SystemExit("could not allocate buffers")
    if nbytes != int(a.gib * (1 << 30)) // chunk * chunk:
        print(f"# note: buffer reduced to {nbytes / 2**30:.3f} GiB (allocation refused)",
              file=sys.stderr)

    check(CUDA.cuMemsetD8_v2(src_p, C.c_ubyte(0x3C), C.c_size_t(nbytes)), "memset src")
    check(CUDA.cuMemsetD8_v2(dst_p, C.c_ubyte(0x00), C.c_size_t(nbytes)), "memset dst")

    args = (C.c_uint64 * 3)(src_p.value, dst_p.value, nbytes)
    arg_ptrs = (C.c_void_p * 3)(
        C.cast(C.byref(args, 0), C.c_void_p),
        C.cast(C.byref(args, 8), C.c_void_p),
        C.cast(C.byref(args, 16), C.c_void_p))

    start, stop = C.c_void_p(), C.c_void_p()
    check(CUDA.cuEventCreate(C.byref(start), 0), "event")
    check(CUDA.cuEventCreate(C.byref(stop), 0), "event")

    def launch():
        return CUDA.cuLaunchKernel(func, grid, 1, 1, block, 1, 1, 0, None, arg_ptrs, None)

    for _ in range(3):
        launch()
    check(CUDA.cuCtxSynchronize(), "warmup")

    before = smi("clocks.current.memory,clocks.current.sm,power.draw,temperature.gpu")
    check(CUDA.cuEventRecord(start, None), "record")
    if a.seconds:
        # Batches are synchronised, so only completed passes are counted.
        iters, t_end = 0, time.time() + a.seconds
        while True:
            for _ in range(4):
                launch()
            check(CUDA.cuCtxSynchronize(), "sync")
            iters += 4
            if time.time() >= t_end:
                break
    else:
        iters = a.iters
        for _ in range(iters):
            launch()
    check(CUDA.cuEventRecord(stop, None), "record")
    check(CUDA.cuEventSynchronize(stop), "sync")
    ms = C.c_float()
    check(CUDA.cuEventElapsedTime(C.byref(ms), start, stop), "elapsed")
    elapsed_ms = ms.value
    after = smi("clocks.current.memory,clocks.current.sm,power.draw,temperature.gpu")

    moved = 2.0 * nbytes * iters          # read + write
    gbps = moved / (elapsed_ms / 1000.0) / 1e9
    result = dict(gib=round(nbytes / 2 ** 30, 3), iters=iters, seconds=round(elapsed_ms / 1000, 3),
                  bandwidth_gbps=round(gbps, 2),
                  mem_clock_before=before[0] if before else None,
                  mem_clock_after=after[0] if after else None,
                  sm_clock=after[1] if after else None,
                  power_w=after[2] if after else None,
                  temp_c=after[3] if after else None)
    if a.json:
        print(json.dumps(result))
    else:
        print("=" * 64)
        print(f"  buffer      : {result['gib']:.3f} GiB per side")
        print(f"  iterations  : {iters}   elapsed {elapsed_ms/1000:.2f} s")
        print(f"  mem clock   : {result['mem_clock_before']} -> {result['mem_clock_after']} MHz")
        print(f"  sm clock    : {result['sm_clock']} MHz   power {result['power_w']} W   {result['temp_c']} C")
        print(f"  bandwidth   : {gbps:.1f} GB/s")
        print("=" * 64)
        for f, label in ((877, "877 MHz (1.75 Gbps)"), (927, "927 MHz"), (958, "958 MHz (SXM3)"), (1000, "1000 MHz")):
            print(f"    theoretical @ {label:22s}: {f*2*4096/8/1000:7.1f} GB/s")

    CUDA.cuMemFree_v2(src_p)
    CUDA.cuMemFree_v2(dst_p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
