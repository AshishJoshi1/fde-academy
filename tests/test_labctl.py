import json

from academy_server import labctl
from academy_server.store import Store


def test_status_before_db_exists(home, capsys):
    assert labctl.main(["status", "--brief"]) == 0
    assert "not created yet" in capsys.readouterr().out


def test_quiz_record_then_mistakes_and_retry(home, capsys):
    q = "What does is_error: true tell the model?"
    args = ["quiz", "record", "--module", "m02", "--question", q, "--answer", "nothing",
            "--correct-answer", "the tool failed; adapt", "--concept", "is_error"]
    assert labctl.main([*args, "--wrong"]) == 0
    assert labctl.main(["status", "--brief"]) == 0
    out = capsys.readouterr().out
    assert "1 still wrong" in out and "is_error" in out
    # Re-asking the same question (same stable item id) and getting it right moves it to "fixed after retry".
    assert labctl.main([*args[:7], "the tool failed; adapt", *args[8:], "--right"]) == 0
    m = Store(home / "academy.db").mistakes("m02")
    assert m["still_wrong"] == [] and len(m["fixed_after_retry"]) == 1


def test_export_import_cli_refuses_to_clobber(home, tmp_path, capsys):
    s = Store(home / "academy.db")
    s.record_quiz_attempt(item_id="q1", module_id="m02", type="mcq", answer=0, correct=False)
    s.close()
    out = tmp_path / "progress.json"
    assert labctl.main(["export", "--to", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["format"] == "fde-academy-progress" and len(data["tables"]["quiz_attempts"]) == 1
    assert labctl.main(["import", "--from", str(out)]) == 2           # DB not empty -> refuse
    assert labctl.main(["import", "--from", str(out), "--yes"]) == 0
    assert Store(home / "academy.db").status()["quiz"]["attempts"] == 1
