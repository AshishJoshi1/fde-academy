"""The tutor behind "Ask the tutor" on every guide step: a small LLM app inside the lab.

Each question is one call to claude-sonnet-5-5 through the gateway. This server makes it with the
real key; lesson code never sees that key. The request is built in layers, most stable first,
because prompt caching reuses a prefix only while it is byte-for-byte identical:

1. system[0]: the tutor's rules, read from playground/tutor/rules.md (yours to edit).
2. system[1]: the whole lesson as authored: step.md, step.yaml (teaching, checks with their
   answers, experiments, quiz, tutor notes) and the numbered starter code.
   Cache breakpoint 1, kept for an hour: every thread of the lesson shares this prefix
   (about 10K tokens on s01), and questions are often more than 5 minutes apart.
3. messages: this guide step's thread. Each question carries a <lab_context> block (the step,
   which checks are still open, your code, your latest run, trimmed) unless nothing in it
   changed since the thread last sent one. Cache breakpoint 2 (the default 5 minutes) sits on
   the newest question, so a follow-up reads the whole thread so far from the cache.

History only grows: earlier turns are replayed exactly as they were sent and returned (thinking
blocks included) and never edited. Editing them would break the cache, and Sonnet 5.5 binds its
thinking blocks to the conversation that produced them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .content.loader import LoadedStep
from .content.schema import FACTS, GuideStep

MODEL = "claude-sonnet-5-5"
EFFORT = "low"              # Sonnet 5.5 defaults to high; low suits short tutoring replies
MAX_TOKENS = 4000
DEFAULT_RULES = Path(__file__).with_name("tutor_rules.md")
CONTEXT_TAG = "<lab_context"

BODY_CHARS = 4000           # per request or response body in the trimmed run
CONSOLE_CHARS = 4000        # the console's last lines
RUN_CHARS = 16000           # the whole trimmed run
_REQUEST_HEADERS = ("anthropic-", "x-stainless-")
_RESPONSE_HEADERS = ("x-litellm-call-id", "x-litellm-response-cost", "retry-after")


# ------------------------------------------------------------------ the stable prefix
def rules_path(playground_root: Path) -> Path:
    return playground_root / "tutor" / "rules.md"


def load_rules(playground_root: Path) -> str:
    """The tutor's rules. The first use copies the default into the playground; after that
    the file is the learner's, and nothing overwrites it."""
    path = rules_path(playground_root)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_RULES.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()


def numbered(code: str) -> str:
    return "\n".join(f"{n:>4}  {line}" for n, line in enumerate(code.split("\n"), start=1))


def lesson_text(step: LoadedStep) -> str:
    """The lesson exactly as authored. Built only from files that don't change while you work,
    so it is byte-identical on every call: the cacheable prefix."""
    spec_yaml = (step.dir / "step.yaml").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    starter = "\n\n".join(f"--- {name} ---\n{numbered(code.rstrip())}"
                          for name, code in sorted(step.starter_files().items()))
    facts = sorted({f for g in step.spec.guide for f in g.show}
                   | {v for v in _walk(spec_yaml) if v in FACTS})
    glossary = "\n".join(f"- {f}: {FACTS[f]}" for f in facts)
    return (f'<lesson id="{step.full_id}" title="{step.spec.title}">\n'
            f"<intro>\n{step.body_md.strip()}\n</intro>\n\n"
            f"<step_yaml>\n{spec_yaml}\n</step_yaml>\n\n"
            "<facts_measured_from_a_run>\n"
            f"Guide steps show these values from the learner's latest run; checks with answer_from are graded against them.\n{glossary}\n"
            "</facts_measured_from_a_run>\n\n"
            f"<starter_code>\nThe guide's line numbers refer to this starter code.\n{starter}\n</starter_code>\n"
            "</lesson>")


def _walk(text: str) -> set[str]:
    return {tok.strip("\"',[]") for tok in text.split()}


# ------------------------------------------------------------------ the volatile part
def _clip(text: str, limit: int, keep: str = "head") -> str:
    if len(text) <= limit:
        return text
    cut = len(text) - limit
    return (text[:limit] + f" [... {cut} chars cut]") if keep == "head" else (f"[{cut} chars cut ...] " + text[-limit:])


