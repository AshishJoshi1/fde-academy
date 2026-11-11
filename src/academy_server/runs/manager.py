"""Lesson runs: start the learner's code, stream its console, enforce the time limit, save it all.

A run is an ordered list of events. Every source appends to the same list under one lock,
so the order you see is the order things happened:
  run.started            the process is up (pid, model, time limit)
  console.out / .err     one line of output
  console.truncated      the 1 MB console cap was reached; later output is dropped
  llm.request            the relay received a model call (exact body, headers minus the key)
  llm.response / .error  what came back (body or stream, status, headers, timing, usage, cost)
  api.request            the step's fixture (the mock Meridian API) answered a request from
                         lesson code: method, path, query, status and the body it sent back
  run.exit               ok | error | timeout | stopped, plus the exit code

The lesson process runs with an allowlisted environment: the server's own variables (and
any secrets in them) are not inherited. It gets a dummy API key and the relay's URL, so a
print(os.environ) in lesson code can't leak the real key. This guards against accidents,
not against deliberately hostile code, which could still read files.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import fixtures
from .proctree import ProcessTree

DUMMY_KEY = "sk-academy-dummy-key-the-relay-holds-the-real-one"
CONSOLE_CAP_BYTES = 1_000_000
ENV_ALLOW = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
             "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "NUMBER_OF_PROCESSORS",
             "PROCESSOR_ARCHITECTURE", "OS", "LANG", "LC_ALL", "TZ")


class RunBusy(Exception):
    """Only one run at a time: one learner, one gateway rate limit."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Run:
    id: str
    token: str
    step_id: str
    module_id: str
    model: str
    entry: str
    playground: Path
    timeout_s: int
    started_at: str = field(default_factory=_now)
    status: str = "running"            # running | finished
    outcome: str | None = None         # ok | error | timeout | stopped
    exit_code: int | None = None
    cost_usd: float = 0.0
    calls: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    _t0: float = field(default_factory=time.monotonic, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _console_bytes: int = field(default=0, repr=False)
    _truncated: bool = field(default=False, repr=False)
    _stop_requested: bool = field(default=False, repr=False)
    _tree: ProcessTree | None = field(default=None, repr=False)
    _fixture: fixtures.Fixture | None = field(default=None, repr=False)
    _api_requests: int = field(default=0, repr=False)

    def emit(self, type: str, **data: Any) -> dict[str, Any]:
        with self._lock:
            event = {"seq": len(self.events) + 1, "t_ms": int((time.monotonic() - self._t0) * 1000),
                     "type": type, "data": data}
            self.events.append(event)
            return event

    def events_after(self, seq: int) -> list[dict[str, Any]]:
        """Events with seq > given seq. Seqs are 1-based and contiguous, so it's a slice."""
        with self._lock:
            return self.events[max(seq, 0):]

    def next_call(self) -> int:
        with self._lock:
            self.calls += 1
            return self.calls

    def record_api_request(self, **data: Any) -> None:
        with self._lock:
            self._api_requests += 1
            n = self._api_requests
        self.emit("api.request", n=n, fixture=self._fixture.name if self._fixture else None, **data)

    def add_cost(self, usd: float) -> None:
        with self._lock:
            self.cost_usd += usd

    def summary(self) -> dict[str, Any]:
        return {"run_id": self.id, "step_id": self.step_id, "model": self.model, "status": self.status,
                "outcome": self.outcome, "exit_code": self.exit_code, "cost_usd": round(self.cost_usd, 8),
                "calls": self.calls, "started_at": self.started_at, "timeout_s": self.timeout_s,
                "playground": str(self.playground / self.entry)}


class RunManager:
    def __init__(self, store: Any, *, relay_base: str, python: str = sys.executable):
        self.store = store
        self.relay_base = relay_base.rstrip("/")
        self.python = python
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}       # this launch's runs, by id
        self._active: dict[str, Run] = {}     # running, by relay token

    # ------------------------------------------------------------------ lookup
    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def by_token(self, token: str) -> Run | None:
        """The relay's only way in: an active run's token. Finished runs can't make calls."""
        return self._active.get(token)

    def active(self) -> Run | None:
        with self._lock:
            return next(iter(self._active.values()), None)

    # ------------------------------------------------------------------- start
    def start(self, *, step_id: str, module_id: str, entry: str, playground: Path,
              files: dict[str, str], model: str, timeout_s: int, fixture: str | None = None) -> Run:
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"
        run = Run(id=run_id, token=secrets.token_urlsafe(24), step_id=step_id, module_id=module_id,
                  model=model, entry=entry, playground=playground, timeout_s=timeout_s)
        with self._lock:
            if self._active:
                raise RunBusy(next(iter(self._active.values())).id)
            self._active[run.token] = run
            self._runs[run.id] = run
        try:
            self.store.record_run_start(run.id, step_id, module_id, "live", model, files)
            if fixture:
                run._fixture = fixtures.start(fixture, on_request=run.record_api_request)
            run._tree = ProcessTree([self.python, "-X", "utf8", "-u", entry], cwd=playground, env=self._env(run))
        except Exception as exc:
            run.emit("run.exit", outcome="error", exit_code=None, error=f"could not start: {exc}")
            self._finish(run, "error", None)
            raise
        run.emit("run.started", step_id=step_id, model=model, entry=entry, timeout_s=timeout_s,
                 pid=run._tree.proc.pid, job_object=run._tree.uses_job_object,
                 fixture={"name": run._fixture.name, "url": run._fixture.url} if run._fixture else None)
        threading.Thread(target=self._supervise, args=(run,), daemon=True, name=f"run-{run.id}").start()
        return run

    def _env(self, run: Run) -> dict[str, str]:
        env = {k: os.environ[k] for k in ENV_ALLOW if k in os.environ}
        env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
                   ANTHROPIC_BASE_URL=f"{self.relay_base}/relay/{run.token}",
                   ANTHROPIC_API_KEY=DUMMY_KEY, LAB_MODEL=run.model)
        if run._fixture is not None:
            env.update(run._fixture.env)     # the fixture's URL and this run's token for it
        return env

    # --------------------------------------------------------------- lifecycle
    def _supervise(self, run: Run) -> None:
        tree = run._tree
        readers = [threading.Thread(target=self._pump, args=(run, tree.proc.stdout, "console.out"), daemon=True),
                   threading.Thread(target=self._pump, args=(run, tree.proc.stderr, "console.err"), daemon=True)]
        for r in readers:
            r.start()
        timed_out = False
        try:
            tree.proc.wait(timeout=run.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
        tree.kill_tree()        # always: nothing the lesson started outlives its run
        code = tree.proc.wait()
        for r in readers:
            r.join(timeout=5)
        tree.close()
        outcome = ("timeout" if timed_out else "stopped" if run._stop_requested
                   else "ok" if code == 0 else "error")
        run.emit("run.exit", outcome=outcome, exit_code=code,
                 **({"error": f"time limit of {run.timeout_s}s reached; the whole process tree was killed"}
                    if timed_out else {}))
        self._finish(run, outcome, code)

    def _pump(self, run: Run, pipe, kind: str) -> None:
        for raw in iter(pipe.readline, b""):
            if run._console_bytes + len(raw) > CONSOLE_CAP_BYTES:
                if not run._truncated:
                    run._truncated = True
                    run.emit("console.truncated", cap_bytes=CONSOLE_CAP_BYTES)
                continue
            run._console_bytes += len(raw)
            run.emit(kind, text=raw.decode("utf-8", "replace").rstrip("\r\n"))
        pipe.close()

    def _finish(self, run: Run, outcome: str, code: int | None) -> None:
        run.outcome, run.exit_code = outcome, code
        if run._fixture is not None:
            run._fixture.stop()          # nothing the run started outlives it
        try:
            self.store.save_run_events(run.id, run.events)
            self.store.record_run_end(run.id, outcome, run.cost_usd)
        finally:
            run.status = "finished"   # after the last event, so a live stream sees run.exit first
            with self._lock:
                self._active.pop(run.token, None)

    def stop(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None or run.status != "running" or run._tree is None:
            return False
        run._stop_requested = True
        run._tree.kill_tree()
        return True

    def shutdown(self) -> None:
        for run in list(self._active.values()):
            self.stop(run.id)
