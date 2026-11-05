"""App Home dashboard: tasks, inbox and quick links."""
from __future__ import annotations

from datetime import datetime

from .listview import format_list
from .triage_ui import _sections


def home_blocks(rows: list[dict], now: datetime,
                list_url: str | None = None) -> list[dict]:
    blocks = [{
        "type": "header",
        "text": {"type": "plain_text", "text": "Mini-Reid"},
    }, {
        "type": "context",
        "elements": [{"type": "mrkdwn",
                      "text": f"{now:%a %d %b %Y} · your tasks, inbox and list"}],
    }]
    blocks.extend(_sections(format_list(rows, now)))
    elements = []
    if list_url:
        elements.append({"type": "button", "url": list_url,
                         "text": {"type": "plain_text",
                                  "text": "Open Slack List"}})
    elements.append({"type": "button", "action_id": "home_refresh",
                     "text": {"type": "plain_text", "text": "Refresh"}})
    blocks.append({"type": "actions", "elements": elements})
    return blocks
