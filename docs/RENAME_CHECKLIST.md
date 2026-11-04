# Renaming this app

**Done, 2026-11-02:** renamed from "MARG-AI" to **"Plan4it"**. Steps 1–3
below are complete. **Done, 2026-11-04:** custom domain `plan4it.co`
registered and connected via Netlify DNS (step 2) — `index.html`,
`robots.txt`, and `sitemap.xml` all updated to it. Still outstanding:
- The cosmetic account display names in step 4 — update whenever
  convenient, never urgent. Of these, the **GitHub repo name** is the
  one actually worth doing soon (it's the most visible one left showing
  "MargAI"/"margai") — it has to be done by the repo owner directly on
  GitHub.com (Settings → rename), since repo renames can't be done
  through this tool's GitHub access. Old links auto-redirect once renamed,
  so it's safe to do anytime, no urgency.

This file is kept as a reusable checklist in case the app is ever renamed
again — the steps below are generic, not specific to this rename.
(The same checklist also lives as a short comment in `index.html`, right
above the GA4 script tag.)

1. **Text in `index.html`** (~30 spots): find-and-replace the old name →
   the new name, and the standalone nav-logo chip text (search for the
   old name wrapped in `>...<`). A plain string replace is safe: every
   occurrence is used as a proper noun, no grammar breaks to worry
   about.

2. **`margai.netlify.app`** (appears in `index.html`, `robots.txt`, and
   `sitemap.xml`): replace with the new domain once one is registered
   and connected. Fine to leave as-is until then.

3. **Regenerate the icons/social-preview image** — these bake the name
   into actual pixels, so a text find-replace can't touch them:
   ```sh
   python3 scripts/generate-brand-assets.py
   ```
   (Edit the `APP_NAME` / `APP_INITIAL` / `APP_TAGLINE` constants at the
   top of that script first.)

4. **Accounts that do *not* need recreating** — only a cosmetic
   display-name field each, update whenever convenient, never urgent:
   - **GA4** — Admin → Property settings (property name only; the
     Measurement ID itself never changes). Also update the Data
     Stream's website URL once the custom domain is live.
   - **Sentry** — Project Settings → General → Name.
   - **Supabase** — Project name in the dashboard (the project
     ref/URL stays the same, unaffected).
   - **GitHub repo** — Settings → rename (old links auto-redirect).
   - **Netlify site** — Project configuration → General → Site
     details → change site name. This *does* change the
     `*.netlify.app` subdomain, so only do this once, deliberately —
     and it stops mattering entirely once a custom domain is
     attached, since that becomes the primary URL. (Tried renaming to
     `plan4it` on 2026-11-04 — already taken by someone else's Netlify
     site; would need a variant like `plan4it-app`. Low priority since
     `plan4it.co` is now the real URL anyone sees.)
