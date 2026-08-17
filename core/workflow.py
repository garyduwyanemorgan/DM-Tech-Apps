"""Structured workflow (compliance pipeline) event emitter — Layer 2.

Every run of the compliance pipeline

    ingest -> parse -> validate(gates) -> persist -> assess -> obligation -> report

should produce one recorded outcome per step, per entity. This module is the
single seam for that. Customers of this product do not ask "did the server
500" — they ask "why is Site 7's March obligation still non-compliant?", and
the answer is "which step failed, and why". This module makes that answerable
without reading logs: it emits a structured JSON line to stderr for local
debugging, and durably persists to the append-only ``workflow_events`` table
(migration 031) so the question can be answered per-entity, after the fact.

It deliberately mirrors ``core/audit.py``'s hard rule: this must NEVER raise
into the caller. Recording a workflow outcome must not itself become a new
failure mode. ``step_timer`` is the one exception to "never raise" in spirit
only — it re-raises the *caller's* original exception after recording it,
because this module records outcomes, it does not swallow them.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional

# core.reasons imports nothing from this module, so a direct import is safe and
# keeps the reason vocabulary a hard dependency rather than an optional one.
from core.reasons import UNEXPECTED_ERROR

# ── Canonical step names, defined once so call sites cannot drift/typo them ──
INGEST = "ingest"
PARSE = "parse"
VALIDATE = "validate"
PERSIST = "persist"
ASSESS = "assess"
OBLIGATION = "obligation"
REPORT = "report"


def new_run_id() -> str:
    """Mint a fresh id correlating every step of one pipeline run."""
    return uuid.uuid4().hex


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_request_id() -> Optional[str]:
    """Best-effort request id, guarded because core.observability may not be
    importable yet — another agent owns that module in this branch."""
    try:
        from core.observability import current_request_id
        return current_request_id()
    except ImportError:
        return None
    except Exception:
        return None


def _persist(event: dict) -> None:
    """Best-effort durable write to the append-only workflow_events table.

    Safe before the table exists: any error (missing table, no DB configured)
    is swallowed by the caller, so this degrades to stderr-only until
    migration 031_workflow_events.sql is applied. Uses the service-role
    client (unscoped) so writes succeed regardless of the actor's RLS —
    imported lazily to avoid a hard dependency at module import time.
    """
    # Do not write real rows from a test run. The ingestion tests exercise the
    # instrumented gates against the live dev stack, and before this guard a
    # single `pytest` run wrote 63 org-less rows straight into workflow_events.
    # That corrupts the operational record with synthetic traffic — the table is
    # meant to be evidence, and evidence you cannot trust is worse than none.
    # The stderr line below still emits, so tests can assert on emission.
    # Tests that inject a fake client and assert on what it received opt back in
    # with WORKFLOW_PERSIST_IN_TESTS=1, so persistence stays directly testable
    # without any test being able to reach the real table by accident.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "WORKFLOW_PERSIST_IN_TESTS"
    ):
        return

    from db.client import get_client
    client = get_client()
    if not client:
        return
    row = {
        "run_id": event.get("run_id"),
        "request_id": event.get("request_id"),
        "organization_id": event.get("organization_id"),
        "step": event.get("step"),
        "status": event.get("status"),
        "reason_code": event.get("reason_code"),
        "entity_type": event.get("entity_type"),
        "entity_id": event.get("entity_id"),
        "duration_ms": event.get("duration_ms"),
        "context": event.get("context"),
    }
    client.table("workflow_events").insert(row).execute()


def emit_step(
    step: str,
    *,
    status: str,
    run_id: str,
    organization_id: Optional[str] = None,
    reason_code: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    duration_ms: Optional[int] = None,
    **context: Any,
) -> None:
    """Record one step's outcome for one pipeline run.

    step          one of the STEP constants (INGEST, PARSE, VALIDATE, PERSIST,
                  ASSESS, OBLIGATION, REPORT) — not enforced, so a step name
                  outside the canonical set still records, but call sites
                  should always pass a constant.
    status        "ok" | "failed" | "skipped".
    run_id        correlates every step of one pipeline run — see new_run_id().
    entity_*      the entity this step concerns (e.g. a site or lab sample),
                  if any.
    reason_code   stable code explaining a failed/skipped outcome. Prefer a
                  code from core.reasons when one applies.
    context       additional non-sensitive extra fields (no tokens/secrets).

    MUST NEVER raise into the caller — same hard rule as core/audit.py.
    """
    event = {
        "ts": _now_iso(),
        "kind": "workflow",
        "step": step,
        "status": status,
        "run_id": run_id,
        "request_id": _current_request_id(),
        "organization_id": organization_id,
        "reason_code": reason_code,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "duration_ms": duration_ms,
    }
    if context:
        event["context"] = context
    try:
        print(json.dumps(event, default=str), file=sys.stderr, flush=True)
        _persist(event)
    except Exception:
        # Never let workflow recording break the pipeline it is recording.
        pass


@contextmanager
def step_timer(
    step: str,
    *,
    run_id: str,
    organization_id: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    reason_code: Optional[str] = None,
    **context: Any,
):
    """Time a block of code as one pipeline step, recording its outcome.

    Emits status="ok" with the elapsed duration on normal exit. On an
    exception, emits status="failed" with a reason code (the given
    ``reason_code``, or one resolved from ``core.reasons`` for the exception
    when importable, or the exception's class name as a last resort), then
    RE-RAISES. Re-raising is deliberate: this module records outcomes, it
    does not swallow them — the caller's error handling still runs.
    """
    start = time.monotonic()
    try:
        yield
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        emit_step(
            step,
            status="failed",
            run_id=run_id,
            organization_id=organization_id,
            reason_code=reason_code or UNEXPECTED_ERROR,
            entity_type=entity_type,
            entity_id=entity_id,
            duration_ms=duration_ms,
            error=str(exc),
            # The exception class goes in the context, never in reason_code.
            # reason_code is a closed vocabulary you can GROUP BY; letting
            # arbitrary class names in gives it unbounded cardinality, makes
            # "how often does parse fail?" unanswerable, and produces codes the
            # UI cannot map to an explanation.
            exception_type=type(exc).__name__,
            **context,
        )
        raise
    else:
        duration_ms = int((time.monotonic() - start) * 1000)
        emit_step(
            step,
            status="ok",
            run_id=run_id,
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            duration_ms=duration_ms,
            **context,
        )


def describe_reason(code: str) -> str:
    """Human-readable text for a reason code, for UI and support tooling."""
    from core.reasons import describe
    return describe(code)
