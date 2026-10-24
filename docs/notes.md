# Field notes — Tesla V100-SXM2-16GB VBIOS

Everything below was established against a dump of one card (GV100, `10de:1db1`, driver 537.13).
Offsets are relative to the start of the relevant image and **may differ on other firmware
revisions** — locate tables by their headers rather than trusting absolute addresses.

---

## 1. Image layout

The dump contains a PCI image and two NPDS images. The clock-related content lives in:

| Image | Contains |
|---|---|
| PCI (first) | clock-programming table, clock table (per-domain offset windows), init bytecode |
| NPDS #1 (second) | clock table, P-State table, power table, VFE curve table, factory-clock entries |
| NPDS #2 (third) | voltage-domain entries and other blocks, not characterised |

## 2. Field map (NPDS #1, offsets for this dump)

| Field | Offset | Encoding | Meaning |
|---|---|---|---|
| Factory clock A0 | `0x33220` | flag byte at `0x3321F`, then s32 kHz | core clock offset |
| Factory clock A1 | `0x33224` | same layout | memory clock offset (reporting only) |
| Clock table entry0, 3rd field | `0x30B23` | u16 = MHz/4 | must match the GPC value below |
| P-State header GPC | `0x30B6E` | u16 `flag\|MHz` + u16 ratio | drives `Max Customer Boost Clocks` |
| P-State row1 GPC | `0x30BC0` | same | |
| P-State row0 XBAR | `0x30B97` | u16 `0x8000\|MHz` + u16 ratio | **inert** — see §3 |
| P-State row2 SYS | `0x30BE9` | same | **inert** |
| P+0x38 target | `0x384A9` / `0x387FB` | u16 MHz | stock 1388; modifying it corrupts the init stream |
| Power table row 2 (NVVDD) | `0x32A1D` | 54 B/row | `+2` current, `+6` default mW, `+10` limit mW |
| Power table row 4 (TGP) | `0x32A89` | 54 B/row | same layout |
| VFE table | `0x3160E` | 150 slots × 24 B | curve equations; slot 13 = 1904.47, slot 14 = 1912.0 clamp |
| VFE GPC offset | slot 42 constant equation, linked from root 9 | 5 floats | curve offset in MHz (may be negative) |

## 3. What does **not** drive the clock

### 3.1 Clock tables → reporting and timing only

The memory gear appears in the clock-programming table (PCI image), the clock table (NPDS #1) and
the P-State rows. All of them must agree, or the firmware refuses to initialise. But changing the
gear consistently across all of them **changes the reported value without changing the frequency the
memory actually runs at** — verified by requesting a gear *below* stock and observing the measured
clock stay put.

### 3.2 The init script is a shared template

The PLL-related byte sequence in the PCI image is **byte-identical across four dumps of different
V100 variants**, including one that ships with a higher memory gear. It is bring-up boilerplate,
not a per-board frequency source.

### 3.3 Cross-image consistency is enforced

Substituting the PCI image from another variant makes the device fail to initialise: the firmware
expects the images to belong together.

### 3.4 XBAR and SYS P-State fields are inert

Writing them has no effect on the fabric clock. Only `A0` moves it.

## 4. The `A0` mechanism

```
XBAR      ≈ 1544 + 0.91 × (A0 − 100)      [MHz]
Max Clocks = 1912 + A0
VFE lookup = target frequency − A0
```

Because the voltage lookup follows `A0`, raising it lowers the voltage the core receives at a given
clock. A negative VFE offset compensates:

```
net lookup = target − A0 + |VFE offset|
```

Measured (this board):

| A0 | XBAR | net lookup for 1897 MHz | note |
|---|---|---|---|
| +100 | 1544 | 1797 | factory value |
| +175 | 1612 | 1722 | |
| +250 | 1687 | 1647 | voltage noticeably low |
| +300 | 1732 | 1697 | with VFE −100 |
| +350 | ~1770 | 1697 | with VFE −150 |

**The failure mode of over-raising `A0` without compensation is silent computation error**, not a
crash. Always re-run the GEMM error check.

## 5. Negative results

| Attempt | Outcome |
|---|---|
| Change the memory gear in every table consistently | reported value changes, actual clock does not |
| Raise the gear above stock | timing behaviour degrades, clock unchanged |
| Swap in the PCI image from another variant | device fails to initialise |
| Write the XBAR / SYS P-State fields | no effect on the fabric clock |
| Exceed the board power ceiling | immediate rejection |
| Large negative VFE offset (e.g. −45 alone) | curve collapses; `Max Clocks` drops to ~1000 |
| Raise `A0` without voltage compensation | silent computation errors |
| Overwrite the PLL target immediate in the init script | breaks the instruction stream; telemetry reads N/A |

## 6. Verification gate

Every change was accepted only if all of the following held:

```bash
# 1. curve intact?  Max Clocks should stay in the ~2000-2300 range, not ~1000
nvidia-smi -q -d CLOCK | grep -A2 "Max Clocks"

# 2. stable under load?  min must equal max
nvidia-smi --query-gpu=clocks.current.sm,power.draw,temperature.gpu --format=csv -lms 500

# 3. computation correct?  undervolt shows up as wrong results, not errors
python tools/gemm_benchmark.py

# 4. memory intact?
python tools/mem_integrity_test.py --gib 8 --passes 2
```

## 7. Open questions

- **Memory frequency is not solved.** The gear can be changed in every place the driver reads it,
  and the reported value follows — but the clock the memory actually runs at does not move. The
  target is most likely produced by PMU microcode combined with board strapping, i.e. outside the
  VBIOS. A runtime BAR0 write (the approach used by the CMP-170HX tooling) is the only route not
  attempted here.
- Several blocks in the NPDS images remain uncharacterised.
