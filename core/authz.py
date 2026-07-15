"""Centralized authorization: atomic permission catalogue and role bundles.

This is the single source of truth for *what* each role may do. It deliberately
uses **explicit permission bundles**, never tier/ordinal comparisons — a higher
management role (e.g. General Manager / ``auditor``) may have broader *read*
scope yet *fewer* operational write permissions than ``admin``. Any ``tier >= N``
style check would get that inverted (see PERMISSIONS_MATRIX.md).

Permission = *what* a user may do. Scope (assigned org/project/site) = *where*,
and is enforced separately at the data layer. This module answers only "what".

Zero web-framework dependency so it is trivially unit-testable. The FastAPI glue
(a ``require(permission)`` dependency) lives in ``api_server.py``.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

# ── Roles ─────────────────────────────────────────────────────────────────────
# Database role -> business label (for reference / logging only; do NOT gate on
# labels). "pending" is a real state: an authenticated user with no org/role yet.
ROLE_OPERATOR = "operator"        # Site Supervisor
ROLE_ADMIN = "admin"              # Project / Contract Manager
ROLE_AUDITOR = "auditor"          # General Manager (read-only oversight)
ROLE_SUPER_ADMIN = "super_admin"  # Executive Management
ROLE_PENDING = "pending"          # authenticated, not yet provisioned into an org

KNOWN_ROLES: FrozenSet[str] = frozenset(
    {ROLE_OPERATOR, ROLE_ADMIN, ROLE_AUDITOR, ROLE_SUPER_ADMIN, ROLE_PENDING}
)

# ── Atomic permission catalogue (PERMISSIONS_MATRIX.md §"Recommended atomic
# permission catalogue"). Stable string keys; bundles reference these. ─────────
PERMISSIONS: FrozenSet[str] = frozenset({
    "sites.read", "sites.create", "sites.update", "sites.delete",
    "readings.read", "readings.create", "readings.overwrite",
    "reports.read", "reports.generate_draft", "reports.approve_final",
    "sludge.read", "sludge.write", "sludge.delete",
    "requests.read", "requests.create", "requests.fulfil",
    "actions.read", "actions.create", "actions.update", "actions.close",
    "inventory.read", "inventory.consume", "inventory.receive",
    "inventory.transfer", "inventory.adjust", "inventory.configure",
    "inventory.valuation.read",
    "assets.read", "assets.configure",
    "science.read", "science.simulate",
    "analytics.site.read", "analytics.project.read",
    "analytics.portfolio.read", "analytics.executive.read",
    "users.read", "users.invite", "users.role.assign",
    "users.executive.assign", "users.sites.assign", "users.remove",
    "billing.read", "billing.manage",
    "organization.configure", "audit.read", "permissions.configure",
    "demo.activate",
})

# ── Role -> permission bundle (PERMISSIONS_MATRIX.md permission map). ──────────
# Only permissions currently *enforceable* against existing features are wired to
# behavior today; the rest are declared so the catalogue is complete and future
# phases attach endpoints without re-deciding the matrix. Read-scope breadth
# (portfolio vs site) is a *scope* concern handled at the data layer, not here.
_OPERATOR: FrozenSet[str] = frozenset({
    "sites.read", "readings.read", "readings.create", "readings.overwrite",
    "reports.read", "reports.generate_draft",
    "sludge.read", "sludge.write",
    # NOTE: sludge.delete is granted to operator to match CURRENT behavior
    # (PERMISSIONS_MATRIX.md row 43 = "A" for Site Supervisor). The review
    # recommends tightening this to Manager+ (least privilege, open question Q3);
    # when approved that is a one-line move of "sludge.delete" up to _ADMIN.
    "sludge.delete",
    "requests.read", "requests.create", "requests.fulfil",
    "actions.read", "actions.create", "actions.update",
    "inventory.read", "inventory.consume",
    "assets.read", "science.read", "science.simulate",
    "analytics.site.read",
})
_ADMIN: FrozenSet[str] = _OPERATOR | frozenset({
    "sites.create", "sites.update", "sites.delete",
    "reports.approve_final",
    "actions.close",
    "inventory.receive", "inventory.transfer", "inventory.adjust", "inventory.configure",
    "assets.configure",
    "analytics.project.read",
    "users.read", "users.invite", "users.role.assign", "users.remove",
    "billing.read", "billing.manage",
    "audit.read",
})
_AUDITOR: FrozenSet[str] = frozenset({
    # General Manager: broad read/oversight, NO operational writes.
    "sites.read", "readings.read", "reports.read", "reports.approve_final",
    "sludge.read", "requests.read", "actions.read",
    "inventory.read", "inventory.valuation.read",
    "assets.read", "science.read", "science.simulate",
    "analytics.site.read", "analytics.project.read", "analytics.portfolio.read",
    "organization.configure", "audit.read",
})
_SUPER_ADMIN: FrozenSet[str] = (
    _ADMIN | _AUDITOR | frozenset({
        "users.executive.assign",
        # Site assignments decide what each user can work on — Executive
        # Management only (Project Managers may read them, not change them).
        "users.sites.assign",
        "inventory.valuation.read",
        "analytics.portfolio.read", "analytics.executive.read",
        "organization.configure", "permissions.configure",
        # Starting the org's one-month demo is an org-level commitment.
        "demo.activate",
    })
)

ROLE_BUNDLES: Dict[str, FrozenSet[str]] = {
    ROLE_OPERATOR: _OPERATOR,
    ROLE_ADMIN: _ADMIN,
    ROLE_AUDITOR: _AUDITOR,
    ROLE_SUPER_ADMIN: _SUPER_ADMIN,
    ROLE_PENDING: frozenset(),  # a pending user can do nothing until provisioned
}


def has_permission(role: str | None, permission: str) -> bool:
    """True iff ``role`` (a database role string) is granted ``permission``.

    Fails closed: an unknown/None role, or an unknown permission key, is denied.
    """
    if permission not in PERMISSIONS:
        # Guard against typos silently granting access.
        return False
    return permission in ROLE_BUNDLES.get(role or "", frozenset())


def permissions_for(role: str | None) -> FrozenSet[str]:
    """The full permission set for a role (empty for unknown/pending)."""
    return ROLE_BUNDLES.get(role or "", frozenset())
