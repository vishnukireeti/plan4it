# Security audit, 25 Nov 2026

Scope: the 19-point checklist (keys, env, admin, auth, access, forms, XSS, rate limits, API, CORS, headers,
debug, dependencies, exposed files, DB, passwords, git secrets, full audit). Not legal advice; not a penetration test.

## Fixed in this change
| # | Area | Finding | Fix |
|---|------|---------|-----|
| 15 | Exposed files | Netlify publishes the whole repo root, so /docs, /scripts, /supabase_*.sql, /package.json, /README.md were public | 404 rules in netlify.toml (force = true) + 404.html |
| 16 | DB access | anon/authenticated held UPDATE/DELETE/TRUNCATE on every table; only RLS stood in the way (TRUNCATE ignores RLS) | supabase/migrations/20261125_tighten_table_grants.sql (exact grants per table, no default grants for new tables) |
| 10 | CORS | Three edge functions answered browsers from any origin (`*`) | Only plan4it.co, www.plan4it.co and the staging site |
| 8 | Rate limiting | Nothing limited order creation per user | create-order: 15 orders per user per hour, else 429 |
| 9, 6 | API / input | waitlist-email passed the email into ILIKE, so `%` and `_` acted as wildcards; no length caps | Wildcards escaped, address format and length checked; payment ids length-capped; webhook body capped |
| 6, 7 | Forms / XSS | Admin waitlist CSV export let a visitor plant spreadsheet formulas (=HYPERLINK...) | Leading = + - @ is neutralised |

## Checked, no change needed
- 1/2 Keys and env: only the Supabase *publishable* key and the Razorpay key *id* reach the browser (both public by design). Secrets (Razorpay secret, webhook secret, Resend, service role) live only in Supabase's secret store. No secret found in the working tree or in any of 58 commits (the only match is a Razorpay *test key id*, which is not secret).
- 3/4/5 Admin and access: all four admin RPCs refuse any signed-in user except the admin email (hash check inside the function); anon cannot run them. RLS is on for all 6 tables with owner-only policies. Edge functions require a login except the Razorpay webhook, which requires Razorpay's signature.
- 7 XSS: user-supplied text (names, waitlist fields, search text) is escaped or set with textContent everywhere it is rendered; no eval, document.write, javascript: links, or unsafe target=_blank.
- 11 Headers: CSP, X-Frame-Options DENY, nosniff, HSTS, Referrer-Policy, Permissions-Policy, COOP already set.
- 12 Debug: no console.log/debug, no debug flags or test keys in the client.
- 13/14 Dependencies: the only npm package is tailwindcss (build tool, not shipped). supabase-js is version-pinned with an SRI hash.
- 17 Passwords: handled by Supabase Auth (bcrypt); the app never sees or stores a password or hash.

## Known limits (not fixed here)
- CSP still allows 'unsafe-inline' scripts because the app is one file with inline scripts and onclick handlers. Removing it means moving all of that into a separate script file with nonces/hashes: a big refactor.
- No package-lock.json (it cannot be generated offline), so tailwind's own dependencies are not pinned in CI.
- The admin check is a hash of the admin email inside the database functions. It is sound while that email account is protected: use a strong unique password and 2-step verification on it.

## Needs the owner (dashboards)
1. Supabase > Authentication > Providers/Policies: turn on leaked-password protection (the one remaining Supabase advisor warning; may need a paid plan) and set minimum password length to 8 or more.
2. Supabase > Authentication > URL configuration: Site URL https://plan4it.co, and redirect allow-list only plan4it.co (+ staging).
3. Turn on 2-step verification for: the admin email, Supabase, Netlify, GitHub, Razorpay, the domain registrar.
4. Run the migration and deploy the four functions on production (see supabase/README.md).
