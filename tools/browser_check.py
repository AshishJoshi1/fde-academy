"""Walk a lesson in headless Edge: every guide step, its checks, experiments and quiz.

    .venv/Scripts/python -X utf8 tools/browser_check.py m02.lab02.s01
    .venv/Scripts/python -X utf8 tools/browser_check.py m02.lab02.s01 --keep   # keep the temp dir

- A fake gateway stands in for Claude (a one-sentence text answer; a thinking block when effort is
  high; count_tokens counts words), so the check costs nothing and makes no live calls. With tools in
  the request it asks for the first tool, answers its tool_result with text, and returns the real
  API's 400 when a tool_use has no tool_result after it. A step's mock API (s02 on) is the real one.
- The lab runs with its own temporary data dir and playground: your progress and playground/ are
  untouched.
- For each step it checks the page rendered (title, code highlights, your-run values), answers every
  check, plays any experiment through to its explanation, answers the quiz, and saves a screenshot.
- Then it starts the lesson over (every tick gone, no run reopened, history and spaced review kept),
  and walks the flash cards (flip, "Didn't know" and "Knew it", tag filter, all cards, the card's
  link back from spaced review).
- On a step with the timeline, messages or mock API panels, it checks each one drew the first run.
- It reports any JavaScript error. Exit code 1 if anything failed.

A lesson whose code needs a different reply extends fake_reply() below.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

EDGE_PATHS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
ANSWER = "An agent loop is the repeating cycle in which an AI model observes its context, acts, and repeats."
TOOL_ANSWER = "Procurement asked for 12% off list on OPP-1042, which is for account ACC-017."


# ------------------------------------------------------------- fake gateway
def _blocks(message: dict) -> list:
    return message["content"] if isinstance(message.get("content"), list) else []


def unanswered_tool_use(messages: list) -> tuple[int, list[str]] | None:
    """(index, ids) of the first assistant message whose tool_use blocks have no tool_result in the next message."""
    for i, m in enumerate(messages):
        ids = [b["id"] for b in _blocks(m) if m.get("role") == "assistant" and b.get("type") == "tool_use"]
        if ids:
            nxt = messages[i + 1] if i + 1 < len(messages) else {}
            got = {b.get("tool_use_id") for b in _blocks(nxt) if b.get("type") == "tool_result"}
            missing = [x for x in ids if x not in got]
            if missing:
                return i, missing
    return None


def fake_reply(body: dict) -> tuple[int, dict]:
    """(status, body) the fake gateway returns for a /v1/messages request body."""
    messages, tools = body.get("messages") or [], body.get("tools") or []
    bad = unanswered_tool_use(messages)
    if bad:   # the real API's check, wrapped the way the gateway wraps errors
        inner = {"type": "error", "error": {"type": "invalid_request_error", "message":
                 f"messages.{bad[0]}: `tool_use` ids were found without `tool_result` blocks immediately after: "
                 f"{', '.join(bad[1])}. Each `tool_use` block must have a corresponding `tool_result` block "
                 "in the next message."}}
        return 400, {"error": {"message": json.dumps(inner), "type": "None", "param": "None", "code": "400"}}
    effort = (body.get("output_config") or {}).get("effort")
    answered = any(b.get("type") == "tool_result" for b in _blocks(messages[-1] if messages else {}))
    size = len(json.dumps(messages)) + len(json.dumps(tools))
    usage = {"input_tokens": size // 4 if tools else 22, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    if tools and not answered:   # ask for the first tool, with OPP-1042 for every required field
        schema = tools[0].get("input_schema") or {}
        content = [{"type": "tool_use", "id": f"toolu_fake{len(messages):02d}", "name": tools[0]["name"],
                    "input": {k: "OPP-1042" for k in schema.get("required", [])}}]
        return 200, {"id": "msg_fake", "type": "message", "role": "assistant", "model": body.get("model"),
                     "content": content, "stop_reason": "tool_use", "stop_sequence": None,
                     "usage": {**usage, "output_tokens": 60}}
    content = [{"type": "text", "text": TOOL_ANSWER if tools else ANSWER}]
    out = min(25, body.get("max_tokens") or 25)
    stop = "max_tokens" if out < 25 else "end_turn"
    if effort == "high":
        content.insert(0, {"type": "thinking", "thinking": "", "signature": "sig"})
        out = min(40, body.get("max_tokens") or 40)
    return 200, {"id": "msg_fake", "type": "message", "role": "assistant", "model": body.get("model"), "content": content,
                 "stop_reason": stop, "stop_sequence": None, "usage": {**usage, "output_tokens": out}}


def gateway(request):
    import httpx
    body = json.loads(request.content or b"{}")
    if request.url.path.endswith("/count_tokens"):
        return httpx.Response(200, json={"input_tokens": 8 + len(body["messages"][0]["content"].split())})
    status, msg = fake_reply(body)
    if status >= 400:
        return httpx.Response(status, json=msg)
    cost = (msg["usage"]["input_tokens"] * 4 + msg["usage"]["output_tokens"] * 20) / 1e6
    return httpx.Response(200, json=msg, headers={"x-litellm-response-cost-original": repr(cost)})


def start_lab(home: Path) -> tuple[str, str]:
    """The lab on a free port with the fake gateway. Returns (base URL, session token)."""
    import httpx
    import httpx2
    import uvicorn
    from academy_server import paths
    from academy_server.app import AppSettings, create_app
    from academy_server.relay import Upstream

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    token = secrets.token_urlsafe(16)
    settings = AppSettings(token=token, port=port, content_dir=paths.content_dir(), db_path=home / "academy.db",
                           web_dist=home / "no-web", upstream=Upstream("https://fake.gateway", "sk-fake"),
                           upstream_transport=httpx.MockTransport(gateway),
                           tutor_transport=httpx2.MockTransport(tutor_gateway), playground_root=home / "playground")
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 20
    while not server.started:
        if time.time() > deadline:
            raise SystemExit("the lab server did not start")
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", token


# ------------------------------------------- DevTools protocol (stdlib only)
class WebSocket:
    def __init__(self, url: str):
        host_port, path = url[len("ws://"):].split("/", 1)
        host, port = host_port.split(":")
        self.sock = socket.create_connection((host, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.sock.recv(4096)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError(f"websocket upgrade refused: {head[:120]!r}")
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def send(self, text: str) -> None:
        data, mask = text.encode(), os.urandom(4)
        n = len(data)
        head = bytearray([0x81])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126); head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127); head += struct.pack(">Q", n)
        self.sock.sendall(bytes(head) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("browser closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> str:
        msg = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if b1 & 0x0F == 8:
                raise EOFError("browser closed the connection")
            if b1 & 0x0F in (9, 10):
                continue
            msg += payload
            if b1 & 0x80:
                return msg.decode()


class Browser:
    def __init__(self, ws: WebSocket):
        self.ws, self.n, self.events = ws, 0, []

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m.get("result", {})
            self.events.append(m)

    def js(self, expr: str):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"])
        return r["result"].get("value")

    def wait(self, expr: str, what: str, timeout: float = 45) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.js(expr):
                return
            time.sleep(0.2)
        raise TimeoutError(f"timed out waiting for {what}")

    def errors(self) -> list[str]:
        out = []
        for e in self.events:
            p = e.get("params", {})
            if e.get("method") == "Runtime.exceptionThrown":
                out.append(p["exceptionDetails"].get("exception", {}).get("description", "exception"))
            elif e.get("method") == "Runtime.consoleAPICalled" and p.get("type") == "error":
                out.append(" ".join(str(a.get("value", a.get("description"))) for a in p.get("args", [])))
            elif e.get("method") == "Log.entryAdded" and p["entry"]["level"] == "error" \
                    and "favicon" not in p["entry"].get("url", ""):
                out.append(f"{p['entry']['text']} {p['entry'].get('url', '')}")
        return out


def open_browser(profile: Path) -> tuple[subprocess.Popen, Browser]:
    edge = next((p for p in EDGE_PATHS if Path(p).is_file()), None)
    if edge is None:
        raise SystemExit("Microsoft Edge not found")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                             f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while True:
        try:
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2).read())
            page = next(t for t in targets if t["type"] == "page")
            break
        except Exception:
            if time.time() > deadline:
                proc.kill()
                raise SystemExit("Edge did not start")
            time.sleep(0.3)
    browser = Browser(WebSocket(page["webSocketDebuggerUrl"]))
    for domain in ("Runtime", "Log", "Page"):
        browser.call(f"{domain}.enable")
    browser.call("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
    return proc, browser


# ---------------------------------------------------------------- the walk
STEP_TEXT = "document.querySelector('#guide-step').textContent"
CLICK_BUTTON = "[...document.querySelectorAll('#guide-step button')].find(b => b.textContent === {!r}).click()"
FILL_FORM = """(function (form) {
  form.querySelectorAll('fieldset').forEach(function (fs) { fs.querySelector('input[type=radio]').click(); });
  form.querySelectorAll('input.input').forEach(function (i) { i.value = '1'; });
  form.querySelectorAll('textarea').forEach(function (t) { t.value = 'browser check'; });
})({form})"""


def tutor_gateway(request):
    """The tutor's fake gateway (the SDK runs on httpx2): a question back, as the tutor would."""
    import httpx2
    body = json.loads(request.content or b"{}")
    n = len(body["messages"])
    return httpx2.Response(200, json={
        "id": f"msg_tutor_{n}", "type": "message", "role": "assistant", "model": body.get("model"),
        "content": [{"type": "text", "text": "What does the `blocks:` line of your run print?"}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 15, "cache_creation_input_tokens": 6000 if n == 1 else 150,
                  "cache_read_input_tokens": 0 if n == 1 else 6000}})


