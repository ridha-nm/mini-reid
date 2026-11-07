"""Send a message to Ridha's Slack DM using the bot token."""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # ponytail: system CA bundle is fine if certifi is absent
    SSL_CTX = ssl.create_default_context()


def _post(api: str, token: str, **data) -> dict:
    req = urllib.request.Request(
        f"https://slack.com/api/{api}",
        data=urllib.parse.urlencode(data).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.load(r)


def dm_channel(token: str, user_id: str, cached: str | None = None) -> str:
    if cached:
        return cached
    d = _post("conversations.open", token, users=user_id)
    if not d.get("ok"):
        raise RuntimeError(f"conversations.open: {d.get('error')}")
    return d["channel"]["id"]


def react(token: str, channel: str, ts: str, name: str = "white_check_mark") -> bool:
    d = _post("reactions.add", token, channel=channel, timestamp=ts, name=name)
    return bool(d.get("ok"))


def send_dm_to(env: dict, user_id: str, text: str,
               blocks: list[dict] | None = None) -> dict:
    token = env["SLACK_BOT_TOKEN"]
    ch = dm_channel(token, user_id)
    data = {"channel": ch, "text": text[:39000]}
    if blocks:
        data["blocks"] = json.dumps(blocks)
    d = _post("chat.postMessage", token, **data)
    if not d.get("ok"):
        raise RuntimeError(f"chat.postMessage: {d.get('error')}")
    return d


def send_dm(env: dict, text: str, blocks: list[dict] | None = None) -> dict:
    return send_dm_to(env, env["SLACK_OWNER_ID"], text, blocks=blocks)


def schedule_dm(env: dict, user_id: str, text: str, post_at: int,
                blocks: list[dict] | None = None) -> str:
    """Slack-side scheduled DM. Survives this Mac sleeping."""
    token = env["SLACK_BOT_TOKEN"]
    ch = dm_channel(token, user_id)
    data = {"channel": ch, "text": text[:39000], "post_at": post_at}
    if blocks:
        data["blocks"] = json.dumps(blocks)
    d = _post("chat.scheduleMessage", token, **data)
    if not d.get("ok"):
        raise RuntimeError(f"chat.scheduleMessage: {d.get('error')}")
    return d.get("scheduled_message_id") or ""


REMINDER_LOG = "reminder_log.json"


def log_reminder(path: str, *, asked_by: str, asked_by_name: str, to: str,
                 to_name: str, what: str, post_at: str,
                 scheduled_id: str = "", status: str = "scheduled",
                 channel: str = "") -> None:
    """Append one reminder to the audit log. Best effort, last 200 kept."""
    p = Path(path)
    try:
        rows = json.loads(p.read_text()) if p.exists() else []
    except (OSError, ValueError):
        rows = []
    rows.append({"asked_by": asked_by, "asked_by_name": asked_by_name,
                 "to": to, "to_name": to_name, "what": what,
                 "post_at": post_at, "scheduled_id": scheduled_id,
                 "status": status, "channel": channel})
    p.write_text(json.dumps(rows[-200:], indent=1, ensure_ascii=False) + "\n")


def scheduled_ids(env: dict) -> set[str]:
    """Slack scheduled-message ids still waiting to post."""
    d = _post("chat.scheduledMessages.list", env["SLACK_BOT_TOKEN"])
    if not d.get("ok"):
        return set()
    return {m.get("id") for m in (d.get("scheduled_messages") or [])}


def dm_reply_count(env: dict, user_id: str, since_ts: float) -> int:
    """Messages the recipient sent in the bot DM since the reminder posted."""
    token = env["SLACK_BOT_TOKEN"]
    try:
        ch = dm_channel(token, user_id)
        d = _post("conversations.history", token, channel=ch,
                  oldest=f"{since_ts:.6f}", limit=100)
    except Exception:  # noqa: BLE001 - the audit view must never fail
        return 0
    if not d.get("ok"):
        return 0
    return sum(1 for m in d.get("messages") or []
               if m.get("user") == user_id and not m.get("subtype"))


def sent_reminders(user_id: str, limit: int = 3,
                   path: str = REMINDER_LOG) -> list[dict]:
    """Reminders this person scheduled for someone else, newest first."""
    try:
        rows = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    mine = [r for r in rows
            if r.get("asked_by") == user_id and r.get("to") != user_id
            and r.get("status") in {"scheduled", "sent"}]
    mine.sort(key=lambda r: r.get("post_at") or "", reverse=True)
    return mine[:limit]
