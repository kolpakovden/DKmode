#!/usr/bin/env python3
"""v74 offline model of the OEM SH7055 Tip-in decision (0x24A04). READ ONLY.

Reproduces, from one specific ROM, the logic traced in v69-v73:
  B028 = B024[n] - B024[n-2]                       (0x171C6, once per task-9 run)
  counters B821/B818/B814, gates, B80C = T(d) * K_boost(err) * K_ect(ect)
  fire if B80C >= ROM_f[0x58DA8]  ->  extra pulse of B80C us on 4 cylinders

All calibrations are read from the ROM given on the command line. Literal-pool
addresses inside 0x24A04 are checked first, so the model refuses a ROM whose
Tip-in code differs. Values from different ROMs are never mixed.

Not modelled (inputs/assumptions, see research/sh7055-tipin-v74-observer-test-plan.md):
  * task-9 period (parameter --period-ms, default 8.0 = estimate for Pphi=20 MHz)
  * execution jitter / lost activations (optional --jitter-ms)
  * external gates B018.1, B469.7, cut mask B434, TPS fault fallback 6.0
  * B024 from throttle %: B024 = pct * 0.84 (RomRaider E38, REFERENCE)

Usage:
  python sh7055_tipin_model_v74.py ROM.bin --calib
  python sh7055_tipin_model_v74.py ROM.bin --ramp 5:35:120 --boost-err 150 --ect 85
  python sh7055_tipin_model_v74.py ROM.bin --csv log.csv   # columns: t_ms,tps_pct[,boost_err_mmHg,ect_c]
"""
import argparse, csv, hashlib, json, random, struct, sys
from pathlib import Path

KNOWN = {
    "43a4751d68da4ddca9d483c1723a78f04c85ad982423f48177402f9962245ad4": ("v39", "ROM"),
    "2ca539d0c47e3b1eec96c41e1e514c7b19b0e3786e9d826a41d3a3505b4c5d99": ("v25", "ROM"),
    "2ee7056bb2cd09b4e943713165f6b4a39b210a58378ce095d335c048ebc6eef8": ("v63", "PROXY"),
    "57cc8860190c15b74b8e7dbbf3bd9bf529f85a2df97d00df0fd73cbe1eedb17a": ("v67", "PROXY"),
    "b9da808571b17bcd38bae71c6949c3da6d7ebcc2e17759abded1e6c1c0766466": ("v68_SPARK_CUT_SAFE", "PROXY"),
    "8f02eecf37fad5340baf0ba5d66e62308a979660b4926c6ad0559fc53f869ecc": ("v68_SPARK_CUT_ENABLED", "PROXY"),
    "02581366d410326102c8ca7ffe7f483e2b1ecdc1f7363cd8a7eac663c8d6e4aa": ("v69_CLEAN_SPARK_CUT", "PROXY"),
    "b3bb642372636c7abb312e7659f91ad4e69d683afe0a2d4d681eb3a405715ec2": ("v69_CLEAN_SPARK_SAFE", "PROXY"),
    "fd01d605b42e06d1f712faf24ba1c57736e4d7bebea29f1957a71b1bc95317f2": ("v70_DUALMAP_TEST", "PROXY"),
}
# literal pool of 0x24A04 -> expected pointer (code-identical in v25/v39/proxies)
POOL = {0x24BA4: 0x58853, 0x24BA8: 0x58854, 0x24BAC: 0x58DA4, 0x24BB0: 0x58852,
        0x24BB4: 0x58DAC, 0x24BB8: 0x209C, 0x24BBC: 0x54910, 0x24BC4: 0x5455C,
        0x24BC8: 0x54924, 0x24BCC: 0x58DA8, 0x24A5C: 0x1763A}
B024_PER_PCT = 0.84          # RomRaider E38: % = B024 / 0.84  (REFERENCE)
TYPES = {0x00: (">f", 4), 0x04: (">B", 1), 0x08: (">H", 2), 0x0C: (">b", 1), 0x10: (">h", 2)}


def u32(b, a): return int.from_bytes(b[a:a + 4], "big")
def f32(b, a): return struct.unpack(">f", b[a:a + 4])[0]


