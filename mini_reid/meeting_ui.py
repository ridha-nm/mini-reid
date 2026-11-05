"""Slack UI for picking a proposed meeting slot."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

MYT = ZoneInfo("Asia/Kuala_Lumpur")


def _label(start: str, end: str) -> str:
    s = datetime.fromisoformat(start).astimezone(MYT)
    e = datetime.fromisoformat(end).astimezone(MYT)
    return f"{s:%a %d %b %H:%M}–{e:%H:%M}"


def slot_blocks(token: str, topic: str, attendee: str,
                slots: list[dict]) -> list[dict]:
    blocks = [{
        "type": "section",
        "text": {"type": "mrkdwn",
                 "text": f"*Meeting with {attendee} — both free*\n{topic}\n"
                         "These slots are free on both calendars. Pick one and I "
                         "create the event and invite them."},
    }]
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
    return blocks


def confirmation_blocks(topic: str, start: str, end: str,
                        link: str = "") -> list[dict]:
    text = f"*Scheduled:* {topic}\n{_label(start, end)}"
    if link:
        text += f"\n<{link}|join>"
    return [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
