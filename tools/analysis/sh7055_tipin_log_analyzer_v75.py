#!/usr/bin/env python3
"""v75 analyzer for RomRaider CSV logs of the OEM SH7055 Tip-in. READ ONLY.

Every reported quantity carries one of four categories:
  measured         value read from the ECU at the logged instant (SSM sample)
  counter-derived  computed from ECU counters across samples (94F0, 94E4,
                   B818, B821); exact over the interval, not at a single instant
  model            produced by the v74/v75 model from an input trace
  unavailable      cannot be determined at this sampling rate (needs DAQ)

The analyzer never interpolates SSM samples into per-run (8 ms) events.

  python sh7055_tipin_log_analyzer_v75.py log.csv [--rom ROM.bin] [--out DIR] [--plot]

--rom loads Tip-in limits (max events, cumulative limit, thresholds) from a
SHA-pinned ROM via sh7055_tipin_model_v74.load(); without it, limit-based
classification is reported as unavailable.
"""
import argparse, csv, json, math, re, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# canonical key -> list of (regex on column name, kind)  ; kind decides unit handling
COLUMNS = {
    "B024": [(r"DKmode Throttle Plate Opening Angle B024", "b024"),
             (r"^Throttle Plate Opening Angle \(4-byte\)", "b024")],
    "B028": [(r"DKmode Delta TPS B028", "b028"), (r"^Tip-in Throttle", "b028_e54")],
    "B80C": [(r"DKmode Tip-in Enrichment B80C", "time"), (r"^Tip-in Enrichment \(Last Calculated\)", "time_us")],
    "B810": [(r"DKmode Tip-in Applied Amount B810", "time")],
    "B814": [(r"DKmode Tip-in Cumulative Delta B814", "raw")],
    "B818": [(r"DKmode Tip-in Event Count B818", "raw")],
    "B821": [(r"DKmode Task9 Runs Since Tip-in B821", "raw")],
    "94E4": [(r"DKmode Task9 Lost Activations 94E4", "raw")],
    "94F0": [(r"DKmode CMT1 Half-Tick Counter 94F0", "raw")],
    "B8D8": [(r"DKmode Injector Latency B8D8", "time"), (r"Fuel Injector #1 Latency", "time")],
    "RPM": [(r"^Engine Speed", "raw")],
    "MAP": [(r"Manifold Absolute Pressure", "pressure")],
    "IPW": [(r"Fuel Injector #1 Pulse Width", "time")],
    "ECT": [(r"^Coolant Temperature", "raw")],
    "TPS_SSM": [(r"^Throttle Opening Angle", "raw")],
    "AFR": [(r"Wideband|A/F Sensor #1", "raw")],
}
U16, U8_SAT = 65536, 255


def parse_time(s):
    s = s.strip()
    if ":" in s:                                  # RomRaider HH:MM:SS.mmm
        h, m, x = s.split(":")
        return (int(h) * 3600 + int(m) * 60 + float(x)) * 1000.0
    return float(s)                               # already ms


def split_units(col):
    m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", col)
    return (m.group(1), m.group(2)) if m else (col, "")


def load_csv(path):
    rows = list(csv.reader(open(path, newline="", encoding="utf-8", errors="replace")))
    head, data = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    t = [parse_time(r[0]) for r in data]
    for i in range(1, len(t)):                    # midnight rollover
        while t[i] < t[i - 1] - 43_200_000:
            t[i] += 86_400_000
    cols, info = {}, {}
    for j, name in enumerate(head[1:], start=1):
        base, unit = split_units(name)
        for key, pats in COLUMNS.items():
            if key in cols:
                continue
            for pat, kind in pats:
                if re.search(pat, name):
                    vals = []
                    for r in data:
                        try:
                            vals.append(float(r[j]))
                        except (ValueError, IndexError):
                            vals.append(math.nan)
                    cols[key] = normalise(key, kind, unit, vals)
                    info[key] = {"column": name, "unit_in_log": unit, "kind": kind}
                    break
    return t, cols, info


