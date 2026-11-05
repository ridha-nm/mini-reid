"""App Home: a per-person dashboard, not the full task list."""
from __future__ import annotations

from datetime import date, datetime

from .ledger import MYT, _dt
from .listview import _title, ordered_rows


def _counts(rows: list[dict], now: datetime) -> dict:
    today = now.date()
    tasks = [r for r in rows
             if r.get("kind") not in {"note", "reminder"}
             and (r.get("status") or "open") not in {"done", "dropped", "inbox"}]
    inbox = [r for r in rows if (r.get("status") or "").lower() == "inbox"]
    notes = [r for r in rows if r.get("kind") == "note"
             and (r.get("status") or "open") not in {"done", "dropped"}]
    overdue = today_count = week = 0
    for row in tasks:
        due = _dt(row.get("due"))
        if not due:
            continue
        days = (due.date() - today).days
        if due.date() < today:
            overdue += 1
        elif due.date() == today:
            today_count += 1
        elif 1 <= days <= 7:
            week += 1
    done_week = len([r for r in rows
                     if r.get("status") == "done"
                     and _dt(r.get("closed_at"))
                     and (now - _dt(r["closed_at"])).days <= 7])
    return {
        "open": len(tasks), "overdue": overdue, "today": today_count,
        "week": week, "inbox": len(inbox), "notes": len(notes),
        "in_progress": len([r for r in tasks
                            if r.get("status") == "in progress"]),
        "blocked": len([r for r in tasks if r.get("status") == "blocked"]),
        "waiting": len([r for r in tasks
                        if r.get("direction") == "owed_to_me"]),
        "done_week": done_week,
    }


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


CAPABILITIES = [
    "Capture tasks from Slack, Gmail and Jira, then confirm with buttons",
    "Add by DM, message shortcut or 📌 reaction",
    "Grouped `list`, Inbox triage, and a native Slack List mirror",
    "`ask` questions, `remind` anyone, `meet` with free/busy and a Meet invite",
]


def access_request_blocks(user: str, details: dict | None = None) -> list[dict]:
    details = details or {}
    fields = [
        {"type": "mrkdwn", "text": f"*Slack*\n<@{user}>"},
        {"type": "mrkdwn",
         "text": f"*Name*\n{details.get('name') or 'unknown'}"},
        {"type": "mrkdwn",
         "text": f"*Email*\n{details.get('email') or 'not in directory'}"},
        {"type": "mrkdwn",
         "text": f"*Jira*\n{details.get('jira') or 'not in directory'}"},
    ]
    return [
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": f"*Access request*\n<@{user}> is asking for their own "
                          "Mini-Reid. Details captured below."}},
        {"type": "section", "fields": fields},
        {"type": "actions", "elements": [{
            "type": "button", "action_id": "approve_access", "value": user,
            "text": {"type": "plain_text", "text": "Authorise and send setup"},
            "style": "primary",
        }]},
    ]


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
                  "text": "*What Mini-Reid can do*\n"
                          + "\n".join(f"• {item}" for item in CAPABILITIES)}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "*Available to you now*\n"
                          "• `remind me to send the deck at 2pm`\n"
                          "• `remind @Teammate to … at 2pm`\n"
                          "• `help` for the command list"}},
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "*Unlocked when Ridha allows you*\n"
                          "• Your own task list and daily digest\n"
                          "• The native Slack List mirror\n"
                          "• Meeting scheduling across calendars\n"
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
                list_url: str | None = None,
                meetings: list[dict] | None = None) -> list[dict]:
    if now.tzinfo is None:
        now = now.replace(tzinfo=MYT)
    counts = _counts(rows, now)
    focus = _focus(rows, now)
    stats = [
        ("Open", counts["open"]), ("Overdue", counts["overdue"]),
        ("Due today", counts["today"]), ("This week", counts["week"]),
        ("In progress", counts["in_progress"]), ("Blocked", counts["blocked"]),
        ("Waiting on others", counts["waiting"]), ("Done 7d", counts["done_week"]),
        ("Inbox", counts["inbox"]), ("Notes", counts["notes"]),
    ]
    blocks: list[dict] = [
        {"type": "header",
         "text": {"type": "plain_text", "text": "Mini-Reid"}},
        {"type": "context",
         "elements": [{"type": "mrkdwn",
                       "text": f"{now:%a %d %b %Y} · your day at a glance"}]},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*{label}*\n{value}"}
            for label, value in stats
        ]},
    ]
    if meetings:
        lines = []
        for meeting in meetings[:3]:
            start = (meeting.get("start") or "")[11:16]
            title = (meeting.get("title") or "Meeting")[:80]
            link = meeting.get("link")
            tail = f" — <{link}|join>" if link else ""
            lines.append(f"• {start} · {title}{tail}")
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn",
                                "text": "*Today's meetings*\n"
                                        + "\n".join(lines)}})
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
                            "text": "*What I can do*\n"
                                    + "\n".join(f"• {item}"
                                                for item in CAPABILITIES)}})
    return blocks
