#!/usr/bin/env python3
"""Validates every data/*.json file parses as JSON.

These are fetched client-side by loadMoreData() in index.html; a broken
file wouldn't throw a build error anywhere, it would just silently fail
to load in the browser (caught, logged to console, nothing more) -- so
this is the only thing that would actually catch it before it ships.
"""
import json
import pathlib
import sys

DATA_DIR = pathlib.Path("data")


def main():
    if not DATA_DIR.is_dir():
        print(f"No {DATA_DIR}/ directory found -- nothing to check.")
        return

    files = sorted(DATA_DIR.glob("*.json")) + sorted(DATA_DIR.glob("colleges/*.json"))
    if not files:
        print(f"No .json files in {DATA_DIR}/ -- nothing to check.")
        return

    failures = []
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            failures.append((path, str(e)))

    if failures:
        print(f"JSON validity check FAILED for {len(failures)} of {len(files)} file(s):\n")
        for path, err in failures:
            print(f"  - {path}: {err}")
        sys.exit(1)

    # the college directory: every state listed in the index needs its file, with the rows it promises
    idx_path = DATA_DIR / "colleges" / "index.json"
    if idx_path.exists():
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        problems = []
        for st in idx.get("states", []):
            f = DATA_DIR / "colleges" / (st["code"] + ".json")
            if not f.exists():
                problems.append(f"{f} is missing")
                continue
            d = json.loads(f.read_text(encoding="utf-8"))
            if len(d.get("rows", [])) != st["count"]:
                problems.append(f"{f}: index says {st['count']} rows, file has {len(d.get('rows', []))}")
            if d.get("cols", [None])[0] != "id":
                problems.append(f"{f}: unexpected column layout")
        if problems:
            print("College directory check FAILED:\n" + "\n".join("  - " + x for x in problems))
            sys.exit(1)

    print(f"JSON OK: {len(files)} file(s) in {DATA_DIR}/ all parse.")


if __name__ == "__main__":
    main()
