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


## EK proven set to bank 2 in boot/dispatcher (2026-10-20)

Researcher's Ghidra disassembly:

```asm
0009C8  LDAB #0x02
0009CA  TBEK
...
000A72  LDAB #0x02
000A74  TBEK
```

At those instruction points **EK=2** is established explicitly, so EK-relative displacement `0x865C` yields logical `0x2865C` **if no intervening callee changes EK**. The supplied text confirms the bank assignment, but does not prove bank-preservation through all nested calls. Two other `TBEK` instances were not found in the analyzed mnemonic search; incompletely disassembled code could still contain bank modifications.

Ghidra Memory Map is file-backed `0x000000–0x027FFF` (160 KiB), so `0x02865C–0x02867A` is **out of range** for this loaded image. This is not fixed by choosing `0x00865C`, nor by allocating an uninitialized memory block. Investigate whether source ROM dump is partial or uses another ROM bank/device mapping, and obtain source bytes covering the effective addresses. Do not fabricate calibration values.

**Recommended next action:** verify bin provenance/size and memory mapping; inspect how EK is preserved through earlier `FUN_000B40` and four calls before `FUN_004E0A`. Most importantly, obtain a full ROM image/companion calibration bank if one exists; otherwise mark those numeric calibrations as inaccessible in this reference.


## Corrected ROM file-to-CPU calibration mapping — inspected original binary (2026-10-20)

**Major correction to preceding missing-data hypothesis.** The researcher supplied the **actual** `original_carberry.bin`; byte inspection established size **163,840 bytes / 0x28000**, SHA-256 `b06e1282a4b274db856d250ae8a1babaf175729f7f9e9fec12e465fb774a4483`. Verified code instructions at file offsets `0x0009C8`, `0x000A72`, `0x004EEE` match Ghidra output. The BIN is **not proven truncated**.

The source image appears **packed from at least two disjoint logical memory segments**. The likely calibration mapping is:

```text
HC16 runtime 0x00000..0x1FFFF  <- BIN file 0x00000..0x1FFFF  (candidate)
HC16 runtime 0x28000..0x2FFFF  <- BIN file 0x20000..0x27FFF  (strong hypothesis)
                                      file offset = HC16 address - 0x8000
```

At file offset `0x20000`, the data begins with the embedded header `CopyrightDENSO2004`, followed by `CarBerry` and a contiguous table area. This lends strong structural support to a distinct calibration segment. Prior Ghidra import erroneously mapped the packed file contiguously `0x00000..0x27FFF`. The inferred runtime calibration `0x02865C` is located at **file offset `0x02065C`**, not at `0x00865C`, and the data at the corrected offset matches many independent calibration usages semantically. This is a **strongly supported mapping hypothesis**, pending independent physical MCU memory-map/dump confirmation.

### Values extracted directly from uploaded BIN

Big-endian unsigned interpretations (bytes are direct file observations; roles are from disassembled control flow):

| HC16 address | File offset | Bytes | Unsigned | Inferred role |
|---|---|---|---:|---|
| 0x02865C | 0x02065C | 80 | 128 | 8-bit threshold |
| 0x02865D | 0x02065D | 00 7A | 122 | 16-bit threshold |
| 0x02865F | 0x02065F | 1C | 28 | low hysteresis threshold |
| 0x028660 | 0x020660 | 1E | 30 | high hysteresis threshold |
| 0x028661 | 0x020661 | 00 00 | 0 | 16-bit condition threshold |
| 0x028663 | 0x020663 | 00 42 | 66 | delta comparison threshold |
| 0x028665 | 0x020665 | 00 0C | 12 | adaptation condition threshold |
| 0x028667 | 0x020667 | 00 40 | 64 | upward step for 0x03C8 |
| 0x028669 | 0x020669 | 00 40 | 64 | downward step for 0x03C8 |
| 0x02866B | 0x02066B | 00 40 | 64 | required baseline-to-filtered gap |
| 0x02866D | 0x02066D | 3F 7D | 16253 | 0x03C8 upper cap |
| 0x02866F | 0x02066F | 0F 5C | 3932 | 0x03C8 lower floor |
| 0x028671 | 0x020671 | 3F 7D | 16253 | initial/reset 0x03C8 |
| 0x02867A | 0x02067A | 00 96 | 150 | 0x17DC counter threshold |
| 0x0293F8 | 0x0213F8 | 82 | 130 | Tip-in activation threshold (byte compare; units unverified) |
| 0x0293F9 | 0x0213F9 | 04 | 4 | repeat/counter guard |
| 0x0293FA | 0x0213FA | 00 60 | 96 | threshold for calculated transient term |
| 0x0293FC | 0x0213FC | 00 24 | 36 | 0x0B04 guard threshold |

**Interpreting the corrected baseline**: init `B=16253`, permitted range [3932,16253], symmetric step 64 (per qualifying update, not per millisecond). Actual physical units and update frequency remain unknown. Qualifying flags and time gating must be replicated before this has tuning meaning.

