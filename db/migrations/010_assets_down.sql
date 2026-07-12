-- ── Rollback for Migration 010 ──
ALTER TABLE public.inventory_ledger DROP CONSTRAINT IF EXISTS inventory_ledger_ref_asset_fk;
DROP TABLE IF EXISTS public.maintenance_schedules;
DROP TABLE IF EXISTS public.assets;
