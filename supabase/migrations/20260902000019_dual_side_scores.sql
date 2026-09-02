-- ============================================================================
-- 20260902000019_dual_side_scores.sql
--
-- CALL and PUT are now scored independently (spec section 21), so both
-- numbers and their gap are stored on every signal.
--
-- Why store all three rather than derive the gap: `score_difference` is
-- what the separation gate actually reads, and a stored decision has to be
-- explicable years later without re-deriving anything. It is a generated
-- column so it can never disagree with the two it comes from.
--
-- Why the scores are NOT complements, recorded here because it is the
-- thing most likely to be "corrected" by someone later: call + put < 100
-- whenever a timeframe's voters abstained. That gap means "no evidence",
-- which is a different state from "evidence balanced". A constraint of
-- call + put = 100 would be wrong, and would manufacture conviction out of
-- silence.
--
-- Nullable with no default: rows written before this migration were
-- produced by an engine that never computed two sides, and a backfilled 0
-- would be indistinguishable from a genuine zero score. NULL reads as
-- "this predates dual scoring", which is the truth.
-- ============================================================================

alter table signals
  add column call_score smallint check (call_score between 0 and 100),
  add column put_score  smallint check (put_score  between 0 and 100),
  add column score_difference smallint
    generated always as (abs(coalesce(call_score, 0) - coalesce(put_score, 0))) stored;

comment on column signals.call_score is
  'Independent 0-100 evidence score for CALL. NOT the complement of put_score: both are low when voters abstained. NULL on rows predating dual scoring.';
comment on column signals.put_score is
  'Independent 0-100 evidence score for PUT. See call_score.';
comment on column signals.score_difference is
  'Generated. The separation gate reads this: a small gap means the market leans rather than commits.';

-- Analysis of near-ties is the point of the column, so make that query fast.
create index idx_signals_score_difference on signals (score_difference)
  where call_score is not null;
