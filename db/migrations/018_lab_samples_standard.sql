BEGIN;

-- ── Migration 018: governing standard + method disclosure on lab_samples ──
-- Migration 016 predates the compliance work, so these ten fields were parsed
-- from every certificate and then silently discarded on save: the allowlist in
-- db/queries.py had no column to write them to.
--
-- This matters more than a missing convenience field. `standard_code` is the
-- limit a PASS was judged against — WD-R-260421-0222 cites DM-HSD-GU44-LCWS2 —
-- and `detection_limit` ("4 cfu/l") is what makes a Legionella "Not Detected"
-- a quantitative statement rather than a shrug. Both survived only inside the
-- raw_extraction JSON blob: evidence, but not queryable, so no report or audit
-- could group by the standard applied.
--
-- Requires 016. Run in the Supabase SQL editor. Reversible: 018_..._down.sql.

ALTER TABLE public.lab_samples
    ADD COLUMN IF NOT EXISTS standard_code        TEXT,
    ADD COLUMN IF NOT EXISTS standard_title       TEXT,
    ADD COLUMN IF NOT EXISTS standard_year        TEXT,
    ADD COLUMN IF NOT EXISTS standard_authority   TEXT,
    ADD COLUMN IF NOT EXISTS standard_citation    TEXT,
    ADD COLUMN IF NOT EXISTS additional_standards JSONB,
    ADD COLUMN IF NOT EXISTS test_procedure       TEXT,
    ADD COLUMN IF NOT EXISTS medium_used          TEXT,
    ADD COLUMN IF NOT EXISTS detection_limit      TEXT,
    ADD COLUMN IF NOT EXISTS filtered_volume      TEXT,
    ADD COLUMN IF NOT EXISTS overall_status       TEXT;

ALTER TABLE public.lab_samples
    DROP CONSTRAINT IF EXISTS lab_samples_overall_status_check;
ALTER TABLE public.lab_samples
    ADD CONSTRAINT lab_samples_overall_status_check
    CHECK (overall_status IS NULL
           OR overall_status IN ('COMPLIANT', 'NON_COMPLIANT', 'INCOMPLETE'));

CREATE INDEX IF NOT EXISTS lab_samples_standard_idx
    ON public.lab_samples (organization_id, standard_code);

COMMENT ON COLUMN public.lab_samples.standard_code IS
    'The governing standard a verdict was judged against, e.g. DM-HSD-GU44-LCWS2. '
    'Empty when the certificate cites none — never infer one.';
COMMENT ON COLUMN public.lab_samples.standard_citation IS
    'The citation verbatim as printed. Quotable back to the regulator; if it ever '
    'disagrees with the parsed parts above, this is the one to trust.';
COMMENT ON COLUMN public.lab_samples.detection_limit IS
    'As printed, unit inseparable (e.g. "4 cfu/l"). It is what makes a reported '
    '"Not Detected" a quantitative statement.';
COMMENT ON COLUMN public.lab_samples.overall_status IS
    'COMPLIANT | NON_COMPLIANT | INCOMPLETE. INCOMPLETE is a third state, not a '
    'flavour of pass: unassessed parameters must never read as an all-clear.';

COMMIT;
