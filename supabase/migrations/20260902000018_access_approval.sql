-- ============================================================================
-- 20260902000018_access_approval.sql
--
-- Signup no longer grants access. A new account lands in PENDING and sees
-- nothing but a waiting page until an admin approves it.
--
-- Why in the database rather than only in the app: the app's gate is a
-- redirect, and a redirect protects pages, not data. A pending account
-- still holds a valid session, so without RLS it could read signals
-- straight from PostgREST with the anon key and never touch the UI. The
-- redirect is for the person; these policies are for the account.
--
-- Two lockout hazards, both handled here rather than left as folklore:
--
--   1. Everyone who signed up BEFORE this migration is grandfathered to
--      APPROVED. They were already inside; a gate added later must not
--      evict them -- and the first casualty would be the owner running
--      this file.
--   2. `is_approved()` treats admins as approved unconditionally, so an
--      admin cannot be locked out of the console that does the approving,
--      and `admin_set_access()` refuses to change your own status.
--
-- If this database has no admin yet, every future signup would queue with
-- nobody able to release it, so the migration raises a NOTICE saying so.
-- ============================================================================

create type access_status as enum ('PENDING', 'APPROVED', 'REJECTED');

alter table profiles
  add column access_status access_status not null default 'PENDING',
  add column access_decided_at timestamptz,
  add column access_decided_by uuid references profiles (id) on delete set null,
  add column access_note text;

comment on column profiles.access_status is
  'PENDING until an admin approves. REJECTED also serves as revoked -- an admin can move an account back to PENDING or APPROVED at any time.';

-- Grandfather every account that already exists. See hazard 1 above.
-- Unconditional on purpose: everyone in this table predates the gate, so
-- everyone in it was already inside.
update profiles set access_status = 'APPROVED', access_decided_at = now();

create index idx_profiles_access_status on profiles (access_status)
  where access_status = 'PENDING';

do $$
begin
  if not exists (select 1 from profiles where role = 'admin') then
    raise notice
      'No admin account exists. New signups will queue in PENDING with nobody able to approve them. Promote one first: update profiles set role = ''admin'' where id = (select id from auth.users where email = ''you@example.com'');';
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- is_approved(): the predicate every user-facing policy now carries.
-- ---------------------------------------------------------------------------
create or replace function is_approved()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from profiles
    where id = auth.uid()
      -- Admins are approved by definition. Without this an admin whose own
      -- row somehow reads PENDING could not open the console that fixes it.
      and (access_status = 'APPROVED' or role = 'admin')
  );
$$;

revoke all on function is_approved() from public;
revoke all on function is_approved() from anon;
grant execute on function is_approved() to authenticated;

-- ---------------------------------------------------------------------------
-- Re-gate the user-facing reads.
--
-- profiles and notification_preferences are deliberately NOT gated: a
-- pending user must still be able to read their own row, or the waiting
-- page cannot tell them what they are waiting for.
-- ---------------------------------------------------------------------------
drop policy if exists "signals_select_user_facing_or_admin" on signals;
create policy "signals_select_user_facing_or_admin"
  on signals for select
  to authenticated
  using (
    (status not in ('CANDIDATE', 'REJECTED') and is_approved())
    or is_admin()
  );

drop policy if exists "candles_select_authenticated" on candles;
create policy "candles_select_authenticated"
  on candles for select
  to authenticated
  using (is_approved());

drop policy if exists "market_features_select_authenticated" on market_features;
create policy "market_features_select_authenticated"
  on market_features for select
  to authenticated
  using (is_approved());

drop policy if exists "economic_events_select_authenticated" on economic_events;
create policy "economic_events_select_authenticated"
  on economic_events for select
  to authenticated
  using (is_approved());

-- ---------------------------------------------------------------------------
-- admin_list_users(): now reports access status too.
--
-- Dropped and recreated rather than replaced: CREATE OR REPLACE cannot
-- change a function's OUT columns.
-- ---------------------------------------------------------------------------
drop function if exists admin_list_users();

create function admin_list_users()
returns table (
  id                  uuid,
  email               text,
  display_name        text,
  role                user_role,
  plan                text,
  subscription_status subscription_status,
  access_status       access_status,
  access_decided_at   timestamptz,
  access_note         text,
  created_at          timestamptz
)
language plpgsql
security definer
set search_path = public, auth
stable
as $$
begin
  if not public.is_admin() then
    raise exception 'admin_list_users: caller is not an admin'
      using errcode = '42501';
  end if;

  return query
    select
      p.id,
      u.email::text,
      p.display_name,
      p.role,
      coalesce(s.plan, 'free') as plan,
      s.status as subscription_status,
      p.access_status,
      p.access_decided_at,
      p.access_note,
      p.created_at
    from public.profiles p
    left join auth.users u on u.id = p.id
    left join public.subscriptions s on s.user_id = p.id
    -- Pending first: this list exists to be acted on, and the accounts
    -- waiting on a decision are the only ones that need one.
    order by (p.access_status = 'PENDING') desc, p.created_at desc;
end;
$$;

revoke all on function admin_list_users() from public;
revoke all on function admin_list_users() from anon;
grant execute on function admin_list_users() to authenticated;

-- ---------------------------------------------------------------------------
-- admin_set_access(): the only way to change an account's access.
--
-- Deliberately cannot touch `role`. Approving a user and making one an
-- admin are different decisions with different blast radii, and a single
-- function that could do both would be one bug away from privilege
-- escalation.
-- ---------------------------------------------------------------------------
create or replace function admin_set_access(
  target_user uuid,
  new_status  access_status,
  note        text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin() then
    raise exception 'admin_set_access: caller is not an admin'
      using errcode = '42501';
  end if;

  -- Hazard 2: an admin revoking their own access would lock the console
  -- that is the only way back in.
  if target_user = auth.uid() then
    raise exception 'admin_set_access: cannot change your own access status'
      using errcode = '42501';
  end if;

  if not exists (select 1 from public.profiles where id = target_user) then
    raise exception 'admin_set_access: no such user' using errcode = '22023';
  end if;

  update public.profiles
     set access_status     = new_status,
         access_decided_at = now(),
         access_decided_by = auth.uid(),
         access_note       = note
   where id = target_user;

  -- Access decisions are exactly the kind of act an audit trail is for.
  insert into audit_logs (action, target_table, target_id, actor_user_id, metadata)
  values (
    'ACCESS_' || new_status::text,
    'profiles',
    target_user::text,
    auth.uid(),
    jsonb_build_object('note', note)
  );
end;
$$;

revoke all on function admin_set_access(uuid, access_status, text) from public;
revoke all on function admin_set_access(uuid, access_status, text) from anon;
grant execute on function admin_set_access(uuid, access_status, text) to authenticated;

comment on function admin_set_access(uuid, access_status, text) is
  'Admin-only. Sets a user''s access_status and writes an audit_logs row. Cannot change roles, and refuses to act on the caller''s own account.';
