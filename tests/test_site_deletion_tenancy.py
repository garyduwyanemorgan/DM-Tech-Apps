"""Deleting a site must not reach another tenant's readings.

`delete_site` used to run a second delete keyed on `site_name` with no site_id
and no organisation predicate, to "cover legacy rows stored by site_name only".
Site names collide constantly — "Main Plant", "Site 1" — so deleting a site
deleted every tenant's readings of that name.

It was not even limited to legacy rows: `insert_reading` writes `site_name` on
every row, so it matched current data across the whole platform. RLS would have
stopped it; the backend runs as service_role and bypasses RLS, so nothing did.

`readings` has no organization_id column — tenancy lives only in site_id — so a
name-based delete cannot be made tenant-safe at all. This test pins that no
delete is ever issued on a name.
"""
from __future__ import annotations

import pytest

import db.queries as queries


class _Q:
    def __init__(self, table, log):
        self.table, self.log, self.filters = table, log, {}
        self.op = None

    def select(self, *a, **k):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def execute(self):
        if self.op == "delete":
            self.log.append((self.table, dict(self.filters)))
        data = [{"id": "site-1"}] if self.table == "sites" else []
        return type("R", (), {"data": data, "count": 0})()


class _Client:
    def __init__(self, log):
        self.log = log

    def table(self, name):
        return _Q(name, self.log)


@pytest.fixture
def deletes(monkeypatch):
    log: list[tuple[str, dict]] = []
    monkeypatch.setattr(queries, "get_client", lambda token=None: _Client(log))
    return log


def test_no_delete_is_ever_keyed_on_site_name(deletes):
    """The whole finding, in one assertion."""
    queries.delete_site("Main Plant", organization_id="org-1")
    by_name = [(t, f) for t, f in deletes if "site_name" in f]
    assert by_name == [], (
        f"a delete was issued keyed on site_name: {by_name}. `readings` has no "
        "organization_id, so this reaches every tenant with a site of that name."
    )


def test_readings_are_deleted_by_site_id(deletes):
    """The legitimate delete must still happen — removing it would orphan rows."""
    queries.delete_site("Main Plant", organization_id="org-1")
    readings = [f for t, f in deletes if t == "readings"]
    assert readings, "readings for the site were not deleted at all"
    assert all("site_id" in f for f in readings)


def test_every_delete_is_scoped_by_an_identifier_not_a_name(deletes):
    queries.delete_site("Main Plant", organization_id="org-1")
    for table, filters in deletes:
        # "id" does not end with "_id" — the primary key on `sites` is plain `id`.
        assert any(k == "id" or k.endswith("_id") for k in filters), (
            f"delete on {table} with filters {filters} is not scoped by an id")
