BEGIN;

-- ── Migration 023: laboratories, modules, entitlements, obligations, certificates
-- The second and final schema migration of Phase 1 (DM_COMPLIANCE_SCOPING.md
-- §4.3, §4.4, §4.5, §4.7). 022 gave the product something to judge AGAINST;
-- this gives it something to be judged, someone permitted to produce the
-- evidence, and a commercial boundary around the whole of it. Structure only —
-- nothing reads these tables until the Phase 1 services land, so applying it
-- changes no behaviour.
--
-- WHY THIS EXISTS. Today the app knows what a certificate SAID. It does not know
-- that a certificate was DUE AND NEVER ARRIVED. For an FM contractor that
-- inversion is the entire value proposition: the risk that ends a contract is
-- the missing test, not the failed one (§4.3). `obligations` is the table that
-- makes an absence visible. Everything else here exists to stop that table from
-- lying — `laboratories` because evidence from an unaccredited lab is not
-- evidence (§4.7), `guideline_modules` because not every guideline can produce a
-- verdict at all (§7.12), and `organization_entitlements` because an obligation
-- nobody is paying to monitor is a promise the product cannot keep (§4.5).
--
-- THE GOVERNING RULE (§4.5). AN OBLIGATION MAY ONLY EXIST FOR AN ENTITLED
-- MODULE. It is enforced here as a NOT NULL composite foreign key from
-- obligations to organization_entitlements, not as application logic, because
-- that one constraint is doing three jobs at once and all three break if it can
-- be bypassed even occasionally:
--
--   * onboarding — the client ticking modules IS the act of creating the
--     obligation registry; there is no second data-entry step to forget;
--   * billing — the count of active entitlements is the invoice, so an
--     obligation being monitored is by construction an obligation being paid
--     for, and no module can be monitored for free by accident;
--   * monitoring scope — the answer to "what does this app watch for this
--     client" is a join, not a judgement call, which is what makes the
--     un-monitored remainder computable and therefore sellable (the
--     self-generating upsell in §4.5).
--
-- An obligation created without an entitlement would be monitored and unbilled;
-- an entitlement with no obligations is a client paying for silence. The schema
-- refuses the first outright and the second is visible as an empty join.
--
-- DELETION POLICY (§7.5). Entitlement is a commercial state, not a retention
-- policy. Un-ticking a module must stop MONITORING while retaining HISTORY:
-- a regulator asking what was tested in 2026 must get the same answer in 2028
-- whether or not the module is still on the invoice. So every FK whose deletion
-- would orphan or destroy compliance history is ON DELETE RESTRICT —
-- entitlement, module, standard, asset, subject, laboratory. Deactivation is
-- setting `active_until`, never DELETE. The one deliberate exception is
-- organization_id, which stays ON DELETE CASCADE to match every other table in
-- the repo: removing a tenant removes the tenant's data, which is a different
-- act with a different authority behind it.
--
-- DEPENDENCIES. Requires `organizations` and `sites` (db/schema.sql),
-- `user_profiles` and the get_user_* helpers (db/schema_rls.sql), `assets`
-- (010), and `standards` / `specification_sets` (022). Run in the Supabase SQL
-- editor after 022. Reversible: 023_obligations_entitlements_down.sql.
--
-- CARRIED FORWARD FROM 022. Four lessons that cost something to learn and are
-- applied throughout this file rather than rediscovered:
--   1. EVERY policy below is scoped `TO authenticated`. Supabase grants SELECT on
--      new public tables to the `anon` role by default, so RLS is the only gate,
--      and an unrestricted `USING (true)` publishes the table to anyone holding
--      the publishable anon key. That matters more here than in 022: under
--      per-guideline pricing `guideline_modules` IS the price list and
--      `obligations` IS the client's compliance posture.
--   2. NO DEFAULT on a column where guessing is unsafe. A default is a silent
--      assertion made on the operator's behalf; where the wrong assertion is a
--      wrong compliance answer, the insert must fail instead. See
--      obligations.status and organization_entitlements.active_from.
--   3. `coalesce(col,'') = 'x'` rather than `col = 'x'` inside a CHECK. With a
--      NULL column a bare comparison yields NULL, and Postgres accepts any CHECK
--      that is not FALSE — so the constraint silently permits exactly what it
--      was written to forbid. Every conditional CHECK below is written this way.
--   4. The `_down` contains NO DROP POLICY statements. `DROP POLICY IF EXISTS p
--      ON t` tolerates a missing policy but NOT a missing table; against an
--      absent table it raises 42P01 and aborts the whole transactional rollback,
--      in precisely the partial-state case such lines appear to protect against.

