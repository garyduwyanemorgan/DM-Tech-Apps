BEGIN;

-- Reverse of 015_site_address.sql. Drops the stored addresses permanently.

ALTER TABLE public.sites DROP COLUMN IF EXISTS address;

COMMIT;
