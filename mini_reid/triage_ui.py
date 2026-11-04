"""Slack Block Kit for the list and its triage modal."""
from __future__ import annotations

from datetime import datetime

from .listview import _title, format_list, ordered_rows

VERDICTS = [
    ("open", "Task"),
    ("in progress", "In progress"),
    ("done", "Done"),
    ("blocked", "Blocked"),
    ("dropped", "Not a task"),
]
CHUNK = 10        # Slack allows 10 options per checkboxes block
MAX_SELECTABLE = 40


def _selectable(rows: list[dict], now: datetime) -> list[dict]:
    inbox = [r for r in rows if (r.get("status") or "").lower() == "inbox"]
    open_rows = ordered_rows(rows, now)
    return (inbox + [r for r in open_rows if r not in inbox])[:MAX_SELECTABLE]


def list_blocks(rows: list[dict], now: datetime) -> list[dict]:
    text = format_list(rows, now)
    blocks = [{"type": "section",
               "text": {"type": "mrkdwn", "text": text[:2950]}}]
    selectable = _selectable(rows, now)
    if selectable:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "action_id": "triage_open",
                "text": {"type": "plain_text",
                         "text": f"Triage & update ({len(selectable)})"},
                "style": "primary",
            }],
        })
    return blocks


CONFIRM_MAX = 10


def confirm_blocks(rows: list[dict]) -> list[dict]:
    """One new item per section, each with Add to list / Not a task buttons."""
    shown = rows[:CONFIRM_MAX]
    headline = (f"*{len(rows)} new — add to the list?*" if len(rows) > 1
                else "*New — add to the list?*")
    blocks: list[dict] = [{
        "type": "section",
        "text": {"type": "mrkdwn", "text": headline},
    }]
    for row in shown:
        meta = []
        if row.get("asker"):
            meta.append(f"from {row['asker']}")
        if row.get("due"):
            meta.append(f"due {row['due']}")
        tail = f"\n_{' · '.join(meta)}_" if meta else ""
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*{_title(row)[:110]}*{tail}"},
        })
        blocks.append({
            "type": "actions",
            "elements": [
                {"type": "button", "action_id": "confirm_task",
                 "value": row.get("id", ""),
                 "text": {"type": "plain_text", "text": "Add to list"},
                 "style": "primary"},
                {"type": "button", "action_id": "reject_task",
                 "value": row.get("id", ""),
                 "text": {"type": "plain_text", "text": "Not a task"},
                 "style": "danger"},
            ],
        })
    if len(rows) > CONFIRM_MAX:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"…and {len(rows) - CONFIRM_MAX} more in the list Inbox."},
        })
    return blocks


def triage_modal(rows: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now()
    rows = _selectable(rows, now)
    blocks: list[dict] = [{
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": "Tick the rows, choose what they become, apply once."},
    }]
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        blocks.append({
            "type": "input",
            "block_id": f"sel_{start // CHUNK}",
            "label": {"type": "plain_text", "text": "Select rows"},
            "element": {
                "type": "checkboxes",
                "action_id": "items",
                "options": [{
                    "text": {"type": "mrkdwn",
                             "text": f"[{r.get('id', '')[:6]}] {_title(r)[:70]}"},
                    "value": r.get("id", ""),
                } for r in chunk],
            },
            "optional": True,
        })
    blocks.append({
        "type": "input",
        "block_id": "verdict",
        "label": {"type": "plain_text", "text": "Set selected to"},
        "element": {
            "type": "static_select",
            "action_id": "value",
            "options": [{"text": {"type": "plain_text", "text": label},
                         "value": value} for value, label in VERDICTS],
        },
    })
    return {
        "type": "modal",
        "callback_id": "triage_apply",
        "title": {"type": "plain_text", "text": "Triage tasks"},
        "submit": {"type": "plain_text", "text": "Apply"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def stale_value(row_id: str, status: str) -> str:
    return f"{row_id}|{status}"


def parse_stale_value(value: str) -> tuple[str, str] | None:
    row_id, _, status = (value or "").partition("|")
    if not row_id or status not in dict(VERDICTS):
        return None
    return row_id, status


def stale_blocks(rows: list[dict]) -> list[dict]:
    """One section per stale task with an inline status picker."""
    blocks: list[dict] = []
    for row in rows:
        due = f" · due {row['due']}" if row.get("due") else ""
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*{_title(row)[:110]}*{due}"},
            "accessory": {
                "type": "static_select",
                "action_id": "stale_set",
                "placeholder": {"type": "plain_text", "text": "Update"},
                "options": [{
                    "text": {"type": "plain_text", "text": label},
                    "value": stale_value(row.get("id", ""), value),
                } for value, label in VERDICTS],
            },
        })
    return blocks


def apply_triage(rows: list[dict], ids: list[str], verdict: str,
                 now: datetime) -> tuple[list[dict], int]:
    """Apply one verdict to every selected row id. Returns (rows, count)."""
    wanted = {i for i in ids if i}
    changed = 0
    for row in rows:
        if row.get("id") not in wanted:
            continue
        changed += 1
        row["status"] = verdict
        row["last_activity"] = now.isoformat()
        row["status_updated_at"] = now.isoformat()
        row["nudges"] = 0
        if verdict == "done":
            row["closed_at"] = now.isoformat()
            row["closed_how"] = "manual"
        elif verdict == "dropped":
            row["closed_at"] = now.isoformat()
            row["closed_how"] = "not_commitment"
        else:
            row["closed_at"] = None
            row["closed_how"] = None
            row.pop("stalled_since", None)
            row.pop("stalled_reason", None)
    return rows, changed