-- ── laboratories ─────────────────────────────────────────────────────────────
-- Who is permitted to produce the evidence (§4.7). Dubai Municipality accredits
-- the laboratories and an FM contractor may not self-test, so every quantitative
-- obligation is discharged by an independent accredited lab or it is not
-- discharged at all. Evidence from a lab that was not accredited — or whose
-- accreditation had lapsed ON THE SAMPLING DATE — is rejected by DM, and today
-- nothing in the app can see that failure coming.
--
-- Global reference data, NOT org-scoped, for the same reason as `standards`:
-- Wimpey Laboratories' accreditation is one fact about the world, not one fact
-- per tenant. Two tenants holding contradictory accreditation windows for one
-- laboratory is a way to lose an argument with a regulator.
CREATE TABLE IF NOT EXISTS public.laboratories (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   TEXT NOT NULL,          -- 'Wimpey Laboratories'
    authority              TEXT NOT NULL DEFAULT 'DM',
    accreditation_no       TEXT,
    accredited_from        DATE,
    accredited_until       DATE,                   -- NULL = open-ended, see comment
    scope_of_accreditation TEXT[] NOT NULL,        -- parameter keys / test families
    status                 TEXT NOT NULL,          -- deliberately no DEFAULT
    contact_email          TEXT,
    notes                  TEXT,
    verified_by            TEXT,
    verified_on            DATE,
    created_at             TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.laboratories DROP CONSTRAINT IF EXISTS laboratories_status_check;
ALTER TABLE public.laboratories
    ADD CONSTRAINT laboratories_status_check
    CHECK (status IN ('active', 'lapsed', 'withdrawn'));

ALTER TABLE public.laboratories DROP CONSTRAINT IF EXISTS laboratories_window_check;
ALTER TABLE public.laboratories
    ADD CONSTRAINT laboratories_window_check
    CHECK (accredited_from IS NULL OR accredited_until IS NULL
           OR accredited_from <= accredited_until);

-- An 'active' laboratory with no start date cannot be checked against a sampling
-- date at all, so it would pass or fail every historical sample arbitrarily. If
-- the window is unknown, the row is not 'active' yet. coalesce() because status
-- being NULL would otherwise make this CHECK evaluate to NULL and be accepted.
ALTER TABLE public.laboratories DROP CONSTRAINT IF EXISTS laboratories_active_needs_window_check;
ALTER TABLE public.laboratories
    ADD CONSTRAINT laboratories_active_needs_window_check
    CHECK (coalesce(status, '') <> 'active' OR accredited_from IS NOT NULL);

-- Same both-or-neither discipline as standards.verified_* in 022: half a
-- provenance record reads as verified while naming nobody.
ALTER TABLE public.laboratories DROP CONSTRAINT IF EXISTS laboratories_verified_pair_check;
ALTER TABLE public.laboratories
    ADD CONSTRAINT laboratories_verified_pair_check
    CHECK ((verified_by IS NULL) = (verified_on IS NULL));

-- Duplicate laboratory rows are worse than missing ones: evidence splits across
-- two ids and a lapsed accreditation on one of them is invisible from the other.
-- lower(name) because the same lab is printed with varying case on certificates.
CREATE UNIQUE INDEX IF NOT EXISTS laboratories_name_idx
    ON public.laboratories (authority, lower(name));
CREATE UNIQUE INDEX IF NOT EXISTS laboratories_accreditation_no_idx
    ON public.laboratories (authority, accreditation_no) WHERE accreditation_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS laboratories_status_idx ON public.laboratories (status);
CREATE INDEX IF NOT EXISTS laboratories_scope_idx
    ON public.laboratories USING GIN (scope_of_accreditation);

COMMENT ON TABLE public.laboratories IS
    'DM-accredited laboratories permitted to produce quantitative evidence '
    '(§4.7). Global reference data shared by all tenants — never org-scoped. '
    'The FM contractor may not self-test, so this registry is what makes a '
    'submitted result admissible or inadmissible.';
COMMENT ON COLUMN public.laboratories.scope_of_accreditation IS
    'The parameter keys or test families this laboratory may certify — matching '
    'spec_limits.parameter_key where the scope is expressed per parameter. An '
    'ARRAY rather than a boolean because accreditation is scoped by test family: '
    'a lab accredited for chemistry but not for Legionella enumeration cannot '
    'certify a GU44 result, so the gate must check the PARAMETER, not merely the '
    'laboratory. NOT NULL with no default, and an EMPTY array is legal and means '
    '"may certify nothing" — the honest state for a lab whose scope document has '
    'not been read. Defaulting to empty would make silence look deliberate; '
    'defaulting to anything else would grant scope nobody verified. The exact '
    'shape is listed as still-open in §8: confirm against DM''s published scope '
    'documents before any code depends on the array being parameter keys rather '
    'than family names.';
COMMENT ON COLUMN public.laboratories.accredited_until IS
    'NULL means the accreditation has no published end date, NOT that it is '
    'expired. laboratory_accredited_on() treats NULL as open-ended, which is why '
    'status must be moved to lapsed/withdrawn explicitly when that is learnt — '
    'an open-ended window plus a stale status is a lab that never expires.';
COMMENT ON COLUMN public.laboratories.status IS
    'active | lapsed | withdrawn. TODAY''s standing, deliberately with NO DEFAULT '
    'and distinct from the date window, which is the historical fact. Never use '
    'this column to judge a past sample — a certificate issued while the lab was '
    'accredited stays valid after the accreditation lapses. Use '
    'laboratory_accredited_on(id, sampling_date) for that, always.';
COMMENT ON COLUMN public.laboratories.verified_by IS
    'Who confirmed this accreditation against DM''s published record, and '
    'verified_on when. Same rule as standards.verified_by (022) and §7.1: an '
    'unverified row must not drive a rejection notice to a client. Wrongly '
    'telling a contractor their laboratory is not accredited is a serious '
    'accusation about a third party.';

-- Accreditation validity is a question about a DATE, not about today.
-- This is the same reasoning core/standards.py::citation_is_stale already
-- applies to guideline editions and it is implemented the same way: the caller
-- supplies the date the sample was TAKEN, and the answer must not change as
-- time passes. Re-running last year's report must reproduce last year's verdict.
--
-- p_parameter, when given, additionally requires the parameter to fall inside
-- scope_of_accreditation, because a lab may be accredited on the date and still
-- not permitted for that test family.
--
-- JUDGEMENT CALL, flagged rather than buried: 'withdrawn' returns FALSE for
-- every date, whereas 'lapsed' defers entirely to the window. The reading is
-- that a lapse is the ordinary expiry of a window that was valid while it ran,
-- whereas a withdrawal is a revocation that calls the work itself into question
-- retrospectively. §4.7 does not say. If DM's meaning turns out to be otherwise,
-- change it HERE — every gate goes through this function precisely so that the
-- rule has one home.
CREATE OR REPLACE FUNCTION public.laboratory_accredited_on(
    p_laboratory_id UUID,
    p_sampled_on    DATE,
    p_parameter     TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.laboratories l
        WHERE l.id = p_laboratory_id
          AND p_sampled_on IS NOT NULL
          AND l.status <> 'withdrawn'
          AND l.accredited_from IS NOT NULL
          AND l.accredited_from <= p_sampled_on
          AND (l.accredited_until IS NULL OR l.accredited_until >= p_sampled_on)
          AND (p_parameter IS NULL OR p_parameter = ANY (l.scope_of_accreditation))
    );
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION public.laboratory_accredited_on(UUID, DATE, TEXT) IS
    'Was this laboratory accredited for this parameter on the SAMPLING date? '
    'Returns FALSE — never NULL — for an unknown laboratory, a NULL sampling '
    'date or a laboratory with no start date, so a caller cannot get a '
    'permissive answer out of missing data. The ingestion gate (§4.7) must treat '
    'FALSE as "cannot be assessed / rejected", not as a compliance failure of '
    'the client: the defect is in the evidence, not in the water.';

-- ── guideline_modules ────────────────────────────────────────────────────────
-- The catalogue: every guideline that is, or could be, sold as a module (§4.5).
-- Global reference data — the catalogue is the same for everyone; what differs
-- per tenant is which rows they have bought, which is organization_entitlements.
CREATE TABLE IF NOT EXISTS public.guideline_modules (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    standard_id        UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    key                TEXT NOT NULL UNIQUE,   -- 'gu44_water_systems'
    label              TEXT NOT NULL,
    category           TEXT,
    module_kind        TEXT NOT NULL,          -- §7.12 — no default, see comment
    obligation_type    TEXT,
    list_price_monthly NUMERIC(12,2),
    currency           TEXT NOT NULL DEFAULT 'AED',
    status             TEXT NOT NULL DEFAULT 'coming_soon',
    provenance         TEXT NOT NULL DEFAULT 'unverified',
    notes              TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);

-- THE MOST IMPORTANT CONSTRAINT IN THIS FILE (§7.12). Reading the first four DM
-- documents properly turned up a distinction the model did not carry: not every
-- guideline can produce a verdict.
--
--   compliance  — COMPLIANT / NON-COMPLIANT against a stated limit (GU119, GU81)
--   monitoring  — a risk band and a control obligation, but NO verdict (GU38)
--   process     — that a procedure was followed; nothing is measured (GU34)
--   delegating  — nothing on its own; the limit lives elsewhere (GU10 → ASHRAE 62.1)
--   unusable    — nothing; the document contradicts itself (GU141)
--
-- All five are sellable — an FM contractor genuinely needs to track GU38
-- obligations — but THEY ARE NOT THE SAME PRODUCT. A report claiming compliance
-- against a guideline that sets no compliance limit is a MISREPRESENTATION TO A
-- REGULATOR. That is the §7.4 failure arriving from an unexpected direction: not
-- the wrong limits applied to an asset, but a verdict rendered where the source
-- document authorises none. The resolver MUST refuse to emit a verdict for any
-- module whose kind is not 'compliance'; a NOT_ASSESSED with the reason shown is
-- the only honest output for the other four.
--
-- NOT NULL with no default, on purpose. Defaulting to 'compliance' manufactures
-- authority the document does not have; defaulting to anything else silently
-- disables modules that should judge. The kind is a reading of the document and
-- has to be stated by whoever read it. Retrofitting this after reports exist
-- means reissuing them.
ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_kind_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_kind_check
    CHECK (module_kind IN ('compliance', 'monitoring', 'process', 'delegating', 'unusable'));

ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_status_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_status_check
    CHECK (status IN ('available', 'coming_soon', 'retired'));

ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_provenance_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_provenance_check
    CHECK (provenance IN ('verified', 'unverified'));

-- §7.1 and decision 5, the narrow verified catalogue, enforced in the schema
-- rather than by good intentions: a module cannot go ON SALE until somebody has
-- read the published DM PDF. A wrong limit in a sold module is a liability, not
-- a bug. Both sides coalesce'd — a NULL on either would make the comparison NULL
-- and Postgres accepts a CHECK that is not FALSE, which would leave this
-- constraint permitting the exact thing it names.
ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_verified_to_sell_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_verified_to_sell_check
    CHECK (coalesce(status, '') <> 'available' OR coalesce(provenance, '') = 'verified');

-- An 'unusable' guideline (GU141 contradicts itself) cannot be sold at all.
-- There is nothing to deliver and nothing a report could truthfully say.
ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_unusable_not_sold_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_unusable_not_sold_check
    CHECK (coalesce(status, '') <> 'available' OR coalesce(module_kind, '') <> 'unusable');

ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_obligation_type_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_obligation_type_check
    CHECK (obligation_type IS NULL
           OR obligation_type IN ('sampling', 'examination', 'inspection', 'competency'));

ALTER TABLE public.guideline_modules DROP CONSTRAINT IF EXISTS guideline_modules_price_check;
ALTER TABLE public.guideline_modules
    ADD CONSTRAINT guideline_modules_price_check
    CHECK (list_price_monthly IS NULL OR list_price_monthly >= 0);

CREATE INDEX IF NOT EXISTS guideline_modules_standard_idx ON public.guideline_modules (standard_id);
CREATE INDEX IF NOT EXISTS guideline_modules_status_idx   ON public.guideline_modules (status, module_kind);

COMMENT ON TABLE public.guideline_modules IS
    'The sellable catalogue: one row per guideline module (§4.5). The unit of '
    'sale is a module, not a site — base platform fee plus per-module add-on '
    '(decision 4), replacing billing.py''s site-count tiers. Global reference '
    'data; what a tenant has bought lives in organization_entitlements.';
COMMENT ON COLUMN public.guideline_modules.module_kind IS
    'What a report is permitted to CLAIM for this module (§7.12): compliance | '
    'monitoring | process | delegating | unusable. The resolver must emit a '
    'verdict ONLY for ''compliance''. Claiming compliance against a guideline '
    'that sets no compliance limit is a misrepresentation to a regulator, so '
    'this column is a legal boundary and not a UI hint. No default: the kind is '
    'a reading of the published document and must be stated by whoever read it.';
COMMENT ON COLUMN public.guideline_modules.standard_id IS
    'ON DELETE RESTRICT: a standard underneath a sold module must not vanish and '
    'leave paying clients entitled to a module that cites nothing. NOT NULL '
    'because a module IS a guideline made sellable — without the guideline there '
    'is no product, only a line on an invoice.';
COMMENT ON COLUMN public.guideline_modules.status IS
    'available | coming_soon | retired. Defaults to coming_soon, which is the '
    'safe direction: a new row is visible as a roadmap item and cannot be sold '
    'until somebody promotes it, and promotion is blocked until provenance is '
    'verified. ''retired'' never means delete — existing entitlements and their '
    'obligations survive (§7.5).';
COMMENT ON COLUMN public.guideline_modules.provenance IS
    'verified = somebody read the published DM PDF (§7.1, decision 5). Defaults '
    'to unverified and gates sale via '
    'guideline_modules_verified_to_sell_check. Under modular pricing every '
    'guideline encoded is a SKU, which makes editorial accuracy a product '
    'liability rather than an internal quality concern.';

-- ── organization_entitlements ────────────────────────────────────────────────
-- Which modules a tenant has bought, and for what period (§4.5). This is
-- simultaneously the onboarding record, the billing driver and the monitoring
-- scope — see THE GOVERNING RULE in the header.
CREATE TABLE IF NOT EXISTS public.organization_entitlements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    module_id       UUID NOT NULL REFERENCES public.guideline_modules(id) ON DELETE RESTRICT,
    active_from     DATE NOT NULL,          -- deliberately no DEFAULT
    active_until    DATE,                   -- NULL = still active
    price_agreed    NUMERIC(12,2),          -- NULL = list price
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    -- Not redundant with the primary key. It is the target of the composite
    -- foreign key on obligations below, which is what stops one tenant's
    -- obligation being hung off another tenant's entitlement.
    UNIQUE (id, organization_id)
);

