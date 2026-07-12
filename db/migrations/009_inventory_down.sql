-- ── Rollback for Migration 009 ──
DROP TRIGGER IF EXISTS inv_ledger_no_mutate ON public.inventory_ledger;
DROP TABLE IF EXISTS public.inventory_ledger;
DROP TABLE IF EXISTS public.inventory_batches;
DROP TABLE IF EXISTS public.inventory_items;
DROP TABLE IF EXISTS public.inventory_locations;
