#!/usr/bin/env python3
"""Read-only clock/RTC timing calculator for a specific CarBerry HC16 reference.

Uses observed ROM bytes plus assumed clock mode/reference frequency.
The SLIM field interpretation is based on the related MC68HC16V1 manual;
Y5 ECU clock hardware and oscillator are NOT independently confirmed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXPECTED_SHA256 = "b06e1282a4b274db856d250ae8a1babaf175729f7f9e9fec12e465fb774a4483"
EXPECTED_LENGTH = 0x28000
MARKERS = {
    "SYNCR write B084": (0x7156, "37 b5 b0 84 9a 04"),
    "PLL-lock compare B08C": (0x715c, "37 b5 b0 8c 98 04 b6 f4"),
    "TIC/TIV write 70A0": (0x7224, "75 a0 5a 53 75 70 5a 52"),
    "SYPCR write 0134": (0x722e, "37 b5 01 34 9a 50"),
    "RTP write 2EE0": (0x7f1c, "37 b5 2e e0 9a 5a"),
    "IRQ flag acknowledge": (0x2fe, "27 18 00 50 08 00"),
    "sampling divider = 8": (0x33c, "17 65 08 b1 78 07"),
    "delta history call": (0x34c, "17 25 08 b1 fa 00 4d 5e"),
}

def calculate(bin_bytes: bytes, fref_hz: float) -> dict:
    if len(bin_bytes) != EXPECTED_LENGTH:
        raise ValueError("Reference must be the original 160-KiB CarBerry image.")
    sha = hashlib.sha256(bin_bytes).hexdigest()
    if sha != EXPECTED_SHA256:
        raise ValueError("Unexpected ROM SHA-256: " + sha)
    for description, (at, encoded) in MARKERS.items():
        expected = bytes.fromhex(encoded)
        if bin_bytes[at:at+len(expected)] != expected:
            raise ValueError("ROM/Ghidra address mismatch at " + description)
    be16 = lambda at: int.from_bytes(bin_bytes[at:at+2], "big")
    syncr = be16(0x7158)
    sypcr = be16(0x7230)
    rtp = be16(0x7f1e)
    tic_tiv = (bin_bytes[0x7229] << 8) | bin_bytes[0x7225]
    X = (syncr >> 15) & 1
    W = (syncr >> 14) & 1
    Y = (syncr >> 8) & 0x3f
    rtc_selection = (tic_tiv >> 8) & 0x07
    if rtc_selection != 0:
        raise ValueError("RTC control no longer selects f_sys/2.")
    factor = 4 * (Y+1) * 2**(2*W+X)  # V1 SLIM slow-reference equation
    fsys = factor * fref_hz
    irq_ms = 1000 * (rtp * 2 / fsys)
    return dict(sha256=sha, syncr=syncr, sypcr=sypcr, tic_tiv=tic_tiv,
                rtp=rtp, X=X, W=W, Y=Y, factor=factor, fref_hz=fref_hz,
                fsys_hz=fsys, irq_ms=irq_ms,
                delta_update_ms=8*irq_ms, delta_comparison_ms=16*irq_ms)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="Path to original_carberry.bin")
    parser.add_argument("--fref", type=float, default=32768,
                        help="ASSUMED reference oscillator frequency in Hz")
    args = parser.parse_args()
    if args.fref <= 0:
        parser.error("Reference frequency must be positive.")
    r = calculate(args.rom.read_bytes(), args.fref)
    print("CarBerry original ROM verified:", r["sha256"])
    print("SYNCR=0x{:04X}; X={}; W={}; Y={}; factor={}".format(
        r["syncr"], r["X"], r["W"], r["Y"], r["factor"]))
    print("SYPCR=0x{:04X}; TIC/TIV=0x{:04X}; RTP={} ticks".format(
        r["sypcr"], r["tic_tiv"], r["rtp"]))
    for key in ("fref_hz", "fsys_hz", "irq_ms", "delta_update_ms", "delta_comparison_ms"):
        print("{}={:.6f}".format(key, r[key]))
    print("CONDITIONAL: Y5 equivalent to V1 SLIM, slow-reference mode, entered f_ref.")

if __name__ == "__main__":
    main()
