"""Characterization + fix tests for the auth resolver and report gate.

Covers CRIT-1 (fail-closed auth; no tenancy from client header) and CRIT-3
(final-report permission mapping). Runnable two ways:
    python tests/test_resolver_authz.py
    pytest tests/test_resolver_authz.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("PYTHONUTF8", "1")

from fastapi import HTTPException  # noqa: E402
import api_server  # noqa: E402
from core.authz import has_permission  # noqa: E402


def _call_resolver(credentials=None, x_org=None, x_email=None):
    """Invoke the dependency directly (bypassing FastAPI injection)."""
    return api_server.get_current_user_profile(
        credentials=credentials, x_organization_id=x_org, x_user_email=x_email
    )


def test_no_token_fails_closed_by_default():
    # CRIT-1: an unauthenticated request must NOT receive an operator identity
    # scoped to a client-supplied organization header.
    os.environ.pop("AUTHZ_FAIL_CLOSED", None)
    try:
        _call_resolver(credentials=None, x_org="victim-org-uuid")
        raise AssertionError("expected 401, got a profile")
    except HTTPException as e:
        assert e.status_code == 401, e.status_code


def test_escape_hatch_restores_legacy_operator():
    # AUTHZ_FAIL_CLOSED=0 is the documented rollback lever; it restores the old
    # anonymous behavior. This test pins that the lever works (and warns anyone
    # who removes it that they are changing rollout semantics).
    os.environ["AUTHZ_FAIL_CLOSED"] = "0"
    try:
        prof = _call_resolver(credentials=None, x_org="some-org")
        assert prof["role"] == "operator"
        assert prof["user_id"] is None
        assert prof["organization_id"] == "some-org"
    finally:
        os.environ.pop("AUTHZ_FAIL_CLOSED", None)


def test_report_permission_mapping():
    # CRIT-3: draft vs final map to distinct permissions.
    assert has_permission("operator", "reports.generate_draft")
    assert not has_permission("operator", "reports.approve_final")
    assert has_permission("admin", "reports.approve_final")


def _profile(role):
    return {"user_id": "u1", "role": role, "organization_id": "org1"}


def _denied(role, permission):
    """True iff _ensure_permission raises 403 for this role+permission."""
    try:
        api_server._ensure_permission(_profile(role), permission)
        return False
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
        return True


def test_ensure_permission_central_gate():
    # Behavior-preserving conversion: each endpoint's role tuple now maps to a
    # permission whose bundle matches. Spot-check both allow and deny sides.
    assert _denied("operator", "sites.create")          # was admin/super_admin only
    assert not _denied("admin", "sites.create")
    assert not _denied("super_admin", "sites.create")
    assert _denied("auditor", "sites.create")

    assert _denied("auditor", "readings.create")         # GM is read-only
    assert not _denied("operator", "readings.create")

    assert _denied("auditor", "sludge.write")
    assert not _denied("operator", "sludge.delete")      # current behavior (Q3 pending)

    assert _denied("operator", "billing.manage")
    assert not _denied("admin", "billing.manage")

    assert _denied("operator", "reports.approve_final")  # CRIT-3
    assert not _denied("auditor", "reports.approve_final")

    # executive-only grant
    assert _denied("admin", "users.executive.assign")
    assert not _denied("super_admin", "users.executive.assign")


def test_scope_enforcement_off_is_org_wide():
    # Default (flag off): every role sees the whole org — no behavior change.
    os.environ.pop("SCOPE_ENFORCEMENT", None)
    from core.scope import ALL_SITES
    for role in ("operator", "admin", "auditor", "super_admin"):
        assert api_server._effective_site_ids(_profile(role)) == ALL_SITES


def test_scope_enforcement_on_role_scoping():
    # Flag on: exec/GM stay org-wide; pending denies without consulting the DB.
    os.environ["SCOPE_ENFORCEMENT"] = "1"
    try:
        from core.scope import ALL_SITES
        assert api_server._effective_site_ids(_profile("super_admin")) == ALL_SITES
        assert api_server._effective_site_ids(_profile("auditor")) == ALL_SITES
        # pending/unknown never reaches the assignment tables — deny outright.
        assert api_server._effective_site_ids(_profile("pending")) == frozenset()
    finally:
        os.environ.pop("SCOPE_ENFORCEMENT", None)


def test_operator_with_unreadable_assignments_is_an_error_not_an_empty_scope():
    """This asserted the defect before it was fixed.

    With no database configured, get_assigned_site_ids used to swallow the
    failure and return [], so an operator resolved to the empty set — identical
    to a genuinely unassigned user. The caller saw an empty site list and an
    empty registry and had no way to tell an outage from a policy decision.
    It must now raise rather than answer.
    """
    from fastapi import HTTPException
    os.environ["SCOPE_ENFORCEMENT"] = "1"
    try:
        try:
            api_server._effective_site_ids(_profile("operator"))
        except HTTPException as exc:
            assert exc.status_code == 503
        else:
            raise AssertionError("an unreadable assignment table returned a scope")
    finally:
        os.environ.pop("SCOPE_ENFORCEMENT", None)


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
            except Exception as e:  # unexpected error surfaces loudly
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{'OK' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
