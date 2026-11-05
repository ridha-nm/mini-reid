"""Unfurl tracked Gmail/Jira links in Slack into Mini-Reid task cards."""
from __future__ import annotations

from .listview import _title


def _clean(url: str) -> str:
    return (url or "").split("?")[0].rstrip("/")


def find_task(ledgers: list[tuple[str, list[dict]]], url: str
              ) -> tuple[str, dict] | None:
    """The first (user, row) whose source link is `url`."""
    clean = _clean(url)
    if not clean:
        return None
    for user, rows in ledgers:
        for row in rows:
            link = _clean(row.get("source_link") or "")
            if link and link == clean:
                return user, row
    return None


def task_blocks(row: dict, user: str = "") -> list[dict]:
    status = row.get("status") or "open"
    due = f" · due {row['due']}" if row.get("due") else ""
    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": f"*Mini-Reid task*\n{_title(row)[:140]}\n"
                         f"_{status}{due}_"},
    }]
    if status not in {"done", "dropped"} and row.get("id") and user:
        blocks.append({"type": "actions", "elements": [{
            "type": "button", "action_id": "unfurl_done",
            "value": f"{user}:{row['id']}",
            "text": {"type": "plain_text", "text": "Mark done"},
        }]})
    return blocks


def unknown_blocks() -> list[dict]:
    return [{"type": "section",
             "text": {"type": "mrkdwn",
                      "text": "*Mini-Reid* · not on your list\n"
                              "Add it with `add: …`"}}]
