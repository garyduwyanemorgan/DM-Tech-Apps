BEGIN;

-- ── Migration 028: people_credentials, prerequisites, coverage_requirements ──
-- The Phase 5 primitive (DM_COMPLIANCE_SCOPING.md §6, Phase 5). Structure only
-- — nothing reads these tables until the Phase 5 services land, so applying it
-- changes no behaviour.
--
-- WHY THIS EXISTS. Phase 5 was scoped as a reuse: take §4.4's `certificates`
-- row, point it at `subject_user_id` instead of `asset_id`, and ship. Reading
-- the twelve competency documents showed the expiry half reuses directly and
-- four things do not (competency_group_notes.md §3, and §6 of the scoping
-- document, which now records the same finding). Each of the four produces a
-- wrong answer ABOUT A NAMED PERSON, which is a materially worse failure than a
-- wrong answer about a pump: it is an accusation, or a false assurance, about an
-- individual's right to do their job.
--
--   1. VALIDITY IS DERIVED, NOT STORED (§3.1). S1 p5: "Certifications are valid
--      only for the remaining period of a candidate's training record." The
--      expiry is MIN(own two-year ceiling, the underlying credential's expiry).
--      A plain `valid_until` DATE holds a value that goes silently wrong the
--      moment a DIFFERENT ROW lapses — and S1 states the consequence outright:
--      the individual "may not perform lifeguard duties".
--   2. RENEWAL ANCHORS TO THE PREVIOUS EXPIRY, NOT THE EXAMINATION (§3.3). S1
--      p14: "the new two-year certification period begins from the date not
--      later than the expiry date of the candidate's initial certification."
--      `issued_on + 24 months` over-grants by up to two months. That is a
--      mis-issuance, not a rounding error.
--   3. STATUS IS NOT A FUNCTION OF DATES (§3.5). S1 lists six revocation
--      grounds and says the list is not exhaustive; S2 invalidates a PIC
--      certificate on a SECTOR CHANGE ("from services to factories"); GU131,
--      S2 and S3 all let a poor company inspection grade cancel an
--      INDIVIDUAL's certificate. A date-driven model reports all of these as
--      valid.
--   4. THE REQUIREMENT IS COVERAGE, NOT HOLDING (§3.7). S2 §6.1 requires one
--      certified Person in Charge PER WORK SHIFT PER WORK LOCATION, "present
--      throughout the conduct of the work activity". Three shifts across twelve
--      sites is 36 coverage slots. No set of certificate rows answers that: a
--      client can hold every certificate in the scheme and be non-compliant on
--      a night shift.
--
-- Two further mismatches with §4.4 specifically. SPECIALTY SCOPE GATES VALIDITY
-- (§3.6): a Shallow Water lifeguard posted to 2 m of water holds a perfectly
-- valid certificate and is non-compliant. And PERSON-CERTIFICATES ARE SITE-TIED
-- — S1 requires water-park lifeguards to sit "additional examinations at the
-- specific facility where they will work", and the pool dive prerequisite is
-- "3m, or to the deepest depth of the facility in which they will be
-- lifeguarding". §4.4's CHECK permits exactly one of asset_id / subject_user_id
-- and has no room for a person-certificate whose SCOPE is a site.
--
-- So `certificates` (023) is left exactly as it is — it fits plant, and Phase 3
-- proved it — and people get a sibling. Overloading the plant table would have
-- meant nullable columns that are meaningless for a crane plus a validity rule
-- that must not apply to one.
--
-- ── PERSONAL DATA ────────────────────────────────────────────────────────────
-- EVERY ROW IN people_credentials AND credential_prerequisites IS ABOUT A NAMED
-- INDIVIDUAL. That changes three things relative to every other table in this
-- repo, and they are decisions, not warnings:
--
--   * ACCESS. RLS below is deliberately TIGHTER than for reference data and
--     tighter than 023's `certificates`. A person's credential is not org-wide
--     reading material by default: SELECT is limited to the subject themselves,
--     tenant `admin`, and `super_admin`. Operators and auditors do NOT get a
--     blanket read. An operator needs to know whether a shift is covered, not
--     who holds which document, and that question is answered by
--     coverage_requirements plus an aggregate — which is precisely why the two
--     tables are separate. Nobody may EDIT their own credential (§7.9: the
--     independence requirement cuts both ways).
--   * RETENTION. Compliance evidence must outlive the employment (§7.5 — a
--     regulator asking about 2026 must get the same answer in 2028), but a
--     credential row is also employee data that should not be kept for ever
--     merely because deletion is inconvenient. The FKs below are ON DELETE
--     RESTRICT, so purging is an explicit, authorised act and never a side
--     effect. There is no automatic purge here and there deliberately is no
--     `purge_after` column: inventing a retention period the client has not
--     agreed would be a policy decision made by a schema.
--   * MINIMISATION. S1 p16 specifies what a certification card must carry —
--     photo, date of birth, examiner information, specialty, training facility.
--     Only the ones a COMPLIANCE CHECK needs are columns here. There is
--     deliberately no date_of_birth, no photo, no Emirates ID and — unlike
--     `certificates` — NO `raw_extraction`. 016's forensic pattern retains the
--     verbatim document contents, which on a personal certificate means holding
--     a copy of someone's DOB and identity-document numbers to answer a
--     question that only needs an expiry date. `source_sha256` gives the
--     byte-for-byte tie to the source file without storing its contents.
--
-- ── DEPENDENCIES ─────────────────────────────────────────────────────────────
-- Requires `organizations` and `sites` (db/schema.sql), `user_profiles` and the
-- get_user_* helpers (db/schema_rls.sql), `standards` (022), and
-- `guideline_modules` (023). Run in the Supabase SQL editor after 027.
-- Reversible: 028_people_credentials_down.sql — read its header first, it is
-- lossy.
--
-- ── CONVENTIONS CARRIED FORWARD FROM 022 / 023 / 027 ─────────────────────────
-- Applied throughout this file rather than rediscovered, and stated here so
-- that a reviewer can check them off:
--   1. EVERY policy below is scoped `TO authenticated`. Supabase grants SELECT
--      on new public tables to the `anon` role by default, so RLS is the only
--      gate and an unqualified `USING (true)` publishes the table to anyone
--      holding the publishable anon key. It bites harder here than anywhere
--      else in the schema: this is named-individual data.
--   2. NO DEFAULT on a column where guessing is unsafe. A default is a silent
--      assertion made on the operator's behalf. See status, credential_type,
--      scope_key, ceiling_anchor, effective_until_source, attempts_used and
--      coverage_requirements.presence_required, each of which says why.
--   3. `coalesce(col,'') = 'x'` rather than `col = 'x'` inside a CHECK. With a
--      NULL column a bare comparison yields NULL, and Postgres accepts any
--      CHECK that is not FALSE — so the constraint silently permits exactly
--      what it was written to forbid. Every conditional CHECK below is written
--      this way, and `btrim` is applied wherever a whitespace-only string would
--      otherwise satisfy an IS NOT NULL test.
--   4. ON DELETE RESTRICT wherever a delete would orphan compliance evidence
--      (§7.5) — site, standard, module, subject, and every credential-to-
--      credential edge. The single exception is organization_id, which stays ON
--      DELETE CASCADE to match every other table in the repo: removing a tenant
--      removes the tenant's data, which is a different act with a different
--      authority behind it.
--   5. Named constraints added via DROP CONSTRAINT IF EXISTS / ADD CONSTRAINT
--      so the whole file re-runs against a partially applied database.
--   6. The `_down` contains NO DROP POLICY statements. `DROP POLICY IF EXISTS p
--      ON t` tolerates a missing policy but NOT a missing table; against an
--      absent table it raises 42P01 and aborts the entire transactional
--      rollback, in precisely the partial-state case such lines appear to
--      protect against.

-- ── people_credentials ───────────────────────────────────────────────────────
-- One row per credential held by one person. The §3.9 shape, with the
-- departures from it defended in the comments below.
CREATE TABLE IF NOT EXISTS public.people_credentials (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id       UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,

    -- WHO. subject_user_id is NULLABLE, which is a deliberate departure from
    -- §3.9's `subject_user_id → user_profiles`. A lifeguard, an HSO in a labour
    -- accommodation or a Person in Charge is an employee of the FM contractor;
    -- almost none of them will ever hold a login to this product. Making the
    -- platform identity mandatory would mean either creating auth users for
    -- people who never sign in, or — far more likely in practice — not
    -- recording the credential at all, which reproduces the silent gap the
    -- whole registry exists to close.
    subject_user_id       UUID REFERENCES public.user_profiles(id) ON DELETE RESTRICT,
    subject_name          TEXT NOT NULL,          -- as printed on the certificate
    subject_ref           TEXT,                   -- the employer's own staff / payroll reference

    -- WHAT. credential_type is the join key to coverage_requirements: the same
    -- closed vocabulary on both sides is what lets "one certified PIC per shift"
    -- be matched against the people who are actually certified.
    credential_type       TEXT NOT NULL,          -- deliberately no DEFAULT
    standard_id           UUID REFERENCES public.standards(id) ON DELETE RESTRICT,

    -- SCOPE (§3.6). What this credential authorises, as distinct from whether
    -- it is in date.
    scope_key             TEXT NOT NULL,          -- specialty / sector, no DEFAULT
    scope_max_depth_m     NUMERIC(5,2),           -- S1's 1.5 m gate, see comment
    scope_site_id         UUID REFERENCES public.sites(id) ON DELETE RESTRICT,

    -- ISSUER CHAIN (§3.8), verbatim. See the comment on issuer_name for why
    -- there is no certification_bodies registry table.
    issuer_name           TEXT NOT NULL,
    issuer_accredited_by  TEXT,                   -- e.g. 'EIAC'
    issuer_approved_by    TEXT,                   -- e.g. 'DCAS' for the BLS portion
    certificate_no        TEXT,
    examiner_ref          TEXT,                   -- S1 p16 mandates examiner information on the card

    issued_on             DATE NOT NULL,

    -- ── DERIVED VALIDITY (§3.1) ──────────────────────────────────────────────
    -- The inputs, the computed answer, and what the answer was computed FROM.
    own_ceiling_until     DATE,                   -- the scheme's own ceiling, NULL = none stated
    ceiling_anchor        TEXT NOT NULL,          -- which date the ceiling runs from, no DEFAULT
    effective_until       DATE,                   -- the computed MIN — never hand-entered
    effective_until_source TEXT NOT NULL,         -- own_ceiling | prerequisite | interim_proof | not_stated
    effective_until_from_credential_id UUID,      -- which row supplied it, when source = prerequisite
    effective_until_computed_at TIMESTAMPTZ NOT NULL,   -- staleness detector, no DEFAULT

    renewal_opens_on      DATE,                   -- expiry − scheme window (§3.4)
    renewal_of_credential_id UUID,                -- the certification this one renews (§3.3)

    -- ── STATUS (§3.5), independent of every date above ───────────────────────
    status                TEXT NOT NULL,          -- deliberately no DEFAULT
    status_reason         TEXT,
    status_effective_from DATE,                   -- the day the status took effect

    interim_proof_expires_on DATE,                -- S1's 3-month bridging credential (§3.8)
    attempts_used         INTEGER,                -- NULL = not known, deliberately no DEFAULT

    -- Forensic tie to the source document WITHOUT retaining its contents; see
    -- the PERSONAL DATA / MINIMISATION note in the header.
    source_filename       TEXT,
    source_sha256         TEXT,
    reviewer_status       TEXT NOT NULL DEFAULT 'pending',
    notes                 TEXT,
    created_at            TIMESTAMPTZ DEFAULT now(),

    -- Not redundant with the primary key. It is the target of the composite
    -- foreign keys below, which is what stops one tenant's credential being
    -- hung off another tenant's row — the same device 023 uses on
    -- organization_entitlements.
    UNIQUE (id, organization_id)
);

-- A credential must identify a person somehow. Either the platform identity or
-- the employer's own reference will do, but not neither: a row naming only
-- "Ahmed" cannot be matched to a second document, and two lifeguards with the
-- same name would silently share one compliance record. btrim so that '   '
-- does not satisfy the test.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_subject_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_subject_check
    CHECK (subject_user_id IS NOT NULL OR coalesce(btrim(subject_ref), '') <> '');

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_name_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_name_check
    CHECK (coalesce(btrim(subject_name), '') <> '');

-- The closed vocabulary. Every value is evidenced in the twelve Phase 5
-- documents; nothing is invented and there is deliberately NO 'other' escape
-- hatch. A credential type that falls into 'other' matches no coverage
-- requirement, so the person would hold a document and the roster would still
-- read as uncovered — a silent miss on exactly the check this migration exists
-- to support. Adding a scheme therefore costs a migration, which is the
-- precedent 025 already set for obligations.obligation_type.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_type_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_type_check
    CHECK (credential_type IN (
        -- S1, the Lifeguard Scheme
        'lifeguard', 'lifeguard_instructor', 'lifeguard_instructor_trainer',
        'pool_plant_operator',
        -- S2 / S3 / GU131
        'ohs_person_in_charge', 'ohs_practitioner', 'health_safety_officer',
        -- scheme roles that carry NO validity anywhere in this corpus (§6 of
        -- the notes): they are maintained by annual reporting and by
        -- suspension-on-non-compliance, not by expiry
        'scheme_trainer', 'examiner', 'invigilator',
        -- underlying credentials that other rows depend on (§3.2). They are
        -- credentials in their own right, not attributes of one
        'bls_first_aid', 'bls_first_aid_trainer', 'occupational_health_card',
        'training_record'));

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_scope_key_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_scope_key_check
    CHECK (coalesce(btrim(scope_key), '') <> '');

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_depth_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_depth_check
    CHECK (scope_max_depth_m IS NULL OR scope_max_depth_m > 0);

-- ── THE DERIVED-VALIDITY RULE, and the choice behind it ──────────────────────
-- The brief allows two shapes for a derived value. This file stores the
-- COMPUTED VALUE TOGETHER WITH WHAT IT WAS DERIVED FROM, rather than storing
-- only the inputs and computing on read.
--
-- WHY THIS ONE. The product's core query is "what expires in the next sixty
-- days, across every tenant" — S1's recertification window, the single most
-- commercially valuable number in the Phase 5 corpus. A value computed on read
-- by walking a prerequisite graph cannot be indexed, so that query degrades
-- into a full recursive scan of every credential the platform holds. Worse, a
-- pure-computation model gives no way to reproduce what the app BELIEVED on the
-- day it sent an alert, and an alert about a named person is exactly the thing
-- that will later be argued about.
--
-- WHY THE OTHER IS WORSE HERE, AND WHERE IT IS BETTER. Storing only the inputs
-- is the more honest model in the abstract — it cannot go stale, because there
-- is nothing to go stale. But it hides the derivation from anyone reading the
-- row: they see a training-record id and a ceiling, and must know the MIN rule
-- to interpret it. The shape below is the compromise: the answer is present and
-- indexable, and it is IMPOSSIBLE FOR IT TO LOOK LIKE A HAND-ENTERED DATE,
-- because it arrives with `effective_until_source`, the id of the row that
-- supplied it, and the timestamp at which it was computed. A lapsing dependency
-- is therefore DETECTABLE two ways: by comparing effective_until_computed_at
-- against the prerequisite's updated_at, and — the belt-and-braces route —
-- by credential_valid_on() below, which re-checks every prerequisite live and
-- so returns FALSE for a lapsed dependency EVEN IF THE CACHE WAS NEVER
-- REFRESHED. That is the property the stored-date model in §4.4 does not have
-- and cannot be given.
--
-- effective_until IS A CACHE. It must be written only by the resolver, never by
-- a form. See the column comment.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_ceiling_anchor_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_ceiling_anchor_check
    CHECK (ceiling_anchor IN ('issued_on', 'previous_expiry', 'accreditation_approval', 'unknown'));

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_until_source_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_until_source_check
    CHECK (effective_until_source IN ('own_ceiling', 'prerequisite', 'interim_proof', 'not_stated'));

-- A derived expiry sourced from a prerequisite must name the prerequisite, and
-- one sourced from anywhere else must not pretend to. Without the second half
-- a stale pointer survives a recompute and blames the wrong row for an expiry.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_until_provenance_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_until_provenance_check
    CHECK ((coalesce(effective_until_source, '') = 'prerequisite'
            AND effective_until_from_credential_id IS NOT NULL)
        OR (coalesce(effective_until_source, '') <> 'prerequisite'
            AND effective_until_from_credential_id IS NULL));

-- 'not_stated' is the honest state for the trainer, examiner and invigilator
-- roles, which carry NO validity anywhere in this corpus (§6 of the notes).
-- It must not be used to smuggle in a row that HAS an expiry nobody computed.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_not_stated_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_not_stated_check
    CHECK (coalesce(effective_until_source, '') <> 'not_stated' OR effective_until IS NULL);

-- The derivation can only ever SHORTEN. MIN(own ceiling, prerequisite expiry)
-- can never exceed the ceiling, so a row that does is a resolver bug, and it is
-- the bug that over-grants validity to a named individual.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_ceiling_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_ceiling_check
    CHECK (effective_until IS NULL OR own_ceiling_until IS NULL
           OR effective_until <= own_ceiling_until);

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_window_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_window_check
    CHECK ((effective_until   IS NULL OR issued_on <= effective_until)
       AND (own_ceiling_until IS NULL OR issued_on <= own_ceiling_until)
       AND (renewal_opens_on  IS NULL OR effective_until IS NULL
            OR renewal_opens_on <= effective_until));

-- §3.3, as far as a single-row CHECK can carry it. A renewal's new period runs
-- from the PREVIOUS EXPIRY, never from the examination date, so a row that
-- renews another row and claims to be anchored on its own issue date has
-- over-granted validity by up to the length of the renewal window — two months
-- under S1. The cross-row half of the rule (that own_ceiling_until actually
-- equals the previous row's effective_until plus the scheme term) is NOT
-- enforced here: it would need a trigger firing on updates to the PREVIOUS row
-- as well, and 023/027 keep this schema trigger-free. Flagged rather than
-- buried — the resolver owns that half, and `ceiling_anchor` is what makes a
-- breach auditable after the fact.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_renewal_anchor_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_renewal_anchor_check
    CHECK (renewal_of_credential_id IS NULL
           OR coalesce(ceiling_anchor, '') = 'previous_expiry');

-- ── STATUS (§3.5) ────────────────────────────────────────────────────────────
-- Not derivable from any date. 'revoked' and 'invalidated' are distinct on
-- purpose: revocation is a disciplinary act against the person (S1's six
-- grounds), invalidation is a change in the world that makes the certificate
-- inapplicable without any finding against them (S2's sector change, and the
-- company inspection grade in GU131/S2/S3 that cancels an individual's
-- certificate). Reporting the second as the first is an accusation the
-- documents do not support.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_status_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_status_check
    CHECK (status IN ('valid', 'interim', 'expired', 'suspended',
                      'revoked', 'invalidated', 'superseded'));

-- A credential that has been taken away must say by whom and from when, or the
-- report cannot be defended and a past-dated report cannot be reproduced. The
-- date is what stops a revocation retrospectively unmaking work that was
-- lawfully supervised before it.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_status_reason_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_status_reason_check
    CHECK (status NOT IN ('suspended', 'revoked', 'invalidated', 'superseded')
           OR (coalesce(btrim(status_reason), '') <> '' AND status_effective_from IS NOT NULL));

-- S1 §3.8: proof of passing is valid for three months pending the card. A row
-- in that state without its expiry shows a false pass for ever; ignoring the
-- state entirely shows a false gap for up to three months after a valid pass.
-- Both failure modes are real, so the interim state is first-class and its
-- expiry is mandatory.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_interim_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_interim_check
    CHECK (coalesce(status, '') <> 'interim' OR interim_proof_expires_on IS NOT NULL);

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_attempts_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_attempts_check
    CHECK (attempts_used IS NULL OR attempts_used >= 0);

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_reviewer_status_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_reviewer_status_check
    CHECK (reviewer_status IN ('pending', 'approved', 'corrected', 'rejected'));

-- Composite self-references, so an edge cannot cross a tenant boundary. The
-- same reasoning as obligations_entitlement_fk in 023: a plain FK would let a
-- credential in org A take its expiry from a training record held by org B, and
-- every row would still look valid. ON DELETE RESTRICT because deleting the row
-- that CAPS another row's validity would silently extend that other row.
ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_until_from_fk;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_until_from_fk
    FOREIGN KEY (effective_until_from_credential_id, organization_id)
    REFERENCES public.people_credentials (id, organization_id)
    ON DELETE RESTRICT;

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_renewal_of_fk;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_renewal_of_fk
    FOREIGN KEY (renewal_of_credential_id, organization_id)
    REFERENCES public.people_credentials (id, organization_id)
    ON DELETE RESTRICT;

ALTER TABLE public.people_credentials DROP CONSTRAINT IF EXISTS people_credentials_no_self_reference_check;
ALTER TABLE public.people_credentials
    ADD CONSTRAINT people_credentials_no_self_reference_check
    CHECK ((effective_until_from_credential_id IS NULL
            OR effective_until_from_credential_id <> id)
       AND (renewal_of_credential_id IS NULL
            OR renewal_of_credential_id <> id));

-- One issuer cannot print the same certificate number twice for one tenant.
-- Partial because certificate_no is genuinely absent on some documents and
-- NULLs are distinct in Postgres anyway — the partial index says so out loud.
CREATE UNIQUE INDEX IF NOT EXISTS people_credentials_number_idx
    ON public.people_credentials (organization_id, issuer_name, certificate_no)
    WHERE certificate_no IS NOT NULL;

CREATE INDEX IF NOT EXISTS people_credentials_org_status_idx
    ON public.people_credentials (organization_id, status);
CREATE INDEX IF NOT EXISTS people_credentials_expiry_idx
    ON public.people_credentials (effective_until) WHERE effective_until IS NOT NULL;
CREATE INDEX IF NOT EXISTS people_credentials_renewal_window_idx
    ON public.people_credentials (renewal_opens_on) WHERE renewal_opens_on IS NOT NULL;
CREATE INDEX IF NOT EXISTS people_credentials_type_idx
    ON public.people_credentials (organization_id, credential_type, scope_key);
CREATE INDEX IF NOT EXISTS people_credentials_subject_idx
    ON public.people_credentials (subject_user_id);
CREATE INDEX IF NOT EXISTS people_credentials_subject_ref_idx
    ON public.people_credentials (organization_id, subject_ref) WHERE subject_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS people_credentials_scope_site_idx
    ON public.people_credentials (scope_site_id);
CREATE INDEX IF NOT EXISTS people_credentials_standard_idx
    ON public.people_credentials (standard_id);
CREATE INDEX IF NOT EXISTS people_credentials_sha_idx
    ON public.people_credentials (source_sha256);

COMMENT ON TABLE public.people_credentials IS
    'Credentials held by named individuals (Phase 5). A sibling of '
    '`certificates` (023), not a replacement: that table fits PLANT, where the '
    'expiry is stored on the document, and Phase 3 proved it. People differ in '
    'four ways set out in the migration header — derived validity, '
    'previous-expiry renewal anchoring, status independent of dates, and a '
    'requirement that is coverage rather than holding. EVERY ROW IS PERSONAL '
    'DATA: see the PERSONAL DATA note in 028''s header for the access, '
    'retention and minimisation consequences, and note the RLS below is '
    'deliberately tighter than for any other table in the schema.';
COMMENT ON COLUMN public.people_credentials.effective_until IS
    'THE COMPUTED EXPIRY — MIN(own_ceiling_until, every prerequisite''s '
    'effective_until). A CACHE, and never hand-entered: it must be written only '
    'by the resolver, which is why it always travels with '
    'effective_until_source, effective_until_from_credential_id and '
    'effective_until_computed_at. S1 p5: "Certifications are valid only for the '
    'remaining period of a candidate''s training record", and if that record '
    'expires "the certification is rendered invalid, and the individual may not '
    'perform lifeguard duties". A lifeguard can therefore be un-certified today '
    'by an event recorded against a DIFFERENT ROW. Do not trust this column '
    'alone for a compliance answer — call credential_valid_on(), which re-reads '
    'the prerequisites live and so is correct even when this cache is stale. '
    'NULL means no expiry has been derived, NOT that the credential never '
    'expires; the renewal duty lives on the obligation, as in 023.';
COMMENT ON COLUMN public.people_credentials.effective_until_computed_at IS
    'When effective_until was last derived. NOT NULL with NO DEFAULT: '
    'defaulting to now() would make every hand-inserted row assert that its '
    'cached expiry is fresh, which is the precise claim this column exists to '
    'let a reader doubt. A row whose prerequisites changed after this timestamp '
    'is STALE and must be recomputed before it is reported on.';
COMMENT ON COLUMN public.people_credentials.ceiling_anchor IS
    'Which date the scheme''s own validity ceiling runs from: issued_on | '
    'previous_expiry | accreditation_approval | unknown. NOT NULL, NO DEFAULT, '
    'and ''unknown'' is a legitimate and expected value — S1 states the two-year '
    'ceiling three times against THREE DIFFERENT ANCHOR DATES (issue date, '
    'final accreditation approval date, and the training record''s remaining '
    'period). The ceiling is certain; the anchor is not, and only DM can close '
    'it. Defaulting to ''issued_on'' would silently pick one of the three and '
    'over-grant validity on renewal by up to the length of the renewal window.';
COMMENT ON COLUMN public.people_credentials.renewal_of_credential_id IS
    'The certification this row renews. S1 p14: "Regardless of the date of the '
    'renewal examination within that 2-month period, the new two-year '
    'certification period begins from the date not later than the expiry date '
    'of the candidate''s initial certification." Setting this column forces '
    'ceiling_anchor = ''previous_expiry'' — the obvious implementation, '
    'issued_on + 24 months, over-grants up to two months of validity to a named '
    'person, which is a mis-issuance rather than a cosmetic bug.';
COMMENT ON COLUMN public.people_credentials.status IS
    'valid | interim | expired | suspended | revoked | invalidated | '
    'superseded. NOT NULL with NO DEFAULT. Status is NOT a function of dates '
    '(§3.5): S1 lists six revocation grounds and says the list is not '
    'exhaustive; S2 invalidates a PIC certificate when the holder changes '
    'sector employment; GU131/S2/S3 let a poor company inspection grade cancel '
    'an individual''s certificate. ''revoked'' is a finding against the person, '
    '''invalidated'' is a change in the world with no finding against them — '
    'reporting the second as the first is an accusation the documents do not '
    'support. A revoked credential must never read as valid, which '
    'credential_valid_on() enforces in one place.';
COMMENT ON COLUMN public.people_credentials.scope_key IS
    'The specialty or sector this credential authorises — S1''s shallow_water / '
    'pool / beach, S2 and S3''s construction / services / factories. NOT NULL '
    'with NO DEFAULT and no empty string: an unscoped credential must say so '
    'explicitly (use ''unscoped''), because silence here reads as "applies to '
    'everything" and that is how a Shallow Water lifeguard ends up counted '
    'against a 2 m pool. S2 makes the sector load-bearing: a sector change '
    'INVALIDATES the certificate, so this column is not a label.';
COMMENT ON COLUMN public.people_credentials.scope_max_depth_m IS
    'The deepest water this credential authorises supervision of. S1 draws the '
    'boundary cleanly — "shallow water means that the depth is maximum 1.5m" '
    'and "Pools means that the depth is more than 1.5m", so exactly 1.5 m is '
    'shallow water. A named numeric column rather than a generic JSONB bag of '
    'scope attributes, on purpose: JSONB cannot be constrained or indexed, and '
    'the depth rule would end up spelled three different ways by three '
    'importers. NULL means no depth ceiling was recorded — and '
    'credential_covers() answers FALSE, never TRUE, to a depth question asked '
    'of such a row. That is deliberate and it bites on S1''s lagoon category, '
    'which is named in scope with NO depth rule, NO prerequisites and NO '
    'specialty examination anywhere in the document. Do NOT infer that the pool '
    'specialty covers a lagoon; only DM can close that gap.';
COMMENT ON COLUMN public.people_credentials.scope_site_id IS
    'Set when the credential is TIED TO A SITE, which §4.4''s exactly-one-of-'
    'asset-or-person CHECK forbids outright. S1 requires lifeguards in '
    'specialised environments such as water parks to sit "additional '
    'examinations at the specific facility where they will work", and the pool '
    'dive prerequisite is "3m, or to the deepest depth of the facility in which '
    'they will be lifeguarding". NULL means the credential is portable. This is '
    'the SCOPE of the credential, not where the person happens to be employed — '
    'employment lives in user_site_assignments (007). ON DELETE RESTRICT: '
    'deleting a site must not silently widen a credential that was granted '
    'against it.';
COMMENT ON COLUMN public.people_credentials.issuer_name IS
    'The issuing body as printed, with issuer_accredited_by (EIAC) and '
    'issuer_approved_by (DCAS for the BLS portion, DHA for the clinic) holding '
    'the rest of the chain (§3.8). JUDGEMENT CALL, flagged: §3.9 proposed '
    'issuer_body_id → a certification_bodies registry, and that registry is NOT '
    'created here. §12 of the notes is explicit that NO register of approved '
    'certification bodies, training companies, trainers, examiners or approved '
    'clinics exists in ANY scheme document, and that verification is by holding '
    'a copy of the certificate and nothing more. A registry table would '
    'therefore be unpopulatable from the corpus and would imply a verification '
    'the product cannot perform — the opposite of `laboratories` (023), which '
    'exists precisely because DM publishes that list. Revisit if DM publishes '
    'one.';
COMMENT ON COLUMN public.people_credentials.subject_user_id IS
    'The platform identity, when the person has one. NULLABLE, departing from '
    '§3.9: a lifeguard or an HSO in a labour accommodation is an employee of '
    'the FM contractor and will almost never hold a login here. ON DELETE '
    'RESTRICT so removing a user account cannot destroy compliance evidence '
    '(§7.5). Grants the subject SELECT on their own row and nothing more — a '
    'credential is third-party evidence and must not be editable by the person '
    'it certifies (§7.9).';
COMMENT ON COLUMN public.people_credentials.attempts_used IS
    'Examination attempts consumed: two before a renewal becomes a full course '
    'under S1, three before the whole process repeats under S2/S3. NULLABLE '
    'with NO DEFAULT — NULL means "not known". Defaulting to 0 would assert '
    'that a named individual still has every attempt in hand, which is the '
    'cheerful wrong answer that lets a client discover on the day that a '
    'renewal exam has become a full re-course.';
COMMENT ON COLUMN public.people_credentials.interim_proof_expires_on IS
    'S1: proof of passing the assessment is valid for up to 3 months from the '
    'date of passing, until the original card is received, and it expires '
    'whether or not the card has arrived. A compliance view that only '
    'recognises issued cards shows a FALSE GAP for up to three months after a '
    'valid pass; one that never expires the interim proof shows a FALSE PASS '
    'afterwards. Both are real, so the bridging state is modelled rather than '
    'approximated.';
COMMENT ON COLUMN public.people_credentials.renewal_opens_on IS
    'When recertification becomes possible — expiry minus the scheme window, '
    'which differs per scheme and is NOT a global "expiring soon" threshold. '
    'S1 is the only document in the corpus that states one (two months, with '
    '"no grace period after their certification expires" and a full re-course '
    'on the far side of it). GU131, S2 and S3 all require renewal before the '
    'end of the final year and state NO window length, so this stays NULL for '
    'them rather than borrowing S1''s answer.';
COMMENT ON COLUMN public.people_credentials.source_sha256 IS
    'Ties the row to the exact source file byte-for-byte, as in 016 and 023. '
    'Note that `raw_extraction` is deliberately ABSENT from this table, unlike '
    '`certificates`: on a personal certificate the verbatim extraction holds a '
    'date of birth, a photograph reference and identity-document numbers, none '
    'of which any compliance check needs. The hash gives the forensic tie '
    'without retaining the contents.';

-- ── credential_prerequisites (§3.2) ─────────────────────────────────────────
-- The edges between credentials. §3.9 sketched a single self-FK,
-- `depends_on_credential_id`, and that is not enough: an S1 lifeguard needs an
-- accredited lifeguard qualification AND a DCAS-approved BLS/First Aid/CPR/AED
-- qualification AND, where DHA requires it, an Occupational Health Card — three
-- prerequisites, not one. A single column would silently hold whichever one was
-- entered last, and the app would show a valid lifeguard certificate while the
-- BLS underneath it had lapsed, which the document says means the person "may
-- not perform lifeguard duties". So: a join table.
--
-- These edges are per-client rather than global because they connect two ROWS,
-- not two concepts. The scheme's statement that a lifeguard needs a BLS
-- qualification belongs with module_obligations (027); THIS table records that
-- Ahmed's lifeguard certificate takes its expiry from Ahmed's BLS card.
CREATE TABLE IF NOT EXISTS public.credential_prerequisites (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id          UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    credential_id            UUID NOT NULL,     -- composite FK below
    prerequisite_credential_id UUID NOT NULL,   -- composite FK below
    applicability            TEXT NOT NULL,     -- deliberately no DEFAULT
    same_issuer_required     BOOLEAN NOT NULL DEFAULT FALSE,
    caps_validity            BOOLEAN NOT NULL DEFAULT TRUE,
    requirement_note         TEXT,
    created_at               TIMESTAMPTZ DEFAULT now(),
    UNIQUE (credential_id, prerequisite_credential_id)
);

ALTER TABLE public.credential_prerequisites DROP CONSTRAINT IF EXISTS credential_prerequisites_credential_fk;
ALTER TABLE public.credential_prerequisites
    ADD CONSTRAINT credential_prerequisites_credential_fk
    FOREIGN KEY (credential_id, organization_id)
    REFERENCES public.people_credentials (id, organization_id)
    ON DELETE RESTRICT;

ALTER TABLE public.credential_prerequisites DROP CONSTRAINT IF EXISTS credential_prerequisites_prereq_fk;
ALTER TABLE public.credential_prerequisites
    ADD CONSTRAINT credential_prerequisites_prereq_fk
    FOREIGN KEY (prerequisite_credential_id, organization_id)
    REFERENCES public.people_credentials (id, organization_id)
    ON DELETE RESTRICT;

-- A credential cannot be its own prerequisite. Longer cycles are NOT preventable
-- by a CHECK and are not prevented here — flagged rather than buried: the
-- resolver must detect them when it walks the graph, because a cycle makes
-- MIN(prerequisite expiries) non-terminating.
ALTER TABLE public.credential_prerequisites DROP CONSTRAINT IF EXISTS credential_prerequisites_no_self_check;
ALTER TABLE public.credential_prerequisites
    ADD CONSTRAINT credential_prerequisites_no_self_check
    CHECK (credential_id <> prerequisite_credential_id);

-- 'conditional_unknown' is the honest state for S1's Occupational Health Card:
-- required "whenever required, as per Dubai Health Authority", with no criteria
-- for WHEN reproduced anywhere in the document. Even the APPLICABILITY of that
-- card cannot be determined from the corpus, so its absence must be reported as
-- indeterminate and must NOT be reported as a breach by a named individual.
ALTER TABLE public.credential_prerequisites DROP CONSTRAINT IF EXISTS credential_prerequisites_applicability_check;
ALTER TABLE public.credential_prerequisites
    ADD CONSTRAINT credential_prerequisites_applicability_check
    CHECK (applicability IN ('mandatory', 'conditional_unknown'));

CREATE INDEX IF NOT EXISTS credential_prerequisites_credential_idx
    ON public.credential_prerequisites (credential_id);
CREATE INDEX IF NOT EXISTS credential_prerequisites_prereq_idx
    ON public.credential_prerequisites (prerequisite_credential_id);
CREATE INDEX IF NOT EXISTS credential_prerequisites_org_idx
    ON public.credential_prerequisites (organization_id);

COMMENT ON TABLE public.credential_prerequisites IS
    'Prerequisite edges between one person''s credentials (§3.2) — the thing '
    '§4.4 has no way to draw. A join table rather than §3.9''s single self-FK '
    'because an S1 lifeguard has THREE prerequisites and an instructor has '
    'five; one column would hold whichever was entered last and the app would '
    'show a valid certificate over a lapsed BLS. Composite FKs to '
    '(id, organization_id) so an edge cannot cross a tenant boundary, the same '
    'device 023 uses for obligations → entitlements.';
COMMENT ON COLUMN public.credential_prerequisites.caps_validity IS
    'TRUE when this prerequisite''s expiry participates in MIN() for the '
    'dependent credential — the §3.1 rule. DEFAULT TRUE because that is the '
    'stated S1 behaviour and because the failure direction is the safe one: '
    'capping too eagerly reports a renewal earlier than necessary, whereas not '
    'capping reports a lapsed lifeguard as current. Set FALSE only for a '
    'prerequisite the document requires at ENTRY but does not tie validity to.';
COMMENT ON COLUMN public.credential_prerequisites.same_issuer_required IS
    'S1: an instructor must hold "a valid lifeguard certificate from the same '
    'certifying agency". DEFAULT FALSE, which is the permissive direction, and '
    'deliberately so: TRUE by default would fail credentials the schemes '
    'expressly permit, and a false accusation about a named person''s '
    'qualification is worse than a check not run. The strict rule is claimed '
    'from the document, per credential, never assumed.';
COMMENT ON COLUMN public.credential_prerequisites.applicability IS
    'mandatory | conditional_unknown. NO DEFAULT. ''conditional_unknown'' means '
    'the document conditions the prerequisite on an external authority whose '
    'trigger it does not reproduce — S1''s Occupational Health Card, required '
    '"whenever required, as per Dubai Health Authority". Its absence is '
    'INDETERMINATE and must never be rendered as a non-compliance.';

-- ── coverage_requirements (§3.7) ────────────────────────────────────────────
-- What must be TRUE about a role being filled, stated per module — deliberately
-- and completely separate from who holds which document.
--
-- S2 §6.1 requires at least one certified OHS Person in Charge PER WORK SHIFT
-- PER WORK LOCATION, "always present throughout the conduct of the work
-- activity". Three shifts across twelve sites is 36 slots that must each be
-- filled by a certified person, and NO SET OF CREDENTIAL ROWS ANSWERS THAT. A
-- client can hold every certificate in the scheme and be non-compliant on a
-- night shift. Holding is a property of a person; coverage is a property of a
-- place and a time.
--
-- The required-count rules differ per standard and none of them lives in §4.4:
-- GU131 is a room-count band table (2 above 100 rooms, 1 for 51–100, none at
-- ≤50); S2 is shifts × locations; S3 says "Certified OHS Practitioners", plural,
-- with NO RATIO AT ALL; S1 says "appropriate for the size of the facility and
-- number of bathers" with no formula. All four shapes have to be expressible,
-- INCLUDING the two that cannot produce a number — because a requirement the
-- app cannot count is still a requirement, and rendering it as "0 required" or
-- omitting it are both lies.
--
-- GLOBAL REFERENCE DATA, not org-scoped, for the same reason as
-- module_obligations (027): what S2 requires does not vary by tenant.
CREATE TABLE IF NOT EXISTS public.coverage_requirements (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id         UUID NOT NULL REFERENCES public.guideline_modules(id) ON DELETE CASCADE,
    standard_id       UUID NOT NULL REFERENCES public.standards(id) ON DELETE RESTRICT,

    credential_type   TEXT NOT NULL,     -- same vocabulary as people_credentials
    basis             TEXT NOT NULL,     -- deliberately no DEFAULT
    required_count    INTEGER,           -- NULL only when basis = 'unquantified'

    -- The band table shape, for GU131's rooms-to-officers table.
    band_metric       TEXT,              -- 'rooms', 'employees'
    band_min          INTEGER,
    band_max          INTEGER,           -- NULL = open-ended upper band

    -- Is mere employment enough, or must the person be THERE?
    presence_required BOOLEAN NOT NULL,  -- deliberately no DEFAULT

    -- Which applicability test credential_covers() must run for this role.
    scope_match       TEXT NOT NULL,     -- none | sector | water_depth | site

    unquantified_note TEXT,              -- required when basis = 'unquantified'

    -- Provenance, on the same terms as module_obligations (027) and spec_limits.
    source_page       INTEGER,
    source_quote      TEXT,
    confidence        TEXT,
    created_at        TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.coverage_requirements DROP CONSTRAINT IF EXISTS coverage_requirements_type_check;
ALTER TABLE public.coverage_requirements
    ADD CONSTRAINT coverage_requirements_type_check
    CHECK (credential_type IN (
        'lifeguard', 'lifeguard_instructor', 'lifeguard_instructor_trainer',
        'pool_plant_operator',
        'ohs_person_in_charge', 'ohs_practitioner', 'health_safety_officer',
        'scheme_trainer', 'examiner', 'invigilator',
        'bls_first_aid', 'bls_first_aid_trainer', 'occupational_health_card',
        'training_record'));

ALTER TABLE public.coverage_requirements DROP CONSTRAINT IF EXISTS coverage_requirements_basis_check;
ALTER TABLE public.coverage_requirements
    ADD CONSTRAINT coverage_requirements_basis_check
    CHECK (basis IN ('per_site', 'per_shift_per_site', 'per_band', 'unquantified'));

ALTER TABLE public.coverage_requirements DROP CONSTRAINT IF EXISTS coverage_requirements_scope_match_check;
ALTER TABLE public.coverage_requirements
    ADD CONSTRAINT coverage_requirements_scope_match_check
    CHECK (scope_match IN ('none', 'sector', 'water_depth', 'site'));

-- An 'unquantified' requirement carries NO number and MUST say why in its own
-- words; every other basis carries one. S1's "appropriate for the size of the
-- facility and number of bathers" and S3's bare plural are real duties with no
-- formula, and the largest single gap in those documents for compliance
-- purposes. Storing 0, or storing 1 as a guess, converts an unanswerable
-- question into a confident wrong answer (§7.4). required_count = 0 IS legal
-- and means something different: GU131's ≤50-room band, where the document
-- positively states that no officer is required.
ALTER TABLE public.coverage_requirements DROP CONSTRAINT IF EXISTS coverage_requirements_count_check;
ALTER TABLE public.coverage_requirements
    ADD CONSTRAINT coverage_requirements_count_check
    CHECK ((coalesce(basis, '') = 'unquantified'
            AND required_count IS NULL
            AND coalesce(btrim(unquantified_note), '') <> '')
        OR (coalesce(basis, '') <> 'unquantified'
            AND required_count IS NOT NULL
            AND required_count >= 0));

-- The band columns exist for basis = 'per_band' and for nothing else. A band
-- metric on a per-shift rule would silently narrow it to one accommodation size.
ALTER TABLE public.coverage_requirements DROP CONSTRAINT IF EXISTS coverage_requirements_band_check;
ALTER TABLE public.coverage_requirements
    ADD CONSTRAINT coverage_requirements_band_check
    CHECK ((coalesce(basis, '') = 'per_band'
            AND coalesce(btrim(band_metric), '') <> ''
            AND band_min IS NOT NULL
            AND (band_max IS NULL OR band_max >= band_min))
        OR (coalesce(basis, '') <> 'per_band'
            AND band_metric IS NULL AND band_min IS NULL AND band_max IS NULL));

ALTER TABLE public.coverage_requirements DROP CONSTRAINT IF EXISTS coverage_requirements_confidence_check;
ALTER TABLE public.coverage_requirements
    ADD CONSTRAINT coverage_requirements_confidence_check
    CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'low'));

-- One rule per module, role and band. coalesce(band_min, -1) because NULLs are
-- distinct in a Postgres unique index, so a plain UNIQUE would permit two
-- contradictory non-band rules for the same role — and "how many are required"
-- returning two answers is worse than it returning none.
CREATE UNIQUE INDEX IF NOT EXISTS coverage_requirements_unique_idx
    ON public.coverage_requirements (module_id, credential_type, coalesce(band_min, -1));

CREATE INDEX IF NOT EXISTS coverage_requirements_module_idx
    ON public.coverage_requirements (module_id);
CREATE INDEX IF NOT EXISTS coverage_requirements_standard_idx
    ON public.coverage_requirements (standard_id);

COMMENT ON TABLE public.coverage_requirements IS
    'What must be TRUE about a role being filled (§3.7), stated per module and '
    'kept deliberately separate from who holds which document. S2 §6.1: at '
    'least one certified OHS Person in Charge PER WORK SHIFT PER WORK LOCATION, '
    '"always present throughout the conduct of the work activity" — three '
    'shifts across twelve sites is 36 slots, and no set of credential rows '
    'answers it. Holding is a property of a person; coverage is a property of a '
    'place and a time. Global reference data like module_obligations (027): '
    'what S2 requires does not vary by tenant. NOTE THE STANDING LIMITATION '
    'recorded in 028''s header: this table states the requirement and the app '
    'cannot yet evaluate it, because there is no roster primitive to evaluate '
    'it against.';
COMMENT ON COLUMN public.coverage_requirements.basis IS
    'per_site | per_shift_per_site | per_band | unquantified. NOT NULL with NO '
    'DEFAULT — the four shapes in the corpus multiply out very differently and '
    'guessing between them misstates a headcount. per_shift_per_site is S2 and '
    'is the one that MULTIPLIES; per_band is GU131''s room-count table; '
    'unquantified is S1''s "appropriate for the size of the facility and number '
    'of bathers" and S3''s bare plural with no ratio at all, both of which are '
    'real duties that support NO verdict.';
COMMENT ON COLUMN public.coverage_requirements.required_count IS
    'How many certified holders the basis requires. NULL ONLY for '
    '''unquantified'', where the document states a duty and no number. 0 is a '
    'DIFFERENT and legitimate value: GU131 positively exempts accommodations of '
    '50 rooms or fewer. Conflating the two — reporting an unquantified duty as '
    '"0 required" — turns an unanswerable question into a clean pass.';
COMMENT ON COLUMN public.coverage_requirements.presence_required IS
    'TRUE when the scheme requires the holder to be PRESENT, not merely '
    'employed — S2''s PIC "must always be present throughout the conduct of the '
    'work activity". NOT NULL with NO DEFAULT in either direction: FALSE by '
    'default understates a live safety duty, TRUE by default asserts a presence '
    'requirement the document may not make. Whoever read the document says '
    'which.';
COMMENT ON COLUMN public.coverage_requirements.scope_match IS
    'Which applicability test credential_covers() must run when counting a '
    'holder against this requirement: none | sector | water_depth | site. '
    '''water_depth'' is S1 — a Shallow Water lifeguard holding a perfectly '
    'valid certificate does not count towards coverage of 2 m of water. '
    '''sector'' is S2/S3, where the certificate face carries the sector and a '
    'sector change invalidates it outright. ''site'' is S1''s water-park and '
    'facility-depth examinations, which tie a person-certificate to a place.';
COMMENT ON COLUMN public.coverage_requirements.unquantified_note IS
    'The document''s own words for a duty it declines to quantify, mandatory '
    'when basis = ''unquantified''. Without it the row is indistinguishable '
    'from an unfinished one — the same failure obligations.trigger_event was '
    'added in 023 to prevent.';

-- ── credential_valid_on() ────────────────────────────────────────────────────
-- Validity is a question about a DATE, not about today — the same reasoning
-- laboratory_accredited_on() (023) applies to accreditation and
-- core/standards.py::citation_is_stale applies to editions. Re-running last
-- year's report must reproduce last year's answer, so a revocation recorded
-- this month must NOT retrospectively un-supervise work that was lawfully
-- supervised before it.
--
-- Three things are checked, and all three must hold:
--   1. STATUS. 'valid' and 'interim' pass. Every other status fails from
--      status_effective_from onwards and passes before it — which is why that
--      column is mandatory for those statuses. A REVOKED CREDENTIAL CAN NEVER
--      READ AS VALID ON OR AFTER ITS EFFECTIVE DATE, by construction.
--   2. THE DATE WINDOW. issued_on ≤ p_on ≤ effective_until, with an interim
--      credential additionally bounded by interim_proof_expires_on. A NULL
--      effective_until does not expire — it means no expiry was derived, and
--      the renewal duty lives on the obligation (as in 023).
--   3. THE PREREQUISITE GRAPH, LIVE. Every prerequisite marked caps_validity
--      must itself be valid on the same date. This is the belt to the cache's
--      braces: if a training record lapsed this morning and nothing has
--      recompute the dependent row's effective_until, this function still
--      returns FALSE. It is what makes "a lapsing dependency is detectable"
--      true even when the derived date is stale.
--
-- Returns FALSE — never NULL — for an unknown credential or a NULL date, so a
-- caller cannot get a permissive answer out of missing data.
--
-- It checks ONE level of prerequisites live, not the whole graph, because each
-- prerequisite's own dependencies are already folded into ITS effective_until.
-- JUDGEMENT CALL, flagged: that is exact when every row's cache is at most one
-- generation stale and conservative-in-the-safe-direction otherwise. A fully
-- recursive walk is the correct long-term answer and belongs in the resolver,
-- where a cycle can be reported rather than hung on.
CREATE OR REPLACE FUNCTION public.credential_valid_on(
    p_credential_id UUID,
    p_on            DATE
) RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.people_credentials c
        WHERE c.id = p_credential_id
          AND p_on IS NOT NULL
          AND c.issued_on <= p_on
          AND (c.effective_until IS NULL OR c.effective_until >= p_on)
          AND (
                c.status IN ('valid', 'interim')
                OR (c.status IN ('expired', 'suspended', 'revoked', 'invalidated', 'superseded')
                    AND c.status_effective_from IS NOT NULL
                    AND c.status_effective_from > p_on)
              )
          AND (c.status <> 'interim'
               OR (c.interim_proof_expires_on IS NOT NULL
                   AND c.interim_proof_expires_on >= p_on))
          AND NOT EXISTS (
                SELECT 1
                FROM public.credential_prerequisites e
                JOIN public.people_credentials p
                  ON p.id = e.prerequisite_credential_id
                WHERE e.credential_id = c.id
                  AND e.caps_validity
                  AND e.applicability = 'mandatory'
                  AND (
                        (p.effective_until IS NOT NULL AND p.effective_until < p_on)
                     OR p.issued_on > p_on
                     OR (p.status NOT IN ('valid', 'interim')
                         AND (p.status_effective_from IS NULL
                              OR p.status_effective_from <= p_on))
                      )
              )
    );
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION public.credential_valid_on(UUID, DATE) IS
    'Was this person''s credential valid on this DATE? Checks status (a revoked '
    'or sector-invalidated credential can never read as valid from its '
    'effective date), the date window including the interim-proof bridge, and '
    'every mandatory validity-capping prerequisite LIVE — so a lapsed training '
    'record makes the lifeguard certificate above it invalid even if nobody has '
    'recomputed effective_until. Returns FALSE, never NULL, for an unknown id '
    'or a NULL date. Deliberately says nothing about SCOPE: a credential can be '
    'perfectly valid and still be the wrong credential for the assignment — '
    'call credential_covers() as well, and report the two failures differently, '
    'because "your certificate has lapsed" and "you are working outside your '
    'specialty" are different findings about a named person.';

-- ── credential_covers() ──────────────────────────────────────────────────────
-- The §3.6 applicability gate: is this credential the RIGHT one for this
-- assignment? Separate from validity on purpose — see the note above.
--
-- The depth test is deliberately asymmetric with the rest of the schema's
-- NULL handling and it is the important line in this function: asking a depth
-- question of a credential with NO recorded depth ceiling returns FALSE, not
-- TRUE. Permissive-on-missing-data is how a Shallow Water lifeguard ends up
-- counted against 2 m of water. It bites on S1's lagoon category — named in
-- scope with no depth rule, no prerequisites and no specialty examination
-- anywhere in the document — and it should: a lagoon lifeguard cannot be
-- assessed against a depth, and inferring that the pool specialty covers a
-- lagoon is exactly the confident wrong answer §7.4 forbids. Lagoon operators
-- are in this product's client base, so this will be met in the field.
CREATE OR REPLACE FUNCTION public.credential_covers(
    p_credential_id      UUID,
    p_site_id            UUID    DEFAULT NULL,
    p_required_scope_key TEXT    DEFAULT NULL,
    p_water_depth_m      NUMERIC DEFAULT NULL
) RETURNS BOOLEAN AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.people_credentials c
        WHERE c.id = p_credential_id
          -- A site-tied credential covers that site and no other. A portable
          -- one (scope_site_id IS NULL) covers wherever it is asked about.
          AND (c.scope_site_id IS NULL OR p_site_id IS NULL OR c.scope_site_id = p_site_id)
          AND (p_required_scope_key IS NULL OR c.scope_key = p_required_scope_key)
          AND (p_water_depth_m IS NULL
               OR (c.scope_max_depth_m IS NOT NULL AND p_water_depth_m <= c.scope_max_depth_m))
    );