class Table1D:
    """Descriptor as used by 0x209C: u16 n, u8 type, ptr axis, ptr data, f mult, f off."""
    def __init__(self, b, d):
        self.addr = d
        self.n = int.from_bytes(b[d:d + 2], "big")
        self.type = b[d + 2]
        ax, da = u32(b, d + 4), u32(b, d + 8)
        fmt, sz = TYPES[self.type]
        self.axis = [f32(b, ax + 4 * i) for i in range(self.n)]
        self.raw = [struct.unpack(fmt, b[da + sz * i:da + sz * (i + 1)])[0] for i in range(self.n)]
        self.scaled = self.type != 0
        self.mult, self.off = (f32(b, d + 12), f32(b, d + 16)) if self.scaled else (1.0, 0.0)
        self.axis_addr, self.data_addr = ax, da

    def __call__(self, x):
        # 0x2684: clamp below first / above last point, linear between
        a, r = self.axis, self.raw
        if x <= a[0]:
            v = r[0]
        elif x >= a[-1]:
            v = r[-1]
        else:
            i = max(k for k in range(self.n - 1) if a[k] <= x)
            fr = (x - a[i]) / (a[i + 1] - a[i])
            v = r[i] + fr * (r[i + 1] - r[i])
        return v * self.mult + self.off

    def dump(self):
        return {"desc": hex(self.addr), "axis_addr": hex(self.axis_addr),
                "data_addr": hex(self.data_addr), "type": self.type,
                "mult": self.mult, "off": self.off, "axis": self.axis,
                "raw": self.raw, "phys": [x * self.mult + self.off for x in self.raw]}


def load(path):
    b = Path(path).read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    if len(b) != 0x80000 or sha not in KNOWN:
        raise SystemExit("refusing unknown ROM: len=%d sha256=%s" % (len(b), sha))
    for lit, ptr in POOL.items():
        if u32(b, lit) != ptr:
            raise SystemExit("Tip-in literal pool mismatch at 0x%X" % lit)
    name, kind = KNOWN[sha]
    cal = {
        "rom": name, "status": "ROM-CONFIRMED" if kind == "ROM" else "PROXY-CONFIRMED",
        "sha256": sha,
        "min_delta": f32(b, 0x58DA4),            # B028 units (= 0.84 per %)
        "min_amount_us": f32(b, 0x58DA8),        # compared with B80C (us)
        "max_cum_delta": f32(b, 0x58DAC),        # B814 limit
        "max_events": b[0x58852],                # B818 limit
        "reset_events_after": b[0x58853],        # B821 >= -> B818 = 0
        "reset_cum_after": b[0x58854],           # B821 >= -> B814 = 0
        "fault_fallback_B024": f32(b, 0x57628),
        "tip": Table1D(b, 0x54910), "kboost": Table1D(b, 0x5455C), "kect": Table1D(b, 0x54924),
    }
    return cal


class OemTipin:
    def __init__(self, cal):
        self.c = cal
        self.hist = []          # B024 samples (B02C/B030 history)
        self.b821 = 0
        self.b818 = 0
        self.b814 = 0.0

    def step(self, b024, boost_err, ect, gate_b018=False, gate_b469=False):
        c = self.c
        self.hist.append(b024)
        if len(self.hist) < 3:
            return None
        self.hist = self.hist[-3:]
        d = self.hist[-1] - self.hist[0]                  # B028
        self.b821 = min(self.b821 + 1, 255)
        if d < 0:
            self.b818, self.b814 = 0, 0.0
        else:
            if self.b821 >= c["reset_events_after"]:
                self.b818 = 0
            if self.b821 >= c["reset_cum_after"]:
                self.b814 = 0.0
        ev = {"delta": d, "fired": False}
        if d < c["min_delta"]:
            ev["block"] = "delta<min"; return ev
        if self.b818 >= c["max_events"]:
            ev["block"] = "B818 limit"; return ev
        if gate_b018:
            ev["block"] = "gate B018.1"; return ev
        if gate_b469:
            ev["block"] = "gate B469.7"; return ev
        if self.b814 >= c["max_cum_delta"]:
            ev["block"] = "B814 limit"; return ev
        f1, f2, f3 = c["tip"](d), c["kboost"](boost_err), c["kect"](ect)
        amt = f1 * f2 * f3                                 # B80C, us
        ev.update(T=f1, Kboost=f2, Kect=f3, B80C_us=amt)
        if c["min_amount_us"] > amt:
            ev["block"] = "B80C<min"; return ev
        self.b818 = min(self.b818 + 1, 255)
        self.b814 += d
        self.b821 = 0
        ev.update(fired=True, B818=self.b818, B814=self.b814)
        return ev


