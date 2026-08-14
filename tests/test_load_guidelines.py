"""The guideline loader must be incapable of selling unverified content.

Fakes only, in the style of tests/test_guard.py — no database, and no network.
Four properties are load-bearing and each is asserted from more than one angle,
because each one is a way for the product to make a false statement to a
regulator rather than merely a way for a script to be wrong:

  * nothing this loader writes can be on sale (§7.1, 023's
    guideline_modules_verified_to_sell_check);
  * a limit whose strictness the document did not state is SKIPPED, never
    defaulted (022 removed the DEFAULT from min_inclusive for this reason);
  * a standard with no issue date from inside the PDF is refused, never given
    the portal's CMS record date (§7.11);
  * the database guard is consulted before anything happens, dry run included.
"""
from __future__ import annotations

import io
import json
import os

import pytest

import db.load_guidelines as loader
from db.load_guidelines import (
    COMING_SOON, UNVERIFIED, LoadError, ModuleKind, catalogue_index,
    describe_obligations, drifted_columns, guideline_no_from_code, limit_rows,
    module_key_for, module_row, refuse_to_sell, resolve_module_kind, standard_row,
    Report,
)


# ── Fakes ────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    """One PostgREST query against one fake table."""

    def __init__(self, table: "FakeTable", op: str, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters: list[tuple[str, object]] = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def is_(self, col, _val):
        self.filters.append((col, None))
        return self

    def _matches(self, row) -> bool:
        return all(row.get(col) == val for col, val in self.filters)

    def execute(self):
        if self.op == "select":
            return FakeResponse([r for r in self.table.rows if self._matches(r)])
        if self.op == "insert":
            row = dict(self.payload)
            row.setdefault("id", f"{self.table.name}-{len(self.table.rows) + 1}")
            self.table.rows.append(row)
            self.table.inserted.append(row)
            return FakeResponse([row] if not self.table.silent else [])
        if self.op == "update":
            hit = [r for r in self.table.rows if self._matches(r)]
            for row in hit:
                row.update(self.payload)
            self.table.updated += hit
            return FakeResponse(hit if not self.table.silent else [])
        raise AssertionError(self.op)


class FakeTable:
    def __init__(self, name, rows=None, silent=False):
        self.name = name
        self.rows = list(rows or [])
        self.inserted: list[dict] = []
        self.updated: list[dict] = []
        # silent=True reproduces the dangerous case: an authenticated
        # non-super_admin whose write is rejected by RLS and reported as success
        # with an empty body.
        self.silent = silent

    def select(self, *_a, **_k):
        return FakeQuery(self, "select")

    def insert(self, row):
        return FakeQuery(self, "insert", row)

    def update(self, row):
        return FakeQuery(self, "update", row)


class FakeClient:
    def __init__(self, deployment="dm-tech-apps", silent=False, seed=None):
        self.tables: dict[str, FakeTable] = {}
        if deployment is not None:
            self.tables["deployment_identity"] = FakeTable(
                "deployment_identity", [{"deployment": deployment}])
        for name, rows in (seed or {}).items():
            self.tables[name] = FakeTable(name, rows, silent=silent)
        self._silent = silent

    def table(self, name):
        if name not in self.tables:
            self.tables[name] = FakeTable(name, silent=self._silent)
        return self.tables[name]

    def inserted(self, name):
        return self.tables[name].inserted if name in self.tables else []


# ── Fixture corpus ───────────────────────────────────────────────────────────

GOOD_LIMIT = {
    "parameter_key": "legionella",
    "parameter_label": "Legionella",
    "unit": "cfu/l",
    "min_val": None,
    "max_val": 1000,
    "min_inclusive": None,
    "max_inclusive": True,
    "display": "Not exceed 1000 cfu/l",
    "qualifier_rule": "bound",
    "source_page": 24,
    "source_quote": "Table (3) row 1",
    "confidence": "high",
}

AMBIGUOUS_LIMIT = {
    "parameter_key": "aerobic_bacterial_count",
    "parameter_label": "Aerobic bacterial count",
    "unit": "cfu/ml",
    "min_val": None,
    "max_val": 10000,
    "min_inclusive": None,
    "max_inclusive": None,          # the document's notation was ambiguous
    "display": "10,000 cfu/ml",
    "qualifier_rule": "bound",
    "source_page": 24,
    "source_quote": "Table (3) row 2",
    "confidence": "medium",
}


def write_doc(directory, name, doc):
    path = os.path.join(str(directory), name)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path


def make_doc(**overrides):
    doc = {
        "standard": {
            "code": "DM-HSD-GU44-LCWS2",
            "title": "Technical Guidelines for Legionella Control in Water System",
            "version": "V.6",
            "issued_on": "2025-08-19",
            "source_url": "https://example.invalid/gu44.pdf",
            "language": "en",
        },
        "specification_sets": [{
            "key": "gu44_cooling_water_system",
            "label": "GU44 — Cooling water system",
            "applies_to_scope": "facilities",
            "limits": [dict(GOOD_LIMIT), dict(AMBIGUOUS_LIMIT)],
        }],
        "obligations": [],
    }
    doc.update(overrides)
    return doc


@pytest.fixture()
def corpus(tmp_path):
    write_doc(tmp_path, "gu44_limits.json", make_doc())
    return tmp_path


# ── 1. Nothing unverified may be sold ────────────────────────────────────────

def test_a_loaded_module_is_never_on_sale(tmp_path):
    """The whole point. status/provenance are literals, not parameters."""
    write_doc(tmp_path, "gu48_certificates.json", make_doc(
        module_kind="compliance", specification_sets=[], obligations=[]))
    client = FakeClient()

    loader.load(directory=str(tmp_path), apply=True, client=client)

    modules = client.inserted("guideline_modules")
    assert len(modules) == 1
    assert modules[0]["status"] == COMING_SOON
    assert modules[0]["provenance"] == UNVERIFIED


def test_module_row_ignores_any_status_the_extraction_claims():
    """An extraction file cannot talk its way onto the price list."""
    std = {"title": "Anything", "status": "available", "provenance": "verified"}
    row = module_row("gu48", "std-1", std, ModuleKind("compliance", "§7.12"), None)
    assert row["status"] == COMING_SOON
    assert row["provenance"] == UNVERIFIED


def test_refuse_to_sell_raises_rather_than_quietly_correcting():
    """A row arriving marked available means a code path exists that must not."""
    with pytest.raises(LoadError, match="refusing to write module"):
        refuse_to_sell({"key": "gu44", "status": "available", "provenance": "verified"})
    with pytest.raises(LoadError):
        refuse_to_sell({"key": "gu44", "status": COMING_SOON, "provenance": "verified"})


def test_reloading_never_demotes_a_module_a_human_verified():
    """provenance and status are human-owned: verification must survive a re-run."""
    assert {"provenance", "status"} <= loader.HUMAN_OWNED["guideline_modules"]
    current = {"key": "gu48", "status": "available", "provenance": "verified",
               "label": "Lifting equipment"}
    desired = {"key": "gu48", "status": COMING_SOON, "provenance": UNVERIFIED,
               "label": "Lifting equipment"}
    assert drifted_columns("guideline_modules", current, desired) == []


def test_no_module_is_created_when_the_kind_is_unknown(tmp_path):
    """023 has no default for module_kind, and neither does this loader."""
    write_doc(tmp_path, "gu999_limits.json", make_doc())
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert client.inserted("guideline_modules") == []
    assert [k for k, _ in report.no_module_kind] == ["gu999"]


def test_a_bad_module_kind_in_an_extraction_is_refused(tmp_path):
    write_doc(tmp_path, "gu44_limits.json", make_doc(module_kind="verdict"))
    with pytest.raises(LoadError, match="module_kind"):
        loader.load(directory=str(tmp_path), apply=True, client=FakeClient())


def test_stated_module_kinds_are_ones_023_permits_and_cite_evidence():
    loader.check_module_kinds()
    for key, mk in loader.MODULE_KINDS.items():
        assert mk.kind in loader.MODULE_KINDS_PERMITTED, key
        assert mk.evidence.strip(), key


def test_the_extraction_file_outranks_the_stated_kind():
    doc = {"module_kind": "monitoring"}
    assert resolve_module_kind("gu119", doc).kind == "monitoring"
    assert resolve_module_kind("gu119", {}).kind == "compliance"


# ── 2. A limit that cannot be judged is skipped, never defaulted ─────────────

def test_an_ambiguous_bound_is_skipped_rather_than_defaulted():
    report = Report()
    rows, blocked = limit_rows(
        {"limits": [dict(GOOD_LIMIT), dict(AMBIGUOUS_LIMIT)]}, "gu44_set", report)

    assert [r["parameter_key"] for r in rows] == ["legionella"]
    assert blocked == 1
    assert any("aerobic_bacterial_count" in where for where, _ in report.blocked_limits)


def test_the_skipped_limit_never_reaches_the_database(corpus):
    client = FakeClient()
    loader.load(directory=str(corpus), apply=True, client=client)

    written = {r["parameter_key"] for r in client.inserted("spec_limits")}
    assert written == {"legionella"}
    assert "aerobic_bacterial_count" not in written


def test_an_inert_flag_is_only_used_where_the_bound_is_absent():
    """False on an absent bound is inert; it is not a guess about a real one."""
    report = Report()
    rows, _ = limit_rows({"limits": [dict(GOOD_LIMIT)]}, "s", report)
    row = rows[0]
    assert row["min_val"] is None and row["min_inclusive"] is False
    assert row["max_val"] == 1000 and row["max_inclusive"] is True


def test_a_limit_bounded_on_neither_side_is_blocked():
    """It would silently PASS every value — 022's spec_limits_bounded_check."""
    unbounded = dict(GOOD_LIMIT, min_val=None, max_val=None)
    report = Report()
    rows, blocked = limit_rows({"limits": [unbounded]}, "s", report)
    assert rows == [] and blocked == 1


def test_a_duplicate_parameter_key_is_blocked():
    report = Report()
    rows, blocked = limit_rows(
        {"limits": [dict(GOOD_LIMIT), dict(GOOD_LIMIT)]}, "s", report)
    assert len(rows) == 1 and blocked == 1


def test_a_set_with_no_loadable_limits_is_not_created(tmp_path):
    """An empty set judges nothing and would read as a silent pass."""
    doc = make_doc()
    doc["specification_sets"][0]["limits"] = [dict(AMBIGUOUS_LIMIT)]
    write_doc(tmp_path, "gu44_limits.json", doc)
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert client.inserted("specification_sets") == []
    assert any("0 of" in reason for _, reason in report.skipped_sets)


def test_a_partial_set_says_so_in_its_own_notes(corpus):
    """A set holding some of its limits must be visible in the table, not only here."""
    client = FakeClient()
    loader.load(directory=str(corpus), apply=True, client=client)

    notes = client.inserted("specification_sets")[0]["notes"]
    assert "1 of 2 limits loaded" in notes
    assert "INCOMPLETE" in notes
    assert "UNVERIFIED" in notes


def test_a_scope_the_migration_forbids_skips_the_set(tmp_path):
    doc = make_doc()
    doc["specification_sets"][0]["applies_to_scope"] = "warehouse"
    write_doc(tmp_path, "gu44_limits.json", doc)
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)
    assert client.inserted("specification_sets") == []
    assert any("warehouse" in reason for _, reason in report.skipped_sets)


