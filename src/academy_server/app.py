"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, pages, paths, playground
from .content.loader import ContentTree, LoadedStep, load_content
from .pricing import Pricing
from .relay import Upstream, build_router
from .runs import RunBusy, RunManager
from .security import STYLESHEET_PATH, LocalOnlyMiddleware, SecurityConfig
from .store import Store

MAX_FILE_CHARS = 200_000
DEFAULT_MODEL = "claude-opus-5-5"
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,63}$")


@dataclass
class AppSettings:
    token: str
    port: int
    content_dir: Path
    db_path: Path
    web_dist: Path
    extra_hosts: list[str] = field(default_factory=list)
    extra_origins: list[str] = field(default_factory=list)
    stylesheet: Path = field(default_factory=paths.stylesheet_path)
    upstream: Upstream | None = None        # the gateway; None means lesson calls get a 503 from the relay
    upstream_transport: Any = None          # tests: an httpx.MockTransport standing in for the gateway
    playground_root: Path = field(default_factory=paths.playground_root)
    pricing_path: Path = field(default_factory=paths.pricing_path)


class RunIn(BaseModel):
    model: str | None = None


def _sse(event: dict[str, Any]) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


SSE_END = "event: end\ndata: {}\n\n"


class FileIn(BaseModel):
    code: str = Field(max_length=MAX_FILE_CHARS)
    base_hash: str | None = None   # the version the editor loaded; None means overwrite whatever is on disk


