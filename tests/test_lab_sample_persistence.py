"""Guards the persistence layer against *silent* drift between three things that
have to agree: the LabSample schema, migration 016's column list, and the
hardcoded allowlist in db.queries.save_lab_sample.

save_lab_sample filters the payload rather than splatting it, because a parsed
LabSample carries more than the table stores (verbatim raw text, gate findings)
and an unexpected key would fail the whole insert. The cost of that safety is
that a *missing* key is invisible: add a field to LabSample, or a column to the
migration, forget the allowlist, and the value is dropped on save with no error,
no log line and no failing test. For forensic lab data that is the worst failure
mode available — the record looks complete and is not.

These tests are deliberately pure: they read the .sql file as text and exercise
the module. Nothing here touches Supabase or the network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from db import queries
from db.queries import _LAB_RESULT_COLUMNS, _LAB_SAMPLE_COLUMNS, save_lab_sample
from ingestion.router import ingest

MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"
MIGRATION = MIGRATIONS_DIR / "016_lab_samples.sql"
# 018 adds the governing-standard columns by ALTER, so the column set is the
# union of both files — reading 016 alone would understate the real schema.
MIGRATION_018 = MIGRATIONS_DIR / "018_lab_samples_standard.sql"
FIXTURE = Path(__file__).parent / "fixtures" / "wimpey" / "WD-R-260421-0222_microbiology.pdf"

# Columns the database fills in itself — never sent by the writer.
_DB_MANAGED = {"id", "organization_id", "created_at"}

# LabSample fields that legitimately have no column in 016, each for a reason.
# Anything NOT on this list and NOT in the migration is drift, and the test below
# will say so. Keep the comments: they are the record of the decision.
_INTENTIONAL_EXCLUSIONS = {
    # Persisted to the child table lab_results, one row per parameter.
    "results",
    # NOTE: overall_status was originally excluded on the grounds that a stored
    # roll-up could drift from editable result rows. Migration 018 gives it a
    # column anyway, so certificates can be queried by verdict without joining
    # every parameter. It is written once at approval; if result rows ever become
    # editable after that, this roll-up has to be recomputed with them.
}

# The governing standard and the legionella method disclosure. 016 predated the
# compliance work and had no columns for these, so they parsed correctly and were
# then silently discarded on save, surviving only inside raw_extraction's text
# blob — evidence, but not queryable. Migration 018 added the columns; this set
# now asserts they stay persisted. A result is only meaningful next to the limit
# it was judged against, so losing these again would reduce a verdict to a number.
_STANDARD_FIELDS_PERSISTED = {
    "standard_code", "standard_title", "standard_year", "standard_authority",
    "standard_citation", "additional_standards",
    "test_procedure", "medium_used", "detection_limit", "filtered_volume",
}


def _columns(table: str) -> set[str]:
    """Column names declared for `table` in migration 016.

    Parsed from the file rather than hardcoded so the migration stays the single
    source of truth; a hardcoded copy here would drift in exactly the way this
    module exists to catch.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    block = re.search(
        rf"CREATE TABLE IF NOT EXISTS public\.{table}\s*\((.*?)\n\);",
        sql, re.S,
    )
    assert block, f"could not find the CREATE TABLE block for {table}"
    extra: set[str] = set()
    if table == "lab_samples" and MIGRATION_018.exists():
        alter = MIGRATION_018.read_text(encoding="utf-8")
        extra = set(re.findall(r"ADD COLUMN IF NOT EXISTS\s+([a-z_][a-z0-9_]*)", alter))
    cols: set[str] = set()
    depth = 0
    for line in block.group(1).splitlines():
        stripped = line.strip()
        # Skip continuation lines of a multi-line constraint (CHECK (...)).
        if depth == 0:
            m = re.match(r"^([a-z_][a-z0-9_]*)\s+[A-Z]", stripped)
            if m and m.group(1) not in {"unique", "primary", "foreign", "constraint", "check"}:
                cols.add(m.group(1))
        depth += stripped.count("(") - stripped.count(")")
    return cols | extra


def test_migration_parse_finds_the_expected_shape():
    """A regex over SQL is only trustworthy if it is itself checked — a silently
    empty parse would make every assertion below vacuously true."""
    samples, results = _columns("lab_samples"), _columns("lab_results")
    assert {"report_no", "raw_extraction", "reviewer_status"} <= samples
    assert {"value_raw", "value_num", "qualifier"} <= results
    assert len(samples) > 25 and len(results) > 5


def test_sample_allowlist_only_names_real_columns():
    """An allowlist entry with no column would let a key through to PostgREST and
    fail the whole insert — the loud failure, but only in production."""
    assert _LAB_SAMPLE_COLUMNS <= _columns("lab_samples")


def test_result_allowlist_only_names_real_columns():
    assert _LAB_RESULT_COLUMNS <= _columns("lab_results")


def test_allowlist_covers_every_column_the_table_has():
    """The other direction: a column added by a later migration that the writer
    never populates. Not an error, but it must be a decision, not an oversight."""
    missing = _columns("lab_samples") - _DB_MANAGED - _LAB_SAMPLE_COLUMNS
    assert missing == set(), f"lab_samples columns never written: {sorted(missing)}"
    missing = _columns("lab_results") - {"id", "sample_id"} - _LAB_RESULT_COLUMNS
    assert missing == set(), f"lab_results columns never written: {sorted(missing)}"


