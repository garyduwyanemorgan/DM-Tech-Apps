BEGIN;

-- ── Rollback for Migration 012 ── restore the BEFORE UPDATE OR DELETE triggers.
DROP TRIGGER IF EXISTS audit_events_no_mutate ON public.audit_events;
CREATE TRIGGER audit_events_no_mutate
    BEFORE UPDATE OR DELETE ON public.audit_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

DROP TRIGGER IF EXISTS cae_no_mutate ON public.corrective_action_events;
CREATE TRIGGER cae_no_mutate
    BEFORE UPDATE OR DELETE ON public.corrective_action_events
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

DROP TRIGGER IF EXISTS inv_ledger_no_mutate ON public.inventory_ledger;
CREATE TRIGGER inv_ledger_no_mutate
    BEFORE UPDATE OR DELETE ON public.inventory_ledger
    FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

COMMIT;
