#!/usr/bin/env python3
"""Apply split_name_place() to the built directory shards in place (same rule the build uses).

Moves an address glued onto a college name to the address column, so cards show the real
name and searches for the locality still work. Safe to run more than once.
"""
import glob, importlib.util, json, pathlib, re

HERE = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location('build', HERE / 'build_colleges.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

changed = total = 0
for f in sorted(glob.glob('data/colleges/*.json')):
    if f.endswith(('index.json', 'links.json', 'josaa.json')):
        continue
    d = json.loads(pathlib.Path(f).read_text(encoding='utf-8'))
    c = d['cols']; iN, iA, iP = c.index('name'), c.index('address'), c.index('pin')
    for r in d['rows']:
        total += 1
        name, place = build.split_name_place(r[iN])
        if name != r[iN]:
            changed += 1
            r[iN] = name
            if place and not r[iA]:
                r[iA] = place
            if place and not r[iP]:
                m = re.search(r'\b(\d{6})\b', place.replace(' ', '') if re.search(r'\d{3}\s\d{3}', place) else place)
                if m:
                    r[iP] = m.group(1)
    d['rows'].sort(key=lambda r: r[iN].lower())
    with open(f, 'w', encoding='utf-8') as fh:
        json.dump(d, fh, ensure_ascii=False, separators=(',', ':'))
print(f'{changed} of {total} names cleaned')
