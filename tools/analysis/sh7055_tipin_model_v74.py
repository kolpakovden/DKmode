#!/usr/bin/env python3
"""v74/v75 offline model of the OEM SH7055 Tip-in decision (0x24A04). READ ONLY.

Reproduces, from one specific ROM, the logic traced in v69-v73:
  B028 = B024[n] - B024[n-2]                       (0x171C6, once per task-9 run)
  counters B821/B818/B814, gates, B80C = T(d) * K_boost(err) * K_ect(ect)
  fire if B80C >= ROM_f[0x58DA8]  ->  extra pulse of B80C us on 4 cylinders

All calibrations are read from the ROM given on the command line. Literal-pool
addresses inside 0x24A04 are checked first, so the model refuses a ROM whose
Tip-in code differs. Values from different ROMs are never mixed.

v75 audit changes (see research/sh7055-tipin-v75-measurement-readiness.md):
  * arithmetic is rounded to IEEE float32 at every SH-2E FPU step (default);
  * history is pre-filled with the first sample (no silent "None" runs);
  * input-mode guard: synthetic / daq / ssm. SSM-rate traces (2-25 Hz) are
    refused for event reconstruction unless --force-coarse, and then every
    output is labelled MODEL-ON-COARSE-INPUT;
  * optional lost activations (--drop-prob) next to execution jitter;
  * CSV lookup by bisection (DAQ files with 10^5..10^6 rows).

Not modelled (inputs/assumptions):
  * true task-9 period (--period-ms, default 8.0 = estimate for Pphi=20 MHz)
  * external gates B018.1, B469.7, cut mask B434, TPS fault fallback 6.0
  * merge with the main pulse (v73 sec. 2.2)
  * B024 from throttle %: B024 = pct * 0.84 (RomRaider E38, REFERENCE)

Usage:
  python sh7055_tipin_model_v74.py ROM.bin --calib
  python sh7055_tipin_model_v74.py ROM.bin --ramp 5:35:120 --boost-err 150 --ect 85
  python sh7055_tipin_model_v74.py ROM.bin --csv daq.csv   # t_ms,tps_pct[,boost_err_mmHg,ect_c]
"""
import argparse, bisect, csv, hashlib, json, random, statistics, struct
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


def F(x):
    """Round to IEEE-754 binary32 (SH-2E single-precision FPU)."""
    return struct.unpack(">f", struct.pack(">f", x))[0]


def _id(x):
    return x


def u32(b, a): return int.from_bytes(b[a:a + 4], "big")
def f32(b, a): return struct.unpack(">f", b[a:a + 4])[0]


class Table1D:
    """Descriptor as used by 0x209C: u16 n, u8 type, ptr axis, ptr data, f mult, f off."""
    def __init__(self, b=None, d=None, *, axis=None, raw=None, mult=1.0, off=0.0, typ=8):
        if b is not None:
            self.addr = d
            self.n = int.from_bytes(b[d:d + 2], "big")
            self.type = b[d + 2]
            ax, da = u32(b, d + 4), u32(b, d + 8)
            fmt, sz = TYPES[self.type]
            self.axis = [f32(b, ax + 4 * i) for i in range(self.n)]
            self.raw = [struct.unpack(fmt, b[da + sz * i:da + sz * (i + 1)])[0] for i in range(self.n)]
            self.mult, self.off = (f32(b, d + 12), f32(b, d + 16)) if self.type != 0 else (1.0, 0.0)
            self.axis_addr, self.data_addr = ax, da
        else:  # synthetic table (tests)
            self.addr = self.axis_addr = self.data_addr = None
            self.axis, self.raw, self.n, self.type = list(axis), list(raw), len(axis), typ
            self.mult, self.off = (mult, off) if typ != 0 else (1.0, 0.0)
        self.r = F  # rounding function, replaced by _id when --no-f32

    def index(self, x):
        """0x2684: (i, frac). Clamp below axis[0] and at/above axis[-1]."""
        a, R = self.axis, self.r
        if not (a[-1] > x):
            return self.n - 1, 0.0
        i = self.n - 1
        while i > 0:
            i -= 1
            if not (a[i] > x):
                return i, R(R(x - a[i]) / R(a[i + 1] - a[i]))
        return 0, 0.0

    def __call__(self, x):
        R = self.r
        i, fr = self.index(x)
        v = float(self.raw[i])
        if fr != 0.0:                                     # FCMP/EQ frac,0 -> skip
            v = R(v + R(fr * R(float(self.raw[i + 1]) - v)))  # FMAC (two roundings assumed)
        if self.type != 0:
            v = R(R(v * self.mult) + self.off)            # 0x20BC..0x20C2
        return v

    def dump(self):
        return {"desc": hex(self.addr) if self.addr else None,
                "axis_addr": hex(self.axis_addr) if self.axis_addr else None,
                "data_addr": hex(self.data_addr) if self.data_addr else None,
                "type": self.type, "mult": self.mult, "off": self.off, "axis": self.axis,
                "raw": self.raw, "phys": [x * self.mult + self.off for x in self.raw]}


