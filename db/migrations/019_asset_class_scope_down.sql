BEGIN;

-- ── Rollback for Migration 019 ────────────────────────────────────────────────
-- Returns scope to the report-type level and removes the asset taxonomy columns.
-- Reversed in dependency order: the scope-requires-sampled constraint first (it
-- spans both columns), then the per-column checks and the index, then the
-- columns themselves.
--
-- Classification IS lost: asset_class and any scope set on an asset are dropped,
-- and re-applying 019 will backfill every row as 'equipment' again. Re-mark the
-- sampled assets by hand afterwards.

ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_scope_requires_sampled_check;
ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_scope_check;
ALTER TABLE public.assets DROP CONSTRAINT IF EXISTS assets_asset_class_check;

DROP INDEX IF EXISTS public.assets_org_class_idx;

ALTER TABLE public.assets
    DROP COLUMN IF EXISTS scope,
    DROP COLUMN IF EXISTS asset_class;

-- Restore report_types.scope as 017 defined it, minus NOT NULL: the column comes
-- back EMPTY (the one row that held 'facilities' was discarded by 019, and no
-- default could be invented without guessing a safety boundary), so a NOT NULL
-- re-add would either fail on the existing row or require a fabricated value.
-- Anything relying on this column must repopulate it before trusting it.
ALTER TABLE public.report_types
    ADD COLUMN IF NOT EXISTS scope TEXT;

ALTER TABLE public.report_types DROP CONSTRAINT IF EXISTS report_types_scope_check;
ALTER TABLE public.report_types
    ADD CONSTRAINT report_types_scope_check
    CHECK (scope IS NULL OR scope IN ('lagoon', 'facilities'));

COMMENT ON COLUMN public.report_types.scope IS
    'lagoon | facilities. Selects the specification set used to judge results. '
    'Never infer this from parameter names — the two scopes overlap, and judging '
    'a facilities sample against lagoon limits returns a confident wrong verdict.';

COMMIT;