$$ LANGUAGE sql STABLE;

COMMENT ON FUNCTION public.credential_covers(UUID, UUID, TEXT, NUMERIC) IS
    'Is this credential APPLICABLE to this assignment (§3.6)? Site tie, '
    'specialty/sector key and water depth. A credential that is perfectly valid '
    'can still be inapplicable — S1''s Shallow Water lifeguard supervising 2 m '
    'of water is the case the notes call probably the single highest-value '
    'check available. Returns FALSE for an unknown id, and FALSE for a depth '
    'question asked of a credential with no recorded depth ceiling: '
    'permissive-on-missing-data here is how someone ends up watching water they '
    'are not certified for. Pair with credential_valid_on(); never substitute '
    'one for the other.';

-- ── RLS ──────────────────────────────────────────────────────────────────────
ALTER TABLE public.people_credentials       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.credential_prerequisites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coverage_requirements    ENABLE ROW LEVEL SECURITY;

GRANT ALL ON public.people_credentials       TO service_role;
GRANT ALL ON public.credential_prerequisites TO service_role;
GRANT ALL ON public.coverage_requirements    TO service_role;

-- EVERY policy below is scoped TO authenticated, for the reason 022 and 023
-- established: Supabase grants SELECT on new public tables to the `anon` role
-- by default, so RLS is the only gate and an unqualified `USING (true)` would
-- publish the table to anyone holding the publishable anon key. On
-- `obligations` that leaks a contractor's exposure; here it would leak NAMED
-- INDIVIDUALS' qualifications, medical-adjacent credentials and disciplinary
-- outcomes — a revoked lifeguard certificate carries a reason, and one of S1's
-- six grounds is substance abuse. This is the most sensitive data in the
-- schema.

