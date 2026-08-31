-- ============================================================================
-- 20260830000015_strategy_configs.sql
--
-- The tuning apparatus: per-asset, per-expiry strategy configuration, and a
-- version stamp on every signal.
--
-- WHY
-- ---
-- The engine ran on one module-level constant (78) applied identically to all
-- fifteen asset/expiry combinations. Spec section 4 says explicitly not to
-- assume the same parameters work across assets, and section 11 wants
-- independent behaviour per expiry -- but "raise the bar on XAUUSD 15m" was a
-- code edit and a redeploy, not a decision.
--
-- The subtler problem was attribution. Signals from an old rule set and a new
-- one landed in this table indistinguishable from one another, so any
-- before/after comparison silently pooled them -- which is how a tuning change
-- gets credited with an improvement it did not cause. `strategy_version` makes
-- that impossible.
--
-- BEHAVIOURAL IMPACT OF THIS MIGRATION: none. The table starts empty and an
-- absent row means "use the shipped default", which reproduces exactly what
-- the engine does today. Introducing the apparatus must not move a single
-- signal, or the history accumulating right now is worthless as a baseline.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- strategy_configs
-- ---------------------------------------------------------------------------
-- Deliberately NOT seeded with default rows. A seeded default is a second copy
-- of a value that already lives in app/features/strategy.py, and the two drift
-- the moment either changes. An absent row is unambiguous and needs no
-- migration to stay in sync.
create table if not exists strategy_configs (
  id                   uuid primary key default gen_random_uuid(),
  asset_id             uuid not null references assets (id) on delete cascade,
  expiry_minutes       smallint not null check (expiry_minutes in (15, 30, 60)),

  -- Minimum technical score for this (asset, expiry) to be tradeable.
  min_technical_score  smallint not null default 78
                         check (min_technical_score between 0 and 100),

  -- Regimes and sessions this expiry may trade in. These can only NARROW
  -- behaviour: the engine's hard stand-down on HIGH_VOLATILITY and UNSTABLE
  -- sits above this layer and is not expressible here, so listing those
  -- regimes does not buy a signal. A configuration mistake should cost
  -- signals, never produce reckless ones.
  allowed_regimes      text[] not null default array[
                         'TRENDING_UP','TRENDING_DOWN','RANGING',
                         'HIGH_VOLATILITY','LOW_VOLATILITY','NEWS_MODE','UNSTABLE'
                       ],
  allowed_sessions     text[] not null default array[
                         'ASIAN','LONDON','NEW_YORK','LONDON_NY_OVERLAP'
                       ],

  enabled              boolean not null default true,

  -- Human-readable name for this generation of the rules, e.g. 'v2-tighter-gold'.
  -- The stored signal's strategy_version is this label plus a fingerprint of the
  -- effective config, so forgetting to bump the label costs clarity but never
  -- correctness -- the fingerprint changes regardless.
  label                text not null default 'v1',
  notes                text,

  updated_by           uuid references auth.users (id),
  updated_at           timestamptz not null default now(),
  created_at           timestamptz not null default now(),

  unique (asset_id, expiry_minutes)
);

-- Membership is validated in the application too (app/features/strategy.py
-- raises on an unknown value). Enforced here as well because a bad array
-- written directly through SQL would otherwise produce a config the engine
-- silently ignores while stamping a version that claims it was applied.
alter table strategy_configs
  add constraint strategy_configs_regimes_known check (
    allowed_regimes <@ array[
      'TRENDING_UP','TRENDING_DOWN','RANGING',
      'HIGH_VOLATILITY','LOW_VOLATILITY','NEWS_MODE','UNSTABLE'
    ]::text[]
  ),
  add constraint strategy_configs_sessions_known check (
    allowed_sessions <@ array['ASIAN','LONDON','NEW_YORK','LONDON_NY_OVERLAP']::text[]
  ),
  -- An empty array would mean "trade in no regime at all", which is what
  -- `enabled = false` is for. Allowing both spellings of the same intent
  -- invites a config that reads as active but can never fire.
  add constraint strategy_configs_regimes_nonempty check (array_length(allowed_regimes, 1) > 0),
  add constraint strategy_configs_sessions_nonempty check (array_length(allowed_sessions, 1) > 0);

comment on table strategy_configs is
  'Per (asset, expiry) tuning. Absent row = shipped default. Config can only narrow engine behaviour, never widen it past a safety stop.';

-- ---------------------------------------------------------------------------
-- RLS: admin-only, read and write
-- ---------------------------------------------------------------------------
-- These rows decide which trades users are shown. A non-admin must not be able
-- to read them (they reveal the filter) and certainly not write them. The
-- collector reaches this table with the service-role key, which bypasses RLS.
alter table strategy_configs enable row level security;

create policy "strategy_configs_select_admin"
  on strategy_configs for select
  using (is_admin());

create policy "strategy_configs_insert_admin"
  on strategy_configs for insert
  with check (is_admin());

create policy "strategy_configs_update_admin"
  on strategy_configs for update
  using (is_admin())
  with check (is_admin());

create policy "strategy_configs_delete_admin"
  on strategy_configs for delete
  using (is_admin());

-- ---------------------------------------------------------------------------
-- strategy_version on signals
-- ---------------------------------------------------------------------------
alter table signals
  add column if not exists strategy_version text;

comment on column signals.strategy_version is
  'Label plus config fingerprint of the rule set that produced this row, e.g. v1:a3f9c2. Group by this before comparing accuracy across time -- rows with different values were produced by different rules and must never be pooled.';

-- Rows written before this column existed came from the pre-config engine.
-- Backfilling them with the current default would be a lie: it would claim a
-- fingerprint that was never computed for them, and they would then pool with
-- genuinely-stamped rows. 'v0-unversioned' says what is actually true -- these
-- predate versioning -- and keeps them separable forever.
update signals set strategy_version = 'v0-unversioned' where strategy_version is null;

-- Every accuracy breakdown that compares rule sets groups on this, usually
-- alongside asset and expiry.
create index if not exists idx_signals_strategy_version
  on signals (strategy_version, asset_id, expiry_minutes);
