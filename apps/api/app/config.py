"""
Central settings, loaded from environment variables (and a local .env file
in development). Nothing in here has a hardcoded secret or API key -- see
.env.example for what must be supplied.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field(default="development")

    # Market data provider (Twelve Data). If unset, the collector falls
    # back to the demo provider so the rest of the pipeline (aggregation,
    # storage, health reporting) can be exercised without spending API
    # credits or requiring a key.
    twelve_data_api_key: str | None = Field(default=None)

    # Supabase. The SERVICE ROLE key is required here (not the anon key) --
    # this process writes candles/system_health directly, bypassing RLS by
    # design, since RLS on those tables is written for what the *browser*
    # is allowed to touch, not the trusted collector process. Never send
    # this key to the frontend.
    supabase_url: str | None = Field(default=None)
    supabase_service_role_key: str | None = Field(default=None)

    # How often the collector polls for new M5 candles, per asset. Kept
    # configurable because it directly trades off against API credit
    # budget -- see apps/api/README.md for the math on your provider plan.
    #
    # Default raised from 300s to 600s when the two 24/7 crypto assets were
    # added: crypto polls around the clock while forex only trades ~17h/day,
    # so 5 assets at 300s is ~1,198 requests/day -- well over Twelve Data's
    # 800/day free tier. Break-even is ~450s; 600s leaves headroom for
    # retries and restarts.
    poll_interval_seconds: int = Field(default=600, ge=30)

    # Per-asset polling cadence instead of one interval for everything:
    # forex/gold every 5 minutes while London or New York is open, every 15
    # otherwise; crypto every 30. See collector/cadence.py for the budget
    # arithmetic. Set to false to fall back to `poll_interval_seconds` for
    # every asset -- the escape hatch if a provider plan changes shape.
    adaptive_polling: bool = Field(default=True)

    # The public-market collector (XAUUSD/EURUSD/GBPUSD/BTC/ETH), OFF by
    # default. The reset concentrates the whole engineering effort on one
    # broker-OTC series, and the spec is explicit that no other instrument
    # should generate signals while that is true.
    #
    # Disabled rather than deleted: the provider, storage and dashboard
    # pages all still work, so re-enabling is a flag rather than a
    # restoration. Turning it on means two engines run at once, and their
    # results must not then be pooled into one accuracy figure.
    public_market_collector_enabled: bool = Field(default=False)

    # Deriv synthetic indices -- broker-generated instruments that trade
    # 24/7, through a documented public API. Only an app_id is needed;
    # market data requires no account token, so nothing secret lives here.
    # Register one at https://api.deriv.com.
    #
    # Unset means the OTC side stays dark, which is the correct default:
    # the engine refuses to price a broker instrument with no broker feed
    # rather than substituting a real-market pair of a similar name.
    deriv_app_id: str | None = Field(default=None)
    # Which registry symbols to collect. Start with one; more instruments
    # multiply the request budget and dilute the sample each is measured on.
    deriv_symbols: str = Field(default="DERIV_V75")

    # How many recent M5 bars to request per poll. Larger than the bare
    # minimum on purpose, so a missed poll (network hiccup, restart) still
    # self-heals on the next successful call instead of leaving a gap.
    poll_outputsize: int = Field(default=30, ge=12, le=200)

    # Shared secret for this service's admin endpoints (currently the
    # backtest trigger). This service has no user auth of its own -- it
    # runs with the service-role key and is meant to sit on a private
    # network, not the public internet. This is a deliberate minimum bar,
    # not a real auth system: if it is unset, admin routes refuse to run
    # rather than defaulting open. Anything internet-facing needs a proper
    # auth layer in front of this service regardless.
    admin_api_key: str | None = Field(default=None)

    # Telegram alerting. Optional: unset means signals are recorded but not
    # pushed anywhere. Both values are required together -- a token with no
    # chat id can authenticate and still deliver nothing, which looks like a
    # working integration that silently drops every message.
    telegram_bot_token: str | None = Field(default=None)
    telegram_chat_id: str | None = Field(default=None)

    # Hour (UTC) at which the daily "collector is alive" report is sent to
    # Telegram. This engine is built to reject most setups, so a quiet
    # channel is the expected state -- but silence from a working system
    # and silence from a dead one are indistinguishable, and the natural
    # reaction to that ambiguity is to lower the quality bar until messages
    # appear. One daily report removes the ambiguity for the price of one
    # message a day. Set to -1 to switch it off.
    heartbeat_hour_utc: int = Field(default=0, ge=-1, le=23)

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def heartbeat_enabled(self) -> bool:
        return self.heartbeat_hour_utc >= 0 and self.has_telegram

    @property
    def has_deriv(self) -> bool:
        return bool(self.deriv_app_id)

    @property
    def deriv_symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.deriv_symbols.split(",") if s.strip()]

    @property
    def has_real_provider(self) -> bool:
        return bool(self.twelve_data_api_key)

    @property
    def has_admin_api_key(self) -> bool:
        return bool(self.admin_api_key)

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
