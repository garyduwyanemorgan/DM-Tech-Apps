"""Supabase client — singleton, lazy-initialised.

Credentials are SUPABASE_URL / SUPABASE_KEY, resolved by core.config (env ->
.env -> secrets.toml).

Returns None gracefully when Supabase is not configured or the package
is not installed, so the dashboard falls back to sample data silently.
"""
from __future__ import annotations

from core.config import secret

try:
    from supabase import create_client, Client as SupabaseClient
    _SUPABASE_PKG = True
except ImportError:
    _SUPABASE_PKG = False

_client: object | None = None


def _secrets() -> dict | None:
    """Return {url, key}, or None when Supabase is not configured."""
    url = secret("supabase", "url")
    key = secret("supabase", "key")
    return {"url": url, "key": key} if url and key else None


def get_client(token: str | None = None):
    """Return a live Supabase client, optionally scoped with a user's JWT token."""
    global _client
    if not _SUPABASE_PKG:
        return None
    cfg = _secrets()
    if not cfg:
        return None
    try:
        if token:
            # Create a request-scoped client for this specific request context
            # to enforce Row-Level Security safely without concurrent race conditions.
            scoped_client = create_client(cfg["url"], cfg["key"])
            scoped_client.postgrest.auth(token)
            return scoped_client

        global _client
        if _client is not None:
            return _client
        _client = create_client(cfg["url"], cfg["key"])
        return _client
    except Exception:
        return None


def is_configured() -> bool:
    """True when secrets are present and the supabase package is installed."""
    return _SUPABASE_PKG and _secrets() is not None
