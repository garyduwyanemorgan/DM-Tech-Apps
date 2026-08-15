# Database migrations

Plain `.sql` files, applied by hand in the Supabase SQL editor. There is no
migration runner and no `schema_migrations` table — the database itself does not
record what has been applied, so **the order below is the only record**.

Each `NNN_name.sql` has a matching `NNN_name_down.sql` that reverses it.

## Applying to a new environment

Run every file in numeric order. They are not independent: 016 creates the
tables that 018 and 021 alter, 019 alters the table 010 creates and drops a
column 017 added, 020 depends on 019, 022 mirrors the scope vocabulary 019
established, and 023 references the tables 022 creates as well as `assets` from
010. Skipping one does not fail loudly — `ADD COLUMN IF NOT EXISTS` and
`CREATE TABLE IF NOT EXISTS` mean a partial apply succeeds quietly and leaves the
schema subtly wrong.

## Bootstrapping a fresh project

Until migration 000 this repository could not stand up a new database at all.
`db/schema.sql` opens with `ALTER TABLE readings ADD COLUMN …` and
`schema_rls.sql` enables RLS on `predictions`, but **neither table was CREATEd
anywhere in the repo** — the original database was built by hand in the Supabase
dashboard and every file since assumed it. `000_base.sql` reconstructs both from
their authoritative uses in `db/queries.py`, and creates the
`deployment_identity` marker row.

Apply in this order, in the Supabase SQL editor:

1. `db/migrations/000_base.sql` — `readings`, `predictions`, `deployment_identity`
2. `db/schema.sql` — `organizations`, `sites`, adds `site_id` to both
3. `db/schema_rls.sql` — `user_profiles`, `get_user_organization()`, `get_user_role()`, policies
4. `db/migrations/001` … `029` in numeric order
5. `python -m db.seed_standards --dry-run`, then without the flag

Note that steps 3 and 4 briefly create policies that 029 then corrects. That is
deliberate: 029 fixes forward rather than rewriting `schema_rls.sql` and eight
historical migrations, because those files are the record of what was applied by
hand to the existing database and rewriting them would not change it. Do not
stop the run before 029.

**000 refuses to run against a database that already has `readings` or
`predictions`.** That is deliberate and is the guard against the one irreversible
mistake available here — pasting the *lagoon* project's credentials into a
fresh-bootstrap run. The lagoon database is a frozen rollback point and must
never be written to by this codebase; it has both tables and years of production
data in them, a fresh project has neither.

`deployment_identity` carries that guard forward at runtime. `db/guard.py`
reads it and refuses to write to a database that does not identify as
`dm-tech-apps` — including one carrying no marker at all, which is what the
lagoon database looks like. The seeder calls it before doing anything, dry runs
included.

022 creates structure only and seeds nothing: its content comes from a Python
seeder that reads `core/standards.py` and `core/constants.py`, so those modules
stay the single source of truth. Applying 022 alone changes no behaviour.

That seeder is `db/seed_standards.py`. Run it after applying 022:

```
python -m db.seed_standards --dry-run          # print the plan, write nothing
python -m db.seed_standards --verified-by "…" --verified-on YYYY-MM-DD
```

It needs the service role key. 022 originally restricted writes on all three
tables to `super_admin`; **029 removed that policy entirely**, so after 029 the
service role is not merely the convenient way to seed them but the only way —
no `authenticated` client can write `standards`, `specification_sets` or
`spec_limits` at all. It is idempotent and never deletes. Note that `min_inclusive`,
`max_inclusive` and `qualifier_rule` have no counterpart in `COMPLIANCE_LIMITS`
and are declared in the seeder's own `BOUND_RULES` table; adding a parameter to
`COMPLIANCE_LIMITS` without a matching rule aborts the seed rather than
defaulting. `tests/test_seed_standards.py` proves the seeded bounds reproduce
`core/calculations.py` verdicts at every bound value.

023 completes the Phase 1 schema and, like 022, seeds nothing. It has no Python
seeder: its content is per-client (entitlements, obligations) or transcribed from
DM's published records (laboratories, module catalogue). Note that
`023_down` is **destructively lossy** — it drops the billing record and the
compliance registry, neither of which can be regenerated from code. Read its
header before running it.