def normalise(key, kind, unit, v):
    u = unit.lower()
    if kind == "b024":                            # to raw B024 units
        return [x * 0.84 for x in v] if u == "%" else v
    if kind == "b028":
        return [x * 0.84 for x in v] if "%" in u else v
    if kind == "b028_e54":                        # RomRaider E54: expr x, label "%": value is raw
        return v
    if kind in ("time", "time_us"):               # to microseconds
        if u == "ms":
            return [x * 1000.0 for x in v]
        return v                                  # us or "raw ecu value" (= us, v72)
    if kind == "pressure":                        # to mmHg absolute
        f = {"bar": 750.0617, "bar absolute": 750.0617, "kpa": 7.500617, "kpa absolute": 7.500617,
             "psi": 51.71493, "psi absolute": 51.71493, "mmhg": 1.0, "mmhg absolute": 1.0}.get(u)
        return [x * f for x in v] if f else v
    return v


def sampling(t):
    d = sorted(b - a for a, b in zip(t, t[1:]))
    if not d:
        return {"samples": len(t)}
    q = lambda p: d[min(len(d) - 1, int(p * (len(d) - 1)))]
    return {"samples": len(t), "span_s": (t[-1] - t[0]) / 1000.0, "median_dt_ms": statistics.median(d),
            "p5_dt_ms": q(0.05), "p95_dt_ms": q(0.95), "max_dt_ms": d[-1],
            "rate_hz": 1000.0 / statistics.median(d) if statistics.median(d) > 0 else None}


def cmt1_rate(t, c, expect=500.0, tol=0.35):
    """Unwrap u16 94F0, repair non-atomic +-256 reads, estimate counts/s."""
    pts = [(ti, ci) for ti, ci in zip(t, c) if not math.isnan(ci)]
    if len(pts) < 3:
        return None
    raw = []
    for (t0, c0), (t1, c1) in zip(pts, pts[1:]):
        raw.append((t1 - t0, (int(c1) - int(c0)) % U16))
    rates = [dc / dt * 1000.0 for dt, dc in raw if dt > 0]
    r0 = statistics.median(rates)
    fixed, glitches, ambiguous, used_dt, used_dc = [], 0, 0, 0.0, 0
    for dt, dc in raw:
        if dt <= 0:
            continue
        if dt / 1000.0 * r0 >= U16 * 0.9:        # possible multiple wraps
            ambiguous += 1
            continue
        exp = r0 * dt / 1000.0
        cands = [dc, dc + 256, dc - 256, (dc + 256) % U16, (dc - 256) % U16]
        best = min(cands, key=lambda x: abs(x - exp))
        if abs(best - exp) > max(tol * exp, 32):
            ambiguous += 1
            continue
        if best != dc:
            glitches += 1
        used_dt += dt; used_dc += best
    if used_dt <= 0:
        return None
    rate = used_dc / used_dt * 1000.0
    if rate <= 0:
        return {"category": "unavailable", "counts_per_s": 0.0,
                "why": "94F0 does not change: address probably wrong for this ROM, or logger not reading RAM"}
    med_dt = statistics.median([dt for dt, _ in raw if dt > 0])
    rel_err = med_dt / used_dt                   # endpoint timing uncertainty (one poll)
    return {"category": "counter-derived",
            "counts_per_s": rate, "rel_uncertainty": rel_err,
            "intervals_used": len(raw) - ambiguous, "intervals_rejected": ambiguous,
            "nonatomic_256_repairs": glitches, "span_used_s": used_dt / 1000.0,
            "implied_cmt1_tick_ms": 1000.0 / (2 * rate),
            "implied_pphi_mhz": 0.04 * rate,
            "implied_task9_activation_period_ms": 4000.0 / rate,
            "expected_if_pphi_20mhz": {"counts_per_s": expect, "tick_ms": 1.0, "task9_ms": 8.0},
            "matches_20mhz": abs(rate - expect) <= max(expect * 3 * rel_err, expect * 0.005)}


