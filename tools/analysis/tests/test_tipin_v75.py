#!/usr/bin/env python3
"""v75 tests: Tip-in model (synthetic calibration), log analyzer, logger addon.

Run:  python -m unittest discover -s tools/analysis/tests -v
Optional ROM test: set DKMODE_ROM=/path/to/pinned.bin
"""
import csv, hashlib, math, os, random, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / "romraider"))

import sh7055_tipin_model_v74 as M          # noqa: E402
import sh7055_tipin_log_analyzer_v75 as A   # noqa: E402
import merge_logger_addon as X              # noqa: E402

ADDON = HERE.parent.parent / "romraider" / "logger_A2WC0MME_dkmode_tipin_v75_addon.xml"


def synth_cal(**kw):
    cal = {
        "rom": "synthetic", "status": "SYNTHETIC",
        "min_delta": 0.5, "min_amount_us": 400.0, "max_cum_delta": 23.0, "max_events": 7,
        "reset_events_after": 22, "reset_cum_after": 22,
        "tip": M.Table1D(axis=[0.0, 10.0, 20.0], raw=[100, 200, 300], mult=4.0),
        "kboost": M.Table1D(axis=[0.0, 128.0], raw=[64, 128], mult=1 / 128, typ=4),
        "kect": M.Table1D(axis=[-40.0, 80.0], raw=[16384, 8192], mult=1 / 8192),
    }
    cal.update(kw)
    return cal


def press(model, seq, be=200.0, ect=85.0):
    return [model.step(x, be, ect) for x in seq]


class TableTests(unittest.TestCase):
    def setUp(self):
        self.t = synth_cal()["tip"]

    def test_clamp_and_points(self):
        self.assertEqual(self.t(-5.0), 400.0)      # below axis -> first point
        self.assertEqual(self.t(0.0), 400.0)
        self.assertEqual(self.t(10.0), 800.0)      # exact interior point
        self.assertEqual(self.t(20.0), 1200.0)     # last point
        self.assertEqual(self.t(99.0), 1200.0)     # above axis -> last point

    def test_linear(self):
        self.assertAlmostEqual(self.t(5.0), 600.0, places=3)
        self.assertAlmostEqual(self.t(15.0), 1000.0, places=3)

    def test_float32(self):
        v = self.t(1.0 / 3.0)
        self.assertEqual(v, M.F(v))                # result is representable in binary32


