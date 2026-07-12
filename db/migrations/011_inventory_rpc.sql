BEGIN;

-- ── Migration 011: Atomic inventory operations (concurrency safety) ──
-- The stock balance is SUM(qty_delta) over the append-only ledger (009). A naive
-- client-side "read balance, then insert" is racy: two concurrent consumes can
-- both read the same balance and both insert, driving stock negative. These
-- Postgres functions make the check-and-insert atomic by taking a transaction-
-- level advisory lock keyed on (item, location) before summing and inserting, so
-- concurrent operations on the same stock serialize (Phase 5 exit gate).
-- Call via supabase-py: client.rpc("record_consumption", {...}). Backend still
-- enforces permission (inventory.consume) and org scope before calling.
-- Requires 009. Reversible: see 011_inventory_rpc_down.sql.

-- Consume: negative qty_delta. Fails if it would drive the (item, location)
-- balance below zero. Returns the new balance.
CREATE OR REPLACE FUNCTION public.record_consumption(
    p_org        UUID,
    p_item       UUID,
    p_location   UUID,
    p_qty        NUMERIC,          -- positive amount to consume
    p_batch      UUID DEFAULT NULL,
    p_actor      TEXT DEFAULT NULL,
    p_ref_site   UUID DEFAULT NULL,
    p_ref_asset  UUID DEFAULT NULL,
    p_ref_action UUID DEFAULT NULL,
    p_reason     TEXT DEFAULT NULL
) RETURNS NUMERIC AS $$
DECLARE
    v_balance NUMERIC;
BEGIN
    IF p_qty IS NULL OR p_qty <= 0 THEN
        RAISE EXCEPTION 'consume quantity must be positive';
    END IF;
    -- Serialize concurrent operations on this (item, location) for the txn.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_item::text || ':' || p_location::text, 0));
    SELECT COALESCE(SUM(qty_delta), 0) INTO v_balance
        FROM public.inventory_ledger
        WHERE item_id = p_item AND location_id = p_location;
    IF v_balance - p_qty < 0 THEN
        RAISE EXCEPTION 'insufficient stock: have %, need %', v_balance, p_qty
            USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO public.inventory_ledger(
        organization_id, item_id, batch_id, location_id, txn_type, qty_delta,
        reason, ref_site_id, ref_asset_id, ref_action_id, actor_clerk_id)
    VALUES (p_org, p_item, p_batch, p_location, 'consume', -p_qty,
            p_reason, p_ref_site, p_ref_asset, p_ref_action, p_actor);
    RETURN v_balance - p_qty;
END;
$$ LANGUAGE plpgsql;

-- Transfer: atomically move qty from one location to another (two ledger rows
-- sharing a transfer_group), checking the source can cover it.
CREATE OR REPLACE FUNCTION public.record_transfer(
    p_org      UUID,
    p_item     UUID,
    p_from     UUID,
    p_to       UUID,
    p_qty      NUMERIC,
    p_batch    UUID DEFAULT NULL,
    p_actor    TEXT DEFAULT NULL,
    p_reason   TEXT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_balance NUMERIC;
    v_group   UUID := gen_random_uuid();
BEGIN
    IF p_qty IS NULL OR p_qty <= 0 THEN
        RAISE EXCEPTION 'transfer quantity must be positive';
    END IF;
    IF p_from = p_to THEN
        RAISE EXCEPTION 'transfer source and destination must differ';
    END IF;
    -- Lock both endpoints in a stable order to avoid deadlocks.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_item::text || ':' || LEAST(p_from, p_to)::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended(p_item::text || ':' || GREATEST(p_from, p_to)::text, 0));
    SELECT COALESCE(SUM(qty_delta), 0) INTO v_balance
        FROM public.inventory_ledger
        WHERE item_id = p_item AND location_id = p_from;
    IF v_balance - p_qty < 0 THEN
        RAISE EXCEPTION 'insufficient stock at source: have %, need %', v_balance, p_qty
            USING ERRCODE = 'check_violation';
    END IF;
    INSERT INTO public.inventory_ledger(organization_id, item_id, batch_id, location_id,
        txn_type, qty_delta, reason, transfer_group, actor_clerk_id)
    VALUES
        (p_org, p_item, p_batch, p_from, 'transfer_out', -p_qty, p_reason, v_group, p_actor),
        (p_org, p_item, p_batch, p_to,   'transfer_in',   p_qty, p_reason, v_group, p_actor);
    RETURN v_group;
END;
$$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION public.record_consumption(
    UUID, UUID, UUID, NUMERIC, UUID, TEXT, UUID, UUID, UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.record_transfer(
    UUID, UUID, UUID, UUID, NUMERIC, UUID, TEXT, TEXT) TO service_role;

COMMIT;