def lost_activations(v):
    pts = [int(x) for x in v if not math.isnan(x)]
    if not pts:
        return None
    inc, resets, sat = 0, 0, any(x >= U8_SAT for x in pts)
    for a, b in zip(pts, pts[1:]):
        if b >= a:
            inc += b - a
        else:
            resets += 1; inc += b
    return {"category": "counter-derived", "first": pts[0], "last": pts[-1],
            "increments_in_log": inc, "decreases (ECU reset?)": resets,
            "saturated_255": sat,
            "note": "lower bound if saturated" if sat else "exact over the log span"}


def events(t, cols, cal):
    """Event detection from latched counters; never per-run timing."""
    b818, b821, b80c, b814 = (cols.get(k) for k in ("B818", "B821", "B80C", "B814"))
    if b818 is None and b821 is None:
        return None
    n = len(t)
    g = lambda arr, i: (arr[i] if arr is not None and not math.isnan(arr[i]) else None)
    rows, series, cur = [], [], None
    for i in range(1, n):
        e818 = e821 = e80c = False
        lo = 0
        a, b = g(b818, i - 1), g(b818, i)
        if a is not None and b is not None and (b > a or 0 < b < a):
            e818 = True                             # b < a but > 0: reset, then >= b new events
            lo = b - a if b > a else b
        a2, b2 = g(b821, i - 1), g(b821, i)
        if a2 is not None and b2 is not None and b2 < a2:
            e821 = True; lo = max(lo, 1)
        a3, b3 = g(b80c, i - 1), g(b80c, i)
        if a3 is not None and b3 is not None and b3 != a3:
            e80c = True
        hit = e818 or e821
        rows.append({"t_ms": t[i], "event_lower_bound": lo, "b818": b, "b821": b2,
                     "b80c_us": b3, "b80c_changed": e80c, "event": hit})
        if hit:
            if cur is None or (b is not None and a is not None and b < a):
                cur = {"t_start_ms": t[i], "samples": [], "max_b818": 0, "max_b814": 0.0,
                       "b80c_values": []}
                series.append(cur)
            cur["samples"].append(i)
            if b is not None:
                cur["max_b818"] = max(cur["max_b818"], b)
            if b814 is not None and not math.isnan(b814[i]):
                cur["max_b814"] = max(cur["max_b814"], b814[i])
            if b3 is not None:
                cur["b80c_values"].append(b3)
        elif cur is not None and b is not None and b == 0:
            cur = None
    for s in series:
        s["t_end_ms"] = t[s["samples"][-1]]
        s["category"] = "counter-derived"
        s["events_lower_bound"] = s["max_b818"]
        if cal is None:
            s["limiting_factor"] = {"category": "unavailable", "why": "no --rom calibration"}
        elif s["max_b818"] >= cal["max_events"]:
            s["limiting_factor"] = {"category": "counter-derived", "value": "B818 event limit"}
        elif s["max_b814"] >= cal["max_cum_delta"]:
            s["limiting_factor"] = {"category": "counter-derived", "value": "B814 cumulative limit"}
        elif any(v < cal["min_amount_us"] for v in s["b80c_values"]):
            s["limiting_factor"] = {"category": "counter-derived",
                                    "value": "B80C below amount threshold seen (B80C is stored before the check)"}
        else:
            s["limiting_factor"] = {"category": "unavailable",
                                    "why": "delta-threshold vs throttle release needs per-run data (DAQ)"}
        del s["samples"]
    return {"per_sample": rows, "series": series}


def plot(t, cols, out):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    keys = [k for k in ("B024", "B028", "B80C", "B818", "B814", "RPM", "MAP", "94E4") if k in cols]
    if not keys:
        return None
    ts = [(x - t[0]) / 1000.0 for x in t]
    fig, ax = plt.subplots(len(keys), 1, figsize=(10, 1.7 * len(keys)), sharex=True)
    ax = ax if len(keys) > 1 else [ax]
    for a, k in zip(ax, keys):
        a.step(ts, cols[k], where="post", lw=0.9)
        a.set_ylabel(k, rotation=0, ha="right", fontsize=8)
        a.grid(alpha=0.3)
    ax[-1].set_xlabel("s (SSM sample time, measured values; steps = sample-and-hold, not interpolation)")
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    return str(out)


