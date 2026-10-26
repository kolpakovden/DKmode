#!/usr/bin/env python3
"""Minimal dependency-free SH-2E (SH7055) big-endian disassembler. READ ONLY.

Purpose: reproducible offline listings for DKmode research notes without
Ghidra/capstone. Covers the SH-2 integer ISA plus SH-2E single-precision FPU.
PC-relative literals are resolved and printed (MOV.W sign-extended).

Usage:
  python sh2e_disasm.py ROM.bin START END        # hex addresses
  python sh2e_disasm.py ROM.bin 0x37BC 0x3812
"""
import struct
import sys

def u16(b, o): return int.from_bytes(b[o:o + 2], "big")
def u32(b, o): return int.from_bytes(b[o:o + 4], "big")
def s8(x): return x - 0x100 if x & 0x80 else x
def s12(x): return x - 0x1000 if x & 0x800 else x

def decode(b, pc):
    """Return (text, info) for the 16-bit instruction at pc.

    info keys: 'lit' (resolved literal address and value), 'target'
    (branch target), 'kind' in {'jsr','bsr','bra','jmp','rts','rte','bt','bf',
    'bts','bfs','braf','bsrf'}, 'delay' (True if delayed branch).
    """
    op = u16(b, pc)
    n = (op >> 8) & 15
    m = (op >> 4) & 15
    lo4 = op & 15
    lo8 = op & 255
    info = {}
    R = lambda r: "R%d" % r
    F = lambda r: "FR%d" % r
    top = op >> 12

    if top == 0x0:
        t = {0x02: "STC SR,{n}", 0x12: "STC GBR,{n}", 0x22: "STC VBR,{n}",
             0x03: "BSRF {n}", 0x23: "BRAF {n}", 0x29: "MOVT {n}",
             0x0A: "STS MACH,{n}", 0x1A: "STS MACL,{n}", 0x2A: "STS PR,{n}",
             0x5A: "STS FPUL,{n}", 0x6A: "STS FPSCR,{n}"}
        if op == 0x0008: return "CLRT", info
        if op == 0x0018: return "SETT", info
        if op == 0x0028: return "CLRMAC", info
        if op == 0x0009: return "NOP", info
        if op == 0x0019: return "DIV0U", info
        if op == 0x000B: info.update(kind="rts", delay=True); return "RTS", info
        if op == 0x001B: return "SLEEP", info
        if op == 0x002B: info.update(kind="rte", delay=True); return "RTE", info
        if lo8 in t:
            if lo8 == 0x03: info.update(kind="bsrf", delay=True)
            if lo8 == 0x23: info.update(kind="braf", delay=True)
            return t[lo8].format(n=R(n)), info
        x = {0x4: "MOV.B {m},@(R0,{n})", 0x5: "MOV.W {m},@(R0,{n})",
             0x6: "MOV.L {m},@(R0,{n})", 0x7: "MUL.L {m},{n}",
             0xC: "MOV.B @(R0,{m}),{n}", 0xD: "MOV.W @(R0,{m}),{n}",
             0xE: "MOV.L @(R0,{m}),{n}", 0xF: "MAC.L @{m}+,@{n}+"}
        if lo4 in x: return x[lo4].format(m=R(m), n=R(n)), info
    elif top == 0x1:
        return "MOV.L %s,@(%d,%s)" % (R(m), lo4 * 4, R(n)), info
    elif top == 0x2:
        x = {0: "MOV.B {m},@{n}", 1: "MOV.W {m},@{n}", 2: "MOV.L {m},@{n}",
             4: "MOV.B {m},@-{n}", 5: "MOV.W {m},@-{n}", 6: "MOV.L {m},@-{n}",
             7: "DIV0S {m},{n}", 8: "TST {m},{n}", 9: "AND {m},{n}",
             10: "XOR {m},{n}", 11: "OR {m},{n}", 12: "CMP/STR {m},{n}",
             13: "XTRCT {m},{n}", 14: "MULU.W {m},{n}", 15: "MULS.W {m},{n}"}
        if lo4 in x: return x[lo4].format(m=R(m), n=R(n)), info
    elif top == 0x3:
        x = {0: "CMP/EQ", 2: "CMP/HS", 3: "CMP/GE", 4: "DIV1", 5: "DMULU.L",
             6: "CMP/HI", 7: "CMP/GT", 8: "SUB", 10: "SUBC", 11: "SUBV",
             12: "ADD", 13: "DMULS.L", 14: "ADDC", 15: "ADDV"}
        if lo4 in x: return "%s %s,%s" % (x[lo4], R(m), R(n)), info
    elif top == 0x4:
        x = {0x00: "SHLL {n}", 0x10: "DT {n}", 0x20: "SHAL {n}",
             0x01: "SHLR {n}", 0x11: "CMP/PZ {n}", 0x21: "SHAR {n}",
             0x02: "STS.L MACH,@-{n}", 0x12: "STS.L MACL,@-{n}",
             0x22: "STS.L PR,@-{n}", 0x52: "STS.L FPUL,@-{n}",
             0x62: "STS.L FPSCR,@-{n}",
             0x03: "STC.L SR,@-{n}", 0x13: "STC.L GBR,@-{n}",
             0x23: "STC.L VBR,@-{n}",
             0x04: "ROTL {n}", 0x24: "ROTCL {n}",
             0x05: "ROTR {n}", 0x15: "CMP/PL {n}", 0x25: "ROTCR {n}",
             0x06: "LDS.L @{n}+,MACH", 0x16: "LDS.L @{n}+,MACL",
             0x26: "LDS.L @{n}+,PR", 0x56: "LDS.L @{n}+,FPUL",
             0x66: "LDS.L @{n}+,FPSCR",
             0x07: "LDC.L @{n}+,SR", 0x17: "LDC.L @{n}+,GBR",
             0x27: "LDC.L @{n}+,VBR",
             0x08: "SHLL2 {n}", 0x18: "SHLL8 {n}", 0x28: "SHLL16 {n}",
             0x09: "SHLR2 {n}", 0x19: "SHLR8 {n}", 0x29: "SHLR16 {n}",
             0x0A: "LDS {n},MACH", 0x1A: "LDS {n},MACL", 0x2A: "LDS {n},PR",
             0x5A: "LDS {n},FPUL", 0x6A: "LDS {n},FPSCR",
             0x0B: "JSR @{n}", 0x1B: "TAS.B @{n}", 0x2B: "JMP @{n}",
             0x0E: "LDC {n},SR", 0x1E: "LDC {n},GBR", 0x2E: "LDC {n},VBR"}
        if lo8 in x:
            if lo8 == 0x0B: info.update(kind="jsr", delay=True, reg=n)
            if lo8 == 0x2B: info.update(kind="jmp", delay=True, reg=n)
            return x[lo8].format(n=R(n)), info
        if lo4 == 0xF: return "MAC.W @%s+,@%s+" % (R(m), R(n)), info
    elif top == 0x5:
        return "MOV.L @(%d,%s),%s" % (lo4 * 4, R(m), R(n)), info
    elif top == 0x6:
        x = {0: "MOV.B @{m},{n}", 1: "MOV.W @{m},{n}", 2: "MOV.L @{m},{n}",
             3: "MOV {m},{n}", 4: "MOV.B @{m}+,{n}", 5: "MOV.W @{m}+,{n}",
             6: "MOV.L @{m}+,{n}", 7: "NOT {m},{n}", 8: "SWAP.B {m},{n}",
             9: "SWAP.W {m},{n}", 10: "NEGC {m},{n}", 11: "NEG {m},{n}",
             12: "EXTU.B {m},{n}", 13: "EXTU.W {m},{n}",
             14: "EXTS.B {m},{n}", 15: "EXTS.W {m},{n}"}
        return x[lo4].format(m=R(m), n=R(n)), info
    elif top == 0x7:
        return "ADD #%d,%s" % (s8(lo8), R(n)), info
    elif top == 0x8:
        d = lo4
        if n == 0x0: return "MOV.B R0,@(%d,%s)" % (d, R(m)), info
        if n == 0x1: return "MOV.W R0,@(%d,%s)" % (d * 2, R(m)), info
        if n == 0x4: return "MOV.B @(%d,%s),R0" % (d, R(m)), info
        if n == 0x5: return "MOV.W @(%d,%s),R0" % (d * 2, R(m)), info
        if n == 0x8: return "CMP/EQ #%d,R0" % s8(lo8), info
        br = {0x9: ("BT", "bt", False), 0xB: ("BF", "bf", False),
              0xD: ("BT/S", "bts", True), 0xF: ("BF/S", "bfs", True)}
        if n in br:
            name, kind, dl = br[n]
            tgt = pc + 4 + 2 * s8(lo8)
            info.update(kind=kind, target=tgt, delay=dl)
            return "%s 0x%X" % (name, tgt), info
    elif top == 0x9:
        a = pc + 4 + 2 * lo8
        v = u16(b, a)
        sv = (v - 0x10000) if v & 0x8000 else v
        info["lit"] = (a, sv & 0xFFFFFFFF, 2)
        return "MOV.W @(0x%X),%s ; =0x%04X (%d)" % (a, R(n), v, sv), info
    elif top in (0xA, 0xB):
        tgt = pc + 4 + 2 * s12(op & 0xFFF)
        info.update(kind="bra" if top == 0xA else "bsr", target=tgt, delay=True)
        return "%s 0x%X" % ("BRA" if top == 0xA else "BSR", tgt), info
    elif top == 0xC:
        x = {0: "MOV.B R0,@(%d,GBR)" % lo8, 1: "MOV.W R0,@(%d,GBR)" % (lo8 * 2),
             2: "MOV.L R0,@(%d,GBR)" % (lo8 * 4), 3: "TRAPA #%d" % lo8,
             4: "MOV.B @(%d,GBR),R0" % lo8, 5: "MOV.W @(%d,GBR),R0" % (lo8 * 2),
             6: "MOV.L @(%d,GBR),R0" % (lo8 * 4),
             8: "TST #0x%02X,R0" % lo8, 9: "AND #0x%02X,R0" % lo8,
             10: "XOR #0x%02X,R0" % lo8, 11: "OR #0x%02X,R0" % lo8,
             12: "TST.B #0x%02X,@(R0,GBR)" % lo8, 13: "AND.B #0x%02X,@(R0,GBR)" % lo8,
             14: "XOR.B #0x%02X,@(R0,GBR)" % lo8, 15: "OR.B #0x%02X,@(R0,GBR)" % lo8}
        if n == 7:
            a = ((pc + 4) & ~3) + 4 * lo8
            info["mova"] = a
            return "MOVA @(0x%X),R0" % a, info
        if n in x: return x[n], info
    elif top == 0xD:
        a = ((pc + 4) & ~3) + 4 * lo8
        v = u32(b, a)
        info["lit"] = (a, v, 4)
        extra = ""
        if 0x30000 <= v < 0x80000 or (v & 0xFFFFFF00) in (0x3F800000,):
            f = struct.unpack(">f", b[v:v + 4])[0] if v + 4 <= len(b) else None
            if f is not None and 1e-6 < abs(f) < 1e7: extra = " [ROM f32=%g]" % f
        return "MOV.L @(0x%X),%s ; =0x%08X%s" % (a, R(n), v, extra), info
    elif top == 0xE:
        return "MOV #%d,%s" % (s8(lo8), R(n)), info
    elif top == 0xF:
        x = {0: "FADD {m},{n}", 1: "FSUB {m},{n}", 2: "FMUL {m},{n}",
             3: "FDIV {m},{n}", 4: "FCMP/EQ {m},{n}", 5: "FCMP/GT {m},{n}",
             12: "FMOV {m},{n}", 14: "FMAC FR0,{m},{n}"}
        if lo4 in x: return x[lo4].format(m=F(m), n=F(n)), info
        y = {6: "FMOV.S @(R0,R%d),FR%d" % (m, n), 7: "FMOV.S FR%d,@(R0,R%d)" % (m, n),
             8: "FMOV.S @R%d,FR%d" % (m, n), 9: "FMOV.S @R%d+,FR%d" % (m, n),
             10: "FMOV.S FR%d,@R%d" % (m, n), 11: "FMOV.S FR%d,@-R%d" % (m, n)}
        if lo4 in y: return y[lo4], info
        if lo4 == 0xD:
            z = {0: "FSTS FPUL,FR{n}", 1: "FLDS FR{n},FPUL", 2: "FLOAT FPUL,FR{n}",
                 3: "FTRC FR{n},FPUL", 4: "FNEG FR{n}", 5: "FABS FR{n}",
                 8: "FLDI0 FR{n}", 9: "FLDI1 FR{n}"}
            if m in z: return z[m].format(n=n), info
    return ".word 0x%04X" % op, info

def listing(b, start, end):
    out = []
    pc = start
    while pc < end:
        text, _ = decode(b, pc)
        out.append("%06X: %04X  %s" % (pc, u16(b, pc), text))
        pc += 2
    return out

if __name__ == "__main__":
    rom = open(sys.argv[1], "rb").read()
    s, e = int(sys.argv[2], 0), int(sys.argv[3], 0)
    print("\n".join(listing(rom, s, e)))
