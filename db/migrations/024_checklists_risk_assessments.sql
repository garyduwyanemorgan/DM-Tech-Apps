BEGIN;

-- ── Migration 024: checklists, inspections, risk-assessment registers ─────────
-- The Phase 3/4 primitives (DM_COMPLIANCE_SCOPING.md §4.6), plus two columns
-- that reading the checklist family showed were missing from 022 and 023
-- (§7.13, and checklist_group_notes.md §6.7). Structure only — nothing reads
-- these tables until the Phase 3 services land, so applying it changes no
-- behaviour.
--
-- WHY THIS EXISTS. 022 gave the product limits to judge against and 023 gave it
-- a registry of what is due. Neither can hold an INSPECTION: most DM
-- establishment guidelines are not limit tables at all, they are requirement
-- lists that somebody walks a building with. GU83 alone is 368 items across 14
-- annexes. Until those exist as data, the only way to sell GU83/GU84/GU85 is to
-- hand a client a PDF, which is the product they already have.
--
-- WHAT READING THE DOCUMENTS CHANGED. §4.6 sketched
-- checklist_templates → checklist_items → inspections → inspection_findings.
-- The right-hand half survived contact with the sources; the left-hand half did
-- not, and one document does not fit the shape at all. Every departure below is
-- forced by a specific finding, recorded against the finding:
--
--   * GU137 is a REGISTER, not a checklist (notes §1.1). Its Appendix A has a
--     FIXED COLUMN SET and a VARIABLE, UNBOUNDED, site-specific ROW SET — one
--     row per hazard — which is the exact inverse of a checklist's fixed item
--     set and variable response. It cannot be stored as checklist_items without
--     pretending ten columns are ten items. Hence risk_assessments →
--     risk_assessment_entries, a second primitive alongside the checklist
--     engine, and NOT a specialisation of it.
--   * GU84 has 43 unscored group-header rows and GU83, built from the same DM
--     master template, is flat throughout (notes §1.2). Both shapes have to fit
--     in one table: parent_item_id + is_scorable.
--   * About thirty items across four of the five documents require a
--     MEASUREMENT (notes §4) — GU85 alone carries 19 numeric thresholds, GU84's
--     noise annex prints hard dB limits, GU83 points at GU119's air limits.
--     Checklists and spec_limits are therefore a HYBRID, not alternatives:
--     checklist_items.spec_limit_id says what passes while the item says what
--     is checked.
--   * GU85 states outright that its scored checklist and risk matrix live in
--     DM's internal inspection system, not in the published document (notes
--     §1.5). Some templates can only ever be OUR rendering of DM's published
--     requirements. template_provenance and is_complete make that visible
--     rather than letting a client believe they are filling in the regulator's
--     form.
--
-- ── THE TWO RULES THIS FILE EXISTS TO MAKE UNBREAKABLE ────────────────────────
--
-- RULE 1: SEVERITY IS NAMESPACED PER STANDARD. NEVER A GLOBAL ENUM.
-- GU83 and GU84 are the same DM framework with incompatible vocabularies on
-- every axis (notes §1.3). "Minor" is a risk OUTCOME in GU83 and a severity
-- INPUT in GU84. "Medium" is the reverse. GU83 grades A–F with no E; GU84
-- grades A–E with no F. GU83 grade A tolerates 1–2 Minor violations while GU84
-- grade A requires zero of everything, so even the letter does not carry across.
-- A shared failure_severity enum does not fail loudly on any of this — it
-- silently re-labels GU84 findings with GU83 semantics and every row still looks
-- valid. There is also no slot anywhere for CATASTROPHIC, and folding it into
-- 'critical' is substantive rather than cosmetic: under GU83's own formula ONE
-- Catastrophic is grade F alone, where it would otherwise take FIVE Criticals.
--
-- So the vocabulary is data (severity_scales → severity_scale_values) owned by
-- the standards row, and an item carries a scale-local VALUE plus the document's
-- verbatim label. The composite foreign keys below make it structurally
-- impossible for an item on a GU84 template to carry a GU83 severity — the same
-- device 023 used to stop an obligation borrowing another tenant's entitlement,
-- applied to the same class of error.
--
-- RULE 2: NO COMPUTED GRADE, AND NO COMPUTED RISK LEVEL. EVER.
-- Both grading formulas join their bands with `&/or`, which is not a decidable
-- operator: conjunctive and disjunctive readings give different grades for most
-- real inspections. GU83 is worse — grades A and B overlap and are not separable
-- as printed (0 Critical, 0 Major, 2 Minor satisfies both), neither band
-- mentions Catastrophic, and A ZERO-VIOLATION ESTABLISHMENT MATCHES NO BAND AT
-- ALL. GU137's risk matrix is labelled "an example", is explicitly
-- non-normative, and is asymmetric: High probability × Low impact = Low, while
-- Medium × High = Medium, and the entire Low-probability row is Low regardless
-- of impact. Any engine computing probability × severity disagrees with the
-- published matrix on several cells.
--
-- Therefore: inspections store VIOLATION COUNTS BY CLASS and no grade;
-- risk_assessment_entries store the risk level THE ASSESSOR RECORDED and never
-- a product of two ratings. The grade stays the regulator's to assign, and
-- inspections.regulator_grade exists only to record one DM has actually issued.
-- A grade letter this product invented is the §7.12 misrepresentation with the
-- client's own signature under it.
--
-- ── THE TWO MISSING COLUMNS ──────────────────────────────────────────────────
--   * standards.lifecycle_status (§7.13). GU93 is an unrevised COVID-19
--     emergency measure that now contradicts GU85 on occupancy — one person per
--     dining table against a hall sized for a third of the workforce — and BOTH
--     ARE PUBLISHED TODAY. Currency cannot be derived from the edition chain:
--     supersedes_id answers "is there a newer edition", not "is this still in
--     force", and a document nothing supersedes may still be dead because
--     nobody bothered to issue a successor. Orthogonal to module_kind (§7.12):
--     one asks what a module may CLAIM, the other whether it still APPLIES.
--     Neither substitutes for the other and both gate sellability.
--   * obligations.self_declared_review (notes §6.7). GU137 states no interval
--     anywhere; the only date that exists is the assessor's own "Date of next
--     review" from the Appendix A header. That is a fourth cadence kind 023
--     does not have — not periodic, not event-triggered, not absent, but
--     SELF-DECLARED BY THE DUTY-HOLDER — and 023's cadence CHECK rejects it
--     outright, so GU137 obligations cannot be inserted at all today.
--
-- DEPENDENCIES. Requires `organizations` and `sites` (db/schema.sql),
-- `user_profiles` and get_user_* (db/schema_rls.sql), `corrective_actions`
-- (008), `assets` (010), `standards` / `spec_limits` (022), and `obligations`
-- (023). It ALTERS tables created by 022 and 023 but modifies neither file:
-- re-applying 022 or 023 after this migration would revert the widened CHECK
-- constraints below, so 024 must be re-applied if that ever happens. Run in the
-- Supabase SQL editor after 023.
-- Reversible: 024_checklists_risk_assessments_down.sql.
--
-- CARRIED FORWARD FROM 022 AND 023, and applied throughout rather than
-- rediscovered:
--   1. EVERY policy below is scoped `TO authenticated`. Supabase grants SELECT
--      on new public tables to the `anon` role by default, so RLS is the only
--      gate and an unrestricted `USING (true)` publishes the table to anyone
--      holding the publishable anon key. It matters again here: the template
--      library IS the encoded product under per-guideline pricing, and
--      inspection_findings is a named client's list of its own violations —
--      the most damaging document a competitor or complainant could be handed.
--   2. NO DEFAULT on a column where guessing is unsafe. See
--      checklist_items.is_scorable, checklist_items.requires_measurement,
--      checklist_templates.template_provenance and inspections.status.
--   3. `coalesce(col,'') = 'x'` rather than `col = 'x'` inside a CHECK. With a
--      NULL column a bare comparison yields NULL and Postgres accepts any CHECK
--      that is not FALSE, so the constraint silently permits exactly what it
--      forbids. Every conditional CHECK below is written this way.
--   4. ON DELETE RESTRICT wherever a deletion would orphan compliance evidence
--      (§7.5): templates, items, severity values, spec limits, standards,
--      assets, sites, obligations and corrective actions are all RESTRICT.
--      CASCADE appears in exactly two places, both containment rather than
--      reference — findings inside their inspection and entries inside their
--      register, following lab_results → lab_samples in 016 — plus
--      organization_id, which cascades to match every other table in the repo.
--   5. The `_down` contains NO DROP POLICY statements. `DROP POLICY IF EXISTS p
--      ON t` tolerates a missing policy but NOT a missing table; against an
--      absent table it raises 42P01 and aborts the whole transactional
--      rollback, in precisely the partial-state case such lines appear to
--      protect against.
--   6. Named constraints added via DROP/ADD so the file is re-runnable, and
--      IF NOT EXISTS on every CREATE.

-- ═════════════════════════════════════════════════════════════════════════════
-- PART 1 — the two missing columns
-- ═════════════════════════════════════════════════════════════════════════════

-- ── standards.lifecycle_status (§7.13) ───────────────────────────────────────
ALTER TABLE public.standards
    ADD COLUMN IF NOT EXISTS lifecycle_status TEXT NOT NULL DEFAULT 'dormant';

