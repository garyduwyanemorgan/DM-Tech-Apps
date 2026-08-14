BEGIN;

-- ── Rollback for Migration 024 ────────────────────────────────────────────────
-- Drops the checklist library, the inspection tables and the risk-assessment
-- register, and reverts the two columns and four widened CHECK constraints that
-- 024 applied to tables created by 022 and 023.
--
-- LOSSY, IN TWO DIFFERENT WAYS, AND THE SECOND IS THE DANGEROUS ONE.
--
--   * checklist_templates / checklist_items / severity_scales /
--     severity_scale_values are transcribed reference content. They are
--     recoverable in principle — data/dm_guidelines/*.json holds the
--     extractions — but only through a loader, and the mapping from those files
--     to these tables lives nowhere else.
--   * inspections / inspection_findings / risk_assessments /
--     risk_assessment_entries ARE COMPLIANCE EVIDENCE and are recoverable from
--     nothing. A finding is a record that a named person walked a named
--     building on a named date and recorded what they saw; a risk-assessment
--     entry is a hazard a duty-holder signed their name against. §7.5 says
--     evidence is never deleted as a side effect. Running this file IS that
--     deletion, done deliberately.
--
-- EXPORT ALL EIGHT TABLES BEFORE RUNNING THIS.
--
-- IT MAY ALSO FAIL, ON PURPOSE. Restoring 023's cadence rule re-adds a CHECK
-- that a self-declared-review obligation cannot satisfy: such a row has no
-- cadence and no trigger_event, which is exactly what 023 forbade before GU137
-- was read. If any GU137 obligation exists, the ADD CONSTRAINT below aborts the
-- whole rollback and names the constraint. That is the correct outcome — the
-- alternative is silently dropping the column and leaving rows that will never
-- become due, which is the invisible-gap failure the obligations table exists to
-- eliminate. Resolve those obligations first (delete them, or give them a
-- cadence somebody can defend), then re-run.
--
-- standards.lifecycle_status is dropped outright. Every editorial judgement
-- about whether a guideline is still in force is lost with it, including the
-- GU93 determination that §7.13 exists to record.
--
-- ORDERING: children before parents, so each DROP stands on its own rather than
-- relying on cascade behaviour to be correct. The RESTRICTs are what force the
-- order and they are doing their job right up to the moment the table itself
-- disappears.
--   risk_assessment_entries → risk_assessments (entries hold the composite FK)
--   inspection_findings → inspections (findings reference checklist_items and
--     corrective_actions ON DELETE RESTRICT; corrective_actions outlives this)
--   then checklist_items → checklist_templates, which must follow the findings
--     because of that RESTRICT, and severity_scale_values → severity_scales,
--     which must follow the items for the same reason.
--
-- NOTE ON POLICIES. There are deliberately no DROP POLICY statements here, for
-- the reason 022_down and 023_down set out: policies, indexes and constraints
-- are dropped with their table, and `DROP POLICY IF EXISTS p ON t` tolerates a
-- missing POLICY but not a missing TABLE — against an absent table it raises
-- 42P01, which inside this BEGIN…COMMIT aborts the entire rollback including
-- the DROP TABLEs that would have cleaned up. That failure lands in exactly the
-- partial-state case such statements appear to protect against.

DROP TABLE IF EXISTS public.risk_assessment_entries;
DROP TABLE IF EXISTS public.risk_assessments;
DROP TABLE IF EXISTS public.inspection_findings;
DROP TABLE IF EXISTS public.inspections;
DROP TABLE IF EXISTS public.checklist_items;
DROP TABLE IF EXISTS public.checklist_templates;
DROP TABLE IF EXISTS public.severity_scale_values;
DROP TABLE IF EXISTS public.severity_scales;

-- ── Revert the 022 column ────────────────────────────────────────────────────
ALTER TABLE public.standards DROP CONSTRAINT IF EXISTS standards_lifecycle_status_check;
DROP INDEX IF EXISTS public.standards_lifecycle_idx;
ALTER TABLE public.standards DROP COLUMN IF EXISTS lifecycle_status;

-- ── Revert the 023 column and the widened vocabularies ───────────────────────
-- Order matters: the cadence CHECK must be restored to its 023 wording BEFORE
-- the column it references is dropped, or the restored constraint would be
-- written against a column that no longer exists. Restoring it first is also
-- what makes the failure described in the header land loudly rather than after
-- the column has already gone.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_cadence_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_cadence_check
    CHECK (
        (
            (cadence_months IS NOT NULL OR cadence_days IS NOT NULL)
            AND coalesce(btrim(trigger_event), '') = ''
        )
        OR
        (
            cadence_months IS NULL AND cadence_days IS NULL
            AND coalesce(btrim(trigger_event), '') <> ''
        )
    );

ALTER TABLE public.obligations DROP COLUMN IF EXISTS self_declared_review;

-- Back to 023's four-value vocabularies. Any obligation or module typed
-- 'risk_assessment' blocks this, deliberately and for the same reason as the
-- cadence rule above: the row would otherwise survive with a type nothing in
-- the restored schema can express.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_type_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_type_check
    CHECK (obligation_type IN ('sampling', 'examination', 'inspection', 'competency'));

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_satisfied_kind_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_satisfied_kind_check
    CHECK (last_satisfied_kind IS NULL
           OR last_satisfied_kind IN ('lab_sample', 'certificate', 'inspection'));

ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_obligation_type_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_obligation_type_check
    CHECK (obligation_type IS NULL
           OR obligation_type IN ('sampling', 'examination', 'inspection', 'competency'));

COMMIT;
