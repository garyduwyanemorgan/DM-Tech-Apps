"""Loads the extracted guideline JSON in data/dm_guidelines/ into 022 and 023.

This is the bridge between the content work and the product. `db/seed_standards.py`
seeds the ten lagoon limits that already existed in Python; this loads the DM
corpus that was extracted by reading published PDFs — twenty-two documents, an
eighty-one row catalogue, several hundred limits.

    python -m db.load_guidelines                    # DRY RUN — the default
    python -m db.load_guidelines --apply            # write inserts
    python -m db.load_guidelines --apply --apply-updates   # also overwrite drift
    python -m db.load_guidelines --worklist         # what cannot load, and why

It follows db/seed_standards.py throughout: drift is detected and reported rather
than blindly overwritten, human-owned columns are never reverted, every write
response is checked for the silent-RLS-rejection case, and db.guard.assert_deployment
runs before anything — including before a dry run, because a dry run against the
lagoon database still tells a comforting story about a database this codebase must
never touch.

It diverges from the seeder in one deliberate way: **writing requires --apply.**
The seeder writes by default because it seeds ten values that have been in the
codebase for months. This loads hundreds of rows that nobody has checked, into
the tables that ARE the product under per-guideline pricing. The safe direction
is that running it by accident prints a plan.

FOUR RULES THIS FILE EXISTS TO ENFORCE
--------------------------------------

1. NOTHING UNVERIFIED MAY BE SOLD (§7.1, and 023's
   guideline_modules_verified_to_sell_check). Everything in data/dm_guidelines/
   was produced by an agent reading a PDF. No human has checked it. So every
   module row this loader creates carries provenance='unverified' and
   status='coming_soon', and `refuse_to_sell()` re-asserts that on the row
   immediately before it is written — the loader is structurally incapable of
   marking a module available. Both columns are additionally HUMAN_OWNED, so a
   later re-run cannot DEMOTE a module a human has since verified either.
   Verification is a separate, human, later act performed against the PDF.

2. A LIMIT THAT CANNOT BE JUDGED IS SKIPPED, NEVER DEFAULTED. The blocking
   checks are not reimplemented here — `scripts.validate_extractions.check_limit`
   is imported and called, so the gate the validator describes and the gate the
   loader applies cannot drift apart. A null min_inclusive/max_inclusive on a
   real bound is blocking: 022 made those columns NOT NULL with no default
   precisely so a guessed operator cannot reach the database, and guessing one
   here would put a confident wrong verdict on a regulator-facing report. Thirty-
   one such findings block across the corpus today. They are a worklist of pages
   for a human to read, not a bug to code around.

3. issued_on IS NEVER INVENTED. §7.11: the DM portal publishes no issue date.
   The `Date` on each portal page is a CMS record date — GU44's page reads
   27/07/2026 while its V.6 edition issued 2025-08-19 — and it is carried in the
   catalogue as `portal_document_date` for exactly one reason: so that it is
   visibly NOT an issue date. This loader never reads that field. A standard with
   no issue date from inside the PDF is refused, because 022 makes issued_on NOT
   NULL and the only alternative to refusing is fabricating a date that
   citation_is_stale would then act on.

   The consequence is severe and is the headline finding: ALL 81 CATALOGUE ROWS
   ARE REFUSED. Not one carries an issue date. The catalogue can name a document;
   it cannot describe an edition. Standards therefore come only from the
   extraction files, which read the date off the cover page.

4. A CODE IS NEVER DERIVED. Ten catalogue entries have a null code, and two known
   irregulars would be silently corrupted by any pattern-based guess: GU146's code
   is `DM-HSD-146-FL2` with no GU prefix, and GU10's file says `DM-HSD-GU101-VSC2`
   against a listing that calls it guideline 10 (§7.11 — one of the two is a DM
   typo and it must be resolved with DM, not in code). Whatever the document
   recorded is loaded verbatim; a null code is a refusal. Note the direction: a
   guideline NUMBER is parsed out of a code where one is present, which is safe
   and is what the seeder already does. A code is never constructed from a number.

WHAT module_kind COSTS US
-------------------------
023 makes `guideline_modules.module_kind` NOT NULL with no default, because a
report claiming compliance against a guideline that sets no compliance limit is a
misrepresentation to a regulator (§7.12). The five *_certificates.json files
state their own module_kind. The *_limits.json and *_checklist.json files do NOT
carry the field at all — it postdates them.

§7.12 states the kind for five of those documents in prose. Transcribing that
into MODULE_KINDS below, with the evidence, is the same move BOUND_RULES makes in
the seeder: data the extraction cannot express, stated once, in the open, where
it can be reviewed. Everything else gets NO module row rather than a defaulted
one — a missing module is a visible gap, a wrongly-kinded module is a licence to
misrepresent. That is why this loader creates far fewer modules than there are
standards, and the gap is reported as a worklist.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys

from core.console import use_utf8_stdout
from typing import Any, NamedTuple, Optional

from db.client import get_client, is_configured
from db.guard import WrongDatabase, assert_deployment
# Imported, not reimplemented. The validator IS the specification of what 022
# will reject; two copies of that logic would agree today and diverge quietly.
from scripts.validate_extractions import check_limit, check_standard

DATA_DIR = os.path.join("data", "dm_guidelines")
CATALOGUE = os.path.join(DATA_DIR, "catalogue.json")

# The only two values a module row may ever carry when written from here.
UNVERIFIED = "unverified"
COMING_SOON = "coming_soon"

# 023's vocabulary, restated so a bad value fails in Python with a readable
# message rather than as a 23514 from PostgREST half way through a corpus.
MODULE_KINDS_PERMITTED = {"compliance", "monitoring", "process", "delegating", "unusable"}
# Widened by migration 026 — GU116/GU117 govern goods placed on a market,
# not a site under an FM contract. Kept in step with the three CHECKs 026
# moves together (assets, asset_types, specification_sets).
SCOPES_PERMITTED = {"lagoon", "facilities", "consumer_product", None}
# Must match obligations_type_check in migration 025, which widened 023's four
# values after this loader refused 25 obligations from ten real guidelines for
# requiring ordinary FM duties — cleaning, disinfection, pest control, waste
# removal, maintenance. Kept in step by hand: a value permitted here but not by
# the CHECK fails at write time with a 23514 part-way through the corpus, and one
# permitted by the CHECK but not here is silently never loaded.
#
# `appeal_window` is deliberately absent from both. An obligation ages toward
# overdue and is discharged by evidence; an appeal window is a right that expires
# and is discharged by doing nothing. Recording it would put "overdue: appeal
# window" in front of a client who simply chose not to appeal.
OBLIGATION_TYPES = {
    # produce judgeable evidence
    "sampling", "examination", "inspection", "self_inspection", "health_screening",
    # operational duties, evidenced by a completion record
    "cleaning", "deep_cleaning", "disinfection", "pest_control", "waste_removal",
    "maintenance",
    # administrative
    "competency", "permit_renewal", "reporting", "review", "risk_assessment",
    "process",
    # incident-driven; event-triggered only
    "isolation_and_notification",
}

# Columns a human is expected to own in the database, which this loader must
# never revert — the same discipline as seed_standards.HUMAN_OWNED, and for
# sharper reasons here.
HUMAN_OWNED: dict[str, set[str]] = {
    # Verification is the act this loader cannot perform. Once somebody has read
    # the PDF and set verified_by/verified_on, re-running must not erase it. The
    # supersedes pair is human-owned for 022's reason: rewriting
    # superseded_issued_on over a linked chain violates
    # standards_one_predecessor_check and aborts the run mid-way.
    "standards": {"supersedes_id", "superseded_issued_on", "verified_by", "verified_on"},
    # THE IMPORTANT ONE. provenance and status are how a module goes on sale.
    # This loader sets them on INSERT only, to the two values that mean "not for
    # sale". Excluding them from drift means a re-run after somebody verified
    # GU48 will not quietly demote it back to coming_soon — and, symmetrically,
    # that this loader has no code path at all that writes 'available'.
    # The commercial columns are nobody's business but a human's.
    "guideline_modules": {"provenance", "status", "list_price_monthly",
                          "currency", "obligation_type"},
    "specification_sets": set(),
    "spec_limits": set(),
}


class ModuleKind(NamedTuple):
    kind: str
    evidence: str


# module_kind for documents whose extraction file predates the field. Every entry
# is transcribed from DM_COMPLIANCE_SCOPING.md §7.12, which names five documents
# explicitly in its table. Nothing is inferred: a document not listed here and
# not carrying module_kind in its own JSON gets no module row.
#
# Keyed by MODULE KEY (the file stem with its kind-suffix removed), which is this
# product's own identifier for a module and is deliberately not a document code.
MODULE_KINDS: dict[str, ModuleKind] = {
    "gu119": ModuleKind("compliance", "§7.12 table names GU119 as Compliance"),
    "gu81":  ModuleKind("compliance", "§7.12 table names GU81 as Compliance"),
    "gu38":  ModuleKind("monitoring", "§7.12 table names GU38 as Monitoring — risk "
                                      "band and control obligation, no verdict"),
    "gu34":  ModuleKind("process",    "§7.12 table names GU34 as Process — nothing "
                                      "is measured"),
    "gu10":  ModuleKind("delegating", "§7.12 table names GU10 as Delegating — the "
                                      "limit lives in ASHRAE 62.1, not in the DM "
                                      "document"),
    "gu141": ModuleKind("unusable",   "§7.12 table names GU141 as Unusable — the "
                                      "document contradicts itself. 023's "
                                      "guideline_modules_unusable_not_sold_check "
                                      "blocks sale outright"),
}

# §7.13: A PUBLISHED GUIDELINE IS NOT NECESSARILY A LIVE ONE.
#
# GU93 is an unrevised COVID-19 emergency measure (v2, January 2021) that now
# CONTRADICTS the current GU85 — it requires one person per dining table while
# GU85 sizes the hall for a third of the workforce at once — and both are
# currently published on the DM portal. Selling GU93 as a live module would have
# a client enforcing a superseded emergency rule against a current one.
#
# Currency is NOT derivable from the edition chain. Nothing supersedes GU93
# because nobody issued a successor; they simply stopped meaning it.
# `supersedes_id` answers "is there a newer edition", never "is this still in
# force".
#
# THE COLUMN THIS NEEDS IS standards.lifecycle_status, ADDED BY MIGRATION 024,
# WHICH IS BEING WRITTEN SEPARATELY AND IS NOT THIS FILE'S TO CREATE. So this
# loader is written to work either side of it: `lifecycle_column_present()`
# probes for the column once per run, the value is written when it exists, and
# the finding is reported when it does not. Nothing here fails because 024 has
# not been applied yet, and nothing needs editing when it has.
#
# Only DOCUMENTS WHOSE LIFECYCLE IS ACTUALLY KNOWN appear below. A lifecycle is a
# reading of the document and its context, exactly like module_kind, so an
# unlisted document gets NO value written rather than an assumed 'live' — which
# would be this file asserting on the reader's behalf that a document is in
# force. That is the assertion §7.13 exists to stop.
LIFECYCLE_COLUMN = "lifecycle_status"

_lifecycle_present: dict[int, bool] = {}


def lifecycle_column_present(client) -> bool:
    """True when standards.lifecycle_status exists — i.e. 024 has been applied.

    Probed once per client rather than assumed, so this loader works either side
    of migration 024 without editing. Cached because it is asked once per
    document and the answer cannot change mid-run.

    Fails CLOSED: any error answers False, so a document whose lifecycle cannot
    be recorded is reported as unrecorded rather than silently treated as though
    the value had been stored. Claiming to have recorded a lifecycle that was
    dropped is worse than admitting the column is missing.
    """
    key = id(client)
    if key not in _lifecycle_present:
        try:
            client.table("standards").select(LIFECYCLE_COLUMN).limit(1).execute()
            _lifecycle_present[key] = True
        except Exception:
            _lifecycle_present[key] = False
    return _lifecycle_present[key]


class Lifecycle(NamedTuple):
    status: str
    evidence: str


LIFECYCLES: dict[str, Lifecycle] = {
    "gu93": Lifecycle(
        "emergency",
        "§7.13 — unrevised COVID-19 emergency measure (v2, January 2021) that "
        "CONTRADICTS the current GU85. Published, but not a live requirement. "
        "Must not be sold as one."),
}

# The vocabulary §7.13 names. Restated so a bad value fails readably here rather
# than as a 23514 from PostgREST part-way through the corpus.
LIFECYCLES_PERMITTED = {"live", "emergency", "dormant", "withdrawn"}

# An inert inclusivity flag — one describing a bound that is NULL. False
# throughout, exactly as seed_standards._INERT: the value is never read while the
# bound is absent, but exclusive is the stricter reading, so code that someday
# forgets the NULL check errs toward failing a value rather than passing one.
# This is NOT a default for an ambiguous operator; those are blocked by rule 2.
_INERT = False


class LoadError(Exception):
    """The load cannot proceed. Never raised for 'already present' or 'blocked'."""


# ── The report ───────────────────────────────────────────────────────────────

class Report:
    """Everything the run could not do, and why. Printed as a worklist."""

    def __init__(self) -> None:
        self.blocked_standards: list[tuple[str, str]] = []
        self.blocked_limits: list[tuple[str, str]] = []
        self.skipped_sets: list[tuple[str, str]] = []
        self.no_module_kind: list[tuple[str, str]] = []
        self.catalogue_refusals: list[tuple[str, str]] = []
        self.unloadable_obligations: list[tuple[str, int, str]] = []
        self.shape_conflicts: list[tuple[str, str]] = []
        self.counts: dict[str, int] = {}

    def bump(self, name: str, n: int = 1) -> None:
        self.counts[name] = self.counts.get(name, 0) + n

    def print(self, worklist_only: bool = False) -> None:
        def section(title: str, rows) -> None:
            if not rows:
                return
            print(f"\n{title} ({len(rows)})")
            for row in rows:
                print("  " + " — ".join(str(p) for p in row))

        if not worklist_only and self.counts:
            print("\ncounts:")
            for k in sorted(self.counts):
                print(f"  {k:<28} {self.counts[k]}")

        section("STANDARDS REFUSED — need the PDF read", self.blocked_standards)
        section("SETS NOT CREATED", self.skipped_sets)
        section("LIMITS BLOCKED — a page for a human to read", self.blocked_limits)
        section("NO MODULE CREATED — module_kind unknown", self.no_module_kind)
        section("CATALOGUE ROWS REFUSED", self.catalogue_refusals)
        section("OBLIGATIONS NOT LOADED", self.unloadable_obligations)
        section("EXTRACTION SHAPE vs DATABASE SHAPE", self.shape_conflicts)


# ── Fail-closed guards ───────────────────────────────────────────────────────

def refuse_to_sell(row: dict) -> dict:
    """Assert a module row cannot be sold, immediately before it is written.

    Belt and braces over the literals in module_row(). This function is the
    single place the whole file's rule 1 is checkable, and it raises rather than
    corrects: a row arriving here marked available means some code path was added
    that believes it may sell unverified content, and quietly fixing the row
    would leave that path in place.
    """
    if row.get("provenance") != UNVERIFIED or row.get("status") != COMING_SOON:
        raise LoadError(
            f"refusing to write module {row.get('key')!r} with "
            f"status={row.get('status')!r} provenance={row.get('provenance')!r}.\n"
            "Everything in data/dm_guidelines/ was extracted from a PDF by an "
            "agent and checked by nobody (§7.1). A module goes on sale only when "
            "a human has verified it against the published document, and that is "
            "not something a loader can do."
        )
    return row


def check_module_kinds() -> None:
    """Abort unless every stated kind is one 023 permits."""
    for key, mk in MODULE_KINDS.items():
        if mk.kind not in MODULE_KINDS_PERMITTED:
            raise LoadError(
                f"MODULE_KINDS[{key!r}] is {mk.kind!r}, not one of "
                f"{sorted(MODULE_KINDS_PERMITTED)} — 023's "
                "guideline_modules_kind_check would reject it."
            )
        if not mk.evidence.strip():
            raise LoadError(
                f"MODULE_KINDS[{key!r}] records no evidence. A module kind with no "
                "provenance is a guess about what a report may claim."
            )


# ── Drift detection (same contract as seed_standards) ────────────────────────

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
    """Columns where the database disagrees with what the loader would write."""
    owned = HUMAN_OWNED.get(table, set())
    return sorted(
        col for col, want in desired.items()
        if col not in owned and _values_differ(current.get(col), want)
    )


def _write(client, table: str, row: dict, row_id: Optional[str]) -> dict:
    """INSERT or UPDATE one row, refusing to believe a write that wrote nothing.

    022 and 023 restrict every mutate policy to super_admin, resolved from a user
    JWT this script does not hold, so the service role key is the only one that
    works. The dangerous case is an authenticated non-super_admin: the read
    policies admit the SELECT, the UPDATE then matches zero rows, and PostgREST
    reports that as success with an empty body. Without this check the loader
    prints 'updated' and exits 0 having changed nothing.
    """
    if row_id:
        res = client.table(table).update(row).eq("id", row_id).execute()
        if not res.data:
            raise LoadError(
                f"UPDATE on {table} id={row_id} matched no rows. The row exists — "
                "it was just read — so this is almost certainly RLS: 022/023 "
                "restrict writes to super_admin and this key is not it. Use the "
                "service role key. Nothing after this point would have been "
                "written either."
            )
        return res.data[0]

    res = client.table(table).insert(row).execute()
    if not res.data:
        raise LoadError(
            f"INSERT into {table} returned no row. Expected the inserted record "
            "back; check the key has write access under 022/023's policies."
        )
    return res.data[0]


# ── Reading the corpus ───────────────────────────────────────────────────────

KIND_SUFFIXES = ("_limits", "_certificates", "_checklist")


def module_key_for(path: str) -> str:
    """'data/dm_guidelines/gu44_limits.json' -> 'gu44'.

    This is the PRODUCT's key for a module and is deliberately derived from the
    filename rather than from the document code. It is not a code and must never
    be treated as one — rule 4. GU146 is the case that proves it: its code is
    DM-HSD-146-FL2 with no GU prefix, while its extraction file is gu146_*.json.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    for suffix in KIND_SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def extraction_paths(directory: str = DATA_DIR) -> list[str]:
    """Every extraction document, catalogue excluded — it is a different shape."""
    return sorted(
        p for p in glob.glob(os.path.join(directory, "*.json"))
        if os.path.basename(p) != "catalogue.json"
    )


