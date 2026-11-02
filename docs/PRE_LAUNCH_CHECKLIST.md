# Pre-launch checklist

Things that are intentionally left half-done right now, deferred to just
before the real launch, and need a human to finish them — none of these
can be done from code alone.

## Analytics & error monitoring (deferred on purpose)

Both are already wired into `index.html` but inert — loading is skipped
entirely until a real ID replaces the placeholder, so there's nothing to
undo if you do this late.

- [ ] **Google Analytics 4** — create a property at
      https://analytics.google.com (Admin → Create Property), add a Web
      data stream for the final domain, copy its Measurement ID (format
      `G-XXXXXXXXXX`), and paste it into `index.html` in place of
      `'PASTE_YOUR_GA4_MEASUREMENT_ID'` (search for that string — one
      spot, near the top of `<head>`).
- [ ] **Sentry** — create a project at https://sentry.io, copy its DSN,
      and paste it into `index.html` in place of
      `'PASTE_YOUR_SENTRY_DSN'` (search for that string — also near the
      top of `<head>`, right after the GA4 block).
- [ ] If GA4 goes live, consider a cookie-consent notice to match the
      app's privacy-first positioning (not legally required under
      India's DPDP Act the way GDPR requires it in the EU, but worth
      doing anyway since GA4 sets tracking cookies).

## Accounts (Google + email, SMS deferred)

Email/password accounts work end-to-end (signup, login, forgot password,
data synced to Supabase). Google needs one dashboard step; real network
testing against Supabase hasn't happened yet because of a sandbox
limitation, not a known bug — see below.

- [ ] **Turn on Google sign-in**: in Google Cloud Console, create an OAuth
      Client ID (see the step-by-step instructions given earlier in this
      project) and paste the Client ID + Secret into Supabase's dashboard
      → Authentication → Providers → Google. No code change needed —
      `authGoogleStart()` already calls the real thing and will start
      working the moment this is turned on.
- [ ] **Test the real signup/login flow once deployed.** This was built
      and verified against a mocked Supabase client (form validation,
      session handling, cloud save/load, local-to-cloud migration, error
      states all confirmed working), but the actual network round-trip to
      Supabase was never exercised — the sandbox this was built in
      couldn't reach `*.supabase.co` or the CDN that serves the Supabase
      JS library at all (both outside its network allowlist). Once this
      is live (or even running locally on your own machine), do one real
      signup and one real login to confirm the network path itself works
      end-to-end.
- [ ] Phone/SMS login was intentionally dropped for now — TRAI requires
      DLT registration before sending OTP SMS to Indian numbers, which is
      a multi-day/week regulatory process. Revisit after launch if phone
      login is still wanted (WhatsApp OTP is a DLT-free alternative worth
      considering instead of SMS).
- [ ] Full account deletion (not just saved-data deletion, which already
      works from the app) needs a service-role call Supabase doesn't
      expose to the client — currently handled as an email request per
      the Privacy Policy. A proper self-service "delete my account"
      button needs a Supabase Edge Function later.

## Domain

- [ ] Register and connect the custom domain (target: by end of
      November). Once live, update: the Data Stream URL in GA4, the
      canonical/OG URLs and sitemap in `index.html` /
      `sitemap.xml`, and `robots.txt`'s `Sitemap:` line.

## Still unresolved from earlier

- [ ] **Netlify auto-deploy**: this site has only ever deployed via a
      manual Netlify CLI/API trigger, never via GitHub's webhook —
      confirmed from Netlify's own deploy records (`deploy_source` was
      always `"api"`, never `"github"`). Whether that's intentional or
      a misconfigured "Continuous deployment" setting in the Netlify
      dashboard was never confirmed either way. Worth checking Site
      settings → Build & deploy → Continuous deployment if git-push-to-
      deploy is wanted instead of the current manual trigger.

## Already done (kept here for a record, not action items)

- [x] SEO infra (robots.txt, sitemap.xml, canonical/OG tags, JSON-LD)
- [x] Tailwind CDN JIT compiler replaced with a precompiled stylesheet
- [x] Basic CI (structural/syntax/JSON/browser checks on every push)
- [x] Stray unused Supabase project deleted
- [x] Real Supabase Auth (email/password + Google code path) replacing
      the old localStorage-only demo accounts; saved careers/colleges/
      exams/checklist/profile now sync to an account when signed in
- [x] Renamed "MARG-AI" → "Plan4it" (2026-11-02): all in-app text, README,
      docs, and favicons/OG image regenerated. Domain and a few cosmetic
      account display names intentionally left — see
      `docs/RENAME_CHECKLIST.md`.
