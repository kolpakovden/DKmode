# DKmode — SH7055 Tip-in bridge specification (research v0)

**Status:** DESIGN PROPOSAL / OFFLINE-ONLY, not a compiled module, not an ECU patch. Date: 2026-10-20.

## Purpose and evidence boundary

Translate the *observable behavior* of CarBerry's HC16 Tip-in input/delta logic to a controlled, independent SH7055 design for Subaru Forester SG9 STI. Do **not** copy HC16 machine code, peripheral registers, RAM addresses, or calibration units into the SH7055 ROM. The source of truth for the target is independently validated **v39**, not v25 tables or earlier bench hooks.

- CarBerry reference: original 160-KiB HC16 BIN SHA-256 `b06e1282a4b274db856d250ae8a1babaf175729f7f9e9fec12e465fb774a4483`; [HC16 trace](carberry-hc16-tipin-trace.md).
- Proposed target: modified `Forester_SG9_MAP_clean_v39.bin`, 512 KiB, ROM ID `A2WC0MME`, expected SHA-256 `43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4`. Re-verify original byte length/hash before any build. No in-car confirmation available.
- Historical mapping and comparison in [forester_A2WC012E / SD transient fueling](https://github.com/kolpakovden/forester_A2WC012E/blob/main/docs/sd-transient-fueling.md) uses **v25**. Its `0x58DA8 = 1.000 ms` and other calibration values are not automatically representative of v39 and must be read anew in v39.

## Offline target v39 byte audit (actual source files)

Both CarBerry and Forester binaries are available in the local research session. The v39 target file is **actually present**, size 524,288 bytes and hash `43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4`. Comparison to original clean v25 (`2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99`) establishes:

| Forester BE ROM offset | v25 raw content | v39 raw content | Meaning/evidence boundary |
| --- | --- | --- | --- |
| `0x58DA4` | float32 `0.2` | float32 `0.2` | Minimum throttle-delta activation definition label; same raw |
| `0x58DA8` | float32 `250.0` | float32 **`25.0`** | Minimum pulse activation definition label; raw **10× lower** |
| `0x59B3C` | float32 `0.4` first axis value | float32 `0.4` | At least first axis value unchanged |
| `0x59B84` | first 6 uint16 BE: `33,75,115,158,243,284` | **`25,56,86,124,191,224`** | Actual Tip-in lookup table values are lower |

These observations are direct read-only byte extraction from pinned binaries, not guesses from XML. The older v25 document's statement `minimum pulse activation = 1.000 ms` refers to **v25 under its XML/display scaling**. If the same *linear* display scale applies to v39, a tenfold smaller raw value could correspond to 0.100 ms, **but that physical conversion must be checked in a suitable definition and in the consuming SH7055 function before presenting it as fact**.

**Implication:** A proposal to lower v39's threshold on the basis of the old v25 comparison is **not warranted**. v39 already has a far smaller raw activation threshold and lower initial Tip-in table entries. This makes observer-only A/B comparison against **actual v39** essential before enabling any new fuel actuator or additional pulse: double enrichment/rich spikes are plausible risks, not validated effects.

## HC16 behaviors supported by disassembly

- Analog result (candidate, vehicle TPS wiring not proven) -> subtraction of mutable 16-bit baseline `0x03C8` -> 8-bit high-byte signal `0x17C8`.
- Every **eight** executions of RTC vector `0xA0` ISR, `FUN_004D5E` updates two-byte sample history and computes `0x17DA`. Nominal steady-state behavior, apart from under/overflow edge paths:
  ```text
  q8[n] = top_byte_of_corrected_input
  encoded_delta[n] = clamp(128 + q8[n] - q8[n-2], 0, 255)
  ```
- `FUN_004E0A` publishes `0x17DA` to `0x17D9`; `FUN_00A7C4` checks `encoded_delta >= 0x82` plus additional gates, then enters transient computation. Actuator details, true QADC channel wiring, absolute TPS percent scaling are **not** validated.
- `SYNCR = B084`, `SYPCR = 0134`, `TIC/TIV=70A0`, `RTP=2EE0`. Under **related MC68HC16V1 SLIM slow-reference semantics** and an **assumed** 32,768-Hz oscillator: update spacing ≈14.9474 ms; sample-history comparison ≈29.8948 ms. This is **not measured ECU timing**.
- Source threshold `0x82` has no direct equivalence to Subaru percent opening. The older XML-based ~1.63% threshold and 8 ADC count / 0.78% full-scale rough estimate are **different coordinate systems**, not established as equivalent.

## v69 design correction: Subaru already has a two-step Delta TPS

The pinned **v39 OEM binary** (not merely a legacy XML definition) is documented in [the native SH7055 trace](sh7055-tipin-v69-static-trace.md), verified by [read-only script](../tools/analysis/sh7055_tipin_v69_audit.py).

- **0x171C6** shifts sample history \`0xFFFFB02C/B030/B034\` and writes \`0xFFFFB028 = current(0xFFFFB024) - two-steps-earlier\`. **No need to port CarBerry's two-step history as if Subaru lacked it.**
- **0x1716E** conditions source signal from \`0xFFFF90E4\` and two corrections; \`0x1718E\` can substitute fallback ROM float **6.0**. The physical signal scale remains unknown.
- **0x24A04** directly reads OEM delta at \`0xFFFFB028\`. Threshold branch consumers at \`0x24AA0\` (\`ROM[0x58DA4]\` raw 0.2) and \`0x24B1C\` (\`ROM[0x58DA8]\` v39 raw 25.0) are now verified.
- The upstream long call sequence evaluates the sensor/history block at **0x10372** and OEM Tip-in at **0x103F0**, in that order. Invocation cadence is *not* known.
- Existing native v39 Tip-in code is byte-identical to v25; modified raw table and thresholds differ from v25.

**Revised DKmode strategy:** First capture/compare the native \`0xFFFFB028\` as an observer signal and characterize scheduling/physical units. Only propose a separate custom history function if evidence demonstrates the stock source or time window is deficient. Avoid double-counting native transient fuel and avoid equating HC16 byte units to SH7055 floats.

## Independent SH7055 module interface — proposed

Observer-only first; do not modify injector actuation in the first phase.

| Input / state | Contract | Validation required |
| --- | --- | --- |
| `throttle_plate_pct` | Explicit physical plate opening scale 0–100%, not accelerator pedal | SH7055 ROM read path, RAM location, range, sampling/filtering |
| `sample_timestamp` | Native scheduler/monotonic tick, measured period | SH7055 timer and actual task cadence |
| `throttle_history` | At least two prior samples, tagged with time; cold-init seeds current value | Tests for initialization, wraparound, missed sample |
| `delta_tps_pct` | Change over a calibrated time window ≈30 ms **as candidate** | Avoid uncalibrated direct conversion from CarBerry 8-bit units |
| `tipin_observer` | Candidate activation, gate reasons, calculated additional pulse separate from OEM value | Logging hooks and no interference with штатный Tip-in |
| `safety` | No fuel-command changes when observer disabled/invalid state; retain OEM redline/LC/FFS | byte diff and regression testing |

### Reference behavior model (not SH7055 assembly)

```text
on_valid_throttle_sample(timestamp, plate_pct):
    if uninitialized:
        seed history with present sample; report neutral delta
        return
    retain timestamped samples
    delta = current_plate_pct - plate_pct_at_approximately_30ms_prior
    candidate = delta >= independently_calibrated_SH7055_threshold
    log(current_plate_pct, delta, dt, candidate, OEM_tipin_if_observable)
    do NOT change fuel output
```

A fixed 30-ms delay is a **candidate** derived from assumed oscillator and historical processing, not a mandatory literal constant. If native SH7055 sampling is substantially different, compute a time-indexed rather than two-execution delta.

## Test and implementation gates

1. **ROM identity:** confirm target v39 SHA/size and read existing Tip-in threshold, table, native throttle variables; do not lift v25 constants without a direct comparison.
2. **Read-path:** inspect plate TPS conversion code, raw vs filtered signal and whether pedal signal differs; determine the main task period and any update buffering.
3. **Observer-only unit tests:** no motion, tiny plate movement, rapid step, signal saturation/invalid input, cold reset, wrapped tick, irregular sample period, throttle closure; encoded CarBerry byte model can be used as separate reference.
4. **Offline ROM diff:** any build must have deterministic changed-byte manifest, checksum coverage, verified call-convention and RAM allocation; do not use old neutral hooks as evidence of an actual working algorithm.
5. **Bench with ECU + logger:** validate output clocks and observer trace; any active transient fuel actuator requires separately gated experimental validation.
6. **Car tests only after bench:** warmed-up controlled pulls, WB lambda/AFR and injector pulse logging, steadystate regression, no LC/FFS/hard-redline changes.

**Currently blocked:** no validated v39 native TPS address, no confirmed SH7055 hook/scheduler, physical oscillator for HC16 unverified, no ECU bench available. Thus **NO FLASHABLE ROM** and no claim of a working CarBerry port.

## Read-only reproducibility

- [HC16 original ROM RTC calculator](../tools/analysis/carberry_rtc_timing.py).
- [CarBerry calibration bytes](carberry-calibration-values.csv).
- [Full HC16 source tracing](carberry-hc16-tipin-trace.md).
