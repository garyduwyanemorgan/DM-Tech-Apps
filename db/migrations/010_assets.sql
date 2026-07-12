-- ── Migration 010: Asset & maintenance configuration ──
-- Asset types/equipment, inspection checklists, required lab parameters, and
-- maintenance schedules (PERMISSIONS_MATRIX.md row 50). Managers/Executive
-- configure within scope; General Managers view; Site Supervisors execute
-- generated tasks without changing templates. Requires 007 (sites). Run in
-- Supabase SQL editor. Reversible: see 010_assets_down.sql.

CREATE TABLE IF NOT EXISTS public.assets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id          UUID REFERENCES public.sites(id) ON DELETE CASCADE,
    asset_type       TEXT,                 -- pump / filter / dosing / water_body …
    name             TEXT NOT NULL,
    config           JSONB,                -- checklist, required lab params, thresholds
    created_at       TIMESTAMPTZ DEFAULT now(),
    UNIQUE (site_id, name)
);
CREATE INDEX IF NOT EXISTS assets_org_site_idx ON public.assets (organization_id, site_id);

CREATE TABLE IF NOT EXISTS public.maintenance_schedules (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    asset_id         UUID NOT NULL REFERENCES public.assets(id) ON DELETE CASCADE,
    checklist        JSONB,
    interval_days    INT,
    next_due         DATE,
    created_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS maint_asset_idx ON public.maintenance_schedules (asset_id);
CREATE INDEX IF NOT EXISTS maint_next_due_idx ON public.maintenance_schedules (next_due);

-- Now that assets exist, link the inventory ledger's optional asset reference
-- (declared UUID-only in 009 to avoid an ordering dependency).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'inventory_ledger_ref_asset_fk'
    ) THEN
        ALTER TABLE public.inventory_ledger
            ADD CONSTRAINT inventory_ledger_ref_asset_fk
            FOREIGN KEY (ref_asset_id) REFERENCES public.assets(id) ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_schedules ENABLE ROW LEVEL SECURITY;
GRANT ALL ON public.assets TO service_role;
GRANT ALL ON public.maintenance_schedules TO service_role;
