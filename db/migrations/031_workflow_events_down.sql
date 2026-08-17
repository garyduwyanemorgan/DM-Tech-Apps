BEGIN;

-- ── Rollback for Migration 031 ──
-- Drops the workflow_events table and its read policy. The reject_mutation()
-- helper is shared with earlier migrations (006, 008, 009), so it is not
-- dropped here.
DROP POLICY IF EXISTS select_workflow_events ON public.workflow_events;
DROP TRIGGER IF EXISTS workflow_events_no_mutate ON public.workflow_events;
DROP TABLE IF EXISTS public.workflow_events;
-- Only drop the shared guard if no append-only tables remain.
-- DROP FUNCTION IF EXISTS public.reject_mutation();

COMMIT;
