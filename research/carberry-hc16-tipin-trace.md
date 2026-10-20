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


## Follow-up: FUN_004E0A full listing and EK bank uncertainty (2026-10-20)

Ghidra Memory Map supplied by the researcher: imported `RAM` block at `0x000000–0x027FFF` (length `0x28000`, backing `original_carberry.bin`), plus `IMB` at `0x0F0000–0x0FFFFF` (non-file-backed). Thus `DAT_02865C` inferred by Ghidra lies outside current file-backed block. Opening `0x00865C` instead exposes instructions (`LDE #0xFFFF`, `LDD #0xFFFF`, etc.), **not proven calibration**. Do **not** create uninitialized blocks and treat them as actual ROM bytes or assume a modulo address mapping.

Full pasted `FUN_004E0A` disassembly (`0x004E0A–0x004FBA`) contains **no `TBEK`**. Its only recorded caller is `FUN_000BA6` at `0x000BB6`. The current bank value must be traced in caller/call-chain or ECU startup initialization; Ghidra's `EK` offset annotation alone does not validate ROM file offsets.

New observations beyond the baseline-adaptation branches:

- `0x004E68–0x004E80`: `FUN_0087DE` updates `RAM[0x17C6]` using `RAM[0x17BE]`, previous state and argument setup; precise math remains unresolved.
- `0x004E84–0x004EA4`: absolute 16-bit difference between `0x17BE` and `0x17C2` gates `0x17E6` accumulation via calibration `0x028663`.
- `0x004EA8–0x004EC6`: threshold-based bit-2 hysteresis/state `0x17D2` through `0x02865F`/`0x028660`.
- `0x004F80–0x004FBA`: independent `0x17DC` counter/state gate, compared against `0x02867A`, setting bit 7 of `0x03CA` when threshold is reached. This is **after** the store at `0x004F7C` and does not itself write `0x03C8`.

**Highest-priority next step:** inspect `FUN_000BA6` around `0x000BA6–0x000BC0` plus its caller(s), and search `TBEK` in initialization/call chain. Identify any ROM load mapping/banking independently before extracting calibration values `0x02865C–0x02867A`. The physical TPS meaning remains unproven.


## Caller `FUN_000BA6` and bank propagation (2026-10-20)

Ghidra establishes a direct caller `FUN_0009EE:0x000AEA` -> `FUN_000BA6:0x000BA6`. The caller dispatches:
```asm
000BA6 JSR FUN_00D040
000BAA JSR FUN_008826
000BAE JSR FUN_00906A
000BB2 JSR FUN_008CD0
000BB6 JSR FUN_004E0A   ; updates/compares baseline 0x03C8
000BBA JSR FUN_004FBC
000BBE JSR FUN_004FF6
000BC2 JSR FUN_00503A
000BC6 JSR FUN_019A22
000BCA JSR FUN_019A4A
000BCE TEKB
000BD0 TBXK
000BD2 TBYK
```
**Correction on transfer direction:** `TEKB` copies EK **to** accumulator B (`EK -> B[3:0]`, high nibble cleared); `TBEK` is the reverse (`B -> EK`). `TBXK` and `TBYK` then transfer B to their respective banks, effectively synchronizing XK/YK with current EK after the listed calls, without modifying EK. This is documented in Motorola CPU16 Reference Manual Table 5-27: https://www.nxp.com/docs/en/reference-manual/CPU16RM.pdf

The value of EK on entry to `FUN_004E0A` is still unknown: inspect `FUN_0009EE` around `0x000ACA–0x000B00` AND possible `TBEK` in four predecessor callees (including nested calls), or global initialization. Neither the inferred `0x02865C` effective calibration address nor the file offset is yet proven.


## Dispatcher scheduling clue: FUN_0009EE at 0x000ACA–0x000B26 (2026-10-20)