ALTER TABLE public.standards DROP CONSTRAINT IF EXISTS standards_lifecycle_status_check;
ALTER TABLE public.standards
    ADD CONSTRAINT standards_lifecycle_status_check
    CHECK (lifecycle_status IN ('live', 'emergency', 'dormant', 'withdrawn'));

CREATE INDEX IF NOT EXISTS standards_lifecycle_idx ON public.standards (lifecycle_status);

COMMENT ON COLUMN public.standards.lifecycle_status IS
    'Does this edition still APPLY? live | emergency | dormant | withdrawn '
    '(§7.13). Orthogonal to guideline_modules.module_kind (§7.12), which asks '
    'what a module may CLAIM. Neither substitutes for the other and both gate '
    'sellability: GU141 is unusable but live, GU93 is coherent but dead. '
    'THE DEFAULT IS DELIBERATE AND IS THE INERT VALUE, NOT THE COMMON ONE. '
    'Every convention in 022 and 023 says a column like this takes no default '
    'at all, because it is an editorial reading that must be stated by whoever '
    'read the document. That is not available here: ADD COLUMN … NOT NULL '
    'against a table that already holds rows requires one, and the choice is '
    'therefore between two wrong answers rather than between an answer and a '
    'refusal. ''live'' is the more dangerous wrong answer by a wide margin — it '
    'asserts on the operator''s behalf that eighty transcribed guidelines are '
    'all currently in force, which is the exact claim GU93 disproves, and its '
    'failure mode is a client enforcing a superseded emergency rule against a '
    'current one. ''dormant'' fails in the visible direction instead: a module '
    'nobody has confirmed refuses to be sold or served and somebody notices '
    'within a day. Read it as "must not be relied on until confirmed". The '
    'seeder must state the real value per edition, and no module may go '
    'available on a standard still carrying the default. '
    'CURRENCY CANNOT BE DERIVED FROM supersedes_id: that column answers "is '
    'there a newer edition", and a document nothing supersedes may still be '
    'dead because nobody issued a successor — they simply stopped meaning it. '
    '''emergency'' is its own value rather than a flavour of live because GU93 '
    'was validly in force when issued: an inspection recorded against it in '
    '2021 attests to something real, and collapsing it into dormant would '
    'rewrite that history.';

-- ── obligations.self_declared_review (notes §6.7) ────────────────────────────
ALTER TABLE public.obligations
    ADD COLUMN IF NOT EXISTS self_declared_review BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.obligations.self_declared_review IS
    'TRUE when the due date was set by the DUTY-HOLDER, not by DM — GU137''s '
    '"Date of next review" on the Appendix A header. A fourth cadence kind 023 '
    'does not have: not periodic, not event-triggered, and not absent. GU137 '
    'says "regular" risk assessment and states no interval anywhere in the '
    'document, so there is nothing to encode as cadence_months and inventing '
    'one would manufacture a DM requirement. 023''s obligations_cadence_check '
    'rejects a row with no cadence and no trigger, which means a GU137 '
    'obligation cannot be inserted at all until the constraint below widens it. '
    'DEFAULT false is safe in the one direction that matters: every obligation '
    'that existed before this migration was transcribed from a DM-stated '
    'cadence or trigger, so false is a statement of fact about them rather than '
    'a guess. Any alert on such a row must read "past the date YOU set", never '
    '"past the DM interval" — DM sets none, and attributing the deadline to the '
    'regulator misstates who imposed it.';

-- 023's cadence rule, widened from two kinds to three. Still EXACTLY ONE: a row
-- with both a cadence and a self-declared date is two schedules and the due-date
-- calculator would have to pick one; a row with none is the silent gap the
-- obligations table exists to eliminate. btrim() on trigger_event for the reason
-- 023 gives — a whitespace-only string is a null cadence in disguise and would
-- satisfy a bare IS NOT NULL. coalesce() on the boolean so a future nullable
-- variant cannot make a branch evaluate to NULL and pass.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_cadence_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_cadence_check
    CHECK (
        (
            (cadence_months IS NOT NULL OR cadence_days IS NOT NULL)
            AND coalesce(btrim(trigger_event), '') = ''
            AND coalesce(self_declared_review, false) = false
        )
        OR
        (
            cadence_months IS NULL AND cadence_days IS NULL
            AND coalesce(btrim(trigger_event), '') <> ''
            AND coalesce(self_declared_review, false) = false
        )
        OR
        (
            cadence_months IS NULL AND cadence_days IS NULL
            AND coalesce(btrim(trigger_event), '') = ''
            AND coalesce(self_declared_review, false) = true
        )
    );

-- The obligation-type vocabulary, widened for the register primitive. 023 fixed
-- it at sampling | examination | inspection | competency, before GU137 was read.
-- A risk assessment is none of those: nothing is sampled, nothing is examined by
-- a third party, no checklist is walked and no person is certified. Forcing it
-- into 'inspection' would make it indistinguishable from a GU83 walk-through in
-- every count and filter, and an inspection carries a verdict where GU137
-- explicitly cannot. Both vocabularies are widened together, exactly as they
-- were introduced together — a type legal on an obligation but illegal on the
-- module that sells it is an obligation no entitlement can cover.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_type_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_type_check
    CHECK (obligation_type IN ('sampling', 'examination', 'inspection',
                               'competency', 'risk_assessment'));

ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_obligation_type_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_obligation_type_check
    CHECK (obligation_type IS NULL
           OR obligation_type IN ('sampling', 'examination', 'inspection',
                                  'competency', 'risk_assessment'));

-- 023 left last_satisfied_by deliberately without a foreign key because the
-- target is polymorphic and `inspections` did not exist yet. It does now, and so
-- does risk_assessments — but the pointer stays FK-free for the reason 023
-- gives: four possible targets cannot be one real FK without four nullable
-- columns. Only the vocabulary widens, so a recorded risk assessment can
-- discharge its obligation and be resolved back to the right table.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_satisfied_kind_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_satisfied_kind_check
    CHECK (last_satisfied_kind IS NULL
           OR last_satisfied_kind IN ('lab_sample', 'certificate', 'inspection',
                                      'risk_assessment'));

-- ═════════════════════════════════════════════════════════════════════════════
-- PART 2 — severity vocabularies, namespaced per standard (RULE 1)
-- ═════════════════════════════════════════════════════════════════════════════

-- ── severity_scales ──────────────────────────────────────────────────────────
-- One row per AXIS per standard edition. GU83 publishes three (probability of
-- repetition, severity of the potential risk, and the risk-assessment class the
-- grading formula counts); GU84 publishes three with different words on all
-- three; GU85 and GU137 publish none at all, which is a fact about those
-- documents and not a gap in this table.
--
-- Global reference data, NOT org-scoped, for the same reason as standards: what
-- GU83 calls Critical is one fact about a published document, not one fact per
-- tenant. Two tenants holding different orderings of one scale is a way to
-- disagree about a grade with the regulator in the room.
CREATE TABLE IF NOT EXISTS public.severity_scales (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    standard_id    UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    key            TEXT NOT NULL,      -- 'gu83_risk_outcome'
    label          TEXT NOT NULL,      -- verbatim heading, e.g. 'Risk assessment'
    axis           TEXT NOT NULL,      -- deliberately no DEFAULT
    source_section TEXT,
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE (standard_id, key),
    -- Not redundant with the primary key. It is the target of the composite
    -- foreign key on severity_scale_values below, which is what keeps a scale's
    -- values inside the standard that published the scale.
    UNIQUE (id, standard_id)
);

-- Which axis of the document's own matrix this is. It matters because GU83 and
-- GU84 both print the word "Minor" on two different axes with two different
-- meanings, so a value is only interpretable as (standard, axis, value) — never
-- as a bare word.
--   risk_outcome — the class the grading formula counts (GU83 Minor…Catastrophic)
--   severity_input — one matrix input axis (GU83 Very Low…Very High)
--   probability — the other input axis (GU83 Very Unlikely…Almost certain)
--   risk_level — an assessor-recorded overall level (GU137's example matrix)
ALTER TABLE public.severity_scales DROP CONSTRAINT IF EXISTS severity_scales_axis_check;
ALTER TABLE public.severity_scales
    ADD CONSTRAINT severity_scales_axis_check
    CHECK (axis IN ('risk_outcome', 'severity_input', 'probability', 'risk_level'));

CREATE INDEX IF NOT EXISTS severity_scales_standard_idx ON public.severity_scales (standard_id, axis);

COMMENT ON TABLE public.severity_scales IS
    'Severity/probability vocabularies OWNED BY A STANDARD EDITION, never '
    'global (notes §1.3). GU83 and GU84 are the same DM framework with '
    'incompatible words on every axis: "Minor" is a risk outcome in GU83 and a '
    'severity input in GU84, "Medium" the reverse. A shared enum does not fail '
    'loudly on that — it silently re-labels GU84 findings with GU83 semantics '
    'and every row still looks valid. Bound to standard_id rather than to a '
    'guideline because the vocabulary can change between editions, exactly as '
    'the requirement set does.';
COMMENT ON COLUMN public.severity_scales.axis IS
    'risk_outcome | severity_input | probability | risk_level. NOT NULL with no '
    'default: the two matrix INPUT axes and the OUTPUT class are printed side '
    'by side in one table in both GU83 and GU84, and mistaking one for another '
    'feeds the grading formula the wrong column. Defaulting to risk_outcome '
    'would make that the silent failure rather than an insert error.';

-- ── severity_scale_values ────────────────────────────────────────────────────
-- The words themselves, in the document's own order, with the document's own
-- stated action per class where it states one.
CREATE TABLE IF NOT EXISTS public.severity_scale_values (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scale_id        UUID NOT NULL REFERENCES public.severity_scales(id) ON DELETE CASCADE,
    -- Denormalised so the composite keys below can reach it. Kept honest by
    -- severity_scale_values_scale_fk, which makes it impossible for this column
    -- to disagree with the parent scale.
    standard_id     UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    value_key       TEXT NOT NULL,      -- 'catastrophic' — scale-local, lowercased
    label           TEXT NOT NULL,      -- 'Catastrophic' — VERBATIM from the document
    ordinal         INTEGER NOT NULL,   -- 1 = least severe, ascending. Scale-local.
    required_action TEXT,               -- the document's own stated response
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (scale_id, value_key),
    UNIQUE (scale_id, ordinal),
    -- Target of the composite foreign key from checklist_items.
    UNIQUE (id, standard_id)
);

ALTER TABLE public.severity_scale_values DROP CONSTRAINT IF EXISTS severity_scale_values_scale_fk;
ALTER TABLE public.severity_scale_values
    ADD CONSTRAINT severity_scale_values_scale_fk
    FOREIGN KEY (scale_id, standard_id)
    REFERENCES public.severity_scales (id, standard_id)
    ON DELETE CASCADE;

ALTER TABLE public.severity_scale_values DROP CONSTRAINT IF EXISTS severity_scale_values_ordinal_check;
ALTER TABLE public.severity_scale_values
    ADD CONSTRAINT severity_scale_values_ordinal_check
    CHECK (ordinal > 0);

COMMENT ON TABLE public.severity_scale_values IS
    'The severity words of one scale, in the document''s own order. Extending '
    'the vocabulary is a matter of inserting a row, which is why CATASTROPHIC '
    'is representable here and is not in the extraction schema''s '
    'critical|major|minor|unknown enum. That omission is substantive, not '
    'cosmetic: under GU83''s own formula ONE Catastrophic is grade F on its '
    'own, where it would otherwise take FIVE Criticals, so collapsing it into '
    'critical understates the worst findings the framework can record.';
COMMENT ON COLUMN public.severity_scale_values.ordinal IS
    'Rank within THIS scale only, ascending. It orders a report and nothing '
    'else. It is NOT comparable across scales and must never be used to map one '
    'standard''s severity onto another''s: GU83''s fourth-of-four outcome and '
    'GU84''s fourth-of-four outcome happen to share the word Catastrophic while '
    'their first three do not correspond at all. Cross-guideline severity '
    'arithmetic — a "compliance score" over two modules — is meaningless for '
    'the same reason grade A is not the same grade in the two documents.';
COMMENT ON COLUMN public.severity_scale_values.label IS
    'Verbatim from the document, case included. value_key is the normalised '
    'handle code uses; this is what a client sees and quotes back to DM.';
COMMENT ON COLUMN public.severity_scale_values.required_action IS
    'The response the DOCUMENT states for this class, where it states one — '
    'GU83/GU84 §8: continue for Minor/Low, recommended corrections for '
    'Major/Medium, mandatory corrections within a proposed period and stop on '
    'non-compliance for Critical/High, stop until corrected and re-assess '
    'before relaunch for Catastrophic. This is the one place in the checklist '
    'family where a corrective-action priority is authorised by the source '
    'rather than invented, which is what §7.12 requires of it. NULL where the '
    'document is silent — and a NULL must not be filled from another '
    'guideline''s table, however similar the words look.';

-- ═════════════════════════════════════════════════════════════════════════════
-- PART 3 — checklist templates and items
-- ═════════════════════════════════════════════════════════════════════════════

-- ── checklist_templates ──────────────────────────────────────────────────────
-- One row per annex or section a client is served as a form. Bound to a
-- standard EDITION, not to a guideline, and the documents settle the question:
-- GU85's change log shows version 4 adding requirements for buildings, kitchens,
-- laundry, lifts, pools, water and indoor air, and version 5 revising
-- definitions, kitchens, water and air. An inspection recorded against v4
-- attests to a different item set than one against v5, so re-pointing a stored
-- inspection at a newer edition would silently change what was attested.
CREATE TABLE IF NOT EXISTS public.checklist_templates (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    standard_id              UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    key                      TEXT NOT NULL,   -- 'gu83_annex_01'
    label                    TEXT NOT NULL,   -- verbatim annex/section heading
    applies_to               TEXT,            -- verbatim scope wording, see below
    source_section           TEXT,            -- 'Part E, Annex 1'
    source_pages             INTEGER[],
    -- Applicability predicate (§4.6). Three columns, because the honest answer
    -- for GU83 is "nobody knows" and that must be storable.
    applicability_condition  JSONB,
    applicability_note       TEXT,
    applicability_provenance TEXT NOT NULL,   -- deliberately no DEFAULT
    -- Provenance of the FORM itself, distinct from the provenance of the facts.
    template_provenance      TEXT NOT NULL,   -- deliberately no DEFAULT
    is_complete              BOOLEAN NOT NULL, -- deliberately no DEFAULT
    incompleteness_note      TEXT,
    status                   TEXT NOT NULL DEFAULT 'draft',
    notes                    TEXT,
    created_at               TIMESTAMPTZ DEFAULT now(),
    UNIQUE (standard_id, key),
    -- Target of the composite foreign keys from checklist_items and
    -- inspections: an item may not belong to one standard's template while
    -- carrying another standard's severity, and an inspection may not attest to
    -- an edition its own template does not belong to.
    UNIQUE (id, standard_id)
);

ALTER TABLE public.checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_status_check;
ALTER TABLE public.checklist_templates
    ADD CONSTRAINT checklist_templates_status_check
    CHECK (status IN ('draft', 'active', 'retired'));

-- published_dm_form         — DM publishes the form and we transcribed it
-- derived_from_requirements — DM publishes REQUIREMENTS and this is our
--                             rendering of them as a form (GU85, notes §1.5)
-- No default: this is the difference between "you are filling in the
-- regulator's checklist" and "you are filling in ours", and there is no safe
-- guess in either direction. Claiming published for a derived form misleads the
-- client about what they are signing; claiming derived for a real DM form
-- understates evidence they could put in front of an inspector.
ALTER TABLE public.checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_provenance_check;
ALTER TABLE public.checklist_templates
    ADD CONSTRAINT checklist_templates_provenance_check
    CHECK (template_provenance IN ('published_dm_form', 'derived_from_requirements'));

ALTER TABLE public.checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_applicability_provenance_check;
ALTER TABLE public.checklist_templates
    ADD CONSTRAINT checklist_templates_applicability_provenance_check
    CHECK (applicability_provenance IN ('document_stated', 'derived', 'unresolved'));

-- "We know this template is incomplete" must be more than a flag nobody reads:
-- an incomplete template has to SAY WHAT IS MISSING, or the warning degrades
-- into a checkbox that gets ticked and forgotten. GU85's note writes itself —
-- the scored checklist and the risk matrix are in DM's internal system and no
-- overall category may be computed from the published document.
ALTER TABLE public.checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_incompleteness_check;
ALTER TABLE public.checklist_templates
    ADD CONSTRAINT checklist_templates_incompleteness_check
    CHECK (is_complete OR coalesce(btrim(incompleteness_note), '') <> '');

-- Same discipline for applicability: anything other than a scope the document
-- states outright must record HOW it was arrived at. Every applies_to in
-- gu83_checklist.json was read off an annex heading because GU83's Part E is
-- titled "Business activity Annexes" and then prints NO activity-to-annex
-- mapping anywhere — the largest content gap in the group. A derived scope that
-- does not admit to being derived is indistinguishable from a published one.
ALTER TABLE public.checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_applicability_note_check;
ALTER TABLE public.checklist_templates
    ADD CONSTRAINT checklist_templates_applicability_note_check
    CHECK (coalesce(applicability_provenance, '') = 'document_stated'
           OR coalesce(btrim(applicability_note), '') <> '');

-- A template whose applicability nobody has resolved must not be servable, for
-- the reason §7.4 gives about scope resolution: serving the wrong annex set
-- changes the violation counts, which changes the grade. Refusing to serve is
-- visible; serving the wrong one is not.
ALTER TABLE public.checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_unresolved_not_active_check;
ALTER TABLE public.checklist_templates
    ADD CONSTRAINT checklist_templates_unresolved_not_active_check
    CHECK (coalesce(status, '') <> 'active'
           OR coalesce(applicability_provenance, '') <> 'unresolved');

CREATE INDEX IF NOT EXISTS checklist_templates_standard_idx ON public.checklist_templates (standard_id, status);

COMMENT ON TABLE public.checklist_templates IS
    'One servable form per annex or section, bound to a standard EDITION '
    '(§4.6). Note that templates are shared as well as versioned: GU83 and GU84 '
    'draw the toys, low-voltage, detergent and biocide annexes from a common DM '
    'master library, differing in risk class and a few labels. That is a '
    'commercial benefit — the same annex is content for two SKUs, so editorial '
    'effort amortises better than §7.1 assumes — and an editorial hazard, '
    'because a correction to a shared annex must be propagated to every module '
    'that embeds it. This schema stores a row per module; nothing here detects '
    'the divergence for you.';
COMMENT ON COLUMN public.checklist_templates.template_provenance IS
    'published_dm_form | derived_from_requirements. GU85 §3 says outright that '
    'the scored checklist and the risk matrix are "electronically registered in '
    'the system designated for the inspection and monitoring of labor '
    'accommodations" — DM publishes the REQUIREMENTS and keeps the CHECKLIST. '
    'So a GU85 template is OUR rendering, and a client filling it in must be '
    'told so, or they will reasonably believe they are completing the '
    'regulator''s actual form and that a clean result is DM''s verdict. '
    'No default — see the constraint comment above.';
COMMENT ON COLUMN public.checklist_templates.is_complete IS
    'FALSE means we KNOW this template does not cover everything the guideline '
    'is inspected against, and incompleteness_note must say what is missing. '
    'NOT NULL with no default because both guesses are bad in the same '
    'direction as template_provenance: a template silently marked complete is a '
    'client believing a clean sheet means compliance. For GU85 this is '
    'permanent, not a backlog item — the missing half is not published and '
    'never will be.';
COMMENT ON COLUMN public.checklist_templates.applicability_condition IS
    'Machine-evaluable predicate for whether this template is served at all: '
    'GU137''s "employer has 5 or more employees" recording duty, GU85''s '
    'if-a-pool-exists items, and eventually GU83''s activity-to-annex mapping '
    'once DM states it. JSONB rather than columns because the three known '
    'predicates share no shape and inventing one from the first example would '
    'force every later guideline into it. NULL DOES NOT MEAN "ALWAYS '
    'APPLICABLE" — that reading is what applicability_provenance exists to '
    'prevent: NULL with provenance ''unresolved'' means nobody knows, and such '
    'a template may not go active. Where a template genuinely has no condition, '
    'say so with provenance ''document_stated'' and a NULL condition. Note also '
    'that a template not served must not be scored as a failure: below GU137''s '
    'headcount threshold the document imposes no recording duty at all.';
COMMENT ON COLUMN public.checklist_templates.applies_to IS
    'The scope in the document''s own words, as printed on the annex heading. '
    'Verbatim and for display; the machine-readable form is '
    'applicability_condition. Never route from this column.';
COMMENT ON COLUMN public.checklist_templates.standard_id IS
    'ON DELETE RESTRICT: a template whose edition vanished attests to nothing. '
    'Binding to the edition rather than the guideline is deliberate and '
    'evidenced — GU85''s change log shows the requirement set changing between '
    'v4 and v5, so an inspection against one is not an inspection against the '
    'other.';

-- ── checklist_items ──────────────────────────────────────────────────────────
-- The checkpoints. Two shapes have to live here at once: GU84's two-level
-- annexes (43 of 302 rows print a requirement with the Risk column EMPTY and the
-- rows beneath elaborate it) and GU83's flat lists, built from the same DM
-- master template. A flat-only table drops the grouping an inspector navigates
-- by, or scores the headers as failures they were never meant to be — and since
-- headers carry no risk class, scoring one feeds the grading formula a violation
-- it cannot classify.
CREATE TABLE IF NOT EXISTS public.checklist_items (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id          UUID NOT NULL,      -- composite FK below
    -- Denormalised from the template so the severity composite FK can reach it.
    -- checklist_items_template_fk makes disagreement impossible.
    standard_id          UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    parent_item_id       UUID,               -- composite self-FK below
    item_no              TEXT NOT NULL,      -- 'A1.2' — the document's, or ours; see comment
    ordinal              INTEGER,
    text                 TEXT NOT NULL,      -- VERBATIM, defects included
    response_type        TEXT NOT NULL,      -- deliberately no DEFAULT
    is_scorable          BOOLEAN NOT NULL,   -- deliberately no DEFAULT
    is_mandatory         BOOLEAN NOT NULL,   -- deliberately no DEFAULT
    severity_value_id    UUID,               -- composite FK below; NULL = none stated
    source_risk_label    TEXT,               -- verbatim risk word, kept alongside
    requires_measurement BOOLEAN NOT NULL,   -- deliberately no DEFAULT
    spec_limit_id        UUID REFERENCES public.spec_limits(id) ON DELETE RESTRICT,
    measurement_note     TEXT,
    duplicate_of_item_id UUID,               -- composite self-FK below
    duplicate_note       TEXT,
    source_page          INTEGER,
    confidence           TEXT NOT NULL,      -- deliberately no DEFAULT
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (template_id, item_no),
    -- Targets of the composite foreign keys from this table (parent, duplicate)
    -- and from inspection_findings.
    UNIQUE (id, template_id),
    -- Trivially unique because id is the primary key. It exists so a finding can
    -- carry the item's scorability as a foreign-keyed fact rather than a copy —
    -- see inspection_findings_item_fk.
    UNIQUE (id, is_scorable)
);

-- An item belongs to a template, and both must agree about which edition they
-- are. Composite rather than a plain FK to checklist_templates(id) for the
-- reason 023 gives about obligations and entitlements: a plain reference lets
-- the denormalised standard_id drift from the template's, and the drift is
-- invisible because every row still looks valid. CASCADE because items are
-- contained by their template, not merely referenced by it; deletion is
-- nonetheless blocked once evidence exists, by the RESTRICT from
-- inspection_findings to items.
ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_template_fk;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_template_fk
    FOREIGN KEY (template_id, standard_id)
    REFERENCES public.checklist_templates (id, standard_id)
    ON DELETE CASCADE;

-- RULE 1, ENFORCED RATHER THAN DOCUMENTED. An item may only carry a severity
-- value published by ITS OWN standard. Without the standard_id in this key, a
-- loader bug — or an admin screen offering a flat list of severity words — could
-- hang GU83's "Minor" (a risk outcome) off a GU84 item where "Minor" is a
-- severity input, and the row would be accepted, counted, and graded. This is
-- the mis-mapping notes §1.3 warns about, made structurally impossible.
-- MATCH SIMPLE (the default) means the constraint is not enforced when
-- severity_value_id is NULL, which is exactly right: GU85 and GU137 state no
-- severities at all and every item there is legitimately NULL.
ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_severity_fk;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_severity_fk
    FOREIGN KEY (severity_value_id, standard_id)
    REFERENCES public.severity_scale_values (id, standard_id)
    ON DELETE RESTRICT;

-- GU84's group headers, kept inside one template. ON DELETE RESTRICT: deleting
-- a parent would orphan the grouping an inspector navigates by.
ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_parent_fk;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_parent_fk
    FOREIGN KEY (parent_item_id, template_id)
    REFERENCES public.checklist_items (id, template_id)
    ON DELETE RESTRICT;

ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_duplicate_fk;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_duplicate_fk
    FOREIGN KEY (duplicate_of_item_id, template_id)
    REFERENCES public.checklist_items (id, template_id)
    ON DELETE RESTRICT;

ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_no_self_reference_check;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_no_self_reference_check
    CHECK ((parent_item_id IS NULL OR parent_item_id <> id)
           AND (duplicate_of_item_id IS NULL OR duplicate_of_item_id <> id));

ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_response_type_check;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_response_type_check
    CHECK (response_type IN ('yes_no', 'yes_no_na', 'numeric', 'free_text'));

ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_confidence_check;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_confidence_check
    CHECK (confidence IN ('high', 'medium', 'low'));

-- A row printed with the Risk column EMPTY has no class, so it cannot enter a
-- grading formula and must not carry a severity. Reading GU84's blank-risk rows
-- as group headings is an inference from LAYOUT — the document never says its
-- annex tables are two-level — and this constraint is what stops that inference
-- being quietly upgraded into a scored classification later.
ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_unscorable_no_severity_check;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_unscorable_no_severity_check
    CHECK (is_scorable OR severity_value_id IS NULL);

-- A limit attached to an item that claims to need no measurement is two
-- statements that cannot both be true, and the pair decides whether an
-- inspector may tick a box by eye.
ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_measurement_check;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_measurement_check
    CHECK (spec_limit_id IS NULL OR requires_measurement);

-- A duplicate flagged without saying which row it duplicates, or vice versa, is
-- not actionable — and de-duplication is not cosmetic here: one real-world
-- failure counted twice can push an establishment down a grade band.
ALTER TABLE public.checklist_items DROP CONSTRAINT IF EXISTS checklist_items_duplicate_note_check;
ALTER TABLE public.checklist_items
    ADD CONSTRAINT checklist_items_duplicate_note_check
    CHECK (duplicate_of_item_id IS NULL OR coalesce(btrim(duplicate_note), '') <> '');

CREATE INDEX IF NOT EXISTS checklist_items_template_idx   ON public.checklist_items (template_id, ordinal);
CREATE INDEX IF NOT EXISTS checklist_items_parent_idx     ON public.checklist_items (parent_item_id);
CREATE INDEX IF NOT EXISTS checklist_items_severity_idx   ON public.checklist_items (severity_value_id);
CREATE INDEX IF NOT EXISTS checklist_items_spec_limit_idx ON public.checklist_items (spec_limit_id);
CREATE INDEX IF NOT EXISTS checklist_items_scorable_idx   ON public.checklist_items (template_id) WHERE is_scorable;

COMMENT ON TABLE public.checklist_items IS
    'Checkpoints within a template. Holds both shapes the DM master template '
    'produces: GU84''s two-level annexes via parent_item_id + is_scorable, and '
    'GU83''s flat lists, which come from the same source and must coexist '
    'inside one guideline family.';
COMMENT ON COLUMN public.checklist_items.is_scorable IS
    'Whether a NOT MET response on this item counts as a violation. FALSE for '
    'GU84''s 43 group headers, which print a requirement with the Risk column '
    'empty, and for GU137''s method prompts, which expect a written output '
    'rather than an attestation. NOT NULL WITH NO DEFAULT, because both guesses '
    'corrupt a count in opposite directions: defaulting TRUE scores 43 headings '
    'as unclassifiable violations that no grading band can absorb, defaulting '
    'FALSE silently drops real violations out of the total. The count is what '
    'the client puts in front of DM.';
COMMENT ON COLUMN public.checklist_items.requires_measurement IS
    'TRUE when the answer can only be produced by an instrument or a '
    'laboratory. NOT NULL with no default: FALSE is the common value but it is '
    'a substantive claim — that an inspector may settle this item by eye — and '
    'guessing it wrong turns roughly thirty measurement items across GU83, '
    'GU84, GU85 and GU93 into checkboxes. Note it is INDEPENDENT of '
    'spec_limit_id: GU83 A3.22/A3.23 and GU84 A2.11/A2.12 demand a humidity and '
    'heat comfort measurement while stating NO range in either document, so '
    'TRUE with a NULL limit is a real and expected combination meaning '
    '"measure it; we cannot tell you what passes".';
COMMENT ON COLUMN public.checklist_items.spec_limit_id IS
    'The §4.2 limit this item is judged against, where one exists (§4.6, notes '
    '§4). Checklists and limits are a HYBRID, not alternatives: the item states '
    'WHAT IS CHECKED and the limit states WHAT PASSES. The limit may come from '
    'the same guideline — GU85''s 19 numeric thresholds, GU84 A4.8/A4.9''s 55 dB '
    'daytime and 45 dB night noise ceilings — or from a different one: GU83 '
    'A3.11 and GU84 A2.1 point at GU119''s indoor-air limits, and GU83 A4.6 / '
    'GU84 A3.11 pull in a full laboratory analysis, which under §4.7 must come '
    'from a DM-accredited independent laboratory. ON DELETE RESTRICT: an item '
    'silently losing its limit becomes an unjudgeable checkbox that still looks '
    'answerable. Two cautions from the sources. First, GU84''s noise annex '
    'prints numbers that GU83''s corresponding annex omits entirely, so a '
    'client holding only the GU83 module cannot evaluate its own noise items — '
    'that is a NULL to surface, not to fill from GU84. Second, two thresholds '
    'were deliberately left unresolved because a maximum cannot be two numbers '
    '(GU85 6.3 "no more than 8 to 10 workers", GU93 6.3 "maximum 3 to 5 workers '
    'per group"); they must stay NULL rather than being snapped to either '
    'bound, which would authorise an occupancy DM may not permit or forbid one '
    'it does.';
COMMENT ON COLUMN public.checklist_items.severity_value_id IS
    'Scale-local severity, and NEVER a global enum (RULE 1 in the header). The '
    'composite foreign key with standard_id makes it structurally impossible '
    'for a GU84 item to carry a GU83 severity. NULL is common and honest: GU85 '
    'and GU137 assign no risk class to anything, and GU85 says why — severities '
    'exist in DM''s internal system, not in the published document. A NULL '
    'therefore must not be inferred, and corrective-action due dates cannot be '
    'derived from it. GU84 A1.114 shows the opposite defect: a bare reference '
    'list (":TG14, TG15, …") printed as a requirement and carrying a risk class '
    'of High, which a naive loader would score.';
COMMENT ON COLUMN public.checklist_items.source_risk_label IS
    'The risk word exactly as the document prints it, kept alongside the mapped '
    'value so nothing is lost if the scales are ever reworked. Also the audit '
    'trail for the cases where the source contradicts itself: GU84 prints '
    '"Availability of suitable cleaning materials." twice, once Medium and once '
    'High, which is left unmapped rather than resolved — preferring either '
    'value would change a grade on a guess.';
COMMENT ON COLUMN public.checklist_items.text IS
    'VERBATIM, including where the source is broken. GU85 7-1 is truncated '
    'mid-sentence ("A dishwashing sink with both hot and cold") and is stored '
    'that way, because an inspector cannot attest to a requirement that was '
    'never fully stated. GU83''s typographical errors (inscects, Prsence, '
    'AvaiIability, driniking) are reproduced. Correcting the text here would '
    'make our form disagree with the document a client is inspected against.';
COMMENT ON COLUMN public.checklist_items.item_no IS
    'The document''s own numbering where it has one — GU85 numbers its '
    'requirements and GU83/GU84 number their annex rows — and OURS where it '
    'does not: GU137 numbers none of its bullets or columns, so every number '
    'there is positional and assigned by extraction. That distinction must '
    'reach the UI: an item number presented as DM''s when it is ours is a '
    'citation the regulator cannot match.';
COMMENT ON COLUMN public.checklist_items.confidence IS
    'high | medium | low — how sure the extraction is that this row says what '
    'the document says. NOT NULL with no default: ''high'' is the common value '
    'but defaulting to it asserts an editorial confidence nobody expressed, and '
    'the low-confidence rows are exactly the ones somebody must revisit before '
    'the module is sold (§7.1).';
COMMENT ON COLUMN public.checklist_items.duplicate_of_item_id IS
    'Points at the row this one duplicates within the same template. Real and '
    'load-bearing: GU83 Annexes 5 and 7 repeat rows, GU84 Annex 2 prints '
    '"Presence of suitable ventilation mechanism in pump rooms" both as an '
    'unscored header and as a scored Medium item, and GU93 sections 4 and 7 are '
    'near-total duplicates with seven of eight items verbatim identical. '
    'Scoring both counts one real-world failure twice and can push a grade down '
    'a band. Flagged rather than deleted, because the row exists in the '
    'document and an inspector reading along will look for it.';

-- ═════════════════════════════════════════════════════════════════════════════
-- PART 4 — inspections and findings
-- ═════════════════════════════════════════════════════════════════════════════

-- ── inspections ──────────────────────────────────────────────────────────────
-- One walk-through of one template. This is the half of §4.6 that survived
-- contact with the documents unchanged.
CREATE TABLE IF NOT EXISTS public.inspections (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id        UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id                UUID REFERENCES public.sites(id) ON DELETE RESTRICT,
    asset_id               UUID REFERENCES public.assets(id) ON DELETE RESTRICT,
    template_id            UUID NOT NULL,   -- composite FK below
    standard_id            UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    obligation_id          UUID REFERENCES public.obligations(id) ON DELETE RESTRICT,
    inspected_on           DATE NOT NULL,
    inspector_user_id      UUID REFERENCES public.user_profiles(id) ON DELETE RESTRICT,
    inspector_name         TEXT,
    inspector_organisation TEXT,
    status                 TEXT NOT NULL,   -- deliberately no DEFAULT
    -- RULE 2: counts, not a grade. See the comment on the column.
    violation_counts       JSONB,
    regulator_grade        TEXT,
    regulator_grade_source TEXT,
    notes                  TEXT,
    created_at             TIMESTAMPTZ DEFAULT now(),
    -- Targets of the composite foreign key from inspection_findings. The triple
    -- carries tenancy AND template in one key, so a finding can neither be hung
    -- off another tenant's inspection nor answer an item from a different form.
    UNIQUE (id, organization_id, template_id)
);

-- The edition attested to is pinned by the template, not chosen alongside it.
-- Storing standard_id separately and letting it drift would mean an inspection
-- citing GU85 v5 while holding v4's item set — the silent re-attestation the
-- template comment warns about, arriving through the header instead.
ALTER TABLE public.inspections DROP CONSTRAINT IF EXISTS inspections_template_fk;
ALTER TABLE public.inspections
    ADD CONSTRAINT inspections_template_fk
    FOREIGN KEY (template_id, standard_id)
    REFERENCES public.checklist_templates (id, standard_id)
    ON DELETE RESTRICT;

ALTER TABLE public.inspections DROP CONSTRAINT IF EXISTS inspections_status_check;
ALTER TABLE public.inspections
    ADD CONSTRAINT inspections_status_check
    CHECK (status IN ('in_progress', 'submitted', 'reviewed', 'void'));

-- A grade may be RECORDED, never COMPUTED, so a grade with no stated source is
-- exactly the fabrication this table refuses to produce. Both directions are
-- checked: a source without a grade is a dangling attribution.
ALTER TABLE public.inspections DROP CONSTRAINT IF EXISTS inspections_regulator_grade_check;
ALTER TABLE public.inspections
    ADD CONSTRAINT inspections_regulator_grade_check
    CHECK ((regulator_grade IS NULL) = (coalesce(btrim(regulator_grade_source), '') = ''));

CREATE INDEX IF NOT EXISTS inspections_org_date_idx   ON public.inspections (organization_id, inspected_on);
CREATE INDEX IF NOT EXISTS inspections_template_idx   ON public.inspections (template_id);
CREATE INDEX IF NOT EXISTS inspections_site_idx       ON public.inspections (site_id);
CREATE INDEX IF NOT EXISTS inspections_asset_idx      ON public.inspections (asset_id);
CREATE INDEX IF NOT EXISTS inspections_obligation_idx ON public.inspections (obligation_id);
CREATE INDEX IF NOT EXISTS inspections_status_idx     ON public.inspections (organization_id, status);

COMMENT ON TABLE public.inspections IS
    'One completed walk-through of one checklist template (§4.6). Discharges an '
    'obligation via obligation_id, and its findings feed corrective_actions '
    '(008). There is deliberately NO computed grade column — see '
    'violation_counts.';
COMMENT ON COLUMN public.inspections.violation_counts IS
    'A snapshot of violations by severity class, keyed by scale-local value_key '
    '(e.g. {"catastrophic":0,"critical":2,"major":4,"minor":1}), derivable from '
    'the findings and stored because a report cites the numbers as they stood '
    'when it was issued. THIS IS ALL THAT MAY BE EMITTED. The grading formulas '
    'are NOT implemented and must not be: GU83 and GU84 both join their bands '
    'with "&/or", which is not a decidable operator — the conjunctive and '
    'disjunctive readings give different grades for most real inspections. GU83 '
    'is worse still: grades A and B overlap and are not separable as printed (0 '
    'Critical, 0 Major, 2 Minor satisfies both), neither band mentions '
    'Catastrophic, and A ZERO-VIOLATION ESTABLISHMENT MATCHES NO BAND AT ALL. '
    'GU85 goes further and says its overall category is computed inside DM''s '
    'own system from a checklist it does not publish. The grade is the number a '
    'client puts in front of the regulator, so a wrong letter is the §7.12 '
    'misrepresentation with their signature under it. Counts are defensible; a '
    'letter is not. Nor is a cross-guideline "compliance score": grade A '
    'tolerates 1–2 Minor violations in GU83 and requires zero of everything in '
    'GU84, so the letters do not even mean the same thing between two documents '
    'built from one template.';
COMMENT ON COLUMN public.inspections.regulator_grade IS
    'A grade DM ITSELF ISSUED, transcribed. The only circumstance in which a '
    'grade letter may appear anywhere in this product. regulator_grade_source '
    'must name where it came from — the inspection report number, the DM '
    'portal, the notice — so that no derived value can ever be written here '
    'without an obvious lie beside it. NULL is the normal state.';
COMMENT ON COLUMN public.inspections.status IS
    'in_progress | submitted | reviewed | void. NOT NULL with NO DEFAULT: '
    'defaulting to in_progress would make a fully imported historical '
    'inspection look unfinished and drop it out of compliance reporting, while '
    'defaulting to submitted would make a half-filled form count as evidence '
    'that a walk-through happened.';
COMMENT ON COLUMN public.inspections.obligation_id IS
    'The obligation this inspection discharges (023). ON DELETE RESTRICT: the '
    'obligation is the reason the evidence exists, and losing the link makes an '
    'inspection unattributable and the obligation look unmet. Nullable — an '
    'ad-hoc or client-initiated inspection is real and must be storable.';
COMMENT ON COLUMN public.inspections.site_id IS
    'ON DELETE RESTRICT, deliberately unlike assets.site_id (010), which '
    'cascades. An asset is operational data; an inspection is compliance '
    'evidence, and §7.5 forbids deleting evidence as a side effect of an '
    'unrelated administrative action.';

-- ── inspection_findings ──────────────────────────────────────────────────────
-- One response per item. Feeds corrective_actions (008), which is where the
-- checklist family finally earns the workflow that already exists: GU83 and
-- GU84 state a required action per risk class in the document itself, so the
-- priority on a corrective action raised here is citable rather than invented.
CREATE TABLE IF NOT EXISTS public.inspection_findings (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id       UUID NOT NULL,      -- composite FK below
    organization_id     UUID NOT NULL,      -- part of the composite FK, see below
    template_id         UUID NOT NULL,      -- part of the composite FK, see below
    item_id             UUID NOT NULL,      -- composite FK below
    -- Carried as a foreign-keyed fact, not a copy. See the constraint comment.
    item_is_scorable    BOOLEAN NOT NULL,
    outcome             TEXT NOT NULL,      -- deliberately no DEFAULT
    response_value      TEXT,               -- verbatim, as entered
    measured_value      NUMERIC,
    measured_unit       TEXT,
    reason              TEXT,               -- required for na / not_assessed
    evidence_url        TEXT,
    corrective_action_id UUID REFERENCES public.corrective_actions(id) ON DELETE RESTRICT,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (inspection_id, item_id)
);

-- Tenancy and form in one composite key, for the reason 023 gives about
-- obligations borrowing another tenant's entitlement. Without organization_id
-- in the key a finding could be attached to another tenant's inspection; without
-- template_id it could answer an item belonging to a completely different
-- checklist, and the inspection would still total up as if it were complete.
-- CASCADE because a finding is contained by its inspection, exactly as
-- lab_results are contained by lab_samples (016) — a response with no
-- walk-through around it is not evidence of anything.
ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_inspection_fk;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_inspection_fk
    FOREIGN KEY (inspection_id, organization_id, template_id)
    REFERENCES public.inspections (id, organization_id, template_id)
    ON DELETE CASCADE;

-- The item, pinned to the same template, and carrying its scorability with it.
-- Including is_scorable in the foreign key is unusual and is doing real work:
-- it is what makes inspection_findings_unscorable_check below enforceable at
-- all. A CHECK cannot look at another table, so the only alternatives were to
-- copy the flag (which drifts silently) or to leave the rule to application
-- code (which is where the GU84 header problem came from in the first place).
-- ON UPDATE CASCADE so that correcting an item's scorability propagates rather
-- than being blocked; ON DELETE RESTRICT because an item underneath recorded
-- evidence must not be deletable (§7.5).
ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_item_fk;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_item_fk
    FOREIGN KEY (item_id, template_id)
    REFERENCES public.checklist_items (id, template_id)
    ON DELETE RESTRICT;

ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_item_scorable_fk;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_item_scorable_fk
    FOREIGN KEY (item_id, item_is_scorable)
    REFERENCES public.checklist_items (id, is_scorable)
    ON UPDATE CASCADE ON DELETE RESTRICT;

ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_outcome_check;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_outcome_check
    CHECK (outcome IN ('met', 'not_met', 'not_applicable', 'not_assessed', 'recorded'));

-- GU84's 43 group headers cannot be violations, because they carry no risk
-- class and nothing in the grading formula can absorb them. Neither can GU137's
-- method prompts, which ask for a written output and define no failure. Both are
-- answerable — 'recorded' exists precisely for a response that is not a
-- judgement — but neither may be counted against an establishment.
ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_unscorable_check;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_unscorable_check
    CHECK (item_is_scorable OR coalesce(outcome, '') <> 'not_met');

-- §7.4, at item level: a gap must be visible as a gap. An item marked not
-- applicable without saying why is how an annex quietly stops being inspected,
-- and one marked not_assessed without a reason is a silent pass wearing a
-- different label. Both are legitimate outcomes and both must be accountable.
ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_reason_check;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_reason_check
    CHECK (coalesce(outcome, '') NOT IN ('not_applicable', 'not_assessed')
           OR coalesce(btrim(reason), '') <> '');

-- A measurement half recorded reads as a number without a unit, which is the
-- likeliest place for a plausible wrong verdict (§7.12's column-to-unit trap).
ALTER TABLE public.inspection_findings DROP CONSTRAINT IF EXISTS inspection_findings_measured_pair_check;
ALTER TABLE public.inspection_findings
    ADD CONSTRAINT inspection_findings_measured_pair_check
    CHECK (measured_value IS NULL OR coalesce(btrim(measured_unit), '') <> '');

CREATE INDEX IF NOT EXISTS inspection_findings_inspection_idx ON public.inspection_findings (inspection_id);
CREATE INDEX IF NOT EXISTS inspection_findings_item_idx       ON public.inspection_findings (item_id);
CREATE INDEX IF NOT EXISTS inspection_findings_action_idx     ON public.inspection_findings (corrective_action_id);
CREATE INDEX IF NOT EXISTS inspection_findings_violation_idx
    ON public.inspection_findings (inspection_id) WHERE outcome = 'not_met';

COMMENT ON TABLE public.inspection_findings IS
    'One response per checklist item (§4.6). Violations are counted from here — '
    'joining to checklist_items for the severity and EXCLUDING duplicates and '
    'non-scorable rows — and never graded. Findings feed corrective_actions '
    '(008); the priority comes from severity_scale_values.required_action, '
    'which the source documents state, so it is the one corrective-action '
    'priority in this family that is not invented.';
COMMENT ON COLUMN public.inspection_findings.item_is_scorable IS
    'The item''s is_scorable, carried here as a FOREIGN-KEYED fact rather than '
    'a copy: (item_id, item_is_scorable) references checklist_items '
    '(id, is_scorable) ON UPDATE CASCADE, so it cannot disagree with the item '
    'and cannot go stale. It exists only so that a CHECK — which cannot read '
    'another table — can refuse a not_met outcome on an unscorable row. Do not '
    'set it independently; the loader copies it from the item and the database '
    'rejects any other value.';
COMMENT ON COLUMN public.inspection_findings.outcome IS
    'met | not_met | not_applicable | not_assessed | recorded. NOT NULL with no '
    'default. ''recorded'' is for items that are answerable but not judgeable — '
    'GU137''s free-text method prompts and GU84''s group headers — and it is '
    'deliberately not a synonym for met: a written answer to "list all safe and '
    'unsafe work practices" is not a pass, and GU137 authorises no pass. '
    '''not_assessed'' is a first-class visible outcome (§7.4), never a silent '
    'pass, and both it and not_applicable require a reason.';
