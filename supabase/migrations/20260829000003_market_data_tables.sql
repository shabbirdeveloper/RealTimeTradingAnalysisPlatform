-- ============================================================================
-- 20260829000003_market_data_tables.sql
--
-- candles, market_features. These are the highest-volume tables in the
-- schema (one row per candle per timeframe per asset, forever), so they use
-- a bigint identity primary key instead of uuid — smaller index, faster
-- range scans over time, and no reason to obscure a purely internal id.
-- ============================================================================

create table candles (
  id          bigint generated always as identity primary key,
  asset_id    uuid not null references assets (id) on delete cascade,
  timeframe   timeframe_type not null,
  open_time   timestamptz not null,
  open        numeric not null,
  high        numeric not null,
  low         numeric not null,
  close       numeric not null,
  volume      numeric,
  source      text not null,             -- data provider name, for audit/debugging
  created_at  timestamptz not null default now(),
  unique (asset_id, timeframe, open_time)
);

-- The dominant query pattern is "most recent N candles for asset+timeframe",
-- so the index is ordered newest-first.
create index idx_candles_asset_tf_time on candles (asset_id, timeframe, open_time desc);

-- Computed feature snapshot for one candle (spec section 6 — price action,
-- trend, momentum, volatility, market structure, session features). Stored
-- as jsonb rather than one column per feature: the feature set is large,
-- versioned, and expected to grow — a flexible document avoids a migration
-- every time the feature engine adds a column, while `feature_version`
-- keeps historical rows honest about which engine produced them.
create table market_features (
  id               bigint generated always as identity primary key,
  asset_id         uuid not null references assets (id) on delete cascade,
  timeframe        timeframe_type not null,
  candle_time      timestamptz not null,
  feature_version  text not null,
  features         jsonb not null,
  created_at       timestamptz not null default now(),
  unique (asset_id, timeframe, candle_time, feature_version)
);

create index idx_market_features_asset_tf_time on market_features (asset_id, timeframe, candle_time desc);
-- GIN index so the feature engine / analyzer can filter on individual
-- feature values (e.g. "atr_percentile > 80") without a full table scan.
create index idx_market_features_gin on market_features using gin (features);