| # | File | What it adds |
|---|---|---|
| 000 | `000_base.sql` | `readings`, `predictions`, `deployment_identity` — run first |
| 001 | `001_billing.sql` | Billing/subscription columns |
| 002 | `002_clerk.sql` | Clerk identity columns |
| 002 | `002_payment_provider.sql` | Payment provider selection |
| 003 | `003_sludge_surveys.sql` | Sludge survey records |
| 004 | `004_sludge_metric.sql` | Sludge metric column |
| 005 | `005_data_requests.sql` | Client data requests |
| 006 | `006_audit_events.sql` | Audit trail |
| 006 | `006_sample_data_pref.sql` | Per-org sample-data toggle |
| 007 | `007_assignments.sql` | Sites + user/site assignments |
| 008 | `008_corrective_actions.sql` | Corrective actions |
| 009 | `009_inventory.sql` | Inventory items and ledger |
| 010 | `010_assets.sql` | `assets`, `maintenance_schedules` |
| 011 | `011_inventory_rpc.sql` | Inventory RPC |
| 012 | `012_fix_append_only_triggers.sql` | Append-only trigger fixes |
| 013 | `013_audit_events_drop_org_fk.sql` | Drops an audit FK |
| 014 | `014_demo_mode.sql` | 30-day demo per org |
| 015 | `015_site_address.sql` | `sites.address` |
| 016 | `016_lab_samples.sql` | `lab_samples`, `lab_results` |
| 017 | `017_report_types.sql` | Org-defined report types |
| 018 | `018_lab_samples_standard.sql` | Governing standard + verdict columns |
| 019 | `019_asset_class_scope.sql` | `assets.asset_class`/`scope`; drops `report_types.scope` |
| 020 | `020_asset_types.sql` | Org-defined asset types |
| 021 | `021_lab_samples_asset_type.sql` | `lab_samples.asset_type` |
| 022 | `022_standards_specifications.sql` | `standards`, `specification_sets`, `spec_limits` |
| 023 | `023_obligations_entitlements.sql` | `laboratories`, `guideline_modules`, `organization_entitlements`, `obligations`, `certificates` |
| 024 | `024_checklists_risk_assessments.sql` | `severity_scales`, `checklist_templates`, `checklist_items`, `inspections`, `inspection_findings`, `risk_assessments` |
| 025 | `025_obligation_types.sql` | Widens `obligations.obligation_type` to the full corpus vocabulary |
| 026 | `026_consumer_product_scope.sql` | Adds `consumer_product` to the scope CHECKs |
| 027 | `027_module_obligations.sql` | `module_obligations` — the duties a guideline states, plus `obligations.module_obligation_id` |
| 028 | `028_people_credentials.sql` | `people_credentials`, `credential_prerequisites`, `coverage_requirements`, `credential_valid_on()`, `credential_covers()` |
| 029 | `029_rls_tenant_scope.sql` | Removes the cross-tenant `super_admin` clause from 41 policies; drops the write policies on the 9 global reference tables |

Two files share the `002` and `006` prefixes. They are independent of each
other, so either order within the pair is fine.

## Rolling back

Apply the `_down` files in **reverse** numeric order. Read the one you intend to
run first: several are lossy by design and say so in their header. `029_down`
loses no data but **reintroduces a known cross-tenant vulnerability** — it is a
faithful reversal, which is exactly the problem; there is no good reason to run
it. `023_down`
destroys entitlements, obligations and certificate evidence with no way back —
export before running it. `028_down` is worse in kind rather than in degree: it
destroys credential records about **named individuals**, including the reasons
credentials were revoked, and the prerequisite graph whose loss makes every
derived expiry read afterwards as the scheme's full ceiling. `019_down`
cannot restore `report_types.scope` as `NOT NULL`, and `018_down` discards the
governing-standard columns (the citations survive inside `raw_extraction`, which
016 makes immutable, but they stop being queryable).

## Adding a migration

- Wrap in `BEGIN; … COMMIT;`, use `IF NOT EXISTS`, and write the `_down` at the
  same time.
- Explain *why* in the header, not just what. The existing files are the model.
- If it adds a column to `lab_samples`, also add it to `_LAB_SAMPLE_COLUMNS` in
  `db/queries.py`, or the value is silently dropped on save with no error —
  `tests/test_lab_sample_persistence.py` scans every migration for
  `ALTER … ADD COLUMN` and will fail if you forget.
- Prefer `coalesce(col, '') = 'x'` over `col = 'x'` in a `CHECK`: with a NULL
  column a bare comparison yields NULL, and Postgres accepts a `CHECK` that is
  not FALSE, so the constraint silently permits what it was written to forbid.

### RLS policies: never write `OR get_user_role() = 'super_admin'`

**`super_admin` is a TENANT role, not a platform one.** `core/authz.py` calls it
Executive Management, and `api_server.py` auto-provisions it to every user who
signs in without an existing profile, each in a fresh organisation of their own.
So a predicate of the form

```sql
organization_id = public.get_user_organization()
OR public.get_user_role() = 'super_admin'    -- ← WRONG
```

does not mean "or the vendor's staff". It means "or the caller is an admin of
*any* organisation on the platform, including one created thirty seconds ago" —
a cross-tenant read on a `SELECT` and a cross-tenant write on a `FOR ALL`. The
same applies to `USING (get_user_role() = 'super_admin')` with no organisation
test at all.

This was copied from migration to migration into 41 policies across 9 files
before anyone noticed (security review H2, fixed by 029). It was easy to miss
because the backend connects as `service_role`, which bypasses RLS entirely, so
no policy here has ever actually executed — a wrong one costs nothing until the
day a JWT-carrying client ships, and then fails silently and completely.

Write one of these two shapes instead:

```sql
-- Tenant table (has an organization_id, or joins to one):
organization_id = public.get_user_organization()
AND public.get_user_role() IN ('admin', 'super_admin')

-- Global reference table (no organization_id — vendor-curated data):
--   a select_… USING (true) policy, and NO write policy whatsoever.
--   The CLI loaders write these as service_role and bypass RLS.
```

`tests/test_rls_tenant_scope.py` scans every `.sql` file here and fails on
either defect shape, so this is enforced rather than merely recommended. The
historical files are listed in its `SUPERSEDED_BY_029` allowlist; do not add to
that list to make a new migration pass.

One more consequence worth knowing: these policies resolve identity through
`auth.uid()` against `user_profiles.id`, which references `auth.users(id)`. This
app authenticates with **Clerk** and keys profiles on `clerk_id`, so
`get_user_organization()` returns NULL for every real user and the policies match
nothing. They are correct-but-inert. **Re-keying those two helper functions onto
the Clerk subject is a prerequisite for any client-side Supabase access** — and
must happen after 029, never before, or the cross-tenant clauses would activate.
