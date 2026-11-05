"""App Home: a per-person dashboard, not the full task list."""
from __future__ import annotations

from datetime import date, datetime

from .ledger import _dt
from .listview import _title, ordered_rows


def _counts(rows: list[dict], today: date) -> dict:
    tasks = [r for r in rows
             if r.get("kind") not in {"note", "reminder"}
             and (r.get("status") or "open") not in {"done", "dropped", "inbox"}]
    inbox = [r for r in rows if (r.get("status") or "").lower() == "inbox"]
    notes = [r for r in rows if r.get("kind") == "note"
             and (r.get("status") or "open") not in {"done", "dropped"}]
    overdue = today_count = 0
    for row in tasks:
        due = _dt(row.get("due"))
        if not due:
            continue
        if due.date() < today:
            overdue += 1
        elif due.date() == today:
            today_count += 1
    return {"open": len(tasks), "overdue": overdue,
            "today": today_count, "inbox": len(inbox), "notes": len(notes)}


def _focus(rows: list[dict], now: datetime, limit: int = 3) -> list[dict]:
    today = now.date()
    ordered = ordered_rows(rows, now)
    urgent = [r for r in ordered if _dt(r.get("due"))
              and _dt(r["due"]).date() <= today]
    rest = [r for r in ordered if r not in urgent]
    return (urgent + rest)[:limit]


def _focus_line(row: dict, now: datetime) -> str:
    title = _title(row)[:100]
    due = _dt(row.get("due"))
    when = ""
    if due:
        days = (due.date() - now.date()).days
        when = (f"{abs(days)}d overdue" if days < 0 else
                "today" if days == 0 else f"in {days}d")
    link = row.get("source_link")
    tail = f" — <{link}|open>" if link else ""
    return f"• *{title}*" + (f" — {when}" if when else "") + tail


def public_home_blocks(owner: str = "", team: str = "gopantas") -> list[dict]:
    """App Home for someone who has not been authorised yet."""
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text": "Mini-Reid"}},
        {"type": "context",
         "elements": [{"type": "mrkdwn",
                       "text": "A personal commitment assistant for Pantas."}]},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "*Available now*\n"
                          "• `remind me to send the deck at 2pm`\n"
                          "• `remind @Teammate to … at 2pm`\n"
                          "• `help` for the command list"}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "*Once Ridha allows you*\n"
                          "• Your own task list and daily digest\n"
                          "• A native Slack List mirror with status/date/source\n"
                          "• Meeting scheduling with free/busy across calendars\n"
                          "• Inbox triage and confirmation buttons"}},
    ]
    elements = [{"type": "button", "action_id": "request_access",
                 "text": {"type": "plain_text", "text": "Request access"},
                 "style": "primary"}]
    if owner:
        elements.append({
            "type": "button",
            "url": f"https://{team}.slack.com/team/{owner}",
            "text": {"type": "plain_text", "text": "Message Ridha"},
        })
    blocks.append({"type": "actions", "elements": elements})
    return blocks


def home_blocks(rows: list[dict], now: datetime,
                list_url: str | None = None) -> list[dict]:
    counts = _counts(rows, now.date())
    focus = _focus(rows, now)
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": "Mini-Reid"}},
        {"type": "context",
         "elements": [{"type": "mrkdwn",
                       "text": f"{now:%a %d %b %Y} · your day at a glance"}]},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*{counts['open']} open* · "
                          f"*{counts['overdue']} overdue* · "
                          f"*{counts['today']} due today* · "
                          f"*{counts['inbox']} in Inbox* · "
                          f"*{counts['notes']} notes*"}},
    ]
    if focus:
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": "*Focus*"}})
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn",
                                "text": "\n".join(_focus_line(r, now)
                                                  for r in focus)}})
    else:
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": "Nothing urgent."}})
    elements = []
    if list_url:
        elements.append({"type": "button", "url": list_url,
                         "text": {"type": "plain_text",
                                  "text": "Open Slack List"}})
    elements.append({"type": "button", "action_id": "triage_open",
                     "text": {"type": "plain_text", "text": "Triage Inbox"},
                     "style": "primary"})
    elements.append({"type": "button", "action_id": "home_refresh",
                     "text": {"type": "plain_text", "text": "Refresh"}})
    blocks.append({"type": "actions", "elements": elements})
    blocks.append({"type": "section",
                   "text": {"type": "mrkdwn",
                            "text": "*Quick commands*\n"
                                    "`add: …` · `done: …` · `remind … at 2pm` · "
                                    "`meet: @Name about …`"}})
    return blocks
