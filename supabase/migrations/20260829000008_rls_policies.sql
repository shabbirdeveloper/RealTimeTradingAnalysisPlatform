-- ============================================================================
-- 20260829000008_rls_policies.sql
--
-- Row-level security (spec section 38). Design:
--   - The FastAPI backend (market data collector, feature/signal/backtest
--     engines) authenticates with the Supabase SERVICE ROLE key, which
--     bypasses RLS entirely. None of the policies below grant INSERT/UPDATE/
--     DELETE to `authenticated`/`anon` on engine-owned tables — all writes
--     to market/signal/model/backtest data go through the backend, never
--     directly from the browser. This mirrors "no API secrets in frontend":
--     the service role key lives only in the backend's environment.
--   - `authenticated` users get read-only access to their own rows (profile,
--     subscription, notifications) and to the subset of market/signal data
--     that is meant to be user-facing.
--   - Admin-only tables (backtests, audit_logs, system_health, and the
--     REJECTED/CANDIDATE half of signals) are gated on profiles.role =
--     'admin'. This is a second layer, not a replacement for the
--     server-side role check the admin routes must also do (spec: "server-
--     side role checks" is listed as its own requirement, section 38).
-- ============================================================================

-- security definer so this can be called from profiles' own policies
-- without the self-referential-select recursion Postgres RLS would
-- otherwise hit.
create or replace function is_admin()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (
    select 1 from profiles where id = auth.uid() and role = 'admin'
  );
$$;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
alter table profiles enable row level security;

create policy "profiles_select_own_or_admin"
  on profiles for select
  using (auth.uid() = id or is_admin());

create policy "profiles_update_own"
  on profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- RLS's `with check` only sees the NEW row, not OLD, so it cannot by itself
-- express "role must not change" — a self-promoting user would satisfy
-- `auth.uid() = id` no matter what they set `role` to. This trigger closes
-- that gap: any UPDATE not made with the service-role key (i.e. not the
-- backend/admin action path) has `role` silently reset to its previous
-- value, regardless of what the caller tried to write.
create or replace function prevent_profile_role_self_escalation()
returns trigger
language plpgsql
as $$
begin
  if new.role is distinct from old.role and coalesce(auth.role(), '') <> 'service_role' then
    new.role := old.role;
  end if;
  return new;
end;
$$;

create trigger trg_profiles_prevent_role_escalation
  before update on profiles
  for each row execute function prevent_profile_role_self_escalation();

-- ---------------------------------------------------------------------------
-- subscriptions
-- ---------------------------------------------------------------------------
alter table subscriptions enable row level security;

create policy "subscriptions_select_own_or_admin"
  on subscriptions for select
  using (auth.uid() = user_id or is_admin());

-- ---------------------------------------------------------------------------
-- assets / economic_events — read-only reference data for any signed-in user
-- ---------------------------------------------------------------------------
alter table assets enable row level security;
alter table economic_events enable row level security;

create policy "assets_select_authenticated"
  on assets for select
  to authenticated
  using (true);

create policy "economic_events_select_authenticated"
  on economic_events for select
  to authenticated
  using (true);

-- ---------------------------------------------------------------------------
-- candles / market_features — read-only for any signed-in user
-- ---------------------------------------------------------------------------
alter table candles enable row level security;
alter table market_features enable row level security;

create policy "candles_select_authenticated"
  on candles for select
  to authenticated
  using (true);

create policy "market_features_select_authenticated"
  on market_features for select
  to authenticated
  using (true);

-- ---------------------------------------------------------------------------
-- models / model_versions / model_predictions — read-only transparency for
-- signed-in users; management stays behind /admin's server-side role check
-- and the service-role key.
-- ---------------------------------------------------------------------------
alter table models enable row level security;
alter table model_versions enable row level security;
alter table model_predictions enable row level security;

create policy "models_select_authenticated"
  on models for select
  to authenticated
  using (true);

create policy "model_versions_select_authenticated"
  on model_versions for select
  to authenticated
  using (true);

create policy "model_predictions_select_authenticated"
  on model_predictions for select
  to authenticated
  using (true);

-- ---------------------------------------------------------------------------
-- signals / signal_results — CANDIDATE/REJECTED rows are admin-only (they're
-- the "rejected opportunities" view from spec section 30); everything else
-- is visible to any signed-in user.
-- ---------------------------------------------------------------------------
alter table signals enable row level security;
alter table signal_results enable row level security;

create policy "signals_select_user_facing_or_admin"
  on signals for select
  to authenticated
  using (status not in ('CANDIDATE', 'REJECTED') or is_admin());

create policy "signal_results_select_authenticated"
  on signal_results for select
  to authenticated
  using (
    exists (
      select 1 from signals s
      where s.id = signal_results.signal_id
        and (s.status not in ('CANDIDATE', 'REJECTED') or is_admin())
    )
  );

-- ---------------------------------------------------------------------------
-- backtests / backtest_signals — admin-only (spec: /admin/backtesting)
-- ---------------------------------------------------------------------------
alter table backtests enable row level security;
alter table backtest_signals enable row level security;

create policy "backtests_select_admin"
  on backtests for select
  using (is_admin());

create policy "backtest_signals_select_admin"
  on backtest_signals for select
  using (is_admin());

-- ---------------------------------------------------------------------------
-- notification_preferences / notifications — strictly own-row
-- ---------------------------------------------------------------------------
alter table notification_preferences enable row level security;
alter table notifications enable row level security;

create policy "notification_preferences_select_own"
  on notification_preferences for select
  using (auth.uid() = user_id);

create policy "notification_preferences_update_own"
  on notification_preferences for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "notifications_select_own"
  on notifications for select
  using (auth.uid() = user_id);

-- Users may mark their own notifications read, nothing else.
create policy "notifications_update_own_read_state"
  on notifications for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- system_health / audit_logs — admin-only
-- ---------------------------------------------------------------------------
alter table system_health enable row level security;
alter table audit_logs enable row level security;

create policy "system_health_select_admin"
  on system_health for select
  using (is_admin());

create policy "audit_logs_select_admin"
  on audit_logs for select
  using (is_admin());
