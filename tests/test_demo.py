"""Unit tests for demo-mode decision logic (core/demo.py).

Pure — no web framework, DB, or env required. Runnable two ways:
    python tests/test_demo.py
    pytest tests/test_demo.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.demo import (  # noqa: E402
    DEMO_DURATION_DAYS,
    blocked_when_demo_expired,
    demo_expiry,
    demo_status,
    generate_demo_key,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def test_demo_lasts_one_month():
    assert DEMO_DURATION_DAYS == 30
    assert demo_expiry(NOW) == NOW + timedelta(days=30)


def test_status_active_with_ceiling_days_left():
    st = demo_status(NOW + timedelta(days=30), now=NOW)
    assert st == {"active": True, "expired": False, "days_left": 30}
    # Partial days round UP: one hour left still reads "1 day left".
    st = demo_status(NOW + timedelta(hours=1), now=NOW)
    assert st == {"active": True, "expired": False, "days_left": 1}


def test_status_expired():
    st = demo_status(NOW - timedelta(seconds=1), now=NOW)
    assert st == {"active": False, "expired": True, "days_left": 0}


def test_status_accepts_iso_strings_and_none():
    # Supabase returns timestamptz as ISO strings.
    st = demo_status((NOW + timedelta(days=2)).isoformat(), now=NOW)
    assert st["active"] and st["days_left"] == 2
    # No/garbled expiry -> neither active nor expired (fail open: no block).
    assert demo_status(None, now=NOW) == {"active": False, "expired": False, "days_left": 0}
    assert demo_status("not-a-date", now=NOW) == {"active": False, "expired": False, "days_left": 0}


def test_expired_demo_blocks_writes_not_reads():
    # Writes are blocked once the demo has expired...
    for perm in ("sites.create", "readings.create", "sludge.write",
                 "users.invite", "actions.create", "inventory.consume"):
        assert blocked_when_demo_expired(perm), perm
    # ...reads always work, and billing stays open — it IS the go-live path.
    for perm in ("sites.read", "readings.read", "analytics.executive.read",
                 "billing.read", "billing.manage"):
        assert not blocked_when_demo_expired(perm), perm


def test_key_format():
    key = generate_demo_key()
    assert key.startswith("DEMO-") and len(key) == 19
    assert key != generate_demo_key()  # random


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
