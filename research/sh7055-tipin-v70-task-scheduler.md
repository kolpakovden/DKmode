# v70 — SH7055 OEM Tip-in task scheduler and timing boundary

**Date:** 2026-10-20. **Status:** ROM-CONFIRMED STATIC TASK STRUCTURE; ACTUAL MILLISECOND PERIOD **NOT YET PROVEN**. Read-only research, no flashable ECU image.

## Source verification

- `Forester_SG9_MAP_clean_v39.bin`: 524288 bytes, SHA-256 `43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4`.
- `Forester_SG9_MAP_clean_v25.bin`: 524288 bytes, SHA-256 `2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99`.
- Byte-for-byte unchanged between both: scheduler descriptors `0x4640..0x47CF`, scheduler `0x37BC..0x3811` and `0x3F20..0x3F6F`, task-9 handler `0x6330..0x6369`, Tip-in call chain `0x1028C..0x1040F`.

> **v71 correction (2026-10-26):** records are indexed as `0x469C + 16*id` (not `0x46A0 + 16*i`). For task 9 the record is `0x472C`: +0 `04000200` (byte+2 = priority 2), +4 state `0xFFFF71E4`, +8 handler `0x6330`, +12 `02000000` (byte = activation limit 2). The `0x04000100` word that the original table attributed to task 9 belongs to task 10 (table replaced in v73). Wakeup source and period: see [v71](sh7055-tipin-v71-task9-wakeup.md).

## 19-task table (corrected in v73)

The 16-bit value at `ROM 0x4648` is `0x0013` = **19 tasks**. The literal `ROM[0x3810]` referenced by instruction `0x37C0` yields the anchor `0x0000469C`. The scheduler's `0x37C8: SHLL2 R13`, `0x37CA: SHLL2 R13`, `0x37CC: ADD R3,R13`, `0x37CE: MOV.L @(4,R13),R14` show **16-byte record indexing from `0x469C`** (record of task *id* = `0x469C + 16*id`). The original v70 text started the table at `0x46A0`, which shifted every field by one word; that version is superseded.

Record fields (proof): +0 flags, byte +2 = priority (`0x38EA MOV.B @(2,R11),R0`); +4 RAM state (`0x37CE`); +8 entry point (`0x37F4 MOV.L @(8,R13),R4`); byte +12 = activation limit (`0x3F50 MOV.B @(12,R13),R0` → state byte 3).

| Task | Record | Flags (+0) | Priority | RAM state | Entry | Activation limit |
| ---: | ---: | --- | ---: | --- | --- | ---: |
| 8 | `0x471C` | `04000200` | 2 | `0xFFFF71DC` | `0x6304` | 2 |
| **9** | **`0x472C`** | **`04000200`** | **2** | **`0xFFFF71E4`** | **`0x6330`** | **2** |
| 10 | `0x473C` | `04000100` | 1 | `0xFFFF71EC` | `0x63F2` | 2 |

All 19 records are enumerated by [the corrected SHA-pinned audit](../tools/analysis/sh7055_task_v70_audit.py). **No record field encodes milliseconds**; the activation period comes from the CMT1 tick tree (see [v71](sh7055-tipin-v71-task9-wakeup.md)).

## Verified call path

```text
Task #9 record @ ROM 0x472C (entry field at 0x4734)
  RAM state = 0xFFFF71E4; callback = 0x6330
  0x634A PC-relative MOV.L -> ROM[0x63D4] = 0x0001028C
  0x634C JSR @R3  -> process multiple ECU subsystems
    0x10372 PC-relative MOV.L -> ROM[0x10570] = 0x000170E8
    0x10374 JSR @R3
      0x170F6 BSR 0x171C6 -> current processed signal minus sample from two updates earlier
    ... other processing ...
    0x103F0 PC-relative MOV.L -> ROM[0x105C4] = 0x00024A04
    0x103F2 JSR @R2 -> OEM Tip-in uses native Delta TPS
  0x6364 JMP @R2 -> common task/yield routine 0x3DB8
```

The input/history calculation and OEM Tip-in are executed **in that order in the same task invocation**. As the handler references and call sites are shared by v25/v39, their scheduling *structure* was not altered by the v39 calibration changes.

`0xCD4E` calls `0x38B4` with `R4=9`, a task-index-dependent status/probe path. It does not by itself establish when task #9 wakes up or whether it is dispatched periodically.

## What can be calculated — and what cannot

From the verified history-shift code at `0x171C6`, under regularly spaced task-9 updates:

```text
delta[n] = conditioned_throttle[n] - conditioned_throttle[n-2]
T_delta_comparison = 2 × T_task9
```

Neither `T_task9` nor its jitter/conditional skip behavior is established from the ROM task descriptor. It would be **unsound** to claim "Subaru calculates Delta TPS every 10 ms" or to interpret `0x0100` as 256 ticks without decoding how the scheduler wakes task #9.

CarBerry's ~14.947ms update and ~29.895ms history window remain *conditional* on a presumed reference oscillator, from [HC16 research](carberry-hc16-tipin-trace.md), and are not measured Subaru timings.

## What to inspect next (specific v70 follow-up)

1. Ghidra SH7055: `0x37BC–0x3810`, `0x38B4–0x3932`, `0x3A1A–0x3A88`, `0x3F20–0x3F70`. Establish exact semantics of task 9 descriptor flags and runtime events.
2. Trace scheduler wake/event posting paths back to an interrupt or timer. Examine IRQ vector table and timer configuration rather than inferring from task descriptor words.
3. Without ECU hardware, use an explicit parameter `T_task9` in the observer-only v71 simulator. Treat real timing as unknown; never label a chosen example "the Forester frequency".
4. At the bench stage, timestamp `0xFFFFB024` and `0xFFFFB028` changes, verify physical units and actual OEM enrichment response before any actuator modification.

**No new ROM or flash patch was generated.** No hardware verification.

Related: [v69 native Tip-in trace](sh7055-tipin-v69-static-trace.md), [independent SH7055 bridge specification](sh7055-tipin-bridge.md).
