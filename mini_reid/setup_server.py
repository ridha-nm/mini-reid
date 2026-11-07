"""Self-serve setup page for allowlisted members.

`allow: @Name` issues a one-time link. The page connects Google (Gmail and
Calendar) and Jira, then starts the member's first digest.
"""
from __future__ import annotations

import html
import json
import os
import socket
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .notify import send_dm_to
from .profiles import (issue_setup_token, load as load_profiles,
                       save as save_profiles, token_owner)
from .sources import SSL_CTX, _get_json

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = " ".join([
    "openid", "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
])


def public_url(env: dict, token: str = "") -> str:
    base = (env.get("SETUP_BASE_URL") or "").rstrip("/")
    if not base:
        port = env.get("SETUP_PORT", "8765")
        host = socket.gethostname()
        if "." not in host:
            host += ".local"
        base = f"http://{host}:{port}"
    return f"{base}/setup/{token}" if token else base


def _client_path(env: dict) -> str:
    return env.get("SETUP_GOOGLE_CREDS") or env.get("GMAIL_CREDS") or ""


def _client(env: dict) -> dict:
    path = _client_path(env)
    if not path:
        raise RuntimeError("GMAIL_CREDS is not configured")
    data = json.loads(Path(os.path.expanduser(path)).read_text())
    return data.get("installed") or data.get("web") or {}


def _redirect_uri(env: dict) -> str:
    """HTTPS callback when available; otherwise the registered loopback URI.

    Google rejects non-HTTPS redirects except localhost. The fallback flow lets
    the member paste the failed localhost URL back into the setup page.
    """
    base = public_url(env)
    if base.startswith("https://"):
        return f"{base}/setup/google/callback"
    if env.get("SETUP_GOOGLE_REDIRECT_URI"):
        return env["SETUP_GOOGLE_REDIRECT_URI"]
    try:
        uris = _client(env).get("redirect_uris") or []
        for uri in uris:
            if uri.startswith(("http://localhost", "http://127.0.0.1")):
                return uri
    except Exception:  # noqa: BLE001 - fall through to the documented default
        pass
    return "http://localhost:44000/oauth2callback"


def _exchange(env: dict, code: str, redirect_uri: str | None = None) -> dict:
    client = _client(env)
    data = urllib.parse.urlencode({
        "code": code, "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri or _redirect_uri(env),
        "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(
            urllib.request.Request(client["token_uri"], data=data),
            timeout=30, context=SSL_CTX) as r:
        return json.load(r)


def _store_google(env: dict, user: str, profile: dict, token: dict) -> None:
    info = _get_json("https://www.googleapis.com/oauth2/v2/userinfo",
                     {"Authorization": f"Bearer {token['access_token']}"})
    _write_secret(_member_path(profile, user, "google_token.json"), token)
    profiles = load_profiles()
    profiles[user]["email"] = info.get("email") or profile.get("email")
    profiles[user]["google_client"] = _client_path(env)
    save_profiles(profiles)
    _finish(env, user, profiles[user])


def _member_path(profile: dict, user: str, name: str) -> Path:
    ledger = profile.get("ledger") or f"data/{user}/ledger.json"
    return Path(ledger).parent / name


def _write_secret(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1) + "\n")
    path.chmod(0o600)


def _connected(profile: dict, user: str) -> tuple[bool, bool]:
    return (_member_path(profile, user, "google_token.json").exists(),
            _member_path(profile, user, "jira.json").exists()
            or bool(profile.get("jira_account_id")))


