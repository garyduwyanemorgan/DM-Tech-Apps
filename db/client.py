"""Supabase client — singleton, lazy-initialised.

Credentials are SUPABASE_URL / SUPABASE_KEY, resolved by core.config (env ->
.env -> secrets.toml). Token-scoped requests use SUPABASE_ANON_KEY instead of
the service_role key, so Row-Level Security is actually enforced for them.

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


def _anon_secrets() -> dict | None:
    """Return {url, key} using the anon key, or None when not configured.

    The anon key is required for token-scoped clients: it carries no
    privileges of its own, so Row-Level Security is enforced against the
    token passed to `.postgrest.auth()`. Falling back to the service_role
    key here would defeat that entirely.
    """
    url = secret("supabase", "url")
    anon_key = secret("supabase", "anon_key")
    return {"url": url, "key": anon_key} if url and anon_key else None


def get_client(token: str | None = None):
    """Return a live Supabase client, optionally scoped with a user's JWT token."""
    global _client
    if not _SUPABASE_PKG:
        return None
    if token:
        # Create a request-scoped client for this specific request context
        # to enforce Row-Level Security safely without concurrent race conditions.
        # This MUST use the anon key, never service_role: a request-scoped
        # client built from service_role would bypass RLS entirely if the
        # token turned out to be missing or invalid, which is exactly the
        # fail-open hole this function exists to close. If no anon key is
        # configured we fail closed (return None) rather than silently
        # falling back to service_role.
        cfg = _anon_secrets()
        if not cfg:
            return None
        try:
            scoped_client = create_client(cfg["url"], cfg["key"])
            scoped_client.postgrest.auth(token)
            return scoped_client
        except Exception:
            return None

    cfg = _secrets()
    if not cfg:
        return None
    if _client is not None:
        return _client
    try:
        _client = create_client(cfg["url"], cfg["key"])
        return _client
    except Exception:
        return None


def is_configured() -> bool:
    """True when secrets are present and the supabase package is installed."""
    return _SUPABASE_PKG and _secrets() is not None
