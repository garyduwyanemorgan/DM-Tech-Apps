BEGIN;

-- ── Migration 025: widen obligations.obligation_type ─────────────────────────
-- WHY. 023 permitted four types — sampling, examination, inspection, competency.
-- That vocabulary was derived from GU44, the one guideline available when §4.3
-- was written, and it looked complete because GU44 is a sampling-and-inspection
-- document. Loading the extracted corpus against 023 refused **25 obligations**,
-- almost all of them for requiring something outside the list.
--
-- The refused ones are not exotic. They are cleaning, deep cleaning,
-- disinfection, pest control, waste removal, maintenance, permit renewal, health
-- screening and reporting — which is to say, most of what an FM contractor is
-- actually on the hook for day to day, and much of what a client would first
-- expect this product to track. A registry that cannot express "the grease trap
-- must be cleaned monthly" is not a compliance registry for facilities
-- management.
--
-- WHY A WIDER ENUM RATHER THAN FREE TEXT. The vocabulary is now grounded in ten
-- real documents rather than one, so it is no longer a guess. A CHECK still buys
-- what it bought in 023: a typo fails at write time rather than silently
-- creating an obligation category nobody queries, which in a registry whose
-- whole job is noticing absence would be a duty that quietly stops being
-- tracked. Expect this list to grow again — that is a migration, and cheap.
--
-- HOW TO EXTEND IT. Add the value here, do not invent one at a call site, and do
-- not map an unfamiliar duty onto a near-miss. `inspection` and `self_inspection`
-- are kept distinct deliberately: one is performed by an independent party and
-- one by the operator on their own premises, and collapsing them would let a
-- self-declaration satisfy an obligation the guideline requires a third party to
-- discharge. That distinction is the entire basis of §4.7's accreditation gate.

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_type_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_type_check
    CHECK (obligation_type IN (
        -- Evidence-producing: a third party or instrument yields a record that
        -- can be judged. These are the ones §4.7's accreditation gate applies to.
        'sampling',
        'examination',
        'inspection',
        'self_inspection',
        'health_screening',

        -- Recurring operational duties: performed rather than measured. Evidence
        -- is a completion record, not a result, so nothing here is judged against
        -- a spec_limit.
        'cleaning',
        'deep_cleaning',
        'disinfection',
        'pest_control',
        'waste_removal',
        'maintenance',

        -- Administrative: a document or a person's standing must be kept current.
        'competency',
        'permit_renewal',
        'reporting',
        'review',           -- a document must be revisited, e.g. an annual policy review
        'risk_assessment',  -- the GU137 register must be produced and kept current
        'process',          -- a procedure must be in place and followed

        -- Incident-driven: exists only as an event-triggered obligation
        -- (023's obligations_cadence_check), never on a cadence.
        'isolation_and_notification'
    ));

COMMENT ON COLUMN public.obligations.obligation_type IS
    'What kind of duty this is. Widened by 025 from the four values 023 carried, '
    'which came from GU44 alone and refused 25 obligations from ten real '
    'guidelines. Grouped in the migration source by whether the duty produces '
    'judgeable evidence (sampling/examination/inspection/self_inspection/'
    'health_screening), is an operational task with only a completion record '
    '(cleaning/disinfection/pest_control/waste_removal/maintenance), is '
    'administrative (competency/permit_renewal/reporting), or is incident-driven. '
    'inspection and self_inspection are deliberately NOT the same value: one is '
    'independent and one is the operator attesting about their own premises, and '
    'merging them would let a self-declaration discharge a duty the guideline '
    'assigns to a third party.';

-- ── Where this list stops, and why ───────────────────────────────────────────
-- The extraction also produced `third_party_examination_anchorage`,
-- `waste_covering_at_landfill`, `subcontractor_verification`,
-- `training_record_retention`, `waste_disposal_route` and `safe_system_of_work`.
-- Those are not types. They are descriptions of one duty in one guideline, and
-- adding them would grow this CHECK without bound — a new value per document,
-- forever, each one queryable by nobody.
--
-- obligation_type answers "what kind of duty is this", which is what a dashboard
-- groups by and what determines whether §4.7's accreditation gate applies.
-- `obligations.label` answers "which duty", and it is NOT NULL precisely so the
-- specific thing is always recorded. A third-party anchorage examination is an
-- `examination` labelled "Anchorage examination by a competent person". Loading
-- it as its own type would put a category on the dashboard with one member.
--
-- Rule for extending: add a value only when a duty genuinely groups differently
-- from every existing one for a purpose the product acts on. Otherwise map it and
-- put the detail in the label.

-- ── Deliberately NOT added: appeal_window ────────────────────────────────────
-- GU83, GU84 and GU85 each state a window in which an establishment may appeal
-- its grade, and the extraction recorded those as obligations. They are not.
-- An obligation is a duty that ages toward overdue and is discharged by
-- evidence; an appeal window is a right that expires and is discharged by doing
-- nothing. Modelling it here would put "overdue: appeal window" in front of a
-- client who simply chose not to appeal, which is both wrong and alarming.
--
-- If appeal deadlines are worth surfacing they belong on the inspection or grade
-- record that started the clock, not in the obligations registry. Left out until
-- somebody decides that deliberately.

COMMIT;
