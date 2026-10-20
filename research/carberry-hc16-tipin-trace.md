# CarBerry HC16 → DKmode — Tip-in input signal trace (v58)

**Status:** REFERENCE (instruction trace) + HYPOTHESIS (physical meaning). **OFFLINE RESEARCH ONLY — DO NOT FLASH.**  
**Recorded:** 2026-10-20  
**Source:** CarBerry 4.2 HC16 160-KiB reference `work2_100+95_3D04EA4605_CarBerry42_FULL_160KiB.bin`, SHA-256 `b06e1282a4b274db856d250ae8a1babaf175729f7f9e9fec12e465fb774a4483`. Addresses below are **CarBerry HC16 disassembly/program addresses**, not Subaru SH7055 ROM offsets. Evidence: pasted Ghidra disassembly from reverse-engineering conversation (2026-10-20). Secondary source/bank mapping is not independently verified against the exact MCU manual.

## Scope and target separation

- **Reference:** 68HC16-based CarBerry firmware; reconstruct data path and behavior, not transplant machine code.
- **Potential DKmode target:** Forester SG9 STI JDM Denso SH7055 512 KiB, ROM family A2WC012E / historical modified A2WC0MME.
- **Current stated target baseline:** `Forester_SG9_MAP_clean_v39.bin`, SHA-256 `43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4`. No on-car confirmation in this research.
- No claim that a neutral hook or previous bench-only ROM implements CarBerry Tip-in; no flashable artifact delivered.

## Observed HC16 data flow

1. `0x001712`: `LDAB #0x0F; TBYK; LDY #0xF200`; loop on `LDE 0x10,IY`, `ANDE #0x2000` until bit set. `0x001726–0x00172A` re-establish `YK = 0xF`, `IY = 0xF200`.
2. `0x0017D6`: `LDD 0x01EC,IY` → effective 20-bit `0xFF3EC` **given YK=F and unchanged YK/IY**; `0x0017DA: STD 0x175E,IZ`.
3. `0x0018F0: LDD 0x175E,IZ`; `0x0018F4: STD 0x081C,IZ`.
4. `0x004D66: LDD 0x081C,IZ`; `0x004D6E: SUBD 0x03C8,IZ`; clear to zero on borrow. On `0xDC & 0x01` set, replace result with `0x0D00` (`LDAA #0x0D; CLRB`). `0x004D82: STAA 0x17C8,IZ` saves the **high 8 bits** of the resulting 16-bit D; `0x004D86: STD 0x17CC,IZ`.
5. `0x004DDC–0x004E04` reads `0x17C8`, subtracts `0x17D8`, produces biased-and-clamped 8-bit delta at `0x17DA`, shifts history `0x17D7 → 0x17D8`, `0x17C8 → 0x17D7`. The nominal representation is `clamp(128 + current - older_sample, 0, 255)`; arithmetic branch edge cases warrant explicit emulation.
6. `FUN_004E0A` copies `0x17DA → 0x17D9`. Initialization `0x006D50–0x006D60` sets both history entries from current and initializes `0x17D9`, `0x17DA` to neutral `0x80`.
7. `FUN_00A7C4` consumes `0x17D9` as a gated Tip-in input, checks ROM thresholds `0x0293F8..`, and computes enrichment using tables/helpers; downstream actuation and physical units remain unverified.

**Caution:** Searching for the literal encoding `STAA 0x17C8,IZ` found `0x004D82` and `0x006CF6`; this does not prove these are the only writes (other instruction forms, pointers, aliases). The `0x006CF6` occurrence is in an initialization routine.

## QADC configuration trace

- `0x0069FE: LDE #0x0030`; `0x006A02: STE 0x006C,IY` → `0xFF26C` under the established `YK/IY` setup.
- The adjacent instructions configure successive words `0xFF25C=0x0039`, `0xFF25E=0x0038`, `0xFF260=0x0037`, `0xFF262=0x0036`, `0xFF264=0x0035`, `0xFF266=0x0033`, `0xFF268=0x0032`, `0xFF26A=0x0031`, `0xFF26C=0x0030`, `0xFF26E=0x0003` etc.
- Candidate interpretation: QADC CCW slot 30 selects channel code `0x30`, result is read at `0xFF3EC`. **Validate against the exact 68HC16Y5/QADC register map, conversion-result numbering, and CCW bitfields.** Channel code does *not* by itself prove the vehicle sensor is TPS.
- End of sampling routine: `0x00198C: BCLRW 0x10,IY,0x2000` and `0x001992: BSETW 0x0E,IY,0x2000`; the actual update period has not been measured.