**Recommended Ghidra fix:** keep an untouched backup of the current project. In the working copy, create a *file-backed mapped block* starting at `0x028000`, length `0x8000`, from original file bytes offset `0x020000`, or reimport using a documented segmented loader. Do not create an uninitialized RAM block or fill with `FF`. Avoid assuming all addresses use `file offset = logical - 0x8000`; this correction is for the identified high calibration segment. Check that `Go To 0x02865C` displays `80 00 7A 1C 1E 00 00 ...` and `0x0293F8` displays `82 04 00 60 00 24`. Any old cross-reference/data analysis based on contiguous mapping must be revalidated.

**Priority changes:** correct the Ghidra memory map; confirm the high segment base and ECU ROM decode; then compute exact calibration units and scheduler interval. The previous claim that calibration bytes are *missing* is **superseded** by direct file evidence.


## Calibration bank helper and preliminary scale/scheduling evidence (2026-10-20)

The **actual uploaded** `original_carberry.bin` was independently verified by hashing and byte inspection: 163,840 bytes, SHA-256 `b06e1282a4b274db856d250ae8a1babaf175729f7f9e9fec12e465fb774a4483`. Example file bytes:

```text
BIN 0x20000: 80 10 43 6F 70 79 72 69 67 68 74 44 45 4E 53 4F ... ('CopyrightDENSO2004')
BIN 0x2065C: 80 00 7A 1C 1E 00 00 00 42 00 0C 00 40 00 40 00 40 ...
BIN 0x213F8: 82 04 00 60 00 24
```

A **Ghidra Java helper** is committed at [`tools/ghidra/MapCarBerryCalibrationBank.java`](../tools/ghidra/MapCarBerryCalibrationBank.java). It checks existing memory, selects existing imported FileBytes, and maps original byte range `0x20000–0x27FFF` into additional runtime memory block `0x28000–0x2FFFF`; it verifies expected markers at `0x2865C`, `0x28667` and `0x293F8`. It never writes a modified BIN. **Status: source reviewed against official Ghidra Memory API, not executed in Ghidra yet.** Save a separate copy of the Ghidra program before running. Parsed values available in [calibration CSV](carberry-calibration-values.csv).

### Tip-in threshold and physical units — conditional estimate only

Observed in `FUN_00A7C4`: activation threshold byte at `0x0293F8` is **0x82**; differential signal's neutral code is **0x80**. Thus the minimal positive *coded* delta meeting `CMPA #0x82; BCS return` is **2** high-byte units, subject to other gates.

For standard **10-bit unsigned left-justified QADC** output (see Motorola QADC reference), the 16-bit result has `ADC10 << 6`, so `1` unit of the high byte corresponds to `4` raw 10-bit counts. Then `2` units correspond to **8 raw ADC counts**, approximately **8/1023 = 0.78% of ADC full scale**. This is a *conditional estimate*, not a confirmed percent throttle opening, and near boundaries the precise original raw difference is quantized. Physical channel-to-TPS wiring, signedness/format of actual read, baseline `0x03C8`, and sampling interval still need verification. Do not transfer this value directly to SH7055 TPS percentage.

### Two scheduler domains — need timing

A previously unexamined code slice around `0x00033C–0x000350` was inspected as bytes:

```asm
00033C  LDAA  0x08B1,IZ
000340  CMPA  #0x07
000342  BCC   (branch to clear-counter path)
000344  INCA
000346  STAA  0x08B1,IZ
00034A  BRA   (skip sampling block)
00034C  CLR   0x08B1,IZ
000350  JSR   FUN_004D5E
```

The branch structure suggests `FUN_004D5E` is performed **once per ~8 visits** to this handler (assuming no other writes/reset to `0x08B1` and the expected HC16 branch decode). This does *not* give milliseconds: the frequency/caller of this handler and concurrent updates are not established. The Tip-in calculation `FUN_00A7C4` is explicitly called at `0x000BE8` within `FUN_000BA6`, the same dispatched group as `FUN_004E0A` at `0x000BB6`. These can be distinct from the sample-history update schedule. A two-history-step comparison could therefore cover ~16 handler visits, but this is only a **hypothesis** until Ghidra branch targets/cadence are confirmed.

### Next validation

1. In Ghidra run the file-backed calibration mapping helper; return console MATCH/MISMATCH lines and Memory Map screenshot.
2. Disassemble `0x00033C–0x000354`, follow direct caller or interrupt-vector relationship, and search writes to `RAM[0x08B1]`.
3. Establish actual QADC result format and whether channel code 0x30 truly corresponds to the vehicle TPS signal.
4. Determine update intervals for `FUN_004D5E` vs `FUN_004E0A/FUN_00A7C4` before estimating delta-TPS in percent per second.

## Cross references

- [SD / transient fueling baseline](sd-tip-in.md)
- [Sources and provenance](../docs/source-register.md)
- [Architecture and patch lifecycle](../docs/architecture.md)
- Original historical research: [forester_A2WC012E](https://github.com/kolpakovden/forester_A2WC012E)

**Confidence rule:** observed instructions are facts about the supplied disassembly; labels such as TPS, channel identity, physical units, sampling rate, and engineering suitability remain hypotheses until independently corroborated.
