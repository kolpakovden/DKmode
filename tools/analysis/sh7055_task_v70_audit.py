#!/usr/bin/env python3
"""v70 read-only SH7055 task-9 Tip-in scheduler audit.
Pins exact known 512KiB clean v25/v39 ROM hashes; does not derive milliseconds.
"""
import argparse,hashlib,json
from pathlib import Path

KNOWN={
"43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4":"v39",
"2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99":"v25"}
def u16(b,p):return int.from_bytes(b[p:p+2],"big")
def u32(b,p):return int.from_bytes(b[p:p+4],"big")
def check_pc(b,ins,addr,value):
    op=u16(b,ins)
    if op>>12!=0xd:raise ValueError("not MOV.L PC-relative @"+hex(ins))
    target=((ins+4)&~3)+4*(op&255)
    if target!=addr or u32(b,target)!=value:
        raise ValueError("wrong literal @"+hex(ins))
def check(b,addr,hexstr):
    expected=bytes.fromhex(hexstr)
    if b[addr:addr+len(expected)]!=expected:
        raise ValueError("wrong instruction @"+hex(addr))
def audit(path):
    b=Path(path).read_bytes();sha=hashlib.sha256(b).hexdigest()
    if len(b)!=0x80000 or sha not in KNOWN:
        raise ValueError("unknown ROM len="+str(len(b))+" sha256="+sha)
    for a,p,val in [
        (0x37c0,0x3810,0x469c),(0x3f2c,0x3fd0,0x469c),
        (0x3f36,0x3fd8,0x4648),(0x634a,0x63d4,0x1028c),
        (0x10372,0x10570,0x170e8),(0x103f0,0x105c4,0x24a04)]:
        check_pc(b,a,p,val)
    for a,raw in [
        (0x37c8,"4d08 4d08 3d3c 5ed1"),
        (0x634c,"430b 0009"),(0x10374,"430b"),
        (0x103f2,"420b"),(0x6330,"4f22"),(0x6366,"422b")]:
        check(b,a,raw)
    count=u16(b,0x4648)
    if count!=19:raise ValueError("task count changed")
    tasks=[]
    for i in range(count):
        a=0x46a0+i*16
        tasks.append({"task":i,"descriptor":hex(a),
                      "state_ram":hex(u32(b,a)),"handler":hex(u32(b,a+4)),
                      "cfg0":hex(u32(b,a+8)),"cfg1":hex(u32(b,a+12))})
    t=tasks[9]
    if u32(b,0x4730)!=0xffff71e4 or u32(b,0x4734)!=0x6330:
        raise ValueError("Task 9 mismatch")
    return {"rom":KNOWN[sha],"sha256":sha,"task_count":count,
            "tipin_task":t,"chain":"task9 0x6330 -> 0x1028C -> "
            "0x170E8 -> 0x171C6 (Delta TPS); "
            "later 0x24A04 (OEM Tip-in)",
            "delta_span":"2 consecutive task9 updates; time unknown",
            "period_ms":"UNVERIFIED","tasks":tasks}
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("rom",type=Path)
    p.add_argument("--brief",action="store_true")
    args=p.parse_args();out=audit(args.rom)
    if args.brief:out.pop("tasks")
    print(json.dumps(out,ensure_ascii=False,indent=2))