def read_json(path: str) -> Any:
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def guideline_no_from_code(code: str) -> Optional[int]:
    """Pull 44 out of 'DM-HSD-GU44-LCWS2'. None when the code carries no GU number.

    Safe in the direction it runs. Rule 4 forbids the INVERSE — constructing a
    code from a number — which is what would corrupt DM-HSD-146-FL2.
    """
    for part in (code or "").upper().split("-"):
        if part.startswith("GU") and part[2:].isdigit():
            return int(part[2:])
    return None


# ── standards ────────────────────────────────────────────────────────────────

def standard_row(doc: dict) -> tuple[Optional[dict], list[str]]:
    """The standards row for one extraction document, or None with reasons.

    Refusal reasons come from scripts.validate_extractions.check_standard, so the
    gate is the validator's gate. issued_on absent is the common one and is rule 3
    in action: there is no substitute for reading the cover page.
    """
    std = doc.get("standard") or {}
    blocking = [str(f) for f in check_standard(std) if f.level == "BLOCKING"]
    if blocking:
        return None, blocking

    code = std["code"]
    row = {
        "authority": "DM",
        "code": code,                                   # verbatim, never derived
        "guideline_no": std.get("guideline_no") if std.get("guideline_no") is not None
                        else guideline_no_from_code(code),
        "title": std["title"],
        "version": std["version"],                      # verbatim, never from a filename
        "issued_on": std["issued_on"],                  # from inside the PDF only
        "source_url": std.get("source_url"),
        "language": std.get("language", "en"),
    }
    return row, []


