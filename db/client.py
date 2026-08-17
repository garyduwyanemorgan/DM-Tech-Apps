"""Supabase client — singleton, lazy-initialised.

Credentials are SUPABASE_URL / SUPABASE_KEY, resolved by core.config (env ->
.env -> secrets.toml). Token-scoped requests use SUPABASE_ANON_KEY instead of
the service_role key, so Row-Level Security is actually enforced for them.

Returns None gracefully when Supabase is not configured or the package
is not installed, so the dashboard falls back to sample data silently.
"""
from __future__ import annotations

import contextvars

from core.config import secret
from core.reasons import ANON_KEY_MISSING, DB_UNAVAILABLE, NOT_CONFIGURED

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


# Re-entrancy guard. core.audit._persist() writes through get_client(), so a
# failed get_client() that emits an audit event re-enters get_client(), which
# fails again, which emits again — unbounded recursion that only stops when
# RecursionError is swallowed by audit's own except. Measured at 50+ frames per
# call before this guard. It triggers exactly when the database is unreachable,
# i.e. the failure this instrumentation exists to observe, so the guard is not
# optional. A ContextVar rather than a plain bool so concurrent requests on the
# same thread cannot suppress each other's events.
_emitting: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "db_client_emitting", default=False
)


def _emit_client_failure(reason_code: str, *, detail: str | None = None, scoped: bool) -> None:
    """Record why a client could not be built. Never raises into the caller.

    Imported lazily to avoid a cycle: core.audit's own best-effort persistence
    goes through db.client.get_client(), so importing audit at module scope
    here would run at import time before this module finishes defining itself.
    """
    if _emitting.get():
        # We are already inside an emission whose own persistence just failed
        # to build a client. The outer call has reported this; reporting it
        # again would recurse forever.
        return
    token = _emitting.set(True)
    try:
        from core.audit import emit
        emit(
            "db.client.unavailable",
            actor_user_id=None,
            actor_role=None,
            organization_id=None,
            outcome="error",
            target_type="supabase_client",
            reason_code=reason_code,
            scoped=scoped,
            detail=detail,
        )
    except Exception:
        # Auditing must never break client resolution, which already fails
        # closed (returns None) on every path that calls this.
        pass
    finally:
        _emitting.reset(token)


def get_client(token: str | None = None):
    """Return a live Supabase client, optionally scoped with a user's JWT token."""
    global _client
    if not _SUPABASE_PKG:
        _emit_client_failure(NOT_CONFIGURED, detail="supabase package not installed",
                             scoped=bool(token))
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
            _emit_client_failure(ANON_KEY_MISSING, scoped=True)
            return None
        try:
            scoped_client = create_client(cfg["url"], cfg["key"])
            scoped_client.postgrest.auth(token)
            return scoped_client
        except Exception as exc:
            _emit_client_failure(DB_UNAVAILABLE, detail=str(exc)[:200], scoped=True)
            return None

    cfg = _secrets()
    if not cfg:
        _emit_client_failure(NOT_CONFIGURED, detail="SUPABASE_URL/SUPABASE_KEY not set",
                             scoped=False)
        return None
    if _client is not None:
        return _client
    try:
        _client = create_client(cfg["url"], cfg["key"])
        return _client
    except Exception as exc:
        _emit_client_failure(DB_UNAVAILABLE, detail=str(exc)[:200], scoped=False)
        return None


def is_configured() -> bool:
    """True when secrets are present and the supabase package is installed."""
    return _SUPABASE_PKG and _secrets() is not None