# ── 3. issued_on is never invented ───────────────────────────────────────────

def test_a_standard_with_no_issue_date_is_refused():
    doc = make_doc()
    doc["standard"].pop("issued_on")
    row, blocking = standard_row(doc)
    assert row is None
    assert any("issued_on" in reason for reason in blocking)


def test_the_portal_record_date_is_never_used_as_an_issue_date():
    """§7.11: GU44's page reads 27/07/2026 for an edition issued 2025-08-19."""
    doc = make_doc()
    doc["standard"].pop("issued_on")
    doc["standard"]["portal_document_date"] = "2026-07-27"
    row, blocking = standard_row(doc)
    assert row is None and blocking


def test_nothing_is_written_for_a_refused_standard(tmp_path):
    """No standard means no set, no limit and no module — the whole document waits."""
    doc = make_doc()
    doc["standard"].pop("issued_on")
    doc["module_kind"] = "compliance"
    write_doc(tmp_path, "gu44_limits.json", doc)
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert client.inserted("standards") == []
    assert client.inserted("specification_sets") == []
    assert client.inserted("spec_limits") == []
    assert client.inserted("guideline_modules") == []
    assert report.blocked_standards


def test_the_catalogue_contributes_no_standards():
    """Not one of its rows carries an issue date, so none can become an edition."""
    report = Report()
    entries = [
        {"guideline_no": 44, "code": "DM-HSD-GU44-LCWS2", "title": "Legionella",
         "version": "V.6", "issued_on": None, "portal_document_date": "2026-07-27",
         "evidence_type": "laboratory"},
        {"guideline_no": 148, "code": None, "title": "Safe Storage",
         "issued_on": None, "portal_document_date": "2026-08-12"},
    ]
    by_code = catalogue_index(entries, report)

    assert set(by_code) == {"DM-HSD-GU44-LCWS2"}
    assert any("issue date" in reason for _, reason in report.catalogue_refusals)
    assert any("no code recorded" in reason for _, reason in report.catalogue_refusals)


