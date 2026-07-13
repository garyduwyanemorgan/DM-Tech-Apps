BEGIN;

-- ── Rollback for Migration 011 ──
DROP FUNCTION IF EXISTS public.record_consumption(
    UUID, UUID, UUID, NUMERIC, UUID, TEXT, UUID, UUID, UUID, TEXT);
DROP FUNCTION IF EXISTS public.record_transfer(
    UUID, UUID, UUID, UUID, NUMERIC, UUID, TEXT, TEXT);

COMMIT;