def walk(b: Browser, base: str, token: str, step_id: str, out: Path) -> list[str]:
    fails: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(f"    [{'ok' if ok else 'FAIL'}] {label}")
        if not ok:
            fails.append(label)

    b.call("Page.navigate", url=f"{base}/auth?t={token}&next=/lab/{step_id}%23g1")
    b.wait("!!document.querySelector('#guide-step h2')", "the lesson to load")
    with urllib.request.urlopen(urllib.request.Request(f"{base}/api/steps/{step_id}/guide",
                                                       headers={"x-academy-token": token})) as r:
        steps = json.loads(r.read())["steps"]
    print(f"  {len(steps)} guide steps")
    panels = api_get(base, token, f"/api/steps/{step_id}")["panels"]
    b.js("document.getElementById('run').click()")
    b.wait("document.getElementById('status').textContent.startsWith('ok')", "the first run", timeout=90)
    b.wait(f"!{STEP_TEXT}.includes('No run yet')", "your run's values")
    check_panels(b, panels, check)

    for i, g in enumerate(steps):
        print(f"  step {i + 1}: {g['title']}")
        b.js(f"document.querySelectorAll('#guide-nav button')[{i}].click()")
        b.wait(f"{STEP_TEXT}.includes('Step {i + 1} of {len(steps)}')", f"step {i + 1}")
        check("title shown", b.js("document.querySelector('#guide-step h2').textContent") == g["title"])
        check(f"{len(g['lines'])} code line(s) highlighted",
              b.js("document.querySelectorAll('#marks .mark').length") == len(g["lines"]))
        if g["show"]:
            check("your run's values shown",
                  b.js("document.querySelectorAll('#guide-step .facts-table tr').length") == len(g["show"]))
        for k in range(len(g["check"])):
            form = f"document.querySelectorAll('#guide-step form.predict-item')[{k}]"
            b.js(FILL_FORM.replace("{form}", form) + f";{form}.querySelector('button[type=submit]').click()")
            b.wait(f"!!{form}.querySelector('.quiz-feedback')", f"check {k + 1} feedback")
            check(f"check {k + 1} answered with its why", b.js(f"{form}.querySelector('.quiz-feedback').textContent.length > 20"))
        if g["experiment"]:
            b.wait(f"{STEP_TEXT}.includes('Commit predictions') || {STEP_TEXT}.includes('4 · Compare')", "the experiment")
            if b.js(f"{STEP_TEXT}.includes('Commit predictions')"):
                b.js(FILL_FORM.replace("{form}", "document.querySelector('#guide-step .exp-card form')"))
                b.js(CLICK_BUTTON.format("Commit predictions"))
                b.wait(f"{STEP_TEXT}.includes('Run for this experiment')", "the committed card")
                b.wait("!document.getElementById('run').disabled", "the previous run to end")
                b.js(CLICK_BUTTON.format("Run for this experiment"))
                b.wait(f"{STEP_TEXT}.includes('4 · Compare')", "the comparison", timeout=90)
                check("compared with the run", b.js("document.querySelectorAll('#guide-step .exp-card tbody tr').length") > 0)
                b.js("document.querySelector('#guide-step textarea[aria-label=\"Your explanation\"]').value = 'browser check'")
                b.js(CLICK_BUTTON.format("Show the explanation"))
            b.wait(f"{STEP_TEXT}.includes('The explanation')", "the explanation")
            check("experiment played through to its explanation", True)
        if g["quiz"]:
            n = b.js("document.querySelectorAll('#guide-step .quiz-card').length")
            for k in range(n):
                form = f"document.querySelectorAll('#guide-step .quiz-card')[{k}]"
                b.js(FILL_FORM.replace("{form}", form) + f";{form}.querySelector('button[type=submit]').click()")
                b.wait(f"!!{form}.querySelector('.quiz-feedback')", f"quiz question {k + 1}")
            check(f"{n} quiz question(s) answered", n > 0)
        tutor = "document.querySelector('#guide-step .tutor')"
        b.wait(f"!!{tutor} && !{tutor}.querySelector('button[type=submit]').disabled", "the tutor")
        b.js(f"{tutor}.querySelector('textarea').value = 'Why?';{tutor}.querySelector('button[type=submit]').click()")
        b.wait(f"{tutor}.querySelectorAll('.tutor-a').length > 0", "the tutor's answer")
        b.js(f"{tutor}.querySelector('.tutor-a details').open = true")
        b.wait(f"!!{tutor}.querySelector('.tutor-a details pre')", "the tutor's request")
        check("tutor answered, with its exact request", b.js(
            f"{tutor}.querySelector('.tutor-a details pre').textContent.includes('claude-sonnet-5-5')"))
        b.js("window.scrollTo(0, 0)")
        shot = b.call("Page.captureScreenshot", format="png")["data"]
        (out / f"{step_id}-{i + 1:02d}-{g['id']}.png").write_bytes(base64.b64decode(shot))

    errors = b.errors()
    check(f"no JavaScript errors{': ' + '; '.join(errors) if errors else ''}", not errors)
    return fails


