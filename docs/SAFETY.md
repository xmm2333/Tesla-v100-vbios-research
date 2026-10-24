# Safety and recovery

Read this before flashing anything. Every item here exists because it was needed at some point.

## 0. Non-negotiables

1. **Back up your original VBIOS first.** Without a reference dump you cannot tell what changed.
   ```bash
   # GPU-Z → "Save BIOS", or: nvflash --save backup.rom
   ```
2. **Know your recovery path before you start.** Safe Mode does not load the GPU driver, so any
   registry-level override becomes inert and the physical ROM is used.
3. **Do not flash on the GPU that drives your display** unless you have no alternative.

## 1. How the override works

The research used a **registry-based VBIOS override**, not a physical flash:

- the driver reads an override image from a registry value at boot;
- clearing that value reverts to the physical ROM on the next boot;
- the physical ROM is never rewritten.

```
load override → reboot → verify → keep, or clear to roll back
```

If you use `nvflash` instead of an override, your risk profile is entirely different — a failed
physical flash may require an external programmer.

## 2. Recovery ladder

Try in order; stop as soon as the card is healthy.

| # | Action | Situation |
|---|---|---|
| 1 | Clear the override value, reboot | GPU missing, driver fails to initialise |
| 2 | Boot Safe Mode, clear the override, reboot | Normal boot hangs |
| 3 | Re-apply a known-good image | Card works but the configuration is wrong |
| 4 | Physical reflash from the backup | Override corrupted |

Keep a known-good image **and** a restore script in the same folder as the flash script.

## 3. Verification gate

Run after every change, in this order:

```bash
# 1. did the voltage/frequency curve survive?
nvidia-smi -q -d CLOCK | grep -A2 "Max Clocks"

# 2. is the clock stable under load?  min should equal max
nvidia-smi --query-gpu=clocks.current.sm,power.draw,temperature.gpu --format=csv -lms 500

# 3. is the computation correct?  undervolt shows up as wrong results, not errors
python tools/gemm_benchmark.py

# 4. is memory intact?
python tools/mem_integrity_test.py --gib 8 --passes 2
```

## 4. Danger signals

| Signal | Likely meaning | Action |
|---|---|---|
| maximum clock collapses to a very low value | curve table broken | revert immediately |
| clock samples show `min < max` under load | real throttling | inspect power / temperature / voltage |
| GEMM reports non-zero errors | undervolt | undo the last change |
| power draw pinned low under load | configuration rejected by the power model | undo the last change |
| card disappears from `nvidia-smi` | driver rejected the image | revert |

## 5. About throttle flags

`SW Power Cap` and `SW Thermal Slowdown` were observed set on a configuration that was otherwise
completely healthy — idle power and temperature far below any limit, clock stable under sustained
load. Treat these flags as a **model state**, not as a verdict. Judge by measured behaviour:
power draw, clock stability, computation correctness.

## 6. Undervolt is the real risk

Changing the factory-clock offset shifts the frequency the voltage curve is evaluated at, so the
core can end up running at a lower voltage for the same clock. **The failure mode is silent data
corruption, not a crash.**

If you change the offset, re-run the full verification gate — especially the GEMM error check —
and be prepared to back the change out.
