"""Schema for lesson YAML. Strict on purpose (extra="forbid"): a typo in a lesson
file should fail loudly with its path, not silently drop a check or a toggle.

Layout:
  content/<module-dir>/module.yaml          Module
  content/<module-dir>/<chapter-dir>/chapter.yaml   Chapter
  content/<module-dir>/<chapter-dir>/<step-dir>/step.yaml + step.md + starter/ solution/ cassettes/ quiz/
Full step id = "<module.id>.<chapter.id>.<step.id>", e.g. m02.lab02.s01.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, ClassVar, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=40)]

PanelName = Literal["console", "trace", "messages", "tokens", "flow", "fixture",
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
    mode: Literal["replay", "live", "python"] = "replay"
    step: Literal["off", "llm", "all"] = "off"
    cassettes: list[str] = Field(default_factory=list)
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
    HIDDEN: ClassVar[frozenset[str]] = frozenset({"answer", "answer_expr", "explanation", "model_answer", "rubric"})

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
    answer: float | None = None
    answer_expr: str | None = None   # evaluated against a recorded trace, e.g. cost(trace.llm[1])
    tol: float = Field(default=0.0, ge=0)
    unit: str = ""

    @model_validator(mode="after")
    def _one_answer(self) -> "Numeric":
        if (self.answer is None) == (self.answer_expr is None):
            raise ValueError("numeric item needs exactly one of 'answer' or 'answer_expr'")
        return self


class TraceReading(QuizBase):
    type: Literal["trace_reading"]
    trace: str = Field(description="cassette variant whose recorded trace is shown")
    answer: dict[str, Any] = Field(description="event selector, e.g. {type: llm.response, index: 2}")


class CodeFix(QuizBase):
    type: Literal["code_fix"]
    files: dict[str, str]
    tests: str


class ShortAnswer(QuizBase):
    type: Literal["short_answer"]
    rubric: list[RubricItem] = Field(min_length=1)
    model_answer: str


QuizItem = Annotated[Union[MCQ, Numeric, TraceReading, CodeFix, ShortAnswer], Field(discriminator="type")]

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
        ids = [q.id for q in self.quiz]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate quiz ids in {ids}")
        return self
