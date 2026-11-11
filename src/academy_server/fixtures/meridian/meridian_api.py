"""Mock Meridian REST API for App 4 (Python standard library only).

The API serves three read endpoints and one write endpoint from JSON seed files:
  GET   /accounts?page=&page_size=         accounts with their deals[], at most 10 per page
  GET   /opportunities/{id}                one opportunity
  GET   /rate-card?role=&location=&as_of=  rate-card rows, filtered by the given values
  PATCH /opportunities/{id}                a write endpoint that your system must never call

Every request needs the header "Authorization: Bearer <token>". The token comes from the
environment variable MERIDIAN_API_TOKEN. If it is not set, the token is "local-mock-token".

The API writes its own request log as JSON Lines (time, method, path, query, status).
It never writes headers or the token to the log.

Start it with:
  python meridian_api.py [--port 8765] [--seed-dir ../samples/seed] [--log api_requests.jsonl]
"""
import argparse
import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SEED = Path(__file__).resolve().parent.parent / "samples" / "seed"
TOKEN = os.environ.get("MERIDIAN_API_TOKEN", "local-mock-token")
MAX_PAGE_SIZE = 10


def load_seed(seed_dir=SEED):
    """Read accounts.json, opportunities.json and rate_card.json from the seed folder."""
    seed_dir = Path(seed_dir)
    return {name: json.loads((seed_dir / f"{name}.json").read_text()) for name in
            ["accounts", "opportunities", "rate_card"]}


def route(db, path, q):
    """Return (status, body) for the three read endpoints. q maps each query key to one value."""
    parts = [p for p in path.split("/") if p]
    if parts == ["accounts"]:  # each account embeds its deals[]
        page = int(q.get("page", 1))
        size = min(int(q.get("page_size", MAX_PAGE_SIZE)), MAX_PAGE_SIZE)
        items = db["accounts"][(page - 1) * size: page * size]
        more = page * size < len(db["accounts"])
        return 200, {"items": items, "page": page, "page_size": size,
                     "total": len(db["accounts"]), "next_page": page + 1 if more else None}
    if len(parts) == 2 and parts[0] == "opportunities":
        opp = next((o for o in db["opportunities"] if o["opportunity_id"] == parts[1]), None)
        return (200, opp) if opp else (404, {"error": "opportunity not found"})
    if parts == ["rate-card"]:
        rows = [r for r in db["rate_card"]
                if q.get("role", r["role"]) == r["role"] and q.get("location", r["location"]) == r["location"]
                and (not q.get("as_of") or r["valid_from"] <= q["as_of"] <= r["valid_to"])]
        return 200, {"items": rows}
    return 404, {"error": "no such endpoint"}


def make_handler(db, log_path):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            url = urlparse(self.path)
            entry = {"time": datetime.now(timezone.utc).isoformat(), "method": self.command,
                     "path": url.path, "query": url.query, "status": status}
            with lock, open(log_path, "a") as f:  # the API's own request log
                f.write(json.dumps(entry) + "\n")
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _authorised(self):
            return self.headers.get("Authorization") == f"Bearer {TOKEN}"

        def do_GET(self):
            if not self._authorised():
                return self._send(401, {"error": "unauthorised"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                self._send(*route(db, url.path, q))
            except ValueError:
                self._send(400, {"error": "bad query"})

        def do_PATCH(self):  # the write endpoint; it accepts the call but stores nothing
            if not self._authorised():
                return self._send(401, {"error": "unauthorised"})
            self._send(200, {"patched": self.path})

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler


def start(port=0, log_path="api_requests.jsonl", seed_dir=SEED):
    """Start the API in a background thread and return (server, base_url). Useful in tests."""
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(load_seed(seed_dir), log_path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def serve(port=8765, log_path="api_requests.jsonl", seed_dir=SEED):
    """Start the API in the foreground."""
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(load_seed(seed_dir), log_path))
    print(f"Meridian mock API on http://127.0.0.1:{port}  seed={seed_dir}  log={log_path}")
    server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Mock Meridian API")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--seed-dir", default=str(SEED), help="folder with accounts.json, opportunities.json, rate_card.json")
    ap.add_argument("--log", default="api_requests.jsonl", help="path of the request log (JSON Lines)")
    a = ap.parse_args()
    serve(a.port, a.log, a.seed_dir)