def file_hash(text: str) -> str:
    """Version tag for optimistic saving: changes whenever the file's text changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def create_app(settings: AppSettings) -> FastAPI:
    store = Store(settings.db_path)
    manager = RunManager(store, relay_base=f"http://127.0.0.1:{settings.port}")
    clients: dict[str, httpx.AsyncClient] = {}

    def upstream_client() -> httpx.AsyncClient:
        if "gateway" not in clients:   # created on first use, inside the server's event loop
            clients["gateway"] = httpx.AsyncClient(transport=settings.upstream_transport,
                                                   timeout=httpx.Timeout(600.0, connect=10.0))
        return clients["gateway"]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.shutdown()
        if "gateway" in clients:
            await clients["gateway"].aclose()
        store.close()

    app = FastAPI(title="FDE Academy", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware, config=SecurityConfig(
        token=settings.token, port=settings.port,
        extra_hosts=settings.extra_hosts, extra_origins=settings.extra_origins,
        open_prefixes=("/relay/",)))   # the relay checks its own per-run token
    app.state.store = store
    app.state.manager = manager
    app.include_router(build_router(
        manager, settings.upstream, upstream_client, Pricing.load(settings.pricing_path), store,
        credentials_hint=f"put ANTHROPIC_BASE_URL and ANTHROPIC_API_KEY in {paths.credentials_path()} "
                         "and restart the server"))
    app.state.content = load_content(settings.content_dir)
    app.state.settings = settings

    def content() -> ContentTree:
        return app.state.content

    def get_step(step_id: str) -> LoadedStep:
        step = content().steps.get(step_id)
        if step is None:
            raise HTTPException(404, f"unknown step {step_id!r}")
        return step

    def step_files(step: LoadedStep, reset: bool = False) -> tuple[Path, dict[str, str]]:
        """The learner's copy in playground/<step-id>/ (created from the starter on first use)."""
        dest = settings.playground_root / step.full_id
        playground.prepare(step.starter_files(), dest, reset=reset)
        return dest, playground.read_files(dest, step.spec.files)

    def files_view(step: LoadedStep, dest: Path, files: dict[str, str]) -> dict[str, Any]:
        return {"dir": str(dest), "entry": step.spec.entry,
                "files": {name: {"code": code, "hash": file_hash(code)} for name, code in files.items()}}

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        tree = content()
        return {"store": store.status(),
                "content": {"modules": len(tree.modules), "steps": len(tree.steps), "errors": len(tree.errors)}}

    @app.get("/api/outline")
    def outline() -> list[dict[str, Any]]:
        return content().outline(store.step_status())

    @app.get("/api/continue")
    def resume() -> dict[str, Any]:
        """Where 'Continue where you left off' goes: last position, else the first step."""
        pos = store.position()
        if pos and pos["step_id"] in content().steps:
            return {"step_id": pos["step_id"], "filename": pos["filename"],
                    "cursor": [pos["cursor_line"], pos["cursor_col"]], "last_run_id": pos["last_run_id"],
                    "resumed": True}
        ids = content().ordered_step_ids()
        return {"step_id": ids[0] if ids else None, "resumed": False}

    @app.get("/api/steps/{step_id}")
    def step_detail(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        store.open_step(step.full_id, step.module_id, step.spec.entry)
        return {**step.public(), "code": step_files(step)[1],
                "status": store.step_status().get(step.full_id, "in_progress")}

    # ---------------------------------------------------------------- editor
    @app.get("/api/steps/{step_id}/files")
    def get_files(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        return files_view(step, *step_files(step))

    @app.put("/api/steps/{step_id}/files/{filename}")
    def save_file(step_id: str, filename: str, body: FileIn) -> dict[str, Any]:
        """Save from the lab editor. Refuses (409) when the file changed on disk since the editor loaded it."""
        step = get_step(step_id)
        if filename not in step.spec.files:
            raise HTTPException(400, f"{filename!r} is not a file of this step")
        dest, files = step_files(step)
        if body.base_hash is not None and body.base_hash != file_hash(files.get(filename, "")):
            raise HTTPException(409, "the file changed on disk since the editor loaded it (edited in VS Code?)")
        code = body.code.replace("\r\n", "\n")
        (dest / filename).write_text(code, encoding="utf-8", newline="\n")
        store.open_step(step.full_id, step.module_id, filename)
        return {"saved": True, "hash": file_hash(code)}

    @app.post("/api/steps/{step_id}/reset")
    def reset(step_id: str) -> dict[str, Any]:
        """Back to the starter. Past runs keep their code snapshots, and git has the history."""
        step = get_step(step_id)
        return files_view(step, *step_files(step, reset=True))

    @app.get("/api/steps/{step_id}/solution")
    def solution(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        if not step.spec.solution:
            raise HTTPException(404, "this step has no solution file")
        return {"files": step.solution_files()}

    # ------------------------------------------------------------------ runs
    @app.post("/api/steps/{step_id}/runs", status_code=201)
    def start_run(step_id: str, body: RunIn | None = None) -> dict[str, Any]:
        """Run the learner's playground copy of the step, live."""
        step = get_step(step_id)
        model = (body.model if body and body.model else None) or os.environ.get("LAB_MODEL") or DEFAULT_MODEL
        if not MODEL_ID.match(model):
            raise HTTPException(400, f"not a model id: {model!r}")
        dest, files = step_files(step)
        try:
            run = manager.start(step_id=step.full_id, module_id=step.module_id, entry=step.spec.entry,
                                playground=dest, files=files, model=model, timeout_s=step.spec.run.timeout_s)
        except RunBusy as busy:
            raise HTTPException(409, f"run {busy} is still running; stop it first")
        return {"run_id": run.id, "events": f"/api/runs/{run.id}/events",
                "code": str(dest / step.spec.entry), "gateway": settings.upstream is not None}

    def run_view(run_id: str) -> dict[str, Any]:
        run = manager.get(run_id)
        if run is not None:
            return {"run": run.summary(), "events": run.events_after(0)}
        rec = store.run_record(run_id)
        if rec is None:
            raise HTTPException(404, f"unknown run {run_id!r}")
        return {"run": {"run_id": rec["run_id"], "step_id": rec["step_id"], "model": rec["model"],
                        "status": "finished" if rec["ended_at"] else "lost", "outcome": rec["outcome"],
                        "cost_usd": rec["cost_usd"], "started_at": rec["started_at"]},
                "events": store.run_events(run_id)}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return run_view(run_id)

    @app.get("/api/steps/{step_id}/runs")
    def step_runs(step_id: str) -> dict[str, Any]:
        return {"runs": store.runs_for_step(get_step(step_id).full_id)}

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str) -> dict[str, Any]:
        if not manager.stop(run_id):
            raise HTTPException(409, "that run isn't running")
        return {"stopping": True}

    @app.get("/api/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
        """Server-sent events: everything after `after` (or Last-Event-ID), live until run.exit."""
        last = request.headers.get("last-event-id", "")
        start = int(last) if last.isdigit() else max(after, 0)
        run = manager.get(run_id)
        if run is None:
            events = run_view(run_id)["events"]          # 404s when unknown

            async def stream():
                for event in events[start:]:
                    yield _sse(event)
                yield SSE_END
        else:
            async def stream():
                seq = start
                while True:
                    for event in run.events_after(seq):
                        seq = event["seq"]
                        yield _sse(event)
                    if run.status == "finished" and not run.events_after(seq):
                        yield SSE_END
                        return
                    if await request.is_disconnected():
                        return
                    await asyncio.sleep(0.1)
        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"cache-control": "no-store", "x-accel-buffering": "no"})

    @app.get("/lab/{step_id}", include_in_schema=False, response_class=HTMLResponse)
    def lab(step_id: str, theme: str | None = None) -> str:
        step = get_step(step_id)
        store.open_step(step.full_id, step.module_id, step.spec.entry)
        return pages.lab_page(step, settings.playground_root / step.full_id / step.spec.entry,
                              gateway=settings.upstream is not None, theme=pages.theme_or_none(theme))

    @app.get("/api/mistakes")
    def mistakes(module: str | None = None) -> dict[str, Any]:
        return store.mistakes(module)

    @app.get("/api/content/errors")
    def content_errors() -> list[str]:
        return content().errors

    @app.post("/api/content/reload")
    def reload_content() -> dict[str, Any]:
        app.state.content = load_content(settings.content_dir)
        return {"steps": len(app.state.content.steps), "errors": app.state.content.errors}

    @app.get(STYLESHEET_PATH, include_in_schema=False)
    def stylesheet() -> FileResponse:
        if not settings.stylesheet.is_file():
            raise HTTPException(404, "stylesheet missing")
        return FileResponse(settings.stylesheet, media_type="text/css",
                            headers={"cache-control": "no-cache"})   # revalidate: edits show on reload

    @app.get("/design", include_in_schema=False, response_class=HTMLResponse)
    def design(theme: str | None = None) -> str:
        return pages.design_page(theme=pages.theme_or_none(theme))

    index = settings.web_dist / "index.html"
    if index.is_file():
        assets = settings.web_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/", include_in_schema=False)
        def spa() -> FileResponse:
            return FileResponse(index, headers={"cache-control": "no-store"})
    else:
        @app.get("/", include_in_schema=False, response_class=HTMLResponse)
        def placeholder(theme: str | None = None) -> str:
            return pages.home_page(content(), store, theme=pages.theme_or_none(theme))

    return app
