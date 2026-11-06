"""Shared run plumbing: credentials parsing, playground copies, and run_live's child environment."""
import importlib.util
from pathlib import Path

import pytest

from academy_server.credentials import CredentialsError, load_credentials
from academy_server.playground import prepare, read_files

REPO = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_live", REPO / "tools" / "run_live.py")
run_live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_live)


def test_load_credentials_tolerates_bom_comments_and_quotes(tmp_path):
    f = tmp_path / "anthropic.env"
    f.write_bytes(b'\xef\xbb\xbf# comment\nANTHROPIC_BASE_URL = https://gw.example\n\nANTHROPIC_API_KEY="sk-test-123"\n')
    assert load_credentials(f) == {"ANTHROPIC_BASE_URL": "https://gw.example", "ANTHROPIC_API_KEY": "sk-test-123"}


def test_load_credentials_reports_missing_without_echoing_values(tmp_path):
    f = tmp_path / "anthropic.env"
    f.write_text("ANTHROPIC_API_KEY=sk-secret-value\n", encoding="utf-8")
    with pytest.raises(CredentialsError) as exc:
        load_credentials(f)
    assert "ANTHROPIC_BASE_URL" in str(exc.value) and "sk-secret-value" not in str(exc.value)


def test_playground_keeps_learner_edits_unless_reset(tmp_path):
    dest = tmp_path / "play"
    assert prepare({"main.py": "starter\n"}, dest) == ["main.py"]
    (dest / "main.py").write_text("my edit\n", encoding="utf-8")
    assert prepare({"main.py": "starter\n"}, dest) == []
    assert read_files(dest, ["main.py", "missing.py"]) == {"main.py": "my edit\n"}
    prepare({"main.py": "starter\n"}, dest, reset=True)
    assert (dest / "main.py").read_text(encoding="utf-8") == "starter\n"


def test_child_env_replaces_any_inherited_anthropic_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "inherited")
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    env = run_live.child_env({"ANTHROPIC_BASE_URL": "https://gw.example", "ANTHROPIC_API_KEY": "sk-x"}, "claude-sonnet-5-5")
    assert "ANTHROPIC_AUTH_TOKEN" not in env and env["ANTHROPIC_LOG"] == "debug"
    assert env["ANTHROPIC_API_KEY"] == "sk-x" and env["LAB_MODEL"] == "claude-sonnet-5-5"