Pasted Ghidra trace shows `FUN_0009EE` conditionally invokes `FUN_000B40` at `0x000AD8` **before** selecting among multiple task handlers. It increments byte `RAM[0x08AB]` at `0x000ADC–0x000AE2`; then uses `LSRA; BCS` to dispatch based on successive bits of the incremented counter. When the first tested (bit 0) is clear, `FUN_000BA6` is called at `0x000AEA`. Other branches call `FUN_000C58`, `FUN_000C9C`, `FUN_000D2E`, `FUN_000E68`, `FUN_000EAA`, `FUN_000EF0` etc. The earlier `ANDA #0xFC` and compare to `RAM[0x08AA]` additionally gate whether this dispatch runs at all. Thus the block appears to divide workloads among scheduler ticks; **actual wall-clock cadence remains unknown**, and it does not yet prove the invocation cadence of `FUN_004D5E` or `FUN_00A7C4`.

**Bank caveat:** This `0x000ACA–0x000B26` slice contains no `TBEK`. `FUN_000B40`, which runs before the selected branch, might alter bank state (not yet proven). Next inspect `FUN_000B40` and its callees, together with any `TBEK` instructions along the path leading into `FUN_000BA6`. Also verify earlier bank setup in `FUN_0009EE`, not visible in supplied slice.


## FUN_000B40 expanded dispatcher (2026-10-20)

Disassembly of `0x000B40–0x000BA4`: the function consists of 22 sequential `JSR` operations, two bank-alignment groups, and `RTS`; **no local `TBEK`**. Its first calls are `FUN_001B28`, `FUN_001CB4`, `FUN_001AFE`, `FUN_002242`, `FUN_00888E`, `FUN_0030F0`, `FUN_005252`, `FUN_0025E4`, `FUN_00263E`, `FUN_0199FC`, `FUN_003E1A`, `FUN_0097AE`, `FUN_003D18`, `FUN_015182`, `FUN_016196`, `FUN_0161C8`, followed by:
```asm
000B80  TEKB
000B82  TBXK
000B84  TBYK
000B86  JSR FUN_0177E8
000B8A  TEKB
000B8C  TBXK
000B8E  TBYK
000B90  JSR FUN_01B972
000B94  JSR FUN_019AF2
000B98  JSR FUN_012DEE
000B9C  JSR FUN_012206
000BA0  JSR FUN_000F5A
000BA4  RTS
```
Bank groups propagate `EK` to `XK` and `YK`, not vice versa. Their position suggests callers expect a coordinated bank context, but **does not determine EK**. Any nested callee could set it, and `FUN_000BA6` itself calls four routines before `FUN_004E0A`. A faster next step is a **program-wide `TBEK` listing with addresses**, then examine relevant callers/initializers rather than requesting all 22 callees. Also inspect `FUN_0009EE` prologue. Continue to treat `0x02865C` as an unverified Ghidra bank-derived address, not a ROM file offset.


## Ghidra TBEK mnemonic search results (2026-10-20)

Researcher screenshot of **Search Program Text → Instruction Mnemonics** reports two recognized `TBEK` instructions: **`0x0009CA` in `FUN_0009B6`**, and **`0x000A74` in `FUN_0009EE`**. This is a promising lead: `FUN_0009EE` dispatches to `FUN_000B40` at `0x000AD8`, then `FUN_000BA6` at `0x000AEA`, and `FUN_000BA6` calls `FUN_004E0A` at `0x000BB6`. The source of B at both `TBEK` instructions remains to be determined. Do **not** equate mnemonic-search results with proof of all possible executable `TBEK` bytes when analysis coverage may be incomplete; screenshot showed a Search Selection checkbox still checked (though results outside currently visible green selection appeared), so repeat full-program unrestricted search if necessary.

Next evidence requested: disassembly `0x0009B0–0x0009E0` and `0x000A58–0x000A90`, especially instructions loading B immediately before both `TBEK`. Then verify no intervening bank changes before `0x000BB6`; only after that map EK-relative calibration addresses to actual ROM bytes.

## Cross references

- [SD / transient fueling baseline](sd-tip-in.md)
- [Sources and provenance](../docs/source-register.md)
- [Architecture and patch lifecycle](../docs/architecture.md)
- Original historical research: [forester_A2WC012E](https://github.com/kolpakovden/forester_A2WC012E)

**Confidence rule:** observed instructions are facts about the supplied disassembly; labels such as TPS, channel identity, physical units, sampling rate, and engineering suitability remain hypotheses until independently corroborated.
