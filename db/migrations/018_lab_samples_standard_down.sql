BEGIN;

-- ── Rollback for Migration 018 ────────────────────────────────────────────────
-- Drops the governing-standard columns. The citations are NOT lost: they remain
-- in each row's raw_extraction blob, which 016 makes immutable. Re-applying 018
-- and re-ingesting would restore them as queryable columns.

ALTER TABLE public.lab_samples DROP CONSTRAINT IF EXISTS lab_samples_overall_status_check;
DROP INDEX IF EXISTS public.lab_samples_standard_idx;

ALTER TABLE public.lab_samples
    DROP COLUMN IF EXISTS standard_code,
    DROP COLUMN IF EXISTS standard_title,
    DROP COLUMN IF EXISTS standard_year,
    DROP COLUMN IF EXISTS standard_authority,
    DROP COLUMN IF EXISTS standard_citation,
    DROP COLUMN IF EXISTS additional_standards,
    DROP COLUMN IF EXISTS test_procedure,
    DROP COLUMN IF EXISTS medium_used,
    DROP COLUMN IF EXISTS detection_limit,
    DROP COLUMN IF EXISTS filtered_volume,
    DROP COLUMN IF EXISTS overall_status;

COMMIT;
