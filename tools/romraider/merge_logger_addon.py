#!/usr/bin/env python3
"""Merge a DKmode ecuparam addon into a COPY of a RomRaider logger definition.

The original logger file is never modified. The addon <ecuparam> nodes are
inserted as text into the SSM protocol's <ecuparams> section of a new file,
so the original formatting is kept. Before writing, the script checks:
  * both files are well-formed XML;
  * the addon only contains <ecuparam> elements with id, name, <ecu id>,
    <address> (0xFFxxxx, length 1/2/4) and <conversion> with units/expr;
  * float parameters use length 4, uint16 uses length 2;
  * no addon id or name collides with an existing ecuparam;
  * the merged result parses again and contains every addon id once.

  python merge_logger_addon.py original.xml addon.xml merged.xml [--ecu-id 1356212FFF]
  python merge_logger_addon.py --check addon.xml          # validate addon only
"""
import argparse, re, sys
import xml.etree.ElementTree as ET
from pathlib import Path

LENGTH_FOR = {"float": 4, "uint16": 2, "int16": 2, "uint8": 1, "int8": 1, "uint32": 4, "int32": 4}


def check_addon(path, ecu_id=None):
    root = ET.parse(path).getroot()
    if root.tag != "ecuparams":
        raise ValueError("addon root must be <ecuparams>")
    ids, problems = [], []
    for p in root.findall("ecuparam"):
        pid, name = p.get("id"), p.get("name")
        if not pid or not re.fullmatch(r"E\d+", pid) or not name:
            problems.append("bad id/name: %r %r" % (pid, name)); continue
        ids.append(pid)
        ecus = p.findall("ecu")
        if not ecus:
            problems.append(pid + ": no <ecu>")
        for e in ecus:
            if ecu_id and ecu_id not in e.get("id", "").split(","):
                problems.append(pid + ": ecu id %s not listed" % ecu_id)
            a = e.find("address")
            if a is None or not re.fullmatch(r"0x[0-9A-Fa-f]{6}", (a.text or "").strip()):
                problems.append(pid + ": bad address"); continue
            ln = int(a.get("length", "1"))
            convs = p.findall("conversions/conversion")
            if not convs:
                problems.append(pid + ": no conversion")
            for c in convs:
                if not c.get("units") or not c.get("expr"):
                    problems.append(pid + ": conversion needs units and expr")
                st = c.get("storagetype", "uint8" if ln == 1 else None)
                if st is None:
                    problems.append(pid + ": length %d needs storagetype" % ln)
                elif LENGTH_FOR.get(st) != ln:
                    problems.append(pid + ": storagetype %s vs length %d" % (st, ln))
    if len(set(ids)) != len(ids):
        problems.append("duplicate ids in addon")
    return ids, [p.get("name") for p in root.findall("ecuparam")], problems


def merge(original, addon, out, ecu_id):
    if Path(out).resolve() == Path(original).resolve():
        raise SystemExit("refusing to overwrite the original logger file")
    ids, names, problems = check_addon(addon, ecu_id)
    if problems:
        raise SystemExit("addon check failed:\n  " + "\n  ".join(problems))
    text = Path(original).read_text(encoding="utf-8")
    root = ET.fromstring(text.encode("utf-8"))
    ssm = [p for p in root.iter("protocol") if p.get("id") == "SSM"]
    if not ssm or ssm[0].find("ecuparams") is None:
        raise SystemExit("original has no SSM <ecuparams> section")
    exist_ids = {e.get("id") for e in ssm[0].iter("ecuparam")}
    exist_names = {e.get("name") for e in ssm[0].iter("ecuparam")}
    clash = sorted(set(ids) & exist_ids) + sorted(set(names) & exist_names)
    if clash:
        raise SystemExit("id/name collision with original: %s" % clash)
    # textual insertion right before the SSM </ecuparams>
    m_open = re.search(r'<protocol\s+id="SSM"', text)
    m_close = text.find("</ecuparams>", m_open.end())
    body = Path(addon).read_text(encoding="utf-8")
    inner = re.search(r"<ecuparams>(.*)</ecuparams>", body, re.S).group(1).rstrip() + "\n"
    note = "    <!-- DKmode v75 research addon (%s) -->\n" % Path(addon).name
    merged = text[:m_close] + note + inner + "            " + text[m_close:]
    root2 = ET.fromstring(merged.encode("utf-8"))
    got = [e.get("id") for p in root2.iter("protocol") if p.get("id") == "SSM" for e in p.iter("ecuparam")]
    for i in ids:
        if got.count(i) != 1:
            raise SystemExit("merge verification failed for " + i)
    Path(out).write_text(merged, encoding="utf-8")
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--ecu-id", default="1356212FFF")
    a = ap.parse_args()
    if a.check:
        ids, _, problems = check_addon(a.files[0], a.ecu_id)
        print("ids:", ", ".join(ids))
        if problems:
            print("PROBLEMS:\n  " + "\n  ".join(problems)); sys.exit(1)
        print("addon OK"); return
    if len(a.files) != 3:
        ap.error("need original.xml addon.xml merged.xml")
    ids = merge(*a.files, a.ecu_id)
    print("merged %d parameters into %s (original untouched)" % (len(ids), a.files[2]))


if __name__ == "__main__":
    main()
