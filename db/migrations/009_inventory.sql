BEGIN;

-- ── Migration 009: Inventory & chemical control ──
-- Items, batches (expiry), storage locations, and an APPEND-ONLY stock ledger.
-- Stock balances are never stored mutably: a balance is SUM(qty_delta) over the
-- ledger for an (item, location[, batch]). Transfers are two linked rows
-- (transfer_out + transfer_in) sharing a transfer_group; corrections are
-- compensating 'adjust' rows — nothing is ever updated or deleted. This is what
-- keeps stock consistent under concurrency (PERMISSIONS_MATRIX.md rows 54-61,
-- exit gate for Phase 5). Requires 006 (reject_mutation). Run in Supabase SQL editor.
-- Financial fields (unit_cost, received_cost) are protected at the app layer:
-- only inventory.configure / inventory.valuation.read may see/set them.
-- Reversible: see 009_inventory_down.sql.

CREATE TABLE IF NOT EXISTS public.inventory_locations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id          UUID REFERENCES public.sites(id) ON DELETE SET NULL,
    kind             TEXT CHECK (kind IN ('warehouse','vehicle','site_store')),
    name             TEXT NOT NULL,
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, name)
);
CREATE INDEX IF NOT EXISTS inv_loc_org_idx ON public.inventory_locations (organization_id);

CREATE TABLE IF NOT EXISTS public.inventory_items (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id    UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    sku                TEXT,
    name               TEXT NOT NULL,
    unit               TEXT,               -- kg, L, ea …
    reorder_threshold  NUMERIC,
    unit_cost          NUMERIC,            -- financial: app-layer protected
    created_at         TIMESTAMPTZ DEFAULT now(),
    UNIQUE (organization_id, sku)
);
CREATE INDEX IF NOT EXISTS inv_item_org_idx ON public.inventory_items (organization_id);

CREATE TABLE IF NOT EXISTS public.inventory_batches (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id          UUID NOT NULL REFERENCES public.inventory_items(id) ON DELETE CASCADE,
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    batch_number     TEXT,
    expiry_date      DATE,
    received_cost    NUMERIC,             -- financial: app-layer protected
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (item_id, batch_number)
);
CREATE INDEX IF NOT EXISTS inv_batch_item_idx ON public.inventory_batches (item_id);
CREATE INDEX IF NOT EXISTS inv_batch_expiry_idx ON public.inventory_batches (expiry_date);

CREATE TABLE IF NOT EXISTS public.inventory_ledger (
    id               BIGSERIAL PRIMARY KEY,
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    item_id          UUID NOT NULL REFERENCES public.inventory_items(id) ON DELETE CASCADE,
    batch_id         UUID REFERENCES public.inventory_batches(id) ON DELETE SET NULL,
    location_id      UUID NOT NULL REFERENCES public.inventory_locations(id) ON DELETE CASCADE,
    txn_type         TEXT NOT NULL
                       CHECK (txn_type IN ('receive','consume','transfer_out','transfer_in','adjust')),
    qty_delta        NUMERIC NOT NULL,     -- signed: receive/transfer_in > 0, consume/transfer_out < 0
    reason           TEXT,
    ref_site_id      UUID REFERENCES public.sites(id) ON DELETE SET NULL,
    ref_asset_id     UUID,                 -- FK added in 010 if assets present
    ref_action_id    UUID REFERENCES public.corrective_actions(id) ON DELETE SET NULL,
    transfer_group   UUID,                 -- links the two legs of a transfer
    actor_clerk_id   TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS inv_ledger_scope_idx
    ON public.inventory_ledger (organization_id, item_id, location_id);
CREATE INDEX IF NOT EXISTS inv_ledger_batch_idx ON public.inventory_ledger (batch_id);
CREATE INDEX IF NOT EXISTS inv_ledger_transfer_idx ON public.inventory_ledger (transfer_group);

DROP TRIGGER IF EXISTS inv_ledger_no_mutate ON public.inventory_ledger;
CREATE TRIGGER inv_ledger_no_mutate
    BEFORE UPDATE OR DELETE ON public.inventory_ledger
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

ALTER TABLE public.inventory_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_ledger ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.inventory_locations TO service_role;
GRANT ALL ON public.inventory_items TO service_role;
GRANT ALL ON public.inventory_batches TO service_role;
GRANT SELECT, INSERT ON public.inventory_ledger TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.inventory_ledger_id_seq TO service_role;

COMMIT;
