"""An unknown scope is not an empty scope, and admin scope has two halves.

Two defects surfaced by the L1 investigation of SECURITY_REVIEW_COMPLIANCE.md.
Neither is reachable today — both live behind SCOPE_ENFORCEMENT, which is off —
and both become live the instant that flag is turned on, which is precisely why
they are worth pinning now rather than discovering during a rollout.

  1. `get_assigned_site_ids` and `get_project_site_ids` swallowed every
     exception and returned []. Under enforcement, [] is a positive claim —
     "assigned to nothing", which denies every site. So a transient Supabase
     error or an unapplied migration 007 made a fully-assigned operator
     indistinguishable from an unassigned one: empty site list, empty
     obligations registry, no error anywhere. The user reads that as policy.
     The helpers now raise ScopeUnavailable and the endpoints answer 503.

     The distinction these tests exist to defend is the pair: a genuinely
     unassigned user must still resolve to the empty set, or "fail loudly"
     would just be a different way of being wrong.

  2. `_effective_site_ids` resolved admin through project assignments alone,
     while core/scope.py:resolve_site_scope defines admin as
     `project_site_ids | assigned_site_ids` and says so in its docstring. The
     dropped half is the only one with a working writer — PUT /users/{id}/sites
     — so an admin granted sites through the User Management "Sites" column
     resolved to nothing at all.

Style follows tests/test_invite_tenancy.py (monkeypatched query layer, endpoint
functions called directly with a fake profile; no network, no database).
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_server  # noqa: E402
import db.client as db_client  # noqa: E402
import db.queries as queries  # noqa: E402
from core.scope import ALL_SITES  # noqa: E402
from db.queries import ScopeUnavailable  # noqa: E402


def _profile(role: str) -> dict:
    return {"role": role, "user_id": "user_clerk_1", "organization_id": "org_1"}


def _patch_client(monkeypatch, client):
    """db/queries.py does `from .client import get_client`, so the name is bound
    into the queries module — patching db.client alone leaves these tests talking
    to the live stack and passing for the wrong reason. Patch both."""
    monkeypatch.setattr(queries, "get_client", lambda *a, **k: client)
    monkeypatch.setattr(db_client, "get_client", lambda *a, **k: client)


@pytest.fixture
def enforcing(monkeypatch):
    """Scope enforcement on — the only state in which any of this executes."""
    monkeypatch.setenv("SCOPE_ENFORCEMENT", "1")


# ── 1. unknown scope vs empty scope ───────────────────────────────────────────

class _BoomClient:
    """A configured client whose every query fails, as in an outage."""

    def table(self, _name):
        raise RuntimeError("connection reset by peer")


def test_unreadable_assignments_raise_rather_than_report_empty(monkeypatch):
    _patch_client(monkeypatch, _BoomClient())
    with pytest.raises(ScopeUnavailable):
        queries.get_assigned_site_ids("user_clerk_1", "org_1")
    with pytest.raises(ScopeUnavailable):
        queries.get_project_site_ids("user_clerk_1", "org_1")


def test_unconfigured_supabase_raises_rather_than_reporting_empty(monkeypatch):
    """No client is "cannot find out", not "assigned to nothing"."""
    _patch_client(monkeypatch, None)
    with pytest.raises(ScopeUnavailable):
        queries.get_assigned_site_ids("user_clerk_1", "org_1")
    with pytest.raises(ScopeUnavailable):
        queries.get_project_site_ids("user_clerk_1", "org_1")


def test_a_genuinely_unassigned_user_still_resolves_to_empty(monkeypatch, enforcing):
    """The other half of the distinction: no assignments is a real answer.

    If this failed, the fix would have replaced a silent denial with a blanket
    503 and told the caller just as little.
    """
    monkeypatch.setattr(queries, "get_assigned_site_ids", lambda *a: [])
    monkeypatch.setattr(queries, "get_project_site_ids", lambda *a: [])
    assert api_server._effective_site_ids(_profile("operator")) == frozenset()
    assert api_server._effective_site_ids(_profile("admin")) == frozenset()


def test_missing_identifiers_are_a_real_empty_not_a_failure(monkeypatch):
    """A profile with no org has nothing to resolve against — deny, don't 503."""
    _patch_client(monkeypatch, _BoomClient())
    assert queries.get_assigned_site_ids("", "org_1") == []
    assert queries.get_assigned_site_ids("user_clerk_1", "") == []
    assert queries.get_project_site_ids("", "org_1") == []
    assert queries.get_project_site_ids("user_clerk_1", "") == []


def test_no_projects_is_an_empty_not_a_failure(monkeypatch):
    """An admin on zero projects is a real state; only a failed READ raises."""
    class _NoRows:
        class _Q:
            def select(self, *a): return self
            def eq(self, *a): return self
            def in_(self, *a): return self
            def execute(self): return type("R", (), {"data": []})()

        def table(self, _name): return self._Q()

    _patch_client(monkeypatch, _NoRows())
    assert queries.get_project_site_ids("user_clerk_1", "org_1") == []


