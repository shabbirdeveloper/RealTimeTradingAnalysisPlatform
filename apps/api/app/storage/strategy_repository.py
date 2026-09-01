"""
Loads per-asset strategy configuration from `strategy_configs`, layered over
the code defaults in app.features.strategy.

TWO FAILURE MODES, DELIBERATELY DISTINGUISHED
---------------------------------------------
An empty result and a failed query are not the same thing, and collapsing
them is the same class of mistake as `calendar_available` in the news filter:

  * No rows        -> no overrides exist. Normal. Defaults apply, which
                      reproduce today's behaviour. Nothing to warn about.
  * Query failed   -> we do not know what the rules are. Defaults still
                      apply (signal generation must not stop because a config
                      table is unreachable), but that is now failing OPEN:
                      if an admin had TIGHTENED the config, we are about to
                      generate signals under looser rules than they intended.
                      The caller gets `loaded=False` so it can say so.

The version stamp limits the damage either way -- signals produced during an
outage carry the defaults' fingerprint, so they can never be pooled with
signals produced under the tightened config. The data stays honest even when
the load does not.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from app.features.strategy import AssetStrategy, default_strategy, strategy_from_rows
from app.instruments import get_instrument
from app.schemas.candle import Asset
from app.storage.candle_repository import _asset_id_map
from app.storage.supabase_client import get_service_client

logger = logging.getLogger(__name__)

# Long enough that a poll cycle isn't issuing a config query per asset per
# minute; short enough that an admin who changes a threshold sees it take
# effect while they are still looking at the screen.
#
# Deliberately a TTL rather than @lru_cache: an unbounded process-lifetime
# cache means a config edit does nothing until someone restarts the
# collector, and "I changed it and nothing happened" is how people conclude
# the feature is broken and go back to editing code.
CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class LoadedStrategy:
    strategy: AssetStrategy
    # False means the stored config could not be read and defaults were
    # substituted -- see the module docstring. NOT the same as "no overrides".
    loaded: bool
    error: str | None = None


_lock = threading.Lock()
_cache: dict[str, tuple[float, LoadedStrategy]] = {}


def _fetch(asset: Asset) -> LoadedStrategy:
    try:
        asset_id = _asset_id_map()[asset]
        client = get_service_client()
        response = (
            client.table("strategy_configs")
            .select("expiry_minutes, expiry_seconds, min_technical_score, allowed_regimes, "
                    "allowed_sessions, enabled, label")
            .eq("asset_id", asset_id)
            .execute()
        )
        rows = response.data or []
        # Expiry set comes from the instrument's profile, so an OTC asset
        # gets its second-scale horizons rather than the real-market ones.
        expiries = get_instrument(asset.value).profile.expiries_seconds
        return LoadedStrategy(
            strategy=strategy_from_rows(asset.value, rows, expiries=expiries), loaded=True
        )
    except Exception as exc:  # noqa: BLE001 -- see module docstring
        logger.warning("strategy config load failed for %s: %s", asset.value, exc)
        return LoadedStrategy(
            strategy=default_strategy(
                asset.value, expiries=get_instrument(asset.value).profile.expiries_seconds
            ),
            loaded=False,
            error=str(exc),
        )


def load_strategy(asset: Asset, *, now: float | None = None) -> LoadedStrategy:
    """Cached for CACHE_TTL_SECONDS. A failed load is cached too, and on
    purpose: a database that is down stays down for more than a second, and
    retrying on every poll turns one outage into a flood of failing queries
    on the same connection the collector needs for candles."""
    now = time.monotonic() if now is None else now
    key = asset.value

    with _lock:
        cached = _cache.get(key)
        if cached is not None and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]

    # Fetched outside the lock: this makes a network call, and holding the
    # lock across it would serialize every asset's poll behind one slow query.
    # A rare duplicate fetch on a cold cache is much cheaper than that.
    result = _fetch(asset)

    with _lock:
        _cache[key] = (now, result)
    return result


def clear_cache() -> None:
    """For tests, and for an admin endpoint that wants a config change to
    apply immediately rather than within the TTL."""
    with _lock:
        _cache.clear()
