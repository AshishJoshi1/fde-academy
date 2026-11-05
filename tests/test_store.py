import sqlite3

from academy_server.store import Store
from academy_server.store.migrations import MIGRATIONS


def test_migrations_apply_once(store):
    assert store.schema_version == len(MIGRATIONS)
    store.migrate()  # idempotent
    assert store.schema_version == len(MIGRATIONS)
    with sqlite3.connect(store.path) as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_draft_autosave_dedupes_and_normalizes_crlf(store):
    assert store.save_draft("m02.lab02.s01", "m02", "main.py", "print(1)\r\n") is True
    assert store.save_draft("m02.lab02.s01", "m02", "main.py", "print(1)\n") is False  # same after CRLF fix
    assert store.latest_code("m02.lab02.s01", "main.py") == "print(1)\n"
    assert store.position()["step_id"] == "m02.lab02.s01"
    assert store.step_status()["m02.lab02.s01"] == "in_progress"


def test_drafts_are_pruned(store):
    from academy_server.store.db import DRAFTS_KEPT
    for i in range(DRAFTS_KEPT + 5):
        store.save_draft("s", "m", "main.py", f"v{i}")
    n = store._query("SELECT COUNT(*) AS n FROM code_snapshots WHERE kind = 'draft'")[0]["n"]
    assert n == DRAFTS_KEPT
    assert store.latest_code("s", "main.py") == f"v{DRAFTS_KEPT + 4}"


def test_reset_keeps_run_history(store):
    store.save_draft("s", "m", "main.py", "draft")
    store.record_run_start("r1", "s", "m", "replay", "claude-opus-5-5", {"main.py": "ran"})
    store.discard_drafts("s")
    assert store.latest_code("s", "main.py") == "ran"


def test_mistakes_still_wrong_vs_fixed_after_retry(store):
    rec = store.record_quiz_attempt
    rec(item_id="q-a", module_id="m02", type="mcq", answer=0, correct=False, concepts=["is_error"], question="A?")
    rec(item_id="q-b", module_id="m02", type="mcq", answer=2, correct=False, concepts=["stop-reason"])
    rec(item_id="q-b", module_id="m02", type="mcq", answer=1, correct=True, concepts=["stop-reason"])
    rec(item_id="q-c", module_id="m02", type="mcq", answer=1, correct=True)
    rec(item_id="q-z", module_id="m01", type="mcq", answer=1, correct=False)

    m = store.mistakes("m02")
    assert [r["item_id"] for r in m["still_wrong"]] == ["q-a"]
    assert m["still_wrong"][0]["answer"] == 0 and m["still_wrong"][0]["concepts"] == ["is_error"]
    assert [r["item_id"] for r in m["fixed_after_retry"]] == ["q-b"]
    assert m["fixed_after_retry"][0]["misses"] == 1 and m["fixed_after_retry"][0]["tries"] == 2
    assert m["by_concept"] == {"is_error": 1}
    assert {r["item_id"] for r in store.mistakes()["still_wrong"]} == {"q-a", "q-z"}


def test_failing_checks_use_latest_run_only(store):
    store.record_run_start("r1", "m02.lab02.s04", "m02", "replay", None, {})
    store.record_run_end("r1", "ok", 0.0, [{"check_id": "fixture_log", "passed": False, "message": "1 PATCH"}])
    assert len(store.mistakes("m02")["failing_checks"]) == 1
    store.record_run_start("r2", "m02.lab02.s04", "m02", "replay", None, {})
    store.record_run_end("r2", "ok", 0.0, [{"check_id": "fixture_log", "passed": True}])
    assert store.mistakes("m02")["failing_checks"] == []


def test_spend_summary(store):
    store.record_spend("run", 0.01, model="claude-opus-5-5", usage={"input_tokens": 10, "output_tokens": 5})
    store.record_spend("tutor", 0.002)
    s = store.spend_summary()
    assert s["today_usd"] == s["total_usd"] == 0.012
    assert s["by_source"] == {"run": 0.01, "tutor": 0.002}


def test_export_import_roundtrip(store, home):
    store.save_draft("m02.lab02.s01", "m02", "main.py", "x = 1  # Łódź\n")
    store.record_run_start("r1", "m02.lab02.s01", "m02", "replay", "claude-opus-5-5", {"main.py": "x"})
    store.record_run_end("r1", "ok", 0.003, [{"check_id": "llm_calls", "passed": True, "evidence": [3]}])
    store.record_quiz_attempt(item_id="q1", module_id="m02", type="mcq", answer=0, correct=False)
    store.record_spend("run", 0.003, run_id="r1")
    exported = store.export_all()

    fresh = Store(home / "other.db")
    assert fresh.is_empty()
    counts = fresh.import_all(exported)
    assert counts["quiz_attempts"] == 1 and counts["check_results"] == 1
    again = fresh.export_all()
    assert again["tables"] == exported["tables"]
    assert fresh.status()["quiz"]["still_wrong"] == 1
    assert fresh.latest_code("m02.lab02.s01", "main.py") == "x"   # run snapshot is newest
    fresh.close()


def test_import_rejects_foreign_or_newer(store):
    import pytest
    with pytest.raises(ValueError):
        store.import_all({"format": "something-else"})
    with pytest.raises(ValueError):
        store.import_all({"format": "fde-academy-progress", "schema_version": 999, "tables": {}})
