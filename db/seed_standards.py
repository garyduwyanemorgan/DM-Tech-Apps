"""Seeds the standards / specification_sets / spec_limits tables from Python.

Migration 022 (DM_COMPLIANCE_SCOPING.md §5 step 1) created these tables empty and
deliberately carried no INSERTs. The values it would have inserted already exist
in Python — core/standards.py KNOWN_EDITIONS and core/constants.py
COMPLIANCE_LIMITS — and copying them into SQL would create the second source of
truth this whole exercise exists to remove. So the seed reads those modules
instead, and the values can only ever have one origin.

    python -m db.seed_standards --dry-run          # print the plan, write nothing
    python -m db.seed_standards --verified-by "…" --verified-on YYYY-MM-DD
    python -m db.seed_standards --apply-updates    # overwrite drifted rows

REQUIRES THE SERVICE ROLE KEY. Every policy in 022 is scoped `TO authenticated`
and every mutate policy requires super_admin, which is resolved from a user JWT.
This script holds no JWT, so service_role — which bypasses RLS — is the only key
that works. With an anon key the INSERT raises 42501 loudly. The dangerous case
is an authenticated non-super_admin: `select_standards` is `USING (true)`, so
reads succeed and the UPDATE then matches zero rows and returns success having
written nothing. Every write here therefore checks its response rather than
trusting it.

WHY RE-RUNNING DOES NOT OVERWRITE BY DEFAULT
--------------------------------------------
The obvious seeder writes its values every time. That is wrong here, because
this file's own documentation asks a human to go and change two things in the
database: link `specification_sets.standard_id` once the source document is
identified, and correct a bound where the published guideline disagrees with
BOUND_RULES. A blind upsert reverts both on the next run, silently, printing the
same "updated" line it prints for a no-op — destroying the one remediation the
docstring exists to demand.

So the default is: **detect drift, report it, write nothing.** `--apply-updates`
opts into overwriting, and says exactly which columns it is about to change.
Inserts are never gated — a missing row is unambiguous.

WHAT THIS SCRIPT CANNOT READ FROM THE MODULES, AND WHY THAT MATTERS
-------------------------------------------------------------------
Two of the columns 022 requires have no counterpart in COMPLIANCE_LIMITS:

  * min_inclusive / max_inclusive — ComplianceLimit stores ("do", 4.0, None,
    "> 4.0"). The operator survives only inside the human-readable display
    string, which 022 forbids parsing back. So strictness has to be stated here.
  * qualifier_rule — no equivalent concept exists in core/constants.py at all.

They are declared in BOUND_RULES below, one entry per parameter, each recording
the evidence it was taken from. That table is genuinely new data, which makes it
the most dangerous thing in this file: a wrong bound is a wrong verdict on a
regulator-facing report. It is therefore fail-closed — a parameter in
COMPLIANCE_LIMITS with no BOUND_RULES entry aborts the run rather than taking a
default. See the min_inclusive column comment in 022 on why no default is safe.

WHY THE LAGOON SET HAS NO standard_id
-------------------------------------
`lagoon_dm_water` is seeded with standard_id NULL, even though a standards row
for GU44 is created in the same run. They are not related. GU44 is *Legionella
Control in Water Systems*; the ten limits in COMPLIANCE_LIMITS are lagoon water
chemistry — pH, DO, TSS, COD, nutrients, faecal indicators. Attributing those
ten to GU44 because it is the only standard we happen to hold would put a false
citation on every lagoon report, and would then feed core/standards.py's
staleness logic a document the numbers never came from.

The honest position is that the published source of these ten limits is not
recorded anywhere in this codebase. Someone must identify it against the DM
document and link the set. Until then NULL — which specification_sets.standard_id
explicitly permits — is correct, and is visible as a gap rather than hidden
behind a plausible wrong answer. Once linked by hand, this seeder leaves it
alone: standard_id is on the human-owned list below.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Any, NamedTuple, Optional

from core.constants import COMPLIANCE_LIMITS
from core.standards import KNOWN_EDITIONS
from db.client import get_client, is_configured
from db.guard import WrongDatabase, assert_deployment

LAGOON_SET_KEY = "lagoon_dm_water"
LAGOON_SET_LABEL = "DM Lagoon Water Quality"
LAGOON_SET_SCOPE = "lagoon"

# Columns a human is expected to set in the database, which this seeder must
# never revert even under --apply-updates. Each is here because some other part
# of this file or of 022 explicitly asks a person to go and change it.
HUMAN_OWNED: dict[str, set[str]] = {
    # The docstring above asks someone to identify the source document and link
    # the set. Reverting that to NULL would undo the remediation.
    "specification_sets": {"standard_id"},
    # 022:128-134 describes promoting a bare superseded date into a real
    # predecessor row. Doing so sets supersedes_id and nulls superseded_issued_on;
    # rewriting the date afterwards violates standards_one_predecessor_check and
    # aborts the run mid-way.
    "standards": {"supersedes_id", "superseded_issued_on", "verified_by", "verified_on"},
}


class BoundRule(NamedTuple):
    """The strictness and qualifier handling COMPLIANCE_LIMITS cannot express."""
    min_inclusive: bool
    max_inclusive: bool
    qualifier_rule: str
    evidence: str


# An inert flag — one describing a bound that is NULL — is set False throughout.
# The value is never read while the bound is absent, but exclusive is the
# stricter reading, so code that someday forgets the NULL check errs toward
# failing a value rather than silently passing one.
_INERT = False

# Every entry below is derived from core/calculations.py::check_compliance, which
# DM_COMPLIANCE_SCOPING.md §5 names as the canonical implementation of the eight
# that currently exist. Seeding anything else would break the parity proof that
# core/specs.py has to pass before those copies can be retired, so this table is
# transcribed from observed behaviour rather than from the published guideline.
#
#   calculations.py:23  two-sided  ->  lim.min_val <= value <= lim.max_val   BOTH INCLUSIVE
#   calculations.py:28  min only   ->  value > lim.min_val                   MIN EXCLUSIVE
#   calculations.py:32  max only   ->  value < lim.max_val                   MAX EXCLUSIVE
#
# NOTE FOR WHOEVER VERIFIES THIS AGAINST THE DM DOCUMENT. These operators are
# NOT arbitrary, and an audit raised the prior that they are document-derived:
# they agree exactly, parameter for parameter, with the notation in the `display`
# strings of COMPLIANCE_LIMITS — "> 4.0" and "< 50" carry strict glyphs and are
# implemented strictly, while pH's "6.0 – 9.0" carries no glyph and is
# implemented inclusively, which is the universal convention for a range in a
# water-quality standard. Someone merely transcribing a table would have written
# <= in all three branches. That corroboration is why preserving this behaviour
# is the safe default rather than a coin toss.
#
# It is still not verification. Where the published document disagrees, the
# document wins — but change it HERE, in BOUND_RULES, as its own commit with the
# parity test updated in the same change. Editing the database directly will not
# survive review and this seeder will report it as drift.
#
# qualifier_rule is 'bound' for all ten: none of these parameters is one where
# mere presence is the breach, so '<X' is judged by X — the upper bound of what
# the true value could be. See the qualifier_rule column comment in 022.
BOUND_RULES: dict[str, BoundRule] = {
    "ph":              BoundRule(True,   True,   "bound", "calculations.py:23 two-sided, <= both ends; display '6.0 – 9.0' has no glyph"),
    "do":              BoundRule(False,  _INERT, "bound", "calculations.py:28 min-only, strict >; display '> 4.0'"),
    "tss":             BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 50'"),
    "turbidity":       BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 75'"),
    "cod":             BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 50'"),
    "ammonia":         BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 5.0'"),
    "phosphate":       BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 5.0'"),
    "oil_grease":      BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 10'"),
    "ecoli":           BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 200'"),
    "total_coliforms": BoundRule(_INERT, False,  "bound", "calculations.py:32 max-only, strict <; display '< 1000'"),
}


class SeedError(Exception):
    """The seed cannot proceed. Never raised for 'already present'."""


# ── Pre-flight ───────────────────────────────────────────────────────────────

def check_bound_rules() -> None:
    """Abort unless every limit has an explicitly stated strictness.

    Fail-closed on purpose. If someone adds an eleventh parameter to
    COMPLIANCE_LIMITS and this seeder quietly defaulted its bounds, the wrong
    verdict would reach a report with nothing anywhere recording that a value
    had been guessed. 022 removed the DEFAULT from these columns for the same
    reason; this is that decision enforced one layer up.
    """
    missing = sorted(set(COMPLIANCE_LIMITS) - set(BOUND_RULES))
    if missing:
        raise SeedError(
            "no bound rule for: " + ", ".join(missing) + ".\n"
            "COMPLIANCE_LIMITS cannot express whether a bound is inclusive, so it "
            "must be stated in BOUND_RULES with the evidence it came from. Read "
            "the published guideline — do not infer it from the display string."
        )

    stale = sorted(set(BOUND_RULES) - set(COMPLIANCE_LIMITS))
    if stale:
        raise SeedError(
            "bound rule for parameter(s) no longer in COMPLIANCE_LIMITS: "
            + ", ".join(stale) + ". Remove them, or restore the limit."
        )

    for key, rule in BOUND_RULES.items():
        lim = COMPLIANCE_LIMITS[key]
        if lim.min_val is None and lim.max_val is None:
            raise SeedError(
                f"{key} is bounded on neither side and would pass every value. "
                "spec_limits_bounded_check would reject it; it does not belong "
                "in a specification set."
            )
        if rule.qualifier_rule not in ("bound", "detect_fails", "unassessable"):
            raise SeedError(
                f"{key}: qualifier_rule {rule.qualifier_rule!r} is not one of the "
                "three 022 permits."
            )


# ── Drift detection ──────────────────────────────────────────────────────────

def _values_differ(current: Any, desired: Any) -> bool:
    """Compare one column, tolerating how PostgREST renders NUMERIC and DATE."""
    if current is None or desired is None:
        return (current is None) != (desired is None)
    if isinstance(desired, bool) or isinstance(current, bool):
        return bool(current) != bool(desired)
    try:
        return abs(float(current) - float(desired)) > 1e-9
    except (TypeError, ValueError):
        return str(current) != str(desired)


def drifted_columns(table: str, current: dict, desired: dict) -> list[str]:
    """Columns where the database disagrees with what the seeder would write.

    Human-owned columns are excluded: they are expected to diverge, and reporting
    them as drift would train the operator to ignore this output.
    """
    owned = HUMAN_OWNED.get(table, set())
    return sorted(
        col for col, want in desired.items()
        if col not in owned and _values_differ(current.get(col), want)
    )


def _write(client, table: str, row: dict, row_id: Optional[str]) -> dict:
    """INSERT or UPDATE one row, refusing to believe a write that wrote nothing.

    The empty-response check is the whole point. Under an authenticated
    non-super_admin key, 022's read policy admits the SELECT while the mutate
    policy rejects the UPDATE, and PostgREST reports that as success with an
    empty body. Without this the seeder prints 'updated' and exits 0 having
    changed nothing at all.
    """
    if row_id:
        res = client.table(table).update(row).eq("id", row_id).execute()
        if not res.data:
            raise SeedError(
                f"UPDATE on {table} id={row_id} matched no rows. The row exists — "
                "it was just read — so this is almost certainly RLS: 022 restricts "
                "writes to super_admin, and this key is not it. Use the service "
                "role key. Nothing after this point would have been written either."
            )
        return res.data[0]

    res = client.table(table).insert(row).execute()
    if not res.data:
        raise SeedError(
            f"INSERT into {table} returned no row. Expected the inserted record "
            "back; check the key has write access under 022's policies."
        )
    return res.data[0]


# ── Upserts, each matched on the natural key 022 declares ────────────────────

def upsert_standard(client, edition, verified_by: Optional[str],
                    verified_on: Optional[date], dry_run: bool,
                    apply_updates: bool) -> Optional[str]:
    """Create or update one standards row. Returns its id."""
    row = {
        "authority": "DM",
        "code": edition.code,
        "guideline_no": _guideline_no(edition.code),
        "title": edition.title,
        "version": edition.current_version,
        "issued_on": edition.current_issue.isoformat(),
        "source_url": edition.source_url,
        "language": "en",
    }

    # Look up by CODE ONLY, deliberately wider than the unique key. Matching the
    # full key (authority, code, version, language) would miss when the version
    # is bumped in core/standards.py — and then INSERT would succeed, leaving two
    # GU44 rows both with supersedes_id NULL and therefore both "current" under
    # 022's derivation. That is not a crash; it is an arbitrary staleness warning,
    # the one failure 022:95-99 exists to prevent.
    existing = (
        client.table("standards")
        .select("id,version,language,supersedes_id,superseded_issued_on,"
                "authority,code,guideline_no,title,issued_on,source_url")
        .eq("authority", "DM")
        .eq("code", edition.code)
        .execute()
    )
    rows = existing.data or []

    exact = [r for r in rows
             if r["version"] == edition.current_version and r["language"] == "en"]
    others = [r for r in rows if r not in exact]

    if not exact and others:
        held = ", ".join(f"{r['version']}/{r['language']}" for r in others)
        raise SeedError(
            f"{edition.code}: the database already holds {held}, but "
            f"core/standards.py now says {edition.current_version}/en.\n"
            "Refusing to insert. A second row would leave two editions of this "
            "code with supersedes_id NULL, and 022 derives currency as 'the "
            "edition nothing supersedes' — so both would read as current and "
            "staleness warnings would fire arbitrarily.\n"
            "Insert the new edition by hand and set its supersedes_id to the "
            "previous row, which is a decision about the document's history and "
            "not something a seeder should infer."
        )

    if exact:
        current = exact[0]
        std_id = current["id"]
        # superseded_issued_on is only ours to set while nobody has promoted the
        # predecessor to a real row. Writing it alongside a non-NULL supersedes_id
        # violates standards_one_predecessor_check and aborts mid-run.
        if not current.get("supersedes_id"):
            row["superseded_issued_on"] = edition.superseded_issue.isoformat()

        changes = drifted_columns("standards", current, row)
        if not changes:
            print(f"  standard {edition.code} {edition.current_version} — unchanged")
        elif dry_run:
            print(f"  [dry-run] standard {edition.code} drift in: {', '.join(changes)}")
        elif apply_updates:
            _write(client, "standards", row, std_id)
            print(f"  updated standard {edition.code} — {', '.join(changes)}")
        else:
            print(f"  standard {edition.code} DIFFERS from the seed in: "
                  f"{', '.join(changes)} — not written (use --apply-updates)")
        return std_id

    row["superseded_issued_on"] = edition.superseded_issue.isoformat()
    # verified_by/verified_on are one fact: 022's paired CHECK rejects half of
    # it. Set only on insert — thereafter it is human-owned.
    if verified_by and verified_on:
        row["verified_by"] = verified_by
        row["verified_on"] = verified_on.isoformat()

    if dry_run:
        print(f"  [dry-run] would insert standard {edition.code} {edition.current_version}")
        return None

    created = _write(client, "standards", row, None)
    print(f"  inserted standard {edition.code} {edition.current_version}")
    return created["id"]


def _guideline_no(code: str) -> Optional[int]:
    """Pull 44 out of 'DM-HSD-GU44-LCWS2'. None when the code carries no GU number."""
    for part in (code or "").upper().split("-"):
        if part.startswith("GU") and part[2:].isdigit():
            return int(part[2:])
    return None


def upsert_lagoon_set(client, dry_run: bool, apply_updates: bool) -> Optional[str]:
    """Create or update the built-in lagoon specification set. Returns its id."""
    row = {
        "key": LAGOON_SET_KEY,
        "label": LAGOON_SET_LABEL,
        "applies_to_scope": LAGOON_SET_SCOPE,
        "notes": (
            "Seeded from core/constants.py COMPLIANCE_LIMITS by db/seed_standards.py. "
            "standard_id is NULL because the published DM document these ten limits "
            "were taken from is not recorded anywhere in the codebase; it must be "
            "identified and linked before this set is cited on a regulator-facing "
            "report."
        ),
    }

    existing = (
        client.table("specification_sets")
        .select("id,key,label,applies_to_scope,notes,standard_id")
        .eq("key", LAGOON_SET_KEY)
        .is_("organization_id", "null")
        .execute()
    )

    if existing.data:
        current = existing.data[0]
        set_id = current["id"]
        changes = drifted_columns("specification_sets", current, row)
        if not changes:
            print(f"  specification set {LAGOON_SET_KEY} — unchanged")
        elif dry_run:
            print(f"  [dry-run] set {LAGOON_SET_KEY} drift in: {', '.join(changes)}")
        elif apply_updates:
            _write(client, "specification_sets", row, set_id)
            print(f"  updated specification set {LAGOON_SET_KEY} — {', '.join(changes)}")
        else:
            print(f"  specification set {LAGOON_SET_KEY} DIFFERS in: "
                  f"{', '.join(changes)} — not written (use --apply-updates)")

        if current.get("standard_id"):
            print("    (standard_id is set and left alone — human-owned)")
        return set_id

    if dry_run:
        print(f"  [dry-run] would insert specification set {LAGOON_SET_KEY}")
        return None

    # organization_id NULL = built-in and shared; standard_id NULL deliberately,
    # see the module docstring.
    created = _write(client, "specification_sets",
                     {**row, "organization_id": None, "standard_id": None}, None)
    print(f"  inserted specification set {LAGOON_SET_KEY}")
    return created["id"]


def upsert_spec_limits(client, set_id: Optional[str], dry_run: bool,
                       apply_updates: bool) -> None:
    """Create or update one spec_limits row per COMPLIANCE_LIMITS entry."""
    by_key: dict[str, dict] = {}
    if set_id:
        res = (
            client.table("spec_limits")
            # spec_set_id must be selected even though it is the column we
            # filtered on: drifted_columns() compares every key in the desired
            # row, so omitting it here makes it read as None and report drift on
            # every limit, every run. False drift is worse than none — it trains
            # the operator to ignore the one report that is meant to stop a
            # silent overwrite.
            .select("id,spec_set_id,parameter_key,parameter_label,unit,min_val,"
                    "max_val,min_inclusive,max_inclusive,display,qualifier_rule")
            .eq("spec_set_id", set_id)
            .execute()
        )
        by_key = {r["parameter_key"]: r for r in (res.data or [])}

    for key, lim in COMPLIANCE_LIMITS.items():
        rule = BOUND_RULES[key]
        row = {
            "spec_set_id": set_id,
            "parameter_key": key,
            "parameter_label": lim.parameter,
            "unit": lim.unit,
            "min_val": lim.min_val,
            "max_val": lim.max_val,
            "min_inclusive": rule.min_inclusive,
            "max_inclusive": rule.max_inclusive,
            # Verbatim from the module. 022 keeps display as output only —
            # never reconstructed from min_val/max_val, never parsed back.
            "display": lim.display,
            "qualifier_rule": rule.qualifier_rule,
        }

        current = by_key.get(key)

        if dry_run:
            if current is None:
                print(f"  [dry-run] would insert limit {key:<16} {lim.display}")
            else:
                changes = drifted_columns("spec_limits", current, row)
                print(f"  [dry-run] limit {key:<16} "
                      + (f"drift in: {', '.join(changes)}" if changes else "unchanged"))
            continue

        if current is None:
            _write(client, "spec_limits", row, None)
            print(f"  inserted limit {key}")
            continue

        changes = drifted_columns("spec_limits", current, row)
        if not changes:
            continue
        if apply_updates:
            _write(client, "spec_limits", row, current["id"])
            print(f"  updated limit {key} — {', '.join(changes)}")
        else:
            # Loud, because a bound differing from the seed is either a
            # correction someone made against the published document — which
            # belongs in BOUND_RULES, not the database — or a value nobody
            # intended. Either way it must not pass unremarked.
            print(f"  LIMIT {key} DIFFERS in: {', '.join(changes)} — not written. "
                  "If this was a deliberate correction, move it into BOUND_RULES.")

    # Limits present in the database but no longer in COMPLIANCE_LIMITS are
    # reported, never deleted. A limit that vanishes silently is a parameter that
    # stops being judged with nothing recording that it stopped.
    orphans = sorted(set(by_key) - set(COMPLIANCE_LIMITS))
    if orphans:
        print(
            "  WARNING: " + ", ".join(orphans) + " exist in the database but not "
            "in COMPLIANCE_LIMITS. Left in place — remove them by hand once you "
            "have confirmed nothing is judged against them."
        )


def verify_complete(client, set_id: Optional[str]) -> None:
    """Re-read the limit set and confirm it is whole.

    There is no transaction here: PostgREST gives one HTTP call per row, so a
    failure part-way leaves a specification set carrying some of its limits. A
    set holding six of ten parameters does not fail loudly — it judges samples
    with four parameters silently unassessed, which is precisely the confident-
    wrong-answer failure §7.4 names as the central risk. So count at the end.
    """
    if not set_id:
        return
    res = (client.table("spec_limits").select("parameter_key")
           .eq("spec_set_id", set_id).execute())
    found = {r["parameter_key"] for r in (res.data or [])}
    missing = sorted(set(COMPLIANCE_LIMITS) - found)
    if missing:
        raise SeedError(
            "the specification set is INCOMPLETE — missing: " + ", ".join(missing) +
            ".\nA partial set judges the missing parameters as unassessed rather "
            "than failing. Re-run the seeder; it is safe to repeat."
        )
    print(f"  verified {len(found)} limits present")


# ── Entry point ──────────────────────────────────────────────────────────────

def seed(verified_by: Optional[str] = None, verified_on: Optional[date] = None,
         dry_run: bool = False, apply_updates: bool = False) -> int:
    check_bound_rules()

    if not is_configured():
        raise SeedError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY to the "
            "service role key — 022 restricts writes on all three tables to "
            "super_admin, which cannot be satisfied without a user JWT."
        )

    client = get_client()
    if client is None:
        raise SeedError("could not create a Supabase client.")

    # Before anything is written, and before --dry-run too: a dry run against the
    # wrong database still tells you a comforting story about a database you must
    # not touch, and the operator would act on it.
    try:
        assert_deployment(client)
    except WrongDatabase as exc:
        raise SeedError(str(exc)) from exc

    if not verified_by:
        print(
            "NOTE: no --verified-by given, so a newly inserted standards row "
            "carries no verification. That is the honest default, and per the "
            "standards.verified_by comment in 022 an unverified standard must not "
            "drive a staleness warning to a client.\n"
        )

    print("standards:")
    for edition in KNOWN_EDITIONS.values():
        upsert_standard(client, edition, verified_by, verified_on,
                        dry_run, apply_updates)

    print("specification_sets:")
    set_id = upsert_lagoon_set(client, dry_run, apply_updates)

    print("spec_limits:")
    upsert_spec_limits(client, set_id, dry_run, apply_updates)

    if not dry_run:
        print("verification:")
        verify_complete(client, set_id)

    print("\ndry run complete — nothing written." if dry_run else "\nseed complete.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan without writing.")
    parser.add_argument("--apply-updates", action="store_true",
                        help="overwrite rows that differ from the seed. Without "
                             "this, drift is reported and left alone.")
    parser.add_argument("--verified-by",
                        help="who checked these facts against the published PDF. "
                             "Recorded on insert only.")
    parser.add_argument("--verified-on",
                        help="ISO date of that check. Required with --verified-by.")
    args = parser.parse_args(argv)

    if bool(args.verified_by) != bool(args.verified_on):
        parser.error(
            "--verified-by and --verified-on must be given together: 022's "
            "standards_verified_pair_check rejects half-recorded provenance, "
            "which reads as verified while naming nobody."
        )
    if args.dry_run and args.apply_updates:
        parser.error("--dry-run and --apply-updates are contradictory.")

    verified_on = None
    if args.verified_on:
        try:
            verified_on = date.fromisoformat(args.verified_on)
        except ValueError:
            parser.error(f"--verified-on must be ISO format (YYYY-MM-DD), "
                         f"got {args.verified_on!r}")

    try:
        return seed(args.verified_by, verified_on, args.dry_run, args.apply_updates)
    except SeedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:                      # noqa: BLE001 — see below
        # Anything else is a PostgREST/network failure part-way through a run
        # that has no transaction around it. Say so plainly: the operator needs
        # to know the database may be half-seeded, and that re-running fixes it.
        print(f"error: {type(exc).__name__}: {exc}\n"
              "The seed may have stopped part-way. There is no transaction "
              "across PostgREST calls, so re-run it — every write matches on a "
              "natural key first and repeating is safe.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
