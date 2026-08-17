"""Layer 3 observability — crash reporting, off unless explicitly configured.

Layers 0-2 (core/observability.py, core/reasons.py, core/workflow.py) record
what this system does and why it fails, and all of it stays inside our own
Postgres. This module is the only piece that can send anything OUTWARD, so it
is built to be inert by default and conservative when switched on.

    SENTRY_DSN unset  ->  complete no-op. No SDK import, no network, no cost.
    SENTRY_DSN set    ->  unhandled exceptions are reported to that collector.

WHY OFF BY DEFAULT
------------------
A crash report is not just "line 32 raised TypeError". Out of the box these
SDKs attach local variables from every stack frame, request headers, cookies
and request bodies — which in this codebase can mean organisation ids, email
addresses, site names and lab results. This is regulated environmental data
handled for a government client, so shipping it to a third-party host is a
contractual and data-residency decision, not a default. Nothing here transmits
until somebody sets a DSN deliberately.

SELF-HOSTING
------------
The DSN is Sentry-protocol, so it points equally at hosted Sentry or at a
self-hosted GlitchTip. Pointing it at GlitchTip beside the existing Supabase
stack keeps crash data on our own infrastructure and sidesteps the residency
question rather than answering it. That is the recommended deployment.

WHAT IS STRIPPED BEFORE SENDING
-------------------------------
Even with a DSN configured, `_before_send` removes the payload that makes
these reports risky: request bodies, cookies, headers (Authorization and the
Clerk session token above all), and frame-local variables. What remains is the
exception type, the stack trace, and the correlation ids needed to find the
matching rows in our own audit_events / workflow_events — which is where the
detail already lives, safely, under our control.

The correlation id is attached as a tag, so a crash report and the local
evidence trail resolve to the same request rather than being two disconnected
records.
"""
from __future__ import annotations

import os
from typing import Any, Optional

# Header names dropped wholesale. Lower-cased for comparison.
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "apikey",
    "x-organization-id",
}

# Context/extra keys that must never leave, whatever attached them.
_SENSITIVE_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "password",
    "authorization",
    "clerk_secret_key",
    "supabase_key",
    "service_role_key",
    "anon_key",
}

_REDACTED = "[redacted]"

_initialised = False


def is_enabled() -> bool:
    """True when a DSN is configured. Everything here is a no-op otherwise."""
    return bool(_dsn())


def _dsn() -> str:
    return (os.environ.get("SENTRY_DSN") or "").strip()


def _send_source() -> bool:
    """True when source snippets may accompany a report. Off unless asked for."""
    return (os.environ.get("SENTRY_SEND_SOURCE") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _scrub_mapping(data: Any, *, drop: set[str]) -> Any:
    """Recursively redact keys in `drop`. Returns the same shape it was given."""
    if isinstance(data, dict):
        return {
            k: (_REDACTED if str(k).lower() in drop else _scrub_mapping(v, drop=drop))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_scrub_mapping(v, drop=drop) for v in data]
    return data


def _before_send(event: dict, hint: dict | None = None) -> Optional[dict]:
    """Strip everything that could carry tenant data, then let the event go.

    Runs on every event. Deliberately subtractive: it removes known-dangerous
    payload rather than trying to detect sensitive values, because the latter
    fails open on anything it does not recognise.
    """
    try:
        request = event.get("request")
        if isinstance(request, dict):
            # Bodies and cookies go entirely — never worth the risk.
            request.pop("data", None)
            request.pop("cookies", None)
            headers = request.get("headers")
            if isinstance(headers, dict):
                request["headers"] = {
                    k: (_REDACTED if str(k).lower() in _SENSITIVE_HEADERS else v)
                    for k, v in headers.items()
                }
            # A query string can carry ids; keep the path, drop the rest.
            request.pop("query_string", None)

        # Frame-local variables are the single largest leak: they hold whatever
        # the failing function was holding, including rows just read from the
        # database. The stack trace itself is what has diagnostic value.
        for exception in (event.get("exception") or {}).get("values") or []:
            for frame in (exception.get("stacktrace") or {}).get("frames") or []:
                frame.pop("vars", None)

        for key in ("extra", "contexts", "tags"):
            if key in event:
                event[key] = _scrub_mapping(event[key], drop=_SENSITIVE_KEYS)

        # Correlate the crash report with our own evidence trail.
        try:
            from core.observability import current_request_id
            rid = current_request_id()
            if rid:
                tags = event.setdefault("tags", {})
                if isinstance(tags, dict):
                    tags["request_id"] = rid
        except Exception:
            pass

        return event
    except Exception:
        # A scrubber that raises would either drop the event or, worse, let an
        # unscrubbed one through. Dropping is the safe failure.
        return None


def init_error_tracking() -> bool:
    """Initialise crash reporting if a DSN is set. Returns True if active.

    Safe to call more than once and safe to call when `sentry_sdk` is not
    installed — both are no-ops. Never raises: a telemetry failure must not
    stop the server from starting.
    """
    global _initialised
    if _initialised or not is_enabled():
        return False
    try:
        import sentry_sdk
    except ImportError:
        # DSN set but the SDK absent is a misconfiguration worth seeing, but
        # not worth crashing over.
        print(
            "SENTRY_DSN is set but sentry-sdk is not installed; "
            "crash reporting is inactive.",
            flush=True,
        )
        return False
    try:
        sentry_sdk.init(
            dsn=_dsn(),
            environment=os.environ.get("SENTRY_ENVIRONMENT", "development"),
            release=os.environ.get("SENTRY_RELEASE") or None,
            # No PII, no bodies. The defaults are the permissive opposite.
            send_default_pii=False,
            max_request_body_size="never",
            # Crash reporting only. Performance tracing would sample real
            # request URLs and timings continuously; that is a separate
            # decision with its own data-volume and residency implications.
            traces_sample_rate=0.0,
            # Source context OFF by default. The SDK otherwise attaches the
            # surrounding source lines of every frame (`pre_context` /
            # `context_line` / `post_context`), which ships proprietary source
            # to whoever runs the collector. Verified by capturing a real
            # exception and inspecting the payload — stripping frame locals
            # alone does NOT prevent this, because the values also appear in
            # the code lines that reference them.
            #
            # We still get file, line number and function, and the repository
            # is right there to read. Set SENTRY_SEND_SOURCE=1 to turn it back
            # on — reasonable for a self-hosted GlitchTip, where the code never
            # leaves our own infrastructure anyway.
            include_source_context=_send_source(),
            before_send=_before_send,
        )
        _initialised = True
        return True
    except Exception as exc:
        print(f"crash reporting failed to initialise: {type(exc).__name__}", flush=True)
        return False
