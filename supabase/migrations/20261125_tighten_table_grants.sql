-- Least-privilege table grants for the two browser roles (anon = signed-out visitor, authenticated = signed in).
--
-- Why: Supabase grants every right on new tables to both roles and leaves row-level security (RLS) as the only
-- gate. RLS is on and correct for every table, but TRUNCATE is not covered by RLS at all, and "defence in depth"
-- says a signed-out visitor should not even hold UPDATE/DELETE on a table. This keeps only what index.html uses:
--
--   saved_reports        signed in: read / add / refresh / delete own copies
--   user_data            signed in: read / add / update / delete own data
--   usage_events         anyone: add an anonymous usage event (write-only)
--   report_log           signed in: add a row (write-only; the admin reads it through admin_report_flags())
--   purchases            signed in: read own purchases (rows are written only by the edge functions, with the service role)
--   learnership_waitlist signed in (confirmed email): join and read own rows -- see 20261126_waitlist_confirmed_email_only.sql
--
-- The service role (edge functions) and the postgres role are unaffected. Safe to run more than once.

revoke all on all tables in schema public from anon, authenticated;

grant select, insert, update, delete on public.saved_reports to authenticated;
grant select, insert, update, delete on public.user_data     to authenticated;
grant insert on public.usage_events                          to anon, authenticated;
grant insert on public.report_log                            to authenticated;
grant select on public.purchases                             to authenticated;
grant insert on public.learnership_waitlist                  to authenticated;
grant select on public.learnership_waitlist                  to authenticated;

-- A table created later must be opted in on purpose, not exposed by default.
alter default privileges in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
