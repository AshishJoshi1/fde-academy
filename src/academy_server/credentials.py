"""Gateway credentials from %LOCALAPPDATA%\\fde-academy\\anthropic.env. Standard library only.

The file holds KEY=VALUE lines. '#' comments and blank lines are ignored, and a BOM and
surrounding quotes are tolerated. Error messages name the missing keys, never the values.
"""
from __future__ import annotations

from pathlib import Path

REQUIRED = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY")


class CredentialsError(ValueError):
    pass


def load_credentials(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise CredentialsError(f"no credentials file at {path}. "
                               "Create it with ANTHROPIC_BASE_URL=... and ANTHROPIC_API_KEY=...")
    creds: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        creds[key.strip()] = value.strip().strip('"').strip("'")
    missing = [k for k in REQUIRED if not creds.get(k)]
    if missing:
        raise CredentialsError(f"{path} is missing: {', '.join(missing)}")
    return creds