class ModelLogicTests(unittest.TestCase):
    def test_history_prefill_no_spurious_event(self):
        m = M.OemTipin(synth_cal())
        ev = m.step(30.0, 200, 85)
        self.assertEqual(ev["delta"], 0.0)
        self.assertFalse(ev["fired"])

    def test_delta_is_two_runs(self):
        m = M.OemTipin(synth_cal())
        evs = press(m, [0.0, 1.0, 2.0, 3.0])
        self.assertEqual([round(e["delta"], 6) for e in evs], [0.0, 1.0, 2.0, 2.0])

    def test_delta_equal_threshold_passes(self):
        m = M.OemTipin(synth_cal(min_amount_us=0.0))
        evs = press(m, [0.0, 0.0, 0.5])
        self.assertTrue(evs[-1]["fired"])

    def test_amount_equal_threshold_fires_and_below_blocks(self):
        cal = synth_cal()
        amt = M.F(M.F(cal["tip"](1.0) * cal["kboost"](200.0)) * cal["kect"](85.0))
        m = M.OemTipin(synth_cal(min_amount_us=amt))
        self.assertTrue(press(m, [0.0, 0.0, 1.0])[-1]["fired"])
        m = M.OemTipin(synth_cal(min_amount_us=M.F(amt + 0.01)))
        ev = press(m, [0.0, 0.0, 1.0])[-1]
        self.assertEqual(ev["block"], "B80C<min")

    def test_event_limit(self):
        m = M.OemTipin(synth_cal())
        evs = press(m, [i * 1.0 for i in range(20)])
        self.assertEqual(sum(e["fired"] for e in evs), 7)
        self.assertEqual(evs[-1]["block"], "B818 limit")

    def test_cumulative_limit_equality_blocks(self):
        m = M.OemTipin(synth_cal(max_cum_delta=20.0, max_events=99))
        evs = press(m, [0, 0, 10, 20, 30, 40])      # deltas 10, 20 -> cum 10, then 30 >= 20
        fired = [e for e in evs if e["fired"]]
        self.assertEqual(len(fired), 2)
        self.assertEqual(evs[-1]["block"], "B814 limit")

    def test_negative_delta_resets_series(self):
        m = M.OemTipin(synth_cal())
        press(m, [i * 1.0 for i in range(10)])
        self.assertEqual(m.b818, 7)
        press(m, [5.0, 0.0])                          # release
        self.assertEqual((m.b818, m.b814), (0, 0.0))

    def test_b821_reset_after_quiet_runs(self):
        m = M.OemTipin(synth_cal())
        press(m, [i * 1.0 for i in range(10)])
        self.assertEqual(m.b818, 7)
        press(m, [9.0] * (21 - m.b821))               # delta 0, not negative
        self.assertEqual((m.b821, m.b818), (21, 7))   # B821 = 21 < 22: no reset yet
        press(m, [9.0])
        self.assertEqual((m.b821, m.b818), (22, 0))   # B821 reached 22

    def test_repeated_presses(self):
        cal = synth_cal()
        def series(gap_runs):
            m = M.OemTipin(dict(cal, tip=cal["tip"], kboost=cal["kboost"], kect=cal["kect"]))
            seq = [i * 1.0 for i in range(10)] + [9.0] * gap_runs + [9.0 + i for i in range(1, 10)]
            return sum(e["fired"] for e in press(m, seq))
        self.assertEqual(series(5), 7)                # second press inside reset window: blocked
        self.assertEqual(series(30), 14)              # after reset: a new series of 7

    def test_gates(self):
        m = M.OemTipin(synth_cal())
        m.step(0, 200, 85); m.step(0, 200, 85)
        self.assertEqual(m.step(5, 200, 85, gate_b018=True)["block"], "gate B018.1")
        self.assertEqual(m.step(10, 200, 85, gate_b469=True)["block"], "gate B469.7")


class RunTests(unittest.TestCase):
    def fired(self, profile, **kw):
        ev, lost = M.run(synth_cal(), profile, 8.0, **kw)
        return sum(e["fired"] for e in ev), ev, lost

    def test_slow_medium_fast(self):
        slow = M.Profile([(0, 5), (50, 5), (2050, 15), (2300, 15)])     # 5 %/s
        med = M.Profile([(0, 5), (50, 5), (150, 25), (400, 25)])        # 200 %/s
        fast = M.Profile([(0, 5), (50, 5), (75, 80), (400, 80)])        # 3000 %/s
        n_slow, _, _ = self.fired(slow)
        n_med, _, _ = self.fired(med)
        n_fast, ev_fast, _ = self.fired(fast)
        self.assertEqual(n_slow, 0)                   # delta per 16 ms << 0.5
        self.assertGreater(n_med, 0)
        self.assertTrue(any(e.get("block") == "B814 limit" for e in ev_fast))

    def test_drop_and_jitter(self):
        n, ev, lost = self.fired(M.Profile([(0, 5), (50, 5), (150, 25), (400, 25)]),
                                 jitter_ms=3.0, drop_prob=0.2, seed=3)
        self.assertGreater(lost, 0)
        self.assertTrue(all(0 <= e["t_ms"] - round(e["t_ms"] / 8.0 - 0.5) * 8.0 <= 8.0 for e in ev))

    def test_input_classification(self):
        t_daq = [i * 1.0 for i in range(2000)]
        t_ssm = [i * 48.0 for i in range(200)]
        self.assertEqual(M.classify_input(t_daq, 8.0)[0], "daq")
        self.assertEqual(M.classify_input(t_ssm, 8.0)[0], "ssm")