def run(cal, samples, period_ms, jitter_ms, seed):
    """samples: function t_ms -> (tps_pct, boost_err, ect)."""
    rnd = random.Random(seed)
    m = OemTipin(cal)
    out, t, k = [], 0.0, 0
    t_end = samples.t_end
    while t <= t_end:
        te = t + (rnd.uniform(0, jitter_ms) if jitter_ms else 0.0)
        pct, be, ect = samples(te)
        ev = m.step(pct * B024_PER_PCT, be, ect)
        if ev is not None:
            ev["t_ms"] = round(te, 3); ev["tps_pct"] = pct
            out.append(ev)
        k += 1
        t = k * period_ms
    return out


class Ramp:
    def __init__(self, spec, be, ect, pre=50.0, post=200.0):
        a, b, dur = (float(x) for x in spec.split(":"))
        self.a, self.b, self.dur, self.pre, self.be, self.ect = a, b, dur, pre, be, ect
        self.t_end = pre + dur + post

    def __call__(self, t):
        if t < self.pre:
            p = self.a
        elif t < self.pre + self.dur:
            p = self.a + (self.b - self.a) * (t - self.pre) / self.dur
        else:
            p = self.b
        return p, self.be, self.ect


class CsvTrace:
    def __init__(self, path, be, ect):
        rows = list(csv.DictReader(open(path)))
        self.t = [float(r["t_ms"]) for r in rows]
        self.p = [float(r["tps_pct"]) for r in rows]
        self.be = [float(r.get("boost_err_mmHg") or be) for r in rows]
        self.ect = [float(r.get("ect_c") or ect) for r in rows]
        self.t_end = self.t[-1]

    def __call__(self, t):  # sample-and-hold of the latest logged row
        i = max(0, max((k for k in range(len(self.t)) if self.t[k] <= t), default=0))
        return self.p[i], self.be[i], self.ect[i]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("--calib", action="store_true", help="print calibrations and exit")
    ap.add_argument("--ramp", help="tps_from:tps_to:duration_ms")
    ap.add_argument("--csv", help="trace with t_ms,tps_pct[,boost_err_mmHg,ect_c]")
    ap.add_argument("--boost-err", type=float, default=200.0, help="AF08-AF94, mmHg")
    ap.add_argument("--ect", type=float, default=85.0)
    ap.add_argument("--period-ms", type=float, default=8.0, help="task-9 period (ESTIMATE)")
    ap.add_argument("--jitter-ms", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    cal = load(a.rom)
    head = {k: v for k, v in cal.items() if k not in ("tip", "kboost", "kect")}
    head["period_ms"] = "%s (estimate, not measured)" % a.period_ms
    if a.calib or not (a.ramp or a.csv):
        head.update(tip=cal["tip"].dump(), kboost=cal["kboost"].dump(), kect=cal["kect"].dump())
        print(json.dumps(head, indent=2, ensure_ascii=False)); return
    src = Ramp(a.ramp, a.boost_err, a.ect) if a.ramp else CsvTrace(a.csv, a.boost_err, a.ect)
    ev = run(cal, src, a.period_ms, a.jitter_ms, a.seed)
    fired = [e for e in ev if e["fired"]]
    print(json.dumps({"model": head, "fired": len(fired),
                      "total_extra_us": round(sum(e["B80C_us"] for e in fired), 1),
                      "events": [e for e in ev if e["fired"] or e.get("block") not in (None, "delta<min")]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
