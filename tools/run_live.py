"""Run a lesson step's code live against Claude.

    .venv/Scripts/python -X utf8 tools/run_live.py m02.lab02.s01            # run your copy
    .venv/Scripts/python -X utf8 tools/run_live.py m02.lab02.s01 --reset    # start over from the starter
    .venv/Scripts/python -X utf8 tools/run_live.py m02.lab02.s01 --model claude-sonnet-5-5
    ANTHROPIC_LOG=debug .venv/Scripts/python -X utf8 tools/run_live.py m02.lab02.s01   # see the raw request

- The first run copies the step's starter files to playground/<step-id>/ (tracked in git). Edit them
  there. Later runs never overwrite your edits; --reset copies the starter again.
- ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY come from %LOCALAPPDATA%\\fde-academy\\anthropic.env and
  go into the lesson process only, never into your shell. The key is never printed.
- A step with a fixture (`run: {fixture: meridian}`) gets it here too: the mock Meridian API starts on a
  free port for the run, and each request it answers is printed as a [meridian] line.

Lesson code runs with your real key, so only run code you've read. Spend is capped by the
gateway's per-key budget, not by this tool.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from academy_server import fixtures, paths, playground  # noqa: E402
from academy_server.credentials import REQUIRED, CredentialsError, load_credentials  # noqa: E402

KEEP = ("ANTHROPIC_LOG",)   # SDK logging switch: ANTHROPIC_LOG=debug prints each request body and retry decision


def child_env(creds: dict[str, str], model: str | None) -> dict[str, str]:
    """Inherited ANTHROPIC_* credentials and URLs are dropped so only the file's values apply."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTHROPIC_") or k in KEEP}
    env.update({k: creds[k] for k in REQUIRED})
    env["PYTHONUTF8"] = "1"
    if model:
        env["LAB_MODEL"] = model
    return env


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_live", description=__doc__.split("\n\n")[0])
    ap.add_argument("step_id", help="e.g. m02.lab02.s01")
    ap.add_argument("--reset", action="store_true", help="discard your copy and start from the starter")
    ap.add_argument("--model", help="sets LAB_MODEL for this run, e.g. claude-sonnet-5-5")
    args = ap.parse_args(argv)

    from academy_server.content.loader import load_content  # needs the venv (pyyaml, pydantic)

    tree = load_content(paths.content_dir())
    step = tree.steps.get(args.step_id)
    if step is None:
        known = ", ".join(sorted(tree.steps)) or "none"
        print(f"unknown step {args.step_id!r}. Known: {known}", file=sys.stderr)
        return 2

    try:
        creds = load_credentials(paths.credentials_path())
    except CredentialsError as exc:
        raise SystemExit(str(exc))
    play = paths.playground_root() / step.full_id
    written = playground.prepare(step.starter_files(), play, reset=args.reset)
    entry = step.spec.entry
    model = args.model or os.environ.get("LAB_MODEL") or "claude-opus-5-5"
    host = creds["ANTHROPIC_BASE_URL"].split("://")[-1].rstrip("/")

    print(f"live run · {step.full_id} · {model} via {host}")
    print(f"your code: {play / entry}" + ("  (fresh copy of the starter)" if written else ""))
    env = child_env(creds, model)
    fixture = None
    if step.spec.run.fixture:
        def show(method, path, query, status, body):
            print(f"[{step.spec.run.fixture}] {method} {path}{'?' + query if query else ''} -> {status}", flush=True)
        fixture = fixtures.start(step.spec.run.fixture, on_request=show)
        env.update(fixture.env)
        print(f"fixture: {fixture.name} mock API on {fixture.url}")
    print("note: live calls cost money; the gateway enforces your key's budget\n", flush=True)
    try:
        return subprocess.call([sys.executable, "-X", "utf8", "-u", entry], cwd=play, env=env)
    finally:
        if fixture is not None:
            fixture.stop()


if __name__ == "__main__":
    sys.exit(main())
