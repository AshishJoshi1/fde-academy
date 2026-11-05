"""Where FDE Academy keeps things. Standard library only.

Learner data lives outside the repo, per user:
  Windows  %LOCALAPPDATA%\\fde-academy
  macOS    ~/Library/Application Support/fde-academy
  Linux    $XDG_DATA_HOME/fde-academy (default ~/.local/share/fde-academy)
Set FDE_ACADEMY_HOME to override (tests do this).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP = "fde-academy"


def repo_root() -> Path:
    # src/academy_server/paths.py -> repo root
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get("FDE_ACADEMY_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP


def db_path() -> Path:
    return data_dir() / "academy.db"


def server_info_path() -> Path:
    """Written while the server runs: {port, url, pid}. Lets `labctl open` re-open the UI."""
    return data_dir() / "server.json"


def content_dir() -> Path:
    return repo_root() / "content"


def default_export_path() -> Path:
    return repo_root() / "progress" / "learner-progress.json"
