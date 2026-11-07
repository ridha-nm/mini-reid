"""Open-task list: ordered, grouped and short enough to scan."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .ledger import _dt
from .render import _client_name

# Rows a person still has to act on, in display order.
LIVE = {"open", "stalled", "in progress", "blocked"}
BUCKETS = [
    ("recent", "Just added"),
    ("in progress", "In progress"),
    ("blocked", "Blocked"),
    ("overdue", "Overdue"),
    ("today", "Due today"),
    ("week", "This week"),
    ("later", "Later"),
    ("nodate", "No date"),
]


def _bucket(row: dict, today: date) -> str:
    status = (row.get("status") or "open").lower()
    created = _dt(row.get("created_at"))
    if (row.get("via") in {"shortcut", "reaction"} and created
            and created.date() == today):
        return "recent"
    if status == "in progress":
        return "in progress"
    if status == "blocked":
        return "blocked"
    due = _dt(row.get("due"))
    if due is None:
        return "nodate"
    if due.date() < today:
        return "overdue"
    if due.date() == today:
        return "today"
    if due.date() <= today + timedelta(days=6):
        return "week"
    return "later"


SECTIONS = [(0, "My reminders"), (1, "Triage epic"), (2, "My tasks"),
            (3, "Tagged by others")]


def _section(row: dict) -> int:
    """0 reminders, 1 tracked Jira epic, 3 work others put on me, 2 rest."""
    if row.get("kind") == "reminder":
        return 0
    if row.get("kind") == "triage":
        return 1
    if ((row.get("direction") or "") == "owed_to_me"
            or row.get("via") in {"assigned", "reassigned"}
            or (row.get("source") == "slack"
                and row.get("kind") in {"mention", "dm"}
                and row.get("asker"))):
        return 3
    return 2


def ordered_rows(rows: list[dict], now: datetime) -> list[dict]:
    """Rows the numbered list shows, in the order the numbers use."""
    live = [r for r in rows if (r.get("status") or "open").lower() in LIVE
            and r.get("kind") != "note"]
    order = [key for key, _ in BUCKETS]
    # Newest first inside a bucket; the stable sort keeps that tie-break.
    # Without this, a new undated assignment sits at the end and gets cut.
    newest = sorted(live, key=lambda r: r.get("created_at") or "", reverse=True)
    return sorted(newest, key=lambda r: (
        _section(r),
        order.index(_bucket(r, now.date())),
        r.get("priority") if isinstance(r.get("priority"), int) else 99,
        r.get("due") or "9999-12-31",
    ))


def _ref(row: dict) -> str:
    who = f"from {row['asker']}" if row.get("asker") else ""
    if row.get("via"):
        who = f"{who} ({row['via']})" if who else row["via"]
    out = f" — {who}" if who else ""
    if row.get("source_link"):
        out += f" — <{row['source_link']}|open>"
    return out


def _title(row: dict) -> str:
    return (row.get("action") or row.get("what") or "").strip()


def _due_label(due: datetime, today: date) -> str:
    days = (due.date() - today).days
    if days < 0:
        return f"{abs(days)}d overdue"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days < 7:
        return f"in {days}d"
    return f"{due:%a %d %b}"


def _line(number: int, row: dict, today: date) -> str:
    parts = [f"{number}. [{row.get('id', '')[:6]}] {_title(row)[:100]}"]
    due = _dt(row.get("due"))
    if due:
        parts.append(f"— {_due_label(due, today)}")
    client = _client_name(row.get("client"))
    if client:
        parts.append(f"· {client}")
    if isinstance(row.get("priority"), int):
        parts.append(f"· P{row['priority']}")
    if row.get("kind") == "triage":
        if row.get("assignee"):
            parts.append(f"· {row['assignee']}")
        chatter = (row.get("chatter") or {}).get("text") or (
            row.get("latest_comment") or {}).get("text") or ""
        if chatter:
            chatter = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", chatter)).strip()
            if chatter:
                parts.append(f"· “{chatter[:80]}”")
    return " ".join(parts) + _ref(row)


def _sent_line(reminder: dict) -> str:
    when = (reminder.get("post_at") or "")[:16].replace("T", " ")
    status = ("sent" if reminder.get("status") == "sent" else "pending")
    return (f"• {reminder.get('to_name') or 'someone'} — "
            f"{(reminder.get('what') or '')[:70]} · {when} · {status}")


def format_list(rows: list[dict], now: datetime, limit: int = 40,
                sent: list[dict] | None = None) -> str:
    """Numbered, grouped text version. Same numbering as `ordered_rows`."""
    ordered = ordered_rows(rows, now)
    inbox = [r for r in rows if (r.get("status") or "").lower() == "inbox"]
    notes = [r for r in rows if r.get("kind") == "note"
             and (r.get("status") or "open") not in {"done", "dropped"}]
    sent = sent or []
    if not ordered and not inbox and not notes and not sent:
        return "Nothing open."

    shown = ordered[:limit]
    today = now.date()
    sections: list[str] = []
    current_section = None
    current_bucket = None
    for number, row in enumerate(shown, 1):
        section = _section(row)
        if section != current_section:
            current_section = section
            current_bucket = None
            sections.append(f"*{dict(SECTIONS)[section]}*")
            if section == 0 and sent:
                sections.append("*Reminders I sent*")
                sections.extend(_sent_line(r) for r in sent)
        bucket = _bucket(row, today)
        if bucket != current_bucket:
            current_bucket = bucket
            sections.append(f"_{dict(BUCKETS)[bucket]}_")
        sections.append(_line(number, row, today))
    if not any(_section(r) == 0 for r in shown) and sent:
        sections.append("*Reminders I sent*")
        sections.extend(_sent_line(r) for r in sent)
    if len(ordered) > limit:
        sections.append(f"… and {len(ordered) - limit} more")

    if inbox:
        sections.append(f"*Inbox — needs decision ({len(inbox)})*")
        for row in inbox[:20]:
            sections.append(f"• [{row.get('id', '')[:6]}] {_title(row)[:100]}")

    if notes:
        sections.append(f"*Notes ({len(notes)})*")
        for row in notes[:20]:
            sections.append(f"• [{row.get('id', '')[:6]}] {_title(row)[:100]}")
        if len(notes) > 20:
            sections.append(f"… and {len(notes) - 20} more notes")

    return "\n".join(sections)
