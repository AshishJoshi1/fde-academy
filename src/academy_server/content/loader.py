"""Load the content/ tree. A bad lesson is reported, never fatal: the server
still starts and /api/content/errors lists what to fix (file + reason)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .schema import Chapter, Module, Step


@dataclass
class LoadedStep:
    full_id: str
    module_id: str
    chapter_id: str
    spec: Step
    dir: Path
    body_md: str

    def _read(self, mapping: dict[str, str]) -> dict[str, str]:
        return {name: (self.dir / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
                for name, rel in mapping.items()}

    def starter_files(self) -> dict[str, str]:
        return self._read(self.spec.files)

    def solution_files(self) -> dict[str, str]:
        return self._read(self.spec.solution)

    def public(self) -> dict[str, Any]:
        """What the browser gets: no quiz answers, no solution (that's a separate, logged request)."""
        s = self.spec
        return {
            "id": self.full_id, "module_id": self.module_id, "chapter_id": self.chapter_id,
            "title": s.title, "body_md": self.body_md, "entry": s.entry, "files": sorted(s.files),
            "has_solution": bool(s.solution), "panels": s.panels, "run": s.run.model_dump(),
            "toggles": [t.model_dump() for t in s.toggles], "faults": s.faults,
            "checks": [{"id": c.check_id, "type": c.type, "severity": c.severity} for c in s.checks],
            "hints": s.hints, "experiments": [e.public() for e in s.experiments],
            "quiz": [q.public() for q in s.quiz],
        }


@dataclass
class LoadedChapter:
    id: str
    spec: Chapter
    steps: list[LoadedStep] = field(default_factory=list)


@dataclass
class LoadedModule:
    id: str
    spec: Module
    dir: Path
    chapters: list[LoadedChapter] = field(default_factory=list)


@dataclass
class ContentTree:
    root: Path
    modules: list[LoadedModule] = field(default_factory=list)
    steps: dict[str, LoadedStep] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def ordered_step_ids(self) -> list[str]:
        return [s.full_id for m in self.modules for c in m.chapters for s in c.steps]

    def outline(self, status: dict[str, str] | None = None) -> list[dict[str, Any]]:
        status = status or {}
        return [{
            "id": m.id, "title": m.spec.title, "summary": m.spec.summary, "elective": m.spec.elective,
            "chapters": [{
                "id": c.id, "title": c.spec.title,
                "steps": [{"id": s.full_id, "title": s.spec.title,
                           "status": status.get(s.full_id, "not_started")} for s in c.steps],
            } for c in m.chapters],
        } for m in self.modules]


def _yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _fmt(path: Path, root: Path, exc: Exception) -> str:
    rel = path.relative_to(root) if path.is_relative_to(root) else path
    if isinstance(exc, ValidationError):
        reasons = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}" for e in exc.errors())
        return f"{rel}: {reasons}"
    return f"{rel}: {type(exc).__name__}: {exc}"


def load_content(root: Path) -> ContentTree:
    root = Path(root)
    tree = ContentTree(root=root)
    if not root.is_dir():
        tree.errors.append(f"{root}: content directory not found")
        return tree
    modules: list[LoadedModule] = []
    for mdir in sorted(p for p in root.iterdir() if (p / "module.yaml").is_file()):
        mfile = mdir / "module.yaml"
        try:
            mspec = Module.model_validate(_yaml(mfile))
        except (ValidationError, yaml.YAMLError, OSError) as exc:
            tree.errors.append(_fmt(mfile, root, exc))
            continue
        module = LoadedModule(id=mspec.id, spec=mspec, dir=mdir)
        for cname in mspec.chapters:
            cfile = mdir / cname / "chapter.yaml"
            try:
                cspec = Chapter.model_validate(_yaml(cfile))
            except (ValidationError, yaml.YAMLError, OSError) as exc:
                tree.errors.append(_fmt(cfile, root, exc))
                continue
            chapter = LoadedChapter(id=cspec.id, spec=cspec)
            for sname in cspec.steps:
                step = _load_step(tree, mspec.id, cspec.id, mdir / cname / sname)
                if step:
                    chapter.steps.append(step)
            module.chapters.append(chapter)
        modules.append(module)
    tree.modules = sorted(modules, key=lambda m: (m.spec.order, m.id))
    seen: dict[str, str] = {}
    for m in tree.modules:
        if m.id in seen:
            tree.errors.append(f"duplicate module id {m.id!r} in {seen[m.id]} and {m.dir.name}")
        seen[m.id] = m.dir.name
    return tree


def _load_step(tree: ContentTree, module_id: str, chapter_id: str, sdir: Path) -> LoadedStep | None:
    sfile = sdir / "step.yaml"
    try:
        spec = Step.model_validate(_yaml(sfile))
    except (ValidationError, yaml.YAMLError, OSError) as exc:
        tree.errors.append(_fmt(sfile, tree.root, exc))
        return None
    missing = [rel for rel in [*spec.files.values(), *spec.solution.values()] if not (sdir / rel).is_file()]
    for q in spec.quiz:
        if q.type == "code_fix":
            missing += [rel for rel in [*q.files.values(), q.tests] if not (sdir / rel).is_file()]
    if missing:
        tree.errors.append(f"{sfile.relative_to(tree.root)}: missing file(s) {missing}")
        return None
    md = sdir / "step.md"
    body = md.read_text(encoding="utf-8") if md.is_file() else ""
    full_id = f"{module_id}.{chapter_id}.{spec.id}"
    if full_id in tree.steps:
        tree.errors.append(f"{sfile.relative_to(tree.root)}: duplicate step id {full_id}")
        return None
    step = LoadedStep(full_id=full_id, module_id=module_id, chapter_id=chapter_id,
                      spec=spec, dir=sdir, body_md=body)
    tree.steps[full_id] = step
    return step
