"""Application version — read from the root VERSION file.

`VERSION` is the source of truth (kept in step with `frontend/package.json`
by scripts/release.{sh,ps1}). The commit SHA comes from the hosting
platform's build environment; Render injects RENDER_GIT_COMMIT.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
_UNKNOWN = "0.0.0-dev"


@lru_cache(maxsize=1)
def get_version() -> str:
    """Return the semantic version string, e.g. "0.2.0"."""
    try:
        version = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return _UNKNOWN
    return version or _UNKNOWN


@lru_cache(maxsize=1)
def get_commit() -> str | None:
    """Return the short SHA of the deployed commit, if the platform exposes it."""
    sha = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT")
        or os.getenv("SOURCE_VERSION")
    )
    return sha[:7] if sha else None


def get_version_info() -> dict[str, str | None]:
    """Full version payload served by GET /api/version."""
    return {
        "version": get_version(),
        "commit": get_commit(),
        "environment": os.getenv("APP_ENV", "production" if get_commit() else "development"),
    }
