import os
from pathlib import Path

import anthropic
from anthropic.lib.tools import BetaAbstractMemoryTool, ToolError

client = anthropic.Anthropic()  # in the lab, the key and URL are injected for you (relay)
MODEL = os.getenv("LAB_MODEL", "claude-opus-5-5")

PHASE = "ask"         # g1: "ask" questions a fresh conversation. g4: "tell" saves a fact. g5: "ask" again
USE_MEMORY = False    # g4: True gives the model the memory tool
GUARD = True          # g6: False removes the path check
SELF_TEST = False     # g6: your code tries to write outside /memories, no model involved

ROOT = Path("memories").resolve()   # the folder behind /memories. The run's folder is the step's playground folder
ROOT.mkdir(exist_ok=True)

TELL = "Acme (ACC-001) told us today: their contracts must use UK law and their invoices must be in GBP. Note it for next time. Reply in one line."
ASK = "I'm drafting the Acme contract. Which law must it use, and which currency do I invoice in? If you don't know, say so."
SYSTEM = "You help a consultant with Meridian CRM accounts. Keep answers short."


class Memory(BetaAbstractMemoryTool):
    """The six commands the model can send. The model names a path; YOUR code decides what happens to the disk."""

    def path(self, p):
        if not p.startswith("/memories"):
            raise ToolError(f"Path must start with /memories, got: {p}")
        full = ROOT / p[len("/memories"):].lstrip("/")
        if GUARD and ROOT not in [full.resolve(), *full.resolve().parents]:
            raise ToolError(f"Path {p} would escape /memories")
        return full

    def view(self, c):
        full = self.path(c.path)
        if not full.exists():
            raise ToolError(f"The path {c.path} does not exist.")
        if full.is_dir():
            rows = [f"{f.stat().st_size}\t/memories/{f.relative_to(ROOT).as_posix()}" for f in sorted(full.rglob("*")) if f.is_file()]
            return f"Files under {c.path}:\n" + ("\n".join(rows) or "(empty)")
        lines = full.read_text(encoding="utf-8").split("\n")
        return f"Content of {c.path}:\n" + "\n".join(f"{i}\t{line}" for i, line in enumerate(lines, 1))

    def create(self, c):
        full = self.path(c.path)
        if full.exists():
            raise ToolError(f"File {c.path} already exists. Use str_replace or insert to change it.")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(c.file_text, encoding="utf-8")
        return f"File created at {c.path}"

    def str_replace(self, c):
        full = self.path(c.path)
        text = full.read_text(encoding="utf-8")
        if text.count(c.old_str) != 1:
            raise ToolError(f"old_str must appear exactly once in {c.path}; it appears {text.count(c.old_str)} times.")
        full.write_text(text.replace(c.old_str, c.new_str), encoding="utf-8")
        return f"Replaced in {c.path}"

    def insert(self, c):
        full = self.path(c.path)
        lines = full.read_text(encoding="utf-8").split("\n")
        lines.insert(c.insert_line, c.insert_text)
        full.write_text("\n".join(lines), encoding="utf-8")
        return f"Inserted into {c.path}"

    def delete(self, c):
        self.path(c.path).unlink()
        return f"Deleted {c.path}"

    def rename(self, c):
        self.path(c.old_path).rename(self.path(c.new_path))
        return f"Renamed {c.old_path} to {c.new_path}"


if SELF_TEST:  # no model: what does YOUR handler do with a path that climbs out of /memories?
    outside = ROOT.parent / "escape.txt"
    try:
        Memory().call({"command": "create", "path": "/memories/../escape.txt", "file_text": "planted"})
        print(f"WROTE OUTSIDE the memory folder: {outside} exists = {outside.exists()}")
        outside.unlink(missing_ok=True)
    except ToolError as err:
        print(f"BLOCKED: {err}")
    raise SystemExit

ask = dict(model=MODEL, max_tokens=1024, output_config={"effort": "low"}, system=SYSTEM,
           messages=[{"role": "user", "content": TELL if PHASE == "tell" else ASK}])
if USE_MEMORY:
    runner = client.beta.messages.tool_runner(**ask, tools=[Memory()], max_iterations=8, thread=False)
    for final in runner:  # the runner runs each memory command your class handles, then calls again
        pass
else:
    final = client.messages.create(**ask)

print("ANSWER:", "".join(b.text for b in final.content if b.type == "text"))
print("MEMORY FILES:", [f.relative_to(ROOT).as_posix() for f in ROOT.rglob("*") if f.is_file()] or "(none)")
