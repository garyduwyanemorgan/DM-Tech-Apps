"""Unit tests for the pure domain invariants: scope, inventory ledger, and the
corrective-action state machine. No DB required. Run:
    python tests/test_domain_logic.py   |   pytest tests/test_domain_logic.py
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import corrective, inventory, scope  # noqa: E402


# ── scope ─────────────────────────────────────────────────────────────────────
def test_operator_scope_is_assigned_sites_only():
    s = scope.resolve_site_scope("operator", assigned_site_ids=["s1", "s2"],
                                 project_site_ids=["s3"], portfolio_site_ids=["s4"])
    assert s == frozenset({"s1", "s2"})
    assert scope.site_in_scope(s, "s1")
    assert not scope.site_in_scope(s, "s3")   # a project site they are not assigned


def test_admin_scope_is_project_sites():
    s = scope.resolve_site_scope("admin", project_site_ids=["p1", "p2"])
    assert s == frozenset({"p1", "p2"})
    assert not scope.site_in_scope(s, "other")


def test_super_admin_scope_is_all():
    s = scope.resolve_site_scope("super_admin", assigned_site_ids=[])
    assert s == scope.ALL_SITES
    assert scope.site_in_scope(s, "anything")


def test_unknown_or_pending_scope_denies():
    assert scope.resolve_site_scope("pending") == frozenset()
    assert not scope.site_in_scope(scope.resolve_site_scope(None), "s1")


# ── inventory ledger ───────────────────────────────────────────────────────────
def _ledger():
    return [
        {"item_id": "i1", "location_id": "L1", "batch_id": "b1", "qty_delta": 100},
        {"item_id": "i1", "location_id": "L1", "batch_id": "b1", "qty_delta": -30},
        {"item_id": "i1", "location_id": "L2", "batch_id": "b1", "qty_delta": 10},
        {"item_id": "i2", "location_id": "L1", "batch_id": None, "qty_delta": 5},
    ]


def test_balance_filters_and_sums():
    assert inventory.balance(_ledger(), item_id="i1", location_id="L1") == Decimal(70)
    assert inventory.balance(_ledger(), item_id="i1") == Decimal(80)   # across locations
    assert inventory.balance(_ledger(), item_id="i2") == Decimal(5)


def test_consume_cannot_go_negative():
    inventory.validate_consume(70, 70)          # exact is fine
    try:
        inventory.validate_consume(70, 71)
        raise AssertionError("expected ValueError for oversized consume")
    except ValueError:
        pass
    for bad in (0, -5):
        try:
            inventory.validate_consume(70, bad)
            raise AssertionError("expected ValueError for non-positive consume")
        except ValueError:
            pass


def test_transfer_conserves_quantity_and_links_legs():
    rows = inventory.build_transfer(
        organization_id="org1", item_id="i1", from_location_id="L1",
        to_location_id="L2", qty=25, from_balance=70, batch_id="b1",
    )
    assert len(rows) == 2
    assert sum(r["qty_delta"] for r in rows) == 0            # conserved
    assert rows[0]["txn_type"] == "transfer_out" and rows[0]["qty_delta"] == Decimal(-25)
    assert rows[1]["txn_type"] == "transfer_in" and rows[1]["qty_delta"] == Decimal(25)
    assert rows[0]["transfer_group"] == rows[1]["transfer_group"]  # reconcilable


def test_transfer_rejects_insufficient_and_same_location():
    try:
        inventory.build_transfer(organization_id="o", item_id="i1", from_location_id="L1",
                                 to_location_id="L2", qty=999, from_balance=70)
        raise AssertionError("expected ValueError for insufficient stock")
    except ValueError:
        pass
    try:
        inventory.build_transfer(organization_id="o", item_id="i1", from_location_id="L1",
                                 to_location_id="L1", qty=5, from_balance=70)
        raise AssertionError("expected ValueError for same-location transfer")
    except ValueError:
        pass


def test_low_stock():
    assert inventory.is_low_stock(5, 10)
    assert inventory.is_low_stock(10, 10)
    assert not inventory.is_low_stock(11, 10)
    assert not inventory.is_low_stock(0, None)


# ── corrective-action state machine ────────────────────────────────────────────
def test_valid_transitions():
    assert corrective.can_transition("open", "in_progress")
    assert corrective.can_transition("in_progress", "pending_approval")
    assert corrective.can_transition("pending_approval", "closed")
    assert corrective.can_transition("pending_approval", "in_progress")  # reject back


def test_invalid_transitions_blocked():
    assert not corrective.can_transition("open", "closed")          # cannot skip approval
    assert not corrective.can_transition("closed", "in_progress")   # terminal
    assert not corrective.can_transition("cancelled", "open")       # terminal
    assert corrective.is_terminal("closed") and corrective.is_terminal("cancelled")


def test_closure_requires_actions_close():
    assert corrective.required_permission("closed") == "actions.close"
    assert corrective.required_permission("in_progress") == "actions.update"


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
            except Exception as e:
                failures += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{'OK' if not failures else str(failures) + ' FAILED'}")
    sys.exit(1 if failures else 0)
