# Database migrations

Plain `.sql` files, applied by hand in the Supabase SQL editor. There is no
migration runner and no `schema_migrations` table — the database itself does not
record what has been applied, so **the order below is the only record**.

Each `NNN_name.sql` has a matching `NNN_name_down.sql` that reverses it.

## Applying to a new environment

Run every file in numeric order. They are not independent: 016 creates the
tables that 018 and 021 alter, 019 alters the table 010 creates and drops a
column 017 added, 020 depends on 019, and 022 mirrors the scope vocabulary 019
established. Skipping one does not fail loudly — `ADD COLUMN IF NOT EXISTS` and
`CREATE TABLE IF NOT EXISTS` mean a partial apply succeeds quietly and leaves the
schema subtly wrong.

022 creates structure only and seeds nothing: its content comes from a Python
seeder that reads `core/standards.py` and `core/constants.py`, so those modules
stay the single source of truth. Applying 022 alone changes no behaviour.

| # | File | What it adds |
|---|---|---|
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

Two files share the `002` and `006` prefixes. They are independent of each
other, so either order within the pair is fine.

## Rolling back

Apply the `_down` files in **reverse** numeric order. Read the one you intend to
run first: several are lossy by design and say so in their header. `019_down`
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
