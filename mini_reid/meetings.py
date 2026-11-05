"""Propose and create meetings from Google Calendar free/busy."""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta, timezone

from .sources import gmail_access

MYT = timezone(timedelta(hours=8))
OWNER_EMAIL = "ridha@pantas.com"
SLOT_MINUTES = 30
WORK_START = 9
WORK_END = 18
PROPOSE_DAYS = 5
PROPOSE_COUNT = 5


def _post(url: str, access: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {access}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def busy_by_email(env: dict, emails: list[str], start: datetime,
                  end: datetime, token_path: str | None = None,
                  client_path: str | None = None) -> dict[str, list[tuple]]:
    access = gmail_access(env, token_path, client_path)
    wanted = [{"id": e} for e in emails]
    d = _post("https://www.googleapis.com/calendar/v3/freeBusy", access, {
        "timeMin": start.astimezone(timezone.utc).isoformat(),
        "timeMax": end.astimezone(timezone.utc).isoformat(),
        "items": wanted})
    out: dict[str, list[tuple]] = {}
    for email in emails:
        cal = (d.get("calendars") or {}).get(email) or {}
        if cal.get("errors"):
            raise RuntimeError(f"{email}: {cal['errors'][0].get('reason')}")
        out[email] = [
            (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
            for b in cal.get("busy") or []
        ]
    return out


def _overlaps(start: datetime, end: datetime, busy: list[tuple]) -> bool:
    return any(start < b_end and end > b_start for b_start, b_end in busy)


def propose_slots(env: dict, emails: list[str], now: datetime | None = None,
                  duration: int = SLOT_MINUTES, days: int = PROPOSE_DAYS,
                  token_path: str | None = None,
                  client_path: str | None = None,
                  busy_out: dict | None = None) -> list[dict]:
    now = now or datetime.now(MYT)
    earliest = now.replace(second=0, microsecond=0) + timedelta(minutes=30)
    end = (now + timedelta(days=days)).replace(hour=WORK_END, minute=0,
                                               second=0, microsecond=0)
    everyone = [OWNER_EMAIL] + [e for e in emails if e != OWNER_EMAIL]
    busy = busy_by_email(env, everyone, earliest, end,
                         token_path=token_path, client_path=client_path)
    if busy_out is not None:
        busy_out.update(busy)
    slots: list[dict] = []
    day = earliest.date()
    while day <= end.date() and len(slots) < PROPOSE_COUNT:
        if day.weekday() < 5:
            cursor = datetime.combine(day, time(WORK_START), tzinfo=MYT)
            if cursor < earliest:
                cursor = earliest.replace(minute=(earliest.minute // 30) * 30)
            close = datetime.combine(day, time(WORK_END), tzinfo=MYT)
            while cursor + timedelta(minutes=duration) <= close:
                stop = cursor + timedelta(minutes=duration)
                if not any(_overlaps(cursor, stop, b) for b in busy.values()):
                    slots.append({"start": cursor.isoformat(),
                                  "end": stop.isoformat()})
                    if len(slots) >= PROPOSE_COUNT:
                        break
                cursor += timedelta(minutes=30)
        day += timedelta(days=1)
    return slots


def create_event(env: dict, topic: str, start: str, end: str,
                 emails: list[str], notes: str = "",
                 token_path: str | None = None,
                 client_path: str | None = None) -> dict:
    """Create a Google Calendar event with a Meet link and invite attendees."""
    access = gmail_access(env, token_path, client_path)
    body = {
        "summary": topic[:200],
        "description": (notes or f"Meeting notes: {topic}")[:8000],
        "start": {"dateTime": start, "timeZone": "Asia/Kuala_Lumpur"},
        "end": {"dateTime": end, "timeZone": "Asia/Kuala_Lumpur"},
        "attendees": [{"email": e} for e in emails],
        "conferenceData": {"createRequest": {
            "requestId": secrets.token_hex(8),
            "conferenceSolutionKey": {"type": "hangoutsMeet"}}},
    }
    url = ("https://www.googleapis.com/calendar/v3/calendars/primary/events?"
           + urllib.parse.urlencode({"conferenceDataVersion": 1,
                                     "sendUpdates": "all"}))
    try:
        return _post(url, access, body)
    except urllib.error.HTTPError as ex:
        detail = ex.read().decode()[:300]
        raise RuntimeError(f"calendar create failed ({ex.code}): {detail}") from ex
