-- ============================================================================
-- 20260830000013_admin_list_users.sql
--
-- /admin/users needs each account's email, but emails live in `auth.users`,
-- which the browser's anon key cannot read (by design). Rather than ship the
-- service-role key to the frontend -- which would hand the browser
-- unrestricted access to every table -- this exposes exactly one hardened,
-- read-only function.
--
-- Security notes, because SECURITY DEFINER runs with the definer's rights
-- and is the classic place to get this wrong:
--   * `search_path` is pinned so a caller cannot shadow `profiles` or
--     `auth.users` with their own objects and redirect the query.
--   * The admin check is INSIDE the function body and raises. Relying on the
--     caller to check first would mean any authenticated user could invoke
--     it directly over PostgREST and read every email.
--   * EXECUTE is granted only to `authenticated` (never `anon`), and the
--     function is read-only -- it exposes no way to change a role or a plan.
-- ============================================================================

create or replace function admin_list_users()
returns table (
  id            uuid,
  email         text,
  display_name  text,
  role          user_role,
  plan          text,
  subscription_status subscription_status,
  created_at    timestamptz
)
language plpgsql
security definer
set search_path = public, auth
stable
as $$
begin
  -- Schema-qualified even though search_path is pinned: two independent
  -- barriers, and the qualification survives anyone later relaxing the
  -- search_path line.
  if not public.is_admin() then
    raise exception 'admin_list_users: caller is not an admin'
      using errcode = '42501';  -- insufficient_privilege
  end if;

  return query
    select
      p.id,
      u.email::text,
      p.display_name,
      p.role,
      coalesce(s.plan, 'free') as plan,
      s.status as subscription_status,
      p.created_at
    from public.profiles p
    left join auth.users u on u.id = p.id
    left join public.subscriptions s on s.user_id = p.id
    order by p.created_at desc;
end;
$$;

revoke all on function admin_list_users() from public;
revoke all on function admin_list_users() from anon;
grant execute on function admin_list_users() to authenticated;

comment on function admin_list_users() is
  'Admin-only read of the user list including auth emails. Raises 42501 for non-admins. See migration 20260830000013 for the SECURITY DEFINER hardening rationale.';
