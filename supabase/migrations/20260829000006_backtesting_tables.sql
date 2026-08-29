-- ============================================================================
-- 20260829000006_backtesting_tables.sql
--
-- backtests, backtest_signals (spec sections 13, 14, 32, 33). No look-ahead
-- bias is a code-level guarantee the backtester service must honor — the
-- schema just records inputs and outputs; it cannot enforce that on its own.
-- ============================================================================

create table backtests (
  id                              uuid primary key default gen_random_uuid(),
  requested_by                    uuid references profiles (id),
  asset_id                        uuid references assets (id),        -- null = all configured assets
  model_version_id                uuid references model_versions (id),
  expiry_minutes                  smallint check (expiry_minutes in (15, 30, 60)),
  start_date                      date not null,
  end_date                        date not null,
  min_confidence                  numeric,
  session_filter                  text,
  regime_filter                   market_regime_type,
  status                          backtest_status not null default 'PENDING',

  -- Result summary (spec section 13/32) — populated once status = COMPLETED.
  total_opportunities             integer,
  accepted_signals                integer,
  rejected_signals                integer,
  wins                            integer,
  losses                          integer,
  draws                           integer,
  win_rate                        numeric,
  accuracy                        numeric,
  signal_coverage                 numeric,
  max_win_streak                  integer,
  max_loss_streak                 integer,
  performance_by_pair             jsonb,
  performance_by_expiry           jsonb,
  performance_by_session          jsonb,
  performance_by_regime           jsonb,
  performance_by_confidence_bucket jsonb,

  error_message                   text,          -- populated if status = FAILED
  started_at                      timestamptz,
  completed_at                    timestamptz,
  created_at                      timestamptz not null default now()
);

create index idx_backtests_status on backtests (status);
create index idx_backtests_requested_by on backtests (requested_by);

comment on column backtests.start_date is 'Inclusive backtest window start. The backtester must only use data available as of each simulated point in time — no future candles/features in any calculation.';

-- Every opportunity the backtest evaluated, accepted or not — mirrors
-- signals' shape so "accepted vs rejected" and "performance by X" can be
-- computed straight off this table (spec section 13's full breakdown list).
create table backtest_signals (
  id                     bigint generated always as identity primary key,
  backtest_id            uuid not null references backtests (id) on delete cascade,
  asset_id                uuid not null references assets (id),
  direction              direction_type not null,
  generated_at           timestamptz not null,
  entry_price            numeric,
  expiry_minutes         smallint,
  technical_score        numeric not null,
  calibrated_confidence  numeric,
  grade                  signal_grade not null,
  market_regime          market_regime_type not null,
  session                text,
  accepted               boolean not null,        -- true = counted as an accepted signal, false = rejected opportunity
  result                 text check (result in ('WON', 'LOST', 'DRAW')),
  closing_price          numeric,
  created_at             timestamptz not null default now()
);

create index idx_backtest_signals_backtest on backtest_signals (backtest_id);
create index idx_backtest_signals_asset on backtest_signals (asset_id);
