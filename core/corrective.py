"""Corrective-action state machine — valid transitions and who may drive them.

Pure policy for db/migrations/008_corrective_actions.sql. Prevents invalid state
transitions and maps each transition to the atomic permission it requires, so the
workflow rules are unit-tested without a database (Phase 4). Site Supervisors
execute assigned actions; Managers/Executive assign and approve closure; General
Managers stay read-only (enforced by the permission bundles in core/authz.py).
"""
from __future__ import annotations

from typing import Dict, FrozenSet

OPEN = "open"
IN_PROGRESS = "in_progress"
PENDING_APPROVAL = "pending_approval"
CLOSED = "closed"
CANCELLED = "cancelled"

STATUSES: FrozenSet[str] = frozenset({OPEN, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELLED})

# Allowed forward/backward transitions. Closed and cancelled are terminal.
_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    OPEN: frozenset({IN_PROGRESS, CANCELLED}),
    IN_PROGRESS: frozenset({PENDING_APPROVAL, CANCELLED}),
    PENDING_APPROVAL: frozenset({CLOSED, IN_PROGRESS}),  # reviewer may reject back to in_progress
    CLOSED: frozenset(),
    CANCELLED: frozenset(),
}

# The permission required to *enter* a given status.
_TRANSITION_PERMISSION: Dict[str, str] = {
    IN_PROGRESS: "actions.update",       # executor records work
    PENDING_APPROVAL: "actions.update",  # executor submits for approval
    CLOSED: "actions.close",             # only Manager/Executive approve closure
    CANCELLED: "actions.update",
}


def can_transition(from_status: str, to_status: str) -> bool:
    """True iff moving from_status -> to_status is a legal state change."""
    return to_status in _TRANSITIONS.get(from_status, frozenset())


def required_permission(to_status: str) -> str:
    """Atomic permission needed to move an action into ``to_status``.

    Raises KeyError for a status that is never a transition target (open is only
    an initial state; use actions.create to create).
    """
    return _TRANSITION_PERMISSION[to_status]


def is_terminal(status: str) -> bool:
    return status in (CLOSED, CANCELLED)