-- people_credentials: DELIBERATELY TIGHTER THAN 023's `certificates`, which
-- grants SELECT to the whole tenant. A person's credential is not org-wide
-- reading material. Read is limited to the subject, tenant `admin` and
-- `super_admin`; `operator` and `auditor` get nothing here, which is a
-- deliberate divergence from the "an auditor's read-only view is the point of
-- the product" reasoning applied to obligations. An operator needs to know
-- whether a shift is COVERED, not who holds which document, and an auditor
-- needs the same aggregate — that is what coverage_requirements is for, and it
-- is why the coverage question was modelled apart from the holding question.
-- The aggregate view that serves them (counts, never rows) belongs with the
-- Phase 5 services and must be SECURITY DEFINER; it is not created here because
-- a view that returns compliance counts before there is anything to count would
-- be a view returning zero and looking authoritative.
DROP POLICY IF EXISTS select_people_credentials ON public.people_credentials;
CREATE POLICY select_people_credentials ON public.people_credentials
  FOR SELECT TO authenticated USING (
    subject_user_id = auth.uid()
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
    OR public.get_user_role() = 'super_admin'
  );

-- Writes: admin and super_admin only, and NOT the subject even for their own
-- row. A credential is third-party evidence about a person and must not be
-- editable by the person it certifies (§7.9 — the independence requirement cuts
-- both ways; 023 made the same call on certificates). Note that
-- effective_until is a DERIVED column: even an admin must not hand-enter it,
-- and the Phase 5 write path should compute it under service_role. The database
-- cannot enforce that distinction without a trigger, so it is stated here and
-- in the column comment rather than assumed.
DROP POLICY IF EXISTS mutate_people_credentials ON public.people_credentials;
CREATE POLICY mutate_people_credentials ON public.people_credentials
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
  );

