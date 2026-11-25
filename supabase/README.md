# Supabase source of truth

These files are the copy of what runs in the Supabase project. Edit here, then deploy.

- `functions/<name>/index.ts` are the edge functions. Deploy with the Supabase dashboard, the CLI
  (`supabase functions deploy <name>`) or the MCP tool. `razorpay-webhook` must stay "verify JWT: off"
  (Razorpay cannot send a login; it is protected by its signature). The other three stay "verify JWT: on".
- `migrations/` are one-off SQL changes. Run each once in the SQL editor of every project (production and staging).
- Secrets (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, RESEND_API_KEY) are set only in
  the Supabase dashboard under Edge Functions > Secrets. Never put them in this repo.
- Browser calls are only accepted from plan4it.co, www.plan4it.co and the staging site (see ALLOWED_ORIGINS in each function).