COMMENT ON COLUMN public.inspection_findings.measured_value IS
    'The number an instrument or laboratory produced, where the item requires '
    'one. Judged against checklist_items.spec_limit_id by core/specs.py, using '
    'the same min_inclusive/max_inclusive and qualifier_rule semantics as any '
    'other measurement — the point of the hybrid is that a checklist '
    'measurement is judged by exactly the same machinery as a lab result, not '
    'by a second implementation. Where the item requires a laboratory (GU83 '
    'A4.6, GU84 A3.11) the result belongs in lab_samples with its accreditation '
    'gate (§4.7) and this column holds nothing.';
COMMENT ON COLUMN public.inspection_findings.corrective_action_id IS
    'ON DELETE RESTRICT: the corrective action is the answer to the finding, '
    'and a violation whose remediation record vanished reads as an unaddressed '
    'violation with no history. Nullable — not every not_met has been actioned '
    'yet, and that backlog is exactly what a dashboard needs to show.';

-- ═════════════════════════════════════════════════════════════════════════════
-- PART 5 — the register primitive (GU137)
-- ═════════════════════════════════════════════════════════════════════════════

-- ── risk_assessments ─────────────────────────────────────────────────────────
-- The header of GU137's Appendix A. A REGISTER, not a checklist: a checklist has
-- a fixed item set and a variable response, this has a fixed COLUMN set and a
-- variable, unbounded, site-specific ROW set — one row per hazard the assessor
-- identifies. It is the inverse shape, and it is the Phase 4 lead guideline, so
-- the document scheduled to prove the checklist engine is the one document in
-- the group that does not exercise it.
--
-- GU137 is module_kind = 'process' (§7.12) and cannot say COMPLIANT: it states
-- no limit, no acceptance criterion, no checkpoint and no definition of an
-- adequate assessment. It says action "will vary between supervision … to
-- complete halt of work (in case of unacceptable risk)" and never defines which
-- cell is unacceptable, so even the halt-of-work trigger is unencodable. What a
-- report may legitimately say is: an assessment was carried out on date X by
-- person Y, recorded these hazards, and is due for review on date Z — the date
-- the assessor set.
CREATE TABLE IF NOT EXISTS public.risk_assessments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id     UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id             UUID REFERENCES public.sites(id) ON DELETE RESTRICT,
    asset_id            UUID REFERENCES public.assets(id) ON DELETE RESTRICT,
    activity            TEXT,               -- keyed to an asset OR an activity
    standard_id         UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    obligation_id       UUID REFERENCES public.obligations(id) ON DELETE RESTRICT,
    -- Appendix A header fields, verbatim.
    company_name        TEXT,
    assessed_by         TEXT NOT NULL,
    assessed_on         DATE NOT NULL,
    next_review_on      DATE,               -- SELF-DECLARED. See the comment.
    headcount           INTEGER,            -- GU137's 5-or-more recording gate
    -- Optional scale bindings, for a future guideline that publishes one.
    probability_scale_id UUID REFERENCES public.severity_scales(id) ON DELETE RESTRICT,
    severity_scale_id    UUID REFERENCES public.severity_scales(id) ON DELETE RESTRICT,
    level_scale_id       UUID REFERENCES public.severity_scales(id) ON DELETE RESTRICT,
    status              TEXT NOT NULL,      -- deliberately no DEFAULT
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    -- Target of the composite foreign key from risk_assessment_entries.
    UNIQUE (id, organization_id)
);

