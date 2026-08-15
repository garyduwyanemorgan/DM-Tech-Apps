BEGIN;

-- ── Rollback for 028_people_credentials.sql ─────────────────────────────────
-- DESTRUCTIVELY LOSSY, AND LOSSY ABOUT NAMED INDIVIDUALS. Read this header
-- before running it. Nothing dropped here can be regenerated from code:
--
--   * people_credentials holds one row per credential per PERSON — the
--     certificate number, the issuer chain, the specialty or sector it
--     authorises, the derived expiry and the provenance of that derivation,
--     and, where a credential was taken away, the STATUS REASON. Some of those
--     reasons are disciplinary: S1's revocation grounds include falsification,
--     substance abuse and culpability in an accident. This is the most
--     sensitive data in the schema and none of it is recoverable after this
--     file runs.
--   * credential_prerequisites holds the graph — which lifeguard certificate
--     took its expiry from which training record. Losing the edges does not
--     merely lose a convenience: the surviving `certificates` rows in 023
--     carry a stored valid_until with NO record that it was capped by another
--     document, so a re-import afterwards will read every derived expiry as if
--     it were the scheme's full ceiling. That over-grants validity to a named
--     person, which is the §3.3 mis-issuance this migration exists to prevent,
--     arriving through the rollback instead.
--   * coverage_requirements holds the transcribed per-scheme rules (S2's one
--     PIC per shift per location, GU131's room-count bands, the two duties the
--     documents decline to quantify). These came off published PDFs by hand,
--     have no Python seeder, and cost editorial time to reproduce.
--
-- EXPORT BEFORE RUNNING. The same warning 023's header carries, with the added
-- consideration that a deliberate deletion of employee credential data may be
-- exactly what a data-protection request requires — in which case this file is
-- the wrong instrument, because it also destroys the compliance evidence §7.5
-- says must survive an administrative action. Delete the rows, not the tables.
--
-- ORDER. Functions first (they reference the tables), then the edge table, then
-- the credentials, then the standalone reference table. The composite
-- self-references inside people_credentials go with the table, so no constraint
-- has to be dropped separately.
--
-- NO DROP POLICY STATEMENTS APPEAR BELOW, and that is deliberate rather than an
-- omission. `DROP POLICY IF EXISTS p ON t` tolerates a missing POLICY but NOT a
-- missing TABLE: against an absent table it raises 42P01 and aborts this entire
-- transactional rollback — in precisely the partial-state case those lines look
-- like they are protecting against. DROP TABLE removes the table's policies
-- with it, so the statements would be redundant even when they worked. Same
-- reasoning as 023's and 027's `_down`.

DROP FUNCTION IF EXISTS public.credential_covers(UUID, UUID, TEXT, NUMERIC);
DROP FUNCTION IF EXISTS public.credential_valid_on(UUID, DATE);

DROP TABLE IF EXISTS public.credential_prerequisites;
DROP TABLE IF EXISTS public.people_credentials;
DROP TABLE IF EXISTS public.coverage_requirements;

COMMIT;
