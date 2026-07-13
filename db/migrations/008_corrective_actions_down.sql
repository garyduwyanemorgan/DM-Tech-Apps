BEGIN;

-- ── Rollback for Migration 008 ──
DROP TRIGGER IF EXISTS cae_no_mutate ON public.corrective_action_events;
DROP TABLE IF EXISTS public.corrective_action_events;
DROP TABLE IF EXISTS public.corrective_actions;

COMMIT;
