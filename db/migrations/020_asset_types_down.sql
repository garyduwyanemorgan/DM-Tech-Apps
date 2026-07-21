BEGIN;

-- ── Rollback for Migration 020 ────────────────────────────────────────────────
-- Drops organisation-defined asset types. Assets created under them are NOT
-- affected: they store asset_type/asset_class/scope by value, so they keep
-- working — the type simply stops being offered when creating new ones.

DROP POLICY IF EXISTS select_asset_types ON public.asset_types;
DROP POLICY IF EXISTS mutate_asset_types ON public.asset_types;
DROP TABLE IF EXISTS public.asset_types;

COMMIT;
