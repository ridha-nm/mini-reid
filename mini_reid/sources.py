"""Source readers. Parsers are pure; fetchers touch the network."""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # ponytail: system CA bundle is fine if certifi is absent
    SSL_CTX = ssl.create_default_context()

MYT = timezone(timedelta(hours=8))
DM_CHANNEL = re.compile(r"^[UD][A-Z0-9]+$")


def load_env(path: str | Path = ".env") -> dict[str, str]:
    out: dict[str, str] = {}
    p = Path(os.path.expanduser(str(path)))
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _get_json(url: str, headers: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                time.sleep(int(ex.headers.get("Retry-After") or 0) or 2 ** attempt)
                continue
            raise
    raise RuntimeError(f"retries exhausted: {url}")


# ---------------------------------------------------------------- slack

def parse_slack_search(payload: dict) -> list[dict]:
    out, seen = [], set()
    for m in (payload.get("messages") or {}).get("matches") or []:
        ch = m.get("channel") or {}
        name = ch.get("name") or ch.get("id") or ""
        key = (ch.get("id") or "", m.get("ts") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source": "slack",
            "native_id": f"{ch.get('id','')}:{m.get('ts','')}",
            "kind": "mention",
            "channel": name,
            "channel_id": ch.get("id") or "",
            "author": m.get("username") or m.get("user") or "?",
            "ts": datetime.fromtimestamp(float(m["ts"]), MYT).isoformat(),
            "text": (m.get("text") or "").strip(),
            "link": m.get("permalink") or "",
            "is_dm": bool(DM_CHANNEL.match(name)),
            "thread_ts": m.get("thread_ts"),
            "direction": "owed_by_me",
        })
    return out


def slack_me(token: str) -> str:
    d = _get_json("https://slack.com/api/auth.test", {"Authorization": f"Bearer {token}"})
    if not d.get("ok"):
        raise RuntimeError(f"slack auth.test: {d.get('error')}")
    return d["user_id"]


def parse_slack_dm_history(channel_id: str, data: dict, me: str,
                           team: str = "gopantas") -> list[dict]:
    """Messages other people sent Ridha in a DM. Mentions never appear there."""
    out = []
    for m in data.get("messages") or []:
        if m.get("bot_id") or m.get("subtype") or m.get("user") in (None, me):
            continue
        ts = m.get("ts") or ""
        out.append({
            "source": "slack",
            "native_id": f"{channel_id}:{ts}",
            "kind": "dm",
            "channel": channel_id,
            "channel_id": channel_id,
            "author": m.get("user") or "?",
            "ts": datetime.fromtimestamp(float(ts), MYT).isoformat() if ts else "",
            "text": (m.get("text") or "").strip(),
            "link": f"https://{team}.slack.com/archives/{channel_id}/p{ts.replace('.', '')}",
            "is_dm": True,
            "direction": "owed_by_me",
        })
    return out


_NAME_CACHE: dict[str, str] = {}


def slack_user_name(token: str, user_id: str) -> str:
    """Slack gives IDs in DM history. People read names."""
    if not user_id:
        return "?"
    if user_id in _NAME_CACHE:
        return _NAME_CACHE[user_id]
    name = user_id
    try:
        d = _get_json(
            "https://slack.com/api/users.info?"
            + urllib.parse.urlencode({"user": user_id}),
            {"Authorization": f"Bearer {token}"})
        u = d.get("user") or {}
        prof = u.get("profile") or {}
        name = prof.get("display_name") or u.get("real_name") or u.get("name") or user_id
    except Exception:  # noqa: BLE001 - a name lookup must never break capture
        pass
    _NAME_CACHE[user_id] = name
    return name


def fetch_slack_dms(days: int, token: str, me: str) -> list[dict]:
    """Recent messages in Ridha's direct messages, from other people."""
    ims = _get_json(
        "https://slack.com/api/conversations.list?" + urllib.parse.urlencode(
            {"types": "im", "limit": 200}),
        {"Authorization": f"Bearer {token}"})
    items = []
    oldest = (datetime.now(MYT) - timedelta(days=days)).timestamp()
    for ch in ims.get("channels") or []:
        cid = ch.get("id")
        if not cid or ch.get("user") == me:
            continue
        hist = _get_json(
            "https://slack.com/api/conversations.history?"
            + urllib.parse.urlencode({"channel": cid, "oldest": f"{oldest:.6f}", "limit": 20}),
            {"Authorization": f"Bearer {token}"})
        for item in parse_slack_dm_history(cid, hist, me):
            item["author"] = slack_user_name(token, item["author"])
            items.append(item)
    return items


