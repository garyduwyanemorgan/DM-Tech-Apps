"""The correlation id must be readable by the browser, not merely sent.

`RequestIdMiddleware` puts `X-Request-Id` on every response, and the UI shows it
so a user can quote it to support. Between those two facts sits a rule that is
easy to miss: **a browser can only read response headers named in the server's
CORS `expose_headers`.** `allow_headers` governs REQUEST headers and does not
cover this, and there is no wildcard default — `expose_headers` must list the
header explicitly.

The failure mode is what makes this worth a test. Same-origin calls (the Vite
proxy in development, the mounted SPA in production) can read the header
regardless, so everything looks correct locally. Only a cross-origin caller —
which `allow_origins=["*"]` explicitly invites — gets `null`, silently, with no
error anywhere. That is precisely the kind of invisible gap this whole
observability effort exists to remove.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api_server  # noqa: E402

CROSS_ORIGIN = {"Origin": "https://some-other-host.example"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(api_server.app)


def _exposed(response) -> set[str]:
    raw = response.headers.get("access-control-expose-headers", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()}


def test_the_header_is_present_at_all(client):
    """Positive first: prove it is being sent before asserting it is readable."""
    res = client.get("/api/version")
    assert res.headers.get("x-request-id"), "middleware did not stamp the response"


def test_a_cross_origin_caller_may_read_the_request_id(client):
    """The assertion that actually protects the feature."""
    res = client.get("/api/version", headers=CROSS_ORIGIN)
    assert res.headers.get("x-request-id")
    assert "x-request-id" in _exposed(res), (
        "X-Request-Id is sent but not listed in Access-Control-Expose-Headers, "
        "so a cross-origin browser reads null and the id is unquotable"
    )


def test_an_error_response_also_carries_a_readable_id(client):
    """The response a user reports is usually the failing one."""
    res = client.get("/api/sites", headers=CROSS_ORIGIN)   # 401, unauthenticated
    assert res.status_code == 401
    assert res.headers.get("x-request-id")
    assert "x-request-id" in _exposed(res)


def test_a_caller_supplied_id_is_echoed_so_it_can_be_correlated_upstream(client):
    res = client.get("/api/version", headers={**CROSS_ORIGIN, "X-Request-Id": "upstream-42"})
    assert res.headers.get("x-request-id") == "upstream-42"