def test_a_null_catalogue_code_is_never_derived_from_the_number():
    report = Report()
    by_code = catalogue_index(
        [{"guideline_no": 146, "code": None, "title": "Forklifts"}], report)
    assert by_code == {}


@pytest.mark.parametrize("code,expected", [
    ("DM-HSD-GU44-LCWS2", 44),
    ("dm-hsd-gu119-iaq", 119),
    ("DM-HSD-146-FL2", None),        # GU146 omits the GU prefix — not invented
    ("DM-HSD-GU101-VSC2", 101),      # the GU10/GU101 conflict, recorded as printed
    ("", None),
])
def test_guideline_number_is_parsed_only_where_a_code_states_one(code, expected):
    assert guideline_no_from_code(code) == expected


def test_the_module_key_is_not_a_document_code():
    assert module_key_for("data/dm_guidelines/gu146_certificates.json") == "gu146"
    assert module_key_for("data/dm_guidelines/gu44_limits.json") == "gu44"
    assert module_key_for("data/dm_guidelines/gu83_checklist.json") == "gu83"


# ── 4. The guard is consulted ────────────────────────────────────────────────

def test_the_loader_refuses_the_wrong_database(corpus):
    client = FakeClient(deployment="decca-lagoons")
    with pytest.raises(LoadError, match="decca-lagoons"):
        loader.load(directory=str(corpus), apply=True, client=client)


