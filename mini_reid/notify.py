"""Send a message to Ridha's Slack DM using the bot token."""
from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request

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


def send_dm(env: dict, text: str) -> str:
    token = env["SLACK_BOT_TOKEN"]
    ch = dm_channel(token, env["SLACK_OWNER_ID"], env.get("SLACK_DM_CHANNEL"))
    d = _post("chat.postMessage", token, channel=ch, text=text[:39000])
    if not d.get("ok"):
        raise RuntimeError(f"chat.postMessage: {d.get('error')}")
    return d["channel"]


def schedule_dm(env: dict, user_id: str, text: str, post_at: int) -> str:
    """Slack-side scheduled DM. Survives this Mac sleeping."""
    token = env["SLACK_BOT_TOKEN"]
    ch = dm_channel(token, user_id)
    d = _post("chat.scheduleMessage", token, channel=ch, text=text[:39000],
              post_at=post_at)
    if not d.get("ok"):
        raise RuntimeError(f"chat.scheduleMessage: {d.get('error')}")
    return d.get("scheduled_message_id") or ""
