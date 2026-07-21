BEGIN;

-- ── Rollback for Migration 016 ────────────────────────────────────────────────
-- Drops every ingested laboratory report and its per-parameter results, plus the
-- raw_extraction forensic payload. Nothing else holds that data — `readings` was
-- never written to by the lab ingest — so archive the source PDFs first.
-- Reverse dependency order: results, then samples, then the guard function.

DROP POLICY IF EXISTS select_lab_results ON public.lab_results;
DROP POLICY IF EXISTS mutate_lab_results ON public.lab_results;
DROP POLICY IF EXISTS select_lab_samples ON public.lab_samples;
DROP POLICY IF EXISTS mutate_lab_samples ON public.lab_samples;

DROP TRIGGER IF EXISTS lab_samples_raw_extraction_immutable ON public.lab_samples;

DROP TABLE IF EXISTS public.lab_results;
DROP TABLE IF EXISTS public.lab_samples;

-- Only used by 016; unlike reject_mutation() it is not shared with other tables.
DROP FUNCTION IF EXISTS public.reject_raw_extraction_change();

COMMIT;