def upsert_standard(client, row: dict, dry_run: bool, apply_updates: bool,
                    report: Report) -> Optional[str]:
    """Create or update one standards row. Returns its id, or None in a dry run."""
    code = row["code"]

    # Look up by CODE ONLY, deliberately wider than 022's unique key, for the
    # reason seed_standards documents: matching the full key would miss a version
    # bump, INSERT would then succeed, and two editions of one code would both
    # have supersedes_id NULL — two heads, and 022 derives currency as "the
    # edition nothing supersedes". Arbitrary staleness warnings, not a crash.
    existing = (
        client.table("standards")
        .select("id,version,language,supersedes_id,superseded_issued_on,authority,"
                "code,guideline_no,title,issued_on,source_url")
        .eq("authority", "DM")
        .eq("code", code)
        .execute()
    )
    rows = existing.data or []
    exact = [r for r in rows
             if r.get("version") == row["version"] and r.get("language") == row["language"]]
    others = [r for r in rows if r not in exact]

    if not exact and others:
        held = ", ".join(f"{r.get('version')}/{r.get('language')}" for r in others)
        report.blocked_standards.append((
            code,
            f"database holds {held}; the extraction says "
            f"{row['version']}/{row['language']}. Not inserting: a second row "
            "would leave two editions with supersedes_id NULL and both would read "
            "as current. Link the chain by hand — which edition superseded which "
            "is a fact about the document's history, not something a loader infers."
        ))
        return None

    if exact:
        current = exact[0]
        std_id = current["id"]
        changes = drifted_columns("standards", current, row)
        if not changes:
            print(f"  standard {code} — unchanged")
        elif dry_run:
            print(f"  [dry-run] standard {code} drift in: {', '.join(changes)}")
        elif apply_updates:
            _write(client, "standards", row, std_id)
            print(f"  updated standard {code} — {', '.join(changes)}")
        else:
            print(f"  standard {code} DIFFERS in: {', '.join(changes)} — not "
                  "written (use --apply-updates)")
        return std_id

    if dry_run:
        print(f"  [dry-run] would insert standard {code} {row['version']}")
        return None

    created = _write(client, "standards", row, None)
    report.bump("standards inserted")
    print(f"  inserted standard {code} {row['version']}")
    return created["id"]


