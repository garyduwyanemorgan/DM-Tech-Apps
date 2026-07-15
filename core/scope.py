"""Data-scope resolution — the *where* half of authorization.

A permission answers *what* a role may do (core/authz.py); scope answers *where*.
Every authorization decision combines the two (PERMISSIONS_REVIEW_PACKAGE.md §7).
These functions are pure: they take the already-fetched assignment sets and return
the effective scope, so they unit-test without a database. The DB-backed wrappers
that load a user's assignments live in the query layer and stay behind the
SCOPE_ENFORCEMENT flag until every existing user is backfilled with assignments.
"""
from __future__ import annotations

from typing import FrozenSet, Iterable, Union

from core.authz import ROLE_ADMIN, ROLE_AUDITOR, ROLE_OPERATOR, ROLE_SUPER_ADMIN

# Sentinel meaning "every site in the organization" (org isolation still applies
# separately — this is scope *within* the already-resolved tenant).
ALL_SITES = "*"

SiteScope = Union[str, FrozenSet[str]]


def resolve_site_scope(
    role: str | None,
    *,
    assigned_site_ids: Iterable[str] = (),
    project_site_ids: Iterable[str] = (),
    portfolio_site_ids: Iterable[str] = (),
) -> SiteScope:
    """The set of site ids a role may act within, or ALL_SITES for org-wide.

    operator     -> explicitly assigned sites (Site Supervisor boundary)
    admin        -> sites of assigned projects/contracts, plus any directly
                    assigned sites (Project Managers routinely span sites, and
                    the User Management "Sites" column assigns sites directly)
    auditor      -> sites across the assigned portfolio/business-units (read-only GM)
    super_admin  -> ALL_SITES (Executive, org-wide)
    anything else (pending/unknown) -> empty (deny)
    """
    if role == ROLE_SUPER_ADMIN:
        return ALL_SITES
    if role == ROLE_AUDITOR:
        return frozenset(portfolio_site_ids)
    if role == ROLE_ADMIN:
        return frozenset(project_site_ids) | frozenset(assigned_site_ids)
    if role == ROLE_OPERATOR:
        return frozenset(assigned_site_ids)
    return frozenset()


def site_in_scope(scope: SiteScope, site_id: str) -> bool:
    """True iff ``site_id`` falls within a resolved site scope."""
    return scope == ALL_SITES or site_id in scope