@pytest.mark.parametrize("role", ["operator", "admin"])
def test_scope_failure_surfaces_as_503(monkeypatch, enforcing, role):
    def _boom(*_a):
        raise ScopeUnavailable("tables unreadable")

    monkeypatch.setattr(queries, "get_assigned_site_ids", _boom)
    monkeypatch.setattr(queries, "get_project_site_ids", _boom)
    with pytest.raises(HTTPException) as exc:
        api_server._effective_site_ids(_profile(role))
    assert exc.value.status_code == 503


def test_scope_failure_does_not_widen_to_all_sites(monkeypatch, enforcing):
    """Failing closed matters more than failing loudly: never ALL_SITES."""
    def _boom(*_a):
        raise ScopeUnavailable("tables unreadable")

    monkeypatch.setattr(queries, "get_assigned_site_ids", _boom)
    monkeypatch.setattr(queries, "get_project_site_ids", _boom)
    for role in ("operator", "admin"):
        with pytest.raises(HTTPException):
            api_server._effective_site_ids(_profile(role))


def test_executive_and_gm_never_consult_the_assignment_tables(monkeypatch, enforcing):
    """super_admin/auditor short-circuit, so an outage must not 503 them."""
    def _boom(*_a):
        raise ScopeUnavailable("tables unreadable")

    monkeypatch.setattr(queries, "get_assigned_site_ids", _boom)
    monkeypatch.setattr(queries, "get_project_site_ids", _boom)
    assert api_server._effective_site_ids(_profile("super_admin")) == ALL_SITES
    assert api_server._effective_site_ids(_profile("auditor")) == ALL_SITES


def test_flag_off_is_unaffected_by_an_outage(monkeypatch):
    """With enforcement off nothing is consulted, so nothing can fail."""
    monkeypatch.delenv("SCOPE_ENFORCEMENT", raising=False)

    def _boom(*_a):
        raise ScopeUnavailable("tables unreadable")

    monkeypatch.setattr(queries, "get_assigned_site_ids", _boom)
    monkeypatch.setattr(queries, "get_project_site_ids", _boom)
    for role in ("operator", "admin", "auditor", "super_admin"):
        assert api_server._effective_site_ids(_profile(role)) == ALL_SITES


def test_admin_assignment_screen_503s_rather_than_showing_no_sites(monkeypatch):
    """GET /users/{id}/sites feeds the picker an admin assigns against.

    An empty list here does not merely mislead — it is the input to the next
    write, so "could not load" rendered as "assigned to nothing" invites an
    admin to reassign from a blank slate.
    """
    def _boom(*_a):
        raise ScopeUnavailable("tables unreadable")

    monkeypatch.setattr(queries, "list_user_site_assignments", _boom)
    monkeypatch.setattr(api_server, "_ensure_permission", lambda *a, **k: None)
    monkeypatch.setattr(api_server, "_resolve_target_clerk_id", lambda *a: "user_clerk_2")
    with pytest.raises(HTTPException) as exc:
        api_server.get_user_sites("user_2", profile=_profile("super_admin"))
    assert exc.value.status_code == 503


# ── 2. admin scope is projects AND direct assignments ─────────────────────────

def test_admin_keeps_directly_assigned_sites(monkeypatch, enforcing):
    """The defect: this resolved to frozenset() with no projects assigned.

    PUT /users/{id}/sites is the only assignment writer that exists, so before
    the fix the sole working mechanism did not apply to the admin role at all.
    """
    monkeypatch.setattr(queries, "get_project_site_ids", lambda *a: [])
    monkeypatch.setattr(queries, "get_assigned_site_ids", lambda *a: ["site_a", "site_b"])
    assert api_server._effective_site_ids(_profile("admin")) == frozenset({"site_a", "site_b"})


def test_admin_scope_is_the_union_of_both_halves(monkeypatch, enforcing):
    monkeypatch.setattr(queries, "get_project_site_ids", lambda *a: ["site_p"])
    monkeypatch.setattr(queries, "get_assigned_site_ids", lambda *a: ["site_a"])
    assert api_server._effective_site_ids(_profile("admin")) == frozenset({"site_p", "site_a"})


def test_admin_union_matches_core_scope(monkeypatch, enforcing):
    """api_server must not re-implement the rule core/scope.py already states."""
    from core.scope import resolve_site_scope
    monkeypatch.setattr(queries, "get_project_site_ids", lambda *a: ["site_p"])
    monkeypatch.setattr(queries, "get_assigned_site_ids", lambda *a: ["site_a"])
    assert api_server._effective_site_ids(_profile("admin")) == resolve_site_scope(
        "admin", project_site_ids=["site_p"], assigned_site_ids=["site_a"])


def test_operator_scope_ignores_project_assignments(monkeypatch, enforcing):
    """Widening admin must not have widened the Site Supervisor boundary too."""
    monkeypatch.setattr(queries, "get_project_site_ids", lambda *a: ["site_p"])
    monkeypatch.setattr(queries, "get_assigned_site_ids", lambda *a: ["site_a"])
    assert api_server._effective_site_ids(_profile("operator")) == frozenset({"site_a"})