# ── specification_sets and spec_limits ───────────────────────────────────────

def limit_rows(spec_set: dict, set_key: str, report: Report) -> tuple[list[dict], int]:
    """Loadable limit rows for one set, and how many were blocked.

    A blocked limit is SKIPPED and recorded. It is never defaulted: 022 removed
    the DEFAULT from min_inclusive/max_inclusive so that a guessed operator cannot
    reach the database, and inventing one here would route around the one control
    standing between an ambiguous table cell and a regulator-facing verdict.
    """
    rows: list[dict] = []
    blocked = 0
    seen: set[str] = set()

    for lim in spec_set.get("limits") or []:
        pkey = lim.get("parameter_key") or "<no key>"
        where = f"{set_key}.{pkey}"

        findings = [f for f in check_limit(lim, where) if f.level == "BLOCKING"]
        if pkey in seen:
            report.blocked_limits.append(
                (where, "duplicate parameter_key within the set — violates "
                        "UNIQUE (spec_set_id, parameter_key)"))
            blocked += 1
            continue
        seen.add(pkey)

        if findings:
            for f in findings:
                report.blocked_limits.append((where, f.message))
            blocked += 1
            continue

        rows.append({
            "parameter_key": pkey,
            "parameter_label": lim["parameter_label"],
            "unit": lim.get("unit"),
            "min_val": lim.get("min_val"),
            "max_val": lim.get("max_val"),
            # Never a guess: check_limit above has already refused any row whose
            # inclusivity is null on a bound that exists. _INERT applies only
            # where the bound itself is NULL and the flag is never read.
            "min_inclusive": lim["min_inclusive"] if lim.get("min_val") is not None else _INERT,
            "max_inclusive": lim["max_inclusive"] if lim.get("max_val") is not None else _INERT,
            "display": lim["display"],              # output only — never parsed back
            "qualifier_rule": lim["qualifier_rule"],
        })

    return rows, blocked


