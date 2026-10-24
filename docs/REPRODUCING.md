# Reproducing the result

Step-by-step for someone starting from their own card. Read [`SAFETY.md`](SAFETY.md) first.

> **The single biggest risk:** every offset in this repository was observed on **one** dump
> (V100-SXM2-16GB, driver 537.13). Other firmware revisions may place the tables elsewhere.
> **Never write to an offset you have not verified on your own image.** Step 2 exists for that.

---

## Prerequisites

| Item | Requirement |
|---|---|
| GPU | Tesla V100 SXM2 (the methods were characterised on the 16 GB variant) |
| Driver | 537.13 (other versions untested) |
| OS | Windows 10/11 |
| Python | 3.9+ |
| Libraries | [nvidia-vbios-vix-editor](https://github.com/artyom-beilis/nvidia-vbios-vix-editor), PyTorch+CUDA |
| Flash method | a registry-override wrapper, so rollback is a reboot away |

Set the library path once:

```bash
set NVBIOS_EDITOR_SRC=D:\path\to\nvidia-vbios-vix-editor\src
```

---

## Step 0 — Back up and baseline

```bash
# dump your VBIOS (GPU-Z → Save BIOS, or nvflash --save)
copy my_rom.rom my_rom.original.rom
```

Record the stock numbers before changing anything:

```bash
nvidia-smi --query-gpu=clocks.max.sm,clocks.current.memory,power.limit --format=csv
```

Write them down. Without a baseline you cannot tell whether a change did anything.

> **Important — Single-chain (`e0end`) payload requirement:**
> A full raw SPI dump from GPU-Z or nvflash is typically ~330 KiB and contains redundant multi-chain flash. The Windows driver's registry override buffer accepts only a **single complete image chain** ending at the last data image (type `0xE0`, exact size 253,440 bytes on our reference dump).
> Before modifying or flashing via registry override, normalize your dump using Vix Editor (`--representation turing-e0-end-v1`, which exports `<name>-loader-e0end.bin`) or ensure your working image is truncated to the primary 253,440-byte chain (carrying the last-image flag on Image 3). Overriding with an un-truncated multi-chain dump will be rejected by `nvlddmkm.sys`.

---

## Step 1 — Confirm the tables are where this repository says

Run the dumpers on **your** image and compare against `notes.md` §2:

```bash
python tools/dump_clkprog_all.py my_rom.rom
python tools/dump_img3_mems.py my_rom.rom
```

What you are checking:

| Check | Expected |
|---|---|
| `clkprog` table found, 23 entries | matches §2 of the notes |
| P-State rows readable, 10 rows | each row starts with a memory gear value |
| Factory-clock entry present | header bytes `10 06 05 02 05 02` |
| VFE table parses | 150 slots, a clamp value near 1912 |

**If any of these fail, stop.** Your firmware differs; re-derive the offsets with the dumpers
before writing anything.

To confirm a candidate offset is the right field, change it by a small amount and check that the
*reported* value moves:

```bash
python tools/tune_core.py --base my_rom.rom --a0 110 --gpc 1900 --xbar 1900 --sys 1900 --out probe.rom
# flash probe.rom, reboot, then:
nvidia-smi -q -d CLOCK | grep -A2 "Max Clocks"
```

A `Max Clocks` shift of roughly the amount you added confirms you are writing the right field.

---

## Step 2 — Compute the parameters

Two numbers decide the outcome: the factory-clock offset `A0` and the VFE curve offset.

```
XBAR      ≈ stock_XBAR + 0.91 × (A0 − 100)
Max Clocks = 1912 + A0
net VFE lookup = target clock − A0 + |VFE offset|
```

Work backwards from what you want:

1. Pick a target `A0` (start at `+150`, not `+350` — see below).
2. Compute the net lookup you need for your target core clock.
3. Set `VFE offset = A0 − target clock + desired net lookup`.

Keep the **net lookup at or above the stock value for that clock**. Going below it means the core is
undervolted, which shows up as wrong results rather than a crash.

---

## Step 3 — Generate the image

```bash
# write the clock fields
python tools/tune_core.py --base my_rom.rom --a0 150 --gpc 1912 --xbar 1900 --sys 1900 --out stage1.rom

# add the curve offset (negative raises the voltage the core sees)
python tools/apply_vfe_gpc_offset.py --base stage1.rom --offset -50 --out stage2.rom
```

Verify the result before flashing:

```bash
python tools/dump_img3_mems.py stage2.rom     # fields should read back as intended
nvidia-smi -q -d CLOCK                         # after flashing, Max Clocks must stay sane
```

---

## Step 4 — Flash

Use the registry-override approach (see `../examples/`). Keep the restore script in the same folder.

> **Reboot requirement:** Perform a complete reboot (`shutdown /r /t 0`) rather than a standard shutdown, or ensure Windows Fast Startup is disabled (`HiberbootEnabled = 0`), otherwise the driver restores its cached session and skips loading the new registry override.

After reboot, the first thing to check is that the curve survived:

```bash
nvidia-smi -q -d CLOCK | grep -A2 "Max Clocks"
```

**A `Max Clocks` near 1000 means the VFE table broke** — restore immediately. A value in the
2000–2300 range means the table is intact.

---

## Step 5 — Verify (all four must pass)

```bash
# 1. curve intact
nvidia-smi -q -d CLOCK | grep -A2 "Max Clocks"

# 2. stable under load — min must equal max
nvidia-smi --query-gpu=clocks.current.sm,power.draw,temperature.gpu --format=csv -lms 500

# 3. computation correct — zero errors required
python tools/gemm_benchmark.py

# 4. memory intact
python tools/mem_integrity_test.py --gib 8 --passes 2
```

If any fails, go back one step. Do not stack another change on an unverified one.

---

## Step 6 — Iterate upward

Only after all four checks pass at `A0 +150`:

1. raise `A0` by 50,
2. increase the VFE offset by the same amount to keep the net lookup constant,
3. repeat Step 5.

Stop when either the GEMM check reports errors, power draw stops rising under load, or the clock
samples show `min < max`.

Record every step — the useful artefact is the table of `A0` → XBAR → net lookup → result, not a
single final number.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Max Clocks` ≈ 1000 | VFE curve broken | restore; reduce the VFE offset magnitude |
| `dump_img3_mems.py` shows odd values | wrong offset for your firmware | re-derive with Step 1 |
| GEMM errors ≠ 0 | undervolt | raise the net lookup |
| power draw flat under load | configuration rejected | reduce `A0` |
| card disappears after reboot | image rejected | boot Safe Mode, clear the override |
| reported value changes, hardware does not | you are editing a reporting-only field | check `notes.md` §3 |

## What you cannot reproduce

**The memory clock.** The gear can be changed in every table the driver reads, and the reported
value follows — the actual clock does not. That is documented as unsolved in `notes.md` §7; do not
expect the methods here to move it.
