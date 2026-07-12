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
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist(event: dict) -> None:
    """Best-effort durable write. No-op until the audit_events table exists.

    Wrapped by the caller in a broad try/except; kept separate so the DB-backed
    implementation can be dropped in here later (service-role insert, append-only).
    """
    # TODO(phase1-migration): insert into audit_events once 006_audit_events.sql
    # is applied. Intentionally a no-op now so nothing writes to a missing table.
    return None


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
    }
    if extra:
        event["context"] = extra
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
