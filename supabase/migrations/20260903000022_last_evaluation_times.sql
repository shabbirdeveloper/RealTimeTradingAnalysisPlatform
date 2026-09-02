-- ============================================================================
-- 20260903000022_last_evaluation_times.sql
--
-- The dashboard could not tell a dead engine from a rejected setup.
--
-- Signals with status REJECTED are hidden from non-admins by design (spec
-- section 30: rejected opportunities are an admin analysis view). But a
-- rejected opportunity is also the engine's CURRENT answer. When the
-- newest decision for an asset happens to be one, the user's newest
-- VISIBLE row is whatever came before it -- possibly hours old -- and the
-- card then stamps it "last checked 16h ago — engine may be stopped".
--
-- Which was false. The engine had evaluated that asset ten minutes
-- earlier. It just said no in a way the user is not allowed to read.
--
-- This exposes the one fact needed to tell those apart: WHEN each asset
-- was last evaluated, across every status. Deliberately nothing else --
-- no direction, no score, no grade, no reason. A timestamp cannot be
-- traded on, and it is the whole of what the staleness stamp needs.
-- ============================================================================

create or replace function latest_evaluation_times()
returns table (symbol text, last_evaluated_at timestamptz)
language sql
security definer
set search_path = public, auth
stable
as $$
  select a.symbol, max(coalesce(s.last_evaluated_at, s.generated_at))
  from assets a
  join signals s on s.asset_id = a.id
  where a.is_active
  group by a.symbol;
$$;

revoke all on function latest_evaluation_times() from public;
revoke all on function latest_evaluation_times() from anon;
grant execute on function latest_evaluation_times() to authenticated;

comment on function latest_evaluation_times() is
  'Per-asset time of the most recent decision of ANY status, so the UI can distinguish "the engine stopped" from "the current decision is a rejected setup you may not read". Exposes no decision content.';
