# Third-party notices

This project builds on work by others. Nothing below is redistributed in this repository —
each component is either quoted for attribution (MIT requires the notice to travel with
substantial portions) or used as an external dependency.

---

## 1. nouveau — `nvkm/subdev/bios/init.c`

**Used by:** `tools/disasm_init.py` — the init opcode table (`init_opcode[]`) and the meaning of
each opcode are derived from this file.

**Licence:** MIT

```
Copyright 2012 Red Hat Inc.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
THE COPYRIGHT HOLDER(S) OR AUTHOR(S) BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

Authors: Ben Skeggs
```

Source: <https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/tree/drivers/gpu/drm/nouveau/nvkm/subdev/bios/init.c>

---

## 2. nvidia-vbios-vix-editor

**Licence:** GPL-3.0 (full text in [`LICENSE`](LICENSE))

**Not redistributed.** Install it separately and point `NVBIOS_EDITOR_SRC` at its `src` directory.

Source: <https://github.com/artyom-beilis/nvidia-vbios-vix-editor>

### 2.1 What is used directly (API calls)

| API | Used by | For |
|---|---|---|
| `nvidia_vbios.rom.structure.scan_images` | `tune_core.py`, `apply_vfe_gpc_offset.py`, `dump_clkprog_all.py`, `dump_img3_mems.py`, `diff_sxm3.py` | locating the PCI / NPDS images and their checksums |
| `nvidia_vbios.rom.structure.parse_bit` | `dump_clkprog_all.py` | walking the BIT token structure |
| `nvidia_vbios.rom.structure.gpc_curve_slot` | `apply_vfe_gpc_offset.py` | finding the GPC curve root, its link byte and a free VFE slot |
| `nvidia_vbios.rom.structure.vfe_constant_mhz` | `apply_vfe_gpc_offset.py` | building the constant-MHz equation that carries the offset |

### 2.2 What is derived from its documentation and implementation

This is the part worth stating plainly: several **core architecture concepts and layouts used
throughout this repository were established by that project, not by this one**:

- **The single-chain `0xE0` / `e0end` representation format**: identifying that Windows kernel display
  driver `nvlddmkm.sys` only accepts single-chain VBIOS payloads in registry overrides (`EnableGpuFirmware = 0x11`).
  The method of truncating the dump to terminate at the primary NPDS data image (type `0xE0`) with the
  PCIR `last-image` indicator bit set (known as the `turing-e0-end-v1` / `e0end` representation) was originated
  and documented by Artyom Beilis;
- **NPDS checksum balancing**: the checksum rule where every sub-image (including type `0xE0` data blocks)
  must satisfy `sum(bytes) % 256 == 0`, and the technique of balancing modified tables by adjusting the
  trailing checksum byte;
- **The VFE root / slot / constant-equation mechanism**: the internal format of the Voltage-Frequency
  Equation table (kind byte, variable byte, next link, five 32-bit floats) and the elegant technique of
  allocating a free VFE slot as a constant-MHz equation and inserting it into the root link chain to offset
  the curve without touching polynomial coefficients (`gpc_curve_slot`, `vfe_constant_mhz`);
- **The BIT token chain**: walking the BIT header and locating sub-table pointers (`clkprog`, `clocks`,
  P-State, power, VFE);
- **The factory-clock offset layout**: decoding the factory-clock entries (`A0` for core, `A1` for memory)
  with their flag byte and signed 32-bit kHz payload;
- **Clock table offset windows**: interpreting the per-domain offset windows (GPC / XBAR / DRAM / SYS …)
  and the meaning of their `usage` / `min` / `max` fields.

What this repository adds on top is the **empirical characterisation** of those fields on one board:
which ones actually change hardware behaviour, the measured relationships between them, and the
approaches that do not work (see `docs/notes.md`).

If you are looking for the origin of the parsing logic and payload structure, go to that project — it deserves
the credit and the bug reports.

---

## 3. nvidia-windows-vbios-vix-loader

**Used by:** the flash wrapper described in `examples/` — invoked as a module
(`python -m nvidia_vbios.windows_loader`) to apply a registry-level VBIOS override.

**Licence:** GPL-3.0

**Not redistributed.** Install it separately.

Source: <https://github.com/artyom-beilis/nvidia-windows-vbios-vix-loader>

**Derived concept:**
The entire methodology of applying non-volatile-free, safe VBIOS modifications on modern Windows via
`EnableGpuFirmware = 0x11` and `GpuFirmwareImage*` binary registry entries in the display device key was
reverse-engineered, documented, and packaged by Artyom Beilis in `nvidia-windows-vbios-vix-loader`. This
repository relies directly on that driver loading pathway for all experiments.

---

## 4. Licence compatibility note

- nouveau's `init.c` is **MIT**, which is compatible with (and may be incorporated into) a
  **GPL-3.0** work, provided the copyright notice and permission notice are preserved — hence the
  full text above.
- Both vix-editor and vix-loader are **GPL-3.0**. Because this project imports/invokes them and is
  distributed as source, it is licensed **GPL-3.0** as a whole.
- This project contains **no** NVIDIA proprietary code, **no** firmware images and **no** driver
  binaries.