ALTER TABLE public.risk_assessments DROP CONSTRAINT IF EXISTS risk_assessments_status_check;
ALTER TABLE public.risk_assessments
    ADD CONSTRAINT risk_assessments_status_check
    CHECK (status IN ('draft', 'recorded', 'superseded', 'void'));

-- An assessment of nothing in particular cannot be reviewed, actioned or shown
-- to be missing. GU137 assesses "procedures, processes and equipment", so either
-- a piece of plant or a named activity has to be on the row.
ALTER TABLE public.risk_assessments DROP CONSTRAINT IF EXISTS risk_assessments_subject_check;
ALTER TABLE public.risk_assessments
    ADD CONSTRAINT risk_assessments_subject_check
    CHECK (asset_id IS NOT NULL OR coalesce(btrim(activity), '') <> '');

ALTER TABLE public.risk_assessments DROP CONSTRAINT IF EXISTS risk_assessments_review_window_check;
ALTER TABLE public.risk_assessments
    ADD CONSTRAINT risk_assessments_review_window_check
    CHECK (next_review_on IS NULL OR assessed_on <= next_review_on);

ALTER TABLE public.risk_assessments DROP CONSTRAINT IF EXISTS risk_assessments_headcount_check;
ALTER TABLE public.risk_assessments
    ADD CONSTRAINT risk_assessments_headcount_check
    CHECK (headcount IS NULL OR headcount >= 0);

