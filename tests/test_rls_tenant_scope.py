"""The `super_admin` cross-tenant clause must not come back (review H2).

`super_admin` is a TENANT role — core/authz.py calls it Executive Management,
and api_server.py hands it to every self-provisioned signup in a fresh org. A
policy predicate of the form

    OR public.get_user_role() = 'super_admin'

therefore reads "or the caller is an admin of any organisation at all", which is
a cross-tenant read on a SELECT and a cross-tenant write on a FOR ALL. Migration
029 removed 41 of these.

The pattern was copied from migration to migration for twelve files — including
028, written the same day the review landed — so removing it once is not enough.
This module fails the build if it reappears anywhere outside the historical
files that 029 supersedes.

Like tests/test_lab_sample_persistence.py, this reads the migration .sql files
directly. No database is involved.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parent.parent / "db" / "migrations"
SCHEMA_RLS = Path(__file__).resolve().parent.parent / "db" / "schema_rls.sql"

# Any mention of the role test, in any spacing, with or without the public.
# prefix. Mentioning it is not itself the defect — see the two shapes below.
SUPER_ADMIN_TEST = re.compile(
    r"get_user_role\(\)\s*=\s*'super_admin'", re.IGNORECASE
)

# Defect shape 1: disjoined. `… OR get_user_role() = 'super_admin'` widens
# whatever predicate precedes it to every organisation on the platform.
DISJOINED_SUPER_ADMIN = re.compile(
    r"\bOR\s+(?:public\.)?get_user_role\(\)\s*=\s*'super_admin'",
    re.IGNORECASE | re.DOTALL,
)

# Defect shape 2: sole predicate. `USING (get_user_role() = 'super_admin')` with
# no organisation test anywhere in the statement — the role alone decides.
#
# The legitimate shape is neither: the role test CONJOINED to an organisation
# test, as in `organization_id = get_user_organization() AND get_user_role() =
# 'super_admin'`, or the role named in an IN list alongside one. Those are how
# 029 rewrites the tenant tables, so a blanket ban on the string would fail the
# fix as loudly as the defect.


def _strip_sql_comments(sql: str) -> str:
    """Drop `--` lines. Headers quote the defect while explaining it."""
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def _policy_statements(sql: str) -> list[tuple[str, str]]:
    """(policy_name, predicate) for every CREATE POLICY in the file."""
    return [
        (m.group(1), m.group(2))
        for m in re.finditer(
            r"CREATE POLICY\s+(\w+)\s+ON\s+public\.\w+(.*?);",
            _strip_sql_comments(sql),
            re.S | re.I,
        )
    ]


def _violations(sql: str) -> list[str]:
    """Policies whose super_admin test is not bound to an organisation."""
    bad = []
    for name, predicate in _policy_statements(sql):
        if not SUPER_ADMIN_TEST.search(predicate):
            continue
        if DISJOINED_SUPER_ADMIN.search(predicate):
            bad.append(f"{name} (super_admin disjoined with OR)")
        elif "get_user_organization()" not in predicate:
            bad.append(f"{name} (super_admin is the sole predicate)")
    return bad

# Files that legitimately still contain it.
#
# The historical migrations are a RECORD of what was applied by hand, in order —
# db/migrations/README.md is explicit that the order is the only record there is,
# so rewriting them would falsify history and would not change any database that
# has already run them. 029 supersedes them by fixing forward.
#
# 029_down restores the defect deliberately, because a reversal that quietly kept
# the fix would be lying about what it does. Its header says so at length.
SUPERSEDED_BY_029 = {
    "016_lab_samples.sql",
    "017_report_types.sql",
    "020_asset_types.sql",
    "022_standards_specifications.sql",
    "023_obligations_entitlements.sql",
    "024_checklists_risk_assessments.sql",
    "027_module_obligations.sql",
    "028_people_credentials.sql",
    "029_rls_tenant_scope_down.sql",
}

# schema_rls.sql is the bootstrap file, applied before 001 on a fresh project. It
# still creates the holed policies and 029 corrects them at the end of the run,
# which is the same fix-forward treatment the numbered migrations get.
SUPERSEDED_FILES = SUPERSEDED_BY_029 | {"schema_rls.sql"}


def _sql_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("*.sql")) + [SCHEMA_RLS]


def test_029_exists_with_its_reversal():
    """The fix itself is present, and reversible like every other migration."""
    assert (MIGRATIONS / "029_rls_tenant_scope.sql").is_file()
    assert (MIGRATIONS / "029_rls_tenant_scope_down.sql").is_file()


@pytest.mark.parametrize("path", _sql_files(), ids=lambda p: p.name)
def test_no_new_cross_tenant_super_admin_clause(path: Path):
    """Any NEW occurrence fails, wherever it appears.

    If you are reading this because your migration failed here: the clause you
    wrote grants access to every organisation on the platform, not to platform
    staff. Scope the predicate to `organization_id = get_user_organization()`
    and put super_admin in the role list, e.g.

        organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'super_admin')

    If the table has no organization_id it is vendor reference data. Give it a
    `select_… USING (true)` policy and NO write policy — the CLI loaders write it
    as service_role and bypass RLS. See 029's header.
    """
    if path.name in SUPERSEDED_FILES:
        pytest.skip(f"{path.name} is superseded by 029 (see SUPERSEDED_BY_029)")
    bad = _violations(path.read_text(encoding="utf-8", errors="replace"))
    assert not bad, (
        f"{path.name} has {len(bad)} policy/policies whose super_admin test is "
        f"not bound to an organisation: {', '.join(bad)}. super_admin is a tenant "
        f"role, not a platform role — see this test's docstring for the fix."
    )


def test_029_drops_every_global_reference_write_policy():
    """The nine vendor-curated tables end up with no authenticated writer.

    Named explicitly rather than derived, so that adding a global table with a
    super_admin write policy fails the test above rather than silently joining a
    list nobody maintains.
    """
    sql = (MIGRATIONS / "029_rls_tenant_scope.sql").read_text(encoding="utf-8")
    for policy, table in [
        ("mutate_standards", "standards"),
        ("mutate_laboratories", "laboratories"),
        ("mutate_guideline_modules", "guideline_modules"),
        ("mutate_module_obligations", "module_obligations"),
        ("mutate_severity_scales", "severity_scales"),
        ("mutate_severity_scale_values", "severity_scale_values"),
        ("mutate_checklist_templates", "checklist_templates"),
        ("mutate_checklist_items", "checklist_items"),
        ("mutate_coverage_requirements", "coverage_requirements"),
    ]:
        assert f"DROP POLICY IF EXISTS {policy} ON public.{table};" in sql, (
            f"029 must drop {policy} — it lets any tenant's Executive Management "
            f"rewrite vendor-curated data."
        )


def test_029_creates_no_policy_carrying_the_defect():
    """029's own CREATEs are clean.

    The fix is only a fix if it does not reintroduce the pattern while rewriting
    41 policies by hand. (029 is not in SUPERSEDED_FILES, so the scan above
    covers it too — this states the intent directly rather than relying on a
    parametrised case that a future skip could quietly remove.)
    """
    sql = (MIGRATIONS / "029_rls_tenant_scope.sql").read_text(encoding="utf-8")
    assert not _violations(sql), (
        "029 recreated a policy whose super_admin test is not organisation-scoped"
    )


def test_the_scan_catches_both_defect_shapes():
    """The guard is not vacuous.

    A scan that passes because its regex never matches anything is worse than no
    scan, so both defect shapes are fed to it here, along with the legitimate
    conjoined form that must NOT trip it.
    """
    disjoined = """
    CREATE POLICY select_thing ON public.things
      FOR SELECT USING (
        organization_id = public.get_user_organization()
        OR public.get_user_role() = 'super_admin'
      );
    """
    sole = """
    CREATE POLICY mutate_thing ON public.things
      FOR ALL TO authenticated USING (public.get_user_role() = 'super_admin');
    """
    legitimate = """
    CREATE POLICY mutate_thing ON public.things
      FOR ALL TO authenticated USING (
        organization_id = public.get_user_organization()
        AND public.get_user_role() IN ('admin', 'super_admin')
      );
    """
    assert _violations(disjoined) == ["select_thing (super_admin disjoined with OR)"]
    assert _violations(sole) == ["mutate_thing (super_admin is the sole predicate)"]
    assert _violations(legitimate) == []


def test_029_scopes_the_commercially_sensitive_tables():
    """The two the review called out by name are org-scoped, not role-only.

    organization_entitlements carries price_agreed; obligations is what 023's own
    header calls the single most damaging table in the schema to leak.
    """
    sql = (MIGRATIONS / "029_rls_tenant_scope.sql").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    for policy in (
        "select_organization_entitlements",
        "mutate_organization_entitlements",
        "select_obligations",
        "mutate_obligations",
    ):
        m = re.search(
            r"CREATE POLICY\s+%s\s+ON\s+public\.\w+(.*?);" % policy, body, re.S
        )
        assert m, f"029 does not recreate {policy}"
        assert "get_user_organization()" in m.group(1), (
            f"{policy} must test the caller's organisation"
        )
