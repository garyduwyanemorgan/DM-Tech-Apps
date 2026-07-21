BEGIN;

-- ── Rollback for Migration 017 ────────────────────────────────────────────────
-- Drops organisation-defined report types. Built-in types are unaffected — they
-- live in core/report_types.py, not here. Any lab_samples already recorded under
-- a custom type keep their stored report_type string; the type simply stops
-- being offered in the upload dropdown.

DROP POLICY IF EXISTS select_report_types ON public.report_types;
DROP POLICY IF EXISTS mutate_report_types ON public.report_types;

DROP TABLE IF EXISTS public.report_types;

COMMIT;
