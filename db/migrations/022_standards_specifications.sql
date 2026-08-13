BEGIN;

-- ── Migration 022: standards registry + specification sets ────────────────────
-- The first migration of the DM compliance generalisation (DM_COMPLIANCE_SCOPING.md
-- §4.1–4.2, §5 step 1). It creates structure only; nothing reads these tables
-- until core/specs.py lands in step 2, so applying it changes no behaviour.
--
-- WHY THIS EXISTS. Compliance limits live in core/constants.py as a Python dict
-- (COMPLIANCE_LIMITS, ten parameters, lagoon scope). That was right for one
-- water body judged against one standard. It does not survive the product this
-- is becoming: Dubai Municipality publishes ~80 technical guidelines, each with
-- its own limits, and each is intended to be a sellable module. Limits therefore
-- have to be data — seeded, versioned, and overridable per organisation —
-- rather than a dict that requires a deploy to extend.
--
-- WHAT THE GAP IS TODAY. assets.scope (019) already permits 'facilities'
-- alongside 'lagoon', and core/report_types.py documents the facilities scope as
-- governed by DM technical guidelines. But no facilities limit set exists
-- anywhere in the code: COMPLIANCE_LIMITS is lagoon-only and
-- core/calculations.py reads from it exclusively. A facilities result is judged
-- today either by the laboratory's own verbatim `specification` string on
-- lab_results, or not at all. This migration is where that second set finally
-- has somewhere to live — and, more importantly, where the eightieth one will.
--
-- ORDER OF SEEDING. Deliberately no seed data here. The GU44 edition facts and
-- the ten lagoon limits both already exist in Python (core/standards.py
-- KNOWN_EDITIONS, core/constants.py COMPLIANCE_LIMITS), and copying them into
-- SQL would create a second source of truth that drifts silently — the exact
-- failure this migration exists to end. Seeding is done by a Python seeder that
-- reads those modules, so the values can only ever have one origin.
--
-- DEPENDENCIES. `organizations` comes from db/schema.sql, not from a numbered
-- migration. There is no hard dependency on 019 — no foreign key — but this file
-- duplicates the scope vocabulary 019 established on assets.scope, and the two
-- CHECK constraints must be widened together (see specification_sets below).
-- Run in the Supabase SQL editor. Reversible: 022_standards_specifications_down.sql.

-- ── standards ────────────────────────────────────────────────────────────────
-- One row per EDITION of a guideline, not per guideline. A certificate must be
-- judged against the edition in force when it was sampled, so editions are kept
-- as a chain (supersedes_id) rather than as a single mutable "current" row.
-- This replaces the flat current_issue/superseded_issue pair in
-- core/standards.py, which can only express one hop of history.
--
-- Global reference data, NOT org-scoped: DM-HSD-GU44-LCWS2 V.6 is the same
-- document for every tenant. Organisation-specific interpretation belongs on
-- specification_sets below, never here.
CREATE TABLE IF NOT EXISTS public.standards (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    authority            TEXT NOT NULL DEFAULT 'DM',
    code                 TEXT NOT NULL,   -- as laboratories print it: 'DM-HSD-GU44-LCWS2'
    guideline_no         INTEGER,         -- 44. NULL for documents with no GU number
    title                TEXT NOT NULL,
    version              TEXT NOT NULL,   -- 'V.6' — verbatim from the document
    issued_on            DATE NOT NULL,
    supersedes_id        UUID REFERENCES public.standards(id) ON DELETE RESTRICT,
    superseded_issued_on DATE,            -- predecessor known only by date, not held as a row
    source_url           TEXT,
    language             TEXT NOT NULL DEFAULT 'en',
    verified_by          TEXT,            -- who read the published PDF
    verified_on          DATE,
    created_at           TIMESTAMPTZ DEFAULT now(),
    UNIQUE (authority, code, version, language)
);

ALTER TABLE public.standards DROP CONSTRAINT IF EXISTS standards_language_check;
ALTER TABLE public.standards
    ADD CONSTRAINT standards_language_check
    CHECK (language IN ('en', 'ar', 'both'));

-- A standard cannot supersede itself. Longer cycles are not preventable in a
-- CHECK; the seeder is responsible for not building one.
ALTER TABLE public.standards DROP CONSTRAINT IF EXISTS standards_no_self_supersede_check;
ALTER TABLE public.standards
    ADD CONSTRAINT standards_no_self_supersede_check
    CHECK (supersedes_id IS NULL OR supersedes_id <> id);

-- The two ways of naming a predecessor are mutually exclusive: if we hold the
-- previous edition as a row, point at it; if we only know the date it was
-- issued, record that. Both set would be two answers to one question.
ALTER TABLE public.standards DROP CONSTRAINT IF EXISTS standards_one_predecessor_check;
ALTER TABLE public.standards
    ADD CONSTRAINT standards_one_predecessor_check
    CHECK (supersedes_id IS NULL OR superseded_issued_on IS NULL);

