BEGIN;

-- Reverse of 014_demo_mode.sql. Dropping the table removes every org's demo
-- state — expired-demo read-only enforcement fails open (no key = no block).

DROP TABLE IF EXISTS public.demo_keys;

COMMIT;
