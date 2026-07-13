BEGIN;

-- ── Migration 013: decouple audit_events from organization lifecycle ──
-- audit_events.organization_id was a FK with ON DELETE SET NULL. Nulling the FK
-- on org deletion is an UPDATE, which the append-only guard (trigger + the
-- SELECT/INSERT-only grant) correctly forbids — so any org that has audit rows
-- cannot be deleted. An audit log should outlive the tenant it describes anyway,
-- so we drop the FK and keep organization_id as a plain (denormalised) column:
-- history is retained verbatim for forensics, and org deletion no longer touches
-- this table. Immutability (no UPDATE/DELETE) is unchanged. Idempotent.

ALTER TABLE public.audit_events
    DROP CONSTRAINT IF EXISTS audit_events_organization_id_fkey;

COMMIT;
