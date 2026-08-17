"""Migration 032 — self-serve provisioning must be possible under RLS.

mutate_org and mutate_profiles (schema_rls.sql, re-scoped by 029) are both
`FOR ALL` with no WITH CHECK, so Postgres reuses their USING clause as the
INSERT check. Both clauses require `... = public.get_user_organization()`, which
is NULL for a caller with no user_profiles row yet — exactly the caller
`_create_super_admin_profile()` (api_server.py:297-318) exists to provision.
Under RLS, both INSERTs that function issues are therefore denied; today this
works only because db/client.py connects as service_role and bypasses RLS.

032 adds `public.bootstrap_self_serve_profile()`, a SECURITY DEFINER function
that provisions the organisation and the caller's own profile atomically, scoped
so tightly that it cannot be turned into an escalation primitive:

  - identity comes ONLY from public.clerk_subject() — the function takes no
    parameters, so there is no argument through which a caller could name
    someone else's identity, an existing organisation, or a role;
  - it refuses outright if the caller already has a profile;
  - it always creates a NEW organisation and always writes role='super_admin'
    of THAT organisation — never join, never choose.

TWO HALVES, like tests/test_rls_clerk_identity.py, which this borrows its psql
harness from:

  STATIC — parses the .sql, no database, asserts the security properties by
  inspection.

  LIVE — applies 032 inside a transaction that is always rolled back (per this
  task's instructions: piping the whole file, with its own BEGIN/COMMIT, into an
  outer BEGIN lets the file's COMMIT escape and persist — that is how 031 was
  once accidentally applied during verification). This module never lets that
  happen: it strips 032's own BEGIN/COMMIT wrapper and embeds the inner
  statements inside its own BEGIN ... ROLLBACK, so the CREATE FUNCTION itself
  never survives the test process. Skips cleanly when Docker or the
  `supabase-db` container is absent — a skip means NOT EXERCISED, not passing.

    scripts/apply_schema.sh --container supabase-db   (not required for this
                                                         module — it applies its
                                                         own migration per test)
    python -m pytest tests/test_bootstrap_migration.py -v
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
UP = MIGRATIONS / "032_bootstrap_self_serve_profile.sql"
DOWN = MIGRATIONS / "032_bootstrap_self_serve_profile_down.sql"
FUNC = "bootstrap_self_serve_profile"

CONTAINER = "supabase-db"


# ═══════════════════════════════════════════════════════════════════════════
# Static half — no database
# ═══════════════════════════════════════════════════════════════════════════


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )


def _up_body() -> str:
    return _strip_sql_comments(UP.read_text(encoding="utf-8"))


def test_032_exists_with_its_reversal():
    assert UP.is_file()
    assert DOWN.is_file()


def test_function_takes_no_parameters():
    """No parameter exists through which a caller could name an identity.

    This is the load-bearing property behind "never accept a caller-supplied
    user id": there is no argument list to smuggle one into.
    """
    body = _up_body()
    m = re.search(
        r"CREATE OR REPLACE FUNCTION public\.%s\s*\(([^)]*)\)" % FUNC, body
    )
    assert m, f"032 does not define public.{FUNC}()"
    assert m.group(1).strip() == "", (
        f"public.{FUNC}() must take zero parameters, found: {m.group(1)!r}"
    )


def test_identity_comes_only_from_clerk_subject():
    """The function body derives identity via clerk_subject(), nothing else."""
    body = _up_body()
    assert "public.clerk_subject()" in body
    # No parameter-shaped identity input (p_user, p_clerk_id, etc.) anywhere.
    assert not re.search(r"\bp_(user|clerk|subject|id)\w*\b", body, re.IGNORECASE)


def test_function_is_security_definer_with_pinned_search_path():
    body = _up_body()
    m = re.search(
        r"CREATE OR REPLACE FUNCTION public\.%s\(\)(.*?)AS \$\$" % FUNC, body, re.S
    )
    assert m, f"032 does not define public.{FUNC}()"
    header = m.group(1)
    assert "SECURITY DEFINER" in header
    assert "SET search_path = public, pg_temp" in header


def test_refuses_a_caller_who_already_has_a_profile():
    """The static half of the escalation guard: the check is present in source."""
    body = _up_body()
    assert "FROM public.user_profiles WHERE clerk_id = v_subject" in body
    assert "IF FOUND THEN" in body
    assert "RAISE EXCEPTION" in body


def test_never_accepts_an_existing_organisation_or_a_chosen_role():
    """The INSERTs are fixed: a new org, and role='super_admin' of it."""
    body = _up_body()
    assert re.search(r"INSERT INTO public\.organizations", body)
    profile_insert = re.search(
        r"INSERT INTO public\.user_profiles.*?;", body, re.S
    )
    assert profile_insert, "032 does not insert a user_profiles row"
    assert "'super_admin'" in profile_insert.group(0)
    # No column list or VALUES expression names an organization_id other than
    # the one this same statement just created (v_org_id).
    assert "v_org_id" in profile_insert.group(0)


def test_execute_granted_to_authenticated_not_anon():
    body = _up_body()
    assert re.search(
        r"GRANT EXECUTE ON FUNCTION public\.%s\(\)\s+TO\s+authenticated\s*;" % FUNC,
        body,
    ), "EXECUTE must be granted to authenticated"
    assert not re.search(
        r"GRANT EXECUTE ON FUNCTION public\.%s\(\).*\banon\b" % FUNC, body
    ), "EXECUTE must NOT be granted to anon"
    assert re.search(
        r"REVOKE ALL ON FUNCTION public\.%s\(\)\s+FROM\s+PUBLIC\s*;" % FUNC, body
    ), "PUBLIC's default EXECUTE grant must be revoked explicitly"
    # REVOKE FROM PUBLIC is not enough on Supabase: its ALTER DEFAULT PRIVILEGES
    # grants EXECUTE on new public functions to anon directly, and revoking
    # PUBLIC leaves that entry in place. Caught only by reading the live ACL
    # after the first apply. See test_anon_really_cannot_execute_it below — this
    # static check exists so the line is not deleted as redundant.
    assert re.search(
        r"REVOKE ALL ON FUNCTION public\.%s\(\)\s+FROM\s+anon\s*;" % FUNC, body
    ), "anon's default EXECUTE grant must be revoked explicitly, not just PUBLIC's"


def test_anon_really_cannot_execute_it():
    """Assert the resulting ACL, not the SQL text.

    The static test above passed while `anon` held EXECUTE, because the file
    genuinely grants only to `authenticated` — Supabase's default privileges had
    already granted anon separately at CREATE FUNCTION time. Reading the
    migration can never reveal that; only the database can. This is the
    difference between testing what we wrote and testing what exists.
    """
    out = _psql(
        "SELECT has_function_privilege('anon', 'public.%s()', 'EXECUTE'),"
        "       has_function_privilege('authenticated', 'public.%s()', 'EXECUTE');"
        % (FUNC, FUNC)
    )
    if "does not exist" in out:
        pytest.skip("032 is not applied to this database")
    anon, authed = [p.strip() for p in out.strip().split("|")]
    assert authed == "t", "authenticated must be able to call the provisioning function"
    assert anon == "f", (
        "anon can EXECUTE the provisioning function — REVOKE FROM PUBLIC does not "
        "remove Supabase's default grant to anon; revoke from anon explicitly"
    )


def test_down_drops_what_up_creates():
    up_functions = set(
        re.findall(r"CREATE OR REPLACE FUNCTION public\.(\w+)\s*\(", _up_body())
    )
    assert up_functions, "expected at least one function defined in 032"
    down_body = _strip_sql_comments(DOWN.read_text(encoding="utf-8"))
    for fn in up_functions:
        assert re.search(
            r"DROP FUNCTION IF EXISTS public\.%s\s*\(\)\s*;" % fn, down_body
        ), f"032_down does not drop public.{fn}()"


# ═══════════════════════════════════════════════════════════════════════════
# Live half — real Postgres, migration applied and rolled back per test
# ═══════════════════════════════════════════════════════════════════════════


def _inner_sql(path: Path) -> str:
    """032's statements with its own BEGIN;/COMMIT; wrapper stripped.

    Piping the whole file (with its own COMMIT) into an outer BEGIN lets that
    COMMIT escape and commit the outer transaction too — the exact mechanism
    that once auto-applied 031 during verification. Stripping the wrapper and
    supplying our own BEGIN/ROLLBACK avoids it entirely.
    """
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\s*BEGIN;\s*", "", text, count=1)
    text = re.sub(r"\s*COMMIT;\s*$", "", text.rstrip(), count=1)
    assert "BEGIN;" not in text.split("\n")[0:1]
    return text


def _psql(sql: str, *, allow_error: bool = False):
    """Run SQL as superuser. Skips if Docker/the container is absent.

    Returns stdout on success. With allow_error=True, returns (returncode,
    stdout, stderr) instead of failing the test on a non-zero exit — used for
    the refusal tests, where a Postgres error IS the expected outcome.
    """
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
        input=sql, capture_output=True, text=True, encoding="utf-8", timeout=120,
    )
    if allow_error:
        return proc.returncode, proc.stdout, proc.stderr
    if proc.returncode != 0:
        pytest.fail(f"psql failed:\n{proc.stderr.strip()}\n\nSQL was:\n{sql}")
    return proc.stdout.strip()


def _row(out: str) -> str:
    rows = [line for line in out.splitlines() if line.strip()]
    assert len(rows) == 1, f"expected one result row, got {len(rows)}: {rows}"
    return rows[0]


def _lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _claim_sql(subject: str) -> str:
    claims = json.dumps({"sub": subject, "role": "authenticated"})
    return "SET LOCAL request.jwt.claims = %s;\n" % _lit(claims)


def _subject() -> str:
    return f"user_zzzbootstrap{uuid.uuid4().hex[:12]}"


def test_a_caller_with_no_profile_gets_exactly_one_org_and_one_profile():
    """The positive case. Without this the refusals below prove nothing.

    Everything happens in ONE transaction/psql invocation — the creation and
    the visibility check both need the org/profile ids the function just
    generated, and those ids don't survive past this transaction's rollback.
    A temp table carries the result from the CREATE step to the CHECK step
    without a second round trip.
    """
    subject = _subject()
    sql = (
        "BEGIN;\n"
        + _inner_sql(UP)
        + "\nSET LOCAL ROLE authenticated;\n"
        + _claim_sql(subject)
        + "CREATE TEMP TABLE _bootstrap_result AS "
          "SELECT * FROM public.bootstrap_self_serve_profile();\n"
        + "SELECT organization_id::text || '|' || profile_id::text "
          "FROM _bootstrap_result;\n"
        # The caller must see their OWN row before any refusal is meaningful —
        # an empty result is not evidence. RLS's select_org policy is
        # `id = get_user_organization()`, so this exercises the live policy,
        # not just the function's return value.
        + "SELECT "
          "(SELECT count(*) FROM public.organizations "
          " WHERE id = (SELECT organization_id FROM _bootstrap_result)) || '|' "
          "|| (SELECT count(*) FROM public.organizations) || '|' "
          "|| (SELECT count(*) FROM public.user_profiles "
          " WHERE id = (SELECT profile_id FROM _bootstrap_result) "
          " AND role = 'super_admin');\n"
    )
    out = _psql(sql)
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 2, f"expected two result rows, got: {lines}"
    org_id, profile_id = lines[0].split("|")
    assert org_id and profile_id

    mine, total, own_profile = lines[1].split("|")
    assert mine == "1", "the caller cannot see the organisation they just created"
    assert total == "1", "the caller sees more than their own organisation"
    assert own_profile == "1", (
        "the caller cannot see their own super_admin profile row"
    )


def test_second_call_by_same_caller_is_rejected():
    """A caller who already has a profile cannot mint another organisation."""
    subject = _subject()
    sql = (
        "BEGIN;\n"
        + _inner_sql(UP)
        + "\nSET LOCAL ROLE authenticated;\n"
        + _claim_sql(subject)
        + "SELECT profile_id FROM public.bootstrap_self_serve_profile();\n"
        + "SELECT profile_id FROM public.bootstrap_self_serve_profile();\n"
    )
    code, out, err = _psql(sql, allow_error=True)
    assert code != 0, "a second call by the same caller must fail, not succeed"
    assert "already has a profile" in err, (
        f"expected the refusal message, got: {err.strip()}"
    )
    # Exactly one row from the first (successful) call, none from the second.
    rows = [l for l in out.splitlines() if l.strip()]
    assert len(rows) == 1, f"expected exactly one successful provisioning: {rows}"


def test_caller_cannot_target_another_subject_via_argument():
    """There is no parameter through which identity can be supplied.

    Calling with an argument must fail with "function does not exist" (42883),
    proving at the database level — not just by source inspection — that
    identity cannot be spoofed via an argument.
    """
    subject = _subject()
    sql = (
        "BEGIN;\n"
        + _inner_sql(UP)
        + "\nSET LOCAL ROLE authenticated;\n"
        + _claim_sql(subject)
        + "SELECT * FROM public.bootstrap_self_serve_profile('user_someone_else');\n"
    )
    code, out, err = _psql(sql, allow_error=True)
    assert code != 0, "calling with an argument must fail"
    assert "does not exist" in err.lower(), (
        f"expected an undefined-function error, got: {err.strip()}"
    )


def test_a_caller_with_no_clerk_subject_is_refused():
    """No JWT claim at all -> clerk_subject() is NULL -> refused, not NULL-matched."""
    sql = (
        "BEGIN;\n"
        + _inner_sql(UP)
        + "\nSET LOCAL ROLE authenticated;\n"
        + "SELECT profile_id FROM public.bootstrap_self_serve_profile();\n"
    )
    code, out, err = _psql(sql, allow_error=True)
    assert code != 0, "a caller with no Clerk subject must be refused"
    assert "no Clerk subject" in err or "no clerk subject" in err.lower()


def test_nothing_persists_after_the_transaction_rolls_back():
    """Confidence check on the harness itself: rollback really rolled back.

    Asserts on the ROWS this test creates, not on whether the function exists.
    It originally asserted the function was absent afterwards, which silently
    encoded "032 has not been applied to this database" — true when written,
    false the moment 032 was applied to the local stack, and the test then
    failed for a reason that had nothing to do with rollback. A test that
    breaks when unrelated state changes is testing the wrong thing.
    """
    subject = _subject()
    sql = (
        "BEGIN;\n"
        + _inner_sql(UP)
        + "\nSET LOCAL ROLE authenticated;\n"
        + _claim_sql(subject)
        + "SELECT profile_id FROM public.bootstrap_self_serve_profile();\n"
        + "ROLLBACK;\n"
    )
    _psql(sql)

    # The subject is unique per run, so any row bearing it can only have come
    # from the transaction above — which rolled back.
    out = _psql(
        "SELECT count(*) FROM public.user_profiles WHERE clerk_id = '%s';" % subject
    )
    assert _row(out) == "0", (
        "a profile created inside the rolled-back transaction survived it — "
        "the harness is committing when it believes it is not"
    )
