# Plan4it

> Renamed from "MARG-AI" to "Plan4it" on 2026-11-02. The text rename is
> done (app, README, docs); the domain (still `margai.netlify.app`) and a
> few cosmetic account names are intentionally left for later — see
> [`docs/RENAME_CHECKLIST.md`](docs/RENAME_CHECKLIST.md) for what's left.

Career-guidance web app for Class 10–12 students in India. Currently
free to use end-to-end — no monetization has been built yet, not a
permanent "always free" promise (see `docs/PRE_LAUNCH_CHECKLIST.md`
for the planned direction). Single self-contained `index.html`
(HTML + CSS + JS in one file, no build step required to run it)
backed by Supabase, deployed on Netlify.

**Live:** https://margai.netlify.app

## What's in this repo

| Path | What it is |
|---|---|
| `index.html` | The entire app — markup, styles, and logic in one file. |
| `assets/tailwind.css` | Precompiled Tailwind stylesheet (see "Styling" below). Generated, not hand-edited. |
| `assets/*.png` | Favicon / touch-icon / Open Graph image. |
| `scripts/build-tailwind.mjs` | Regenerates `assets/tailwind.css` from the classes actually used in `index.html`. |
| `scripts/generate-brand-assets.py` | Regenerates the icon/OG-image PNGs. Parameterized for a future rename. |
| `scripts/ci/*.py` | The checks run on every push (see "CI" below). |
| `data/*_more.json` | Supplementary careers/exams/colleges data, fetched lazily after first paint — see the comment above `loadMoreData()` in `index.html`. The *base* catalog (353 careers / 326 exams / 1033 colleges) is intentionally kept inline in `index.html` itself, not fetched, so the app still works on a bad connection. |
| `supabase_schema.sql` | Version-controlled source of truth for the live Supabase schema (project ref `mpfzxbvpndextzgiqpmo`, Mumbai). Keep this in sync with the dashboard. |
| `netlify.toml` | Security headers + Content-Security-Policy. Update this whenever a new third-party script/connection origin is added (GA4, Sentry, etc.). |
| `robots.txt`, `sitemap.xml` | SEO basics. Note: the app uses hash-based routing (`#explorer`, `#exams`, …), and Google does not index hash fragments as separate pages — the sitemap only lists the one real URL. |
| `.github/workflows/ci.yml` | Automated checks on every push/PR (see below). |

## Running it locally

No build step needed to just view it:

```sh
python3 -m http.server 8000
# open http://localhost:8000/index.html
```

## Styling (Tailwind)

This used to load `cdn.tailwindcss.com` — a JS engine that recompiled all
CSS in the visitor's browser on every page load. That's gone now. Classes
are precompiled ahead of time into `assets/tailwind.css`.

**If you add/remove/change any Tailwind utility class in `index.html`, you
must regenerate the stylesheet and commit the result:**

```sh
npm install
node scripts/build-tailwind.mjs
```

CI fails the build if `assets/tailwind.css` doesn't match what
`index.html` actually uses, so this isn't optional.

The brand color palette (10 shades) lives in `scripts/build-tailwind.mjs`,
not in `index.html` — change it there, then rerun the build.

## Deploying

**This is important and easy to get wrong: pushing to GitHub does NOT
deploy the site.** Despite being a GitHub-backed repo, this Netlify site
was never connected for git-triggered auto-deploys — every deploy so far
has been a manual trigger via the Netlify CLI/API. (Whether that's
intentional or a misconfigured Netlify dashboard setting was never fully
confirmed — worth checking Netlify's dashboard under Site settings → Build
& deploy → Continuous deployment if you want git-push-to-deploy instead.)

To actually ship a change to production, a deploy has to be triggered
separately after pushing.

## CI

`.github/workflows/ci.yml` runs on every push/PR to `main`:

- **HTML structure check** — parses `index.html` the way a browser does
  and asserts exactly one `<html>`/`<head>`/`<body>`, and that every
  `<meta>`/`<link>`/`<title>` actually lands inside `<head>`. This exists
  because of a real bug caught during development: a stray duplicate
  document wrapper silently pushed all head-only tags (canonical link,
  Open Graph tags, structured data) into `<body>` instead, with zero
  visible symptom short of inspecting the parsed DOM.
- **JS syntax check** — runs `node --check` against every inline
  `<script>` block.
- **JSON validity check** — validates `data/*.json`.
- **Tailwind drift check** — rebuilds `assets/tailwind.css` and fails if
  it doesn't match what's committed.
- **Browser smoke test** — a real headless-Chromium Playwright run:
  loads the page over HTTP, checks the stylesheet actually applied, the
  catalog data loaded, SEO tags are present, and there are no unexpected
  console errors.

This workflow doesn't block a deploy by itself (deploys are manual, see
above) — treat a green run as "safe to deploy," not as a gate that stops
you.

## Analytics & error monitoring

GA4 and Sentry are wired into `index.html` but inert until configured —
both are deliberately deferred to just before launch. See
[`docs/PRE_LAUNCH_CHECKLIST.md`](docs/PRE_LAUNCH_CHECKLIST.md).

## Architecture & launch plan

A fuller write-up (current state, phased roadmap, what launch-ready
means) lives here: https://claude.ai/artifact/VPkZzTQu62zZqVuJzcd9Sk