def set_row(spec_set: dict, standard_id: Optional[str], loaded: int,
            blocked: int) -> dict:
    """One specification_sets row, with its own completeness stated in notes.

    The partial-set note is not decoration. A set holding six of ten parameters
    does not fail loudly — it judges the other four as unassessed, silently, which
    is the confident-wrong-answer failure §7.4 names as the central risk. Writing
    the shortfall into the row makes it visible to anyone reading the table
    rather than only to whoever watched this script run.
    """
    note = (
        f"Loaded from {DATA_DIR} by db/load_guidelines.py. UNVERIFIED — extracted "
        f"from the published PDF by an agent and checked by no human (§7.1). "
        f"{loaded} of {loaded + blocked} limits loaded."
    )
    if blocked:
        note += (f" {blocked} BLOCKED and not loaded — this set is INCOMPLETE and "
                 "must not judge a sample until they are read from the document.")
    if spec_set.get("unsellable_reason"):
        note += " UNSELLABLE: " + spec_set["unsellable_reason"]
    if spec_set.get("source_section"):
        note += " Source: " + str(spec_set["source_section"])

    return {
        "key": spec_set["key"],
        "label": spec_set["label"],
        "applies_to_scope": spec_set.get("applies_to_scope"),
        "standard_id": standard_id,
        "notes": note,
    }


def upsert_set(client, row: dict, limits: list[dict], dry_run: bool,
               apply_updates: bool, report: Report) -> None:
    """Create or update one built-in specification set and its limits."""
    key = row["key"]
    existing = (
        client.table("specification_sets")
        .select("id,key,label,applies_to_scope,notes,standard_id")
        .eq("key", key)
        .is_("organization_id", "null")
        .execute()
    )

    set_id: Optional[str] = None
    if existing.data:
        current = existing.data[0]
        set_id = current["id"]
        changes = drifted_columns("specification_sets", current, row)
        if not changes:
            print(f"  set {key} — unchanged")
        elif dry_run:
            print(f"  [dry-run] set {key} drift in: {', '.join(changes)}")
        elif apply_updates:
            _write(client, "specification_sets", row, set_id)
            print(f"  updated set {key} — {', '.join(changes)}")
        else:
            print(f"  set {key} DIFFERS in: {', '.join(changes)} — not written "
                  "(use --apply-updates)")
    elif dry_run:
        print(f"  [dry-run] would insert set {key} with {len(limits)} limits")
    else:
        created = _write(client, "specification_sets",
                         {**row, "organization_id": None}, None)
        set_id = created["id"]
        report.bump("specification_sets inserted")
        print(f"  inserted set {key}")

    upsert_limits(client, set_id, limits, dry_run, apply_updates, report)