-- credential_prerequisites: the edges are as sensitive as the rows they join —
-- knowing that someone's lifeguard certificate depends on an Occupational
-- Health Card is itself information about that person. Same posture, minus the
-- subject-self-read: the edge names two credentials and the subject test would
-- need a join, so the subject reads their credentials and the graph is resolved
-- for them by the backend.
DROP POLICY IF EXISTS select_credential_prerequisites ON public.credential_prerequisites;
CREATE POLICY select_credential_prerequisites ON public.credential_prerequisites
  FOR SELECT TO authenticated USING (
    (organization_id = public.get_user_organization()
     AND public.get_user_role() = 'admin')
    OR public.get_user_role() = 'super_admin'
  );

DROP POLICY IF EXISTS mutate_credential_prerequisites ON public.credential_prerequisites;
CREATE POLICY mutate_credential_prerequisites ON public.credential_prerequisites
  FOR ALL TO authenticated USING (
    public.get_user_role() = 'super_admin'
    OR (organization_id = public.get_user_organization()
        AND public.get_user_role() = 'admin')
  );

-- coverage_requirements: readable by any authenticated user and writable only
-- by super_admin — the same posture as module_obligations (027) and for the
-- same reason. This is the published record of what a scheme REQUIRES, it
-- contains no personal data at all, and a tenant admin editing it would change
-- what every other tenant is measured against. The contrast with the two tables
-- above is the point of the split: the rule is public, the people are not.
DROP POLICY IF EXISTS select_coverage_requirements ON public.coverage_requirements;
CREATE POLICY select_coverage_requirements ON public.coverage_requirements
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS mutate_coverage_requirements ON public.coverage_requirements;
CREATE POLICY mutate_coverage_requirements ON public.coverage_requirements
  FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');

COMMIT;
