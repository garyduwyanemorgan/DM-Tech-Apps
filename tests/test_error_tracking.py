"""Crash reporting must stay silent by default, and stay clean when switched on.

Layer 3 is the only part of the observability stack that can transmit anything
off this machine, so the properties worth pinning are not "does it report" but:

  1. with no DSN it does nothing at all, and
  2. with a DSN it does not carry tenant data out with the stack trace.

The scrubber is tested directly rather than through sentry_sdk, so these run
with the SDK absent — which is its normal state here, since it is an optional
dependency. A test that silently skipped when sentry-sdk was missing would
leave the redaction logic — the whole safety argument — unexercised.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import errors  # noqa: E402


# ── Off by default ────────────────────────────────────────────────────────────

def test_disabled_when_no_dsn_is_configured(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert errors.is_enabled() is False


def test_blank_and_whitespace_dsn_count_as_unset(monkeypatch):
    for value in ("", "   ", "\t"):
        monkeypatch.setenv("SENTRY_DSN", value)
        assert errors.is_enabled() is False, f"{value!r} must not enable reporting"


def test_init_is_a_noop_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(errors, "_initialised", False)
    assert errors.init_error_tracking() is False


def test_init_does_not_raise_when_sdk_is_missing(monkeypatch):
    """A DSN set without the SDK installed must not stop the server booting."""
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
    monkeypatch.setattr(errors, "_initialised", False)
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # force ImportError
    assert errors.init_error_tracking() is False


def test_a_dsn_enables_the_feature_flag(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
    assert errors.is_enabled() is True


# ── Source context: off unless explicitly asked for ───────────────────────────

def test_source_context_is_off_by_default(monkeypatch):
    """The SDK ships surrounding source lines unless told not to.

    Stripping frame locals is NOT sufficient on its own: a value assigned in
    the code also appears in the source line that assigns it, so with source
    context enabled the payload carries the data back out again. Verified
    against the real SDK by capturing an exception and inspecting the event.
    """
    monkeypatch.delenv("SENTRY_SEND_SOURCE", raising=False)
    assert errors._send_source() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_source_context_can_be_opted_into(monkeypatch, value):
    monkeypatch.setenv("SENTRY_SEND_SOURCE", value)
    assert errors._send_source() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
def test_only_affirmative_values_enable_source_context(monkeypatch, value):
    monkeypatch.setenv("SENTRY_SEND_SOURCE", value)
    assert errors._send_source() is False


# ── The scrubber: what must never leave ───────────────────────────────────────

def _event_with_everything() -> dict:
    return {
        "request": {
            "url": "https://app.example/api/sites",
            "method": "POST",
            "data": {"site_name": "Dubai Safari Lagoon 3", "ph": 7.9},
            "cookies": {"__session": "clerk-session-cookie"},
            "query_string": "organization_id=ee254648-d393-4edf",
            "headers": {
                "Authorization": "Bearer eyJhbGciOi.super.secret",
                "X-Api-Key": "sk_live_abc123",
                "Cookie": "__session=abc",
                "X-Organization-Id": "ee254648-d393-4edf",
                "User-Agent": "Mozilla/5.0",
            },
        },
        "exception": {
            "values": [{
                "type": "TypeError",
                "stacktrace": {"frames": [
                    {"filename": "db/queries.py", "lineno": 120,
                     "vars": {"organization_id": "ee254648", "rows": [{"ph": 7.9}]}},
                    {"filename": "core/calculations.py", "lineno": 32,
                     "vars": {"value": None, "token": "eyJhbGciOi"}},
                ]},
            }],
        },
        "extra": {"token": "eyJhbGciOi.secret", "site": "Lagoon 3"},
        "tags": {"api_key": "sk_live_abc", "step": "parse"},
    }


def test_request_body_and_cookies_are_dropped():
    ev = errors._before_send(_event_with_everything())
    assert "data" not in ev["request"]
    assert "cookies" not in ev["request"]
    assert "query_string" not in ev["request"]


def test_sensitive_headers_are_redacted_but_harmless_ones_survive():
    ev = errors._before_send(_event_with_everything())
    headers = ev["request"]["headers"]
    for name in ("Authorization", "X-Api-Key", "Cookie", "X-Organization-Id"):
        assert headers[name] == errors._REDACTED, f"{name} leaked"
    # Diagnostic value with no tenant data — keeping it is the point.
    assert headers["User-Agent"] == "Mozilla/5.0"


def test_frame_local_variables_are_stripped_but_the_trace_survives():
    """Locals hold whatever the failing function held, including DB rows."""
    ev = errors._before_send(_event_with_everything())
    frames = ev["exception"]["values"][0]["stacktrace"]["frames"]
    assert frames, "the stack trace itself must survive — it is the diagnostic value"
    for frame in frames:
        assert "vars" not in frame
        assert frame["filename"]          # still identifies where it broke
        assert frame["lineno"]


def test_sensitive_keys_in_extra_and_tags_are_redacted():
    ev = errors._before_send(_event_with_everything())
    assert ev["extra"]["token"] == errors._REDACTED
    assert ev["tags"]["api_key"] == errors._REDACTED
    # Non-sensitive context is preserved, or the report would be useless.
    assert ev["extra"]["site"] == "Lagoon 3"
    assert ev["tags"]["step"] == "parse"


def test_no_secret_value_survives_anywhere_in_the_payload():
    """Belt and braces: scan the whole serialised event for known secrets."""
    import json
    ev = errors._before_send(_event_with_everything())
    blob = json.dumps(ev)
    for secret in ("eyJhbGciOi", "sk_live_abc", "clerk-session-cookie",
                   "Dubai Safari Lagoon 3"):
        assert secret not in blob, f"{secret!r} survived scrubbing"


def test_nested_sensitive_keys_are_redacted():
    ev = errors._before_send({"extra": {"outer": {"inner": {"password": "hunter2"}}}})
    assert ev["extra"]["outer"]["inner"]["password"] == errors._REDACTED


# ── Correlation with our own evidence trail ───────────────────────────────────

def test_request_id_is_attached_as_a_tag():
    from core.observability import set_request_id, reset_request_id
    token = set_request_id("corr-abc-123")
    try:
        ev = errors._before_send({"exception": {"values": []}})
    finally:
        reset_request_id(token)
    assert ev["tags"]["request_id"] == "corr-abc-123"


def test_no_request_id_tag_outside_a_request():
    ev = errors._before_send({"exception": {"values": []}})
    assert "request_id" not in (ev.get("tags") or {})


# ── Failure modes ─────────────────────────────────────────────────────────────

def test_a_scrubber_failure_drops_the_event_rather_than_leaking_it():
    """Failing closed matters more here than delivering the report."""
    class Hostile(dict):
        def get(self, *a, **k):
            raise RuntimeError("boom")

    assert errors._before_send(Hostile()) is None


def test_an_empty_event_survives_scrubbing():
    assert errors._before_send({}) == {}