-- Verification is one fact, not two. Half of it recorded is worse than none:
-- it reads as verified while naming nobody, or names somebody with no date.
ALTER TABLE public.standards DROP CONSTRAINT IF EXISTS standards_verified_pair_check;
ALTER TABLE public.standards
    ADD CONSTRAINT standards_verified_pair_check
    CHECK ((verified_by IS NULL) = (verified_on IS NULL));

-- Currency is derived as "the edition nothing supersedes". That derivation is
-- only sound if the chain cannot FORK — two editions both claiming the same
-- predecessor would leave two heads and therefore two "current" editions, and
-- citation_is_stale() would then fire or stay silent arbitrarily. Partial so
-- that any number of chain roots (supersedes_id NULL) remain legal.
CREATE UNIQUE INDEX IF NOT EXISTS standards_supersedes_unique_idx
    ON public.standards (supersedes_id) WHERE supersedes_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS standards_guideline_idx ON public.standards (guideline_no);

COMMENT ON TABLE public.standards IS
    'Published regulatory guideline EDITIONS. Global reference data shared by all '
    'tenants — never org-scoped. One row per edition, chained via supersedes_id, '
    'so a certificate can be judged against the edition in force on its sampling '
    'date rather than against whatever is newest.';
COMMENT ON COLUMN public.standards.authority IS
    'Issuing body, defaulted to DM. Present from day one specifically so Abu Dhabi '
    '(OSHAD/ADPHC) or Sharjah can be added later as data rather than as a '
    'migration across every standard, specification set and report. All seeded '
    'content is Dubai Municipality today.';
COMMENT ON COLUMN public.standards.code IS
    'The document code EXACTLY as laboratories print it on certificates, because '
    'matching a citation is the only way to detect a stale one. Do not normalise '
    'punctuation or case here; normalise at lookup time.';
COMMENT ON COLUMN public.standards.version IS
    'Verbatim from the document (''V.6'', not ''6''). Part of the uniqueness key '
    'along with language: two editions of one code differ by version and issue '
    'date, and the same edition may be published separately in English and Arabic.';
COMMENT ON COLUMN public.standards.supersedes_id IS
    'The edition this one replaced, forming a chain back through history. NULL '
    'means this is the earliest edition held — NOT that it is current. Currency is '
    'derived by finding the edition nothing else supersedes, so never infer '
    '"current" from this column alone. ON DELETE RESTRICT, not SET NULL: nulling '
    'a link would splice the chain, leaving the deleted row''s predecessor '
    'superseded by nothing and therefore falsely current alongside the real head.';
COMMENT ON COLUMN public.standards.superseded_issued_on IS
    'Issue date of the predecessor when that edition is NOT held as a row of its '
    'own — the state core/standards.py is in today, where superseded_issue is a '
    'bare date and the predecessor''s version string is unknown. Recording the '
    'date here is honest; inventing a placeholder row with a guessed version to '
    'point supersedes_id at would violate the rule that nothing is entered '
    'without the document in front of you, and UNIQUE would then lock the guess in.';
COMMENT ON COLUMN public.standards.verified_by IS
    'Who confirmed these facts against the published PDF, and verified_on when. '
    'Free text, not a user FK: verification is done by the vendor and the person '
    'may not be a row in user_profiles. A standard with no verification recorded '
    'must not drive a staleness warning to a client — a wrong "your citation is '
    'out of date" sends them to argue with their laboratory over nothing. See the '
    'rule already stated in core/standards.py.';

-- ── specification_sets ───────────────────────────────────────────────────────
-- A named collection of limits: what "compliant" means for a class of asset
-- under a given standard. organization_id NULL = built-in and shared; non-NULL =
-- that organisation's override.
CREATE TABLE IF NOT EXISTS public.specification_sets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id  UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    standard_id      UUID REFERENCES public.standards(id) ON DELETE RESTRICT,
    key              TEXT NOT NULL,      -- 'lagoon_dm_water', 'facilities_potable_tank'
    label            TEXT NOT NULL,
    applies_to_scope TEXT,
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);

-- Mirrors assets.scope (019). These two CHECKs must be widened together: a scope
-- legal on an asset but illegal on a specification set is an asset that can
-- never be judged.
ALTER TABLE public.specification_sets DROP CONSTRAINT IF EXISTS specification_sets_scope_check;
ALTER TABLE public.specification_sets
    ADD CONSTRAINT specification_sets_scope_check
    CHECK (applies_to_scope IS NULL OR applies_to_scope IN ('lagoon', 'facilities'));

