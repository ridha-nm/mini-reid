"""Slack UI for a meeting proposal and its free slots."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .meetings import OWNER_EMAIL, SLOT_MINUTES

MYT = ZoneInfo("Asia/Kuala_Lumpur")


def _label(start: str, end: str) -> str:
    s = datetime.fromisoformat(start).astimezone(MYT)
    e = datetime.fromisoformat(end).astimezone(MYT)
    return f"{s:%a %d %b %H:%M}–{e:%H:%M}"


def _busy_on(intervals: list[tuple], day) -> str:
    parts = []
    for start, end in intervals:
        s, e = start.astimezone(MYT), end.astimezone(MYT)
        if s.date() != day and e.date() != day:
            continue
        parts.append(f"{s:%H:%M}–{e:%H:%M}")
    return ", ".join(parts) or "free"


def _snapshot(busy: dict, attendee: str, attendee_email: str,
              slots: list[dict]) -> str:
    days = sorted({datetime.fromisoformat(s["start"]).astimezone(MYT).date()
                   for s in slots})
    lines = []
    for day in days[:5]:
        lines.append(f"{day:%a %d %b}")
        lines.append(f"  You:      {_busy_on(busy.get(OWNER_EMAIL, []), day)}")
        lines.append(f"  {attendee[:10]:9} {_busy_on(busy.get(attendee_email, []), day)}")
    return "\n".join(lines)


def slot_blocks(token: str, topic: str, attendee: str,
                slots: list[dict], attendee_email: str = "",
                busy: dict | None = None) -> list[dict]:
    with_email = (f"{attendee} ({attendee_email})" if attendee_email
                  else attendee)
    blocks: list[dict] = [
        {"type": "section",
         "text": {"type": "mrkdwn", "text": "*Meeting proposal*"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*Title*\n{topic}"},
            {"type": "mrkdwn", "text": f"*With*\n{with_email}"},
            {"type": "mrkdwn", "text": f"*Duration*\n{SLOT_MINUTES} minutes"},
            {"type": "mrkdwn", "text": "*Time zone*\nMYT (Asia/Kuala_Lumpur)"},
        ]},
    ]
    if busy:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": "*Availability snapshot — busy blocks*\n```"
                             + _snapshot(busy, attendee, attendee_email, slots)
                             + "```"},
        })
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": "These slots are free on both calendars. Pick one and I "
                         "create the event and invite them."},
    })
    for slot in slots:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*{_label(slot['start'], slot['end'])}*"},
            "accessory": {
                "type": "button",
                "action_id": "meet_slot",
                "value": f"{token}|{slot['start']}",
                "text": {"type": "plain_text", "text": "Pick"},
                "style": "primary",
            },
        })
    blocks.append({"type": "actions", "elements": [
        {"type": "button", "action_id": "meet_refresh", "value": token,
         "text": {"type": "plain_text", "text": "Refresh availability"}},
        {"type": "button", "action_id": "meet_cancel", "value": token,
         "text": {"type": "plain_text", "text": "Cancel"}, "style": "danger"},
    ]})
    return blocks


def confirmation_blocks(topic: str, start: str, end: str,
                        link: str = "") -> list[dict]:
    text = f"*Scheduled:* {topic}\n{_label(start, end)}"
    if link:
        text += f"\n<{link}|join>"
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
