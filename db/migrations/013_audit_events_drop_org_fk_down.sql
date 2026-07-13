BEGIN;

-- ── Rollback for Migration 013 ── restore the FK (ON DELETE SET NULL).
-- NOTE: this reintroduces the "org with audit rows cannot be deleted" limitation.
-- Requires that no audit_events.organization_id value references a missing org
-- (dangling ids created while the FK was absent must be cleaned first).
ALTER TABLE public.audit_events
    ADD CONSTRAINT audit_events_organization_id_fkey
    FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;

COMMIT;