def check_panels(b: Browser, panels: list[str], check) -> None:
    """The run views a step turns on drew the first run; the ones it doesn't stay hidden."""
    for name in ("timeline", "messages", "fixture"):
        shown = not b.js(f"document.querySelector('.pane[data-panel={name}]').hidden")
        check(f"{name} panel {'shown' if name in panels else 'hidden'}", shown == (name in panels))
    if "timeline" in panels:
        b.wait("document.querySelectorAll('#timeline .trace-row').length > 0", "the timeline")
        rows = b.js("[...document.querySelectorAll('#timeline .trace-label')].map(l => l.textContent)")
        print(f"    timeline: {' | '.join(rows)}")
        check("timeline: calls, the tool run between them, and its API request",
              len(rows) >= 4 and any("result sent" in r for r in rows))
    if "messages" in panels:
        b.wait("document.querySelectorAll('#messages-view .msg').length > 0", "the messages view")
        check("messages: the last call's list, with what it added marked",
              b.js("document.querySelectorAll('#messages-view .msg.is-added').length") > 0
              and b.js("document.querySelectorAll('#messages-tabs .tab').length") > 1)
        b.js("document.querySelector('#messages-tabs .tab').click()")
        check("messages: call 1's tab shows call 1's list",
              b.js("document.getElementById('messages-view').textContent.includes('Call 1 sent 1 message')"))
    if "fixture" in panels:
        check("mock API log lists the tool's request", b.js("document.querySelectorAll('#api-log tbody tr').length") > 0)


