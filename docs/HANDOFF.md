# Plan4it — Handoff / Continuity Brief

Paste this entire document as your first message in a new chat. It gives
Claude everything needed to continue exactly where this session left off —
no other setup needed.

---

## What this project is

**Plan4it** (renamed from "MARG-AI" 2026-11-02, see `docs/RENAME_CHECKLIST.md`)
is a free, single-file HTML career-guidance web app for Class 10–12 students
in India (and their families). It helps them figure out careers, exams,
colleges and scholarships that fit their situation.

- **Repo:** `vishnukireeti/MargAI` on GitHub (repo itself not yet renamed on
  GitHub.com — cosmetic only, see `docs/RENAME_CHECKLIST.md`)
- **Deployed at:** https://plan4it.co via Netlify (custom domain connected
  2026-11-04; also reachable at https://margai.netlify.app, the underlying
  Netlify subdomain)
- **Backend:** Supabase project ref `mpfzxbvpndextzgiqpmo` (Mumbai / `ap-south-1` region)
- **Architecture:** One self-contained `index.html` (HTML+CSS+JS, no build
  step to run it) + a precompiled Tailwind stylesheet + a Supabase backend
  for real user accounts and cloud-synced saved data.
- **Full architecture/roadmap writeup:** https://claude.ai/artifact/VPkZzTQu62zZqVuJzcd9Sk

## ⚠️ Hard constraint — read this first

**Do NOT run `git push` or trigger any Netlify deploy without a fresh,
explicit "yes, deploy/push this" from me in that new conversation.**

This is non-negotiable and here's why: this repo's Netlify site **is**
connected for git-triggered auto-deploy — this was confirmed directly
against Netlify's API earlier in development, reversing an earlier wrong
assumption. **Every `git push` to `main` immediately deploys to the live
production site.** There was already one accidental production deploy
this way (commit `fbb4284`) when an unresolved assumption was wrongly
treated as settled. All work since has stayed local-only (committed to
git, never pushed) specifically to respect this.

So: commit freely, but stop before any `git push` and ask first.

Also note: `README.md`'s "Deploying" section and
`docs/PRE_LAUNCH_CHECKLIST.md`'s "Still unresolved from earlier" section
both still contain **stale text claiming push ≠ deploy**. This is wrong
(see above) and should be corrected — not yet done, not yet asked for.

## Current deploy state (as of this handoff)

**Live on margai.netlify.app** (everything through commit `fbb4284`):
SEO infra (robots.txt, sitemap.xml, canonical/OG tags, JSON-LD), precompiled
Tailwind stylesheet (replacing the old CDN JIT compiler), `supabase_schema.sql`,
CI pipeline files, README/docs.

**Committed locally but NOT pushed / NOT live** (in order):
1. Removal of "free"/"stays on your device"/"saved in this browser" wording
   from various UI strings, SEO meta, auth modal, Privacy Policy (now
   accurately describes both signed-in-synced and signed-out-local-only
   behavior).
2. Full real-accounts rewrite: replaced the old fake localStorage-only
   "accounts" with real Supabase Auth (email/password + Google OAuth code
   path), plus a `user_data` table (one JSONB row per user) with RLS, plus
   a hybrid local/cloud data layer (see "Auth & data architecture" below).
3. `docs/PRE_LAUNCH_CHECKLIST.md` updates reflecting the above.
4. Most recent commit (`61f9c37`): removed the "Your progress" section
   (three-card strip: quiz match / next deadline / saved+checklist count)
   from the home page per explicit request — it's gone from the HTML, its
   `renderHomeProgress()` function and both call sites were deleted, and
   `assets/tailwind.css` was rebuilt to match (CI checks + Playwright smoke
   test all passed before commit).

## Auth & data architecture (built this session, not yet pushed)

- **Why:** the old "accounts" were 100% fake — localStorage only, no real
  backend, so a user's saved data never actually followed them across
  devices/browsers despite looking like a login.
- **Decision made:** build real accounts now (Supabase side), defer SMS/
  phone login (India's TRAI DLT registration is a multi-day/week regulatory
  process), Google Cloud Console OAuth setup deferred to the user to do
  separately ("I will do the google cloud later").
- **Supabase side (done):**
  - `user_data` table: `user_id` (PK, FK to `auth.users`, cascade delete),
    `data jsonb`, `updated_at` (auto-updated via trigger). One row per user,
    holds everything that used to be localStorage-only: saved careers/
    exams/colleges, checklist, profile.
  - RLS: owner-only (`auth.uid() = user_id`) for select/insert/update/delete,
    `to authenticated` only — **no anonymous/public access at all** (unlike
    the pre-existing `usage_events` table, which is anon-insert-only).
  - Schema is version-controlled in `supabase_schema.sql` — keep that file
    and the live dashboard in sync on any future schema change.
- **Client side (done):**
  - Real `sb.auth.signUp` / `signInWithPassword` / `resetPasswordForEmail`
    / `signInWithOAuth({provider:'google'})` / `signOut`.
  - `currentAuthSession` kept in sync via `onAuthStateChange`.
  - Hybrid storage: existing `getSavedCareers()/setSavedCareers()` etc.
    (~5 pairs, ~20 call sites) kept their exact synchronous signatures —
    each now checks `authGetSession()` and reads/writes either an in-memory
    `cloudData` object (debounced 800ms upsert to `user_data`) or
    localStorage, depending on sign-in state. No call-site changes needed.
  - First-ever real sign-in migrates whatever's in localStorage into the
    new cloud row.
  - Account deletion only deletes the `user_data` row today (not the auth
    account itself — that needs a service-role call, flagged as a future
    Supabase Edge Function in both the code comment and
    `docs/PRE_LAUNCH_CHECKLIST.md`).
