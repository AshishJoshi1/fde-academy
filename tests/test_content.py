import shutil
from pathlib import Path

from academy_server.content.loader import load_content
from conftest import REPO


def test_repo_content_loads_cleanly():
    tree = load_content(REPO / "content")
    assert tree.errors == []
    assert "m02.lab02.s01" in tree.steps
    step = tree.steps["m02.lab02.s01"]
    assert "client.messages.create" in step.starter_files()["main.py"]


def test_public_step_hides_quiz_answers():
    step = load_content(REPO / "content").steps["m02.lab02.s01"]
    pub = step.public()
    for q in pub["quiz"]:
        assert "answer" not in q and "explanation" not in q
    assert "solution" not in pub and pub["has_solution"] is True


def _copy_content(tmp_path: Path) -> Path:
    dst = tmp_path / "content"
    shutil.copytree(REPO / "content", dst)
    return dst


def test_typo_in_step_yaml_is_reported_not_fatal(tmp_path):
    root = _copy_content(tmp_path)
    step_yaml = root / "m02-agent-loop/lab02-agent-loop/s01-one-call/step.yaml"
    step_yaml.write_text(step_yaml.read_text(encoding="utf-8").replace("hints:", "hintz:"), encoding="utf-8")
    tree = load_content(root)
    assert "m02.lab02.s01" not in tree.steps
    assert any("step.yaml" in e and "hintz" in e for e in tree.errors), tree.errors


def test_mcq_answer_out_of_range_is_rejected(tmp_path):
    root = _copy_content(tmp_path)
    step_yaml = root / "m02-agent-loop/lab02-agent-loop/s01-one-call/step.yaml"
    text = step_yaml.read_text(encoding="utf-8").replace("    answer: 1\n    concepts: [stop-reason]",
                                                         "    answer: 7\n    concepts: [stop-reason]")
    step_yaml.write_text(text, encoding="utf-8")
    tree = load_content(root)
    assert any("out of range" in e for e in tree.errors), tree.errors


def test_missing_starter_file_is_reported(tmp_path):
    root = _copy_content(tmp_path)
    (root / "m02-agent-loop/lab02-agent-loop/s01-one-call/starter/main.py").unlink()
    tree = load_content(root)
    assert any("missing file" in e for e in tree.errors)


def test_api_step_roundtrip_and_continue(make_client):
    c = make_client()
    assert c.get("/api/continue").json() == {"step_id": "m02.lab02.s01", "resumed": False}
    detail = c.get("/api/steps/m02.lab02.s01").json()
    assert detail["title"].startswith("One call") and "answer" not in detail["quiz"][0]
    assert c.put("/api/steps/m02.lab02.s01/files/main.py", json={"code": "# mine\n"}).json()["saved"] is True
    assert c.get("/api/steps/m02.lab02.s01").json()["code"]["main.py"] == "# mine\n"
    resume = c.get("/api/continue").json()
    assert resume["resumed"] is True and resume["step_id"] == "m02.lab02.s01"
    starter = c.post("/api/steps/m02.lab02.s01/reset").json()["files"]["main.py"]["code"]
    assert c.get("/api/steps/m02.lab02.s01").json()["code"]["main.py"] == starter
    assert c.get("/api/steps/nope").status_code == 404


def test_saved_code_survives_server_restart(make_client):
    """Continuity: kill the server, start a new one, the code saved from the editor is still there."""
    first = make_client()
    first.put("/api/steps/m02.lab02.s01/files/main.py", json={"code": "# survives\n"})
    first.__exit__(None, None, None)
    second = make_client()
    assert second.get("/api/continue").json()["resumed"] is True
    assert second.get("/api/steps/m02.lab02.s01").json()["code"]["main.py"] == "# survives\n"


def test_placeholder_home_page(make_client):
    r = make_client().get("/")
    assert r.status_code == 200 and "FDE Academy" in r.text and "m02.lab02.s01" in r.text


def _leaf_commands(parser, prefix: str = "") -> list[str]:
    """Every runnable labctl command, e.g. 'status', 'quiz record', 'content validate'."""
    import argparse
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        return [prefix.strip()]
    return [c for name, p in subs[0].choices.items() for c in _leaf_commands(p, f"{prefix}{name} ")]


def test_the_glossary_covers_every_slash_command_and_labctl_command(make_client):
    from academy_server.labctl import build_parser
    glossary = load_content(REPO / "content").glossary
    terms = {e.term.split(" <")[0] for s in glossary.sections for e in s.entries}
    for cmd in sorted((REPO / ".claude" / "commands").glob("*.md")):
        assert f"/{cmd.stem}" in terms, f"/{cmd.stem} has no glossary entry"
    for leaf in _leaf_commands(build_parser()):
        assert f"labctl {leaf}" in terms, f"labctl {leaf} has no glossary entry"
    for tool in sorted((REPO / "tools").glob("*.py")):
        if tool.stem != "labctl":                              # labctl's commands are listed one by one
            assert any(t.startswith(f"tools/{tool.name}") for t in terms), f"tools/{tool.name} has no glossary entry"

    page = make_client().get("/glossary")
    assert page.status_code == 200
    assert '<a href="/glossary" aria-current="page">Glossary</a>' in page.text      # in the top bar, current
    assert '<code id="today">/today</code>' in page.text and "Defined in .claude/commands/wrap.md" in page.text
    assert "&lt;step-id&gt;" in page.text and "<step-id>" not in page.text          # every term escaped