def upsert_limits(client, set_id: Optional[str], limits: list[dict], dry_run: bool,
                  apply_updates: bool, report: Report) -> None:
    by_key: dict[str, dict] = {}
    if set_id:
        res = (client.table("spec_limits")
               .select("id,parameter_key,parameter_label,unit,min_val,max_val,"
                       "min_inclusive,max_inclusive,display,qualifier_rule")
               .eq("spec_set_id", set_id).execute())
        by_key = {r["parameter_key"]: r for r in (res.data or [])}

    for limit in limits:
        row = {**limit, "spec_set_id": set_id}
        current = by_key.get(limit["parameter_key"])

        if dry_run:
            continue
        if current is None:
            _write(client, "spec_limits", row, None)
            report.bump("spec_limits inserted")
            continue

        changes = drifted_columns("spec_limits", current, row)
        if not changes:
            continue
        if apply_updates:
            _write(client, "spec_limits", row, current["id"])
            print(f"    updated limit {limit['parameter_key']} — {', '.join(changes)}")
        else:
            # Loud. A bound differing from the extraction is either a correction
            # somebody made against the published document — which is exactly the
            # verification act this loader cannot perform, and which must not be
            # reverted — or a value nobody intended.
            print(f"    LIMIT {limit['parameter_key']} DIFFERS in: "
                  f"{', '.join(changes)} — not written.")


# ── guideline_modules ────────────────────────────────────────────────────────

def resolve_module_kind(mod_key: str, doc: dict) -> Optional[ModuleKind]:
    """The document's own module_kind, else the stated one, else None.

    None means NO MODULE ROW. 023 has no default for this column because
    defaulting to 'compliance' manufactures authority the document does not have,
    and defaulting to anything else silently disables modules that should judge.
    A gap in the catalogue is visible; a wrongly-kinded module is a licence to
    misrepresent to a regulator (§7.12).
    """
    stated = doc.get("module_kind")
    if stated:
        if stated not in MODULE_KINDS_PERMITTED:
            raise LoadError(
                f"{mod_key}: module_kind {stated!r} in the extraction is not one "
                f"of {sorted(MODULE_KINDS_PERMITTED)}."
            )
        return ModuleKind(stated, f"stated by the extraction file for {mod_key}")
    return MODULE_KINDS.get(mod_key)


def module_row(mod_key: str, standard_id: Optional[str], std: dict,
               kind: ModuleKind, category: Optional[str]) -> dict:
    """One guideline_modules row that cannot be sold. See rule 1."""
    return refuse_to_sell({
        "standard_id": standard_id,
        "key": mod_key,
        "label": std.get("title") or mod_key,
        "category": category,
        "module_kind": kind.kind,
        # THE TWO COLUMNS THAT MATTER. Literals, not parameters — there is no
        # argument, flag or config that can make this loader write anything else.
        "status": COMING_SOON,
        "provenance": UNVERIFIED,
        "notes": (
            f"Loaded by db/load_guidelines.py from {DATA_DIR}. module_kind "
            f"evidence: {kind.evidence}. UNVERIFIED — no human has checked this "
            "against the published DM PDF (§7.1). Promotion to status='available' "
            "requires provenance='verified' first and is a human act."
        ),
    })


def upsert_module(client, row: dict, dry_run: bool, apply_updates: bool,
                  report: Report) -> None:
    key = row["key"]
    existing = (client.table("guideline_modules")
                .select("id,key,label,category,module_kind,status,provenance,"
                        "notes,standard_id")
                .eq("key", key).execute())

    if existing.data:
        current = existing.data[0]
        changes = drifted_columns("guideline_modules", current, row)
        if current.get("provenance") == "verified":
            print(f"  module {key} — VERIFIED in the database; provenance and "
                  "status left alone (human-owned)")
        if not changes:
            print(f"  module {key} — unchanged")
        elif dry_run:
            print(f"  [dry-run] module {key} drift in: {', '.join(changes)}")
        elif apply_updates:
            _write(client, "guideline_modules", row, current["id"])
            print(f"  updated module {key} — {', '.join(changes)}")
        else:
            print(f"  module {key} DIFFERS in: {', '.join(changes)} — not written "
                  "(use --apply-updates)")
        return

    if dry_run:
        print(f"  [dry-run] would insert module {key} "
              f"({row['module_kind']}, {row['status']}/{row['provenance']})")
        return

    _write(client, "guideline_modules", refuse_to_sell(row), None)
    report.bump("guideline_modules inserted")
    print(f"  inserted module {key} ({row['module_kind']}, coming_soon/unverified)")


# ── obligations and examinations: reported, not loaded ───────────────────────
#
# THIS IS A FINDING, NOT AN OMISSION. See the module docstring for the summary;
# the detail is here because it is where somebody will come looking.
#
# The `obligations` arrays in the extraction files are TEMPLATE obligations: what
# the guideline requires of anybody it applies to. 023's `obligations` table holds
# INSTANTIATED obligations: what one named client owes for one named asset under
# one paid entitlement. They are not the same object, and the difference is not
# cosmetic — four of 023's NOT NULL columns have no possible value here:
#
#   organization_id  — a template belongs to no tenant.
#   entitlement_id   — THE GOVERNING RULE (§4.5) is that an obligation may only
#                      exist for an entitled module, enforced as a composite NOT
#                      NULL foreign key. A template obligation has no buyer.
#   status           — 023 gives it no default on purpose: 'compliant' would make
#                      every row assert a clean record before any evidence exists.
#                      A template has no compliance state at all.
#   label            — NOT NULL; the extraction has `applies_to`, which is a
#                      description of who the requirement binds, not a label.
#
# Forcing them in would mean inventing a tenant, an entitlement and a compliance
# status — three fabrications, one of which is a billing record. The honest
# reading is that 023 is right and the model is simply missing a layer: a
# `guideline_obligation_templates` table (standard_id, obligation_type, cadence,
# trigger_event, applies_to, source provenance) from which real obligations are
# INSTANTIATED at onboarding, when an organisation, an entitlement and an asset
# finally exist. That is a migration 024, not something this loader may improvise.
#
# Two further mismatches would bite even once that table exists, and are reported
# so they are fixed in the template table's design rather than discovered later:
#
#   * FRACTIONAL CADENCE. GU44 carries cadence_days 0.333 (three times daily) and
#     0.0104 (roughly every fifteen minutes, during emergency disinfection).
#     023's cadence_days is INTEGER with a > 0 CHECK. Rounding 0.333 up to 1 day
#     turns three checks a day into one and would report a client compliant while
#     they miss two thirds of the required monitoring. A sub-daily cadence needs
#     its own representation (minutes, or a separate intraday concept).
#   * EVENT TRIGGERS ARE IN THE WRONG FIELD. 023 requires exactly one of a cadence
#     or a `trigger_event`, specifically so that a triggered obligation is not
#     indistinguishable from an unfilled field. The *_limits.json extractions have
#     no trigger_event key at all — GU44's post-disinfection sample carries its
#     trigger in prose inside `cadence_note`. That prose must be promoted to a
#     real trigger_event by a human reading it; parsing English out of a note to
#     satisfy a CHECK constraint is exactly the guessing this file refuses.
#     (The *_certificates.json files DO carry trigger_event properly.)

