# Ghidra — CarBerry HC16 calibration bank

**Research-only helper. Not a ROM patch and not validated on ECU.**

Tool: [`MapCarBerryCalibrationBank.java`](MapCarBerryCalibrationBank.java)

### Source and mapping

- Original `original_carberry.bin` size: `0x28000` (160 KiB).
- SHA-256: `b06e1282a4b274db856d250ae8a1babaf175729f7f9e9fec12e465fb774a4483`.
- Source (packed file) range: `0x020000..0x027FFF`.
- Target (candidate CPU runtime address) range: `0x028000..0x02FFFF`.
- Mapping: `file_offset = CPU_address - 0x8000` **only in this high calibration segment**.
- Original Ghidra program block remains unchanged: additional file-backed block instead of replacing the earlier 160-KiB contiguous import.

### Instructions

1. Back up/duplicate the Ghidra program.
2. Open the analyzed `original_carberry.bin` (the original Binary-loader import).
3. Open **Window → Script Manager**, register the folder with the Java script, run `MapCarBerryCalibrationBank.java`.
4. In Ghidra console, check `MATCH` at `0x2865C`, `0x28667`, `0x293F8`.
5. Open `02865c` through **G**. It should start `80 00 7A 1C 1E`.
6. If the script reports missing `FileBytes` or mismatched values, stop and inspect import provenance; don't create fake data or fill the gap with `FF`.

The script only changes the **Ghidra project database**, not the ROM file; it has been checked against Ghidra Memory API signatures but **not executed inside your installed Ghidra version yet**.

See [reverse-engineering notes](../../research/carberry-hc16-tipin-trace.md) and [calibration value table](../../research/carberry-calibration-values.csv).

**Research boundaries:** The mapping has strong binary evidence but is not independently confirmed from ECU memory decode; TPS sensor identity, input scaling and task cadence are still under study.
