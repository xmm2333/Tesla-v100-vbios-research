# tools/

All scripts operate on a VBIOS dump **you** supply — none of them contain firmware.

## Dependencies

| Dependency | Needed by |
|---|---|
| Python 3.9+ | all |
| [nvidia-vbios-vix-editor](https://github.com/artyom-beilis/nvidia-vbios-vix-editor) | `tune_core.py`, `apply_vfe_gpc_offset.py`, `dump_*.py`, `diff_sxm3.py` |
| PyTorch + CUDA | `gemm_benchmark.py` |
| CUDA runtime / NVAPI | `mem_bw_test.py`, `mem_integrity_test.py`, `nvapi_pstates.py` |

`disasm_init.py` needs **nothing** beyond the standard library.

Point the scripts at the editor's source tree:

```bash
# PowerShell
$env:NVBIOS_EDITOR_SRC = "D:\path\to\nvidia-vbios-vix-editor\src"
# cmd
set NVBIOS_EDITOR_SRC=D:\path\to\nvidia-vbios-vix-editor\src
# bash
export NVBIOS_EDITOR_SRC=/path/to/nvidia-vbios-vix-editor/src
```

## Usage

```bash
# Disassemble the init script region
python disasm_init.py --rom my_rom.rom --start 0x7930 --count 60

# Diff two dumps of the same family
python diff_sxm3.py --a my_rom.rom --b other_rom.rom

# Write clock fields (always keep a copy of the input)
python tune_core.py --base my_rom.rom --a0 <n> --gpc <n> --xbar <n> --sys <n> --out tuned.rom

# Apply a VFE curve offset (negative raises the voltage the core sees)
python -c "from apply_vfe_gpc_offset import apply_offset; \
           apply_offset('tuned.rom', 'final.rom', <offset_mhz>)"

# Verification gate
python gemm_benchmark.py
python mem_integrity_test.py --gib 8 --passes 2
```

## Notes

- Field offsets in the scripts are those observed in one dump; **verify them against yours** before
  writing (see `docs/notes.md` §2).
- `tune_core.py` requires `--base`; there is no default image.
- Nothing here touches the driver or the network — the scripts only read and write local files.
