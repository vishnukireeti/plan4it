#!/usr/bin/env python3
"""Builds data/programmes.json (the "All programmes" browser) from two programme CSV exports.

Usage: python3 scripts/build_programmes.py UNDERGRAD.csv POSTGRAD.csv

Only facts are kept: programme, degree, university, city, duration, mode, fee and the source link tail.
Written descriptions, review scores and ranking badges in the CSVs belong to the portal they came from
and are deliberately NOT copied into the site.
"""
import json, re, sys
import pandas as pd

CITY_FIX = {'Bengalore': 'Bengaluru', 'Bhubaneshwar': 'Bhubaneswar', 'Calcutta': 'Kolkata', 'Cochin': 'Kochi',
            'Nasik': 'Nashik', 'Dehra Dun': 'Dehradun', 'Ahmadabad': 'Ahmedabad', 'Sangareddi': 'Sangareddy',
            'Gurgaon': 'Gurugram', 'Karari': 'Karari'}
NAGAR_BY_UNI = {'National Institute of Technology, Rourkela': 'Rourkela', 'JSS Academy of Higher Education and Research': 'Mysuru'}
DUR = re.compile(r'^\d+(½)?\s*years?$|^\d+\s*months?$')


def money(s):
    m = re.sub(r'[^\d]', '', str(s))
    return int(m) if m else None


def clean(df, level):
    rows, unis, degs, cities = [], {}, {}, {}
    seen = set()
    for r in df.to_dict('records'):
        dur, att, fmt, tui, per = (r['duration'], r['attendance'], r['format'], r['tuition'], r['tuition_period'])
        dur = None if pd.isna(dur) else str(dur)
        tui = str(tui)
        per = None if pd.isna(per) else str(per)
        # some rows are shifted one column to the right: duration/format/tuition have slid
        if DUR.match(tui):
            dur, tui, per = tui, (per or ''), None
            fmt = 'On-campus' if fmt not in ('Online', 'Blended') and dur is not None else fmt
        if fmt not in ('On-campus', 'Online', 'Blended'):
            fmt = 'Online' if dur == 'Online' else 'On-campus'
        if dur and not DUR.match(dur):
            dur = None
        fee = money(tui) if tui.startswith('₹') else None
        free = tui.strip().lower() == 'free'
        # fee period: y = per year, t = total programme, u = not stated
        ft = 'y' if per == 'yr' else 't' if per in ('full', 'total') else 'u'
        if per == 'module':
            ft = 'u'
        loc = str(r['location'])
        extra = re.search(r'\+(\d+)$', loc)
        city = re.sub(r'\s*\+\d+$', '', loc).replace(', India', '').strip()
        if city == 'Nagar':
            city = NAGAR_BY_UNI.get(r['university'], 'Nagar')
        city = CITY_FIX.get(city, city)
        m = re.match(r'https?://www\.(?:bachelors|masters)portal\.com/studies/(.+)$', str(r['url']))
        tail = m.group(1) if m else ''
        key = (r['programme'], r['university'], r['degree_type'], city, dur, fee)
        if key in seen:
            continue
        seen.add(key)
        u = unis.setdefault(r['university'], len(unis))
        d = degs.setdefault(r['degree_type'], len(degs))
        c = cities.setdefault(city, len(cities))
        mode = {'On-campus': 0, 'Online': 1, 'Blended': 2}[fmt]
        part = 1 if att == 'Part-time' else 0
        rows.append([r['programme'].strip(), u, d, c, dur or '', mode, part, -1 if free else (fee if fee is not None else 0), ft if (fee or free) else '', int(extra.group(1)) if extra else 0, tail])
    rows.sort(key=lambda x: (x[0].lower(), x[1]))
    inv = lambda m: [k for k, _ in sorted(m.items(), key=lambda kv: kv[1])]
    return {'unis': inv(unis), 'degrees': inv(degs), 'cities': inv(cities), 'rows': rows}


def main(ug, pg):
    out = {'v': 1,
           'about': 'Programme facts compiled from public listings; fees and seats change every year, so check the university before you apply.',
           'ug': clean(pd.read_csv(ug, encoding='utf-8-sig'), 'ug'),
           'pg': clean(pd.read_csv(pg, encoding='utf-8-sig'), 'pg')}
    with open('data/programmes.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    for k in ('ug', 'pg'):
        print(k, len(out[k]['rows']), 'programmes,', len(out[k]['unis']), 'universities,', len(out[k]['cities']), 'cities')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
