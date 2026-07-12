-- ── Rollback for Migration 006 ──
-- Drops the audit_events table. The reject_mutation() helper is shared with later
-- migrations, so it is only dropped if nothing else uses it (run last).
DROP TRIGGER IF EXISTS audit_events_no_mutate ON public.audit_events;
DROP TABLE IF EXISTS public.audit_events;
-- Only drop the shared guard if no append-only tables remain (008/009 also use it).
-- DROP FUNCTION IF EXISTS public.reject_mutation();
