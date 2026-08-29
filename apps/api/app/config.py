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
    poll_interval_seconds: int = Field(default=300, ge=30)

    # How many recent M5 bars to request per poll. Larger than the bare
    # minimum on purpose, so a missed poll (network hiccup, restart) still
    # self-heals on the next successful call instead of leaving a gap.
    poll_outputsize: int = Field(default=30, ge=12, le=200)

    @property
    def has_real_provider(self) -> bool:
        return bool(self.twelve_data_api_key)

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