ALTER TABLE public.organization_entitlements DROP CONSTRAINT IF EXISTS organization_entitlements_window_check;
ALTER TABLE public.organization_entitlements
    ADD CONSTRAINT organization_entitlements_window_check
    CHECK (active_until IS NULL OR active_from <= active_until);

ALTER TABLE public.organization_entitlements DROP CONSTRAINT IF EXISTS organization_entitlements_price_check;
ALTER TABLE public.organization_entitlements
    ADD CONSTRAINT organization_entitlements_price_check
    CHECK (price_agreed IS NULL OR price_agreed >= 0);

-- §4.5's "UNIQUE (organization_id, module_id) WHERE active". Partial, because a
-- tenant may legitimately have bought a module, dropped it, and bought it again
-- — that is a history of closed windows plus at most one open one. Two OPEN
-- entitlements for the same module would double-bill and make "is this module
-- entitled" return two contradictory rows.
--
-- JUDGEMENT CALL, flagged: this does not prevent two CLOSED windows overlapping.
-- Doing so properly needs an EXCLUDE constraint over a daterange, which requires
-- the btree_gist extension. That is deliberately not created here — adding an
-- extension is a heavier act than this migration should perform unannounced, and
-- an overlap between historical windows misstates an invoice rather than
-- misstating compliance. Revisit when billing actually reads these rows.
CREATE UNIQUE INDEX IF NOT EXISTS organization_entitlements_active_idx
    ON public.organization_entitlements (organization_id, module_id)
    WHERE active_until IS NULL;

