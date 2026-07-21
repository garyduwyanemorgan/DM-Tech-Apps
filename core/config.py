"""Single source of truth for secrets and configuration.

Every secret in the app resolves through here, in this order (first hit wins):

  1. Process environment          — what Render/CI sets; authoritative in cloud
  2. `.env` at the project root   — local dev convenience (gitignored)
  3. `.streamlit/secrets.toml`    — legacy local dev file (gitignored)

Only step 1 exists on Render: there is no `.env` and no `secrets.toml` on the
box, so a value missing from the Render dashboard resolves to "" and the
feature reports itself unconfigured rather than crashing.

Env var names are derived mechanically — `SECTION_KEY`, uppercased:

    [anthropic] api_key   ->  ANTHROPIC_API_KEY
    [clerk] dev_secret_key -> CLERK_DEV_SECRET_KEY

`_ALIASES` carries the handful of historical names that predate that rule, so
existing deployments keep working. See `.env.example` for the full list.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Iterable

_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"
_SECRETS_TOML = _ROOT / ".streamlit" / "secrets.toml"

# Extra env names checked after the mechanical SECTION_KEY form. These predate
# the naming rule and are still referenced by render.yaml / existing hosts.
_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("payments", "provider"): ("PAYMENT_PROVIDER",),   # mechanical: PAYMENTS_PROVIDER
    ("smtp", "password"): ("SMTP_PASS",),              # mechanical: SMTP_PASSWORD
}


def env_name(section: str, key: str) -> str:
    """The canonical env var name for a secret, e.g. ("anthropic", "api_key") -> ANTHROPIC_API_KEY."""
    return f"{section}_{key}".upper().replace("-", "_")


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    """Parse `.env` into a dict. Returns {} when absent (cloud, CI).

    Deliberately does not mutate os.environ: the process environment stays
    authoritative, so precedence is decided in one place — `secret()`.
    """
    values: dict[str, str] = {}
    try:
        text = _ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, raw = line.removeprefix("export ").partition("=")
        raw = raw.strip()
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
            raw = raw[1:-1]        # strip matching quotes; leave inner text as-is
        values[name.strip()] = raw
    return values


@lru_cache(maxsize=1)
def _toml() -> dict:
    """Load `.streamlit/secrets.toml` if present (local dev); {} on Render/serverless."""
    try:
        import tomllib
    except ImportError:                    # Python < 3.11
        import tomli as tomllib            # type: ignore[no-redef]
    try:
        with open(_SECRETS_TOML, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def secret(section: str, key: str, default: str = "") -> str:
    """Resolve one secret: env -> .env -> secrets.toml -> default.

    Always returns a string; missing values come back as `default` ("") rather
    than raising, so callers can report "not configured" in their own words.
    """
    names = (env_name(section, key), *_ALIASES.get((section, key), ()))
    dotenv = _dotenv()
    for name in names:
        value = os.environ.get(name) or dotenv.get(name)
        if value:
            return value.strip()
    value = _toml().get(section, {}).get(key, "")
    return str(value).strip() if value else default


def secret_block(section: str, keys: Iterable[str] = ()) -> dict[str, str]:
    """Resolve a whole section as a dict.

    With `keys`, each is resolved through the full `secret()` chain — use this
    for a known set of credentials, so a single value can be overridden by env
    without having to move the whole block out of secrets.toml.

    Without `keys`, returns the raw secrets.toml section — for sections whose
    key names are data rather than fixed config (e.g. [site_passwords], one
    entry per client site).
    """
    if keys:
        return {key: secret(section, key) for key in keys}
    return {str(k): v for k, v in (_toml().get(section, {}) or {}).items()}


def has_secrets_file() -> bool:
    """True when a local secrets.toml is in play — i.e. we are not on Render."""
    return bool(_toml())
