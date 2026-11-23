#!/usr/bin/env python3
"""Fails if the static SEO pages (/careers/, /exams/, /degrees/, sitemap.xml) are out of
date with the data in index.html and data/*.json.

It re-runs scripts/build-seo-pages.mjs with the same build date as the committed
sitemap (so the check only fails when the data changed, not because a day passed),
then asks git whether anything in those folders changed.
Fix a failure with:  node scripts/build-seo-pages.mjs   and commit the result.
"""
import os
import re
import subprocess
import sys

root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
os.chdir(root)
m = re.search(r"<lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", open("sitemap.xml", encoding="utf-8").read())
if not m:
    print("sitemap.xml has no <lastmod>; run node scripts/build-seo-pages.mjs and commit.")
    sys.exit(1)
env = dict(os.environ, SEO_BUILD_DATE=m.group(1))
subprocess.run(["node", "scripts/build-seo-pages.mjs"], check=True, env=env)
paths = ["careers", "exams", "degrees", "sitemap.xml"]
changed = (subprocess.check_output(["git", "diff", "--name-status", "--", *paths], text=True)
           + subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "--", *paths], text=True)).strip()
if changed:
    print("SEO pages are out of date with the data:")
    print("\n".join(changed.splitlines()[:20]))
    print("\nRun 'node scripts/build-seo-pages.mjs' and commit the regenerated pages.")
    sys.exit(1)
print("SEO pages are in sync with the data.")
