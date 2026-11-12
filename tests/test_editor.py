"""The lab editor's API: it reads and writes the learner's playground files, never the lesson source."""
from conftest import REPO

STEP = "m02.lab02.s01"
STARTER = (REPO / "content/m02-agent-loop/lab02-agent-loop/s01-one-call/starter/main.py").read_text(encoding="utf-8")


def test_first_open_copies_the_starter_into_the_playground(make_client, home):
    view = make_client().get(f"/api/steps/{STEP}/files").json()
    assert view["entry"] == "main.py" and view["files"]["main.py"]["code"] == STARTER
    assert (home / "playground" / STEP / "main.py").read_text(encoding="utf-8") == STARTER


def test_save_writes_the_file_with_lf_endings(make_client, home):
    c = make_client()
    base = c.get(f"/api/steps/{STEP}/files").json()["files"]["main.py"]["hash"]
    r = c.put(f"/api/steps/{STEP}/files/main.py", json={"code": "print('mine')\r\n", "base_hash": base})
    assert r.status_code == 200 and r.json()["hash"] != base
    assert (home / "playground" / STEP / "main.py").read_bytes() == b"print('mine')\n"
    assert c.get(f"/api/steps/{STEP}/files").json()["files"]["main.py"] == {"code": "print('mine')\n",
                                                                          "hash": r.json()["hash"]}


def test_save_refuses_to_overwrite_a_file_changed_on_disk(make_client, home):
    c = make_client()
    base = c.get(f"/api/steps/{STEP}/files").json()["files"]["main.py"]["hash"]
    (home / "playground" / STEP / "main.py").write_text("# edited in VS Code\n", encoding="utf-8")
    stale = c.put(f"/api/steps/{STEP}/files/main.py", json={"code": "# from the browser\n", "base_hash": base})
    assert stale.status_code == 409 and "changed on disk" in stale.json()["detail"]
    assert (home / "playground" / STEP / "main.py").read_text(encoding="utf-8") == "# edited in VS Code\n"
    forced = c.put(f"/api/steps/{STEP}/files/main.py", json={"code": "# from the browser\n", "base_hash": None})
    assert forced.status_code == 200
    assert (home / "playground" / STEP / "main.py").read_text(encoding="utf-8") == "# from the browser\n"


def test_only_the_steps_own_files_can_be_written(make_client, home):
    c = make_client()
    for name in ("evil.py", "..%2F..%2Fpwned.py", "step.yaml"):
        assert c.put(f"/api/steps/{STEP}/files/{name}", json={"code": "x"}).status_code in (400, 404), name
    assert not (home / "pwned.py").exists() and not (home / "playground" / "pwned.py").exists()


def test_reset_restores_the_starter_and_leaves_the_lesson_untouched(make_client, home):
    c = make_client()
    c.put(f"/api/steps/{STEP}/files/main.py", json={"code": "# broken on purpose\n"})
    view = c.post(f"/api/steps/{STEP}/reset").json()
    assert view["files"]["main.py"]["code"] == STARTER
    assert (home / "playground" / STEP / "main.py").read_text(encoding="utf-8") == STARTER
    assert (REPO / "content/m02-agent-loop/lab02-agent-loop/s01-one-call/starter/main.py").read_text(encoding="utf-8") == STARTER


def test_lab_page_has_the_editor(make_client):
    c = make_client()
    html = c.get(f"/lab/{STEP}").text
    for name in ("editor", "panels", "run", "extras"):   # the page's scripts are static files
        js = c.get(f"/static/lab-js/lab-{name}.js")
        assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
        html += js.text
    assert c.get("/static/lab-js/..%5Capp.py").status_code == 404
    for marker in ('id="code"', 'id="gutter"', 'id="save"', 'id="reset"', "window.labEditor.saveAll()",
                   '<option>claude-haiku-4-5</option>', 'rejects output_config.effort with a 400'):
        assert marker in html, marker
