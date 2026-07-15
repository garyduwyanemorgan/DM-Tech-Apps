"""Unit tests for the atomic permission catalogue and role bundles.

Pure — no web framework, DB, or env required. Runnable two ways:
    python tests/test_authz.py      # zero dependencies
    pytest tests/test_authz.py      # once pytest is installed
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.authz import (  # noqa: E402
    PERMISSIONS,
    ROLE_BUNDLES,
    has_permission,
    permissions_for,
)


def test_report_final_requires_manager_or_above():
    assert has_permission("admin", "reports.approve_final")
    assert has_permission("auditor", "reports.approve_final")       # GM may sign off / view final
    assert has_permission("super_admin", "reports.approve_final")
    assert not has_permission("operator", "reports.approve_final")  # Site Supervisor may not


def test_operator_can_draft_but_not_finalize():
    assert has_permission("operator", "reports.generate_draft")
    assert not has_permission("operator", "reports.approve_final")


def test_auditor_is_read_only_no_operational_writes():
    # General Manager: broad read, but no operational mutations.
    for write_perm in ("readings.create", "readings.overwrite", "sludge.write",
                       "sludge.delete", "requests.create", "sites.create"):
        assert not has_permission("auditor", write_perm), write_perm
    # ...yet retains oversight reads.
    for read_perm in ("readings.read", "reports.read", "analytics.portfolio.read",
                      "inventory.valuation.read", "audit.read"):
        assert has_permission("auditor", read_perm), read_perm


def test_sludge_delete_current_behavior():
    # Pins CURRENT behavior: matrix row 43 grants operator sludge.delete ("A").
    # The recommended least-privilege tightening (Manager+) is open question Q3,
    # deferred to Phase 3. When approved, flip these operator assertions.
    assert has_permission("operator", "sludge.delete")
    assert has_permission("admin", "sludge.delete")
    assert has_permission("super_admin", "sludge.delete")
    assert not has_permission("auditor", "sludge.delete")  # GM is read-only


def test_billing_read_starts_at_manager_tier():
    # M1: subscription/financial visibility begins at Project/Contract Manager.
    assert has_permission("admin", "billing.read")
    assert has_permission("super_admin", "billing.read")
    assert not has_permission("operator", "billing.read")
    assert not has_permission("auditor", "billing.read")  # GM does not see billing


def test_extract_excludes_auditor():
    # M5: uploading/extracting a lab report is a data-entry action.
    assert has_permission("operator", "readings.create")
    assert has_permission("admin", "readings.create")
    assert not has_permission("auditor", "readings.create")


def test_executive_only_permissions():
    for exec_perm in ("users.executive.assign", "users.sites.assign",
                      "analytics.executive.read", "permissions.configure",
                      "demo.activate"):
        assert has_permission("super_admin", exec_perm), exec_perm
        assert not has_permission("admin", exec_perm), exec_perm
        assert not has_permission("auditor", exec_perm), exec_perm


def test_fails_closed():
    assert not has_permission(None, "sites.read")
    assert not has_permission("", "sites.read")
    assert not has_permission("pending", "sites.read")          # authenticated but unprovisioned
    assert not has_permission("nonsense-role", "sites.read")
    assert not has_permission("operator", "typo.permission")    # unknown key denied
    assert permissions_for("pending") == frozenset()
    assert permissions_for(None) == frozenset()


def test_bundles_reference_only_real_permissions():
    for role, bundle in ROLE_BUNDLES.items():
        unknown = bundle - PERMISSIONS
        assert not unknown, f"{role} references unknown permissions: {unknown}"


def test_super_admin_superset_of_admin():
    # Executive Management can do everything a Project Manager can (plus more).
    assert ROLE_BUNDLES["admin"] <= ROLE_BUNDLES["super_admin"]


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
    print(f"\n{'OK' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
