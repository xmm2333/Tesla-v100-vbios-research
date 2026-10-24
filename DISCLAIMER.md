# Disclaimer

**This is not legal advice. If you plan to distribute anything derived from this work, consult a lawyer in your jurisdiction.**

## 1. What this repository does NOT contain

- **No NVIDIA firmware.** No `.rom`, `.bin` or any VBIOS image, in whole or in part.
- **No driver binaries or patches** for `nvlddmkm.sys` or any NVIDIA driver.
- **No third-party source code.** Libraries such as `nvidia-vbios-vix-editor`, `170tune` or `cmpunlocker` are referenced as external dependencies and are **not** vendored here.
- **No proprietary code extracted from any NVIDIA product.** Documentation describes *observed data structures and field offsets* obtained by reading a dump of the author's own hardware — it does not reproduce NVIDIA source code.

## 2. Legal considerations you should understand

Firmware modification sits in a grey area that differs by country:

| Topic | Typical concern |
|---|---|
| **Copyright** | A VBIOS image is a copyrighted work. *Redistributing* an image (modified or not) is generally infringement. *Analysing your own dump* for interoperability/research is treated more leniently in many jurisdictions, but not universally. |
| **Anti-circumvention** | The US DMCA §1201, the EU InfoSoc Directive Art. 6 and similar provisions in other countries restrict circumventing technical protection measures. Some jurisdictions provide research/interoperability exemptions; many do not. |
| **Contract / EULA** | NVIDIA's driver and software licence terms commonly prohibit reverse engineering, modification and redistribution. Breaching them is a contractual matter, separate from copyright. |
| **Warranty** | Modifying firmware will void the hardware warranty. |
| **Export / sanctions** | High-performance accelerators may be subject to export controls in some jurisdictions. |

**Practical guidance if you publish your own fork:**

1. **Never publish firmware images.** Share tooling and documentation; let others dump their own card.
2. **Never publish driver patches.** Describe the method instead.
3. **Do not copy code from projects whose licence you have not checked.** `170tune` and `cmpunlocker` have their own terms — link to them, do not re-host them.
4. **Keep the research framing explicit**: interoperability, repair, education. Avoid language that suggests bypassing licensing or enabling infringement.
5. **Respect local law.** If you are unsure whether publishing a specific offset table is permitted where you live, ask before publishing.

## 3. Hardware risk

Flashing a modified VBIOS can:

- brick the card (no POST, no display, unrecoverable without an external programmer);
- corrupt data silently through undervolt-induced computation errors;
- damage the card through overcurrent or overheating;
- void the warranty and any service contract.

**You are solely responsible for any damage to hardware, data or third parties.**

## 4. No warranty

The software and documentation are provided "AS IS", without warranty of any kind. The authors accept no liability for any claim, damage or other liability arising from the use of this material.

## 5. Trademarks

NVIDIA, Tesla, V100 and related marks are trademarks of NVIDIA Corporation. This project is not affiliated with, endorsed by, or supported by NVIDIA.