def _compact(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def run_text(run_id: str | None, events: list[dict[str, Any]], cost_usd: float | None = None) -> str:
    """The latest run, trimmed to what a tutor needs: outcome, console, each call's request and
    response bodies, usage and timing."""
    if not run_id:
        return "He hasn't run this step yet."
    lines: list[str] = []
    calls = [e for e in events if e["type"] == "llm.request"]
    end = next((e["data"] for e in reversed(events) if e["type"] == "run.exit"), {})
    head = f"Run {run_id}: {end.get('outcome', 'unknown')}, exit code {end.get('exit_code')}, {len(calls)} model call(s)"
    lines.append(head + (f", ${cost_usd:.6f}" if cost_usd else "") + ".")
    if end.get("error"):
        lines.append(f"Run error: {end['error']}")
    console = "\n".join(("[stderr] " if e["type"] == "console.err" else "") + e["data"].get("text", "")
                        for e in events if e["type"] in ("console.out", "console.err"))
    lines.append("Console:\n" + (_clip(console, CONSOLE_CHARS, keep="tail") if console else "(empty)"))
    for e in events:
        d = e["data"]
        if e["type"] == "llm.request":
            hdrs = {k: v for k, v in (d.get("headers") or {}).items() if k.startswith(_REQUEST_HEADERS)}
            lines.append(f"Call {d.get('call')} request: {d.get('method')} {d.get('path')}\n"
                         f"  headers: {_compact(hdrs)}\n  body: {_clip(_compact(d.get('body')), BODY_CHARS)}")
        elif e["type"] == "llm.response":
            hdrs = {k: v for k, v in (d.get("headers") or {}).items() if k.startswith(_RESPONSE_HEADERS)}
            lines.append(f"Call {d.get('call')} response: status {d.get('status')} in {d.get('ms')} ms"
                         f"{' (streamed)' if d.get('stream') else ''}, cost {d.get('cost_usd')}\n"
                         f"  headers: {_compact(hdrs)}\n  body: {_clip(_compact(d.get('body')), BODY_CHARS)}")
        elif e["type"] == "llm.error":
            lines.append(f"Call {d.get('call')} failed after {d.get('ms')} ms: {d.get('error')}")
    return _clip("\n".join(lines), RUN_CHARS)


def open_items(g: GuideStep, step_id: str, latest: dict[str, dict[str, Any]], quiz_ids: list[str],
               experiment: list[dict[str, Any]] | None) -> str:
    """Which of this guide step's checks, experiment predictions and quiz items are answered."""
    out = []
    for c in g.check:
        last = latest.get(f"{step_id}:{g.id}:{c.id}")
        out.append(f"- check {c.id}: " + ("not answered yet: don't reveal its answer" if not last else
                                          f"answered {'right' if last['correct'] else 'wrong'}, "
                                          f"his answer {_compact(last['answer'])}, {last['tries']} tries"))
    if g.experiment:
        att = (experiment or [None])[-1]
        if not att:
            out.append(f"- experiment {g.experiment}: predictions not committed yet: don't reveal what the run will show")
        else:
            preds = ", ".join(f"{p['item_id']}={_compact(p['answer'])}"
                              + ("" if p["correct"] is None else (" right" if p["correct"] else " wrong"))
                              for p in att["predictions"])
            state = "explained" if att.get("explained_at") else "graded" if att.get("graded_at") else "committed, not run yet"
            out.append(f"- experiment {g.experiment}, attempt {att['attempt']}: {state}; predictions {preds}")
    if g.quiz:
        for qid in quiz_ids:
            last = latest.get(f"{step_id}:{qid}")
            out.append(f"- quiz {qid}: " + ("not answered yet: don't reveal its answer" if not last else
                                            f"answered {'right' if last['correct'] else 'wrong'}"))
    return "\n".join(out) or "- nothing to answer on this step"


def context_text(step: LoadedStep, g: GuideStep, files: dict[str, str], changed_since_run: bool | None,
                 run: str, open_text: str) -> str:
    index = next(i for i, x in enumerate(step.spec.guide, start=1) if x.id == g.id)
    code = "\n\n".join(f"--- {name} ---\n{numbered(text.rstrip())}" for name, text in sorted(files.items()))
    since = ("" if changed_since_run is None else
             "\nHis code has changed since that run." if changed_since_run else "\nHis code is unchanged since that run.")
    return (f'{CONTEXT_TAG} guide_step="{g.id}">\n'
            f'He is on guide step {index} of {len(step.spec.guide)}: "{g.title}".\n'
            f"On this step:\n{open_text}\n\n"
            f"His code now:\n{code}\n\n"
            f"His latest run:{since}\n{run}\n"
            "</lab_context>")


def last_context(thread: list[dict[str, Any]]) -> str | None:
    """The newest <lab_context> this thread sent, to skip resending one that hasn't changed."""
    for turn in reversed(thread):
        if turn["role"] == "user":
            for block in turn.get("sent") or []:
                if isinstance(block, dict) and block.get("text", "").startswith(CONTEXT_TAG):
                    return block["text"]
    return None


def user_content(context: str | None, question: str) -> list[dict[str, Any]]:
    blocks = [{"type": "text", "text": context}] if context else []
    return blocks + [{"type": "text", "text": question if context else
                      f"(Lab context unchanged since my last question.)\n\n{question}"}]


# ------------------------------------------------------------------ the request
def build_request(rules: str, lesson: str, thread: list[dict[str, Any]], new_user: list[dict[str, Any]]) -> dict[str, Any]:
    """The exact request body. Earlier turns go back unchanged; only the newest question gets the
    second cache breakpoint (a breakpoint marks where to cache; it isn't part of the cached bytes)."""
    messages = [{"role": t["role"], "content": t["sent"]} for t in thread]
    newest = [dict(b) for b in new_user]
    newest[-1]["cache_control"] = {"type": "ephemeral"}
    messages.append({"role": "user", "content": newest})
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "output_config": {"effort": EFFORT},
        "system": [{"type": "text", "text": rules},
                   {"type": "text", "text": lesson, "cache_control": {"type": "ephemeral", "ttl": "1h"}}],
        "messages": messages,
    }


def answer_of(blocks: list[dict[str, Any]]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
