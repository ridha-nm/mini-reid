"""One-time consent to add Google Calendar read access.

Keeps the existing refresh token and Gmail scopes; adds calendar.readonly.
Run: .venv/bin/python -m mini_reid.google_auth
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import ssl
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .sources import load_env

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _paths(env: dict) -> tuple[Path, Path]:
    return (Path(os.path.expanduser(env["GMAIL_CREDS"])),
            Path(os.path.expanduser(env["GMAIL_TOKEN"])))


def _scopes(token: dict) -> list[str]:
    scopes = (token.get("scope") or "").split()
    if CALENDAR_SCOPE not in scopes:
        scopes.append(CALENDAR_SCOPE)
    return scopes


def _exchange(client: dict, code: str, redirect: str) -> dict:
    data = urllib.parse.urlencode({
        "code": code, "client_id": client["client_id"],
        "client_secret": client["client_secret"], "redirect_uri": redirect,
        "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.load(r)


def main() -> int:
    env = load_env(".env")
    creds_path, token_path = _paths(env)
    client = (json.loads(creds_path.read_text()).get("installed")
              or json.loads(creds_path.read_text()).get("web") or {})
    token = json.loads(token_path.read_text())
    redirect = (client.get("redirect_uris") or ["http://localhost:44000/oauth2callback"])[0]
    port = urllib.parse.urlparse(redirect).port or 44000
    scopes = _scopes(token)
    state = secrets.token_urlsafe(16)

    params = {
        "client_id": client["client_id"], "redirect_uri": redirect,
        "response_type": "code", "scope": " ".join(scopes),
        "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true", "state": state,
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("state", [""])[0] != state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch. Close this tab and retry.")
                return
            result.update({k: v[0] for k, v in query.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Authorization complete. Close this tab.")
            self.server._done = True  # type: ignore[attr-defined]

        def log_message(self, *_args):
            pass

    server = HTTPServer(("localhost", port), Handler)
    print(url, flush=True)
    if env.get("NO_BROWSER") != "1":
        webbrowser.open(url)
    while not getattr(server, "_done", False):
        server.handle_request()

    if "code" not in result:
        print(f"Authorization failed: {result.get('error', 'no code')}")
        return 1
    got = _exchange(client, result["code"], redirect)
    if "refresh_token" not in got and not token.get("refresh_token"):
        print("No refresh token returned. Retry with prompt=consent.")
        return 1

    backup = token_path.with_name(
        f"{token_path.name}.bak-calendar-{datetime.now():%Y%m%d%H%M%S}")
    shutil.copy2(token_path, backup)
    token.update({
        "access_token": got["access_token"],
        "refresh_token": got.get("refresh_token") or token["refresh_token"],
        "scope": " ".join(scopes),
        "token_type": got.get("token_type") or token.get("token_type", "Bearer"),
        "expiry_date": int(time.time() * 1000) + int(got.get("expires_in", 3600)) * 1000,
    })
    token_path.write_text(json.dumps(token, indent=2))
    token_path.chmod(0o600)
    print(f"Calendar scope granted. Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
