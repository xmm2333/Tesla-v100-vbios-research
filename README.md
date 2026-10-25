# Tesla V100 VBIOS research

Structural analysis of the VBIOS on a **Tesla V100-SXM2-16GB** (GV100, `10de:1db1`), plus the
tooling used to characterise and tune clock-related fields.

> **No firmware is included.** To reproduce any of this you must dump the VBIOS of your own card
> (GPU-Z → *Save BIOS*, or `nvflash --save`). Everything here operates on a dump you supply.
> **This repository is completed by AI** AI may make mistakes.You use this software entirely at your own risk.
> Any modification you make with it, anything derived from it or from its output, and any damage that results,
> is solely your responsibility. AT LEAST USING AI AGENT TO CHECK THIS PROJECT BEFORE USING IT!
---

## Configuration

Three settings, applied in this order. The values below are the *method* — pick your own targets and
verify each step on hardware.

### 1. Power table — both rails together

Row 2 (NVVDD, the core rail) and row 4 (TGP, the board total) must be raised **together**. Raising
only the TGP row leaves the core rail limiting. Going past the board's delivery ceiling is rejected
outright, so this is a ceiling to find, not a number to maximise.

### 2. Factory-clock offset (`A0`) — the only fabric-clock lever

`A0` is the single field that moves XBAR. Start small (`+150`), then raise in steps of 50. Keep the
GPC report field consistent with it — a mismatch between `A0` and the GPC value means a corrupted
field, not a working configuration.

### 3. VFE curve offset — compensate the voltage shift

Raising `A0` makes the PMU evaluate the voltage curve at a lower frequency, so the core runs
undervolted at the same clock. A negative curve offset shifts the lookup back. **Raise `A0` and the
VFE offset together**, keeping the net lookup constant.

### The relationships

```
XBAR           ≈ stock_XBAR + 0.91 × (A0 − 100)
Max Clocks      = 1912 + A0
net VFE lookup  = target clock − A0 + |VFE offset|
```

### Reference configuration

The combination verified end-to-end on the reference board:

| Field | Value |
|---|---|
| `A0` (factory clock offset) | **+350** |
| GPC report (P-State header + row1) | **1912** |
| XBAR / SYS P-State fields | stock — inert, leave them |
| VFE curve offset | **−150** |
| `P+0x38` target clock | stock (1388) |
| Power table rows 2 / 4 | 450 W |

The two numbers that matter as a pair are `A0` and the VFE offset. Their sum fixes the net lookup:

```
net lookup = target clock − A0 + |VFE offset|
           = 1897 − 350 + 150 = 1697
```

Keep that net lookup constant and `A0` can be raised further; let it fall and the core starts
producing wrong results before it ever crashes.

### What to leave alone

| Field | Why |
|---|---|
| `P+0x38` target clock | stock value; modifying it corrupts the init instruction stream |
| XBAR / SYS P-State fields | inert — writing them does not change the fabric clock |
| Memory gear tables | reporting and timing only; the memory PLL ignores them |
| VFE clamp slot | moving it drags the real core clock down with it |

---

## How it works

Three findings make the result reproducible.

### 1. XBAR is driven by the factory-clock offset (`A0`), and nothing else

The P-State XBAR and SYS fields are inert, and the per-domain offset windows are `0..0` on Tesla
parts. Only `A0` moves the fabric clock:

```
XBAR ≈ stock_XBAR + 0.91 × (A0 − 100)     [MHz]
```

The slope was derived from stepwise measurements on one board; the constant depends on your stock
fabric clock, so read it from your own baseline rather than assuming a number.

### 2. Raising `A0` costs voltage headroom — and that can be compensated

```
Max Clocks = 1912 + A0
PMU looks up the VFE curve at (target frequency − A0)
```

So a higher `A0` makes the core run undervolted at the same clock. The fix is a **negative VFE
curve offset**, which shifts the lookup back:

```
net lookup = target − A0 + |VFE offset|
```

Keeping `net lookup` constant while raising `A0` gives more fabric clock at the same core voltage.
This is what makes high `A0` usable — without it the core runs into silent computation errors.

### 3. `pwr` / `thrm` throttle flags are not a reliable signal

They were observed set on a configuration that was otherwise completely healthy (idle at 39 °C /
62 W, clock stable under sustained load, zero GEMM errors). **Judge by measured power, clock
stability and computation correctness — not by the flag.**

Full field offsets, the verification procedure and the list of approaches that do **not** work are
in [`docs/notes.md`](docs/notes.md).

---

## Reproducing

Full walkthrough in [`docs/REPRODUCING.md`](docs/REPRODUCING.md). The short version:

1. **Dump your own VBIOS** and record the stock numbers.
2. **Verify the table layout on your image** with `dump_clkprog_all.py` / `dump_img3_mems.py` —
   every offset here was observed on one dump and may differ on other firmware revisions.
   **Do not write to an unverified offset.**
3. Compute `A0` and the VFE offset from the formulas above.
4. Generate the image, flash through a registry override, and check that `Max Clocks` stays in the
   2000–2300 range (a value near 1000 means the curve broke).
5. Run the four-part verification gate before trusting it: curve intact, `min == max` under load,
   GEMM zero errors, full-VRAM integrity pass.
6. Iterate upward only after all four pass.

## Tools

| Tool | Purpose |
|---|---|
| `tune_core.py` | Write A0 / GPC / XBAR / SYS / P+0x38 fields from parameters |
| `apply_vfe_gpc_offset.py` | Apply a VFE curve offset (MHz, may be negative) |
| `disasm_init.py` | Disassemble the Volta init bytecode (no third-party deps) |
| `dump_clkprog_all.py` / `dump_img3_mems.py` | Dump clock-programming and NPDS entries |
| `diff_sxm3.py` | Anchor-aligned diff between two dumps |
| `gemm_benchmark.py` | FP16 GEMM throughput **and error check** |
| `mem_bw_test.py` / `mem_integrity_test.py` | Bandwidth and full-VRAM integrity |
| `nvapi_pstates.py` | Read P-State info via NVAPI |

Requirements: Windows 10/11, driver 537.13, Python 3.9+. Some tools import
[nvidia-vbios-vix-editor](https://github.com/Panchovix/nvidia-vbios-vix-editor) — install it
yourself and point `NVBIOS_EDITOR_SRC` at its `src` directory.

## Licence and third parties

GPL-3.0 (see [`LICENSE`](LICENSE)).

**A significant part of the architecture and parsing groundwork comes from
[nvidia-vbios-vix-editor](https://github.com/Panchovix/nvidia-vbios-vix-editor) and
[nvidia-windows-vbios-vix-loader](https://github.com/Panchovix/nvidia-windows-vbios-vix-loader)**:
- The **single-chain `0xE0` (`e0end`) payload structure** needed to bypass the Windows driver's registry override buffer limitation;
- The **VFE curve root / slot / constant-equation insertion mechanism** for applying non-destructive curve offsets;
- The **driver registry override pathway** (`EnableGpuFirmware = 0x11`);
- The **BIT token parsing, factory-clock (`A0`/`A1`) layout**, and per-domain clock table offset windows.

This repository uses their APIs and builds directly on those concepts; the contribution here is
the empirical characterisation of how those fields behave on Volta (GV100), including the exact
interplay between `A0`, XBAR and VFE undervolting, and what does not work.

Full attribution and licence texts: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

This project contains no NVIDIA proprietary code, no firmware images and no driver binaries.

Read [`DISCLAIMER.md`](DISCLAIMER.md) before flashing anything.
