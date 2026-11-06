"""Slack UI for a meeting proposal and its free slots."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from .meetings import OWNER_EMAIL, SLOT_MINUTES

MYT = ZoneInfo("Asia/Kuala_Lumpur")


def _label(start: str, end: str) -> str:
    s = datetime.fromisoformat(start).astimezone(MYT)
    e = datetime.fromisoformat(end).astimezone(MYT)
    return f"{s:%a %d %b %H:%M}–{e:%H:%M}"


def _busy_on(intervals: list[tuple], day) -> str:
    day_start = datetime.combine(day, time.min, tzinfo=MYT)
    day_end = day_start + timedelta(days=1)
    parts = []
    for start, end in intervals:
        s, e = start.astimezone(MYT), end.astimezone(MYT)
        if e <= day_start or s >= day_end:
            continue
        if s <= day_start and e >= day_end:
            parts.append("all day")
        else:
            parts.append(f"{max(s, day_start):%H:%M}–"
                         f"{min(e, day_end):%H:%M}")
    return ", ".join(parts) or "free"


def _snapshot(busy: dict, attendees: list[dict], slots: list[dict]) -> str:
    days = sorted({datetime.fromisoformat(s["start"]).astimezone(MYT).date()
                   for s in slots})
    lines = []
    for day in days[:5]:
        lines.append(f"{day:%a %d %b}")
        lines.append(f"  You:      {_busy_on(busy.get(OWNER_EMAIL, []), day)}")
        for person in attendees:
            label = person["name"][:10]
            lines.append(f"  {label:9} {_busy_on(busy.get(person['email'], []), day)}")
    return "\n".join(lines)


def slot_blocks(token: str, topic: str, attendees: list[dict],
                slots: list[dict], busy: dict | None = None) -> list[dict]:
    if isinstance(attendees, str):
        attendees = [{"name": attendees, "email": ""}]
    with_email = "\n".join(
        f"{a['name']}" + (f" ({a['email']})" if a.get("email") else "")
        for a in attendees)
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
                             + _snapshot(busy, attendees, slots)
                             + "```"},
        })
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": "These slots are free on every calendar. Pick one and I "
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
        {"type": "button", "action_id": "meet_edit", "value": token,
         "text": {"type": "plain_text", "text": "Edit title / notes"}},
        {"type": "button", "action_id": "meet_refresh", "value": token,
         "text": {"type": "plain_text", "text": "Refresh availability"}},
        {"type": "button", "action_id": "meet_cancel", "value": token,
         "text": {"type": "plain_text", "text": "Cancel"}, "style": "danger"},
    ]})
    return blocks


def edit_modal(token: str, topic: str, notes: str = "") -> dict:
    return {
        "type": "modal",
        "callback_id": "meet_edit",
        "private_metadata": token,
        "title": {"type": "plain_text", "text": "Edit meeting"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "input", "block_id": "title",
             "label": {"type": "plain_text", "text": "Meeting title"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "initial_value": topic[:200],
                         "max_length": 200}},
            {"type": "input", "block_id": "notes", "optional": True,
             "label": {"type": "plain_text", "text": "Notes (event description)"},
             "element": {"type": "plain_text_input", "action_id": "value",
                         "multiline": True, "initial_value": (notes or "")[:2000]}},
        ],
    }


def confirmation_blocks(topic: str, start: str, end: str,
                        link: str = "") -> list[dict]:
    text = f"*Scheduled:* {topic}\n{_label(start, end)}"
    if link:
        text += f"\n<{link}|join>"
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
