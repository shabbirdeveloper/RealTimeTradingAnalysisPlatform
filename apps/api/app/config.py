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

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

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
