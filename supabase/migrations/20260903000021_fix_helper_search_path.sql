-- ============================================================================
-- 20260903000021_fix_helper_search_path.sql
--
-- is_approved() and is_admin() both pin search_path to `public` and then
-- call auth.uid(), which lives in the `auth` schema. Under a pinned
-- search_path that call cannot be resolved by name.
--
-- The symptom is the reason this took so long to find: an RLS helper that
-- fails or returns NULL does not raise anything a user sees. The policy
-- simply matches no rows, so the site reports an empty database while the
-- collector -- which writes with the service role and never evaluates
-- these policies -- stays perfectly healthy. Every diagnostic that used
-- the service role said OK.
--
-- The pinned search_path is not the mistake; it is a deliberate hardening
-- so a caller cannot shadow `profiles` with their own object. The mistake
-- is depending on name resolution at all inside a SECURITY DEFINER
-- function. So both fixes are applied together:
--
--   * auth.uid() is written schema-qualified, which is what actually makes
--     it resolve, and keeps working if anyone tightens search_path further.
--   * `auth` is added to search_path as well, matching admin_list_users(),
--     which was written correctly and has worked all along -- the
--     discrepancy between them is what this migration removes.
--
-- Both functions are replaced in place; no policy changes, no data changes.
-- ============================================================================

create or replace function is_admin()
returns boolean
language sql
security definer
set search_path = public, auth
stable
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

create or replace function is_approved()
returns boolean
language sql
security definer
set search_path = public, auth
stable
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid()
      -- Admins are approved by definition: an admin whose own row somehow
      -- reads PENDING must still be able to open the console that fixes it.
      and (access_status = 'APPROVED' or role = 'admin')
  );
$$;

comment on function is_approved() is
  'True when the caller is APPROVED, or is an admin. SECURITY DEFINER with search_path = public, auth so auth.uid() resolves — see migration 21.';
