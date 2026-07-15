"""Demo-mode decision logic — pure and unit-testable, no DB or web framework.

A demo is one server-provisioned key per organization giving full access
(unlimited sites) for DEMO_DURATION_DAYS from activation. After expiry the org
is read-only until it subscribes — billing stays reachable so "switch to live"
is one click, and all demo data carries over. The DB wrappers live in
db/queries.py; the request-time gate lives in api_server.py.
"""
from __future__ import annotations

import math
import secrets
from datetime import datetime, timedelta, timezone

DEMO_DURATION_DAYS = 30  # "one month" per demo key

# Permissions that stay usable after a demo expires. Billing must remain open —
# it IS the switch-to-live path. Everything else that mutates data is blocked;
# reads (*.read) are always allowed so the org can still see its own data.
_EXPIRED_DEMO_ALLOWED = frozenset({"billing.read", "billing.manage"})


def generate_demo_key() -> str:
    """A readable demo key code, e.g. DEMO-9F3A-C07D-51B2. The user never types
    it (activation is one click); it exists as a database artifact for audit."""
    raw = secrets.token_hex(6).upper()
    return f"DEMO-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def demo_expiry(activated_at: datetime) -> datetime:
    return activated_at + timedelta(days=DEMO_DURATION_DAYS)


def parse_ts(value: str | datetime | None) -> datetime | None:
    """Parse a Supabase timestamptz (ISO string) into an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def demo_status(expires_at: str | datetime | None, *, now: datetime | None = None) -> dict:
    """Active/expired flags and whole-days-left for a demo key expiry.

    days_left counts partial days as a full day (a demo expiring in one hour
    shows "1 day left", not "0"), and is 0 once expired.
    """
    now = now or datetime.now(timezone.utc)
    exp = parse_ts(expires_at)
    if exp is None:
        return {"active": False, "expired": False, "days_left": 0}
    remaining = (exp - now).total_seconds()
    if remaining <= 0:
        return {"active": False, "expired": True, "days_left": 0}
    return {"active": True, "expired": False, "days_left": math.ceil(remaining / 86400)}


def blocked_when_demo_expired(permission: str) -> bool:
    """True iff this permission should be denied for an org whose demo has
    expired (and that has no subscription). Read-only + billing stays open."""
    if permission.endswith(".read"):
        return False
    return permission not in _EXPIRED_DEMO_ALLOWED