def test_even_a_dry_run_refuses_the_wrong_database(corpus):
    """A dry run against the lagoon database is still a wrong answer acted upon."""
    client = FakeClient(deployment="decca-lagoons")
    with pytest.raises(LoadError, match="decca-lagoons"):
        loader.load(directory=str(corpus), apply=False, client=client)


def test_an_unbootstrapped_database_is_refused(corpus):
    client = FakeClient(deployment=None)
    with pytest.raises(LoadError, match="no deployment_identity row"):
        loader.load(directory=str(corpus), apply=False, client=client)


def test_the_guard_runs_before_any_write(corpus):
    client = FakeClient(deployment="decca-lagoons")
    with pytest.raises(LoadError):
        loader.load(directory=str(corpus), apply=True, client=client)
    assert client.inserted("standards") == []


# ── Dry run is the default, and writes nothing ───────────────────────────────

def test_a_dry_run_writes_nothing(corpus):
    client = FakeClient()
    loader.load(directory=str(corpus), apply=False, client=client)
    for name in ("standards", "specification_sets", "spec_limits",
                 "guideline_modules", "obligations"):
        assert client.inserted(name) == []


def test_apply_updates_without_apply_is_rejected():
    with pytest.raises(SystemExit):
        loader.main(["--apply-updates"])