def _finish(env: dict, user: str, profile: dict) -> None:
    profiles = load_profiles()
    entry = profiles.get(user) or profile
    google, _jira = _connected(entry, user)
    if not google or entry.get("setup_done_at"):
        return
    entry["setup_done_at"] = datetime.now(timezone.utc).isoformat()
    entry.pop("setup_token", None)
    entry.pop("setup_expires", None)
    profiles[user] = entry
    save_profiles(profiles)
    current = entry.get("clients") or []
    accounts = (("Email filter: " + ", ".join(current))
                if current else
                "Reply `clients: Name, Name` to set the clients your email "
                "should be filtered to.")
    send_dm_to(env, user,
               "*Mini-Reid is ready.*\n"
               "Your Slack mentions, email, Jira, reminders and morning digest "
               f"are active. {accounts}\nTry `list` or `add: …`.")
    owner = env.get("SLACK_OWNER_ID")
    if owner and owner != user:
        try:
            send_dm_to(env, owner,
                       f"*{(entry.get('name') or user)} is fully set up.*\n"
                       "Gmail, Calendar, Jira, digest and Slack List are active.")
        except Exception as ex:  # noqa: BLE001 - member setup already succeeded
            print(f"setup owner notice failed: {type(ex).__name__}: {ex}",
                  flush=True)

    def first_digest() -> None:
        try:
            from .members import deliver_digest

            deliver_digest(env, user, entry)
        except Exception as ex:  # noqa: BLE001 - setup must still succeed
            print(f"first digest failed: {type(ex).__name__}: {ex}", flush=True)

    threading.Thread(target=first_digest, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server: "SetupServer"

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 - HTTP noise
        return

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _html(self, body: str, status: int = 200) -> None:
        page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mini-Reid setup</title>
<style>
body{{font:16px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;max-width:620px;
margin:40px auto;padding:0 20px;color:#111}}
.card{{border:1px solid #ddd;border-radius:12px;padding:20px;margin:16px 0}}
.ok{{color:#0a7d32}} .bad{{color:#a33}} input{{display:block;width:100%;
padding:10px;margin:6px 0 14px;box-sizing:border-box;border:1px solid #bbb;
border-radius:8px}} button,a.btn{{background:#1f2937;color:#fff;border:0;
border-radius:8px;padding:10px 16px;text-decoration:none;display:inline-block;
cursor:pointer}} code{{background:#f3f3f3;padding:2px 5px;border-radius:4px}}
</style></head><body><h1>Mini-Reid setup</h1>{body}</body></html>"""
        data = page.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _token(self) -> tuple[str, dict, dict] | None:
        part = urllib.parse.urlparse(self.path).path.split("/")
        token = part[2] if len(part) > 2 else ""
        found = token_owner(load_profiles(), token)
        if not found:
            self._html("<p class='bad'>This setup link is invalid or expired.</p>", 403)
            return None
        user, profile = found
        return token, user, profile

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = urllib.parse.urlparse(self.path).path
        if path == "/setup/google/callback":
            self._google_callback()
            return
        found = self._token()
        if not found:
            return
        token, user, profile = found
        parts = path.split("/")
        if len(parts) == 4 and parts[3] == "google":
            self._google_start(token)
            return
        google, jira = _connected(profile, user)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        note = ""
        if query.get("ok"):
            note = f"<p class='ok'>Connected {html.escape(query['ok'][0])}.</p>"
        if query.get("err"):
            note = f"<p class='bad'>{html.escape(query['err'][0])}</p>"
        base = public_url(self.server.env)
        if google:
            gmail = "<p class='ok'>Gmail + Calendar connected.</p>"
        elif base.startswith("https://"):
            gmail = (f"<p><a class='btn' href='{base}/setup/{token}/google'>"
                     "Connect Gmail + Calendar</a></p>")
        else:
            gmail = f"""
<p><a class='btn' href='{base}/setup/{token}/google'>Connect Gmail + Calendar</a></p>
<p>After Google, the browser may land on a page that does not load. That is
expected. Copy the whole address-bar URL and paste it here:</p>
<form method="post" action="{base}/setup/{token}/google-code">
<input name="redirect_url" placeholder="http://localhost:44000/oauth2callback?code=..."
       required>
<button type="submit">Finish Gmail connection</button>
</form>"""
        jira_box = ("<p class='ok'>Jira connected automatically — issues assigned "
                    "to you.</p>" if jira else f"""
<form method="post" action="{base}/setup/{token}/jira">
<input name="base_url" placeholder="https://pantas.atlassian.net"
       value="https://pantas.atlassian.net" required>
<input name="email" type="email" placeholder="Work email" required>
<input name="api_token" type="password" placeholder="Jira API token" required>
<p>Create one at <a href="https://id.atlassian.com/manage-profile/security/api-tokens">
id.atlassian.com</a>. It is stored only on this Mac.</p>
<button type="submit">Connect Jira</button>
</form>""")
        self._html(f"""
<p>Setting up <b>{html.escape(profile.get('name') or user)}</b>.
Both connections are optional; Slack reminders and commands already work.</p>
{note}
<div class="card"><h2>Email</h2>{gmail}</div>
<div class="card"><h2>Jira</h2>{jira_box}</div>
<p>Done when both show connected. The link is one-time and expires in 24 hours.</p>""")

    def _google_start(self, token: str) -> None:
        try:
            client = _client(self.server.env)
            redirect = _redirect_uri(self.server.env)
            query = urllib.parse.urlencode({
                "client_id": client["client_id"], "redirect_uri": redirect,
                "response_type": "code", "scope": SCOPES,
                "access_type": "offline", "prompt": "consent",
                "include_granted_scopes": "true", "state": token,
            })
            self._redirect(f"{AUTH_URL}?{query}")
        except Exception as ex:  # noqa: BLE001 - show the reason on the page
            self._redirect(f"/setup/{token}?err="
                           + urllib.parse.quote(f"Google not configured: {ex}"))

    def _google_callback(self) -> None:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        state = (query.get("state") or [""])[0]
        found = token_owner(load_profiles(), state)
        if not found:
            self._html("<p class='bad'>Invalid setup state.</p>", 403)
            return
        user, profile = found
        if query.get("error"):
            self._redirect(f"/setup/{state}?err="
                           + urllib.parse.quote(query["error"][0]))
            return
        try:
            token = _exchange(self.server.env, (query.get("code") or [""])[0])
            _store_google(self.server.env, user, profile, token)
            self._redirect(f"/setup/{state}?ok=google")
        except Exception as ex:  # noqa: BLE001 - show the reason on the page
            self._redirect(f"/setup/{state}?err="
                           + urllib.parse.quote(f"Google: {ex}"))

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        found = self._token()
        if not found:
            return
        token, user, profile = found
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode())
        if path.endswith("/google-code"):
            raw = (form.get("redirect_url") or [""])[0].strip()
            query = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
            state = (query.get("state") or [""])[0]
            code = (query.get("code") or [""])[0]
            if state != token or not code:
                self._redirect(f"/setup/{token}?err="
                               + urllib.parse.quote("Paste the whole redirected URL."))
                return
            try:
                _store_google(self.server.env, user, profile,
                              _exchange(self.server.env, code))
                self._redirect(f"/setup/{token}?ok=google")
            except Exception as ex:  # noqa: BLE001 - show the reason on the page
                self._redirect(f"/setup/{token}?err="
                               + urllib.parse.quote(f"Google: {ex}"))
            return
        if not path.endswith("/jira"):
            self._html("<p class='bad'>Not found.</p>", 404)
            return
        base = (form.get("base_url") or [""])[0].strip().rstrip("/")
        email = (form.get("email") or [""])[0].strip()
        api = (form.get("api_token") or [""])[0].strip()
        if not base.startswith("https://") or not email or not api:
            self._redirect(f"/setup/{token}?err="
                           + urllib.parse.quote("Jira needs https, email and a token."))
            return
        try:
            import base64

            auth = base64.b64encode(f"{email}:{api}".encode()).decode()
            me = _get_json(f"{base}/rest/api/3/myself",
                           {"Authorization": f"Basic {auth}",
                            "Accept": "application/json"})
            _write_secret(_member_path(profile, user, "jira.json"),
                          {"base_url": base, "email": email, "api_token": api})
            profiles = load_profiles()
            if me.get("displayName") and not profiles[user].get("name"):
                profiles[user]["name"] = me["displayName"]
            save_profiles(profiles)
            _finish(self.server.env, user, profiles[user])
            self._redirect(f"/setup/{token}?ok=jira")
        except Exception as ex:  # noqa: BLE001 - show the reason on the page
            self._redirect(f"/setup/{token}?err="
                           + urllib.parse.quote(f"Jira: {ex}"))


class SetupServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, env: dict):
        self.env = env
        super().__init__(addr, Handler)


def start(env: dict) -> SetupServer | None:
    port = int(env.get("SETUP_PORT", "8765"))
    try:
        server = SetupServer(("0.0.0.0", port), env)
    except OSError as ex:
        print(f"setup page not started: {ex}", flush=True)
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"setup page on {public_url(env)}", flush=True)
    return server


def link_for(env: dict, profiles: dict, user: str) -> str:
    token = issue_setup_token(profiles, user)
    save_profiles(profiles)
    relay = (env.get("RELAY_URL") or "").rstrip("/")
    if relay:
        return f"{relay}/setup?state={urllib.parse.quote(token)}"
    return public_url(env, token)


def _relay_callback(env: dict) -> str:
    return (env.get("RELAY_URL") or "").rstrip("/") + "/callback"


def complete_google_code(env: dict, user: str, state: str,
                         code: str) -> str:
    profiles = load_profiles()
    found = token_owner(profiles, state)
    if not found or found[0] != user:
        raise RuntimeError("setup link expired or belongs to someone else")
    _store_google(env, user, found[1],
                  _exchange(env, code, _relay_callback(env)))
    return "Gmail and Calendar connected."


def poll_relay(env: dict) -> int:
    """Pick up Google codes and Jira credentials the relay is holding."""
    relay = (env.get("RELAY_URL") or "").rstrip("/")
    key = env.get("RELAY_KEY") or ""
    if not (relay and key):
        return 0
    handled = 0
    for user, profile in load_profiles().items():
        token = profile.get("setup_token")
        if not token or profile.get("setup_done_at"):
            continue
        url = (f"{relay}/take?"
               + urllib.parse.urlencode({"state": token, "key": key}))
        try:
            with urllib.request.urlopen(url, timeout=15, context=SSL_CTX) as r:
                data = json.load(r)
        except Exception as ex:  # noqa: BLE001 - relay is best effort
            print(f"  relay poll failed: {type(ex).__name__}: {ex}", flush=True)
            continue
        if data.get("jira"):
            _write_secret(_member_path(profile, user, "jira.json"), data["jira"])
            handled += 1
        if data.get("google_code"):
            try:
                complete_google_code(env, user, token, data["google_code"])
                handled += 1
            except Exception as ex:  # noqa: BLE001 - user can retry
                print(f"  relay google exchange failed: {type(ex).__name__}: {ex}",
                      flush=True)
    return handled


def complete_google_url(env: dict, user: str, raw: str) -> str:
    """Finish OAuth from the redirected localhost URL a member pasted."""
    profiles = load_profiles()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
    state = (query.get("state") or [""])[0]
    code = (query.get("code") or [""])[0]
    found = token_owner(profiles, state)
    if not found or found[0] != user:
        raise RuntimeError("setup link expired or belongs to someone else")
    if not code:
        raise RuntimeError("no code in that URL")
    _store_google(env, user, found[1], _exchange(env, code))
    return "Gmail and Calendar connected."
