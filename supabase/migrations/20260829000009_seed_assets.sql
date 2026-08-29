-- ============================================================================
-- 20260829000009_seed_assets.sql
--
-- Seed data for the 3 configured instruments (spec section 4). The assets
-- table comment in 20260829000002 always said this would be "seeded by
-- the seed script, not by the application" -- this is that script. Written
-- as its own migration (rather than supabase/seed.sql) so it runs the same
-- way as the other 8: paste into the SQL editor and execute, in order.
--
-- `pip_decimal` is the decimal place that constitutes one pip for that
-- instrument -- 4 for EUR/USD and GBP/USD (standard forex convention), 2
-- for XAU/USD (gold is typically quoted to cents). Adjust here if your
-- broker/provider uses a different convention; nothing downstream hardcodes
-- these values, they're read from this table.
--
-- `config` is left as an empty object -- the spec-section-4 per-asset
-- parameters (DXY weighting, session emphasis, etc.) belong to the feature
-- engine, which is Phase 3, not this migration. Safe to add keys here later
-- without a schema change, since the column is jsonb.
--
-- ON CONFLICT DO NOTHING makes this safe to re-run.
-- ============================================================================

insert into assets (symbol, display_name, short_name, pip_decimal, config, is_active)
values
  ('XAUUSD', 'XAU/USD', 'Gold', 2, '{}'::jsonb, true),
  ('EURUSD', 'EUR/USD', 'Euro', 4, '{}'::jsonb, true),
  ('GBPUSD', 'GBP/USD', 'Cable', 4, '{}'::jsonb, true)
on conflict (symbol) do nothing;
