# Flash step — structure only

No ROM is shipped here. This folder shows **how the flash wrapper is structured** so you can
write your own for your own image.

## What a flash wrapper does

1. **Self-elevate** (administrator is required for the driver-level override).
2. **Check the image exists** before touching anything.
3. **Load the override** through the VixLoader-style mechanism.
4. **Disable Fast Startup** so the override actually takes effect on the next boot.
5. **Reboot.**

> `vix_loader.bat` in the skeleton is a thin launcher for the GPL-3.0
> [nvidia-windows-vbios-vix-loader](https://github.com/artyom-beilis/nvidia-windows-vbios-vix-loader)
> (`python -m nvidia_vbios.windows_loader`). It is **not** included in this repository — install the
> loader yourself and place its launcher next to your flash script.

## Minimal skeleton

See [`flash_example.bat`](flash_example.bat) and [`restore_example.bat`](restore_example.bat). Replace `YOUR_ROM.rom` with your own image path.

## Rules that keep you out of trouble

- **Always ship a restore script next to the flash script.** The research used a fixed
  "restore to a known-good image" script and kept it in the same folder.
- **Never flash a ROM you did not derive from your own card's dump.**
- **Verify after every flash** — see [`../docs/SAFETY.md`](../docs/SAFETY.md) §3.
- **Do not commit ROMs.** `.gitignore` already blocks `*.rom`, `*.bin` and `flash_*.bat`.

## Why the wrapper is not just `nvflash -6`

The research used a **registry override** rather than a physical flash, so rollback is a reboot
away and the physical ROM is never rewritten. If you use `nvflash` instead, your risk profile is
completely different — read the SAFETY document first.
