BEGIN;

-- ── Migration 012: append-only triggers block UPDATE only (not DELETE) ──
-- 006/008/009 created BEFORE UPDATE OR DELETE triggers. The DELETE half also
-- fires on CASCADE deletes, making parent rows undeletable: deleting a corrective
-- action (or a whole organization, which cascades down) fails because the child
-- event/ledger rows cannot be deleted. That breaks tenant offboarding and normal
-- admin cleanup. Recorded history still must not be *altered*, so we keep the
-- UPDATE guard and drop the DELETE guard. Only service_role can reach these
-- tables, and a full-parent delete is an administrative action, not tampering.
-- Idempotent; safe to run on the already-migrated database.

DROP TRIGGER IF EXISTS audit_events_no_mutate ON public.audit_events;
CREATE TRIGGER audit_events_no_mutate
    BEFORE UPDATE ON public.audit_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

DROP TRIGGER IF EXISTS cae_no_mutate ON public.corrective_action_events;
CREATE TRIGGER cae_no_mutate
    BEFORE UPDATE ON public.corrective_action_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

DROP TRIGGER IF EXISTS inv_ledger_no_mutate ON public.inventory_ledger;
CREATE TRIGGER inv_ledger_no_mutate
    BEFORE UPDATE ON public.inventory_ledger
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

COMMIT;
