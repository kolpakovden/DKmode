#!/usr/bin/env python3
"""v69 offline audit for known clean Forester SH7055 ROMs. READ ONLY.

No Ghidra needed: validates code/literal anchors from exact pinned v25/v39
SuperH big-endian ROMs. Reports raw calibration values without physical scaling.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

KNOWN = {
    "43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4": "v39",
    "2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99": "v25",
}

def u16(b, o): return int.from_bytes(b[o:o+2], "big")
def u32(b, o): return int.from_bytes(b[o:o+4], "big")
def f32(b, o): return struct.unpack_from(">f", b, o)[0]

def pc_literal(b, o):
    opcode = u16(b, o)
    if (opcode & 0xf000) == 0xd000:  # MOV.L @(disp,PC),Rn
        address = ((o+4) & ~3) + 4*(opcode & 0xff)
        return u32(b, address)
    if (opcode & 0xf000) == 0x9000:  # MOV.W @(disp,PC),Rn
        address = o+4+2*(opcode & 0xff)
        signed = u16(b, address)
        return (signed - 0x10000 if signed & 0x8000 else signed) & 0xffffffff
    raise ValueError("Expected PC-relative SH load at 0x%X" % o)

def target_of_bsr(b, o):
    opcode=u16(b,o)
    assert (opcode & 0xf000)==0xb000, "Expected BSR at 0x%X"%o
    disp=opcode & 0xfff
    if disp & 0x800: disp-=0x1000
    return o+4+2*disp

def verify(path):
    b=Path(path).read_bytes()
    digest=hashlib.sha256(b).hexdigest()
    if len(b)!=0x80000 or digest not in KNOWN:
        raise ValueError("Unknown ROM. %d bytes sha256=%s" %(len(b),digest))
    required_pc={
        0x10372:0x170e8, 0x103f0:0x24a04,
        0x17170:0xffff90e4, 0x17174:0xffff80e8,
        0x17178:0xffff80a0, 0x1717c:0x2444,
        0x17186:0xffffb020, 0x171a0:0xffffb024,
        0x171b8:0x57628, 0x171c8:0xffffb02c,
        0x171e4:0xffffb024, 0x171e8:0xffffb028,
        0x24a14:0xffffb8d8, 0x24a18:0xffffb028,
        0x24a9c:0x58da4, 0x24b0c:0x58da8,
    }
    for offset,expected in required_pc.items():
        got=pc_literal(b,offset)
        assert got==expected, "PC literal @0x%05X: 0x%X instead of 0x%X"%(offset,got,expected)
    assert u32(b,0x10570)==0x170e8
    assert u32(b,0x105c4)==0x24a04
    assert target_of_bsr(b,0x170f6)==0x171c6
    for offset,hexd in {0x171f2:"f231",0x171f4:"f32a",
                       0x24a22:"ff28",0x24aa0:"f3f5",
                       0x24b1c:"f325"}.items():
        assert b[offset:offset+2]==bytes.fromhex(hexd), "Instruction mismatch @0x%X"%offset
    return {
        "variant":KNOWN[digest], "sha256":digest,
        "source_conditioned":"0xFFFFB024",
        "source_raw_and_corrections":["0xFFFF90E4","0xFFFF80E8","0xFFFF80A0"],
        "fallback_rom_0x57628":f32(b,0x57628),
        "history":["0xFFFFB02C","0xFFFFB030","0xFFFFB034"],
        "delta_ram":"0xFFFFB028",
        "delta_formula":"current B024 minus prior B030 (two update steps)",
        "delta_period_ms":"not proven",
        "callsite_delta":"0x10372 -> 0x170E8 -> BSR 0x171C6",
        "callsite_tipin":"0x103F0 -> 0x24A04",
        "raw_min_delta_0x58DA4":f32(b,0x58da4),
        "raw_min_activation_0x58DA8":f32(b,0x58da8),
        "tipin_first6_raw_u16":[u16(b,0x59b84+2*i) for i in range(6)],
        "actuator_units_and_side_effects":"unverified",
    }

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("rom",help="Exact pinned v25 or v39 .bin")
    args=ap.parse_args()
    print(json.dumps(verify(args.rom),indent=2,ensure_ascii=False))