def load(path):
    b = Path(path).read_bytes()
    sha = hashlib.sha256(b).hexdigest()
    if len(b) != 0x80000 or sha not in KNOWN:
        raise SystemExit("refusing unknown ROM: len=%d sha256=%s (needs separate code/address audit)" % (len(b), sha))
    for lit, ptr in POOL.items():
        if u32(b, lit) != ptr:
            raise SystemExit("Tip-in literal pool mismatch at 0x%X" % lit)
    name, kind = KNOWN[sha]
    return {
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


class OemTipin:
    """One call of step() == one execution of task 9 (0x171C6 then 0x24A04)."""

    def __init__(self, cal, use_f32=True):
        self.c = cal
        self.R = F if use_f32 else _id
        for t in ("tip", "kboost", "kect"):
            cal[t].r = self.R
        self.hist = None        # [B034, B030, B02C] newest last
        self.b821 = 0
        self.b818 = 0
        self.b814 = 0.0

    def step(self, b024, boost_err, ect, gate_b018=False, gate_b469=False):
        c, R = self.c, self.R
        b024 = R(b024)
        if self.hist is None:                      # pre-fill: first run sees delta 0
            self.hist = [b024, b024, b024]
        self.hist = self.hist[1:] + [b024]
        d = R(self.hist[-1] - self.hist[0])        # current - two runs earlier
        self.b821 = min(self.b821 + 1, 255)        # 0x24A26 sat-inc
        if d < 0.0:                                # 0x24A3A FCMP/GT d,0
            self.b818, self.b814 = 0, 0.0
        else:
            if self.b821 >= c["reset_events_after"]:
                self.b818 = 0
            if self.b821 >= c["reset_cum_after"]:
                self.b814 = 0.0
        ev = {"delta": d, "fired": False, "B821": self.b821}
        if c["min_delta"] > d:                     # equality passes
            ev["block"] = "delta<min"; return ev
        if self.b818 >= c["max_events"]:
            ev["block"] = "B818 limit"; return ev
        if gate_b018:
            ev["block"] = "gate B018.1"; return ev
        if gate_b469:
            ev["block"] = "gate B469.7"; return ev
        if not (c["max_cum_delta"] > self.b814):   # equality blocks
            ev["block"] = "B814 limit"; return ev
        f1, f2, f3 = c["tip"](d), c["kboost"](boost_err), c["kect"](ect)
        amt = R(R(f1 * f2) * f3)                   # B80C, us
        ev.update(T=f1, Kboost=f2, Kect=f3, B80C_us=amt)
        if c["min_amount_us"] > amt:               # equality fires
            ev["block"] = "B80C<min"; return ev
        self.b818 = min(self.b818 + 1, 255)
        self.b814 = R(self.b814 + d)
        self.b821 = 0
        ev.update(fired=True, B818=self.b818, B814=self.b814)
        return ev


def run(cal, samples, period_ms, jitter_ms=0.0, seed=1, drop_prob=0.0, use_f32=True):
    """samples(t_ms) -> (tps_pct, boost_err, ect). One run per activation."""
    rnd = random.Random(seed)
    m = OemTipin(cal, use_f32)
    out, k, lost = [], 0, 0
    while k * period_ms <= samples.t_end:
        if drop_prob and rnd.random() < drop_prob:
            lost += 1; k += 1; continue           # activation lost (would count in 0xFFFF94E4)
        te = k * period_ms + (rnd.uniform(0, jitter_ms) if jitter_ms else 0.0)
        pct, be, ect = samples(te)
        ev = m.step(pct * B024_PER_PCT, be, ect)
        ev["t_ms"] = round(te, 3); ev["tps_pct"] = pct
        out.append(ev)
        k += 1
    return out, lost


class Ramp:
    mode = "synthetic"

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


class Profile:
    """Piecewise-linear synthetic trace: [(t_ms, pct), ...]."""
    mode = "synthetic"

    def __init__(self, points, be=200.0, ect=85.0):
        self.t = [p[0] for p in points]; self.p = [p[1] for p in points]
        self.be, self.ect, self.t_end = be, ect, self.t[-1]

    def __call__(self, t):
        i = bisect.bisect_right(self.t, t) - 1
        if i < 0:
            return self.p[0], self.be, self.ect
        if i >= len(self.t) - 1:
            return self.p[-1], self.be, self.ect
        f = (t - self.t[i]) / (self.t[i + 1] - self.t[i])
        return self.p[i] + f * (self.p[i + 1] - self.p[i]), self.be, self.ect


def classify_input(t_ms, period_ms):
    """'daq' if the trace resolves single task-9 runs, otherwise 'ssm'."""
    d = sorted(b - a for a, b in zip(t_ms, t_ms[1:]) if b > a)
    if not d:
        return "ssm", {"median_dt_ms": None}
    med, p95 = statistics.median(d), d[int(0.95 * (len(d) - 1))]
    mode = "daq" if (med <= period_ms / 4 and p95 <= period_ms / 2) else "ssm"
    return mode, {"median_dt_ms": med, "p95_dt_ms": p95, "max_dt_ms": d[-1],
                  "required_median_ms": period_ms / 4, "required_p95_ms": period_ms / 2}


class CsvTrace:
    def __init__(self, path, be, ect, period_ms):
        rows = list(csv.DictReader(open(path, newline="")))
        rows.sort(key=lambda r: float(r["t_ms"]))
        self.t = [float(r["t_ms"]) for r in rows]
        self.p = [float(r["tps_pct"]) for r in rows]
        self.be = [float(r.get("boost_err_mmHg") or be) for r in rows]
        self.ect = [float(r.get("ect_c") or ect) for r in rows]
        self.t_end = self.t[-1]
        self.mode, self.sampling = classify_input(self.t, period_ms)

    def __call__(self, t):  # sample-and-hold of the latest row at or before t
        i = max(0, bisect.bisect_right(self.t, t) - 1)
        return self.p[i], self.be[i], self.ect[i]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom")
    ap.add_argument("--calib", action="store_true", help="print calibrations and exit")
    ap.add_argument("--ramp", help="tps_from:tps_to:duration_ms (synthetic)")
    ap.add_argument("--csv", help="trace with t_ms,tps_pct[,boost_err_mmHg,ect_c]")
    ap.add_argument("--boost-err", type=float, default=200.0, help="AF08-AF94, mmHg")
    ap.add_argument("--ect", type=float, default=85.0)
    ap.add_argument("--period-ms", type=float, default=8.0, help="task-9 period (ESTIMATE)")
    ap.add_argument("--jitter-ms", type=float, default=0.0)
    ap.add_argument("--drop-prob", type=float, default=0.0, help="probability of a lost activation")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-f32", action="store_true", help="use Python double instead of float32")
    ap.add_argument("--force-coarse", action="store_true",
                    help="run on SSM-rate input anyway; results are NOT measured events")
    a = ap.parse_args()
    cal = load(a.rom)
    head = {k: v for k, v in cal.items() if k not in ("tip", "kboost", "kect")}
    head["period_ms"] = "%s (estimate, not measured)" % a.period_ms
    head["arithmetic"] = "python-double" if a.no_f32 else "float32"
    if a.calib or not (a.ramp or a.csv):
        head.update(tip=cal["tip"].dump(), kboost=cal["kboost"].dump(), kect=cal["kect"].dump())
        print(json.dumps(head, indent=2, ensure_ascii=False)); return
    src = Ramp(a.ramp, a.boost_err, a.ect) if a.ramp else CsvTrace(a.csv, a.boost_err, a.ect, a.period_ms)
    label = {"synthetic": "MODEL-SYNTHETIC", "daq": "MODEL-ON-DAQ-INPUT"}.get(src.mode, "MODEL-ON-COARSE-INPUT")
    if src.mode == "ssm" and not a.force_coarse:
        raise SystemExit("input sampling too coarse for task-9 reconstruction %s; "
                         "use the v75 log analyzer for SSM logs, or --force-coarse "
                         "(results will be labelled MODEL-ON-COARSE-INPUT)" % json.dumps(src.sampling))
    ev, lost = run(cal, src, a.period_ms, a.jitter_ms, a.seed, a.drop_prob, not a.no_f32)
    fired = [e for e in ev if e["fired"]]
    print(json.dumps({"label": label, "input_mode": src.mode,
                      "sampling": getattr(src, "sampling", None), "model": head,
                      "fired": len(fired), "lost_activations_simulated": lost,
                      "total_extra_us": round(sum(e["B80C_us"] for e in fired), 1),
                      "events": [e for e in ev if e["fired"] or e.get("block") not in (None, "delta<min")]},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