def test_dry_run_and_apply_are_contradictory():
    with pytest.raises(SystemExit):
        loader.main(["--dry-run", "--apply"])


# ── Silent RLS rejection ─────────────────────────────────────────────────────

def test_a_write_that_wrote_nothing_is_not_believed(corpus):
    """022/023 restrict writes to super_admin; a rejected write returns empty."""
    client = FakeClient(silent=True, seed={"standards": []})
    with pytest.raises(LoadError, match="INSERT into standards returned no row"):
        loader.load(directory=str(corpus), apply=True, client=client)


def test_an_update_matching_no_rows_is_not_believed(corpus):
    existing = {"id": "s1", "authority": "DM", "code": "DM-HSD-GU44-LCWS2",
                "version": "V.6", "language": "en", "title": "Stale title",
                "issued_on": "2025-08-19", "guideline_no": 44,
                "source_url": "https://example.invalid/gu44.pdf"}
    client = FakeClient(silent=True, seed={"standards": [existing]})
    with pytest.raises(LoadError, match="matched no rows"):
        loader.load(directory=str(corpus), apply=True, apply_updates=True,
                    client=client)


# ── Drift, not overwrite ─────────────────────────────────────────────────────

def test_drift_is_reported_and_not_written_by_default(corpus, capsys):
    existing = {"id": "s1", "authority": "DM", "code": "DM-HSD-GU44-LCWS2",
                "version": "V.6", "language": "en", "title": "A corrected title",
                "issued_on": "2025-08-19", "guideline_no": 44,
                "source_url": "https://example.invalid/gu44.pdf"}
    client = FakeClient(seed={"standards": [existing]})

    loader.load(directory=str(corpus), apply=True, client=client)

    assert client.tables["standards"].updated == []
    assert existing["title"] == "A corrected title"
    assert "DIFFERS in: title" in capsys.readouterr().out


def test_apply_updates_overwrites_drift_but_not_human_owned_columns(corpus):
    existing = {"id": "s1", "authority": "DM", "code": "DM-HSD-GU44-LCWS2",
                "version": "V.6", "language": "en", "title": "A stale title",
                "issued_on": "2025-08-19", "guideline_no": 44,
                "source_url": "https://example.invalid/gu44.pdf",
                "verified_by": "G. Morgan", "verified_on": "2026-08-01"}
    client = FakeClient(seed={"standards": [existing]})

    loader.load(directory=str(corpus), apply=True, apply_updates=True, client=client)

    assert existing["title"].startswith("Technical Guidelines")
    assert existing["verified_by"] == "G. Morgan"      # never reverted
    assert existing["verified_on"] == "2026-08-01"


def test_a_second_edition_is_never_inserted_alongside_the_first(tmp_path):
    """Two rows for one code with supersedes_id NULL = two 'current' editions."""
    write_doc(tmp_path, "gu44_limits.json", make_doc())
    existing = {"id": "s1", "authority": "DM", "code": "DM-HSD-GU44-LCWS2",
                "version": "V.5", "language": "en", "title": "Older edition",
                "issued_on": "2024-12-17"}
    client = FakeClient(seed={"standards": [existing]})

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert client.inserted("standards") == []
    assert any("V.5/en" in reason for _, reason in report.blocked_standards)


# ── Template obligations are reported, never loaded ──────────────────────────