def describe_obligations(mod_key: str, doc: dict, report: Report) -> int:
    """Record the template obligations as a worklist. Writes nothing. Returns count."""
    obligations = doc.get("obligations") or []
    examinations = doc.get("examinations") or []
    total = len(obligations) + len(examinations)
    if not total:
        return 0

    if obligations:
        report.unloadable_obligations.append((
            mod_key, len(obligations),
            "template obligations — no organization_id, entitlement_id, status or "
            "label exists for them (see the comment in db/load_guidelines.py). "
            "They need a guideline_obligation_templates table, not 023.obligations."
        ))
    if examinations:
        report.unloadable_obligations.append((
            mod_key, len(examinations),
            "examination requirements — same reason. They additionally describe "
            "certificate_validity_months, which 023 records on the certificate "
            "(valid_until), not on the obligation, so the template table needs it."
        ))

    for i, obl in enumerate(obligations):
        otype = obl.get("obligation_type")
        if otype not in OBLIGATION_TYPES:
            report.shape_conflicts.append((
                f"{mod_key}.obligations[{i}]",
                f"obligation_type {otype!r} is not one 025 permits "
                f"({sorted(OBLIGATION_TYPES)})"))
        days = obl.get("cadence_days")
        if isinstance(days, float) and days != int(days):
            report.shape_conflicts.append((
                f"{mod_key}.obligations[{i}]",
                f"cadence_days {days} is fractional; 023's column is INTEGER > 0. "
                "Rounding it would under-report a sub-daily obligation."))
        if (obl.get("cadence_months") is None and days is None
                and not obl.get("trigger_event")):
            report.shape_conflicts.append((
                f"{mod_key}.obligations[{i}]",
                "no cadence and no trigger_event — 023's obligations_cadence_check "
                "requires exactly one. Any trigger is in cadence_note as prose and "
                "must be promoted by a human, not parsed."))
    return total


# ── catalogue ────────────────────────────────────────────────────────────────

def catalogue_index(entries: list[dict], report: Report) -> dict[str, dict]:
    """Index the catalogue by code, refusing every row as a standards row.

    Rule 3 in its most concrete form. Not one of the 81 entries carries an issue
    date, because the DM portal publishes none — `portal_document_date` is a CMS
    record date and is deliberately never read here. So the catalogue contributes
    NO standards rows at all. What it can do is name a document and say what kind
    of evidence it demands, which is enough to enrich a module whose standard came
    from an extraction file.
    """
    by_code: dict[str, dict] = {}
    no_code = 0
    if not entries:
        return by_code
    for entry in entries:
        code = entry.get("code")
        if not code:
            no_code += 1
            continue
        if code in by_code:
            report.catalogue_refusals.append(
                (code, "appears twice in the catalogue — not indexed"))
            continue
        by_code[code] = entry

    report.catalogue_refusals.append((
        f"{len(entries)} catalogue rows",
        "none can become a standards row: not one carries an issue date, and "
        "022 makes standards.issued_on NOT NULL. portal_document_date is a CMS "
        "record date (GU44's page reads 27/07/2026 for a 2025-08-19 edition) and "
        "must never be loaded into it (§7.11). Each needs its PDF read."))
    if no_code:
        report.catalogue_refusals.append((
            f"{no_code} catalogue rows",
            "no code recorded. Not derived from the guideline number — codes are "
            "not uniform (GU146 is DM-HSD-146-FL2, no GU prefix) and a wrong code "
            "silently breaks citation matching (rule 4)."))
    return by_code


# ── Entry point ──────────────────────────────────────────────────────────────

