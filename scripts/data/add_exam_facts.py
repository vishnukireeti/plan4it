#!/usr/bin/env python3
"""Merge verified exam facts into data/exams_verified.json.

Usage: python3 scripts/data/add_exam_facts.py facts.json
facts.json = {"<exam id>": {cycle, fee, mode, duration, attempts, pattern, age, eligibility,
              last:{reg,exam,result}, next:{exam,regOpens,regCloses,status,short}, site,
              links:[[label,url],...], src, checked}}
Every entry must name the official document it was read from (src) and the day it was checked.
"""
import json, pathlib, re, sys

OUT = pathlib.Path("data/exams_verified.json")
REQ = ("cycle", "src", "checked")

def main(path):
    new = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    pack = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"v": 1, "exams": {}}
    for k, v in new.items():
        miss = [r for r in REQ if not v.get(r)]
        if miss: sys.exit(f"{k}: missing {miss}")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v["checked"]): sys.exit(f"{k}: checked must be YYYY-MM-DD")
        for u in [v["src"]] + [l[1] for l in v.get("links", [])]:
            if not u.startswith("https://") and not u.startswith("http://"): sys.exit(f"{k}: bad url {u}")
        pack["exams"][k] = {kk: vv for kk, vv in v.items() if vv not in (None, "", [], {})}
    pack["exams"] = dict(sorted(pack["exams"].items()))
    pack["count"] = len(pack["exams"])
    OUT.write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(new)} merged, {pack['count']} exams verified in total")

if __name__ == "__main__":
    main(sys.argv[1])
