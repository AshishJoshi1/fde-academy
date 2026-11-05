"""Print a short "where are we" summary at the start of a Claude Code session.

Run by the SessionStart hook in .claude/settings.json and by /today.
Standard library only, so it works before the venv exists.

Sources, in order of authority:
  1. PROGRESS.md           build state + exact stopping point (repo root)
  2. git status            uncommitted work in this repo and tracked project repos
  3. learner database      quiz misses, spend (added once labctl exists)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROGRESS = ROOT / "PROGRESS.md"


def section(text: str, heading: str) -> str:
    """Return the body of '## heading' up to the next '## ' heading."""
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def git_dirty(repo: Path) -> str:
    if not (repo / ".git").exists():
        return "not a git repo yet"
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
        ).stdout
        ahead = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "@{u}..HEAD"],
            capture_output=True, text=True, timeout=10, encoding="utf-8",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"git error: {exc}"
    changed = len([line for line in out.splitlines() if line.strip()])
    parts = [f"{changed} uncommitted file(s)" if changed else "clean"]
    if ahead.returncode == 0 and ahead.stdout.strip() not in ("", "0"):
        parts.append(f"{ahead.stdout.strip()} commit(s) not pushed")
    elif ahead.returncode != 0:
        parts.append("no upstream yet")
    return ", ".join(parts)


def tracked_repos(text: str) -> list[Path]:
    repos = [ROOT]
    for line in section(text, "Tracked repos").splitlines():
        m = re.search(r"`([^`]+)`", line)
        if m:
            p = Path(m.group(1))
            p = p if p.is_absolute() else (ROOT / p).resolve()
            if p != ROOT:
                repos.append(p)
    return repos


def learner_db_line() -> str:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    db = Path(base) / "fde-academy" / "academy.db"
    if not db.exists():
        return "Learner DB: not created yet (arrives with Milestone 1 step 1)."
    labctl = ROOT / "tools" / "labctl.py"
    if labctl.exists():
        try:
            res = subprocess.run(
                [sys.executable, "-X", "utf8", str(labctl), "status", "--brief"],
                capture_output=True, text=True, timeout=20, encoding="utf-8",
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    return f"Learner DB: {db} (run `labctl status` for details)."


def main() -> int:
    if not PROGRESS.exists():
        print("FDE Academy: PROGRESS.md not found. Run /today to rebuild it from git log.")
        return 0
    text = PROGRESS.read_text(encoding="utf-8")
    print("=== FDE Academy: session status ===")
    position = section(text, "Current position")
    last = section(text, "Last session")
    if position:
        print("Current position:\n" + position)
    if last:
        print("\nLast session:\n" + last)
    print("\nRepos:")
    for repo in tracked_repos(text):
        print(f"  - {repo}: {git_dirty(repo)}")
    print("\n" + learner_db_line())
    print("\nStart with /today (spaced review + today's goal). End with /wrap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
