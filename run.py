"""One command to set up and start FDE Academy:

    python run.py               # create .venv if needed, install, build web if stale, start, open browser
    python run.py --no-browser  # any extra args go to the server (see: python -m academy_server --help)

Standard library only: this runs before any dependency is installed.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
STAMP = VENV / ".fde-academy-installed"
WEB = ROOT / "web"
MIN_PY = (3, 12)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def sh(cmd: list[str], **kw) -> None:
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def ensure_venv() -> None:
    if not venv_python().exists():
        print("Creating virtual environment in .venv ...")
        sh([sys.executable, "-m", "venv", str(VENV)])


def ensure_installed() -> None:
    want = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    if STAMP.exists() and STAMP.read_text().strip() == want:
        return
    print("Installing FDE Academy and its dependencies ...")
    py = str(venv_python())
    try:
        sh([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        sh([py, "-m", "pip", "install", "--quiet", "--prefer-binary", "-e", ".[dev]"], cwd=ROOT)
    except subprocess.CalledProcessError:
        print("\nInstall failed. If a package has no wheel for this Python yet, recreate the venv with an "
              "older Python, e.g. on Windows:\n  rmdir /s .venv  &&  py -3.13 run.py\n", file=sys.stderr)
        raise SystemExit(1)
    STAMP.write_text(want)


def web_is_stale() -> bool:
    dist = WEB / "dist" / "index.html"
    if not dist.exists():
        return True
    built = dist.stat().st_mtime
    sources = [p for d in ("src", "public") if (WEB / d).exists() for p in (WEB / d).rglob("*") if p.is_file()]
    sources += [p for p in (WEB / "index.html", WEB / "package.json", WEB / "vite.config.ts") if p.exists()]
    return any(p.stat().st_mtime > built for p in sources)


def ensure_web() -> None:
    if not (WEB / "package.json").exists():
        return  # UI not written yet (arrives in Milestone 1 step 5); server shows a placeholder page
    if not web_is_stale():
        return
    npm = shutil.which("npm")
    if not npm:
        print("warning: npm not found; serving the last built UI (or the placeholder). Install Node 20+.",
              file=sys.stderr)
        return
    print("Building the web UI ...")
    if not (WEB / "node_modules").exists():
        sh([npm, "ci" if (WEB / "package-lock.json").exists() else "install"], cwd=WEB)
    sh([npm, "run", "build"], cwd=WEB)


def main() -> int:
    if sys.version_info < MIN_PY:
        print(f"FDE Academy needs Python {'.'.join(map(str, MIN_PY))}+ (this is {sys.version.split()[0]}).",
              file=sys.stderr)
        return 1
    ensure_venv()
    ensure_installed()
    ensure_web()
    # -X utf8: seed data has non-ASCII names; the Windows code page (cp1252) can't decode them.
    cmd = [str(venv_python()), "-X", "utf8", "-m", "academy_server", *sys.argv[1:]]
    try:
        return subprocess.call(cmd, cwd=ROOT)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
