BEGIN;

-- ── Rollback for Migration 023 ────────────────────────────────────────────────
-- Drops the laboratories registry, the module catalogue, entitlements, the
-- obligation registry and the certificate table.
--
-- LOSSY, AND UNLIKE 022 NOT RECOVERABLY SO. 022 could promise that its content
-- was reproducible from a Python seeder. Nothing here is. Every one of these
-- tables holds facts that exist nowhere else in the repo:
--
--   * organization_entitlements — WHAT EACH CLIENT IS PAYING FOR. This is the
--     billing record. Losing it loses the invoice basis and, because of the
--     governing rule in §4.5, the definition of what the app was watching.
--   * obligations — the compliance registry, including every event-triggered
--     obligation transcribed by hand from a guideline, and last_satisfied_*
--     evidence links that cannot be recomputed once the pointers are gone.
--   * certificates — third-party evidence with forensic provenance
--     (source_sha256, raw_extraction). §7.5 says evidence is never deleted as a
--     side effect. Running this file IS that deletion, done deliberately.
--   * laboratories — accreditation windows and their verified_by / verified_on
--     provenance, transcribed from DM's published record.
--
-- EXPORT ALL FIVE TABLES BEFORE RUNNING THIS. Rolling back 023 on a database
-- that has been in use is destroying the client's compliance history, not
-- undoing a schema change. If the intent is merely to stop monitoring a module,
-- set organization_entitlements.active_until instead — that is what it is for.
--
-- ORDERING: children before parents, so each DROP stands on its own rather than
-- relying on cascade behaviour to be correct.
--   obligations first — it holds the composite FK to organization_entitlements
--     (ON DELETE RESTRICT) and references assets, standards and
--     specification_sets, all of which outlive this migration.
--   certificates next — it references laboratories ON DELETE RESTRICT.
--   then organization_entitlements → guideline_modules → laboratories.
-- The RESTRICTs are what force this order; they are doing their job right up to
-- the moment the table itself disappears.
--
-- NOTE ON POLICIES. There are deliberately no DROP POLICY statements here, for
-- the reason 022_down sets out: policies, indexes and constraints are dropped
-- with their table, and `DROP POLICY IF EXISTS p ON t` tolerates a missing
-- POLICY but not a missing TABLE — against an absent table it raises 42P01,
-- which inside this BEGIN…COMMIT aborts the entire rollback including the DROP
-- TABLEs that would have cleaned up. That failure lands in exactly the
-- partial-state case such statements appear to protect against.

-- Dropped before the table it reads. The dependency is not tracked by Postgres
-- (a SQL function body is not a hard dependency the way a view is), so a
-- surviving function over a dropped table would fail only when next called —
-- and it is called from the accreditation gate, where a runtime error is a
-- rejected report.
DROP FUNCTION IF EXISTS public.laboratory_accredited_on(UUID, DATE, TEXT);

DROP TABLE IF EXISTS public.obligations;
DROP TABLE IF EXISTS public.certificates;
DROP TABLE IF EXISTS public.organization_entitlements;
DROP TABLE IF EXISTS public.guideline_modules;
DROP TABLE IF EXISTS public.laboratories;

COMMIT;