def api_get(base: str, token: str, path: str):
    with urllib.request.urlopen(urllib.request.Request(f"{base}{path}", headers={"x-academy-token": token})) as r:
        return json.loads(r.read())


def reload_after(b: Browser, action: str, what: str) -> None:
    """Run an action that reloads the page, and wait for the new page to load."""
    b.js("window.__checkMark = 1")
    b.js(action)
    b.wait("!window.__checkMark && document.readyState === 'complete'", what)


def walk_start_over(b: Browser, base: str, token: str, step_id: str, out: Path) -> list[str]:
    fails: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(f"    [{'ok' if ok else 'FAIL'}] {label}")
        if not ok:
            fails.append(label)

    print("  start over")
    misses = len(api_get(base, token, "/api/mistakes")["still_wrong"])
    runs = len(api_get(base, token, f"/api/steps/{step_id}/runs")["runs"])
    check("some steps ticked before", b.js("document.querySelectorAll('#guide-nav .icon-check').length") > 0)
    b.js("document.querySelector('details.start-over > summary').click()")
    check("the panel says what's kept", b.js("document.querySelector('details.start-over').open && "
                                             "document.querySelector('details.start-over').textContent.includes('Kept:')"))
    reload_after(b, "document.querySelector('details.start-over .start-over-go').click()", "the lab to reload")
    b.wait("!!document.querySelector('#guide-step h2') && document.querySelectorAll('#history option').length > 1",
           "the lesson and run history to load")
    check("every tick gone", b.js("document.querySelectorAll('#guide-nav .icon-check').length") == 0)
    check("opens on step 1", b.js(f"{STEP_TEXT}.includes('Step 1 of')"))
    check("no run reopened", b.js("document.getElementById('status').textContent") == "no run yet")
    check(f"run history kept ({runs} runs)", b.js("document.querySelectorAll('#history option').length") == runs + 1)
    check(f"spaced review kept ({misses} misses)", len(api_get(base, token, "/api/mistakes")["still_wrong"]) == misses)
    shot = b.call("Page.captureScreenshot", format="png")["data"]
    (out / f"{step_id}-start-over.png").write_bytes(base64.b64decode(shot))

    print("  start over all lessons (home page)")
    b.call("Page.navigate", url=f"{base}/")
    b.wait("!!document.querySelector('details.start-over')", "the home page")
    check("this lesson is in progress before (the lab just opened it)",
          b.js("document.body.textContent.includes('In progress')"))
    b.js("document.querySelector('details.start-over > summary').click()")
    reload_after(b, "document.querySelector('details.start-over .start-over-go').click()", "the home page to reload")
    b.wait("!!document.querySelector('details.start-over')", "the home page")
    check("every lesson back to Not started, none In progress",
          not b.js("document.body.textContent.includes('In progress')")
          and b.js("document.body.textContent.includes('Not started')"))
    check(f"spaced review still kept ({misses} misses)", len(api_get(base, token, "/api/mistakes")["still_wrong"]) == misses)
    return fails