-- Uniqueness of `key` needs TWO indexes, not one composite UNIQUE. In Postgres
-- NULLs are distinct in a unique constraint, so UNIQUE (organization_id, key)
-- would happily accept two built-in sets both keyed 'lagoon_dm_water' with a
-- NULL organization_id — precisely the collision that must not happen, since a
-- resolver looking up a built-in key would then get an arbitrary one of them.
-- Split into a partial index per case so both halves are actually enforced.
CREATE UNIQUE INDEX IF NOT EXISTS specification_sets_builtin_key_idx
    ON public.specification_sets (key) WHERE organization_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS specification_sets_org_key_idx
    ON public.specification_sets (organization_id, key) WHERE organization_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS specification_sets_standard_idx
    ON public.specification_sets (standard_id);

COMMENT ON TABLE public.specification_sets IS
    'A named set of limits defining what compliant means for a class of asset. '
    'organization_id NULL = built-in and shared by all tenants; non-NULL = that '
    'organisation''s override. Replaces COMPLIANCE_LIMITS in core/constants.py, '
    'which could only ever hold one set.';
COMMENT ON COLUMN public.specification_sets.standard_id IS
    'The guideline edition these limits were read from. ON DELETE RESTRICT: a '
    'standard with limits hanging off it must not vanish and silently leave those '
    'limits attributed to nothing. Nullable because client-specific sets exist '
    'that derive from no single published document.';
COMMENT ON COLUMN public.specification_sets.applies_to_scope IS
    'Mirrors assets.scope. NULL means the set is not scope-restricted and must be '
    'selected explicitly. Never default this — see the assets.scope comment in '
    '019 on why a defaulted scope produces a confident wrong verdict.';

-- ── spec_limits ──────────────────────────────────────────────────────────────
-- One row per parameter within a set. min_val/max_val carry the same semantics
-- as core/constants.py ComplianceLimit: NULL means unbounded on that side.
CREATE TABLE IF NOT EXISTS public.spec_limits (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    spec_set_id     UUID NOT NULL REFERENCES public.specification_sets(id) ON DELETE CASCADE,
    parameter_key   TEXT NOT NULL,      -- 'ph', 'legionella_pneumophila', 'wbgt'
    parameter_label TEXT NOT NULL,      -- 'pH', 'Legionella pneumophila'
    unit            TEXT,
    min_val         NUMERIC,            -- NULL = no lower bound
    max_val         NUMERIC,            -- NULL = no upper bound
    min_inclusive   BOOLEAN NOT NULL,   -- deliberately no DEFAULT — see comment
    max_inclusive   BOOLEAN NOT NULL,
    display         TEXT NOT NULL,      -- '6.0 – 9.0', '< 100' — human-readable, verbatim
    qualifier_rule  TEXT NOT NULL DEFAULT 'bound',
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE (spec_set_id, parameter_key)
);

-- A limit bounded on neither side judges nothing and would silently PASS every
-- value put to it. If a parameter is genuinely recorded but not judged, it does
-- not belong in a specification set at all.
ALTER TABLE public.spec_limits DROP CONSTRAINT IF EXISTS spec_limits_bounded_check;
ALTER TABLE public.spec_limits
    ADD CONSTRAINT spec_limits_bounded_check
    CHECK (min_val IS NOT NULL OR max_val IS NOT NULL);

ALTER TABLE public.spec_limits DROP CONSTRAINT IF EXISTS spec_limits_range_check;
ALTER TABLE public.spec_limits
    ADD CONSTRAINT spec_limits_range_check
    CHECK (min_val IS NULL OR max_val IS NULL OR min_val <= max_val);

ALTER TABLE public.spec_limits DROP CONSTRAINT IF EXISTS spec_limits_qualifier_rule_check;
ALTER TABLE public.spec_limits
    ADD CONSTRAINT spec_limits_qualifier_rule_check
    CHECK (qualifier_rule IN ('bound', 'detect_fails', 'unassessable'));

CREATE INDEX IF NOT EXISTS spec_limits_parameter_idx ON public.spec_limits (parameter_key);

COMMENT ON COLUMN public.spec_limits.min_inclusive IS
    'Whether the bound itself passes: TRUE means >= min_val, FALSE means > min_val. '
    'NOT NULL with NO DEFAULT, on purpose. COMPLIANCE_LIMITS cannot express this — '
    'it stores ("do", 4.0, None, "> 4.0"), so strictness survives only inside the '
    'human-readable display string, and a value of exactly 4.0 passes or fails '
    'depending on which call site judges it. Since qualifier_rule = ''bound'' '
    'reasons explicitly about whether a bound is met, the operator has to be data '
    'rather than prose. There is no safe default: guessing inclusive silently '
    'passes a value at a "< 50" ceiling, guessing exclusive silently fails a value '
    'at an inclusive one. The seeder must state it per parameter, read from the '
    'published guideline.';
