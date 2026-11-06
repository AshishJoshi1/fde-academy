"""Ashish's code for each step lives in playground/<step-id>/. Standard library only.

The first use of a step copies its starter files there. After that the files are his:
nothing overwrites them except an explicit reset.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterable


def prepare(starter: dict[str, str], dest: Path, reset: bool = False) -> list[str]:
    """Copy starter files into dest. Existing files are kept unless reset. Returns the files written."""
    if reset and dest.exists():
        shutil.rmtree(dest)
    written = []
    for name, text in starter.items():
        target = dest / name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        written.append(name)
    return written


def read_files(dest: Path, names: Iterable[str]) -> dict[str, str]:
    """The step's files as they are on disk now (a run snapshots exactly this)."""
    return {name: (dest / name).read_text(encoding="utf-8") for name in names if (dest / name).is_file()}
