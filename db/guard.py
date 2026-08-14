"""Refuses to let this codebase write to the wrong database.

DM-Tech-Apps was created by copying the DECCA lagoon app wholesale. The two
repositories therefore have identical client code, read the same
SUPABASE_URL/SUPABASE_KEY pair, and differ only in which project those
credentials happen to point at. The standing rule is that the lagoon database is
a frozen rollback point and is never written to by this codebase — but until
migration 000 nothing enforced it, and the failure mode is both silent and
irreversible: a migration or seeder writing into live client data, discovered
later.

The mechanism is a single row in `deployment_identity` (created by
`db/migrations/000_base.sql`) naming which deployment the database is. The lagoon
database will never carry that row, because 000 cannot run there — it aborts on
the `readings` table that already exists.

Call `assert_deployment()` before any write from a script that could plausibly be
pointed at the wrong project. It is deliberately fail-closed: an unreachable, an
unbootstrapped and a wrongly-named database are all refusals, because none of
them is a database this code should be writing to.
"""
from __future__ import annotations

EXPECTED_DEPLOYMENT = "dm-tech-apps"


class WrongDatabase(Exception):
    """The configured database is not the one this codebase may write to."""


def read_deployment(client) -> str | None:
    """Return the deployment name, or None when the marker is absent.

    None covers both "table does not exist" (a database that predates migration
    000, which includes the lagoon one) and "table exists but is empty", since
    neither is a database that has been bootstrapped by this repo. The caller
    decides what to do about it; this function does not raise.
    """
    try:
        res = client.table("deployment_identity").select("deployment").execute()
    except Exception:
        # PostgREST returns an error for an unknown relation. Absent is absent —
        # distinguishing "no table" from "no permission" would need the error
        # shape, and both answers are the same refusal.
        return None
    rows = res.data or []
    return rows[0].get("deployment") if rows else None


def assert_deployment(client, expected: str = EXPECTED_DEPLOYMENT) -> None:
    """Raise WrongDatabase unless the target database is the expected deployment."""
    found = read_deployment(client)

    if found is None:
        raise WrongDatabase(
            "this database carries no deployment_identity row, so it is either "
            "not bootstrapped or not ours.\n"
            "If it is a NEW project: apply db/migrations/000_base.sql first — see "
            "'Bootstrapping a fresh project' in db/migrations/README.md.\n"
            "If you expected an existing database: check SUPABASE_URL. The lagoon "
            "project has no such row and must not be written to by this codebase."
        )

    if found != expected:
        raise WrongDatabase(
            f"this database identifies as {found!r}, not {expected!r}. Refusing to "
            "write.\nCheck SUPABASE_URL — you are connected to a different "
            "deployment than the one this code is for."
        )