COMMENT ON COLUMN public.spec_limits.display IS
    'The limit as a human reads it on a report (''6.0 – 9.0'', ''< 100 cfu/L''). '
    'Kept alongside min_val/max_val rather than formatted from them, because a '
    'published guideline''s own wording is what a client quotes back to the '
    'regulator, and reconstructing it loses that. It is OUTPUT ONLY — never parse '
    'it to recover strictness; that is what min_inclusive/max_inclusive are for.';
COMMENT ON COLUMN public.spec_limits.qualifier_rule IS
    'How a NON-NUMERIC laboratory result is judged against this limit. Necessary '
    'because lab_results deliberately preserves verbatim values — ''<1'', ''Not '
    'Detected'', ''Absent/100mL'' — and migration 016 forbids coercing them to 0: '
    'a below-LOQ non-detect is regulatorily distinct from a measured zero. '
    'Without a rule per limit, every call site improvises, and they will not '
    'agree. Implemented by core/specs.py, and must stay consistent with the '
    'existing printed-spec logic in ingestion/gates.py. '
    'bound (default): judge ''<X'' by X, the upper bound of what the true value '
    'could be. Passes only when X itself satisfies the limit — ''<4 cfu/L'' '
    'against ''< 100'' is a genuine PASS because the whole possible range is '
    'compliant, whereas ''<4'' against ''< 1'' proves nothing and yields '
    'NOT_ASSESSED rather than a fabricated FAIL. '
    'detect_fails: any detection fails, so ''ND''/''Absent'' passes and any '
    'quantified value fails. For parameters where presence alone is the breach. '
    'unassessable: never judge a qualified value on this parameter; always '
    'NOT_ASSESSED. The honest choice when the guideline does not say.';

-- ── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.standards          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.specification_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spec_limits        ENABLE ROW LEVEL SECURITY;

GRANT ALL ON public.standards          TO service_role;
GRANT ALL ON public.specification_sets TO service_role;
GRANT ALL ON public.spec_limits        TO service_role;

-- EVERY policy below is scoped TO authenticated. This is the first table set in
-- the repo whose read policy would otherwise be unconditional, and Supabase
-- grants SELECT on new public tables to the anon role by default — so RLS is the
-- only gate, and `USING (true)` without a role restriction would publish the
-- entire built-in limit library to anyone holding the publishable anon key. The
-- seeded limit tables ARE the product under a per-guideline commercial model.
-- Existing repo policies avoid this only incidentally, because
-- get_user_organization() returns NULL for an unauthenticated caller.

-- standards: readable by any authenticated user (it is regulatory reference
-- data), writable only by super_admin. A tenant admin must not be able to edit
-- the published record of what a guideline says.
DROP POLICY IF EXISTS select_standards ON public.standards;
CREATE POLICY select_standards ON public.standards
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_standards ON public.standards;
CREATE POLICY mutate_standards ON public.standards
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

-- specification_sets: built-in sets (organization_id IS NULL) are readable by
-- all and writable only by super_admin; org sets follow the standard tenant
-- pattern from schema_rls.sql. Note this admits 'admin' but not 'operator',
-- unlike the comparable policies in 016 and schema_rls.sql: a specification set
-- is regulatory policy, not field data entry, and an operator logging readings
-- has no business redefining what compliant means.
DROP POLICY IF EXISTS select_specification_sets ON public.specification_sets;
CREATE POLICY select_specification_sets ON public.specification_sets
  FOR SELECT TO authenticated USING (
    organization_id IS NULL
    OR organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_specification_sets ON public.specification_sets;
CREATE POLICY mutate_specification_sets ON public.specification_sets
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id IS NOT NULL
        AND organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
  );

-- spec_limits has no organization_id and is scoped through its parent set,
-- exactly as lab_results is scoped through lab_samples (016). The
-- IS NOT NULL on the mutate path matters: without it a user whose profile has a
-- NULL organization_id would match built-in rows via NULL = NULL, and a tenant
-- admin could promote a private override into a global built-in by nulling it.
DROP POLICY IF EXISTS select_spec_limits ON public.spec_limits;
CREATE POLICY select_spec_limits ON public.spec_limits
  FOR SELECT TO authenticated USING (
    spec_set_id IN (
      SELECT id FROM public.specification_sets
      WHERE organization_id IS NULL OR organization_id = public.get_user_organization()
    )
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_spec_limits ON public.spec_limits;
CREATE POLICY mutate_spec_limits ON public.spec_limits
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (spec_set_id IN (
          SELECT id FROM public.specification_sets
          WHERE organization_id IS NOT NULL
            AND organization_id = public.get_user_organization()
        )
        AND public.get_user_role() = 'admin')
  );

COMMIT;
