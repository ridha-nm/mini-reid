"""Track Jira epics: tickets Ridha assigned, their progress and chatter."""
from __future__ import annotations

import base64
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ledger import commitment_id, load, save

MYT = timezone(timedelta(hours=8))
CONFIG = "tracked_epics.json"
CACHE = "epic_cache.json"
KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

STATUS_MAP = {
    "to do": "open", "open": "open", "backlog": "open",
    "in progress": "in progress", "in review": "in progress",
    "peer review": "in progress", "ready for release": "in progress",
    "blocked": "blocked",
}


def _load(path: str, default):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default
    return data if isinstance(data, (dict, list)) else default


def _jira(env: dict, url: str) -> dict:
    auth = base64.b64encode(
        f"{env['JIRA_EMAIL']}:{env['JIRA_API_TOKEN']}".encode()).decode()
    req = urllib.request.Request(
        url, headers={"Authorization": f"Basic {auth}",
                      "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def _me(env: dict, cache: dict) -> str:
    if not cache.get("me"):
        cache["me"] = _jira(env, env["JIRA_BASE_URL"].rstrip("/")
                            + "/rest/api/3/myself").get("accountId") or ""
    return cache["me"]


def status_for(name: str, category: str = "") -> str:
    if (category or "").lower() == "done":
        return "done"
    return STATUS_MAP.get((name or "").lower().strip(), "open")


def assigned_by_me(histories: list[dict], me: str) -> bool:
    for history in histories or []:
        if ((history.get("author") or {}).get("accountId")) != me:
            continue
        if any(item.get("field") == "assignee"
               for item in history.get("items") or []):
            return True
    return False


def latest_comment(fields: dict) -> dict | None:
    comments = ((fields.get("comment") or {}).get("comments") or [])
    if not comments:
        return None
    newest = comments[-1]
    body = newest.get("body")
    if isinstance(body, dict):
        body = _adf_text(body)
    return {
        "author": (newest.get("author") or {}).get("displayName") or "",
        "text": str(body or "")[:300],
        "at": newest.get("updated") or newest.get("created") or "",
    }


def _adf_text(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return " ".join(_adf_text(v) for v in node.values() if v)
    if isinstance(node, list):
        return " ".join(_adf_text(v) for v in node)
    return ""


def _channel_history(env: dict, channel_id: str, oldest: float) -> list[dict]:
    token = env["SLACK_BOT_TOKEN"]
    out = []
    cursor = ""
    while True:
        params = {"channel": channel_id, "oldest": f"{oldest:.6f}",
                  "limit": 200}
        if cursor:
            params["cursor"] = cursor
        req = urllib.request.Request(
            "https://slack.com/api/conversations.history?"
            + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
        if not data.get("ok"):
            break
        out.extend(data.get("messages") or [])
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return out


def _channel_id(env: dict, name: str, cache: dict) -> str:
    known = cache.setdefault("channels", {})
    if known.get(name):
        return known[name]
    token = env["SLACK_BOT_TOKEN"]
    cursor = ""
    while True:
        params = {"types": "public_channel,private_channel", "limit": 200,
                  "exclude_archived": "true"}
        if cursor:
            params["cursor"] = cursor
        req = urllib.request.Request(
            "https://slack.com/api/conversations.list?"
            + urllib.parse.urlencode(params),
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.load(response)
        for channel in data.get("channels") or []:
            if channel.get("name") == name:
                known[name] = channel.get("id") or ""
                return known[name]
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return ""


def _slack_chatter(env: dict, channel: str, keys: set[str],
                   cache: dict) -> dict[str, dict]:
    """Latest message per ticket key in the tracking channel."""
    if not channel:
        return {}
    cid = _channel_id(env, channel, cache)
    if not cid:
        return {}
    seen = cache.setdefault("chatter_at", {})
    backfilled = cache.setdefault("backfilled", {})
    if not backfilled.get(cid):
        oldest = (datetime.now(MYT) - timedelta(days=7)).timestamp()
    else:
        oldest = float(seen.get(cid)
                       or (datetime.now(MYT) - timedelta(days=7)).timestamp())
    messages = _channel_history(env, cid, oldest)
    backfilled[cid] = True
    latest: dict[str, dict] = {}
    watermark = float(seen.get(cid) or 0)
    for message in messages:
        text = message.get("text") or ""
        try:
            ts = float(message.get("ts") or 0)
        except (TypeError, ValueError):
            ts = 0
        watermark = max(watermark, ts)
        for key in keys:
            if key in text:
                latest[key] = {
                    "text": text[:300],
                    "at": datetime.fromtimestamp(ts, MYT).isoformat(),
                    "link": (f"https://{env.get('SLACK_TEAM', 'gopantas')}"
                             f".slack.com/archives/{cid}/"
                             f"p{str(message['ts']).replace('.', '')}"),
                }
    seen[cid] = f"{watermark:.6f}"
    return latest


def sync(env: dict, ledger_path: str = "ledger.json",
         config_path: str = CONFIG, cache_path: str = CACHE) -> int:
    """Upsert a ledger row per open epic ticket Ridha assigned."""
    epics = _load(config_path, {})
    if not epics:
        return 0
    cache = _load(cache_path, {})
    me = _me(env, cache)
    base = env["JIRA_BASE_URL"].rstrip("/")
    ledger = load(ledger_path)
    by_id = {row.get("id"): row for row in ledger}
    changed = 0
    now = datetime.now(MYT)
    for epic, meta in epics.items():
        channel = (meta or {}).get("channel") or ""
        title = (meta or {}).get("title") or epic
        jql = f'parent = {epic} OR "Epic Link" = {epic}'
        data = _jira(env, base + "/rest/api/3/search/jql?" + urllib.parse.urlencode({
            "jql": jql, "maxResults": 100,
            "fields": "summary,status,assignee,updated"}))
        issues = data.get("issues") or []
        tracked = []
        for issue in issues:
            key = issue.get("key") or ""
            fields = issue.get("fields") or {}
            assignee = fields.get("assignee") or {}
            if assignee.get("accountId") == me:
                continue
            cached = (cache.get("issues") or {}).get(key) or {}
            updated = fields.get("updated") or ""
            if cached.get("updated") == updated:
                mine = cached.get("mine")
                detail = cached.get("detail") or {}
            else:
                detail = _jira(
                    env, base + f"/rest/api/3/issue/{key}?" + urllib.parse.urlencode({
                        "expand": "changelog",
                        "fields": "summary,status,assignee,updated,comment"}))
                histories = ((detail.get("changelog") or {}).get("histories")
                             or [])
                mine = assigned_by_me(histories, me)
                cache.setdefault("issues", {})[key] = {
                    "updated": updated, "mine": mine, "detail": detail}
            if not mine:
                continue
            tracked.append((issue, detail))
        keys = {issue.get("key") for issue, _ in tracked}
        chatter = _slack_chatter(env, channel, keys, cache)
        for issue, detail in tracked:
            key = issue.get("key") or ""
            fields = (detail.get("fields") or issue.get("fields") or {})
            summary = fields.get("summary") or key
            status = fields.get("status") or {}
            assignee = fields.get("assignee") or {}
            comment = latest_comment(fields)
            chat = chatter.get(key)
            new_status = status_for(
                status.get("name") or "",
                status.get("statusCategory", {}).get("key", ""))
            rid = commitment_id("jira", issue.get("id", key), summary)
            row = by_id.get(rid)
            if row is None and new_status == "done":
                continue
            if row is None:
                row = {
                    "id": rid, "direction": "owed_to_me", "what": summary[:200],
                    "asker": assignee.get("displayName") or "",
                    "via": "Jira", "source": "jira",
                    "native_id": issue.get("id", key), "kind": "triage",
                    "source_link": f"{base}/browse/{key}",
                    "evidence": summary[:200], "due": None,
                    "due_confidence": 0.0, "cycle": None, "status": "open",
                    "stalled_since": None, "ack_policy": "bot_may_ack",
                    "closure": "open", "client": None,
                    "created_at": now.isoformat(),
                    "last_activity": now.isoformat(),
                    "closed_at": None, "closed_how": None,
                }
                ledger.append(row)
                by_id[rid] = row
            row["kind"] = "triage"
            row["epic"] = epic
            row["epic_title"] = title
            row["jira_status"] = status.get("name") or ""
            row["assignee"] = assignee.get("displayName") or ""
            if comment:
                row["latest_comment"] = comment
            if chat:
                row["chatter"] = chat
            activity = [fields.get("updated") or "",
                        (comment or {}).get("at") or "",
                        (chat or {}).get("at") or ""]
            row["last_activity"] = max(activity) or row.get("last_activity")
            row["status"] = new_status
            if new_status == "done":
                row["closed_at"] = row.get("closed_at") or now.isoformat()
                row["closed_how"] = row.get("closed_how") or "jira_done"
            else:
                row["closed_at"] = None
                row["closed_how"] = None
            changed += 1
    Path(cache_path).write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    if changed:
        save(ledger_path, ledger)
    return changed