CARD_TEXT = "document.getElementById('study').textContent"
CLICK_CARD = "[...document.querySelectorAll('#study button')].find(b => b.textContent === {!r}).click()"


def walk_cards(b: Browser, base: str, token: str, out: Path) -> list[str]:
    fails: list[str] = []

    def check(label: str, ok: bool) -> None:
        print(f"    [{'ok' if ok else 'FAIL'}] {label}")
        if not ok:
            fails.append(label)

    [deck] = api_get(base, token, "/api/cards")["decks"]
    n, first = len(deck["cards"]), deck["cards"][0]["id"]
    print(f"  flash cards: {n} cards")
    b.call("Page.navigate", url=f"{base}/cards")
    b.wait("!!document.querySelector('.fc-card')", "the first card")
    check("Flash cards is the current page in the top bar",
          b.js("document.querySelector('.nav a[aria-current=page]').textContent") == "Flash cards")
    check(f"card 1 of {n}", b.js(f"{CARD_TEXT}.includes('Card 1 of {n}')"))
    b.js(CLICK_CARD.format("Show the answer"))
    b.wait("!!document.querySelector('.fc-back')", "the answer")
    check("answer and source shown", b.js("document.querySelector('.fc-back').textContent.length > 40 && "
                                          f"{CARD_TEXT}.includes('Source:')"))
    shot = b.call("Page.captureScreenshot", format="png")["data"]
    (out / "cards-study.png").write_bytes(base64.b64decode(shot))
    b.js(CLICK_CARD.format("Didn't know"))
    b.wait(f"{CARD_TEXT}.includes('Card 2 of {n}')", "card 2")
    b.js(CLICK_CARD.format("Show the answer"))
    b.wait("!!document.querySelector('.fc-back')", "card 2's answer")
    b.js(CLICK_CARD.format("Knew it"))
    b.wait(f"{CARD_TEXT}.includes('Card 3 of {n}')", "card 3")
    check("tally counts both reviews",
          b.js("document.getElementById('tally').textContent") == f"1 known · 1 to review · {n - 2} new")
    cost = sum(1 for c in deck["cards"] if c["tag"] == "cost")
    b.js("document.querySelector('#tags .tab[data-tag=cost]').click()")
    b.wait(f"{CARD_TEXT}.includes('Card 1 of {cost}')", "the cost cards")
    check(f"tag filter: {cost} cost cards", True)
    b.js("document.querySelector('#tags .tab[data-tag=all]').click()")
    b.js("document.querySelector('#modes .tab[data-mode=list]').click()")
    b.wait("document.getElementById('study').hidden", "the card list")
    check(f"all {n} cards listed", b.js("document.querySelectorAll('#list .fc-item').length") == n)
    b.js("document.querySelector('#list .fc-item').open = true")
    shot = b.call("Page.captureScreenshot", format="png")["data"]
    (out / "cards-list.png").write_bytes(base64.b64decode(shot))

    b.call("Page.navigate", url=f"{base}/")
    b.wait(f"!!document.querySelector('a[href=\"/cards#{first}\"]')", "the card in spaced review")
    check("the missed card is in spaced review on the home page", True)
    b.js(f"document.querySelector('a[href=\"/cards#{first}\"]').click()")
    b.wait(f"!!document.getElementById('fc-{first}')", "the missed card to open first")
    check("its link opens that card, marked as missed",
          b.js(f"document.getElementById('fc-{first}').textContent.includes(\"Didn't know last time\")"))
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="browser_check", description=__doc__.split("\n\n")[0])
    ap.add_argument("step_id", help="e.g. m02.lab02.s01")
    ap.add_argument("--keep", action="store_true", help="keep the temporary data dir and screenshots")
    args = ap.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="fde-academy-check-"))
    os.environ["FDE_ACADEMY_HOME"] = str(tmp / "home")      # never the real learner data
    (tmp / "home").mkdir()
    shots = tmp / "screens"
    shots.mkdir()
    base, token = start_lab(tmp / "home")
    proc, browser = open_browser(tmp / "edge")
    print(f"browser check · {args.step_id} · fake gateway · {base}")
    try:
        fails = walk(browser, base, token, args.step_id, shots)
        seen = len(browser.errors())          # walk() reported these already
        fails += walk_start_over(browser, base, token, args.step_id, shots)
        fails += walk_cards(browser, base, token, shots)
        errors = browser.errors()[seen:]
        if errors:
            fails.append(f"JavaScript errors after the lesson walk: {'; '.join(errors)}")
            print(f"    [FAIL] JavaScript errors: {'; '.join(errors)}")
    except (TimeoutError, RuntimeError) as exc:
        fails = [str(exc)]
        print(f"  STOPPED: {exc}")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    print(f"\nscreenshots: {shots}")
    print("FAILED:\n  - " + "\n  - ".join(fails) if fails else "all checks passed")
    if not args.keep and not fails:
        shutil.rmtree(tmp / "home", ignore_errors=True)
        shutil.rmtree(tmp / "edge", ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
