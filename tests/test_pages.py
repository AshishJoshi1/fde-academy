"""Server-rendered pages: home placeholder, /design style guide, theme stamping."""


def test_home_is_styled_and_lists_the_course(make_client):
    r = make_client().get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert 'href="/static/academy.css"' in html
    assert "m02.lab02.s01" in html and "The Agent Loop" in html
    assert 'class="pill pill-not_started"' in html


def test_design_page_has_every_component(make_client):
    r = make_client().get("/design")
    assert r.status_code == 200
    for marker in ('id="palette"', 'class="workbench"', 'class="trace"', 'class="messages"',
                   'class="segbar"', 'class="why-chain"', 'quiz-card"', 'role="tablist"'):
        assert marker in r.text, marker


def test_design_requires_session(make_client):
    assert make_client(authed=False).get("/design").status_code == 401


def test_theme_param_is_allowlisted(make_client):
    c = make_client()
    assert '<html lang="en" data-theme="dark">' in c.get("/design", params={"theme": "dark"}).text
    assert '<html lang="en" data-theme="light">' in c.get("/", params={"theme": "light"}).text
    evil = c.get("/design", params={"theme": '"><script>alert(1)</script>'}).text
    assert "<script>alert(1)" not in evil and '<html lang="en">' in evil


def test_home_escapes_content(tmp_path, make_client):
    """Lesson titles are author-controlled; they must not inject markup into the page."""
    import shutil
    from conftest import REPO
    content = tmp_path / "content"
    shutil.copytree(REPO / "content", content)
    step_yaml = content / "m02-agent-loop/lab02-agent-loop/s01-one-call/step.yaml"
    text = step_yaml.read_text(encoding="utf-8").replace(
        'title: "One call: what actually comes back"', 'title: "<img src=x onerror=alert(1)>"')
    step_yaml.write_text(text, encoding="utf-8")
    html = make_client(content_dir=content).get("/").text
    assert "<img src=x" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
