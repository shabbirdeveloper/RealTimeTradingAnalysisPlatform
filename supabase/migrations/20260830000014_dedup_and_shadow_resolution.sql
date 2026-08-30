-- ============================================================================
-- 20260830000014_dedup_and_shadow_resolution.sql
--
-- Two changes, both aimed at making signal accuracy measurable rather than
-- assumed.
--
-- 1. DEDUPLICATION. The engine inserted a fresh row every poll cycle, so one
--    market setup persisting for an hour became six "independent" signals
--    resolved against nearly the same price. That does not merely bloat the
--    table -- it corrupts every accuracy figure downstream, because the
--    confidence intervals on the performance page assume independent trials.
--    Six correlated copies of one outcome make the sample look six times
--    larger than it is.
--
-- 2. SHADOW RESOLUTION. Rejected opportunities were stored but never
--    resolved, so the engine could never learn whether the setups it turned
--    down would have lost. That made the quality threshold unfalsifiable.
--    These columns record the counterfactual outcome of a rejected setup.
--
--    They are deliberately SEPARATE columns rather than reusing status/result:
--    every performance query filters on `status in ('WON','LOST','DRAW')`, so
--    keeping rejected rows at status='REJECTED' means counterfactual outcomes
--    can never leak into real reported performance by construction, not by
--    remembering to filter them out.
-- ============================================================================

alter table signals
  -- When this decision was last re-confirmed by a poll cycle. `generated_at`
  -- stays the moment the setup FIRST appeared, so "NO TRADE since 14:20"
  -- remains truthful while the row keeps getting re-evaluated.
  add column if not exists last_evaluated_at timestamptz,

  -- Counterfactual outcome for rejected opportunities. Null on accepted
  -- signals, which use status/result as before.
  add column if not exists shadow_result text
    check (shadow_result in ('WON', 'LOST', 'DRAW')),
  add column if not exists shadow_closing_price numeric,
  add column if not exists shadow_resolved_at timestamptz;

update signals set last_evaluated_at = generated_at where last_evaluated_at is null;

comment on column signals.shadow_result is
  'Counterfactual: how a REJECTED opportunity would have resolved. Never counted in real performance -- those queries filter on status, which stays REJECTED.';

-- ---------------------------------------------------------------------------
-- One open directional signal per asset, enforced by the database
-- ---------------------------------------------------------------------------
-- The application already avoids this, but application-level dedup fails
-- silently on a race or a restart mid-cycle. This makes a duplicate an error
-- rather than a quietly corrupted statistic.
--
-- Deduplicated first so the index can be created on existing data.
with ranked as (
  select id,
         row_number() over (
           partition by asset_id order by generated_at desc, created_at desc
         ) as rn
  from signals
  where status = 'ACTIVE' and direction in ('CALL', 'PUT')
)
update signals
set status = 'INVALIDATED'
where id in (select id from ranked where rn > 1);

create unique index if not exists idx_signals_one_active_per_asset
  on signals (asset_id)
  where status = 'ACTIVE' and direction in ('CALL', 'PUT');

-- ---------------------------------------------------------------------------
-- Indexes for the queries the app actually runs (audit FIN-08)
-- ---------------------------------------------------------------------------
-- Eight frontend queries sort globally with no asset filter. A composite
-- index led by asset_id cannot serve those, so they degraded to scan-and-sort.
create index if not exists idx_signals_generated_at on signals (generated_at desc);

create index if not exists idx_signals_resolved_at
  on signals (resolved_at desc)
  where status in ('WON', 'LOST', 'DRAW');

-- Drives the threshold curve: win rate by technical score, for rejected
-- setups that have a counterfactual outcome.
create index if not exists idx_signals_shadow
  on signals (technical_score)
  where shadow_result is not null;