def write_log(path, rows, header):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def hms(ms):
    s = ms / 1000.0
    h = int(s // 3600) % 24; m = int(s % 3600 // 60); x = s % 60
    return "%02d:%02d:%06.3f" % (h, m, x)


class AnalyzerTests(unittest.TestCase):
    def synth(self, rate, span_s=200.0, glitches=5, seed=7):
        rnd = random.Random(seed)
        t, rows = 3_600_000.0 * 23.98, []           # starts near midnight -> rollover
        c0 = 60000.0
        lost = 0
        while len(rows) * 0.048 < span_s:
            cnt = int(c0 + (t - 3_600_000.0 * 23.98) / 1000.0 * rate) % 65536
            if glitches and rnd.random() < glitches / 4000.0 * 1:
                cnt = (cnt + rnd.choice([256, -256])) % 65536
            lost = min(255, lost + (1 if rnd.random() < 0.01 else 0))
            rows.append([hms(t), "1500", cnt, lost])
            t += 48.0 + rnd.uniform(-3, 3)
        return rows

    def run_an(self, rows, header, rom=None):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "log.csv")
        write_log(p, rows, header)
        return A.analyze(p, rom, d, do_plot=False)

    HDR = ["Time", "Engine Speed (rpm)", "DKmode CMT1 Half-Tick Counter 94F0 (count)",
           "DKmode Task9 Lost Activations 94E4 (count)"]

    def test_cmt1_rate_20mhz_with_wrap_and_glitches(self):
        rep = self.run_an(self.synth(500.0, glitches=40), self.HDR)
        c = rep["counter_derived"]["cmt1"]
        self.assertAlmostEqual(c["counts_per_s"], 500.0, delta=2.5)
        self.assertTrue(c["matches_20mhz"])
        self.assertAlmostEqual(c["implied_task9_activation_period_ms"], 8.0, delta=0.05)
        self.assertEqual(rep["input_mode"], "ssm")
        self.assertIn("per-run Delta TPS", " ".join(rep["unavailable"]))

    def test_cmt1_rate_40mhz_detected(self):
        rep = self.run_an(self.synth(1000.0, glitches=0), self.HDR)
        c = rep["counter_derived"]["cmt1"]
        self.assertAlmostEqual(c["implied_pphi_mhz"], 40.0, delta=0.2)
        self.assertFalse(c["matches_20mhz"])

    def test_lost_activation_counter(self):
        rows = [[hms(i * 48.0), "800", 0, v] for i, v in enumerate([0, 0, 1, 1, 3, 255, 255])]
        rep = self.run_an(rows, self.HDR)
        self.assertEqual(rep["counter_derived"]["cmt1"]["category"], "unavailable")  # static 94F0
        la = rep["counter_derived"]["task9_lost_activations"]
        self.assertEqual(la["increments_in_log"], 255)
        self.assertTrue(la["saturated_255"])

    def test_series_and_limit(self):
        hdr = ["Time", "DKmode Tip-in Event Count B818 (count)",
               "DKmode Task9 Runs Since Tip-in B821 (runs)",
               "DKmode Tip-in Enrichment B80C (us)",
               "DKmode Tip-in Cumulative Delta B814 (raw B024)",
               "DKmode Throttle Plate Opening Angle B024 (%)"]
        seq = [(0, 200, 0, 0, 5), (0, 200, 0, 0, 5), (3, 1, 600, 4, 15), (7, 5, 650, 9, 25),
               (7, 11, 650, 9, 25), (7, 17, 650, 9, 25), (0, 23, 650, 9, 25), (0, 29, 650, 9, 25)]
        rows = [[hms(i * 48.0)] + list(r) for i, r in enumerate(seq)]
        d = tempfile.mkdtemp(); p = os.path.join(d, "s.csv"); write_log(p, rows, hdr)
        t, cols, info = A.load_csv(p)
        self.assertAlmostEqual(cols["B024"][0], 5 * 0.84)          # % -> raw
        cal = {"max_events": 7, "max_cum_delta": 23.0, "min_amount_us": 385.0}
        ev = A.events(t, cols, cal)
        self.assertEqual(len(ev["series"]), 1)
        s = ev["series"][0]
        self.assertEqual(s["max_b818"], 7)
        self.assertEqual(s["limiting_factor"]["value"], "B818 event limit")
        cal2 = {"max_events": 99, "max_cum_delta": 99.0, "min_amount_us": 385.0}
        s2 = A.events(t, cols, cal2)["series"][0]
        self.assertEqual(s2["limiting_factor"]["category"], "unavailable")

    def test_semicolon_decimal_comma_locale(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "loc.csv")
        with open(p, "w") as f:
            f.write("Time (msec);Engine Speed (rpm);DKmode CMT1 Half-Tick Counter 94F0 (count);"
                    "DKmode Throttle Plate Opening Angle B024 (%)\n")
            c = 65000
            for i in range(400):
                f.write("%d;876;%d;3,96\n" % (i * 77, (c + int(i * 77 * 0.5)) % 65536))
        t, cols, info = A.load_csv(p)
        self.assertEqual(t[1], 77.0)
        self.assertAlmostEqual(cols["B024"][0], 3.96 * 0.84)
        r = A.cmt1_rate(t, cols["94F0"])
        self.assertAlmostEqual(r["counts_per_s"], 500.0, delta=1.0)

    def test_time_parsing(self):
        self.assertAlmostEqual(A.parse_time("00:11:07.732"), 667732.0)
        self.assertEqual(A.parse_time("1234.5"), 1234.5)