CREATE INDEX IF NOT EXISTS risk_assessments_org_idx        ON public.risk_assessments (organization_id, assessed_on);
CREATE INDEX IF NOT EXISTS risk_assessments_review_idx     ON public.risk_assessments (next_review_on) WHERE next_review_on IS NOT NULL;
CREATE INDEX IF NOT EXISTS risk_assessments_site_idx       ON public.risk_assessments (site_id);
CREATE INDEX IF NOT EXISTS risk_assessments_asset_idx      ON public.risk_assessments (asset_id);
CREATE INDEX IF NOT EXISTS risk_assessments_obligation_idx ON public.risk_assessments (obligation_id);

COMMENT ON TABLE public.risk_assessments IS
    'Header of a GU137 Appendix A risk-assessment REGISTER — a second primitive '
    'alongside the checklist engine, not a specialisation of it (§4.6, notes '
    '§1.1). The register has a fixed column set and an unbounded, site-specific '
    'row set, one row per hazard: the inverse of a checklist''s fixed item set '
    'and variable response. Expressing it as checklist_items would mean '
    'pretending ten columns are ten items. GU137 is a PROCESS module and no '
    'report built on this table may claim COMPLIANT.';
COMMENT ON COLUMN public.risk_assessments.next_review_on IS
    'The assessor''s own "Date of next review" from the Appendix A header — '
    'SELF-DECLARED BY THE DUTY-HOLDER, not set by DM. GU137 says "regular" and '
    'states no interval anywhere in the document, which is why '
    'obligations.self_declared_review exists. Any overdue flag derived from '
    'this column must read "past the date YOU set", never "past the DM '
    'interval". NULL means the assessor set no review date, which is a finding '
    'to surface — never a licence to substitute a cadence of our own.';
