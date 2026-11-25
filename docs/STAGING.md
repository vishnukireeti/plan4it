# Staging: test first, then go live

| | Live | Staging |
|---|---|---|
| Address | https://plan4it.co | https://staging--plan4it-app.netlify.app |
| Git branch | `main` | `staging` |
| Supabase project | mpfzxbvpndextzgiqpmo | verezawywdnflezvxchd (plan4it.co-staging) |
| Razorpay keys | live | TEST (secrets set in the staging project only) |
| Users / data | real | test only, safe to delete |

The app picks its backend from the address it is opened on (see `IS_LIVE_SITE` in index.html): only plan4it.co and
www.plan4it.co use the live project. Everything else (staging, Netlify previews, localhost) uses staging, shows an
amber STAGING pill, and is set to noindex. So the same code runs on both and nothing is edited when you go live.

## Day to day
1. Work on the `staging` branch and push it. Netlify publishes it at the staging address only.
2. Test there. Razorpay test card: 4111 1111 1111 1111, any future expiry, any CVV, any OTP.
3. Happy? Merge `staging` into `main` and push. That is the live deploy.

## Changes that are not just site files
- **SQL changes** (supabase/migrations): run on the staging project first, test, then run the same file on live.
- **Edge functions** (supabase/functions): deploy to staging first, test, then deploy the same file to live.
- Secrets are set separately in each Supabase project (Edge Functions > Secrets). Never put them in the repo.

## Test checklist before going live
Sign up with a test email, take the quiz, save a career, join the waitlist, buy the Rs 99 report with the test card
and confirm the report unlocks, then reload and confirm it is still unlocked.
