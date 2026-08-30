"""
Selects the economic calendar provider. Currently only the null provider
exists -- see `base.py` for why, and what implementing a real one takes.
"""
from __future__ import annotations

import logging

from app.news.base import EconomicCalendarProvider, NullCalendarProvider

logger = logging.getLogger(__name__)


def build_calendar_provider() -> EconomicCalendarProvider:
    # When a real provider is added, select it here based on settings
    # (e.g. `if settings.calendar_api_key: return TradingEconomicsProvider(...)`),
    # exactly like app/collector/scheduler.py:build_provider() does for
    # market data.
    return NullCalendarProvider()