COMMENT ON COLUMN public.risk_assessments.headcount IS
    'Employees at the time of assessment. GU137 §4-5''s recording duties are '
    'CONDITIONAL ON THE EMPLOYER HAVING 5 OR MORE EMPLOYEES; below that the '
    'document imposes no recording duty at all, so the template must not be '
    'served and its absence MUST NOT BE SCORED AS A FAILURE. Nullable because '
    'the number is often simply unknown, and an unknown headcount is not the '
    'same as a small one.';
COMMENT ON COLUMN public.risk_assessments.probability_scale_id IS
    'Optional binding to a published scale, for a future guideline that states '
    'one. NULL for GU137, which states none: its 3x3 matrix is introduced as '
    '"an example of a 3x3 risk matrix" and is therefore explicitly '
    'non-normative — the document never mandates any matrix, scale or scoring. '
    'A NULL here means the entries'' ratings are the assessor''s own words and '
    'must be shown as such, not silently mapped onto a scale we chose.';
COMMENT ON COLUMN public.risk_assessments.status IS
    'draft | recorded | superseded | void. NOT NULL with no default: a draft '
    'counted as recorded asserts that a duty was discharged, and a recorded '
    'assessment demoted to draft hides one that was.';

-- ── risk_assessment_entries ──────────────────────────────────────────────────
-- One row per identified hazard: the ten Appendix A columns, stored as ten
-- fields of one repeating row rather than as ten checklist items.
CREATE TABLE IF NOT EXISTS public.risk_assessment_entries (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    risk_assessment_id      UUID NOT NULL,   -- composite FK below
    organization_id         UUID NOT NULL,   -- part of the composite FK
    ordinal                 INTEGER NOT NULL,
    hazard                  TEXT NOT NULL,
    affected_persons        TEXT,
    current_controls        TEXT,
    -- The three rating columns, AS THE ASSESSOR RECORDED THEM. See RULE 2.
    risk_probability        TEXT,
    risk_severity           TEXT,
    risk_level              TEXT,
    risk_level_source       TEXT NOT NULL DEFAULT 'assessor_recorded',
    probability_value_id    UUID REFERENCES public.severity_scale_values(id) ON DELETE RESTRICT,
    severity_value_id       UUID REFERENCES public.severity_scale_values(id) ON DELETE RESTRICT,
    level_value_id          UUID REFERENCES public.severity_scale_values(id) ON DELETE RESTRICT,
    further_control_measures TEXT,
    responsible_person      TEXT,
    planned_completion_date DATE,
    completion_date         DATE,
    corrective_action_id    UUID REFERENCES public.corrective_actions(id) ON DELETE RESTRICT,
    notes                   TEXT,
    created_at              TIMESTAMPTZ DEFAULT now(),
    UNIQUE (risk_assessment_id, ordinal)
);

