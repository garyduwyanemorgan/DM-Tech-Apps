"""The database guard must be fail-closed in every direction.

This exists because the two riskiest states are both silent: writing to the
frozen lagoon database (which has no marker row) and writing to a half-built
project (which has no marker row either). Both must refuse, and so must a
database that names itself something else.
"""
from __future__ import annotations

import pytest

from db.guard import EXPECTED_DEPLOYMENT, WrongDatabase, assert_deployment, read_deployment


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, data=None, raises=False):
        self._data = data
        self._raises = raises

    def select(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._raises:
            raise RuntimeError('relation "deployment_identity" does not exist')
        return FakeResponse(self._data)


class FakeClient:
    def __init__(self, data=None, raises=False):
        self._table = FakeTable(data, raises)

    def table(self, _name):
        return self._table


# ── read_deployment ──────────────────────────────────────────────────────────

def test_reads_the_deployment_name():
    client = FakeClient([{"deployment": "dm-tech-apps"}])
    assert read_deployment(client) == "dm-tech-apps"


def test_missing_table_reads_as_none_rather_than_raising():
    """The lagoon database predates migration 000 and has no such table."""
    assert read_deployment(FakeClient(raises=True)) is None


def test_empty_table_reads_as_none():
    assert read_deployment(FakeClient([])) is None


def test_null_data_reads_as_none():
    assert read_deployment(FakeClient(None)) is None


# ── assert_deployment ────────────────────────────────────────────────────────

def test_passes_on_the_expected_deployment():
    client = FakeClient([{"deployment": EXPECTED_DEPLOYMENT}])
    assert_deployment(client)          # must not raise


def test_refuses_a_database_with_no_marker():
    """Covers both the lagoon database and an unbootstrapped project."""
    with pytest.raises(WrongDatabase, match="no deployment_identity row"):
        assert_deployment(FakeClient(raises=True))


def test_refuses_a_database_naming_another_deployment():
    client = FakeClient([{"deployment": "decca-lagoons"}])
    with pytest.raises(WrongDatabase, match="decca-lagoons"):
        assert_deployment(client)


def test_refusal_names_both_the_found_and_expected_deployment():
    """The operator has to be able to see which way round the mistake is."""
    client = FakeClient([{"deployment": "decca-lagoons"}])
    with pytest.raises(WrongDatabase) as exc:
        assert_deployment(client)
    assert "decca-lagoons" in str(exc.value)
    assert EXPECTED_DEPLOYMENT in str(exc.value)


def test_expected_deployment_is_overridable_for_other_deployments():
    client = FakeClient([{"deployment": "staging"}])
    assert_deployment(client, expected="staging")
    with pytest.raises(WrongDatabase):
        assert_deployment(client, expected="production")


# ── The seeder must consult the guard ────────────────────────────────────────

def test_seeder_refuses_to_run_against_the_wrong_database(monkeypatch):
    """A dry run against the wrong database is still a wrong answer acted upon."""
    import db.seed_standards as seeder

    monkeypatch.setattr(seeder, "is_configured", lambda: True)
    monkeypatch.setattr(seeder, "get_client",
                        lambda: FakeClient([{"deployment": "decca-lagoons"}]))

    with pytest.raises(seeder.SeedError, match="decca-lagoons"):
        seeder.seed(dry_run=True)