- **Not yet tested for real:** the sandbox this was built in couldn't reach
  `*.supabase.co` or the CDN serving the Supabase JS library at all (both
  outside its network allowlist), so this was verified against a mocked
  Supabase client (validation, state transitions, migration, error
  handling) — **never a real network round-trip.** First real signup/login
  test is a pre-launch checklist item.

## What I (the user) still need to do myself

- Google Cloud Console: create OAuth Client ID, paste Client ID + Secret
  into Supabase dashboard → Authentication → Providers → Google. No code
  change needed once this is done — `authGoogleStart()` already calls the
  real thing.
- Provide GA4 Measurement ID and Sentry DSN when ready (both wired in but
  inert until real IDs replace placeholders — see
  `docs/PRE_LAUNCH_CHECKLIST.md`).
- Register/connect a custom domain eventually (not started).
- Pick the real app name eventually (currently "MARG-AI" placeholder —
  checklist at `docs/RENAME_CHECKLIST.md`).

## Most recent task (in progress — this is where to pick up)

I asked: *"can you look at the main page and tell me if there could be
better wordings used with good punchlines and also while your doing that
can you remove 'your progress' on the main page its not needed."*

- **"Remove Your progress"** — ✅ fully done, verified, committed locally
  (commit `61f9c37`). Nothing left to do here.
- **Wording/punchline review** — ✅ review was given, but no changes have
  been applied yet. I have NOT yet told Claude which suggestions (if any)
  to apply. The suggestions given were:
  1. Eyebrow text ("Built for Class 10–12 students and their families,
     across India") — flagged as flat/brochure-like, optional rewrite
     offered but not required.
  2. H1 ("Not sure what to do next? Let's map it out.") — flagged as
     already good, no change recommended.
  3. Subhead ("Answer a few quick questions and see the careers, exams and
     colleges that fit you. No sign-up needed.") — flagged two issues: (a)
     "No sign-up needed" is now stale/undersells the new real-accounts
     feature, (b) the rest reads generic. Alternate phrasing offered but
     not applied.
  4. CTA buttons — fine as-is, no change needed.
  5. Stat line ("Covers X careers... Your saved items stay on your device,
     or sync to your account if you sign in.") — flagged as tonally
     mismatched (marketing stat + fine print in one sentence), suggested
     trimming the storage clause since it's already correctly covered in
     the FAQ section.
  6. "Your path, step by step" and "Good to know" sections — fine as-is,
     no changes recommended.
  - **The single change flagged as most worth making:** drop "No sign-up
    needed" from the subhead, and lighten/shorten the stat-line's storage
    clause.
  - **Nothing has been edited in `index.html` for this part yet** — I was
    waiting to hear back on which of these (if any) to apply.

### What to do first in the new chat

Ask me (or just proceed with the recommended single change — my call,
whichever reading you take) whether to apply:
- Dropping "No sign-up needed" from the home-page subhead, and/or
- Trimming the storage clause in the stat line,
- or any other suggestion from the list above,
then make the edit(s) in `/home/claude/margai/index.html`, run the full CI
verification suite (see below), and commit locally (**do not push**).

## Standing instructions / working style for this project

- **Never push/deploy without a fresh explicit go-ahead** (see constraint
  above — this is the most important one).
- Work through tasks one at a time, verify, commit locally, and wait for
  the next instruction rather than batching ahead.
- Before any content/wording change, verify factual claims against the
  actual code/data rather than assuming (this already caught one wrong
  premise earlier in the project — "saved data is already in Supabase" —
  before any copy was changed based on it).
- After any `index.html` change, always run the full verification suite
  before committing:
  ```sh
  cd /home/claude/margai
  python3 scripts/ci/check_html_structure.py
  python3 scripts/ci/check_js_syntax.py
  python3 scripts/ci/check_json.py
  node scripts/build-tailwind.mjs   # then check: git diff --stat -- assets/tailwind.css
  python3 scripts/ci/smoke_test.py
  ```
  (`smoke_test.py` serves the directory over `python3 -m http.server` and
  drives it with Playwright — needs a real HTTP origin, not `file://`,
  because of `cssRules` access restrictions.)
- Commit messages follow the established style: clear "why", then:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  ```
  (session line varies per session, fine to omit or regenerate)

## Known stale/incorrect doc text (not yet fixed, not yet requested)

- `README.md` "Deploying" section claims push ≠ deploy. **Wrong** — see
  constraint above. Needs correcting whenever I ask for it.
- `docs/PRE_LAUNCH_CHECKLIST.md` "Still unresolved from earlier" section
  has the same stale claim about Netlify auto-deploy being unconfirmed —
  it's actually now confirmed (push = deploy). Needs correcting whenever
  I ask for it.

## Gap-list items still open (not urgent, no action needed unless I ask)

- Custom domain (needs me to register one).
- "Decision room" feature (shared student+parent planning space) — never
  built, Phase 2 idea, schema placeholder comment only in
  `supabase_schema.sql`.

---

*End of handoff. Everything above reflects the actual current state of
the code and git history as of this writing — nothing here is aspirational
or planned-but-not-done unless explicitly marked as such.*
