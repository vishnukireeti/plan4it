-- Learnership waitlist: only a signed-in student whose email is confirmed can join, and only with that email.
--
-- Why: the page now asks for a confirmed email, but a browser check alone can be bypassed. This makes the database
-- enforce it. Signing in already requires a confirmed email; the function below checks it again against auth.users.
-- Rows already on the list are not touched. Safe to run more than once.

create or replace function public.waitlist_email_is_confirmed(p_email text)
returns boolean
language sql
stable
security definer
set search_path = public, auth
as $$
  select exists (
    select 1 from auth.users u
    where u.id = auth.uid()
      and u.email_confirmed_at is not null
      and lower(u.email) = lower(p_email)
  );
$$;

revoke all on function public.waitlist_email_is_confirmed(text) from public, anon;
grant execute on function public.waitlist_email_is_confirmed(text) to authenticated;

drop policy if exists "anyone can join waitlist" on public.learnership_waitlist;
drop policy if exists "confirmed users can join waitlist" on public.learnership_waitlist;
create policy "confirmed users can join waitlist" on public.learnership_waitlist
  for insert to authenticated
  with check (user_id = (select auth.uid()) and public.waitlist_email_is_confirmed(email));

revoke insert on public.learnership_waitlist from anon;