## Adaptive subtraction baseline RAM 0x03C8

The value subtracted from `0x081C` is **mutable**, not a hardcoded constant.

| Location | Observed behavior | Calibration |
| --- | --- | --- |
| `0x0012F8–0x0012FC` | Initialize `RAM[0x03C8]` from ROM | `0x028671` |
| `0x004ECA–0x004ED6` | Reset baseline when `0xDC & 0x01` is set; clear `0x17D4` | `0x028671` |
| `0x004F10–0x004F2C` | Increase baseline by step with saturation at `0xFFFF`, then cap | step `0x028667`, max `0x02866D` |
| `0x004F32–0x004F7C` | Conditionally decrease baseline, saturate at zero, then floor | step `0x028669`, min `0x02866F` |

Increase branch (when all applicable gates pass):
```text
B := min(0xFFFF, B + ROM16[0x028667])
B := min(B, ROM16[0x02866D])
```
Decrease branch (when all applicable gates pass):
```text
E := max(0, B - ROM16[0x028669])
E := max(E, ROM16[0x02866F]) // 004F72 CPE; 004F76 BCC; 004F78 LDE minimum
RAM16[0x03C8] := E            // 004F7C STE 0x03C8,IZ
```

**Specific newly closed trace**:
```asm
004F72  CPE  offset DAT_02866F,EK
004F76  BCC  LAB_004F7C
004F78  LDE  offset DAT_02866F,EK
004F7C  STE  DAT_0003C8,IZ
004F80  CLRE
004F82  LDD  0x001B,IZ
004F84  CPD  offset DAT_02865D,EK
004F88  BCS  LAB_004FB6
004F8A  LDD  0x00EC,IZ
004F8C  SUBD 0x00EA,IZ
004F8E  BCS  LAB_004FB6
004F90  CPD  offset DAT_028661,EK
```

Thus the down branch has a verified **calibration-controlled lower bound**, not merely clamping to zero. The subsequent flow from `0x004F80` should not be mistaken for continued baseline reduction: it starts a separate next section.

**Unresolved:** meaning of `RAM[0x03C8]` (adaptive zero/reference is a working hypothesis, not proven TPS calibration); actual constants at `0x02865C..0x028671`, flags/gates (`0x17D2`, `0xDC`, etc.); real QADC input wiring; update/scheduler cadence and scaling; table axis units; activation-to-fuel-output mapping.

## Proposed next research steps

1. Extract **exact 16-bit and 8-bit ROM calibration values** `0x02865C–0x028671` using the known Ghidra endian/bank context. Capture bytes and interpreted values, rather than assuming calibration names.
2. Validate QADC register and result/CCW correspondence for the **actual** CarBerry HC16Y5 variant; identify what physical sensor maps to channel code `0x30` using ECU schematic, sensor probing, or authoritative mapping.
3. Inspect `0x004F80–0x004FBC` to distinguish further baseline logic from adjacent processing.
4. Identify caller/scheduler timing for `FUN_001712`, `FUN_004D5E`, `FUN_004E0A`, and `FUN_00A7C4`; reproduce two-sample deltas with a controlled timing model.
5. Only afterward define an **independent SH7055 implementation spec** using confirmed native v39 throttle data (prefer known physical units), normalization, state, gates, and logging. Do not patch production ROM at this stage.

## Cross references

- [SD / transient fueling baseline](sd-tip-in.md)
- [Sources and provenance](../docs/source-register.md)
- [Architecture and patch lifecycle](../docs/architecture.md)
- Original historical research: [forester_A2WC012E](https://github.com/kolpakovden/forester_A2WC012E)

**Confidence rule:** observed instructions are facts about the supplied disassembly; labels such as TPS, channel identity, physical units, sampling rate, and engineering suitability remain hypotheses until independently corroborated.
