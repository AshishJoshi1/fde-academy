"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anthropic
import httpx
from anthropic._constants import ANTHROPIC_API_VERSION   # the version the lesson SDK sends
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, pages, paths, playground, tutor
from .content.loader import ContentTree, LoadedStep, load_content
from .content.schema import FACTS, Experiment
from .experiments import answer_text, check_answer, code_diff, error_message, grade, grade_quiz, run_facts
from .pricing import Pricing
from .relay import Upstream, build_router
from .runs import RunBusy, RunManager
from .security import STYLESHEET_PATH, LocalOnlyMiddleware, SecurityConfig
from .store import Store

MAX_FILE_CHARS = 200_000
DEFAULT_MODEL = "claude-opus-5-5"
MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,63}$")
CARD_PREFIX = "cards:"     # flash-card reviews are quiz attempts with item ids cards:<deck>:<card>
CARD_MODULE = "cards"      # ...and this module id, so /quiz m02 and module filters leave them out


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
    tutor_transport: Any = None             # tests: the same for the tutor, an httpx2.MockTransport (the SDK runs on httpx2)
    playground_root: Path = field(default_factory=paths.playground_root)
    pricing_path: Path = field(default_factory=paths.pricing_path)


class RunIn(BaseModel):
    model: str | None = None
    experiment: str | None = None   # grade this experiment's committed predictions against the run


class PredictionsIn(BaseModel):
    answers: dict[str, Any]


class ExplainIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class QuizIn(BaseModel):
    answer: Any


class TutorIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class StartOverIn(BaseModel):
    code: bool = False   # also put the code back to the starter


class CardReviewIn(BaseModel):
    knew: bool


class CountIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_FILE_CHARS)
    model: str = DEFAULT_MODEL


