"""
Service-role Supabase client, for the collector's own writes. Deliberately
separate from apps/web's clients (which use the anon key and go through
RLS) -- this key bypasses RLS by design, so it must never be exposed to
the frontend or committed to version control (see .env.example).
"""

from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


class SupabaseNotConfiguredError(Exception):
    """Raised when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY aren't set."""


@lru_cache
def get_service_client() -> Client:
    settings = get_settings()
    if not settings.has_supabase:
        raise SupabaseNotConfiguredError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set "
            "before the collector can write anything."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
