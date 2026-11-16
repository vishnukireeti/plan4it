-- Plan4it admin dashboard: one admin-only function that returns every statistic as JSON.
-- Run once in the Supabase SQL editor (or as a migration). Safe to re-run.
--
-- Security: the function is SECURITY DEFINER so it can read usage_events and auth.users,
-- but it first checks the signed-in user's verified email against the admin hash below
-- (SHA-256 of the lower-cased admin email, same value the app already uses). Anyone else,
-- including signed-out visitors, gets an error and no data. Execute is revoked from
-- anon/public and granted only to authenticated users.

create or replace function public.admin_dashboard()
returns jsonb
language plpgsql
security definer
set search_path = public, auth
as $fn$
declare
  v_email text := lower(trim(coalesce(auth.jwt() ->> 'email', '')));
  v_hash  text := '9961aa7282a77e47a4d55ee130265381e911da7cafb1f4b7f1c3385104871532';
  v_today date := (now() at time zone 'Asia/Kolkata')::date;
  v_out   jsonb;
begin
  if v_email = '' or encode(sha256(convert_to(v_email, 'UTF8')), 'hex') <> v_hash then
    raise exception 'not authorised' using errcode = '42501';
  end if;

  with
  ev as (
    select anon_id, event_name, meta, created_at,
           (created_at at time zone 'Asia/Kolkata')::date as d,
           extract(hour from created_at at time zone 'Asia/Kolkata')::int as h
    from usage_events
  ),
  days as (select generate_series(v_today - 29, v_today, interval '1 day')::date as d),
  daily as (
    select days.d,
           count(distinct ev.anon_id) as visitors,
           count(ev.anon_id) as events,
           count(distinct ev.anon_id) filter (where ev.event_name = 'quiz_completed') as quizzes,
           (select count(*) from auth.users u where (u.created_at at time zone 'Asia/Kolkata')::date = days.d) as signups
    from days left join ev on ev.d = days.d
    group by days.d order by days.d
  ),
  first_seen as (select anon_id, min(d) as first_d, count(distinct d) as active_days from ev group by anon_id),
  ud as (select user_id, data, updated_at from user_data),
  saved as (
    select 'careers' as kind, x as item from ud, jsonb_array_elements_text(case when jsonb_typeof(data -> 'savedCareers') = 'array' then data -> 'savedCareers' else '[]'::jsonb end) x
    union all
    select 'exams', x from ud, jsonb_array_elements_text(case when jsonb_typeof(data -> 'savedExams') = 'array' then data -> 'savedExams' else '[]'::jsonb end) x
    union all
    select 'colleges', x from ud, jsonb_array_elements_text(case when jsonb_typeof(data -> 'savedColleges') = 'array' then data -> 'savedColleges' else '[]'::jsonb end) x
  ),
  wiz_scalar as (
    select kv.key, kv.value from ud, jsonb_each_text(case when jsonb_typeof(data -> 'wizardAnswers') = 'object' then data -> 'wizardAnswers' else '{}'::jsonb end) kv
    where kv.key in ('stage', 'state', 'cls', 'help', 'clarity', 'constraint', 'degree', 'situation', 'mode', 'after') and kv.value <> ''
  ),
  wiz_array as (
    select k as key, x as value from ud, unnest(array['interests', 'values', 'workStyles']) k,
      jsonb_array_elements_text(case when jsonb_typeof(data -> 'wizardAnswers' -> k) = 'array' then data -> 'wizardAnswers' -> k else '[]'::jsonb end) x
  ),
  wiz_all as (select * from wiz_scalar union all select * from wiz_array),
  wiz_counts as (select key, value, count(*) n from wiz_all group by key, value),
  ev_counts as (select event_name as name, count(*) n, count(distinct anon_id) visitors from ev group by 1)
  select jsonb_build_object(
    'generated_at', now(),
    'totals', jsonb_build_object(
      'accounts', (select count(*) from auth.users),
      'accounts_7d', (select count(*) from auth.users where created_at > now() - interval '7 days'),
      'accounts_30d', (select count(*) from auth.users where created_at > now() - interval '30 days'),
      'accounts_today', (select count(*) from auth.users where (created_at at time zone 'Asia/Kolkata')::date = v_today),
      'signed_in_7d', (select count(*) from auth.users where last_sign_in_at > now() - interval '7 days'),
      'with_saved_data', (select count(*) from ud),
      'visitors', (select count(distinct anon_id) from ev),
      'visitors_today', (select count(distinct anon_id) from ev where d = v_today),
      'visitors_7d', (select count(distinct anon_id) from ev where created_at > now() - interval '7 days'),
      'visitors_30d', (select count(distinct anon_id) from ev where created_at > now() - interval '30 days'),
      'events', (select count(*) from ev),
      'events_today', (select count(*) from ev where d = v_today),
      'events_7d', (select count(*) from ev where created_at > now() - interval '7 days'),
      'returning_visitors', (select count(*) from first_seen where active_days > 1),
      'first_event', (select min(created_at) from ev)
    ),
    'daily', (select coalesce(jsonb_agg(jsonb_build_object('d', d, 'visitors', visitors, 'events', events, 'quizzes', quizzes, 'signups', signups) order by d), '[]') from daily),
    'new_vs_returning_7d', jsonb_build_object(
      'new', (select count(*) from first_seen where first_d > v_today - 7),
      'returning', (select count(*) from first_seen fs where fs.first_d <= v_today - 7 and exists (select 1 from ev where ev.anon_id = fs.anon_id and ev.d > v_today - 7))
    ),
    'hours', (select coalesce(jsonb_agg(jsonb_build_object('h', g, 'n', coalesce(c.n, 0)) order by g), '[]') from generate_series(0, 23) g left join (select h, count(*) n from ev group by h) c on c.h = g),
    'events_by_name', (select coalesce(jsonb_agg(jsonb_build_object('name', name, 'n', n, 'visitors', visitors) order by n desc), '[]') from ev_counts),
    'funnel', jsonb_build_object(
      'visited', (select count(distinct anon_id) from ev),
      'explored', (select count(distinct anon_id) from ev where event_name in ('view_explorer', 'view_careerDetail', 'view_exams', 'view_colleges', 'view_confusedMode')),
      'quiz', (select count(distinct anon_id) from ev where event_name = 'quiz_completed'),
      'saved', (select count(distinct anon_id) from ev where event_name = 'career_saved'),
      'dashboard', (select count(distinct anon_id) from ev where event_name = 'view_dashboard'),
      'report', (select count(distinct anon_id) from ev where event_name in ('report_hub_open', 'career_report_open', 'career_report_general', 'career_report_me', 'report_download', 'career_report_download')),
      'account', (select count(*) from auth.users)
    ),
    'saved_top', jsonb_build_object(
      'careers', (select coalesce(jsonb_agg(jsonb_build_object('item', item, 'n', n) order by n desc), '[]') from (select item, count(*) n from saved where kind = 'careers' group by item order by 2 desc limit 15) t),
      'exams', (select coalesce(jsonb_agg(jsonb_build_object('item', item, 'n', n) order by n desc), '[]') from (select item, count(*) n from saved where kind = 'exams' group by item order by 2 desc limit 10) t),
      'colleges', (select coalesce(jsonb_agg(jsonb_build_object('item', item, 'n', n) order by n desc), '[]') from (select item, count(*) n from saved where kind = 'colleges' group by item order by 2 desc limit 10) t),
      'totals', jsonb_build_object('careers', (select count(*) from saved where kind = 'careers'), 'exams', (select count(*) from saved where kind = 'exams'), 'colleges', (select count(*) from saved where kind = 'colleges'))
    ),
    'quiz_profile', (select coalesce(jsonb_object_agg(key, items), '{}') from (
      select key, jsonb_agg(jsonb_build_object('value', value, 'n', n) order by n desc) items from wiz_counts group by key) t),
    'quiz_takers', (select count(*) from ud where jsonb_typeof(data -> 'wizardAnswers') = 'object' and data -> 'wizardAnswers' <> '{}'::jsonb),
    'signup_methods', (select coalesce(jsonb_agg(jsonb_build_object('method', m, 'n', n) order by n desc), '[]') from (select coalesce(raw_app_meta_data ->> 'provider', 'email') m, count(*) n from auth.users group by 1) t),
    'recent_accounts', (select coalesce(jsonb_agg(r order by (r ->> 'joined') desc), '[]') from (
      select jsonb_build_object(
        'who', left(split_part(u.email, '@', 1), 2) || '***@' || split_part(u.email, '@', 2),
        'joined', u.created_at, 'last_seen', u.last_sign_in_at,
        'confirmed', u.email_confirmed_at is not null,
        'careers', coalesce(jsonb_array_length(case when jsonb_typeof(d.data -> 'savedCareers') = 'array' then d.data -> 'savedCareers' end), 0),
        'exams', coalesce(jsonb_array_length(case when jsonb_typeof(d.data -> 'savedExams') = 'array' then d.data -> 'savedExams' end), 0),
        'colleges', coalesce(jsonb_array_length(case when jsonb_typeof(d.data -> 'savedColleges') = 'array' then d.data -> 'savedColleges' end), 0),
        'stage', d.data -> 'wizardAnswers' ->> 'stage',
        'state', d.data -> 'wizardAnswers' ->> 'state'
      ) r
      from auth.users u left join user_data d on d.user_id = u.id order by u.created_at desc limit 15) t)
  ) into v_out
  from (select 1) _;

  return v_out;
end
$fn$;

revoke all on function public.admin_dashboard() from public, anon;
grant execute on function public.admin_dashboard() to authenticated;
