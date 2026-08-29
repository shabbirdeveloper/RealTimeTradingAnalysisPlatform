-- ============================================================================
-- 20260829000004_ml_tables.sql
--
-- models, model_versions, model_predictions (spec sections 11/12/31).
-- Each asset+expiry gets its own independent model (spec section 11):
-- XAUUSD 15m, XAUUSD 30m, ... GBPUSD 60m are separate `models` rows, not one
-- shared model with a parameter.
-- ============================================================================

create table models (
  id              uuid primary key default gen_random_uuid(),
  asset_id        uuid not null references assets (id) on delete cascade,
  expiry_minutes  smallint not null check (expiry_minutes in (15, 30, 60)),
  model_type      text not null,      -- 'xgboost' | 'lightgbm' | 'sklearn' | 'meta'
  name            text not null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index idx_models_asset_expiry on models (asset_id, expiry_minutes);

create trigger trg_models_updated_at
  before update on models
  for each row execute function set_updated_at();

-- A trained snapshot of a model. `status` moves TRAINING -> VALIDATING ->
-- READY -> ACTIVE (or FAILED/ARCHIVED) — nothing here auto-promotes to
-- ACTIVE just because training finished (spec section 31, explicit rule).
create table model_versions (
  id                     uuid primary key default gen_random_uuid(),
  model_id               uuid not null references models (id) on delete cascade,
  version                text not null,
  status                 model_status_type not null default 'TRAINING',
  training_period_start  date,
  training_period_end    date,
  test_accuracy          numeric,          -- 0-100, overall backtest accuracy
  aplusplus_accuracy     numeric,          -- 0-100, accuracy restricted to A++ signals
  signal_coverage        numeric,          -- 0-100, % of opportunities that produced a signal
  artifact_uri           text,             -- where the serialized model file lives
  trained_at             timestamptz,
  activated_at           timestamptz,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now(),
  unique (model_id, version)
);

create index idx_model_versions_model_status on model_versions (model_id, status);

create trigger trg_model_versions_updated_at
  before update on model_versions
  for each row execute function set_updated_at();

-- Only one ACTIVE version per model at a time — enforced with a partial
-- unique index rather than application logic alone.
create unique index idx_model_versions_one_active
  on model_versions (model_id)
  where status = 'ACTIVE';

-- Raw model output per candle, before the meta model's take/reject and
-- before calibration is folded into the final signal (spec section 12).
create table model_predictions (
  id                    bigint generated always as identity primary key,
  model_version_id      uuid not null references model_versions (id) on delete cascade,
  asset_id              uuid not null references assets (id) on delete cascade,
  candle_time           timestamptz not null,
  raw_probability       numeric,        -- pre-calibration model output, null if MODEL_NOT_READY
  calibrated_confidence numeric,        -- post-calibration 0-100, null if MODEL_NOT_READY
  created_at            timestamptz not null default now(),
  unique (model_version_id, candle_time)
);

create index idx_model_predictions_asset_time on model_predictions (asset_id, candle_time desc);
