"""Validates extracted guideline JSON against migration 022's constraints.

The extraction files in data/dm_guidelines/ are candidate content, produced by
reading published DM PDFs. They are not verified (§7.1) and they are not yet
seedable. This script answers one question per file: *if this were loaded into
the tables 022 creates, what would the database reject?*

Running it before a human starts verifying is worth doing, because it separates
two very different kinds of problem:

  * BLOCKING  — the row violates a CHECK or a NOT NULL and cannot be seeded at
                all. Someone must go back to the document.
  * ADVISORY  — the row would load, but something about it is suspect.

A null `min_inclusive`/`max_inclusive` is deliberately BLOCKING. The extraction
brief told the agents to write null where the document's notation is genuinely
ambiguous rather than guess, and 022 made those columns NOT NULL with no default
for exactly the same reason. So an ambiguous bound stops at the gate instead of
becoming a confident wrong verdict — which is the whole design, working. The
count of blocked limits is therefore a worklist, not a failure.

    python -m scripts.validate_extractions
    python -m scripts.validate_extractions --file data/dm_guidelines/gu44_limits.json
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys

QUALIFIER_RULES = {"bound", "detect_fails", "unassessable"}
SCOPES = {"lagoon", "facilities", None}
LANGUAGES = {"en", "ar", "both"}


class Finding:
    def __init__(self, level: str, where: str, message: str):
        self.level = level
        self.where = where
        self.message = message

    def __str__(self) -> str:
        return f"  [{self.level}] {self.where}: {self.message}"


def check_standard(std: dict) -> list[Finding]:
    out = []
    # NOT NULL in 022. issued_on is the one most likely to be missing, because
    # the DM portal publishes no issue date (§7.11) — it must come from the PDF.
    for col in ("code", "title", "version", "issued_on"):
        if not std.get(col):
            out.append(Finding("BLOCKING", f"standard.{col}",
                               "NOT NULL in 022, and absent here"))
    if std.get("language") not in LANGUAGES:
        out.append(Finding("BLOCKING", "standard.language",
                           f"{std.get('language')!r} not in {sorted(LANGUAGES)}"))
    if not std.get("source_url"):
        out.append(Finding("ADVISORY", "standard.source_url",
                           "no source URL — verification cannot be repeated"))
    return out


def check_limit(lim: dict, where: str) -> list[Finding]:
    out = []
    mn, mx = lim.get("min_val"), lim.get("max_val")

    # spec_limits_bounded_check: a limit bounded on neither side judges nothing
    # and would silently PASS every value put to it.
    if mn is None and mx is None:
        out.append(Finding("BLOCKING", where,
                           "bounded on neither side — spec_limits_bounded_check "
                           "rejects this; it would pass every value"))

    # spec_limits_range_check
    if mn is not None and mx is not None and mn > mx:
        out.append(Finding("BLOCKING", where, f"min_val {mn} > max_val {mx}"))

    # NOT NULL, no default — an ambiguous operator must not be guessed.
    if mn is not None and lim.get("min_inclusive") is None:
        out.append(Finding("BLOCKING", where,
                           "has a lower bound but min_inclusive is null — the "
                           "document's notation was ambiguous; a human must read it"))
    if mx is not None and lim.get("max_inclusive") is None:
        out.append(Finding("BLOCKING", where,
                           "has an upper bound but max_inclusive is null — the "
                           "document's notation was ambiguous; a human must read it"))

    for col in ("parameter_key", "parameter_label", "display"):
        if not lim.get(col):
            out.append(Finding("BLOCKING", where, f"{col} is NOT NULL in 022 and absent"))

    if lim.get("qualifier_rule") not in QUALIFIER_RULES:
        out.append(Finding("BLOCKING", where,
                           f"qualifier_rule {lim.get('qualifier_rule')!r} not in "
                           f"{sorted(QUALIFIER_RULES)}"))

    # Provenance. Not a database constraint, but §7.1 makes it a release gate:
    # an uncitable limit cannot be verified, and an unverified limit cannot be sold.
    if lim.get("source_page") in (None, ""):
        out.append(Finding("ADVISORY", where, "no source_page — cannot be verified cheaply"))
    if not lim.get("source_quote"):
        out.append(Finding("ADVISORY", where, "no source_quote"))
    if lim.get("confidence") == "low":
        out.append(Finding("ADVISORY", where, "confidence low — verify before use"))

    # A limit marked unassessable never yields a verdict, so bounds on it are
    # decorative and usually mean it is descriptive text rather than a limit.
    if lim.get("qualifier_rule") == "unassessable" and (mn is not None or mx is not None):
        out.append(Finding("ADVISORY", where,
                           "qualifier_rule 'unassessable' but carries bounds — is "
                           "this a limit, or descriptive text about the parameter?"))
    return out


def check_file(path: str) -> list[Finding]:
    with io.open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    out = check_standard(doc.get("standard", {}) or {})

    units: dict[str, set[str]] = {}
    for st in doc.get("specification_sets", []) or []:
        skey = st.get("key") or "<no key>"
        if not st.get("key") or not st.get("label"):
            out.append(Finding("BLOCKING", skey, "key and label are NOT NULL in 022"))
        if st.get("applies_to_scope") not in SCOPES:
            out.append(Finding("BLOCKING", skey,
                               f"applies_to_scope {st.get('applies_to_scope')!r} is not "
                               "one 022 permits — widen the CHECK, or fix the value"))

        seen: set[str] = set()
        for lim in st.get("limits", []) or []:
            pkey = lim.get("parameter_key") or "<no key>"
            where = f"{skey}.{pkey}"
            # UNIQUE (spec_set_id, parameter_key)
            if pkey in seen:
                out.append(Finding("BLOCKING", where,
                                   "duplicate parameter_key within the set — violates "
                                   "UNIQUE (spec_set_id, parameter_key)"))
            seen.add(pkey)
            out += check_limit(lim, where)
            if lim.get("unit"):
                units.setdefault(pkey, set()).add(str(lim["unit"]))

    # Same parameter, different unit spellings across sets. Not a constraint, but
    # a resolver matching a lab result to a limit by parameter_key will compare
    # against whichever it finds, and 'MG/L' vs 'mg/l' is a silent mismatch.
    for pkey, spellings in units.items():
        if len({s.lower() for s in spellings}) > 1:
            out.append(Finding("ADVISORY", pkey,
                               f"inconsistent units across sets: {sorted(spellings)}"))

    for i, obl in enumerate(doc.get("obligations", []) or []):
        if (obl.get("cadence_months") is None and obl.get("cadence_days") is None
                and not obl.get("cadence_note")):
            out.append(Finding("ADVISORY", f"obligations[{i}]",
                               "no cadence and no cadence_note — cannot drive the "
                               "due/overdue engine, and does not say why"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", help="validate one file instead of the whole directory")
    ap.add_argument("--blocking-only", action="store_true")
    args = ap.parse_args(argv)

    paths = [args.file] if args.file else sorted(
        glob.glob(os.path.join("data", "dm_guidelines", "*_limits.json")))
    if not paths:
        print("no extraction files found under data/dm_guidelines/", file=sys.stderr)
        return 1

    total_block = total_adv = 0
    for path in paths:
        try:
            findings = check_file(path)
        except Exception as exc:                       # noqa: BLE001
            print(f"{os.path.basename(path)}: UNREADABLE — {type(exc).__name__}: {exc}")
            total_block += 1
            continue

        block = [f for f in findings if f.level == "BLOCKING"]
        adv = [f for f in findings if f.level == "ADVISORY"]
        total_block += len(block)
        total_adv += len(adv)

        print(f"\n{os.path.basename(path)} — {len(block)} blocking, {len(adv)} advisory")
        for f in block:
            print(f)
        if not args.blocking_only:
            for f in adv:
                print(f)

    print(f"\n{'='*60}\nTOTAL: {total_block} blocking, {total_adv} advisory")
    if total_block:
        print("Blocking findings are mostly ambiguous bounds, which is the design "
              "working: 022 refuses to store a guessed operator. Each one is a "
              "page for a human to read, not a bug to code around.")
    # Exit 0 either way: this is a worklist, not a build gate. Nothing is seeded
    # from these files yet, and a nonzero exit would imply the extraction failed.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