@pytest.fixture(scope="module")
def parsed_sample():
    """A real parsed certificate — the payload save_lab_sample actually receives."""
    return ingest(FIXTURE.read_bytes(), "application/pdf", FIXTURE.name)


def test_no_persistable_field_is_silently_dropped(parsed_sample):
    """Every LabSample field that 016 HAS a column for must be in the allowlist.

    This is the core drift guard. A field that the table can hold but the
    allowlist omits is data loss with no error anywhere.
    """
    payload = parsed_sample.model_dump(mode="json")
    storable = set(payload) & _columns("lab_samples")
    dropped = storable - _LAB_SAMPLE_COLUMNS
    assert dropped == set(), (
        f"fields with a column but no allowlist entry — silently dropped: {sorted(dropped)}"
    )


def test_every_unpersisted_field_is_accounted_for(parsed_sample):
    """Nothing may fall off the schema unnoticed.

    A LabSample field with no column is either an intentional exclusion or a
    documented defect. A *new* one — someone adds a field and no migration —
    fails here rather than vanishing into raw_extraction.
    """
    payload = parsed_sample.model_dump(mode="json")
    unpersisted = set(payload) - _columns("lab_samples")
    unexplained = unpersisted - _INTENTIONAL_EXCLUSIONS - _STANDARD_FIELDS_PERSISTED
    assert unexplained == set(), (
        "LabSample fields with no column in 016 and no recorded reason — they are "
        f"discarded on save: {sorted(unexplained)}. Either add a column and an "
        "allowlist entry, or add them to _INTENTIONAL_EXCLUSIONS with a comment."
    )


def test_the_governing_standard_is_persisted(parsed_sample):
    """The limit a result was judged against must reach a queryable column.

    This began life documenting a defect: migration 016 predated the compliance
    work, so the parser captured DM-HSD-GU44-LCWS2 and save_lab_sample silently
    dropped it. Migration 018 added the columns. The assertion is now inverted —
    if these ever leave the allowlist again, the citation degrades to a JSON blob
    that is evidence but not reportable, and nothing could answer "which standard
    was this judged against?".
    """
    payload = parsed_sample.model_dump(mode="json")
    assert payload["standard_code"] == "DM-HSD-GU44-LCWS2"
    for field in _STANDARD_FIELDS_PERSISTED:
        assert field in _LAB_SAMPLE_COLUMNS, f"{field} would be discarded on save"
    assert _filtered(payload)["standard_code"] == "DM-HSD-GU44-LCWS2"
    # Still kept verbatim in the immutable audit blob as well (gate 7).
    assert "DM-HSD-GU44-LCWS2" in str(payload["raw_extraction"])


def _filtered(sample: dict) -> dict:
    """The row save_lab_sample would build, minus the client call."""
    return {k: v for k, v in sample.items() if k in _LAB_SAMPLE_COLUMNS}


def _filtered_result(result: dict) -> dict:
    return {k: v for k, v in result.items() if k in _LAB_RESULT_COLUMNS}


def test_verbatim_values_survive_the_filter(parsed_sample):
    """'<1' must reach the database as '<1' and a non-detect must arrive with a
    NULL magnitude. Filtering is the last step before insert, so if it rounded,
    stringified or defaulted anything, the row would assert something the
    laboratory never said."""
    payload = parsed_sample.model_dump(mode="json")
    rows = [_filtered_result(r) for r in payload["results"]]
    assert rows, "fixture produced no result rows"

    below_loq = [r for r in rows if r["value_raw"].startswith("<")]
    assert below_loq, "expected at least one '<' result on this microbiology report"
    for row in below_loq:
        assert row["qualifier"] == "<"
        assert row["value_raw"].startswith("<"), "the '<' was stripped in transit"

    for row in rows:
        if row["qualifier"] == "ND":
            assert row["value_num"] is None, \
                f"{row['parameter']}: a magnitude was invented for a non-detect"
        # Nothing may arrive with an empty verbatim value: lab_results.value_raw
        # is NOT NULL, and an empty string would be a record of nothing.
        assert row["value_raw"].strip()


def test_status_reason_is_not_persisted(parsed_sample):
    """LabResult.status_reason has no column; it is reviewer-facing prose derived
    from status. Asserted explicitly so adding a column is a conscious act."""
    payload = parsed_sample.model_dump(mode="json")
    assert "status_reason" not in _LAB_RESULT_COLUMNS
    assert any(r.get("status_reason") for r in payload["results"])


def test_sample_row_carries_the_provenance_the_table_requires(parsed_sample):
    """raw_extraction is NOT NULL and report_no drives the uniqueness constraint;
    a filtered row missing either would fail at insert time, in production."""
    row = _filtered(parsed_sample.model_dump(mode="json"))
    assert row["report_no"].strip()
    assert row["raw_extraction"]
    assert len(row["source_sha256"]) == 64


def test_save_returns_none_when_supabase_is_unconfigured(monkeypatch):
    """Local and CI runs have no Supabase. Ingestion must degrade to "not saved"
    rather than raising, so an unconfigured environment does not look like a
    parser failure to the user uploading the PDF."""
    monkeypatch.setattr(queries, "get_client", lambda: None)
    assert save_lab_sample("org-1", {"report_no": "X-1"}, []) is None


def test_save_returns_none_without_an_organization(monkeypatch):
    """Org scoping is not optional: an unscoped row would be invisible to RLS and
    effectively orphaned."""
    monkeypatch.setattr(queries, "get_client", lambda: object())
    assert save_lab_sample("", {"report_no": "X-1"}, []) is None
