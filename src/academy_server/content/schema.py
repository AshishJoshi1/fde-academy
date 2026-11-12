"""Schema for lesson YAML. Strict on purpose (extra="forbid"): a typo in a lesson
file should fail loudly with its path, not silently drop a check or a toggle.

Layout:
  content/<module-dir>/module.yaml          Module
  content/<module-dir>/<chapter-dir>/chapter.yaml   Chapter
  content/<module-dir>/<chapter-dir>/<step-dir>/step.yaml + step.md + starter/ solution/
Full step id = "<module.id>.<chapter.id>.<step.id>", e.g. m02.lab02.s01.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=40)]

PanelName = Literal["console", "timeline", "trace", "messages", "tokens", "flow", "fixture",
                    "why", "variables", "compare"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Module(Strict):
    id: ID
    title: str
    summary: str = ""
    order: int = 100
    elective: bool = False
    chapters: list[str] = Field(min_length=1, description="chapter directory names, in order")


class Chapter(Strict):
    id: ID
    title: str
    summary: str = ""
    steps: list[str] = Field(min_length=1, description="step directory names, in order")


class RunSpec(Strict):
    fixture: Literal["meridian"] | None = None
    timeout_s: int = Field(default=120, ge=5, le=600)


class Toggle(Strict):
    """A lab control that edits a work file, e.g. add 'update_opportunity' to policy.json deny."""
    id: ID
    label: str
    file: str
    path: str = Field(description="dotted key path inside the JSON file, e.g. 'deny'")
    value: Any
    kind: Literal["list_add", "set"] = "list_add"


class Check(BaseModel):
    """A named check from the registry plus its parameters (validated by the registry)."""
    model_config = ConfigDict(extra="allow")
    type: str
    id: str | None = None
    severity: Literal["hard", "soft"] = "hard"

    @property
    def check_id(self) -> str:
        return self.id or self.type


class RubricItem(Strict):
    pts: int = Field(ge=1)
    crit: str


class QuizBase(Strict):
    id: ID
    prompt: str
    concepts: list[str] = Field(default_factory=list)
    points: int = Field(default=1, ge=1)
    explanation: str = ""

    # Fields never sent to the browser before the learner answers.
    HIDDEN: ClassVar[frozenset[str]] = frozenset({"answer", "explanation", "model_answer", "rubric"})

    def public(self) -> dict[str, Any]:
        return self.model_dump(exclude=set(self.HIDDEN))


class MCQ(QuizBase):
    type: Literal["mcq"]
    options: list[str] = Field(min_length=2)
    answer: int | list[int]

    @model_validator(mode="after")
    def _answer_in_range(self) -> "MCQ":
        answers = self.answer if isinstance(self.answer, list) else [self.answer]
        bad = [a for a in answers if not 0 <= a < len(self.options)]
        if bad:
            raise ValueError(f"answer index {bad} out of range for {len(self.options)} options")
        return self


class Numeric(QuizBase):
    type: Literal["numeric"]
    answer: float
    tol: float = Field(default=0.0, ge=0)
    unit: str = ""


class CodeFix(QuizBase):
    type: Literal["code_fix"]
    files: dict[str, str]
    tests: str


class ShortAnswer(QuizBase):
    type: Literal["short_answer"]
    rubric: list[RubricItem] = Field(min_length=1)
    model_answer: str


QuizItem = Annotated[Union[MCQ, Numeric, CodeFix, ShortAnswer], Field(discriminator="type")]

# ------------------------------------------------------------- experiments
# What a prediction can be graded against: one value measured from a run
# (academy_server.experiments.run_facts builds exactly these keys).
FACTS: dict[str, str] = {
    "run.outcome": "ok | error | timeout | stopped",
    "run.calls": "model calls the relay saw",
    "run.first_call_ms": "ms from process start to the first model call reaching the relay",
    "run.model": "the model picked for the run (LAB_MODEL)",
    "run.cost_usd": "the relay's cost of every call in the run, added up",
    "run.input_tokens": "usage.input_tokens of every call in the run, added up",
    "request.model": "model in the last request body",
    "request.max_tokens": "max_tokens in the last request body",
    "request.effort": "output_config.effort in the last request body, or 'not set'",
    "request.retry_count": "the SDK's x-stainless-retry-count header on the last request",
    "request.tool_names": "the tools defined in the last request, by name",
    "request.messages": "how many messages the last request sent",
    "request.last_message": "role and block types of the last request's last message, e.g. 'user: tool_result'",
    "request.history_grows": "whether each call's messages start with the previous call's messages, unchanged",
    "response.status": "HTTP status of the last call",
    "response.error_message": "the error message of a failed call (the gateway's wrapper unwrapped)",
    "response.stop_reason": "stop_reason of the last response",
    "response.blocks": "content block types in order, e.g. 'thinking, text'",
    "response.has_thinking": "whether a thinking block came back",
    "response.thinking_text": "'none' (no thinking block), 'empty' or 'readable'",
    "response.has_text": "whether any text block has text in it",
    "response.text_chars": "characters in the text blocks",
    "response.text_tokens": "tokens in the text blocks, measured with count_tokens",
    "response.hidden_output_tokens": "usage.output_tokens minus response.text_tokens",
    "response.usage.input_tokens": "usage.input_tokens of the last call",
    "response.usage.output_tokens": "usage.output_tokens of the last call",
    "response.usage.cache_creation_input_tokens": "usage.cache_creation_input_tokens of the last call",
    "response.usage.cache_read_input_tokens": "usage.cache_read_input_tokens of the last call",
    "response.cost_usd": "the relay's cost of the last call: usage x pricing.yaml",
    "response.gateway_cost_usd": "the gateway's x-litellm-response-cost-original header",
    "response.cost_matches_gateway": "whether those two costs agree (to 0.1%)",
    "response.ms": "how long the call took, in ms",
    "first.response.stop_reason": "stop_reason of the run's first call",
    "first.response.blocks": "content block types of the first call's response",
    "first.response.tool_name": "name of the first tool_use block in the first response",
    "first.response.tool_input": "input of that tool_use block, as JSON",
    "first.response.tool_uses": "how many tool_use blocks the first response holds",
    "first.response.tool_inputs": "the inputs of the first response's tool_use blocks, in order, as JSON",
    "first.response.usage.input_tokens": "usage.input_tokens of the first call",
    "loop.input_growth": "the last call's input_tokens minus the first call's",
    "loop.input_ratio": "the last call's input_tokens divided by the first call's",
    "loop.tool_results": "tool_result blocks in the last request's messages",
    "loop.error_results": "of those, how many carry is_error: true",
    "loop.results_in_one_message": "whether each assistant turn's tool_use blocks are all answered in the one user message right after it",
    "loop.blocked_results": "of the tool_results sent, how many your gate refused (content starts with BLOCKED)",
    "loop.denied_results": "of the tool_results sent, how many a person denied (content starts with DENIED)",
    "request.helper": "the x-stainless-helper header of the last request: BetaToolRunner when the SDK's tool runner made it, else not set",
    "request.beta": "the anthropic-beta header of the last request (a beta feature the SDK switched on), else not set",
    "request.strict": "whether every tool in the last request has strict: true (on, every tool) or not (off)",
    "fuzz.tool_uses": "tool_use blocks the model wrote across all the run's calls",
    "fuzz.invalid": "of those, how many break their tool's input_schema (type, required, additionalProperties, enum), checked by the lab",
    "fuzz.no_tool": "calls whose answer holds no tool_use block (the model refused or asked a question)",
    "approval.asked": "how many times your code paused to ask for Approve or Deny (labkit.approve)",
    "approval.approved": "of those, how many you approved",
    "approval.denied": "of those, how many were denied, timed out or cut off by the run ending",
    "api.requests": "requests your code made to the step's mock API",
    "api.writes": "requests your code made to the mock API that change data (any method but GET)",
    "api.last_request": "the last of those requests, with the status it got",
    "prev.response.usage.output_tokens": "usage.output_tokens of your previous run of this step",
    "ratio.output_tokens": "this run's output_tokens divided by the previous run's",
    "prev.run.input_tokens": "run.input_tokens of your previous run of this step",
    "ratio.input_tokens": "this run's run.input_tokens divided by the previous run's",
}
FactPath = Annotated[str, Field(description="a key of FACTS, e.g. response.usage.output_tokens")]


def _known_fact(path: str | None) -> None:
    if path is not None and path not in FACTS:
        raise ValueError(f"unknown fact {path!r}; known facts: {', '.join(FACTS)}")


class Option(Strict):
    """An answer choice whose label differs from the measured value it stands for."""
    label: str
    value: str | int | float | bool


class PredictBase(Strict):
    id: ID
    prompt: str
    hint: str = ""
    explanation: str = Field(default="", description="the why, shown once answered (guide checks)")

    HIDDEN: ClassVar[frozenset[str]] = frozenset({"answer", "explanation"})

    def public(self) -> dict[str, Any]:
        return self.model_dump(exclude=set(self.HIDDEN))


class PredictMCQ(PredictBase):
    """Graded against a fixed option (answer) or a measured value (answer_from).

    With answer_from the value picks the option whose value (or label) equals it; booleans
    match "yes"/"no". With bins, a number picks an option by range: option i covers
    bins[i-1] <= value < bins[i].
    """
    type: Literal["mcq"]
    options: list[str | Option] = Field(min_length=2)
    answer: int | None = None
    answer_from: FactPath | None = None
    bins: list[float] | None = None

    @model_validator(mode="after")
    def _check(self) -> "PredictMCQ":
        if (self.answer is None) == (self.answer_from is None):
            raise ValueError("an mcq prediction needs exactly one of 'answer' or 'answer_from'")
        _known_fact(self.answer_from)
        if self.answer is not None and not 0 <= self.answer < len(self.options):
            raise ValueError(f"answer index {self.answer} out of range for {len(self.options)} options")
        if self.bins is not None:
            if self.answer_from is None:
                raise ValueError("'bins' only works with 'answer_from'")
            if len(self.bins) != len(self.options) - 1 or self.bins != sorted(self.bins):
                raise ValueError("'bins' must be ascending, with one fewer entry than 'options'")
        return self


class PredictNumeric(PredictBase):
    """Right when within the tolerance: tol (absolute), tol_pct (percent of the actual
    value) or tol_factor (within a factor of the actual value, for orders of magnitude)."""
    type: Literal["numeric"]
    answer: float | None = None
    answer_from: FactPath | None = None
    tol: float | None = Field(default=None, ge=0)
    tol_pct: float | None = Field(default=None, gt=0)
    tol_factor: float | None = Field(default=None, gt=1)
    unit: str = ""

    @model_validator(mode="after")
    def _check(self) -> "PredictNumeric":
        if (self.answer is None) == (self.answer_from is None):
            raise ValueError("a numeric prediction needs exactly one of 'answer' or 'answer_from'")
        _known_fact(self.answer_from)
        if sum(t is not None for t in (self.tol, self.tol_pct, self.tol_factor)) > 1:
            raise ValueError("use at most one of 'tol', 'tol_pct' and 'tol_factor'")
        return self


class PredictText(PredictBase):
    """Your own words. Not auto-graded; show_from puts the measured value beside them."""
    type: Literal["text"]
    show_from: FactPath | None = None

    @model_validator(mode="after")
    def _check(self) -> "PredictText":
        _known_fact(self.show_from)
        return self


Prediction = Annotated[Union[PredictMCQ, PredictNumeric, PredictText], Field(discriminator="type")]
ToolName = Literal["count_tokens"]


class Experiment(Strict):
    """One card: predict, change one thing, run, compare, explain."""
    id: ID
    title: str
    question: str = Field(description="what the card investigates")
    predict: list[Prediction] = Field(min_length=1)
    change: str = Field(description="exactly what to edit before the run")
    observe: list[str] = Field(default_factory=list, description="where to look after the run")
    tools: list[ToolName] = Field(default_factory=list)
    explain: str = Field(description="the authored explanation, shown after the learner's own")

    HIDDEN: ClassVar[frozenset[str]] = frozenset({"explain"})

    def public(self) -> dict[str, Any]:
        out = self.model_dump(exclude=set(self.HIDDEN) | {"predict"})
        out["predict"] = [p.public() for p in self.predict]
        return out

    @model_validator(mode="after")
    def _unique_ids(self) -> "Experiment":
        ids = [p.id for p in self.predict]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate prediction ids in {ids}")
        return self


_LINES = re.compile(r"^(\d+)(?:-(\d+))?$")


class GuideStep(Strict):
    """One step of a lesson walkthrough, taught the way a tutor would: explain one idea and
    point at the code, have the learner do something in the lab, show what their own run
    measured and what to notice in it, then check understanding (or run an experiment)."""
    id: ID
    title: str
    teach: str = Field(description="markdown: the idea, taught before anything is asked")
    code: list[int | str] = Field(default_factory=list, description="entry-file lines to highlight: 8 or '8-13'")
    do: str = Field(default="", description="what to do in the lab, e.g. 'Press Run.'")
    show: list[FactPath] = Field(default_factory=list, description="values from your latest run, shown after it")
    notice: str = Field(default="", description="markdown: what to notice in your run")
    check: list[Prediction] = Field(default_factory=list, description="questions about what you just saw")
    experiment: ID | None = Field(default=None, description="an experiments: card, done inside this step")
    quiz: bool = Field(default=False, description="this step holds the step's quiz")

    @model_validator(mode="after")
    def _check(self) -> "GuideStep":
        for fact in self.show:
            _known_fact(fact)
        self.lines()
        ids = [c.id for c in self.check]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate check ids in {ids}")
        return self

    def lines(self) -> list[int]:
        out: list[int] = []
        for spec in self.code:
            m = _LINES.match(str(spec))
            if not m or (m.group(2) and int(m.group(2)) < int(m.group(1))):
                raise ValueError(f"bad code line {spec!r}; use a number like 8 or a range like '8-13'")
            out += range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1)
        return out


_FAULT = re.compile(r"^(relay|fixture)\.[a-z0-9_]+(:\S+)?$")


class Step(Strict):
    id: ID
    title: str
    files: dict[str, str] = Field(min_length=1, description="work filename -> path relative to the step dir")
    solution: dict[str, str] = Field(default_factory=dict)
    entry: str = "main.py"
    panels: list[PanelName] = Field(default_factory=lambda: ["console"])
    run: RunSpec = Field(default_factory=RunSpec)
    toggles: list[Toggle] = Field(default_factory=list)
    faults: list[str] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    guide: list[GuideStep] = Field(default_factory=list, description="the lesson, step by step")
    experiments: list[Experiment] = Field(default_factory=list)
    quiz: list[QuizItem] = Field(default_factory=list)
    story: list[str] = Field(default_factory=list, description="optional prose for the Why? chain")
    tutor_notes: str = ""

    @field_validator("faults")
    @classmethod
    def _fault_names(cls, v: list[str]) -> list[str]:
        bad = [f for f in v if not _FAULT.match(f)]
        if bad:
            raise ValueError(f"bad fault name(s) {bad}; expected relay.<name> or fixture.<name>[:arg]")
        return v

    @model_validator(mode="after")
    def _entry_is_a_file(self) -> "Step":
        if self.entry not in self.files:
            raise ValueError(f"entry {self.entry!r} is not one of files {sorted(self.files)}")
        for kind, ids in (("quiz", [q.id for q in self.quiz]), ("experiment", [e.id for e in self.experiments]),
                          ("guide step", [g.id for g in self.guide])):
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {kind} ids in {ids}")
        known = {e.id for e in self.experiments}
        missing = [g.experiment for g in self.guide if g.experiment and g.experiment not in known]
        if missing:
            raise ValueError(f"guide steps name unknown experiments {missing}")
        return self

    def guide_step(self, step_id: str) -> GuideStep | None:
        return next((g for g in self.guide if g.id == step_id), None)

    def experiment(self, experiment_id: str) -> Experiment | None:
        return next((e for e in self.experiments if e.id == experiment_id), None)

    def quiz_item(self, item_id: str) -> Any:
        return next((q for q in self.quiz if q.id == item_id), None)


# ------------------------------------------------------------------ flash cards
# content/cards/<deck>.yaml: one deck per file. A card's "Didn't know" is recorded like a quiz miss
# (item id cards:<deck>:<card>), so it comes back in spaced review and in /today.
class FlashCard(Strict):
    id: ID
    tag: ID
    front: str = Field(min_length=1, description="the question, markdown")
    back: str = Field(min_length=1, description="the answer with its why, markdown")
    source: str = Field(min_length=1, description="where the fact is recorded: a file, a section or a log")


class Deck(Strict):
    id: ID
    title: str
    summary: str = ""
    tags: dict[str, str] = Field(min_length=1, description="tag id -> label, in display order")
    cards: list[FlashCard] = Field(min_length=1)

    @model_validator(mode="after")
    def _ids_and_tags(self) -> "Deck":
        ids = [c.id for c in self.cards]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate card ids {dupes}")
        unknown = sorted({c.tag for c in self.cards if c.tag not in self.tags})
        if unknown:
            raise ValueError(f"cards use tags {unknown} that aren't in tags {sorted(self.tags)}")
        return self

    def card(self, card_id: str) -> FlashCard | None:
        return next((c for c in self.cards if c.id == card_id), None)


# --------------------------------------------------------------------- glossary
# content/glossary.yaml: the commands that run the course and the lab (/glossary), each with the file
# that defines it, so an entry can be checked against its source.
class GlossaryEntry(Strict):
    term: str = Field(min_length=1, description="the command as typed, e.g. /today or labctl status")
    what: str = Field(min_length=1, description="markdown: what it does")
    when: str = Field(default="", description="markdown: when to use it")
    source: str = Field(min_length=1, description="where it's defined: a file or a section")


class GlossarySection(Strict):
    id: ID
    title: str
    summary: str = Field(default="", description="markdown")
    entries: list[GlossaryEntry] = Field(min_length=1)


class Glossary(Strict):
    title: str
    summary: str = Field(default="", description="markdown")
    sections: list[GlossarySection] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "Glossary":
        for what, keys in (("section ids", [s.id for s in self.sections]),
                           ("terms", [e.term for s in self.sections for e in s.entries])):
            dupes = sorted({k for k in keys if keys.count(k) > 1})
            if dupes:
                raise ValueError(f"duplicate {what} {dupes}")
        return self
