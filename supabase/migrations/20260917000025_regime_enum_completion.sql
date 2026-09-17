-- ============================================================================
-- 20260917000025_regime_enum_completion.sql
--
-- THE BUG
--
-- The engine classifies into nine regimes. This enum held seven, and four
-- of the engine's did not exist in it:
--
--     BREAKOUT   PULLBACK   CHOPPY   UNKNOWN
--
-- Every decision classified into one of those failed to insert:
--
--     DERIV_V75: signal insert failed:
--       invalid input value for enum market_regime_type: "CHOPPY"
--
-- The collector logged a WARNING and carried on, so nothing looked broken.
-- The engine kept scoring, the log kept printing decisions, and the rows
-- simply never arrived. DERIV_V75 had been evaluating every minute for days
-- and showed nothing at all on the dashboard.
--
-- WHY IT IS WORSE THAN A MISSING ROW
--
-- CHOPPY and UNKNOWN are exactly the two regimes in which no strategy is
-- permitted to fire (app/otc/regime.py: NO_TRADE_REGIMES). So the decisions
-- being dropped were not a random sample -- they were disproportionately
-- REJECTIONS. Spec section 30 calls storing rejected opportunities
-- "extremely important", precisely so the filters can later be asked
-- whether they helped or hurt, and a whole class of them was being
-- discarded silently.
--
-- Anything computed from stored signals -- the dashboard's accuracy, the
-- rejection breakdown -- was therefore computed over a biased subset.
-- The backtest is NOT affected: it replays stored candles through the same
-- evaluate(), and never reads the signals table.
--
-- WHAT THIS DOES
--
-- Adds the four missing values. Nothing is renamed, reordered or removed,
-- and no existing row changes: `add value if not exists` is additive, and
-- an enum's existing members keep their positions.
--
-- Spec section 7 named seven regimes. Phase 16 deliberately went beyond
-- them -- TRENDING alone covered both a clean advance and a vertical
-- spike, which call for different strategies, so routing by regime needed
-- finer states. The enum was never updated to match.
-- ============================================================================

alter type market_regime_type add value if not exists 'BREAKOUT';
alter type market_regime_type add value if not exists 'PULLBACK';
alter type market_regime_type add value if not exists 'CHOPPY';
alter type market_regime_type add value if not exists 'UNKNOWN';

comment on type market_regime_type is
  'Market regime (spec section 7, extended by Phase 16). Must contain every value app/otc/regime.py can return -- a missing member does not fail loudly, it makes the insert fail and the decision disappear. See tests/test_regime_enum.py.';
