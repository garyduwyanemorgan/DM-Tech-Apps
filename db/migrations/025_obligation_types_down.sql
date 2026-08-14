BEGIN;

-- ── Rollback for 025_obligation_types.sql ────────────────────────────────────
-- LOSSY, and in a way that is easy to miss: it narrows the CHECK back to 023's
-- four values. Any obligation already stored with one of the twelve values 025
-- added will make the ADD CONSTRAINT fail, and the whole rollback aborts.
--
-- That is deliberate. The alternative — NOT VALID, or deleting the offending
-- rows — would either leave a constraint that lies about what the table
-- contains, or silently destroy compliance duties a client is relying on being
-- tracked. Failing loudly and making somebody look is the correct outcome.
--
-- If you genuinely need to roll back with such rows present, decide what should
-- happen to them first and do that as its own migration. There is no safe
-- automatic answer: a cleaning obligation cannot be mapped onto 'inspection'
-- without asserting something about it that is not true.

ALTER TABLE public.obligations DROP CONSTRAINT IF EXISTS obligations_type_check;
ALTER TABLE public.obligations
    ADD CONSTRAINT obligations_type_check
    CHECK (obligation_type IN ('sampling', 'examination', 'inspection', 'competency'));

COMMENT ON COLUMN public.obligations.obligation_type IS
    'sampling | examination | inspection | competency';

COMMIT;
