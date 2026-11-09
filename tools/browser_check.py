"""Walk a lesson in headless Edge: every guide step, its checks, experiments and quiz.

    .venv/Scripts/python -X utf8 tools/browser_check.py m02.lab02.s01
    .venv/Scripts/python -X utf8 tools/browser_check.py m02.lab02.s01 --keep   # keep the temp dir

- A fake gateway stands in for Claude (a one-sentence text answer; a thinking block when effort is
  high; count_tokens counts words), so the check costs nothing and makes no live calls.
- The lab runs with its own temporary data dir and playground: your progress and playground/ are
  untouched.
- For each step it checks the page rendered (title, code highlights, your-run values), answers every
  check, plays any experiment through to its explanation, answers the quiz, and saves a screenshot.
  It reports any JavaScript error. Exit code 1 if anything failed.

A lesson whose code needs a different reply (tool calls, from s02 on) extends fake_reply() below.
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


# ------------------------------------------------------------- fake gateway
def fake_reply(body: dict) -> dict:
    """The Message the fake gateway returns for a /v1/messages request body."""
    effort = (body.get("output_config") or {}).get("effort")
    content = [{"type": "text", "text": ANSWER}]
    out = min(25, body.get("max_tokens") or 25)
    stop = "max_tokens" if out < 25 else "end_turn"
    if effort == "high":
        content.insert(0, {"type": "thinking", "thinking": "", "signature": "sig"})
        out = min(40, body.get("max_tokens") or 40)
    return {"id": "msg_fake", "type": "message", "role": "assistant", "model": body.get("model"), "content": content,
            "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 22, "output_tokens": out, "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0}}


def gateway(request):
    import httpx
    body = json.loads(request.content or b"{}")
    if request.url.path.endswith("/count_tokens"):
        return httpx.Response(200, json={"input_tokens": 8 + len(body["messages"][0]["content"].split())})
    msg = fake_reply(body)
    cost = (msg["usage"]["input_tokens"] * 4 + msg["usage"]["output_tokens"] * 20) / 1e6
    return httpx.Response(200, json=msg, headers={"x-litellm-response-cost-original": repr(cost)})


def start_lab(home: Path) -> tuple[str, str]:
    """The lab on a free port with the fake gateway. Returns (base URL, session token)."""
    import httpx
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
                           upstream_transport=httpx.MockTransport(gateway), playground_root=home / "playground")
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
    b.js("document.getElementById('run').click()")
    b.wait("document.getElementById('status').textContent.startsWith('ok')", "the first run", timeout=90)
    b.wait(f"!{STEP_TEXT}.includes('No run yet')", "your run's values")

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
        b.js("window.scrollTo(0, 0)")
        shot = b.call("Page.captureScreenshot", format="png")["data"]
        (out / f"{step_id}-{i + 1:02d}-{g['id']}.png").write_bytes(base64.b64decode(shot))

    errors = b.errors()
    check(f"no JavaScript errors{': ' + '; '.join(errors) if errors else ''}", not errors)
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
