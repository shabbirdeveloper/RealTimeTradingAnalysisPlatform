-- ============================================================================
-- 20260829000005_signals_tables.sql
--
-- signals, signal_results (spec section 37, and the resolution rule in
-- section 49). `signals` holds current state for fast dashboard reads;
-- `signal_results` is an append-only resolution log — a signal is resolved
-- once in the normal case, but this keeps room for a correction to be
-- recorded without destroying the original entry.
-- ============================================================================

create table signals (
  id                     uuid primary key default gen_random_uuid(),
  asset_id               uuid not null references assets (id),
  direction              direction_type not null,
  generated_at           timestamptz not null default now(),
  entry_price            numeric,
  expiry_minutes         smallint check (expiry_minutes in (15, 30, 60)),
  expiry_at              timestamptz,
  technical_score        numeric not null,        -- 0-100, always computed
  raw_probability        numeric,                  -- pre-calibration, null if MODEL_NOT_READY
  calibrated_confidence  numeric,                  -- 0-100, null if MODEL_NOT_READY
  grade                  signal_grade not null,
  market_regime          market_regime_type not null,
  model_version_id       uuid references model_versions (id),
  status                 signal_status not null default 'CANDIDATE',
  result                 text check (result in ('WON', 'LOST', 'DRAW')),
  closing_price          numeric,
  resolved_at            timestamptz,
  session                text,                     -- 'ASIAN' | 'LONDON' | 'NEW_YORK' | 'LONDON_NY_OVERLAP'
  reasons                text[] not null default '{}',
  warnings               text[] not null default '{}',
  timeframes_snapshot    jsonb,                    -- H4/H1/M15/M5 bias + strength at generation time, for the signal detail page
  created_at             timestamptz not null default now()
);

create index idx_signals_asset_generated on signals (asset_id, generated_at desc);
create index idx_signals_status on signals (status);
create index idx_signals_grade on signals (grade);
create index idx_signals_model_version on signals (model_version_id);

-- Admin view needs both accepted AND rejected opportunities (spec section
-- 30) — REJECTED rows live in this same table rather than a separate one,
-- distinguished by `status`, so nothing about a rejected setup is ever
-- silently discarded.
comment on column signals.status is 'CANDIDATE/REJECTED are pre-execution outcomes; ACTIVE/EXPIRED/WON/LOST/DRAW/INVALIDATED track a live or resolved signal.';

-- Immutable resolution record. `quote_source` matters for audit: spec
-- section 49 requires storing exactly which feed's quote decided the
-- WIN/LOSS/DRAW outcome.
create table signal_results (
  id             uuid primary key default gen_random_uuid(),
  signal_id      uuid not null references signals (id) on delete cascade,
  resolved_at    timestamptz not null default now(),
  result         text not null check (result in ('WON', 'LOST', 'DRAW')),
  entry_price    numeric not null,
  closing_price  numeric not null,
  quote_source   text not null,
  notes          text,
  created_at     timestamptz not null default now()
);

create index idx_signal_results_signal on signal_results (signal_id);