class LoggerXmlTests(unittest.TestCase):
    def test_addon_valid(self):
        ids, names, problems = X.check_addon(ADDON, "1356212FFF")
        self.assertEqual(problems, [])
        self.assertEqual(len(ids), 10)
        self.assertIn("E7509", ids)

    def test_merge_into_copy(self):
        d = tempfile.mkdtemp()
        orig = os.path.join(d, "orig.xml")
        Path(orig).write_text('<?xml version="1.0"?>\n<logger version="370"><protocols>'
                              '<protocol id="SSM" baud="4800"><parameters/><ecuparams>'
                              '<ecuparam id="E1" name="X"><ecu id="1356212FFF"><address>0xFF0000</address></ecu>'
                              '<conversions><conversion units="raw" expr="x"/></conversions></ecuparam>'
                              '</ecuparams></protocol></protocols></logger>\n')
        h0 = hashlib.sha256(Path(orig).read_bytes()).hexdigest()
        out = os.path.join(d, "merged.xml")
        ids = X.merge(orig, ADDON, out, "1356212FFF")
        self.assertEqual(hashlib.sha256(Path(orig).read_bytes()).hexdigest(), h0)
        self.assertEqual(len(ids), 10)
        with self.assertRaises(SystemExit):
            X.merge(orig, ADDON, orig, "1356212FFF")          # never overwrite original
        with self.assertRaises(SystemExit):
            X.merge(out, ADDON, os.path.join(d, "twice.xml"), "1356212FFF")  # collision


@unittest.skipUnless(os.environ.get("DKMODE_ROM"), "set DKMODE_ROM to a SHA-pinned ROM")
class RomTests(unittest.TestCase):
    def test_load_and_ramp(self):
        cal = M.load(os.environ["DKMODE_ROM"])
        self.assertTrue(cal["status"].startswith(("ROM-CONFIRMED", "PROXY-CONFIRMED", "CODE-AUDITED")))
        ev, _ = M.run(cal, M.Ramp("5:35:120", 200.0, 85.0), 8.0)
        self.assertLessEqual(sum(e["fired"] for e in ev), cal["max_events"])

    def test_identify_known_and_modified(self):
        import rom_identify_v75 as I
        rep = I.identify(os.environ["DKMODE_ROM"])
        self.assertIn(rep["level"], ("KNOWN-ROM", "KNOWN-PROXY", "KNOWN-AUDITED"))
        self.assertTrue(all(rep["logger_ram_anchors"].values()))
        b = bytearray(Path(os.environ["DKMODE_ROM"]).read_bytes())
        b[0x7FFF0] ^= 1                               # unrelated byte -> unknown SHA
        p = os.path.join(tempfile.mkdtemp(), "mod.bin"); Path(p).write_bytes(b)
        rep2 = I.identify(p)
        self.assertEqual(rep2["level"], "UNKNOWN")
        self.assertIn("DO NOT", rep2["verdict"])
        with self.assertRaises(SystemExit):
            M.load(p)                                 # never whitelisted implicitly


if __name__ == "__main__":
    unittest.main()
