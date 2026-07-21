BEGIN;

-- ── Rollback for Migration 021 ────────────────────────────────────────────────
-- Drops the recorded asset type. The certificate itself is unaffected: the
-- verdicts already computed remain, and the verbatim source stays in
-- raw_extraction. Only the ability to report "all certificates about water tanks"
-- is lost.

DROP INDEX IF EXISTS public.lab_samples_asset_type_idx;
ALTER TABLE public.lab_samples DROP COLUMN IF EXISTS asset_type;

COMMIT;
