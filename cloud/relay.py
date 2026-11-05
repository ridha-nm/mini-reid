"""Mini-Reid hosted setup relay.

Fixed HTTPS page + Google OAuth callback. Holds the code/credentials for a
few seconds until the Mac polls with RELAY_KEY. No tokens are logged.
"""
from __future__ import annotations

import hmac
import html
import json
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = " ".join([
    "openid", "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
])
STORE: dict[str, dict] = {}
LOCK = threading.Lock()
TTL = 600


def _base(handler: BaseHTTPRequestHandler) -> str:
    host = handler.headers.get("Host") or ""
    proto = handler.headers.get("X-Forwarded-Proto") or "https"
    return f"{proto}://{host}"


def _take(state: str) -> dict:
    with LOCK:
        entry = STORE.pop(state, {})
        if time.time() - float(entry.pop("ts", 0)) > TTL:
            return {}
        return entry


def _put(state: str, **fields) -> None:
    with LOCK:
        entry = STORE.setdefault(state, {"ts": time.time()})
        entry["ts"] = time.time()
        entry.update(fields)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _html(self, body: str, status: int = 200) -> None:
        page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mini-Reid setup</title>
<style>
body{{font:16px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;max-width:620px;
margin:40px auto;padding:0 20px;color:#111}}
.card{{border:1px solid #ddd;border-radius:12px;padding:20px;margin:16px 0}}
.ok{{color:#0a7d32}} .bad{{color:#a33}}
input{{display:block;width:100%;padding:10px;margin:6px 0 14px;box-sizing:border-box;
border:1px solid #bbb;border-radius:8px}}
button,a.btn{{background:#1f2937;color:#fff;border:0;border-radius:8px;
padding:10px 16px;text-decoration:none;display:inline-block;cursor:pointer}}
</style></head><body><h1>Mini-Reid setup</h1>{body}</body></html>"""
        data = page.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        state = (query.get("state") or [""])[0]

        if parsed.path == "/health":
            self._html("<p class='ok'>ok</p>")
            return

        if parsed.path == "/take":
            key = (query.get("key") or [""])[0]
            if not hmac.compare_digest(key, os.environ.get("RELAY_KEY", "")):
                self._html("<p class='bad'>Forbidden.</p>", 403)
                return
            data = _take(state)
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if not state:
            self._html("<p class='bad'>Missing setup state.</p>", 400)
            return

        if parsed.path == "/callback":
            code = (query.get("code") or [""])[0]
            if not code:
                self._html("<p class='bad'>Google did not return a code.</p>", 400)
                return
            _put(state, google_code=code)
            self._html("<p class='ok'>Google connected.</p>"
                       "<p>Return to mini-reid. Setup finishes automatically.</p>")
            return

        if parsed.path == "/google":
            client = os.environ.get("GOOGLE_CLIENT_ID", "")
            if not client:
                self._html("<p class='bad'>Google client is not configured yet. "
                           "Ask Ridha.</p>", 503)
                return
            params = {
                "client_id": client,
                "redirect_uri": f"{_base(self)}/callback",
                "response_type": "code", "scope": SCOPES,
                "access_type": "offline", "prompt": "consent",
                "include_granted_scopes": "true", "state": state,
            }
            self.send_response(302)
            self.send_header("Location", f"{AUTH_URL}?"
                             + urllib.parse.urlencode(params))
            self.end_headers()
            return

        if parsed.path == "/setup":
            base = _base(self)
            self._html(f"""
<p>Connect your own Gmail and Calendar. Jira is usually automatic.</p>
<div class="card"><h2>Google</h2>
<p><a class="btn" href="{base}/google?state={urllib.parse.quote(state)}">
Connect Gmail + Calendar</a></p></div>
<div class="card"><h2>Jira (only if Ridha asks)</h2>
<form method="post" action="{base}/jira?state={urllib.parse.quote(state)}">
<input name="base_url" placeholder="https://pantas.atlassian.net"
       value="https://pantas.atlassian.net">
<input name="email" type="email" placeholder="Work email">
<input name="api_token" type="password" placeholder="Jira API token">
<button type="submit">Connect Jira</button>
</form></div>
<p>You can close this page after Google says connected.</p>""")
            return

        self._html("<p class='bad'>Not found.</p>", 404)

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        state = (query.get("state") or [""])[0]
        if parsed.path != "/jira" or not state:
            self._html("<p class='bad'>Not found.</p>", 404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        base = (form.get("base_url") or [""])[0].strip().rstrip("/")
        email = (form.get("email") or [""])[0].strip()
        token = (form.get("api_token") or [""])[0].strip()
        if not base.startswith("https://") or not email or not token:
            self._html("<p class='bad'>Jira needs https, email and a token.</p>", 400)
            return
        _put(state, jira={"base_url": base, "email": email, "api_token": token})
        self._html("<p class='ok'>Jira received.</p>"
                   "<p>Return to mini-reid. Setup finishes automatically.</p>")


class Server(ThreadingHTTPServer):
    daemon_threads = True


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    Server(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