def load(directory: str = DATA_DIR, apply: bool = False,
         apply_updates: bool = False, worklist_only: bool = False,
         client: Any = None) -> Report:
    """Load the corpus. Writes nothing unless apply=True."""
    check_module_kinds()
    dry_run = not apply
    report = Report()

    if client is None:
        if not is_configured():
            raise LoadError(
                "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY to "
                "the service role key — 022 and 023 restrict writes on every table "
                "here to super_admin, which cannot be satisfied without a user JWT."
            )
        client = get_client()
        if client is None:
            raise LoadError("could not create a Supabase client.")

    # Before anything is written, and before the dry run too: a dry run against
    # the wrong database still tells you a comforting story about a database you
    # must not touch, and the operator would act on it.
    try:
        assert_deployment(client)
    except WrongDatabase as exc:
        raise LoadError(str(exc)) from exc

    catalogue_path = os.path.join(directory, "catalogue.json")
    catalogue = read_json(catalogue_path) if os.path.exists(catalogue_path) else []
    by_code = catalogue_index(catalogue, report)

    seen_set_keys: dict[str, str] = {}

    for path in extraction_paths(directory):
        mod_key = module_key_for(path)
        doc = read_json(path)
        print(f"\n{os.path.basename(path)}:")

        row, blocking = standard_row(doc)
        if row is None:
            for reason in blocking:
                report.blocked_standards.append((mod_key, reason.strip()))
            print(f"  REFUSED — {len(blocking)} blocking finding(s) on the standard")
            describe_obligations(mod_key, doc, report)
            continue

        std_id = upsert_standard(client, row, dry_run, apply_updates, report)

        # A known non-live lifecycle is reported whether or not 024 has been
        # applied. When the column exists the value is written; when it does not,
        # the finding must still surface — a document silently loading as though
        # it were in force is exactly what §7.13 exists to prevent.
        if mod_key in LIFECYCLES:
            lc = LIFECYCLES[mod_key]
            recorded = lifecycle_column_present(client)
            report.shape_conflicts.append((mod_key, (
                f"lifecycle_status = '{lc.status}' — {lc.evidence} "
                + ("Recorded on the standard."
                   if recorded else
                   "NOT RECORDED: standards.lifecycle_status does not exist in "
                   "this database, so nothing distinguishes this document from a "
                   "live one. Apply migration 024 and re-run.")
            )))

        # A catalogue entry disagreeing about the guideline number is the GU10 /
        # GU101 case (§7.11). Reported, never reconciled: one of the two is a DM
        # typo and only DM can say which.
        cat = by_code.get(row["code"])
        if cat and cat.get("guideline_no") is not None \
                and row["guideline_no"] is not None \
                and cat["guideline_no"] != row["guideline_no"]:
            report.shape_conflicts.append((
                row["code"],
                f"catalogue calls this guideline {cat['guideline_no']}, the "
                f"document code says {row['guideline_no']}. Both recorded as "
                "printed; resolve with DM before the module ships (§7.11)."))

        # specification sets
        for spec_set in doc.get("specification_sets") or []:
            key = spec_set.get("key")
            if not key or not spec_set.get("label"):
                report.skipped_sets.append(
                    (f"{mod_key}/{key}", "key and label are NOT NULL in 022"))
                continue
            if spec_set.get("applies_to_scope") not in SCOPES_PERMITTED:
                report.skipped_sets.append((
                    key, f"applies_to_scope {spec_set.get('applies_to_scope')!r} is "
                         "not one 022 permits — widen the CHECK or fix the value"))
                continue
            if key in seen_set_keys:
                report.skipped_sets.append((
                    key, f"key already used by {seen_set_keys[key]} — built-in set "
                         "keys are globally unique (specification_sets_builtin_key_idx)"))
                continue
            seen_set_keys[key] = mod_key

            limits, blocked = limit_rows(spec_set, key, report)
            if not limits:
                report.skipped_sets.append((
                    key, f"0 of {blocked} limits are loadable — a set with no limits "
                         "judges nothing and would read as a silent pass"))
                continue

            upsert_set(client, set_row(spec_set, std_id, len(limits), blocked),
                       limits, dry_run, apply_updates, report)

        # module
        kind = resolve_module_kind(mod_key, doc)
        if kind is None:
            report.no_module_kind.append((
                mod_key,
                "no module_kind in the extraction and none stated in MODULE_KINDS. "
                "023 has no default: 'compliance' would manufacture authority the "
                "document may not have (§7.12). Read the document and state it."))
        else:
            cat_type = (cat or {}).get("evidence_type")
            upsert_module(
                client,
                module_row(mod_key, std_id, doc.get("standard") or {}, kind,
                           None if cat_type == "unknown" else cat_type),
                dry_run, apply_updates, report)

        describe_obligations(mod_key, doc, report)

    report.print(worklist_only=worklist_only)
    print("\ndry run — nothing written. Re-run with --apply."
          if dry_run else "\nload complete.")
    return report


def main(argv: Optional[list[str]] = None) -> int:
    use_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="actually write. WITHOUT THIS THE RUN IS A DRY RUN — "
                             "the opposite default to db/seed_standards.py, "
                             "deliberately.")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicit no-op; this is already the default.")
    parser.add_argument("--apply-updates", action="store_true",
                        help="overwrite rows that differ. Without it, drift is "
                             "reported and left alone. Never touches a "
                             "human-owned column.")
    parser.add_argument("--worklist", action="store_true",
                        help="print only what could not be loaded, and why.")
    parser.add_argument("--dir", default=DATA_DIR)
    args = parser.parse_args(argv)

    if args.dry_run and args.apply:
        parser.error("--dry-run and --apply are contradictory.")
    if args.apply_updates and not args.apply:
        parser.error("--apply-updates writes, so it requires --apply.")

    try:
        load(directory=args.dir, apply=args.apply,
             apply_updates=args.apply_updates, worklist_only=args.worklist)
        return 0
    except LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:                            # noqa: BLE001
        # Anything else is a PostgREST/network failure part-way through a run with
        # no transaction around it. Say so plainly: the operator needs to know the
        # database may be half-loaded and that re-running fixes it.
        print(f"error: {type(exc).__name__}: {exc}\n"
              "The load may have stopped part-way. There is no transaction across "
              "PostgREST calls, so re-run it — every write matches on a natural "
              "key first and repeating is safe.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
