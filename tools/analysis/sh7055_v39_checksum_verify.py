#!/usr/bin/env python3
"""Read-only verification of Subaru Denso SH7xxx checksum on pinned Forester v39."""
import hashlib
import json
import pathlib
import struct
import sys

EXPECTED_SHA256 = "43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4"
CONSTANT = 0x5AA5A55A
TABLE = 0x7FB80
ENTRIES = 16

def verify(path: pathlib.Path):
    rom = path.read_bytes()
    actual_sha = hashlib.sha256(rom).hexdigest()
    if len(rom) != 0x80000 or actual_sha != EXPECTED_SHA256:
        raise ValueError("Unexpected v39 size or SHA256; verification refused")
    def be32(offset):
        return struct.unpack_from(">I", rom, offset)[0]
    results = []
    for index in range(ENTRIES):
        pos = TABLE + 12 * index
        lo, hi, stored = (be32(pos), be32(pos + 4), be32(pos + 8))
        disabled = (lo == 0 and hi == 0)
        if disabled:
            calculated = CONSTANT
        else:
            if not (0 <= lo < hi <= len(rom) - 3 and lo % 4 == 0):
                raise ValueError(f"Invalid checksum range in entry {index}")
            total = sum(be32(i) for i in range(lo, hi, 4)) & 0xFFFFFFFF
            calculated = (CONSTANT - total) & 0xFFFFFFFF
        results.append({"index": index, "table_offset": f"0x{pos:05X}",
                        "range_start": f"0x{lo:08X}", "range_high": f"0x{hi:08X}",
                        "stored": f"0x{stored:08X}", "calculated": f"0x{calculated:08X}",
                        "disabled": disabled, "match": stored == calculated})
    if not all(e["match"] for e in results):
        raise AssertionError("One or more checksum entries do not match")
    return {"status": "OFFLINE_CHECKSUM_VERIFIED_NOT_FLASH_SAFE",
            "sha256": actual_sha, "size": len(rom), "entries": results}

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python sh7055_v39_checksum_verify.py <original_v39.bin>")
    print(json.dumps(verify(pathlib.Path(sys.argv[1])), indent=2))
