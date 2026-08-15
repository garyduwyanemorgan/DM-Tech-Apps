"""The RLS identity helpers must resolve the CLERK subject, not auth.uid().

Migration 029 fixed what the policies test. Migration 030 fixed who they test it
against, and this proves it â€” in both directions:

    a caller holding a Clerk subject   ->  sees exactly their own organisation
    a caller holding no subject        ->  sees nothing

The second half matters as much as the first. `auth.uid()` is the subject of a
*Supabase* JWT; this app authenticates with Clerk and 002_clerk.sql dropped
user_profiles' foreign key to auth.users so that Clerk could own identity. Before
030 the helpers returned NULL for every real user, so all 50 policies matched
nothing. A test that only asserted "no cross-tenant leak" would have passed
against that broken state as loudly as against a working one â€” an empty result
set is not evidence of tenancy. So every positive assertion below first proves
the caller can see their OWN row.

TWO HALVES, DIFFERENT COSTS. The static half parses the .sql files and needs no
database, like tests/test_rls_tenant_scope.py. The live half runs real SQL as the
`authenticated` role with a real JWT claim set, which is the only way to observe
a policy actually executing â€” the application connects as service_role and
bypasses RLS entirely, so nothing in normal operation exercises these.

SKIPPING IS NOT PASSING. The live half skips when Docker or the Supabase
container is absent, following the ethos of tests/test_chain_integration.py. A
skip means THIS WAS NOT EXERCISED. To run it:

    scripts/apply_schema.sh --container supabase-db
    python -m pytest tests/test_rls_clerk_identity.py -v

WHAT THE LIVE HALF TOUCHES. It creates two throwaway organisations named
`zzz-clerk-identity-<random>` and one user_profile in the first, then deletes all
three in fixture teardown. It writes nothing else and reads only what it wrote.
Connection is via `docker exec psql`, the same mechanism scripts/apply_schema.sh
uses, so no new Python dependency is introduced.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "db" / "migrations"
UP = MIGRATIONS / "030_clerk_identity.sql"
DOWN = MIGRATIONS / "030_clerk_identity_down.sql"

CONTAINER = "supabase-db"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Static half â€” no database
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def test_030_exists_with_its_reversal():
    """The re-key is present, and reversible like every other migration."""
    assert UP.is_file()
    assert DOWN.is_file()


def test_030_helpers_resolve_the_clerk_subject():
    """The three helpers key on clerk_id, and none of them mentions auth.uid()."""
    body = _strip_sql_comments(UP.read_text(encoding="utf-8"))
    for fn in (
        "get_user_organization",
        "get_user_role",
        "get_user_profile_id",
    ):
        m = re.search(
            r"CREATE OR REPLACE FUNCTION public\.%s\(\)(.*?)\$\$;" % fn,
            body,
            re.S,
        )
        assert m, f"030 does not redefine {fn}"
        definition = m.group(1)
        assert "clerk_id = public.clerk_subject()" in definition, (
            f"{fn} must resolve the caller through clerk_id, not auth.uid()"
        )
        assert "auth.uid()" not in definition, f"{fn} still reads auth.uid()"


@pytest.mark.parametrize(
    "fn",
    ["clerk_subject", "get_user_organization", "get_user_role", "get_user_profile_id"],
)
def test_030_helpers_are_stable_and_search_path_pinned(fn: str):
    """Both properties are load-bearing, not stylistic.

    STABLE: a VOLATILE helper cannot be hoisted out of a row filter, so Postgres
    re-runs it once per row scanned on every policy-checked table.

    SET search_path: a SECURITY DEFINER function with a mutable search_path is
    the standard privilege-escalation shape â€” a caller who can create objects in
    an earlier schema can shadow user_profiles and choose what the helper reads
    while it runs as the definer.
    """
    body = _strip_sql_comments(UP.read_text(encoding="utf-8"))
    m = re.search(
        r"CREATE OR REPLACE FUNCTION public\.%s\(\)(.*?)AS \$\$" % fn, body, re.S
    )
    assert m, f"030 does not define {fn}"
    header = m.group(1)
    assert "STABLE" in header, f"{fn} must be STABLE â€” it is called per row"
    assert "SET search_path" in header, f"{fn} must pin its search_path"


def test_no_policy_outside_the_reversal_compares_auth_uid():
    """auth.uid() in a policy is always a defect in this schema.

    user_profiles.id and every FK that references it are surrogate uuids with no
    relationship to a Supabase auth user. Comparing one to auth.uid() is
    type-correct and can never match â€” a silent denial rather than a loud error,
    which is why this is worth a scan rather than a code review.

    The historical files are the record of what was applied by hand and 030 fixes
    them forward, exactly as 029 did. 030_down restores the defect deliberately,
    because a reversal that quietly kept the fix would be lying.
    """
    superseded = {
        "023_obligations_entitlements.sql",
        "028_people_credentials.sql",
        "029_rls_tenant_scope.sql",
        "029_rls_tenant_scope_down.sql",
        "030_clerk_identity_down.sql",
    }
    offenders = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in superseded:
            continue
        body = _strip_sql_comments(path.read_text(encoding="utf-8", errors="replace"))
        bad = [
            m.group(1)
            for m in re.finditer(
                r"CREATE POLICY\s+(\w+)\s+ON\s+public\.\w+(.*?);", body, re.S | re.I
            )
            if "auth.uid()" in m.group(2)
        ]
        if bad:
            offenders[path.name] = bad
    assert not offenders, (
        f"policies comparing auth.uid(): {offenders}. Compare against "
        f"public.get_user_profile_id() instead â€” see 030's header."
    )


def test_030_rekeys_all_three_auth_uid_policies():
    """Named explicitly, so dropping one from 030 fails here rather than silently.

    These are the "and you may always see your own row" arms. Losing them would
    remove an individual's access to credential and certificate records ABOUT
    THEM, which is the one arm that exists for the data subject rather than the
    employer.
    """
    body = _strip_sql_comments(UP.read_text(encoding="utf-8"))
    for policy, column in [
        ("select_profiles", "id"),
        ("select_certificates", "subject_user_id"),
        ("select_people_credentials", "subject_user_id"),
    ]:
        m = re.search(
            r"CREATE POLICY\s+%s\s+ON\s+public\.\w+(.*?);" % policy, body, re.S
        )
        assert m, f"030 does not recreate {policy}"
        assert f"{column} = public.get_user_profile_id()" in m.group(1), (
            f"{policy} must compare {column} to get_user_profile_id()"
        )


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Live half â€” real Postgres, real policies, real JWT claims
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•


def _psql(sql: str) -> str:
    """Run SQL as superuser and return stdout, or skip if the stack is absent."""
    if shutil.which("docker") is None:
        pytest.skip("docker not on PATH")
    try:
        running = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"docker unavailable: {type(exc).__name__}: {exc}")
    if running.returncode != 0 or CONTAINER not in running.stdout.split():
        pytest.skip(f"no running container named {CONTAINER}")

    proc = subprocess.run(
        ["docker", "exec", "-i", CONTAINER,
         "psql", "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A", "-U", "postgres",
         "-d", "postgres"],
        input=sql, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        pytest.fail(f"psql failed:\n{proc.stderr.strip()}\n\nSQL was:\n{sql}")
    return proc.stdout.strip()


def _row(out: str) -> str:
    """The single result row.

    `-q` suppresses psql's command tags (BEGIN, SET, ROLLBACK), so the only
    output is the SELECT's own. Asserting exactly one line keeps a query that
    unexpectedly returns several from being read as its last.
    """
    rows = [line for line in out.splitlines() if line.strip()]
    assert len(rows) == 1, f"expected one result row, got {len(rows)}: {rows}"
    return rows[0]


def _as_clerk_user(subject: str | None, query: str) -> str:
    """Run one query as the `authenticated` role with a Clerk subject claim.

    SET LOCAL inside a transaction is what PostgREST does per request, so this
    reproduces the real execution context rather than approximating it. When
    subject is None no claim is set at all, which is the state of every caller
    today â€” the fail-closed case.
    """
    if subject is None:
        claim = ""
    else:
        claims = json.dumps({"sub": subject, "role": "authenticated"})
        claim = "SET LOCAL request.jwt.claims = %s;" % _lit(claims)
    return _psql(
        "BEGIN;\n"
        "SET LOCAL ROLE authenticated;\n"
        f"{claim}\n"
        f"{query}\n"
        "ROLLBACK;\n"
    )


def _lit(value: str) -> str:
    """Single-quoted SQL literal."""
    return "'" + value.replace("'", "''") + "'"


@pytest.fixture(scope="module")
def tenant():
    """Two organisations and one profile in the first. Removed in teardown."""
    tag = uuid.uuid4().hex[:8]
    mine = f"zzz-clerk-identity-mine-{tag}"
    theirs = f"zzz-clerk-identity-theirs-{tag}"
    subject = f"user_zzz{tag}"

    out = _psql(
        "BEGIN;\n"
        f"INSERT INTO public.organizations (name) VALUES ({_lit(mine)});\n"
        f"INSERT INTO public.organizations (name) VALUES ({_lit(theirs)});\n"
        "INSERT INTO public.user_profiles (id, organization_id, role, clerk_id, email)\n"
        "VALUES (gen_random_uuid(),\n"
        f"        (SELECT id FROM public.organizations WHERE name = {_lit(mine)}),\n"
        f"        'admin', {_lit(subject)}, {_lit(subject + '@example.test')});\n"
        "COMMIT;\n"
        f"SELECT (SELECT id FROM public.organizations WHERE name = {_lit(mine)})\n"
        f"    || '|' || (SELECT id FROM public.organizations WHERE name = {_lit(theirs)})\n"
        f"    || '|' || (SELECT id FROM public.user_profiles WHERE clerk_id = {_lit(subject)});"
    )
    mine_id, theirs_id, profile_id = _row(out).split("|")

    yield {
        "subject": subject,
        "org_id": mine_id,
        "other_org_id": theirs_id,
        "profile_id": profile_id,
        "role": "admin",
    }

    _psql(
        "BEGIN;\n"
        f"DELETE FROM public.user_profiles WHERE clerk_id = {_lit(subject)};\n"
        "DELETE FROM public.organizations WHERE name IN "
        f"({_lit(mine)}, {_lit(theirs)});\n"
        "COMMIT;\n"
    )


def test_helpers_resolve_a_clerk_subject(tenant):
    """The positive case. Without this the negatives below prove nothing."""
    got = _as_clerk_user(
        tenant["subject"],
        "SELECT public.get_user_organization() || '|' "
        "    || public.get_user_role() || '|' "
        "    || public.get_user_profile_id();",
    )
    org, role, profile = _row(got).split("|")
    assert org == tenant["org_id"]
    assert role == tenant["role"]
    assert profile == tenant["profile_id"]


def test_helpers_return_null_without_a_subject(tenant):
    """No token, no identity. The fail-closed direction."""
    got = _as_clerk_user(
        None,
        "SELECT coalesce(public.get_user_organization()::text, 'NULL') || '|' "
        "    || coalesce(public.get_user_role(), 'NULL') || '|' "
        "    || coalesce(public.get_user_profile_id()::text, 'NULL');",
    )
    assert _row(got) == "NULL|NULL|NULL"


def test_an_unknown_subject_resolves_to_nothing(tenant):
    """A well-formed token for a user with no profile grants no access.

    api_server.py auto-provisions a profile for an unrecognised Clerk user, but
    that happens in the API layer. At the database boundary an unknown subject
    must be nobody, not a default.
    """
    got = _as_clerk_user(
        "user_zzznonexistent",
        "SELECT coalesce(public.get_user_organization()::text, 'NULL');",
    )
    assert _row(got) == "NULL"


def test_the_caller_sees_their_own_organisation_and_only_it(tenant):
    """The whole point: a live policy, executing, scoped to one tenant.

    select_org is `id = get_user_organization()`, so this exercises 029's
    predicate and 030's identity resolution together. It asserts the caller sees
    their own row â€” otherwise an empty set would look like success â€” and that the
    second organisation is absent.
    """
    got = _as_clerk_user(
        tenant["subject"],
        "SELECT count(*) FILTER (WHERE id = %s) || '|' || count(*)\n"
        "  FROM public.organizations;" % _lit(tenant["org_id"]),
    )
    mine, total = _row(got).split("|")
    assert mine == "1", "the caller cannot see their own organisation"
    assert total == "1", "the caller can see another tenant's organisation"


def test_the_caller_sees_their_own_profile(tenant):
    """select_profiles' self arm, re-keyed from auth.uid() by 030.

    Also covers the invite flow: api_server.py leaves an invited profile with a
    NULL organization_id until it is claimed, so the organisation arm cannot
    carry this read.
    """
    got = _as_clerk_user(
        tenant["subject"],
        "SELECT count(*) FROM public.user_profiles WHERE id = %s;"
        % _lit(tenant["profile_id"]),
    )
    assert _row(got) == "1"
