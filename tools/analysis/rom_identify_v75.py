#!/usr/bin/env python3
"""v75: identify a ROM image read from the car and check whether the DKmode
Tip-in model and logger RAM addresses apply to it. STRICT READ ONLY.

  python rom_identify_v75.py car_read.bin

Result levels:
  KNOWN-ROM    SHA-256 equals v39/v25 (original research ROMs)
  KNOWN-PROXY  SHA-256 equals one of the code-audited proxy builds v63..v70
  UNKNOWN      any other SHA. The anchor checks below are reported, but the
               file is NOT added to any whitelist: a separate code/address
               audit (v69-v73 listings) is required before using the model
               or the logger addon with it.
"""
import argparse, hashlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sh7055_tipin_model_v74 import KNOWN, POOL, u32  # noqa: E402
from sh2e_disasm import decode  # noqa: E402

# instruction-level anchors for the logger addresses (literal or MOV.W value)
RAM_ANCHORS = {
    "0xFFFFB024": [(0x171A0, 0xFFFFB024), (0x171E4, 0xFFFFB024)],
    "0xFFFFB028": [(0x171E8, 0xFFFFB028), (0x24A18, 0xFFFFB028)],
    "0xFFFFB80C": [(0x24B08, 0xFFFFB80C)],
    "0xFFFFB810": [(0x24B2E, 0xFFFFB810)],
    "0xFFFFB814": [(0x24A38, 0xFFFFB814), (0x24AD0, 0xFFFFB814)],
    "0xFFFFB818": [(0x24A34, 0xFFFFB818), (0x24AA6, 0xFFFFB818)],
    "0xFFFFB821": [(0x24A2A, 0xFFFFB821)],
    "0xFFFFB8D8": [(0x24A14, 0xFFFFB8D8)],
    "0xFFFF94E4": [(0xD03C, 0xFFFF94DB)],       # base + task id 9
    "0xFFFF94F0": [(0xD2B8, 0xFFFF94F0)],
}


def lit(b, pc):
    _, i = decode(b, pc)
    return i["lit"][1] & 0xFFFFFFFF if "lit" in i else None


def identify(path):
    b = Path(path).read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    rep = {"file": str(path), "size": len(b), "sha256": sha,
           "internal_id_0x2000": b[0x2000:0x2008].decode("ascii", "replace") if len(b) > 0x2008 else None,
           "merpmod_signature": b.find(b"MeRpMoD") >= 0}
    if sha in KNOWN:
        name, kind = KNOWN[sha]
        rep["level"] = "KNOWN-ROM" if kind == "ROM" else "KNOWN-PROXY"
        rep["name"] = name
    else:
        rep["level"] = "UNKNOWN"
    if len(b) != 0x80000:
        rep["anchors"] = "not a 512 KiB image"
        return rep
    rep["tipin_literal_pool_ok"] = all(u32(b, a) == v for a, v in POOL.items())
    ram = {}
    for name, checks in RAM_ANCHORS.items():
        ram[name] = all(lit(b, pc) == want for pc, want in checks)
    rep["logger_ram_anchors"] = ram
    rep["vector_cmt1_0x7FF50"] = hex(u32(b, 0x7FF50))
    rep["verdict"] = (
        "model and logger addon apply (status follows level)" if rep["level"] != "UNKNOWN" and
        rep["tipin_literal_pool_ok"] and all(ram.values()) else
        "DO NOT use model/addon until a separate audit; anchors are informative only")
    return rep


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    print(json.dumps(identify(ap.parse_args().rom), indent=2, ensure_ascii=False))
