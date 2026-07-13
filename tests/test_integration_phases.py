"""End-to-end authorization + workflow integration tests (Phases 4-7).

Exercises the real endpoints (handlers called directly with synthetic role
profiles) against the configured Supabase database, then cleans up its test org.
SKIPS automatically when no DB is configured, so it is safe in CI without secrets.

    python tests/test_integration_phases.py     # runs if DB reachable, else SKIP

NOTE: full cleanup (deleting the test org) requires migration 012 to be applied
(the pre-012 append-only trigger blocks the cascade delete of ledger/event rows).
Until then the test still passes but leaves a 'ZZ_TEST_*' org behind.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYTHONUTF8", "1")

from fastapi import HTTPException  # noqa: E402


def _db():
    try:
        from db.client import get_client
        return get_client()
    except Exception:
        return None


def _code(fn, *a, **k):
    try:
        fn(*a, **k); return "OK"
    except HTTPException as e:
        return str(e.status_code)


def run() -> int:
    client = _db()
    if not client:
        print("SKIP: no database configured (secrets.toml/env absent).")
        return 0
    import api_server as api

    org = client.table("organizations").insert(
        {"name": f"ZZ_TEST_{uuid.uuid4().hex[:8]}"}).execute().data[0]["id"]

    def prof(role):
        return {"user_id": f"t-{role}", "role": role, "organization_id": org}

    R = []
    try:
        # ── Phase 4: corrective-action workflow + state machine ──
        R.append(("auditor cannot create action",
                  _code(api.create_action, api.CorrectiveActionCreate(title="x"), prof("auditor")) == "403"))
        aid = api.create_action(api.CorrectiveActionCreate(title="Fix"), prof("admin"))["action"]["id"]
        R.append(("open->closed illegal (409)",
                  _code(api.transition_action, aid, api.CorrectiveActionTransition(to_status="closed"), prof("admin")) == "409"))
        api.transition_action(aid, api.CorrectiveActionTransition(to_status="in_progress"), prof("operator"))
        api.transition_action(aid, api.CorrectiveActionTransition(to_status="pending_approval"), prof("operator"))
        R.append(("operator cannot close (403)",
                  _code(api.transition_action, aid, api.CorrectiveActionTransition(to_status="closed"), prof("operator")) == "403"))
        api.transition_action(aid, api.CorrectiveActionTransition(to_status="closed"), prof("admin"))
        R.append(("action closed by admin",
                  api.get_action(aid, prof("admin"))["action"]["status"] == "closed"))

        # ── Phase 5: inventory ledger + atomic RPC + financial protection ──
        item = api.create_inventory_item_endpoint(
            api.InventoryItemCreate(name="Cl", unit_cost=5.0, reorder_threshold=10), prof("admin"))["item"]
        L1 = api.create_inventory_location_endpoint(api.InventoryLocationCreate(name="WH"), prof("admin"))["location"]["id"]
        L2 = api.create_inventory_location_endpoint(api.InventoryLocationCreate(name="Truck"), prof("admin"))["location"]["id"]
        iid = item["id"]

        def bal(loc):
            for s in api.inventory_stock(item_id=iid, profile=prof("admin"))["stock"]:
                if s["location_id"] == loc:
                    return s["balance"]
            return 0.0

        R.append(("operator cannot configure (403)",
                  _code(api.create_inventory_item_endpoint, api.InventoryItemCreate(name="y"), prof("operator")) == "403"))
        R.append(("operator sees no cost",
                  all("unit_cost" not in it for it in api.inventory_items(prof("operator"))["items"])))
        api.inventory_receive(api.StockMove(item_id=iid, location_id=L1, qty=100), prof("admin"))
        api.inventory_consume(api.StockMove(item_id=iid, location_id=L1, qty=30), prof("operator"))
        R.append(("consume leaves 70", bal(L1) == 70))
        R.append(("no-negative: over-consume 409",
                  _code(api.inventory_consume, api.StockMove(item_id=iid, location_id=L1, qty=1000), prof("operator")) == "409"))
        api.inventory_transfer(api.StockTransfer(item_id=iid, from_location_id=L1, to_location_id=L2, qty=20), prof("admin"))
        R.append(("transfer conserves", bal(L1) == 50 and bal(L2) == 20))
        R.append(("operator cannot see valuation (403)",
                  _code(api.inventory_valuation, prof("operator")) == "403"))

        # ── Phase 6/7: assets + KPI tiers ──
        R.append(("operator cannot configure asset (403)",
                  _code(api.create_asset_endpoint, api.AssetCreate(name="Pump"), prof("operator")) == "403"))
        api.create_asset_endpoint(api.AssetCreate(name="Pump"), prof("admin"))
        R.append(("auditor views assets", len(api.list_assets_endpoint(profile=prof("auditor"))["assets"]) == 1))
        R.append(("operator cannot see portfolio KPI (403)",
                  _code(api.kpi_portfolio, prof("operator")) == "403"))
        exe = api.kpi_executive(prof("super_admin"))["kpi"]
        R.append(("executive KPI has valuation", "total_valuation" in exe["inventory"]))
    finally:
        # Best-effort cleanup (works once migration 012 is applied).
        try:
            client.table("organizations").delete().eq("id", org).execute()
            cleaned = True
        except Exception:
            cleaned = False

    failures = [n for n, ok in R if not ok]
    for n, ok in R:
        print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    print(f"cleanup: {'ok' if cleaned else 'DEFERRED (apply migration 012, then delete '+org+')'}")
    print("RESULT:", "ALL PASS" if not failures else f"{len(failures)} FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
