# v69 — Forester SH7055 v39: native Tip-in data flow

**Date:** 2026-10-20. **Status:** BINARY-VERIFIED REFERENCE + UNRESOLVED PHYSICAL UNITS/TIMING. **OFFLINE ONLY — NOT A FLASHABLE ROM.**

## Sources

- Source \`Forester_SG9_MAP_clean_v39.bin\`: 524288 bytes, SHA-256 \`43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4\`.
- Comparison v25: SHA-256 \`2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99\`.
- Verification: read-only big-endian SuperH 16-bit opcodes, PC-relative load/branch targets, literal reads, byte comparison, fixed binary hashes. Ghidra decompilation and in-car validation were **not** performed here.

Three ROM code ranges are **byte-identical in v25 and v39**: \`0x17150–0x1722D\`, \`0x24A04–0x24B71\`, \`0x102E0–0x10413\`.

## Proven invocation order

Within a large linear sequence of calls:

\`\`\`asm
10372 D37F MOV.L @(508,PC),R3 ; ROM[0x10570] = 0x000170E8
10374 430B JSR @R3
...
103F0 D274 MOV.L @(464,PC),R2 ; ROM[0x105C4] = 0x00024A04
103F2 420B JSR @R2
\`\`\`

At \`0x170F6\`, the first routine directly calls \`0x171C6\` (\`BSR\`). Thus **history/Delta TPS is updated before OEM Tip-in** in this sequence. The containing call chain starts with a prologue near \`0x1028C\`; it is called from \`0x0634A\` via a PC-relative pointer at ROM \`0x063D4\`. **Scheduler period remains unknown.**

## Conditioned input and fallback

The code at \`0x1716E–0x1718C\` computes:

\`\`\`text
v = RAM_float[0xFFFF90E4] - RAM_float[0xFFFF80E8] - RAM_float[0xFFFF80A0]
RAM_float[0xFFFFB020] = max(v, 0.0)    // helper 0x2444, FR5=0.0
\`\`\`

Then \`0x1718E–0x171C4\` checks byte results of \`0x1D376\` and \`0x1D38A\`:

\`\`\`text
when both condition results are zero: RAM_float[0xFFFFB024] = RAM_float[0xFFFFB020]
otherwise: RAM_float[0xFFFFB024] = ROM_float[0x57628] = 6.0
\`\`\`

Physical identity of \`0xFFFF90E4\` and engineering units of 6.0 are **not proven**; \`0xFFFFB024\` is an input conditioned for throttle/Tip-in processing, not raw ADC by itself.

## OEM two-sample Delta TPS from 0x171C6

The routine shifts 32-bit float history, then subtracts an earlier sample:

\`\`\`asm
171E4 9427 MOV.W ... R4       ; R4 = 0xFFFFB024
171E8 9327 MOV.W ... R3       ; R3 = 0xFFFFB028
171EA F348 FMOV.S @R4,FR3    ; current
171EC F63A FMOV.S FR3,@R6    ; 0xFFFFB02C <- current
171EE F366 FMOV.S @(R0,R6),FR3 ; R0=8 => 0xFFFFB034
171F0 F248 FMOV.S @R4,FR2
171F2 F231 FSUB FR3,FR2
171F4 F32A FMOV.S FR2,@R3    ; 0xFFFFB028 <- delta
\`\`\`

Two-step history shift from the preceding loop:

\`\`\`text
new[B034] = old[B030]
new[B030] = old[B02C]
new[B02C] = current[B024]
new[B028] = current[B024] - old[B030]
\`\`\`

**Conclusion:** just as in the HC16 reference, this Subaru implementation already compares the present sample to a two-update-earlier sample. Neither physical units nor update period are established equivalent.

## OEM Tip-in at 0x24A04

The address is the **function entry** (register-save prologue), reached via ROM pointer \`0x105C4\`. It is not an arbitrary hook or data table.

\`\`\`asm
24A14 D310 MOV.L PC,R3        ; literal 0xFFFFB8D8 — separate state (not Delta)
24A18 9218 MOV.W PC,R2        ; sign-extended literal 0xFFFFB028
24A20 410B JSR @R1           ; helper 0x1763A
24A22 FF28 FMOV.S @R2,FR15   ; delay-slot read of DELTA from B028
...
24A9C D343 MOV.L PC,R3        ; ROM[0x24BAC] = 0x00058DA4
24A9E F338 FMOV.S @R3,FR3    ; minimum Delta, raw float 0.2
24AA0 F3F5 FCMP/GT FR15,FR3  ; threshold > delta
24AA2 8D5B BT/S 0x24B5C      ; reject below min Delta
...
24B0C D32F MOV.L PC,R3        ; ROM[0x24BCC] = 0x00058DA8
24B18 F338 FMOV.S @R3,FR3    ; minimum calculated term, v39 raw float 25.0
24B1C F325 FCMP/GT FR2,FR3   ; threshold > computed
24B1E 8D1D BT/S 0x24B5C      ; reject below min calculated term
\`\`\`

Lookup/table descriptor references include \`0x54910\`, \`0x5455C\`, \`0x54924\` and helper \`0x209C\`. Other state RAM \`B814/B818/B821/B81C/B824/B8D8\` is used; precise purpose/actuator path is *unverified*. More Ghidra tracing of \`0x3980\`, \`0xD754\`, \`0x3994\` is required before describing injector pulse output as proven.

## Measured raw calibration bytes

| Offset | v25 | v39 |
|---|---:|---:|
| \`0x58DA4\` float32 (min delta) | 0.2 | 0.2 |
| \`0x58DA8\` float32 (min calculated quantity) | 250.0 | **25.0** |
| \`0x57628\` fallback float32 | 6.0 | 6.0 |
| \`0x59B84\` first six uint16 BE | 33,75,115,158,243,284 | **25,56,86,124,191,224** |

These are **raw encoded values**, not confirmed milliseconds/percentage display units. Older v25 conclusions about delayed enrichment do not automatically apply to v39.

## What v70 must establish

1. Measure/derive the schedule for the outer \`0x1028C\` sequence (upstream \`0x0634A\`); \`Delta=2×T_subaru_sample\` only with stable cycle rate.
2. Resolve \`0xFFFF90E4\` physical throttle unit, meanings of correction RAM \`0xFFFF80E8/80A0\` and gating helpers \`0x1D376/0x1D38A\`.
3. Identify exact side effects and output units of \`0x209C\`, \`0x3980\`, \`0xD754\`, \`0x3994\`.
4. Prototype **observer-only** comparison of v39 signal/threshold vs HC16 reference; do not add extra fueling until v39 baseline is measured on a bench.

No ECU/vehicle connected, no active ROM built, no claim of safe-to-flash firmware.

Related: [SH7055 observer-first design](sh7055-tipin-bridge.md), [CarBerry HC16 trace](carberry-hc16-tipin-trace.md), [original Forester v25 comparison](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/sd-transient-fueling.md).