CREATE INDEX IF NOT EXISTS organization_entitlements_org_idx    ON public.organization_entitlements (organization_id);
CREATE INDEX IF NOT EXISTS organization_entitlements_module_idx ON public.organization_entitlements (module_id);

COMMENT ON TABLE public.organization_entitlements IS
    'Which guideline modules a tenant has bought (§4.5). Deactivation is setting '
    'active_until — NEVER DELETE. §7.5: un-ticking a module stops monitoring and '
    'must retain history and warn explicitly about what stops being tracked. '
    'Deleting a row here is blocked by the ON DELETE RESTRICT reference from '
    'obligations precisely so that the destructive path is not available even to '
    'a well-meaning admin screen.';
COMMENT ON COLUMN public.organization_entitlements.active_from IS
    'When monitoring and billing begin. NOT NULL with NO DEFAULT: defaulting to '
    'today would silently backdate or forward-date a commercial agreement, and '
    'it is also the date from which obligations are considered live — so a '
    'guessed value produces either phantom overdue obligations or a window of '
    'unmonitored time nobody can see.';
COMMENT ON COLUMN public.organization_entitlements.active_until IS
    'NULL = still active. Setting it stops monitoring and leaves every '
    'obligation, sample and certificate in place (§7.5). Nothing derived from '
    'this column may cascade a delete.';