-- Tenancy carried in the key, as everywhere else in this file. CASCADE because
-- an entry is contained by its register — a hazard row with no assessment
-- around it has no assessor, no date and no scope.
ALTER TABLE public.risk_assessment_entries DROP CONSTRAINT IF EXISTS risk_assessment_entries_parent_fk;
ALTER TABLE public.risk_assessment_entries
    ADD CONSTRAINT risk_assessment_entries_parent_fk
    FOREIGN KEY (risk_assessment_id, organization_id)
    REFERENCES public.risk_assessments (id, organization_id)
    ON DELETE CASCADE;

-- RULE 2, MADE UNWRITABLE RATHER THAN MERELY DOCUMENTED. A single-valued CHECK
-- looks odd on purpose: it means there is no legal way to record a risk level
-- that this product derived. GU137's matrix is asymmetric and is NOT a product —
-- High probability x Low impact = Low, while Medium x High = Medium, and the
-- whole Low-probability row is Low regardless of impact — so any engine
-- computing probability x severity disagrees with the published example on
-- several cells while looking entirely plausible. It is the checklist-side twin
-- of §7.12's band-gap trap. If a future guideline ever publishes a NORMATIVE
-- matrix, widen this constraint deliberately and name the guideline in the new
-- value; do not quietly drop it.
ALTER TABLE public.risk_assessment_entries DROP CONSTRAINT IF EXISTS risk_assessment_entries_level_source_check;
ALTER TABLE public.risk_assessment_entries
    ADD CONSTRAINT risk_assessment_entries_level_source_check
    CHECK (risk_level_source = 'assessor_recorded');