def fetch_slack(days: int, token: str, me: str) -> list[dict]:
    since = (datetime.now(MYT) - timedelta(days=days)).strftime("%Y-%m-%d")
    items, page = [], 1
    while len(items) < 400:
        url = "https://slack.com/api/search.messages?" + urllib.parse.urlencode({
            "query": f"<@{me}> after:{since}", "count": 100, "page": page,
            "sort": "timestamp", "sort_dir": "desc"})
        d = _get_json(url, {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            raise RuntimeError(f"slack search: {d.get('error')}")
        got = parse_slack_search(d)
        if not got:
            break
        items.extend(got)
        if len(got) < 100:
            break
        page += 1
        time.sleep(1.2)
    return items


# ---------------------------------------------------------------- gmail

def parse_gmail_messages(messages: list[dict], kind: str) -> list[dict]:
    out = []
    for msg in messages:
        hdrs = {h["name"].lower(): h["value"]
                for h in (msg.get("payload") or {}).get("headers") or []}
        ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, MYT).isoformat()
        out.append({
            "source": "gmail",
            "native_id": msg["id"],
            "kind": kind,
            "channel": "email",
            "channel_id": "",
            "author": hdrs.get("from", "?"),
            "ts": ts,
            "created_at": ts,
            "text": msg.get("snippet", "") or hdrs.get("subject", ""),
            "subject": hdrs.get("subject", ""),
            "to": hdrs.get("to", ""),
            "link": f"https://mail.google.com/mail/u/0/#all/{msg['id']}",
            "is_dm": True,
            "direction": "owed_by_me",
        })
    return out


def gmail_access(env: dict[str, str]) -> str:
    creds = json.loads(Path(os.path.expanduser(env["GMAIL_CREDS"])).read_text())
    inst = creds.get("installed") or creds.get("web")
    tok = json.loads(Path(os.path.expanduser(env["GMAIL_TOKEN"])).read_text())
    data = urllib.parse.urlencode({
        "client_id": inst["client_id"], "client_secret": inst["client_secret"],
        "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request(inst["token_uri"], data=data)
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.load(r)["access_token"]


HTTP_RETRY_DELAY = 2.0

def _gmail_list(access: str, query: str, limit: int = 50) -> list[str]:
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urllib.parse.urlencode(
        {"q": query, "maxResults": limit})
    d = _get_json(url, {"Authorization": f"Bearer {access}"})
    return [m["id"] for m in d.get("messages") or []]


def _gmail_message(access: str, mid: str) -> dict:
    url = (f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?"
           + urllib.parse.urlencode({"format": "metadata"})
           + "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=To")
    return _get_json(url, {"Authorization": f"Bearer {access}"})


def fetch_gmail(days: int, env: dict[str, str]) -> list[dict]:
    access = gmail_access(env)
    out: list[dict] = []
    for query, kind in [
        # Read mail counts too. An email opened and never answered is the exact
        # failure this exists to catch.
        (f"in:inbox newer_than:{days}d -in:spam -in:trash "
         f"-category:promotions -category:social", "inbox"),
        (f"in:sent newer_than:{days}d -in:spam -in:trash", "sent"),
    ]:
        ids = _gmail_list(access, query)
        msgs = [_gmail_message(access, i) for i in ids]
        out.extend(parse_gmail_messages(msgs, kind))

    drafts = _get_json(
        "https://gmail.googleapis.com/gmail/v1/users/me/drafts?" + urllib.parse.urlencode({"maxResults": 50}),
        {"Authorization": f"Bearer {access}"})
    cutoff = (datetime.now(MYT) - timedelta(days=30)).timestamp() * 1000
    dmgs = []
    for d in drafts.get("drafts") or []:
        mid = (d.get("message") or {}).get("id")
        if not mid:
            continue
        msg = _gmail_message(access, mid)
        if int(msg.get("internalDate", 0)) >= cutoff:
            dmgs.append(msg)
    out.extend(parse_gmail_messages(dmgs, "draft"))
    return out


# ---------------------------------------------------------------- jira

def parse_jira_issues(data: dict, base: str) -> list[dict]:
    out = []
    for issue in data.get("issues") or []:
        f = issue.get("fields") or {}
        key = issue.get("key", "")
        out.append({
            "source": "jira",
            "native_id": issue.get("id", key),
            "kind": "issue",
            "channel": "jira",
            "channel_id": "",
            "author": ((f.get("reporter") or {}).get("displayName") or "jira"),
            "ts": f.get("updated") or "",
            "text": f.get("summary", ""),
            "subject": f.get("summary", ""),
            "due": f.get("duedate"),
            "status": (f.get("status") or {}).get("name"),
            "link": f"{base.rstrip('/')}/browse/{key}",
            "is_dm": False,
            "direction": "owed_by_me",
        })
    return out


def fetch_jira(days: int, env: dict[str, str]) -> list[dict]:
    base = env.get("JIRA_BASE_URL")
    email = env.get("JIRA_EMAIL")
    token = env.get("JIRA_API_TOKEN")
    if not (base and email and token):
        raise RuntimeError("Jira credentials missing")
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    jql = f"(assignee = currentUser() OR comment ~ currentUser()) AND updated >= -{days}d ORDER BY updated DESC"
    url = f"{base.rstrip('/')}/rest/api/3/search/jql?" + urllib.parse.urlencode(
        {"jql": jql, "maxResults": 50, "fields": "summary,duedate,status,reporter,updated"})
    data = _get_json(url, {"Authorization": f"Basic {auth}", "Accept": "application/json"})
    return parse_jira_issues(data, base)