def test_template_obligations_are_not_written_to_the_obligations_table(tmp_path):
    """They go to module_obligations (027), never to obligations (023).

    The distinction is the whole point of 027: a template has no tenant, no
    entitlement and no compliance status to have. Writing one into `obligations`
    would create a duty belonging to nobody that nothing could ever satisfy.
    """
    # module_kind is required: a template hangs off a module, so a guideline
    # whose kind is unresolved creates neither, which is its own tested case.
    doc = make_doc(module_kind="compliance", obligations=[{
        "obligation_type": "sampling", "cadence_months": 3, "cadence_days": None,
        "cadence_note": None, "applies_to": "All water systems",
        "source_quote": "Table (2)",
    }])
    write_doc(tmp_path, "gu44_limits.json", doc)
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert client.inserted("obligations") == []
    written = client.inserted("module_obligations")
    assert len(written) == 1
    assert written[0]["cadence_months"] == 3
    assert written[0]["self_declared_review"] is False
    assert written[0]["label"]          # NOT NULL on 027


def test_a_fractional_cadence_is_reported_as_a_shape_conflict():
    """GU44's 0.333 days is three checks a day; 023's column is INTEGER."""
    report = Report()
    describe_obligations("gu44", {"obligations": [{
        "obligation_type": "inspection", "cadence_days": 0.333,
    }]}, report)
    assert any("fractional" in msg for _, msg in report.shape_conflicts)


def test_a_cadenceless_obligation_becomes_a_self_declared_review():
    """The guideline states a duty and no frequency — 41 of these exist.

    It is no longer refused: 027's self_declared_review holds it, and
    core/obligations.py reports it as needing a cadence agreed with the client
    rather than as either compliant or late. It is still SURFACED, because every
    one is a conversation somebody owes the client — and because the trigger,
    where there is one, is prose in cadence_note that a human must promote
    rather than a parser.
    """
    report = Report()
    row = loader.template_row(
        {"obligation_type": "sampling",
         "cadence_note": "Event-triggered: due after a cleaning or disinfection."},
        "mod-1", "std-1", "Sampling", "gu44.obligations[0]", report)
    assert row["self_declared_review"] is True
    assert row["cadence_months"] is None and row["cadence_days"] is None
    assert row["trigger_event"] is None

    report2 = Report()
    describe_obligations("gu44", {"obligations": [{
        "obligation_type": "sampling",
        "cadence_note": "Event-triggered: due after a cleaning or disinfection.",
    }]}, report2)
    assert any("self-declared review" in msg for _, msg in report2.shape_conflicts)


def test_examination_requirements_are_reported_not_loaded(tmp_path):
    doc = make_doc(module_kind="compliance", specification_sets=[], examinations=[{
        "examination_type": "test", "cadence_months": 12,
        "certificate_validity_months": None, "trigger_event": None,
    }])
    write_doc(tmp_path, "gu48_certificates.json", doc)
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert client.inserted("obligations") == []
    assert client.inserted("certificates") == []
    assert any("examination requirements" in reason
               for _, _, reason in report.unloadable_obligations)


# ── The real corpus ──────────────────────────────────────────────────────────

@pytest.mark.skipif(not os.path.isdir(loader.DATA_DIR),
                    reason="extraction corpus not present")
def test_the_real_corpus_dry_runs_without_writing_or_selling_anything():
    client = FakeClient()
    report = loader.load(directory=loader.DATA_DIR, apply=False, client=client)

    for name in ("standards", "specification_sets", "spec_limits",
                 "guideline_modules", "obligations", "certificates"):
        assert client.inserted(name) == []
    # The blocking limit findings the validator reports are a worklist, and the
    # loader must surface them rather than loading them.
    assert report.blocked_limits
    # §7.13 has nowhere in 022 to live, so it must be said out loud every run.
    assert any(where == "gu93" for where, _ in report.shape_conflicts)


def test_a_dormant_guideline_is_flagged_because_022_cannot_record_it(tmp_path):
    """GU93 contradicts the current GU85; nothing in the schema can say so."""
    doc = make_doc(specification_sets=[], obligations=[])
    doc["standard"]["code"] = "DM-HSD-GU93-LAP_E"
    write_doc(tmp_path, "gu93_checklist.json", doc)
    client = FakeClient()

    report = loader.load(directory=str(tmp_path), apply=True, client=client)

    assert any(where == "gu93" and "lifecycle_status" in msg
               for where, msg in report.shape_conflicts)
