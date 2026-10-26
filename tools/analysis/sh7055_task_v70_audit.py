#!/usr/bin/env python3
"""v70 read-only SH7055 task-9 Tip-in scheduler audit (record layout fixed in v72).

Pins exact known 512 KiB ROM hashes; does not derive milliseconds.

Task records are indexed as 0x469C + 16*task_id (proven by 0x37C0..0x37CE,
0x38C0..0x38D4 and 0x3F2C..0x3F5E):
  +0  u32  flags; byte +2 = priority (0x38EA MOV.B @(2,R11),R0)
  +4  u32  RAM task-state pointer
  +8  u32  entry point (0x37F4 MOV.L @(8,R13),R4)
  +12 u32  byte +12 = activation limit (0x3F50 MOV.B @(12,R13),R0)
The original v70 script read records from 0x46A0 and mislabeled fields;
see research/sh7055-tipin-v71-task9-wakeup.md.

Status: v39/v25 -> ROM-CONFIRMED; listed proxy builds -> PROXY-CONFIRMED.
"""
import argparse, hashlib, json
from pathlib import Path

KNOWN = {
    "43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4": ("v39", "ROM-CONFIRMED"),
    "2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99": ("v25", "ROM-CONFIRMED"),
    # forester_A2WC012E MerpMod builds (calibrations differ from v39)
    "2ee7056bb2cd09b4e943713165f6b4a39b210a58378ce095d335c048ebc6eef8": ("v63", "PROXY-CONFIRMED"),
    "57cc8860190c15b74b8e7dbbf3bd9bf529f85a2df97d00df0fd73cbe1eedb17a": ("v67", "PROXY-CONFIRMED"),
    "b9da808571b17bcd38bae71c6949c3da6d7ebcc2e17759abded1e6c1c0766466": ("v68_SPARK_CUT_SAFE", "PROXY-CONFIRMED"),
    "8f02eecf37fad5340baf0ba5d66e62308a979660b4926c6ad0559fc53f869ecc": ("v68_SPARK_CUT_ENABLED", "PROXY-CONFIRMED"),
    "02581366d410326102c8ca7ffe7f483e2b1ecdc1f7363cd8a7eac663c8d6e4aa": ("v69_CLEAN_SPARK_CUT", "PROXY-CONFIRMED"),
    "b3bb642372636c7abb312e7659f91ad4e69d683afe0a2d4d681eb3a405715ec2": ("v69_CLEAN_SPARK_SAFE", "PROXY-CONFIRMED"),
    "fd01d605b42e06d1f712faf24ba1c57736e4d7bebea29f1957a71b1bc95317f2": ("v70_DUALMAP_TEST", "PROXY-CONFIRMED"),
}
TABLE = 0x469C
COUNT_ADDR = 0x4648


def u16(b, p): return int.from_bytes(b[p:p + 2], "big")
def u32(b, p): return int.from_bytes(b[p:p + 4], "big")


def check_pc(b, ins, addr, value):
    op = u16(b, ins)
    if op >> 12 != 0xD:
        raise ValueError("not MOV.L PC-relative @" + hex(ins))
    target = ((ins + 4) & ~3) + 4 * (op & 255)
    if target != addr or u32(b, target) != value:
        raise ValueError("wrong literal @" + hex(ins))


def check(b, addr, hexstr):
    if b[addr:addr + len(bytes.fromhex(hexstr))] != bytes.fromhex(hexstr):
        raise ValueError("wrong instruction @" + hex(addr))


def record(b, tid):
    r = TABLE + 16 * tid
    return {"task": tid, "record": hex(r), "flags": b[r:r + 4].hex(),
            "priority": b[r + 2], "state_ram": hex(u32(b, r + 4)),
            "entry": hex(u32(b, r + 8)), "activation_limit": b[r + 12]}


def audit(path):
    b = Path(path).read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    if len(b) != 0x80000 or sha not in KNOWN:
        raise ValueError("unknown ROM len=%d sha256=%s" % (len(b), sha))
    name, status = KNOWN[sha]
    for a, p, val in [(0x37C0, 0x3810, TABLE), (0x3F2C, 0x3FD0, TABLE),
                      (0x3F36, 0x3FD8, COUNT_ADDR), (0x38C0, 0x3964, TABLE),
                      (0x634A, 0x63D4, 0x1028C), (0x10372, 0x10570, 0x170E8),
                      (0x103F0, 0x105C4, 0x24A04)]:
        check_pc(b, a, p, val)
    for a, raw in [(0x37C8, "4d08 4d08 3d3c 5ed1"),   # 16-byte index, @(4) = state
                   (0x37F4, "54d2"),                    # MOV.L @(8,R13),R4 = entry
                   (0x38EA, "84b2"),                    # MOV.B @(2,R11),R0 = priority
                   (0x3F50, "84dc 8043"),               # limit byte +12 -> state.b3
                   (0x634C, "430b 0009"), (0x10374, "430b"),
                   (0x103F2, "420b"), (0x6330, "4f22"), (0x6366, "422b")]:
        check(b, a, raw)
    count = u16(b, COUNT_ADDR)
    if count != 19:
        raise ValueError("task count changed")
    tasks = [record(b, i) for i in range(count)]
    for t in tasks:
        sp, ep = int(t["state_ram"], 16), int(t["entry"], 16)
        if not (0xFFFF7000 <= sp < 0xFFFF7300 and 0x2000 <= ep < 0x60000):
            raise ValueError("implausible record " + t["record"])
    t9 = tasks[9]
    if (t9["record"], t9["state_ram"], t9["entry"], t9["priority"],
            t9["activation_limit"]) != ("0x472c", "0xffff71e4", "0x6330", 2, 2):
        raise ValueError("Task 9 mismatch")
    return {"rom": name, "status": status, "sha256": sha, "task_count": count,
            "record_layout": "0x469C + 16*id: +0 flags(+2 prio), +4 state, +8 entry, +12 limit",
            "tipin_task": t9,
            "chain": "task9 0x6330 -> 0x1028C -> 0x170E8 -> 0x171C6 (Delta TPS); later 0x24A04 (OEM Tip-in)",
            "delta_span": "2 consecutive task9 executions",
            "period_ms": "UNVERIFIED here; see v71 (8 ms only if Pphi=20 MHz)",
            "tasks": tasks}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rom", type=Path)
    p.add_argument("--brief", action="store_true")
    a = p.parse_args()
    out = audit(a.rom)
    if a.brief:
        out.pop("tasks")
    print(json.dumps(out, ensure_ascii=False, indent=2))