# Facts that need the gateway's count_tokens to measure.
TOKEN_FACTS = {"response.text_tokens", "response.hidden_output_tokens"}


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

    sdk: dict[str, anthropic.AsyncAnthropic] = {}

    def tutor_client() -> anthropic.AsyncAnthropic:
        """The tutor's SDK client: the real key, straight to the gateway (not through the relay)."""
        if "tutor" not in sdk:
            assert settings.upstream is not None
            http = anthropic.DefaultAsyncHttpxClient(transport=settings.tutor_transport) if settings.tutor_transport else None
            sdk["tutor"] = anthropic.AsyncAnthropic(api_key=settings.upstream.api_key, base_url=settings.upstream.base_url,
                                                    http_client=http, timeout=120.0, max_retries=2)
        return sdk["tutor"]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        manager.shutdown()
        if "gateway" in clients:
            await clients["gateway"].aclose()
        if "tutor" in sdk:
            await sdk["tutor"].close()
        store.close()

    app = FastAPI(title="FDE Academy", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware, config=SecurityConfig(
        token=settings.token, port=settings.port,
        extra_hosts=settings.extra_hosts, extra_origins=settings.extra_origins,
        open_prefixes=("/relay/",)))   # the relay checks its own per-run token
    app.state.store = store
    app.state.manager = manager
    pricing = Pricing.load(settings.pricing_path)
    app.include_router(build_router(
        manager, settings.upstream, upstream_client, pricing, store,
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

    def get_experiment(step: LoadedStep, experiment_id: str) -> Experiment:
        exp = step.spec.experiment(experiment_id)
        if exp is None:
            raise HTTPException(404, f"step {step.full_id} has no experiment {experiment_id!r}")
        return exp

    def since(step: LoadedStep) -> str | None:
        """When the step was last started over: the lab shows only what came after it."""
        return store.started_over_at(step.full_id)

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

    def start_over(steps: list[LoadedStep], code: bool) -> dict[str, Any]:
        at = store.start_over([(s.full_id, s.module_id) for s in steps], code_reset=code)
        reset = []
        if code:
            for s in steps:
                if (settings.playground_root / s.full_id).is_dir():   # never create a copy that wasn't there
                    step_files(s, reset=True)
                    reset.append(s.full_id)
        return {"started_over_at": at, "steps": [s.full_id for s in steps], "code_reset": reset}

    @app.post("/api/steps/{step_id}/start-over")
    def start_step_over(step_id: str, body: StartOverIn | None = None) -> dict[str, Any]:
        """Do the lesson fresh: its answers, experiments, latest run and tutor threads start empty.
        Nothing is deleted; spaced review, quiz history, spend and run history keep everything."""
        return start_over([get_step(step_id)], bool(body and body.code))

    @app.post("/api/start-over")
    def start_all_over(body: StartOverIn | None = None) -> dict[str, Any]:
        """The same for every lesson."""
        return start_over(list(content().steps.values()), bool(body and body.code))

    @app.get("/api/steps/{step_id}/solution")
    def solution(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        if not step.spec.solution:
            raise HTTPException(404, "this step has no solution file")
        return {"files": step.solution_files()}

    # ------------------------------------------------------------------ runs
    @app.post("/api/steps/{step_id}/runs", status_code=201)
    def start_run(step_id: str, body: RunIn | None = None) -> dict[str, Any]:
        """Run the learner's playground copy of the step, live. With an experiment, the run is
        the one its committed predictions get graded against."""
        step = get_step(step_id)
        model = (body.model if body and body.model else None) or os.environ.get("LAB_MODEL") or DEFAULT_MODEL
        if not MODEL_ID.match(model):
            raise HTTPException(400, f"not a model id: {model!r}")
        attempt = None
        if body and body.experiment:
            exp = get_experiment(step, body.experiment)
            attempts = store.attempts(step.full_id, exp.id, since(step))
            attempt = attempts[-1] if attempts else None
            if attempt is None or attempt["run_id"] or attempt["graded_at"]:
                raise HTTPException(409, f"commit your predictions for {exp.id} first: Run stays locked until then")
        dest, files = step_files(step)
        try:
            run = manager.start(step_id=step.full_id, module_id=step.module_id, entry=step.spec.entry,
                                playground=dest, files=files, model=model, timeout_s=step.spec.run.timeout_s,
                                fixture=step.spec.run.fixture)
        except RunBusy as busy:
            raise HTTPException(409, f"run {busy} is still running; stop it first")
        if attempt is not None:
            store.attach_run(attempt["id"], run.id)
        return {"run_id": run.id, "events": f"/api/runs/{run.id}/events", "experiment": body.experiment if body else None,
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

    @app.get("/api/runs/{run_id}/diff")
    def run_diff(run_id: str) -> dict[str, Any]:
        """What changed since the previous run of the same step: the code, and the model."""
        rec = store.run_record(run_id)
        if rec is None:
            raise HTTPException(404, f"unknown run {run_id!r}")
        prev = store.previous_run(run_id)
        view: dict[str, Any] = {"run_id": run_id, "prev_run_id": prev["run_id"] if prev else None,
                                "model": {"prev": prev["model"] if prev else None, "now": rec["model"]},
                                "code": store.run_code(run_id), "diff": "", "note": ""}
        if prev is None:
            view["note"] = "This is your first run of this step, so there is nothing to compare with."
            return view
        before = store.run_code(prev["run_id"])
        if not before:
            view["note"] = "The previous run's code wasn't saved, so it can't be compared."
            return view
        view["diff"] = code_diff(before, view["code"])
        return view

    @app.get("/api/steps/{step_id}/runs")
    def step_runs(step_id: str) -> dict[str, Any]:
        """Every run, for the history menu. The lab reopens the latest only if it's from after
        the step was last started over."""
        step = get_step(step_id)
        return {"runs": store.runs_for_step(step.full_id), "started_over_at": since(step)}

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

    # ----------------------------------------------------------- experiments
    def run_events_for(run_id: str) -> tuple[str, list[dict[str, Any]]]:
        """(running | finished | lost, events). Lost: the server stopped before the run ended."""
        run = manager.get(run_id)
        if run is not None:
            events = run.events_after(0)   # run.exit is always the last event a run emits
            return ("finished" if events and events[-1]["type"] == "run.exit" else run.status), events
        rec = store.run_record(run_id)
        if rec is None or not rec["ended_at"]:
            return "lost", []
        return "finished", store.run_events(run_id)

    async def count_tokens(model: str, text: str) -> int:
        """input_tokens of one user message holding text. Free: count_tokens isn't billed."""
        if settings.upstream is None:
            raise HTTPException(503, f"no gateway credentials: put them in {paths.credentials_path()} and restart")
        r = await upstream_client().post(
            f"{settings.upstream.base_url.rstrip('/')}/v1/messages/count_tokens",
            json={"model": model, "messages": [{"role": "user", "content": text}]},
            headers={"authorization": f"Bearer {settings.upstream.api_key}",
                     "anthropic-version": ANTHROPIC_API_VERSION})
        if r.status_code >= 400:
            try:
                detail = error_message(r.json())
            except ValueError:
                detail = r.text[:300]
            raise HTTPException(502, f"count_tokens failed with {r.status_code}: {detail}")
        return int(r.json()["input_tokens"])

    wrappers: dict[str, int] = {}

    async def measure_text(model: str, text: str) -> dict[str, int]:
        """A message wraps its text in a few tokens of its own. Measure that wrapper once per model
        (one-character text, "a", is one token) and subtract it, leaving the text's own tokens."""
        if model not in wrappers:
            wrappers[model] = await count_tokens(model, "a") - 1
        total = await count_tokens(model, text)
        return {"input_tokens": total, "wrapper_tokens": wrappers[model], "text_tokens": total - wrappers[model]}

    async def grade_attempt(exp: Experiment, attempt: dict[str, Any]) -> dict[str, Any]:
        """Grade an attempt against its run, once the run has finished."""
        status, events = run_events_for(attempt["run_id"])
        if status == "running":
            return attempt
        prev = store.previous_run(attempt["run_id"])
        prev_events = run_events_for(prev["run_id"])[1] if prev else None
        tokens = None
        wanted = {getattr(p, "answer_from", None) or getattr(p, "show_from", None) for p in exp.predict}
        text = answer_text(events)
        if wanted & TOKEN_FACTS and text:
            model = run_facts(events)["request.model"] or DEFAULT_MODEL
            try:
                tokens = (await measure_text(model, text))["text_tokens"]
            except HTTPException:
                tokens = None            # graded as "not measured"
        facts = run_facts(events, prev_events, tokens)
        answers = {p["item_id"]: p["answer"] for p in attempt["predictions"]}
        store.save_grades(attempt["id"], {p.id: grade(p, answers[p.id], facts)
                                          for p in exp.predict if p.id in answers})
        return store.attempt(attempt["id"])

    async def card_state(step: LoadedStep, exp: Experiment) -> dict[str, Any]:
        attempts = store.attempts(step.full_id, exp.id, since(step))
        latest = attempts[-1] if attempts else None
        if latest and latest["run_id"] and not latest["graded_at"]:
            latest = attempts[-1] = await grade_attempt(exp, latest)
        status = ("predict" if latest is None else "committed" if not latest["run_id"]
                  else "running" if not latest["graded_at"] else "graded" if not latest["explained_at"]
                  else "explained")
        return {"card": exp.public(), "status": status, "attempt": latest, "earlier": attempts[:-1],
                "explain": exp.explain if status == "explained" else None}

    @app.get("/api/steps/{step_id}/experiments")
    async def experiments(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        return {"experiments": [await card_state(step, e) for e in step.spec.experiments]}

    @app.post("/api/steps/{step_id}/experiments/{experiment_id}/predictions")
    async def commit_predictions(step_id: str, experiment_id: str, body: PredictionsIn) -> dict[str, Any]:
        """Lock in your predictions. Run unlocks for this card after this."""
        step = get_step(step_id)
        exp = get_experiment(step, experiment_id)
        items = []
        for p in exp.predict:
            if p.id not in body.answers:
                raise HTTPException(400, f"answer every prediction first: {p.id} is missing")
            try:
                answer = check_answer(p, body.answers[p.id])
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            items.append({"item_id": p.id, "type": p.type, "prompt": p.prompt, "answer": answer})
        try:
            store.commit_predictions(step.full_id, step.module_id, exp.id, items, since=since(step))
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return await card_state(step, exp)

    @app.post("/api/steps/{step_id}/experiments/{experiment_id}/grade")
    async def grade_experiment(step_id: str, experiment_id: str) -> dict[str, Any]:
        """Compare: grade the predictions against the run they're attached to (idempotent)."""
        step = get_step(step_id)
        exp = get_experiment(step, experiment_id)
        attempts = store.attempts(step.full_id, exp.id, since(step))
        if not attempts or not attempts[-1]["run_id"]:
            raise HTTPException(409, f"nothing to grade yet: commit predictions for {exp.id}, then run")
        return await card_state(step, exp)

    @app.post("/api/steps/{step_id}/experiments/{experiment_id}/explain")
    async def explain(step_id: str, experiment_id: str, body: ExplainIn) -> dict[str, Any]:
        """Your own why first; the card's explanation comes back with it."""
        step = get_step(step_id)
        exp = get_experiment(step, experiment_id)
        attempts = store.attempts(step.full_id, exp.id, since(step))
        if not attempts or not store.save_explanation(attempts[-1]["id"], body.text.strip()):
            raise HTTPException(409, f"run {exp.id} and compare first, then explain")
        return await card_state(step, exp)

    # ----------------------------------------------------------------- guide
    def latest_finished_run(step: LoadedStep) -> tuple[str | None, list[dict[str, Any]]]:
        for r in store.runs_for_step(step.full_id, limit=5, since=since(step)):
            status, events = run_events_for(r["run_id"])
            if status == "finished":
                return r["run_id"], events
        return None, []

    async def facts_of(run_id: str, events: list[dict[str, Any]], with_tokens: bool) -> dict[str, Any]:
        prev = store.previous_run(run_id)
        tokens = None
        text = answer_text(events)
        if with_tokens and text:
            try:
                tokens = (await measure_text(run_facts(events)["request.model"] or DEFAULT_MODEL, text))["text_tokens"]
            except HTTPException:
                tokens = None
        return run_facts(events, run_events_for(prev["run_id"])[1] if prev else None, tokens)

    def guide_item_id(step: LoadedStep, guide_id: str, check_id: str) -> str:
        return f"{step.full_id}:{guide_id}:{check_id}"

    @app.get("/api/steps/{step_id}/guide")
    async def guide(step_id: str) -> dict[str, Any]:
        """The lesson, step by step: teaching, code lines, what to do, your latest run's values,
        and your answers to each step's checks so far."""
        step = get_step(step_id)
        run_id, events = latest_finished_run(step)
        wanted = {k for g in step.spec.guide for k in g.show}
        facts = await facts_of(run_id, events, bool(wanted & TOKEN_FACTS)) if run_id else {}
        latest = store.quiz_latest(step.full_id, since(step))
        out = []
        for g in step.spec.guide:
            answers = {}
            for c in g.check:
                last = latest.get(guide_item_id(step, g.id, c.id))
                if last:
                    answers[c.id] = {**last, "explanation": c.explanation}
            out.append({"id": g.id, "title": g.title, "teach_html": pages.markdown(g.teach),
                        "do_html": pages.markdown(g.do) if g.do else "", "lines": g.lines(),
                        "notice_html": pages.markdown(g.notice) if g.notice else "",
                        "show": [{"key": k, "label": FACTS[k], "value": facts.get(k)} for k in g.show],
                        "check": [c.public() for c in g.check], "answers": answers,
                        "experiment": g.experiment, "quiz": g.quiz})
        return {"steps": out, "run_id": run_id}

    @app.post("/api/steps/{step_id}/guide/{guide_id}/check")
    async def guide_check(step_id: str, guide_id: str, body: PredictionsIn) -> dict[str, Any]:
        """Grade answers to a step's checks, against fixed answers or your latest run. Recorded like
        quiz answers, so a miss comes back in spaced review."""
        step = get_step(step_id)
        g = step.spec.guide_step(guide_id)
        if g is None:
            raise HTTPException(404, f"step {step.full_id} has no guide step {guide_id!r}")
        items = [c for c in g.check if c.id in body.answers]
        if not items:
            raise HTTPException(400, "no answers for this step's checks")
        run_id, events = latest_finished_run(step)
        about_run = [c for c in items if getattr(c, "answer_from", None)]
        if about_run and run_id is None:
            raise HTTPException(409, "This question is about your run: press Run first.")
        wanted = {getattr(c, "answer_from", None) for c in items}
        facts = await facts_of(run_id, events, bool(wanted & TOKEN_FACTS)) if run_id else {}
        results = {}
        for c in items:
            try:
                answer = check_answer(c, body.answers[c.id])
            except ValueError as exc:
                raise HTTPException(400, str(exc))
            result = grade(c, answer, facts)
            if result["correct"] is not None:
                store.record_quiz_attempt(item_id=guide_item_id(step, g.id, c.id), module_id=step.module_id,
                                          type=c.type, answer=answer, correct=result["correct"], step_id=step.full_id,
                                          question=c.prompt, correct_answer=result["actual_display"],
                                          feedback=result["note"] or None, graded_by="auto", source="app")
            results[c.id] = {**result, "answer": answer, "explanation": c.explanation}
        return {"results": results, "run_id": run_id}

    def quiz_item_id(step: LoadedStep, item_id: str) -> str:
        return f"{step.full_id}:{item_id}"   # quiz ids are per step; the store's ids are global

    @app.get("/api/steps/{step_id}/quiz")
    def quiz(step_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        latest = store.quiz_latest(step.full_id, since(step))
        items = []
        for q in step.spec.quiz:
            last = latest.get(quiz_item_id(step, q.id))
            items.append({**q.public(), "last": {**last, "explanation": q.explanation} if last else None})
        return {"items": items}

    @app.post("/api/steps/{step_id}/quiz/{item_id}")
    def answer_quiz(step_id: str, item_id: str, body: QuizIn) -> dict[str, Any]:
        """Grade one answer and record it, the same as `labctl quiz record`."""
        step = get_step(step_id)
        q = step.spec.quiz_item(item_id)
        if q is None:
            raise HTTPException(404, f"step {step.full_id} has no quiz item {item_id!r}")
        try:
            correct, right = grade_quiz(q, body.answer)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        store.record_quiz_attempt(item_id=quiz_item_id(step, q.id), module_id=step.module_id, type=q.type,
                                  answer=body.answer, correct=correct, step_id=step.full_id, concepts=q.concepts,
                                  question=q.prompt, correct_answer=right, graded_by="auto", source="app")
        return {"correct": correct, "correct_answer": right, "explanation": q.explanation}

    # ----------------------------------------------------------------- tutor
    def guide_of(step: LoadedStep, guide_id: str) -> Any:
        g = step.spec.guide_step(guide_id)
        if g is None:
            raise HTTPException(404, f"step {step.full_id} has no guide step {guide_id!r}")
        return g

    def tutor_view(t: dict[str, Any]) -> dict[str, Any]:
        out = {"id": t["id"], "role": t["role"], "text": t["content"], "at": t["created_at"]}
        if t["role"] == "assistant":
            u = t.get("usage") or {}
            out.update(html=pages.markdown(t["content"]), cost_usd=t["cost_usd"], ms=t["ms"], model=t["model"],
                       usage={k: u.get(k) for k in ("input_tokens", "output_tokens",
                                                    "cache_creation_input_tokens", "cache_read_input_tokens")})
        return out

    @app.get("/api/steps/{step_id}/tutor/{guide_id}")
    def tutor_thread(step_id: str, guide_id: str) -> dict[str, Any]:
        step = get_step(step_id)
        guide_of(step, guide_id)
        return {"turns": [tutor_view(t) for t in store.tutor_thread(step.full_id, guide_id, since(step))],
                "model": tutor.MODEL, "effort": tutor.EFFORT, "gateway": settings.upstream is not None,
                "rules": str(tutor.rules_path(settings.playground_root))}

    @app.post("/api/steps/{step_id}/tutor/{guide_id}")
    async def ask_tutor(step_id: str, guide_id: str, body: TutorIn) -> dict[str, Any]:
        """One question to the tutor: a Sonnet 5.5 call grounded in this step, your code and your
        latest run. The question and answer are stored together; a failed call stores neither."""
        step = get_step(step_id)
        g = guide_of(step, guide_id)
        if settings.upstream is None:
            raise HTTPException(503, f"no gateway credentials: put them in {paths.credentials_path()} and restart")
        question = body.text.strip()
        if not question:
            raise HTTPException(400, "ask a question first")
        fresh = since(step)
        thread = store.tutor_thread(step.full_id, g.id, fresh)
        _dest, files = step_files(step)
        run_id, events = latest_finished_run(step)
        rec = store.run_record(run_id) if run_id else None
        changed = (store.run_code(run_id) != files) if run_id else None
        attempts = store.attempts(step.full_id, g.experiment, fresh) if g.experiment else None
        context = tutor.context_text(
            step, g, files, changed, tutor.run_text(run_id, events, rec.get("cost_usd") if rec else None),
            tutor.open_items(g, step.full_id, store.quiz_latest(step.full_id, fresh), [q.id for q in step.spec.quiz],
                             attempts))
        sent = tutor.user_content(None if context == tutor.last_context(thread) else context, question)
        request = tutor.build_request(tutor.load_rules(settings.playground_root), tutor.lesson_text(step), thread, sent)

        started = time.monotonic()
        try:
            raw = await tutor_client().messages.with_raw_response.create(**request)
            msg = await raw.parse()
        except anthropic.APIStatusError as exc:
            raise HTTPException(502, f"the tutor's call failed with {exc.status_code}: {error_message(exc.body)}")
        except anthropic.APIConnectionError as exc:
            raise HTTPException(502, f"the tutor couldn't reach the gateway: {exc}")
        ms = int((time.monotonic() - started) * 1000)
        usage = msg.usage.to_dict() if msg.usage else None
        cost = pricing.cost_usd(tutor.MODEL, usage) or 0.0
        if cost:
            store.record_spend("tutor", cost, model=tutor.MODEL, usage=usage)
        # Replayed exactly on later turns; drop nulls the API filled in, which aren't request fields.
        blocks = [{k: v for k, v in b.to_dict().items() if v is not None} for b in msg.content]
        text = tutor.answer_of(blocks)
        if msg.stop_reason == "refusal":
            raise HTTPException(422, "The tutor declined to answer that (stop_reason: refusal). Try rephrasing.")
        if not text:
            raise HTTPException(502, f"the tutor returned no text (stop_reason: {msg.stop_reason})")
        if msg.stop_reason == "max_tokens":
            text += "\n\n*(Cut off: the answer reached max_tokens.)*"
        turn_id = store.add_tutor_exchange(step.full_id, g.id, question=question, sent=sent, answer=text,
                                           blocks=blocks, request=request, usage=usage, model=tutor.MODEL,
                                           ms=ms, cost_usd=cost)
        return {"turn": tutor_view(store.tutor_turn(turn_id)), "call_id": raw.headers.get("x-litellm-call-id")}

    @app.get("/api/tutor/turns/{turn_id}")
    def tutor_request(turn_id: int) -> dict[str, Any]:
        """The exact request body behind one tutor answer, and its usage."""
        t = store.tutor_turn(turn_id)
        if t is None or t["role"] != "assistant":
            raise HTTPException(404, f"no tutor answer {turn_id}")
        return {"request": t["request"], "usage": t["usage"], "ms": t["ms"], "model": t["model"],
                "cost_usd": t["cost_usd"]}

    @app.post("/api/tools/count_tokens")
    async def tool_count_tokens(body: CountIn) -> dict[str, Any]:
        """The lab's free token counter: the text's own tokens, and the message wrapper around them."""
        if not MODEL_ID.match(body.model):
            raise HTTPException(400, f"not a model id: {body.model!r}")
        return {"model": body.model, **(await measure_text(body.model, body.text))}

    @app.get("/lab/{step_id}", include_in_schema=False, response_class=HTMLResponse)
    def lab(step_id: str, theme: str | None = None) -> str:
        step = get_step(step_id)
        store.open_step(step.full_id, step.module_id, step.spec.entry)
        return pages.lab_page(step, settings.playground_root / step.full_id / step.spec.entry,
                              gateway=settings.upstream is not None, theme=pages.theme_or_none(theme))

    # ------------------------------------------------------------ flash cards
    def get_deck(deck_id: str) -> Any:
        deck = content().decks.get(deck_id)
        if deck is None:
            raise HTTPException(404, f"unknown deck {deck_id!r}")
        return deck

    def card_item_id(deck_id: str, card_id: str) -> str:
        return f"{CARD_PREFIX}{deck_id}:{card_id}"

    @app.get("/api/cards")
    def cards() -> dict[str, Any]:
        """Every deck, every card with its answer (cards are for recall, not a test), and your last review."""
        out = []
        for deck in content().decks.values():
            latest = store.latest_with_prefix(card_item_id(deck.id, ""))
            out.append({"id": deck.id, "title": deck.title, "summary_html": pages.markdown(deck.summary),
                        "tags": deck.tags,
                        "cards": [{"id": c.id, "tag": c.tag, "front_html": pages.markdown(c.front),
                                   "back_html": pages.markdown(c.back), "source": c.source,
                                   "last": latest.get(card_item_id(deck.id, c.id))} for c in deck.cards]})
        return {"decks": out}

    @app.post("/api/cards/{deck_id}/{card_id}/review")
    def review_card(deck_id: str, card_id: str, body: CardReviewIn) -> dict[str, Any]:
        """Knew it, or didn't. Recorded like a quiz answer (self-graded), so a miss comes back in
        spaced review and in /today until you know it."""
        deck = get_deck(deck_id)
        card = deck.card(card_id)
        if card is None:
            raise HTTPException(404, f"deck {deck_id!r} has no card {card_id!r}")
        item = card_item_id(deck.id, card.id)
        store.record_quiz_attempt(item_id=item, module_id=CARD_MODULE, type="flashcard",
                                  answer="knew it" if body.knew else "didn't know", correct=body.knew,
                                  concepts=[card.tag], question=card.front, correct_answer=card.back,
                                  feedback=f"source: {card.source}", graded_by="self", source="app")
        return {"item_id": item, "last": store.latest_with_prefix(item).get(item)}

    @app.get("/cards", include_in_schema=False, response_class=HTMLResponse)
    def cards_page(theme: str | None = None) -> str:
        return pages.cards_page(theme=pages.theme_or_none(theme))

    @app.get("/meridian", include_in_schema=False, response_class=HTMLResponse)
    def meridian_page(theme: str | None = None) -> str:
        from .fixtures import load_seed   # the seed the mock API serves, read fresh each time
        return pages.meridian_page(load_seed(), theme=pages.theme_or_none(theme))

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
