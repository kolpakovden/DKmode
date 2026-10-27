#!/usr/bin/env python3
"""v76: byte-compare the code regions traced in v69-v73 between a candidate ROM
and an already audited reference ROM. STRICT READ ONLY.

A candidate with an unknown SHA-256 may be added to the DKmode whitelists only
when every region below is byte-identical to an audited reference AND all
instruction anchors of rom_identify_v75 hold. Calibration areas are expected
to differ and are reported separately (they are read per ROM by the model).

  python rom_code_audit_v76.py CANDIDATE.bin REFERENCE.bin [REFERENCE2.bin ...]
"""
import argparse, hashlib, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rom_identify_v75  # noqa: E402

REGIONS = {
    "vectors": (0x7FC50, 0x7FFF4), "isr_stubs": (0x2770, 0x3298), "os_core": (0x3298, 0x3FE0),
    "task_table": (0x4640, 0x47DC), "atu_pfc_init": (0x4B8C, 0x5050), "isr_bodies": (0x5078, 0x5D30),
    "task9_handler": (0x6330, 0x63E0), "adc_isr": (0x6A4A, 0x6C70), "tps_scaling": (0x7618, 0x7750),
    "injector_ctl": (0x9074, 0x9B9C), "tick_slots": (0xCD14, 0xCFA4), "activate_err_tick": (0xD02A, 0xD320),
    "events": (0xD59C, 0xD878), "dcnt_write": (0xD964, 0xD99C), "chan_table": (0xF4EC, 0xF534),
    "tick_tables": (0xF60C, 0xF67C), "event_route": (0xF6AC, 0xF6B0), "event_tab": (0xF75C, 0xF784),
    "call_chain": (0x1028C, 0x10600), "tipin_cb": (0x114B0, 0x11500), "tps_learn_A": (0x15290, 0x159D8),
    "tps_learn_B": (0x16690, 0x16B80), "delta_tps": (0x170E8, 0x17260), "gate": (0x1763A, 0x17670),
    "cut_mask": (0x1DCF4, 0x1DEF8), "interp": (0x2088, 0x2780), "tipin": (0x24A04, 0x24BE8),
    "async_pulse": (0x272F8, 0x27470),
}


def audit(cand, refs):
    a = Path(cand).read_bytes()
    out = {"candidate": str(cand), "sha256": hashlib.sha256(a).hexdigest(),
           "identify": rom_identify_v75.identify(cand), "references": []}
    ok_any = False
    for r in refs:
        b = Path(r).read_bytes()
        diff = {k: sum(x != y for x, y in zip(a[s:e], b[s:e])) for k, (s, e) in REGIONS.items()}
        bad = {k: v for k, v in diff.items() if v}
        out["references"].append({"reference": str(r), "sha256": hashlib.sha256(b).hexdigest(),
                                  "regions_checked": len(REGIONS), "regions_differing": bad,
                                  "total_differing_bytes": sum(x != y for x, y in zip(a, b))})
        ok_any |= not bad
    anchors = out["identify"].get("logger_ram_anchors", {})
    out["code_equivalent"] = ok_any and out["identify"].get("tipin_literal_pool_ok", False) and all(anchors.values())
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidate")
    ap.add_argument("references", nargs="+")
    a = ap.parse_args()
    print(json.dumps(audit(a.candidate, a.references), indent=2, ensure_ascii=False))
