-- ============================================================================
-- 20260902000020_public_preview.sql
--
-- A public, deliberately partial view of the engine, for the landing page.
--
-- THE PROBLEM
--
-- The landing page is anonymous, and `signals` is gated on authenticated
-- AND approved (migration 18). So the marketing site cannot read a single
-- row -- correctly. The three tempting fixes are all worse than the
-- problem: opening a public SELECT policy on `signals` would undo the
-- approval gate; shipping the service-role key to the frontend would hand
-- the browser unrestricted access to every table; and rendering invented
-- example signals would put fabricated market data on the public site.
--
-- So: two narrow, read-only, security-definer functions that expose
-- exactly what a visitor may see, and nothing else.
--
-- WHAT IS DELIBERATELY WITHHELD
--
--   * entry_price -- the tradeable detail.
--   * direction, WHENEVER A REAL SIGNAL EXISTS. `has_signal` says one is
--     there; CALL or PUT is what people are paying for. NO_TRADE is
--     returned in full, because "most cycles end in no trade" is the
--     platform's actual thesis and hiding it would misrepresent the
--     product in the flattering direction.
--   * reasons and warnings -- the analysis itself.
--
-- What is exposed is the shape of the decision: which asset, whether a
-- signal exists, the quality score against its bar, both side scores, the
-- regime, and when the engine last looked. Enough to show that something
-- real is running; not enough to trade on.
-- ============================================================================

create or replace function public_signal_preview()
returns table (
  symbol            text,
  display_name      text,
  has_signal        boolean,
  direction         text,
  grade             text,
  technical_score   smallint,
  call_score        smallint,
  put_score         smallint,
  market_regime     text,
  session           text,
  expiry_seconds    integer,
  generated_at      timestamptz,
  last_evaluated_at timestamptz
)
language sql
security definer
set search_path = public
stable
as $$
  select
    a.symbol,
    a.display_name,
    s.direction in ('CALL', 'PUT') as has_signal,
    -- Masked when it has value, shown when it is the product's own point.
    case when s.direction in ('CALL', 'PUT') then null else s.direction end as direction,
    s.grade,
    s.technical_score,
    s.call_score,
    s.put_score,
    s.market_regime,
    s.session,
    s.expiry_seconds,
    s.generated_at,
    s.last_evaluated_at
  from assets a
  join lateral (
    select *
    from signals x
    where x.asset_id = a.id
      and x.status <> 'REJECTED'
    order by coalesce(x.last_evaluated_at, x.generated_at) desc
    limit 1
  ) s on true
  where a.is_active
  order by a.symbol;
$$;

revoke all on function public_signal_preview() from public;
grant execute on function public_signal_preview() to anon, authenticated;

comment on function public_signal_preview() is
  'Landing-page preview: the latest non-rejected decision per active asset, with entry price and (for live signals) direction withheld. Safe for anon.';

-- ---------------------------------------------------------------------------
-- Aggregate performance. Counts only -- no per-signal detail leaves here.
--
-- Returns raw wins/losses rather than a percentage on purpose. The caller
-- computes the rate AND the interval from the same numbers, so a rate can
-- never be displayed without the sample size that qualifies it. A bare
-- "85% accuracy" is exactly the claim this function is shaped to prevent.
-- ---------------------------------------------------------------------------
create or replace function public_performance()
returns table (
  wins            bigint,
  losses          bigint,
  draws           bigint,
  signals_total   bigint,
  first_resolved  timestamptz
)
language sql
security definer
set search_path = public
stable
as $$
  select
    count(*) filter (where result = 'WON'),
    count(*) filter (where result = 'LOST'),
    count(*) filter (where result = 'DRAW'),
    count(*) filter (where direction in ('CALL', 'PUT') and status <> 'REJECTED'),
    min(resolved_at)
  from signals;
$$;

revoke all on function public_performance() from public;
grant execute on function public_performance() to anon, authenticated;

comment on function public_performance() is
  'Landing-page performance counts. Returns wins/losses, never a percentage, so the caller cannot show a rate without its sample size.';
