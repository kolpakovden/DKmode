# SH7055 v39 checksum — independently verified (2026-10-21)

Status: **OFFLINE ALGORITHM VERIFIED; NOT FLASH-READY**.

Target: `Forester_SG9_MAP_clean_v39.bin`, 524288 bytes, SHA-256 `43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4`.

- Checksum table: `0x7FB80..0x7FC3F`, 16 entries, 12 bytes each, big-endian.
- Entry 0: start `0x00002000`, high/exclusive **word-start** bound `0x0007FAF7`, stored correction `0x9B084277`.
- The calculation sums 32-bit BE words from `range(0x2000,0x7FAF7,4)`, modulo 2^32. Computed sum `0xBF9D62E3`, correction `(0x5AA5A55A - sum) & 0xffffffff` = `0x9B084277` (matches untouched ROM).
- Entries 1–15: `00000000 00000000 5AA5A55A` (inactive), also consistent with the reference algorithm.
- One-byte *in-memory only* test at `0x6AC40` (`FF→FE`) changes the required correction to `0x9C084277`; modified ROM was **not** written.

Independent read-only reference implementation: `tools/analysis/sh7055_v39_checksum_verify.py` (see companion commit).

Algorithm reference: FastECU `modules/checksum/checksum_ecu_subaru_denso_sh7xxx.cpp`, https://github.com/miikasyvanen/FastECU/blob/master/modules/checksum/checksum_ecu_subaru_denso_sh7xxx.cpp. This research verifier is not copied from FastECU.

**Boundaries:** A valid checksum arithmetic result does not prove that the ECU or flasher will accept a modified ROM. Code-space safety at `0x6AC40`, live ABI, RAM allocation, and boot/bench behavior remain unverified. Do not flash an experimental image.
