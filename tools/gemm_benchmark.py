import torch
import time
import sys
import os
import subprocess

def query_gpu_telemetry(device_id=0):
    try:
        smi = r'C:\Windows\sysnative\nvidia-smi.exe' if os.path.exists(r'C:\Windows\sysnative\nvidia-smi.exe') else r'C:\Windows\system32\nvidia-smi.exe'
        cmd = [
            smi, f'-i={device_id}',
            '--query-gpu=clocks.current.graphics,clocks.current.memory,power.draw,temperature.gpu,pstate,clocks_event_reasons.hw_slowdown,clocks_event_reasons.sw_power_cap',
            '--format=csv,noheader,nounits'
        ]
        out = subprocess.check_output(cmd, encoding='utf-8').strip()
        parts = [x.strip() for x in out.split(',')]
        return {
            'core_mhz': float(parts[0]),
            'mem_mhz': float(parts[1]),
            'power_w': float(parts[2]),
            'temp_c': float(parts[3]),
            'pstate': parts[4],
            'hw_slowdown': parts[5],
            'sw_power_cap': parts[6]
        }
    except Exception:
        return None

def benchmark(device_id=0, N=8192, num_iters=500):
    if not torch.cuda.is_available() or torch.cuda.device_count() <= device_id:
        print(f"[!] Error: cuda device not available:{device_id}, device count: {torch.cuda.device_count()}")
        return

    device = torch.device(f'cuda:{device_id}')
    gpu_name = torch.cuda.get_device_name(device)
    print("=" * 75)
    print(f"[*] Target GPU : {gpu_name} (cuda:{device_id})")
    print(f"[*] Matrix size : {N} x {N}  (theoretical per-GEMM: {2 * (N**3) / 1e12:.3f} TFLOPs)")
    print(f"[*] Iterations : {num_iters}")
    init_telem = query_gpu_telemetry(device_id)
    if init_telem:
        print(f"[*] Initial telemetry : core {init_telem['core_mhz']:.0f}MHz | mem {init_telem['mem_mhz']:.0f}MHz | power {init_telem['power_w']:.1f}W | temp {init_telem['temp_c']:.0f}C | P-State {init_telem['pstate']}")
    print("=" * 75)

    # =========================================================================
    # Test 1: pure Tensor Core FP16 GEMM
    # =========================================================================
    print("\n[Test 1/2] pure FP16 Tensor Core GEMM (hardware limit)...")
    A_fp16 = torch.randn(N, N, dtype=torch.float16, device=device)
    B_fp16 = torch.randn(N, N, dtype=torch.float16, device=device)
    C_fp16 = torch.empty(N, N, dtype=torch.float16, device=device)

    # warm up
    for _ in range(100):
        torch.mm(A_fp16, B_fp16, out=C_fp16)
    torch.cuda.synchronize(device)

    start_event = torch.cuda.Event(enable_timing=True)
    end_event = torch.cuda.Event(enable_timing=True)

    start_event.record()
    for _ in range(num_iters):
        torch.mm(A_fp16, B_fp16, out=C_fp16)
    end_event.record()
    torch.cuda.synchronize(device)

    gemm_telem = query_gpu_telemetry(device_id)
    gemm_time_ms = start_event.elapsed_time(end_event)
    gemm_time_sec = gemm_time_ms / 1000.0
    gemm_flops = 2.0 * (N ** 3) * num_iters
    gemm_tflops = (gemm_flops / gemm_time_sec) / 1e12

    print(f"  -> elapsed: {gemm_time_sec:.4f} s (avg per iter: {gemm_time_ms / num_iters:.2f} ms)")
    print(f"  -> pure Tensor Core throughput: {gemm_tflops:.2f} TFLOPs")
    if gemm_telem:
        print(f"  -> runtime telemetry: core {gemm_telem['core_mhz']:.0f}MHz | mem {gemm_telem['mem_mhz']:.0f}MHz | power {gemm_telem['power_w']:.1f}W | temp {gemm_telem['temp_c']:.0f}°C")
        if gemm_telem['hw_slowdown'] != 'Not Active':
            print(f"     [!] Warning: HW slowdown active ({gemm_telem['hw_slowdown']})")

    # free memory
    del A_fp16, B_fp16, C_fp16
    torch.cuda.empty_cache()

    # =========================================================================
    # Test 2: end-to-end AMP pipeline
    # =========================================================================
    print("\n[Test 2/2] end-to-end AMP pipeline (autocast + bias add)...")
    A_fp32 = torch.randn(N, N, dtype=torch.float32, device=device)
    B_fp32 = torch.randn(N, N, dtype=torch.float32, device=device)
    bias_fp32 = torch.randn(N, N, dtype=torch.float32, device=device)

    # warm up
    with torch.autocast(device_type='cuda', dtype=torch.float16):
        for _ in range(20):
            _ = torch.matmul(A_fp32, B_fp32) + bias_fp32
    torch.cuda.synchronize(device)

    start_event.record()
    with torch.autocast(device_type='cuda', dtype=torch.float16):
        for _ in range(num_iters):
            _ = torch.matmul(A_fp32, B_fp32) + bias_fp32
    end_event.record()
    torch.cuda.synchronize(device)

    amp_telem = query_gpu_telemetry(device_id)
    amp_time_ms = start_event.elapsed_time(end_event)
    amp_time_sec = amp_time_ms / 1000.0
    amp_flops = (2.0 * (N ** 3) + (N ** 2)) * num_iters
    amp_tflops = (amp_flops / amp_time_sec) / 1e12

    print(f"  -> elapsed: {amp_time_sec:.4f} s (avg per iter: {amp_time_ms / num_iters:.2f} ms)")
    print(f"  -> AMP end-to-end throughput:  {amp_tflops:.2f} TFLOPs")
    if amp_telem:
        print(f"  -> runtime telemetry: core {amp_telem['core_mhz']:.0f}MHz | mem {amp_telem['mem_mhz']:.0f}MHz | power {amp_telem['power_w']:.1f}W | temp {amp_telem['temp_c']:.0f}°C")

    # =========================================================================
    # summary
    # =========================================================================
    print("\n" + "=" * 75)
    print("                     Summary")
    print("=" * 75)
    print(f"  1. hardware limit (pure FP16 GEMM) : {gemm_tflops:6.2f} TFLOPs")
    print(f"  2. framework pipeline (PyTorch AMP+Bias): {amp_tflops:6.2f} TFLOPs")
    overhead_pct = (1.0 - (amp_tflops / gemm_tflops)) * 100.0 if gemm_tflops > 0 else 0
    print(f"  * framework overhead             : {overhead_pct:.1f}%")
    print("=" * 75)

if __name__ == '__main__':
    # defaults: GPU 0, 8192x8192, 500 iters
    benchmark(device_id=0, N=8192, num_iters=200)