def analyze(path, rom=None, out_dir=None, do_plot=False):
    t, cols, info = load_csv(path)
    smp = sampling(t)
    cal = None
    if rom:
        from sh7055_tipin_model_v74 import load
        c = load(rom)
        cal = {k: c[k] for k in ("rom", "status", "sha256", "min_delta", "min_amount_us",
                                 "max_cum_delta", "max_events", "reset_events_after", "reset_cum_after")}
    mode = "daq" if smp.get("median_dt_ms") is not None and smp["median_dt_ms"] <= 2.0 else "ssm"
    rep = {
        "file": str(path), "input_mode": mode, "sampling": smp, "columns": info,
        "calibration": cal or {"category": "unavailable", "why": "no --rom"},
        "measured": {k: {"category": "measured", "min": min(v), "max": max(v)}
                     for k, v in cols.items() if any(not math.isnan(x) for x in v)
                     for v in [[x for x in v if not math.isnan(x)]]},
        "counter_derived": {},
        "model": {"category": "model",
                  "note": "not run: SSM samples cannot be turned into task-9 events; "
                          "run sh7055_tipin_model_v74.py on a DAQ TPS trace"} if mode == "ssm" else
                 {"category": "model", "note": "DAQ-rate log: run the model with --csv on this trace"},
        "unavailable": [],
    }
    if "94F0" in cols:
        rep["counter_derived"]["cmt1"] = cmt1_rate(t, cols["94F0"])
    else:
        rep["unavailable"].append("CMT1 rate: 94F0 not logged")
    if "94E4" in cols:
        rep["counter_derived"]["task9_lost_activations"] = lost_activations(cols["94E4"])
    else:
        rep["unavailable"].append("lost activations: 94E4 not logged")
    ev = events(t, cols, cal)
    if ev:
        rep["counter_derived"]["tipin_series"] = ev["series"]
        rep["counter_derived"]["samples_with_event"] = sum(1 for r in ev["per_sample"] if r["event"])
    else:
        rep["unavailable"].append("Tip-in events: neither B818 nor B821 logged")
    if mode == "ssm":
        rep["unavailable"] += [
            "per-run Delta TPS sequence and exact event times (8 ms resolution) - needs DAQ TPS",
            "extra injector pulse timing and width - needs injector-signal DAQ",
            "which run crossed the Delta threshold - needs DAQ",
            "lambda response latency - needs fast wideband channel",
        ]
        if smp.get("median_dt_ms"):
            rep["sampling"]["task9_runs_per_sample_at_8ms"] = smp["median_dt_ms"] / 8.0
    if out_dir:
        o = Path(out_dir); o.mkdir(parents=True, exist_ok=True)
        stem = Path(path).stem
        (o / (stem + "_v75_report.json")).write_text(json.dumps(rep, indent=2, ensure_ascii=False))
        if ev:
            with open(o / (stem + "_v75_samples.csv"), "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(ev["per_sample"][0].keys()) + ["category"])
                w.writeheader()
                for r in ev["per_sample"]:
                    w.writerow(dict(r, category="counter-derived"))
        if do_plot:
            rep["plot"] = plot(t, cols, o / (stem + "_v75.png"))
            (o / (stem + "_v75_report.json")).write_text(json.dumps(rep, indent=2, ensure_ascii=False))
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--rom")
    ap.add_argument("--out")
    ap.add_argument("--plot", action="store_true")
    a = ap.parse_args()
    rep = analyze(a.csv, a.rom, a.out, a.plot)
    brief = {k: rep[k] for k in ("input_mode", "sampling", "counter_derived", "unavailable")}
    print(json.dumps(brief, indent=2, ensure_ascii=False, default=str)[:20000])


if __name__ == "__main__":
    main()