COMMENT ON COLUMN public.organization_entitlements.module_id IS
    'ON DELETE RESTRICT. A module cannot be deleted while any tenant has ever '
    'been entitled to it — retire it instead. Deleting would erase the record of '
    'what a client was paying for and what the app was therefore watching.';

-- ── obligations ──────────────────────────────────────────────────────────────
-- The registry of what is DUE. The single biggest product addition (§4.3): the
-- app currently knows what a certificate said, not that one never arrived.
CREATE TABLE IF NOT EXISTS public.obligations (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id      UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id              UUID REFERENCES public.sites(id) ON DELETE RESTRICT,
    asset_id             UUID REFERENCES public.assets(id) ON DELETE RESTRICT,
    standard_id          UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,
    spec_set_id          UUID REFERENCES public.specification_sets(id) ON DELETE RESTRICT,
    entitlement_id       UUID NOT NULL,       -- composite FK below, see comment
    obligation_type      TEXT NOT NULL,
    label                TEXT NOT NULL,
    -- Periodic OR event-triggered. Exactly one. See obligations_cadence_check.
    cadence_months       INTEGER,
    cadence_days         INTEGER,
    trigger_event        TEXT,
    grace_days           INTEGER NOT NULL DEFAULT 0,
    next_due_on          DATE,
    last_satisfied_at    TIMESTAMPTZ,
    last_satisfied_by    UUID,                -- polymorphic, intentionally no FK
    last_satisfied_kind  TEXT,
    status               TEXT NOT NULL,       -- deliberately no DEFAULT
    responsible_user_id  UUID REFERENCES public.user_profiles(id) ON DELETE SET NULL,
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT now()
);

-- THE GOVERNING RULE (§4.5), enforced. Composite rather than a plain FK to
-- organization_entitlements(id): a simple reference would let an obligation in
-- org A point at an entitlement held by org B, which would make the billing
-- driver and the monitoring scope disagree while every row still looked valid.
-- The (id, organization_id) UNIQUE on the parent exists solely to make this
-- possible. NOT NULL: there is no such thing as an unentitled obligation.
-- ON DELETE RESTRICT per §7.5 — deactivating an entitlement must never delete
-- obligations, so the delete path is closed at the database.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_entitlement_fk;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_entitlement_fk
    FOREIGN KEY (entitlement_id, organization_id)
    REFERENCES public.organization_entitlements (id, organization_id)
    ON DELETE RESTRICT;

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_type_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_type_check
    CHECK (obligation_type IN ('sampling', 'examination', 'inspection', 'competency'));

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_status_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_status_check
    CHECK (status IN ('compliant', 'due_soon', 'overdue', 'suspended'));

-- ── THE CADENCE / TRIGGER RULE ───────────────────────────────────────────────
-- An obligation is EITHER periodic (a cadence is set) OR event-triggered
-- (trigger_event is set). Exactly one. Never both, never neither.
--
-- This exists because of a real finding in the GU44 extraction: a sampling
-- obligation triggered by an EVENT — take a sample after a tank is cleaned or
-- disinfected — rather than by a schedule. With only cadence_months and
-- cadence_days, such a row carries a null cadence and is INDISTINGUISHABLE FROM
-- ONE WHERE NOBODY FILLED THE FIELD IN. It would then sit in the registry
-- forever, never becoming due, never alerting anyone: the silent-gap failure
-- this entire table exists to eliminate, reproduced inside the fix for it.
--
-- "Never both" matters as much as "never neither": a row with both a cadence and
-- a trigger is two schedules, and the due-date calculator would have to pick
-- one. Event-triggered obligations become due when the triggering event is
-- recorded and overdue when the evidence does not follow within grace_days.
--
-- cadence_months and cadence_days are likewise mutually exclusive — two answers
-- to one question — enforced separately below so the error message says which
-- rule was broken.
--
-- btrim() on trigger_event because a whitespace-only string is a null cadence
-- wearing a disguise, and it would satisfy a bare IS NOT NULL.
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

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_one_cadence_unit_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_one_cadence_unit_check
    CHECK (cadence_months IS NULL OR cadence_days IS NULL);

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_cadence_positive_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_cadence_positive_check
    CHECK ((cadence_months IS NULL OR cadence_months > 0)
           AND (cadence_days IS NULL OR cadence_days > 0)
           AND grace_days >= 0);

-- Evidence provenance is one fact in three parts. A satisfaction recorded
-- without saying WHAT satisfied it cannot be audited, and a pointer with no
-- table name cannot be resolved at all.
ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_satisfied_pair_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_satisfied_pair_check
    CHECK ((last_satisfied_by IS NULL) = (last_satisfied_kind IS NULL)
           AND (last_satisfied_by IS NULL OR last_satisfied_at IS NOT NULL));

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_satisfied_kind_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_satisfied_kind_check
    CHECK (last_satisfied_kind IS NULL
           OR last_satisfied_kind IN ('lab_sample', 'certificate', 'inspection'));

CREATE INDEX IF NOT EXISTS obligations_org_status_idx  ON public.obligations (organization_id, status);
CREATE INDEX IF NOT EXISTS obligations_due_idx         ON public.obligations (next_due_on) WHERE next_due_on IS NOT NULL;
CREATE INDEX IF NOT EXISTS obligations_entitlement_idx ON public.obligations (entitlement_id);
CREATE INDEX IF NOT EXISTS obligations_asset_idx       ON public.obligations (asset_id);
CREATE INDEX IF NOT EXISTS obligations_site_idx        ON public.obligations (site_id);
CREATE INDEX IF NOT EXISTS obligations_responsible_idx ON public.obligations (responsible_user_id);

