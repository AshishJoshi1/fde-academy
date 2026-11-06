"""Start the FDE Academy server: python -X utf8 -m academy_server [--port N] [--no-browser]

Binds 127.0.0.1 only. Prints a one-time launch URL carrying the per-launch secret.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from . import paths
from .security import new_token

DEFAULT_PORT = 8787


def _free_port(preferred: int) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("no free port on 127.0.0.1")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="academy", description="FDE Academy local server")
    ap.add_argument("--port", type=int, default=int(os.environ.get("FDE_ACADEMY_PORT", DEFAULT_PORT)))
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--content", type=Path, default=paths.content_dir())
    ap.add_argument("--dev-origin", action="append", default=[],
                    help="extra allowed Origin, e.g. http://127.0.0.1:5173 for the Vite dev server")
    args = ap.parse_args(argv)

    if sys.flags.utf8_mode == 0:
        print("warning: start with `python -X utf8` (run.py does). Seed data with non-ASCII names "
              "fails to load under the Windows code page.", file=sys.stderr)

    import uvicorn  # deferred so `--help` is instant

    from .app import AppSettings, create_app
    from .credentials import CredentialsError, load_credentials
    from .relay import Upstream

    port = _free_port(args.port)
    token = new_token()
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    try:
        creds = load_credentials(paths.credentials_path())
        upstream = Upstream(base_url=creds["ANTHROPIC_BASE_URL"], api_key=creds["ANTHROPIC_API_KEY"])
        gateway_line = f"{upstream.base_url.split('://')[-1].rstrip('/')} (key from {paths.credentials_path()})"
    except CredentialsError as exc:
        upstream, gateway_line = None, f"NOT CONFIGURED: lesson model calls will get 503. {exc}"
    settings = AppSettings(token=token, port=port, content_dir=args.content, db_path=paths.db_path(),
                           web_dist=paths.repo_root() / "web" / "dist", extra_origins=args.dev_origin,
                           upstream=upstream)
    app = create_app(settings)

    url = f"http://127.0.0.1:{port}/auth?t={token}"
    info = paths.server_info_path()
    info.write_text(json.dumps({"port": port, "url": url, "pid": os.getpid()}), encoding="utf-8")
    tree = app.state.content
    print(f"\n  FDE Academy  ->  {url}\n"
          f"  lessons: {len(tree.steps)} steps in {len(tree.modules)} module(s)"
          f"{f', {len(tree.errors)} content error(s): see /api/content/errors' if tree.errors else ''}\n"
          f"  gateway: {gateway_line}\n"
          f"  data:    {paths.data_dir()}\n"
          f"  stop:    Ctrl+C   (progress autosaves; nothing is lost)\n", flush=True)
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        try:
            info.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