ALTER TABLE public.risk_assessment_entries DROP CONSTRAINT IF EXISTS risk_assessment_entries_ordinal_check;
ALTER TABLE public.risk_assessment_entries
    ADD CONSTRAINT risk_assessment_entries_ordinal_check
    CHECK (ordinal > 0);

-- A mapped rating with no verbatim text beside it loses what the assessor
-- actually wrote, which is the only authoritative content on the row.
ALTER TABLE public.risk_assessment_entries DROP CONSTRAINT IF EXISTS risk_assessment_entries_verbatim_check;
ALTER TABLE public.risk_assessment_entries
    ADD CONSTRAINT risk_assessment_entries_verbatim_check
    CHECK ((probability_value_id IS NULL OR coalesce(btrim(risk_probability), '') <> '')
           AND (severity_value_id IS NULL OR coalesce(btrim(risk_severity), '') <> '')
           AND (level_value_id    IS NULL OR coalesce(btrim(risk_level), '') <> ''));

CREATE INDEX IF NOT EXISTS risk_assessment_entries_parent_idx ON public.risk_assessment_entries (risk_assessment_id, ordinal);
CREATE INDEX IF NOT EXISTS risk_assessment_entries_action_idx ON public.risk_assessment_entries (corrective_action_id);
CREATE INDEX IF NOT EXISTS risk_assessment_entries_open_idx
    ON public.risk_assessment_entries (planned_completion_date)
    WHERE completion_date IS NULL AND planned_completion_date IS NOT NULL;

COMMENT ON TABLE public.risk_assessment_entries IS
    'One row per identified hazard — GU137 Appendix A''s ten columns as ten '
    'fields of a repeating row. The row set is unbounded and site-specific, '
    'which is the whole reason this table exists rather than a checklist.';
COMMENT ON COLUMN public.risk_assessment_entries.risk_level IS
    'AS THE ASSESSOR RECORDED IT, verbatim, and NEVER computed from '
    'risk_probability and risk_severity — see '
    'risk_assessment_entries_level_source_check and RULE 2 in the migration '
    'header. Free text, because GU137 mandates no scale: it labels its 3x3 '
    'matrix "an example" and its own column headers do not agree with it, the '
    'register saying "Risk Severity" where the matrix axis says "Impact", a '
    'discrepancy the document never reconciles. Inventing a vocabulary here '
    'would put words in the assessor''s mouth on a document they sign.';
COMMENT ON COLUMN public.risk_assessment_entries.completion_date IS
    'When the further control measure was actually completed, from the '
    'register''s own last column. NULL alongside a planned_completion_date is '
    'an open action, which is the only overdue signal GU137 supports — the '
    'document defines no unacceptable risk level and therefore no failure '
    'condition of its own.';

-- ═════════════════════════════════════════════════════════════════════════════
-- PART 6 — RLS
-- ═════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.severity_scales         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.severity_scale_values   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checklist_templates     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.checklist_items         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inspections             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inspection_findings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_assessments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.risk_assessment_entries ENABLE ROW LEVEL SECURITY;

GRANT ALL ON public.severity_scales         TO service_role;
GRANT ALL ON public.severity_scale_values   TO service_role;
GRANT ALL ON public.checklist_templates     TO service_role;
GRANT ALL ON public.checklist_items         TO service_role;
GRANT ALL ON public.inspections             TO service_role;
GRANT ALL ON public.inspection_findings     TO service_role;
GRANT ALL ON public.risk_assessments        TO service_role;
GRANT ALL ON public.risk_assessment_entries TO service_role;

-- EVERY policy below is scoped TO authenticated, for the reason 022 established
-- and 023 restated: Supabase grants SELECT on new public tables to the anon role
-- by default, so RLS is the only gate and an unqualified `USING (true)` would
-- publish the table to anyone holding the publishable anon key. Both halves of
-- this file are sensitive, in opposite directions. checklist_items IS the
-- encoded product — 368 transcribed GU83 items are the thing a competitor would
-- otherwise have to retype — and inspection_findings is a named client's list of
-- its own violations, which is more damaging than obligations: obligations show
-- where a contractor is exposed, findings show where they have already failed.

-- severity_scales / severity_scale_values: published regulatory vocabulary,
-- readable by every authenticated user, writable only by super_admin. A tenant
-- admin who could reorder a scale or add a value would be editing the framework
-- their own violations are counted under.
DROP POLICY IF EXISTS select_severity_scales ON public.severity_scales;
CREATE POLICY select_severity_scales ON public.severity_scales
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_severity_scales ON public.severity_scales;
CREATE POLICY mutate_severity_scales ON public.severity_scales
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS select_severity_scale_values ON public.severity_scale_values;
CREATE POLICY select_severity_scale_values ON public.severity_scale_values
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_severity_scale_values ON public.severity_scale_values;
CREATE POLICY mutate_severity_scale_values ON public.severity_scale_values
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

-- checklist_templates / checklist_items: global reference content, same shape as
-- guideline_modules in 023. Readable by every authenticated user because an
-- inspector has to see the form to fill it in; writable only by super_admin,
-- because editing an item's text or its severity changes what a client attests
-- to and what their violations count as. §7.1 applies with full force — a wrong
-- item in a sold module is a liability, not a bug.
DROP POLICY IF EXISTS select_checklist_templates ON public.checklist_templates;
CREATE POLICY select_checklist_templates ON public.checklist_templates
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_checklist_templates ON public.checklist_templates;
CREATE POLICY mutate_checklist_templates ON public.checklist_templates
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

DROP POLICY IF EXISTS select_checklist_items ON public.checklist_items;
CREATE POLICY select_checklist_items ON public.checklist_items
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_checklist_items ON public.checklist_items;
CREATE POLICY mutate_checklist_items ON public.checklist_items
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

-- inspections / inspection_findings: tenant-scoped, and writable by operators as
-- well as admins. That is a deliberate divergence from 023's obligations and
-- certificates, and it is not a relaxation of §7.9. An inspection is FIELD DATA
-- ENTRY performed by the person walking the building — the same act as logging a
-- reading, which 016 and schema_rls.sql already grant to operators — whereas an
-- obligation is regulatory policy and a certificate is third-party evidence
-- about the person holding it. What operators still cannot do is edit the form
-- they are answering: templates, items and severities are super_admin above, so
-- an operator can record any answer but cannot change the question or what
-- failing it counts as.
DROP POLICY IF EXISTS select_inspections ON public.inspections;
CREATE POLICY select_inspections ON public.inspections
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_inspections ON public.inspections;
CREATE POLICY mutate_inspections ON public.inspections
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

DROP POLICY IF EXISTS select_inspection_findings ON public.inspection_findings;
CREATE POLICY select_inspection_findings ON public.inspection_findings
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_inspection_findings ON public.inspection_findings;
CREATE POLICY mutate_inspection_findings ON public.inspection_findings
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

-- risk_assessments / risk_assessment_entries: same reasoning, and GU137 is
-- explicit that the duty-holder carries out and records the assessment — it is
-- their document, not the regulator's form. Auditors read via the tenant SELECT
-- and write nothing, which is the read-only posture schema_rls.sql gives them
-- everywhere else.
DROP POLICY IF EXISTS select_risk_assessments ON public.risk_assessments;
CREATE POLICY select_risk_assessments ON public.risk_assessments
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_risk_assessments ON public.risk_assessments;
CREATE POLICY mutate_risk_assessments ON public.risk_assessments
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

DROP POLICY IF EXISTS select_risk_assessment_entries ON public.risk_assessment_entries;
CREATE POLICY select_risk_assessment_entries ON public.risk_assessment_entries
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_risk_assessment_entries ON public.risk_assessment_entries;
CREATE POLICY mutate_risk_assessment_entries ON public.risk_assessment_entries
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'operator'))
  );

COMMIT;