COMMENT ON TABLE public.obligations IS
    'What is DUE, and therefore what is missing (§4.3). The inversion that makes '
    'the product: for an FM contractor the risk is the test that never happened, '
    'not the one that failed. An obligation is satisfied by evidence and '
    'otherwise ages due_soon → overdue, raising an alert and optionally opening a '
    'corrective action through the existing core/corrective.py machine. Every '
    'row requires an active entitlement — see the governing rule in the migration '
    'header.';
COMMENT ON COLUMN public.obligations.trigger_event IS
    'For an EVENT-TRIGGERED obligation: what event makes it due, in the '
    'guideline''s own words — e.g. GU44''s "after a tank is cleaned or '
    'disinfected". Mutually exclusive with cadence_months/cadence_days and '
    'enforced by obligations_cadence_check. Without this column a triggered '
    'obligation is a row with a null cadence, indistinguishable from an unfilled '
    'field, that sits in the registry never becoming due — the exact silent gap '
    'this table exists to eliminate. Free text for now: the vocabulary of '
    'triggering events is not yet known across eighty guidelines, and inventing '
    'an enum from one example would force every later guideline into GU44''s '
    'shape.';
COMMENT ON COLUMN public.obligations.entitlement_id IS
    'THE GOVERNING RULE (§4.5): an obligation may only exist for an entitled '
    'module. NOT NULL, and a COMPOSITE foreign key with organization_id so an '
    'obligation cannot borrow another tenant''s entitlement. ON DELETE RESTRICT '
    '(§7.5): deactivating an entitlement sets active_until and stops monitoring; '
    'it must never delete the obligation or the evidence attached to it. History '
    'is retained; monitoring stops.';
