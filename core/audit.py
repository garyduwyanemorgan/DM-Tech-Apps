"""Structured security-audit event emitter.

Every authorization failure and sensitive mutation should produce one auditable
event (PERMISSIONS_MATRIX.md priority gap #5). This module is the single seam
for that. Today it emits a structured JSON line to stderr; once the append-only
``audit_events`` table exists (a Phase 1 migration), ``_persist`` can write there
without any call site changing. It must NEVER raise into a request path — audit
failure must not break the operation it is recording, but it also must not
silently swallow the *operation*; only the logging is best-effort.

It deliberately records identifiers only — never tokens, secrets, or full
request bodies — so audit logs stay safe to retain and export.

Every event is stamped with the current request id (see
``core/observability.py``), so a user-reported symptom can be traced from an
``X-Request-Id`` response header straight to the exact audit rows and log
lines produced while handling that request. ``audit_events`` has no
``request_id`` column, so the id rides inside the existing ``context`` JSONB
column rather than requiring a migration. Reading the request id must be as
best-effort as everything else here: if it fails for any reason, the event
is still emitted, just without one.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist(event: dict) -> None:
    """Best-effort durable write to the append-only audit_events table.

    Safe before the table exists: any error (missing table, no DB configured) is
    swallowed by the caller, so auditing degrades to stderr-only until migration
    006_audit_events.sql is applied, then "lights up" with no code change. Maps the
    emitter's ``context`` extras into the table's JSONB column.
    """
    from db.client import get_client
    client = get_client()
    if not client:
        return
    row = {
        "organization_id": event.get("organization_id"),
        "actor_user_id": event.get("actor_user_id"),
        "actor_role": event.get("actor_role"),
        "action": event.get("action"),
        "outcome": event.get("outcome"),
        "target_type": event.get("target_type"),
        "target_id": event.get("target_id"),
        "context": event.get("context"),
    }
    client.table("audit_events").insert(row).execute()


def emit(
    action: str,
    *,
    actor_user_id: Optional[str],
    actor_role: Optional[str],
    organization_id: Optional[str],
    outcome: str = "success",
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    **extra: Any,
) -> None:
    """Record a security-relevant event.

    action        stable verb, e.g. "role.assign", "site.delete", "report.finalize".
    outcome       "success" | "denied" | "error".
    target_*      the object acted on (type + id), if any.
    extra         additional non-sensitive context (no tokens/secrets/PII bodies).
    """
    # Best-effort: a request id is a nice-to-have for correlation, never a
    # reason to fail an audit event. Falls back to None outside a request
    # (scripts, background jobs, tests that skip the middleware) or if
    # reading the contextvar somehow errors.
    try:
        from core.observability import current_request_id
        request_id = current_request_id()
    except Exception:
        request_id = None

    event = {
        "ts": _now_iso(),
        "kind": "audit",
        "action": action,
        "outcome": outcome,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "organization_id": organization_id,
        "target_type": target_type,
        "target_id": target_id,
        "request_id": request_id,
    }
    context = dict(extra) if extra else {}
    if request_id is not None:
        context["request_id"] = request_id
    if context:
        event["context"] = context
    try:
        print(json.dumps(event, default=str), file=sys.stderr, flush=True)
        _persist(event)
    except Exception:
        # Never let auditing break the request it is recording.
        pass


def emit_denial(
    permission: str,
    *,
    actor_user_id: Optional[str],
    actor_role: Optional[str],
    organization_id: Optional[str],
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
) -> None:
    """Convenience wrapper for an authorization denial (403)."""
    emit(
        "authz.denied",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        organization_id=organization_id,
        outcome="denied",
        target_type=target_type,
        target_id=target_id,
        permission=permission,
    )
