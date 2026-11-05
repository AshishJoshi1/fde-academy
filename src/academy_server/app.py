"""FastAPI application factory."""
from __future__ import annotations

import html
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .content.loader import ContentTree, LoadedStep, load_content
from .security import LocalOnlyMiddleware, SecurityConfig
from .store import Store

MAX_FILE_CHARS = 200_000


@dataclass
class AppSettings:
    token: str
    port: int
    content_dir: Path
    db_path: Path
    web_dist: Path
    extra_hosts: list[str] = field(default_factory=list)
    extra_origins: list[str] = field(default_factory=list)


class DraftIn(BaseModel):
    filename: str
    code: str = Field(max_length=MAX_FILE_CHARS)


def create_app(settings: AppSettings) -> FastAPI:
    store = Store(settings.db_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        store.close()

    app = FastAPI(title="FDE Academy", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware, config=SecurityConfig(
        token=settings.token, port=settings.port,
        extra_hosts=settings.extra_hosts, extra_origins=settings.extra_origins))
    app.state.store = store
    app.state.content = load_content(settings.content_dir)
    app.state.settings = settings

    def content() -> ContentTree:
        return app.state.content

    def get_step(step_id: str) -> LoadedStep:
        step = content().steps.get(step_id)
        if step is None:
            raise HTTPException(404, f"unknown step {step_id!r}")
        return step

    def code_for(step: LoadedStep) -> dict[str, str]:
        starter = step.starter_files()
        return {name: store.latest_code(step.full_id, name) or text for name, text in starter.items()}

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
        return {**step.public(), "code": code_for(step),
                "status": store.step_status().get(step.full_id, "in_progress")}

    @app.put("/api/steps/{step_id}/draft")
    def save_draft(step_id: str, body: DraftIn) -> dict[str, Any]:
        step = get_step(step_id)
        if body.filename not in step.spec.files:
            raise HTTPException(400, f"{body.filename!r} is not a file of this step")
        saved = store.save_draft(step.full_id, step.module_id, body.filename, body.code)
        return {"saved": saved}

    @app.post("/api/steps/{step_id}/reset")
    def reset(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        store.discard_drafts(step.full_id)
        return {"code": step.starter_files()}

    @app.get("/api/steps/{step_id}/solution")
    def solution(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        if not step.spec.solution:
            raise HTTPException(404, "this step has no solution file")
        return {"files": step.solution_files()}

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
        def placeholder() -> str:
            return _placeholder_page(content(), store)

    return app


def _placeholder_page(tree: ContentTree, store: Store) -> str:
    """Shown until the React UI is built (Milestone 1 step 5)."""
    status = store.step_status()
    st = store.status()
    rows = []
    for m in tree.outline(status):
        rows.append(f"<h2>{html.escape(m['id'])}: {html.escape(m['title'])}</h2><ul>")
        for c in m["chapters"]:
            rows.append(f"<li><b>{html.escape(c['title'])}</b><ul>")
            for s in c["steps"]:
                rows.append(f"<li><a href='/api/steps/{html.escape(s['id'])}'>{html.escape(s['id'])}</a> "
                            f"{html.escape(s['title'])} <code>{s['status']}</code></li>")
            rows.append("</ul></li>")
        rows.append("</ul>")
    errors = "".join(f"<li><code>{html.escape(e)}</code></li>" for e in tree.errors) or "<li>none</li>"
    pos = st["position"]
    return f"""<!doctype html><meta charset="utf-8"><title>FDE Academy</title>
<style>body{{font:15px system-ui;max-width:860px;margin:2rem auto;color:#222}}code{{background:#f3f3f3;padding:0 4px}}</style>
<h1>FDE Academy <small>v{__version__}</small></h1>
<p>The interactive UI arrives in Milestone 1 step 5. The server, store and lesson loader are live.</p>
<p><b>Continue:</b> {html.escape(pos['step_id']) if pos else 'not started'} ·
<b>Quiz:</b> {st['quiz']['attempts']} attempts, {st['quiz']['still_wrong']} still wrong ·
<b>Spend today:</b> ${st['spend']['today_usd']:.4f}</p>
{''.join(rows)}
<h3>Content errors</h3><ul>{errors}</ul>"""
