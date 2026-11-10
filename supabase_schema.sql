-- Plan4it — Supabase schema
--
-- This file is the version-controlled source of truth for the Supabase project
-- referenced in index.html (SUPABASE_URL / SUPABASE_ANON_KEY near the top of <head>).
-- It was written by reading the live schema directly from the project (ap-south-1 /
-- Mumbai, project ref mpfzxbvpndextzgiqpmo) — it matches what's actually deployed,
-- not an aspirational design. Keep this file and the live database in sync: any
-- schema change made through the Supabase dashboard or `apply_migration` should be
-- reflected back here in the same commit.
--
-- Safe to re-run: every statement is idempotent (IF NOT EXISTS / CREATE OR REPLACE).

-- ============================================================================
-- usage_events — anonymous, insert-only product analytics.
--
-- Logged from the client via trackEvent() (see index.html). Each row is tied only
-- to a random per-browser id (anon_id), never to a name, email or other identifying
-- detail — see the in-app Privacy Policy. There is deliberately no SELECT/UPDATE/
-- DELETE policy for the public/anon role: the client can only ever insert new rows,
-- never read, edit or remove existing ones. Only service-role access (dashboard,
-- SQL editor, or a future admin-only backend) can query this table.
-- ============================================================================

create table if not exists public.usage_events (
    id         uuid primary key default gen_random_uuid(),
    anon_id    text not null,
    event_name text not null,
    meta       jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_usage_events_created_at on public.usage_events using btree (created_at);
create index if not exists idx_usage_events_event_name on public.usage_events using btree (event_name);
create index if not exists idx_usage_events_anon_id on public.usage_events using btree (anon_id);

alter table public.usage_events enable row level security;

-- Anyone (including the anonymous/public client role) may INSERT a row, as long as
-- anon_id and event_name are both non-empty and no longer than 64 characters — this
-- bounds what a malicious client could stuff into the table, without needing any
-- server-side validation layer. No SELECT/UPDATE/DELETE policy exists for this role
-- by design, so the client genuinely cannot read back analytics data, even its own.
drop policy if exists "anyone can log an event" on public.usage_events;
create policy "anyone can log an event"
    on public.usage_events
    for insert
    to public
    with check (
        char_length(anon_id) >= 1 and char_length(anon_id) <= 64
        and char_length(event_name) >= 1 and char_length(event_name) <= 64
    );

-- Useful ad-hoc queries (run these in the Supabase SQL editor, not from the client —
-- there's no policy allowing the client to read this table):
--
--   -- events per day
--   select date_trunc('day', created_at) as day, count(*)
--   from usage_events group by 1 order by 1 desc;
--
--   -- most common events
--   select event_name, count(*) from usage_events group by 1 order by 2 desc;

-- ============================================================================
-- user_data — one row per signed-in user, holding everything that used to live
-- only in localStorage: saved careers/exams/colleges, checklist progress, and
-- profile (stage/location/budget). A single JSONB blob per user rather than
-- separate tables — simpler to build and migrate, at the cost of not being
-- able to query individual saved items from SQL. Revisit if that's ever needed.
--
-- Requires a signed-in user (auth.uid()) — there is no anonymous/guest access
-- to this table at all, unlike usage_events. A visitor who isn't signed in
-- keeps using localStorage exactly as before; this table only exists for
-- someone who has created a real account (see index.html's auth code).
-- ============================================================================

create table if not exists public.user_data (
    user_id    uuid primary key references auth.users(id) on delete cascade,
    data       jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

alter table public.user_data enable row level security;

-- A signed-in user may only ever read, write or delete their OWN row — never
-- another user's. No policy for the anon/public role exists at all: someone
-- who isn't signed in has no access to this table, full stop.
drop policy if exists "users can read own data" on public.user_data;
create policy "users can read own data"
    on public.user_data
    for select
    to authenticated
    using (auth.uid() = user_id);

drop policy if exists "users can insert own data" on public.user_data;
create policy "users can insert own data"
    on public.user_data
    for insert
    to authenticated
    with check (auth.uid() = user_id);

drop policy if exists "users can update own data" on public.user_data;
create policy "users can update own data"
    on public.user_data
    for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists "users can delete own data" on public.user_data;
create policy "users can delete own data"
    on public.user_data
    for delete
    to authenticated
    using (auth.uid() = user_id);

-- Keeps updated_at honest on every write, without relying on the client to set it.
create or replace function public.set_user_data_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_user_data_updated_at on public.user_data;
create trigger trg_user_data_updated_at
    before update on public.user_data
    for each row
    execute function public.set_user_data_updated_at();

-- NOTE: this table only holds app data, not the account itself. Deleting a
-- user's Supabase Auth account (not just this row) needs a service-role call
-- — the anon key the client uses can never do that — so a real "delete my
-- account" feature needs a server-side function (e.g. a Supabase Edge
-- Function) added later. Not built yet; flagging so it isn't assumed to work.

-- ============================================================================
-- Not yet built: the "decision room" feature referenced in index.html's Supabase
-- comment (a shared space for a student + parent to plan together) has no tables
-- here because it was never implemented — only commented as an intended future
-- use of this Supabase project. When/if that's built, its schema (likely a `rooms`
-- table + membership + RLS scoped to room participants, probably with Realtime
-- enabled) belongs in this file alongside usage_events, not as a separate file.
-- ============================================================================

-- Learnership waitlist (Plan4it Learnership Program, paid). Signed-in users add and read only their own rows.
create table if not exists public.learnership_waitlist (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  email text,
  track text not null check (char_length(track) <= 40),
  stage text not null check (char_length(stage) <= 40),
  duration text not null check (duration in ('1m','2m','3m','4m','5m','6m')),
  college text check (char_length(college) <= 120),
  note text check (char_length(note) <= 400),
  created_at timestamptz not null default now(),
  unique (user_id, track)
);
alter table public.learnership_waitlist enable row level security;
create policy "insert own waitlist row" on public.learnership_waitlist for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "read own waitlist rows" on public.learnership_waitlist for select to authenticated using ((select auth.uid()) = user_id);
