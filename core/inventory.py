"""Pure inventory-ledger logic — the invariants that keep stock consistent.

The database stores an APPEND-ONLY ledger (db/migrations/009_inventory.sql); a
balance is the sum of signed ``qty_delta`` rows for a scope. These helpers compute
balances and validate operations *before* rows are written, so the rules that must
never break — no negative stock, transfers conserve quantity — are unit-tested
here without a database. Money is deliberately absent from this module; valuation
is computed elsewhere and gated by inventory.valuation.read.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

Number = Decimal


def _d(x: Any) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def balance(
    ledger_rows: Iterable[Dict[str, Any]],
    *,
    item_id: Optional[str] = None,
    location_id: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> Decimal:
    """Current stock = sum of qty_delta over ledger rows matching the given filters.

    Filters are optional and combined with AND; omit one to aggregate across it
    (e.g. omit ``location_id`` for an item's total across all locations).
    """
    total = Decimal(0)
    for r in ledger_rows:
        if item_id is not None and r.get("item_id") != item_id:
            continue
        if location_id is not None and r.get("location_id") != location_id:
            continue
        if batch_id is not None and r.get("batch_id") != batch_id:
            continue
        total += _d(r.get("qty_delta", 0))
    return total


def validate_consume(current_balance: Any, qty: Any) -> None:
    """A consume/transfer-out of ``qty`` must be positive and not exceed stock.

    Raises ValueError on violation; returns None when the operation is valid.
    Callers hold a row lock / serialize on the (item, location) scope so the
    check-then-insert is atomic (Phase 5 exit gate: no inconsistency under
    concurrency).
    """
    q = _d(qty)
    if q <= 0:
        raise ValueError("consume quantity must be positive")
    if _d(current_balance) - q < 0:
        raise ValueError("insufficient stock: consume would drive the balance negative")


def build_transfer(
    *,
    organization_id: str,
    item_id: str,
    from_location_id: str,
    to_location_id: str,
    qty: Any,
    from_balance: Any,
    batch_id: Optional[str] = None,
    actor_clerk_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build the two conserving ledger rows for a stock transfer.

    Returns [transfer_out (negative at source), transfer_in (positive at dest)]
    sharing a ``transfer_group`` so the legs are reconcilable and the net effect on
    total stock is zero. Validates the source has enough and the locations differ.
    """
    q = _d(qty)
    if from_location_id == to_location_id:
        raise ValueError("transfer source and destination must differ")
    validate_consume(from_balance, q)  # source must cover the move
    group = str(uuid.uuid4())
    common = {
        "organization_id": organization_id,
        "item_id": item_id,
        "batch_id": batch_id,
        "transfer_group": group,
        "actor_clerk_id": actor_clerk_id,
        "reason": reason,
    }
    return [
        {**common, "location_id": from_location_id, "txn_type": "transfer_out", "qty_delta": -q},
        {**common, "location_id": to_location_id, "txn_type": "transfer_in", "qty_delta": q},
    ]


def is_low_stock(current_balance: Any, reorder_threshold: Any) -> bool:
    if reorder_threshold is None:
        return False
    return _d(current_balance) <= _d(reorder_threshold)
