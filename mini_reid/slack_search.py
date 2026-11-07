"""Live Slack search for `ask:` using the Real-time Search API."""
from __future__ import annotations

import json
import urllib.request


def search(env: dict, query: str, limit: int = 5) -> list[dict]:
    token = env.get("SLACK_USER_TOKEN")
    if not token or not (query or "").strip():
        return []
    body = json.dumps({
        "query": query.strip()[:500],
        "content_types": ["messages"],
        "limit": min(max(limit, 1), 20),
        "include_bots": False,
        "sort": "timestamp",
        "sort_dir": "desc",
    }).encode()
    req = urllib.request.Request(
        "https://slack.com/api/assistant.search.context", data=body,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    if not data.get("ok"):
        raise RuntimeError(f"search.context: {data.get('error')}")
    ignored = {"bd-triager-agent", "C0B59LA0X5M"}
    hits = (data.get("results") or {}).get("messages") or []
    return [h for h in hits
            if (h.get("channel_id") or h.get("channel_name") or "") not in ignored
            and (h.get("channel_name") or "").lstrip("#") not in ignored]


def format_hits(hits: list[dict], limit: int = 3) -> str:
    lines = []
    for hit in hits[:limit]:
        text = " ".join((hit.get("content") or "").split())[:300]
        if not text:
            continue
        channel = hit.get("channel_name") or hit.get("channel_id") or "Slack"
        link = hit.get("permalink") or ""
        tail = f" — <{link}|open>" if link else ""
        lines.append(f"• *{channel}*: {text}{tail}")
    return "\n".join(lines)
