"""
One poll cycle: fetch the latest M5 candles for an asset, store them,
derive M15/H1/H4 from stored history, store those, compute real technical
features + a real signal decision from stored history, store both, and
report health. Called by the scheduler on each tick; also callable
directly (a one-off script, a manual trigger, a test) without needing
APScheduler at all.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.aggregation import Candle as AggCandle
from app.aggregation import Timeframe as AggTimeframe
from app.aggregation import aggregate_candles
from app.features.signal_engine import build_signal
from app.storage.strategy_repository import load_strategy
from app.features.snapshot import compute_feature_dict
from app.market_data.base import MarketDataError, MarketDataProvider
from app.instruments import FeedDescriptor, FeedKind
from app.market_data.closed_bars import split_closed
from app.market_data.resilience import RetryPolicy, call_with_retry
from app.news.factory import build_calendar_provider
from app.schemas.candle import Asset, Candle, Timeframe
from app.storage import audit_repository as audit
from app.storage.candle_repository import fetch_recent_candles, upsert_candles
from app.storage.event_repository import fetch_events_near
from app.storage.feature_repository import upsert_features
from app.storage.health_repository import report_component_health
from app.storage.signal_repository import insert_signal

logger = logging.getLogger(__name__)

# M5 bars kept in memory for deriving H4 candles (48 M5 bars per H4
# bucket); fetched with extra headroom so a couple of closed H4 buckets
# are always derivable, not just the newest one.
_M5_LOOKBACK_FOR_H4 = 48 * 3

# History fetched per timeframe for the feature/signal engine. 250 covers
# a real EMA200 once that much real history exists; fewer real candles
# just means the feature engine honestly reports "insufficient data"
# until then -- see app/features/timeframe_bias.py.
_FEATURE_LOOKBACK = 250


def _to_agg_candle(c: Candle) -> AggCandle:
    return AggCandle(
        open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume
    )


def _from_agg_candle(c: AggCandle) -> Candle:
    return Candle(
        open_time=c.open_time, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume
    )


def _to_feature_dict(c: Candle) -> dict:
    return {
        "open": float(c.open),
        "high": float(c.high),
        "low": float(c.low),
        "close": float(c.close),
        "open_time": c.open_time,
    }


async def run_poll_cycle(
    asset: Asset,
    provider: MarketDataProvider,
    *,
    poll_outputsize: int,
    retry_policy: RetryPolicy | None = None,
) -> None:
    started = time.monotonic()
    component = f"market_data.{asset.value}"

    try:
        fresh_m5, retry_outcome = await call_with_retry(
            lambda: provider.fetch_latest_m5(asset, poll_outputsize),
            policy=retry_policy or RetryPolicy(),
            label=f"{provider.name} fetch {asset.value}",
        )
    except MarketDataError as exc:
        logger.warning("market data fetch failed for %s via %s: %s", asset.value, provider.name, exc)
        report_component_health(component, status="Warning", details={"provider": provider.name, "error": str(exc)})
        audit.record(
            audit.ACTION_MARKET_DATA_FAILED,
            target_table="candles",
            target_id=asset.value,
            metadata={"provider": provider.name, "error": str(exc)},
        )
        return

    if not fresh_m5:
        logger.warning("provider %s returned zero candles for %s", provider.name, asset.value)
        report_component_health(
            component, status="Warning", details={"provider": provider.name, "error": "empty response"}
        )
        return

    # Reject the still-forming bar (audit FIN-04). Storing a partial candle
    # corrupts every indicator computed from it AND makes the backtester
    # better-informed than live was, because by replay time that bar has its
    # final close. See app/market_data/closed_bars.py.
    now = datetime.now(timezone.utc)
    split = split_closed(fresh_m5, Timeframe.M5.value, now)

    if split.future:
        # Not a partial bar -- a bar that cannot exist. Something is wrong
        # with a clock or the timezone handling, and until it is explained
        # none of this asset's data can be trusted.
        logger.error(
            "%s returned %d candle(s) opening in the future for %s — clock or timezone fault",
            provider.name, len(split.future), asset.value,
        )
        audit.record(
            audit.ACTION_MARKET_DATA_FAILED,
            target_table="candles",
            target_id=asset.value,
            metadata={
                "provider": provider.name,
                "error": "candles with future open_time",
                "count": len(split.future),
                "newest_open_time": split.future[-1].open_time.isoformat(),
            },
        )

    if not split.closed:
        # Every bar was still forming. Nothing to store -- and nothing wrong
        # either, on a very small outputsize. Reported so it is visible if it
        # becomes the steady state.
        logger.warning(
            "provider %s returned no CLOSED candles for %s (%d still forming)",
            provider.name, asset.value, len(split.forming),
        )
        report_component_health(
            component,
            status="Warning",
            details={
                "provider": provider.name,
                "error": "no closed candles in response",
                "forming_bars_dropped": len(split.forming),
            },
        )
        return

    logger.info(
        "%s: %d closed M5 bars from %s (dropped %d forming), newest %s",
        asset.value, len(split.closed), provider.name, len(split.forming),
        split.closed[-1].open_time.strftime("%H:%M"),
    )
    upsert_candles(asset, Timeframe.M5, split.closed, source=provider.name)

    # Pull recent M5 history from storage (not just this poll's batch) so
    # H4 aggregation -- 48 M5 bars per bucket -- has enough to work with
    # even right after a restart.
    history = fetch_recent_candles(asset, Timeframe.M5, _M5_LOOKBACK_FOR_H4)
    # split.closed, never fresh_m5 -- the fallback must not smuggle back in
    # the forming bar that was just filtered out. It would end up inside a
    # derived M15/H1/H4 bucket, where it is far harder to notice.
    agg_source = [_to_agg_candle(c) for c in (history or split.closed)]

    for target, agg_target in (
        (Timeframe.M15, AggTimeframe.M15),
        (Timeframe.H1, AggTimeframe.H1),
        (Timeframe.H4, AggTimeframe.H4),
    ):
        derived = aggregate_candles(agg_source, AggTimeframe.M5, agg_target, now=now)
        if derived:
            upsert_candles(
                asset, target, [_from_agg_candle(c) for c in derived], source=f"{provider.name}+aggregated"
            )

    latency_ms = round((time.monotonic() - started) * 1000)
    report_component_health(
        component,
        status="Healthy",
        details={
            "provider": provider.name,
            # The newest CLOSED bar -- the one actually stored. Reporting the
            # provider's newest bar here would make the feed look fresher than
            # the data the engine is allowed to use.
            "last_candle_time": split.closed[-1].open_time.isoformat(),
            "latency_ms": latency_ms,
            # Answers empirically what the provider's docs don't state: does
            # this feed include the in-progress bar? A steady 1 per poll means
            # yes, and that the filter is earning its place.
            "forming_bars_dropped": len(split.forming),
            "future_bars_dropped": len(split.future),
            "retries": retry_outcome.retries,
            "rate_limited": retry_outcome.rate_limited,
            **({"recovered_from": retry_outcome.last_error} if retry_outcome.retries else {}),
        },
    )

    _run_analysis_cycle(asset, provider)


def _run_analysis_cycle(asset: Asset, provider: MarketDataProvider) -> None:
    """Real technical analysis + signal decision from real stored candle
    history (spec sections 6-12), with the news filter applied (section 8).
    Failures here are logged and swallowed -- a feature/signal computation
    problem should never take down candle collection, which is the more
    critical half of this poll cycle.

    `provider` is needed for provenance: the engine records which feed priced
    the candles behind every decision, and refuses instrument/feed pairs that
    do not match.
    """
    # Demo candles are deterministic placeholders, not prices. Aggregation,
    # storage and health reporting are all worth exercising against them --
    # signals are not, and a graded signal derived from them would be fiction
    # rendered as a real result (spec section 50). Skipped explicitly here so
    # it reads as an intended state, rather than surfacing as a provenance
    # exception on every cycle.
    if getattr(provider, "name", "") == "demo":
        logger.info(
            "%s: candles stored from the demo provider; signal generation skipped "
            "(demo data is not market data)", asset.value,
        )
        return

    try:
        candles_by_timeframe: dict[str, list[dict]] = {}
        for tf in (Timeframe.H4, Timeframe.H1, Timeframe.M15, Timeframe.M5):
            stored = fetch_recent_candles(asset, tf, _FEATURE_LOOKBACK)
            feature_candles = [_to_feature_dict(c) for c in stored]
            candles_by_timeframe[tf.value] = feature_candles
            if feature_candles:
                upsert_features(asset, tf, feature_candles[-1]["open_time"], compute_feature_dict(feature_candles))

        now = datetime.now(timezone.utc)

        # News protection. `calendar_available` tracks whether a real feed
        # is configured -- an empty event list from an unconfigured
        # provider must NOT be read as "nothing scheduled, all clear".
        calendar_provider = build_calendar_provider()
        calendar_available = calendar_provider.is_configured
        events = fetch_events_near(now) if calendar_available else []

        # Per-asset/expiry tuning (spec sections 4 and 11). An unreachable
        # config table falls back to the shipped defaults rather than halting
        # signal generation -- but that is failing OPEN if an admin had
        # tightened the rules, so it is stated on the decision rather than
        # swallowed. The version stamp keeps the data honest either way:
        # signals generated during the outage carry the defaults' fingerprint
        # and can never be pooled with the tightened config's results.
        loaded = load_strategy(asset)

        # Provenance stated explicitly. This loop only ever handles
        # public-market instruments (see the note on the Asset enum), so the
        # descriptor is PUBLIC_MARKET -- and the engine will refuse outright
        # if an OTC instrument ever reaches here, rather than pricing a
        # broker-generated series with vendor forex data.
        feed = FeedDescriptor(name=provider.name, kind=FeedKind.PUBLIC_MARKET)

        decision = build_signal(
            asset.value,
            candles_by_timeframe,
            now=now,
            strategy=loaded.strategy,
            feed=feed,
            economic_events=events,
            calendar_available=calendar_available,
        )
        if not loaded.loaded:
            decision.warnings.append(
                "Strategy configuration could not be read — running shipped defaults, "
                "which may be looser than the configured rules."
            )
        # The decision itself, on one line. This is the thing the operator is
        # actually waiting to see, and it was only ever written to the
        # database -- so the console gave no sign the engine was thinking.
        #
        # Which list to quote depends on the outcome. A NO_TRADE is explained
        # by what BLOCKED it (warnings); an accepted CALL/PUT is explained by
        # what SUPPORTED it (reasons). Reading warnings first for an accepted
        # signal surfaces the standing "meta model not available yet" caveat
        # instead of the actual setup -- true, but not why this trade fired.
        if decision.direction in ("CALL", "PUT"):
            note = (decision.reasons or decision.warnings or [""])[0]
        else:
            note = (decision.warnings or decision.reasons or [""])[0]
        logger.info(
            "%s: %s %s score=%d regime=%s%s | %s",
            asset.value, decision.direction, decision.grade,
            decision.technical_score, decision.market_regime,
            f" expiry={decision.expiry_seconds}s" if decision.expiry_seconds else "",
            note[:110],
        )
        insert_signal(asset, decision)
    except Exception as exc:  # noqa: BLE001 -- deliberately broad, see docstring
        logger.exception("analysis cycle failed for %s", asset.value)
        audit.record(
            audit.ACTION_ANALYSIS_FAILED,
            target_table="signals",
            target_id=asset.value,
            metadata={"error": str(exc)},
        )