COMMENT ON COLUMN public.obligations.status IS
    'compliant | due_soon | overdue | suspended. NOT NULL with NO DEFAULT, on '
    'purpose. Defaulting to ''compliant'' would make every newly registered '
    'obligation assert a clean record before any evidence exists, which is the '
    'precise misstatement this registry was built to prevent; defaulting to '
    '''overdue'' would alarm a client about an obligation created moments ago. '
    'The loader must compute it from next_due_on and grace_days. ''suspended'' is '
    'the state for an obligation whose entitlement has lapsed — retained and '
    'visible, no longer alerting.';
COMMENT ON COLUMN public.obligations.grace_days IS
    'Days after next_due_on before the obligation is overdue; for an '
    'event-triggered obligation, days after the event before the evidence is '
    'late. DEFAULT 0 is safe in the one direction that matters — zero grace can '
    'only report something as late sooner, whereas a guessed non-zero grace '
    'silently forgives real lateness and suppresses the alert the client is '
    'paying for.';
COMMENT ON COLUMN public.obligations.last_satisfied_by IS
    'Id of the evidence that discharged this obligation, with last_satisfied_kind '
    'naming which table it lives in (lab_sample | certificate | inspection). '
    'Deliberately NO foreign key: the target is polymorphic across three tables '
    'and `inspections` does not exist until Phase 3 (§4.6), so a real FK is not '
    'available without either three nullable columns or a table that is not '
    'built yet. The pair CHECK is what keeps the pointer resolvable; referential '
    'integrity here is the application''s job and is called out so nobody assumes '
    'the database is doing it.';
COMMENT ON COLUMN public.obligations.asset_id IS
    'NULL for a site-level or organisation-level obligation (a competency '
    'obligation attaches to a person, not to plant). ON DELETE RESTRICT: an '
    'asset with a live compliance obligation must not be deletable, because the '
    'obligation would go with it and the gap would close silently — which is '
    'indistinguishable from the obligation having been met.';
COMMENT ON COLUMN public.obligations.spec_set_id IS
    'Which limits apply, when the module produces a verdict at all. NULL is '
    'legitimate and expected for modules whose guideline_modules.module_kind is '
    'monitoring, process or delegating (§7.12) — there is no limit to point at. '
    'A NULL here must never be resolved by falling back to some other set: '
    'resolve_limits returning None is a first-class visible outcome (§7.4), '
    'never a silent pass.';

-- ── certificates ─────────────────────────────────────────────────────────────
-- Third-party examination with an expiry (§4.4). Distinct from lab_samples
-- because nothing is measured and nothing is judged against a limit: a competent
-- person examines a crane, or a lifeguard sits an assessment, and a certificate
-- with a validity period is issued. The shared primitive is EXPIRY, not
-- measurement — which is why this table has an outcome and no results child.
CREATE TABLE IF NOT EXISTS public.certificates (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id      UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    site_id              UUID REFERENCES public.sites(id) ON DELETE RESTRICT,
    asset_id             UUID REFERENCES public.assets(id) ON DELETE RESTRICT,
    subject_user_id      UUID REFERENCES public.user_profiles(id) ON DELETE RESTRICT,
    standard_id          UUID REFERENCES public.standards(id) ON DELETE RESTRICT,
    laboratory_id        UUID REFERENCES public.laboratories(id) ON DELETE RESTRICT,
    certificate_no       TEXT,
    issuer               TEXT NOT NULL,
    issuer_accreditation TEXT,
    issued_on            DATE NOT NULL,
    valid_until          DATE,
    outcome              TEXT NOT NULL,
    conditions           TEXT,
    -- Forensic trail, following 016's pattern.
    source_filename      TEXT,
    source_sha256        TEXT,
    raw_extraction       JSONB,
    reviewer_status      TEXT NOT NULL DEFAULT 'pending',
    created_at           TIMESTAMPTZ DEFAULT now()
);

-- §4.4, stated outright: exactly one of asset_id / subject_user_id. Plant and
-- people share the expiry primitive but are NEVER the same row. A certificate
-- with both would appear in the plant register and the competency register as
-- one artefact and be renewed once for two obligations; a certificate with
-- neither expires attached to nothing and alerts nobody. `<>` on two IS NULL
-- tests is a genuine XOR here — both operands are strictly boolean, so no
-- three-valued surprise is possible.
ALTER TABLE public.certificates DROP CONSTRAINT IF EXISTS certificates_subject_check;
ALTER TABLE public.certificates
    ADD CONSTRAINT certificates_subject_check
    CHECK ((asset_id IS NULL) <> (subject_user_id IS NULL));

ALTER TABLE public.certificates DROP CONSTRAINT IF EXISTS certificates_outcome_check;
ALTER TABLE public.certificates
    ADD CONSTRAINT certificates_outcome_check
    CHECK (outcome IN ('pass', 'pass_with_conditions', 'fail'));

-- A conditional pass whose conditions are not recorded is reported to a client
-- as a pass. The conditions ARE the finding. coalesce+btrim so that NULL and
-- '   ' are both rejected rather than silently satisfying a bare IS NOT NULL.
ALTER TABLE public.certificates DROP CONSTRAINT IF EXISTS certificates_conditions_check;
ALTER TABLE public.certificates
    ADD CONSTRAINT certificates_conditions_check
    CHECK (coalesce(outcome, '') <> 'pass_with_conditions'
           OR coalesce(btrim(conditions), '') <> '');

ALTER TABLE public.certificates DROP CONSTRAINT IF EXISTS certificates_validity_check;
ALTER TABLE public.certificates
    ADD CONSTRAINT certificates_validity_check
    CHECK (valid_until IS NULL OR issued_on <= valid_until);

ALTER TABLE public.certificates DROP CONSTRAINT IF EXISTS certificates_reviewer_status_check;
ALTER TABLE public.certificates
    ADD CONSTRAINT certificates_reviewer_status_check
    CHECK (reviewer_status IN ('pending', 'approved', 'corrected', 'rejected'));

-- One issuer cannot print the same certificate number twice for one tenant.
-- Partial because certificate_no is genuinely absent on some documents, and in
-- Postgres NULLs are distinct anyway — the partial index says so out loud.
CREATE UNIQUE INDEX IF NOT EXISTS certificates_number_idx
    ON public.certificates (organization_id, issuer, certificate_no)
    WHERE certificate_no IS NOT NULL;

CREATE INDEX IF NOT EXISTS certificates_org_expiry_idx ON public.certificates (organization_id, valid_until);
CREATE INDEX IF NOT EXISTS certificates_asset_idx      ON public.certificates (asset_id);
CREATE INDEX IF NOT EXISTS certificates_subject_idx    ON public.certificates (subject_user_id);
CREATE INDEX IF NOT EXISTS certificates_site_idx       ON public.certificates (site_id);
CREATE INDEX IF NOT EXISTS certificates_review_idx     ON public.certificates (organization_id, reviewer_status);
CREATE INDEX IF NOT EXISTS certificates_sha_idx        ON public.certificates (source_sha256);

COMMENT ON TABLE public.certificates IS
    'Third-party examination with an expiry (§4.4) — plant (crane, boiler, MEWP) '
    'via asset_id, or people (lifeguard, OHS officer) via subject_user_id, never '
    'both. Nothing is measured and nothing is judged against a spec_limit; the '
    'compliance question is whether a valid certificate EXISTS on a given date, '
    'which is why this table pairs with obligations rather than with '
    'specification_sets.';
COMMENT ON COLUMN public.certificates.valid_until IS
    'NULL means the certificate states no expiry — NOT that it never expires in '
    'the regulator''s eyes. The renewal cadence lives on the obligation, not '
    'here, so a NULL must not be read as "no obligation".';
COMMENT ON COLUMN public.certificates.laboratory_id IS
    'JUDGEMENT CALL, flagged: §4.4 lists only free-text issuer / '
    'issuer_accreditation, and §4.7 observes that issuer_accreditation is '
    '"a free text field on a table that does not yet exist, and nothing checks '
    'it". This nullable FK is the join that lets something check it — '
    'laboratory_accredited_on(laboratory_id, issued_on) against the SAMPLING or '
    'examination date. Nullable because many certificates are issued by '
    'competent persons and inspection bodies that are not laboratories at all. '
    'The free-text columns are retained alongside as the verbatim record of what '
    'the document printed; they are the evidence, this is the resolved link.';
COMMENT ON COLUMN public.certificates.standard_id IS
    'JUDGEMENT CALL, flagged: nullable, though §4.4 does not say. A certificate '
    'issued under no DM guideline (a manufacturer''s or insurer''s examination) '
    'is real and must be storable, and NOT NULL would force a false citation to '
    'get it in. The consequence is that a NULL here cannot discharge a '
    'standard-bound obligation, which is the correct and visible outcome.';
COMMENT ON COLUMN public.certificates.raw_extraction IS
    'The extractor''s verbatim output, following 016''s forensic pattern. '
    'NULLABLE here, unlike lab_samples.raw_extraction which is NOT NULL, because '
    'a certificate is routinely entered by hand from a paper document with no '
    'extraction step at all.'
    ' '
    'JUDGEMENT CALL, flagged: 016''s '
    'reject_raw_extraction_change() trigger is deliberately NOT attached to this '
    'table. It rejects any change including NULL → value, which would make it '
    'impossible to attach a scan to a hand-entered certificate later — a normal '
    'workflow here and an impossible one on lab_samples. The immutability '
    'guarantee is therefore weaker on this table and should be restored by a '
    'variant trigger (permitting NULL → value exactly once, rejecting every '
    'other change) when the certificate ingestion path is built in Phase 3.';
COMMENT ON COLUMN public.certificates.source_sha256 IS
    'Ties the row to the exact source file byte-for-byte, as in 016. The index on '
    'it is what makes duplicate ingestion of the same PDF detectable.';
COMMENT ON COLUMN public.certificates.site_id IS
    'ON DELETE RESTRICT, deliberately different from assets.site_id (010), which '
    'cascades. An asset is operational data; a certificate is compliance '
    'evidence, and §7.5 forbids deleting evidence as a side effect of an '
    'unrelated administrative action. Removing a site with certificates against '
    'it must fail loudly and require an explicit decision.';

-- ── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.laboratories               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guideline_modules          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_entitlements  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.obligations                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.certificates               ENABLE ROW LEVEL SECURITY;

GRANT ALL ON public.laboratories              TO service_role;
GRANT ALL ON public.guideline_modules         TO service_role;
GRANT ALL ON public.organization_entitlements TO service_role;
GRANT ALL ON public.obligations               TO service_role;
GRANT ALL ON public.certificates              TO service_role;

-- EVERY policy below is scoped TO authenticated, for the reason 022 established:
-- Supabase grants SELECT on new public tables to the anon role by default, so
-- RLS is the only gate and an unqualified `USING (true)` would publish the table
-- to anyone holding the publishable anon key. It bites harder here than in 022.
-- `guideline_modules` carries list_price_monthly — it is the price list. And
-- `obligations` is a named client's overdue compliance items, which is the
-- single most damaging table in the schema to leak: it is a map of where a
-- contractor is exposed, useful to a competitor bidding against them and to
-- anyone minded to complain about them to DM. Existing repo policies avoid the
-- anon problem only incidentally, because get_user_organization() returns NULL
-- for an unauthenticated caller; these say it explicitly.

-- laboratories: readable by every authenticated user — a client must be able to
-- see whether their laboratory is accredited, and it is public regulatory fact.
-- Writable only by super_admin: an accreditation record edited by the party
-- being audited is worthless, and §7.9 makes lab independence structural rather
-- than a courtesy.
DROP POLICY IF EXISTS select_laboratories ON public.laboratories;
CREATE POLICY select_laboratories ON public.laboratories
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_laboratories ON public.laboratories;
CREATE POLICY mutate_laboratories ON public.laboratories
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

-- guideline_modules: the catalogue is readable by all authenticated users, since
-- a client browsing what they could buy is the upsell path in §4.5. Writable
-- only by super_admin — a tenant admin must not be able to mark a module
-- 'verified' or 'available', which is exactly the guarantee decision 5 sells.
DROP POLICY IF EXISTS select_guideline_modules ON public.guideline_modules;
CREATE POLICY select_guideline_modules ON public.guideline_modules
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_guideline_modules ON public.guideline_modules;
CREATE POLICY mutate_guideline_modules ON public.guideline_modules
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

-- organization_entitlements: a tenant sees its own. Writes are super_admin ONLY
-- — a deliberate divergence from 022's specification_sets, which admits a tenant
-- 'admin'. Entitlement is the billing record; a tenant admin who could INSERT
-- here could grant themselves modules, and one who could UPDATE could rewrite
-- price_agreed. Self-service module selection, when it ships, goes through a
-- service_role endpoint that also books the commercial change — not through a
-- direct table write.
DROP POLICY IF EXISTS select_organization_entitlements ON public.organization_entitlements;
CREATE POLICY select_organization_entitlements ON public.organization_entitlements
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_organization_entitlements ON public.organization_entitlements;
CREATE POLICY mutate_organization_entitlements ON public.organization_entitlements
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

-- obligations: readable by the whole tenant, including operators and auditors —
-- an operator who cannot see what is due cannot act on it, and an auditor's
-- read-only view of the registry is the point of the product. Writes are
-- restricted to admin and super_admin: defining an obligation is regulatory
-- policy, the same reasoning 022 applied to specification_sets. Note that
-- SATISFACTION is not a hand-entered fact either — last_satisfied_* must be
-- derived from evidence by the backend under service_role, because an operator
-- able to mark an obligation satisfied without a document is a way to close a
-- compliance gap on paper only.
DROP POLICY IF EXISTS select_obligations ON public.obligations;
CREATE POLICY select_obligations ON public.obligations
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_obligations ON public.obligations;
CREATE POLICY mutate_obligations ON public.obligations
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
  );

-- certificates: tenant-scoped, plus the subject of a personal certificate can
-- always see their own — a lifeguard's competency certificate is about them, and
-- they may need it after moving organisation, at which point the org test alone
-- would hide it. Writes admin/super_admin: a certificate is third-party evidence
-- and must not be editable by the person it certifies (§7.9 — the independence
-- requirement cuts both ways), which is why subject_user_id grants SELECT only.
DROP POLICY IF EXISTS select_certificates ON public.certificates;
CREATE POLICY select_certificates ON public.certificates
  FOR SELECT TO authenticated USING (
    organization_id = public.get_user_organization()
    OR subject_user_id = auth.uid()
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_certificates ON public.certificates;
CREATE POLICY mutate_certificates ON public.certificates
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
  );

COMMIT;
