"""Google Calendar read: today's meetings, with a join link."""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .sources import _get_json, gmail_access

MYT = timezone(timedelta(hours=8))
SKIP_TYPES = {"workingLocation", "outOfOffice", "focusTime"}
OWNER_EMAIL = "ridha@pantas.com"
IGNORES = "calendar_ignores.json"


def ignored_titles(path: str = IGNORES) -> set[str]:
    """Meeting titles the user said `not:` to. Kept across days."""
    p = Path(path)
    return {t.lower() for t in json.loads(p.read_text())} if p.exists() else set()


def ignore_title(title: str, path: str = IGNORES) -> None:
    titles = sorted(ignored_titles(path) | {title.strip().lower()})
    Path(path).write_text(json.dumps(titles, indent=1) + "\n")


def _join_link(event: dict) -> str:
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    for point in (event.get("conferenceData") or {}).get("entryPoints") or []:
        if point.get("entryPointType") == "video" and point.get("uri"):
            return point["uri"]
    return event.get("htmlLink") or ""


def parse_events(payload: dict, calendar_name: str, day: str,
                 owned: bool = False,
                 owner_email: str = OWNER_EMAIL) -> list[dict]:
    """Timed events for one calendar on `day` (YYYY-MM-DD). Declined and
    cancelled events are not meetings this user is attending. Shared calendars
    contain other people's events, so keep only ones they are invited to unless
    the calendar is their own."""
    owner_email = (owner_email or OWNER_EMAIL).lower()
    out = []
    for event in payload.get("items") or []:
        if event.get("status") == "cancelled":
            continue
        if event.get("eventType") in SKIP_TYPES:
            continue
        start = (event.get("start") or {}).get("dateTime")
        end = (event.get("end") or {}).get("dateTime")
        if not start or not end:
            continue  # all-day items are not meetings
        attendees = event.get("attendees") or []
        # `attendees[].self` marks the calendar's owner, not the reader: on
        # Kasib's shared calendar it is Kasib. Match by address instead.
        # A shared calendar is someone else's diary: an event with no invite to
        # the user is not their meeting, even when it has no attendees at all.
        organizer = ((event.get("organizer") or {}).get("email") or "").lower()
        mine = organizer == owner_email or any(
            (a.get("email") or "").lower() == owner_email for a in attendees)
        if not owned and not mine:
            continue
        declined = any(((a.get("email") or "").lower() == owner_email
                         and a.get("responseStatus") == "declined")
                        for a in attendees)
        if declined:
            continue
        out.append({
            "id": event.get("id") or "",
            "title": (event.get("summary") or "Untitled meeting").strip(),
            "start": start,
            "end": end,
            "link": _join_link(event),
            "calendar": calendar_name,
            "day": day,
        })
    return out


def _calendar_list(access: str) -> list[dict]:
    url = ("https://www.googleapis.com/calendar/v3/users/me/calendarList?"
           + urllib.parse.urlencode({"minAccessRole": "reader", "maxResults": 250}))
    return _get_json(url, {"Authorization": f"Bearer {access}"}).get("items") or []


def _day_events(access: str, calendar_id: str, start: datetime,
                end: datetime) -> dict:
    url = ("https://www.googleapis.com/calendar/v3/calendars/"
           + urllib.parse.quote(calendar_id, safe="") + "/events?"
           + urllib.parse.urlencode({
               "timeMin": start.isoformat(), "timeMax": end.isoformat(),
               "singleEvents": "true", "orderBy": "startTime", "maxResults": 100,
               "fields": ("items(id,summary,status,eventType,start,end,attendees,"
                          "hangoutLink,conferenceData,htmlLink)")}))
    return _get_json(url, {"Authorization": f"Bearer {access}"})


def meetings_for_day(env: dict, now: datetime, token_path: str | None = None,
                     owner_email: str | None = None,
                     ignores_path: str = IGNORES,
                     client_path: str | None = None) -> list[dict]:
    """Today's meetings across every calendar the account can read."""
    access = gmail_access(env, token_path, client_path)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    day = start.date().isoformat()
    seen: set[str] = set()
    ignored = ignored_titles(ignores_path)
    out: list[dict] = []
    for cal in _calendar_list(access):
        cid = cal.get("id")
        if not cid:
            continue
        try:
            payload = _day_events(access, cid, start, end)
        except Exception:  # noqa: BLE001 - one bad calendar must not hide the rest
            continue
        owned = bool(cal.get("primary")) or cal.get("accessRole") == "owner"
        for event in parse_events(payload, cal.get("summary") or cid, day, owned,
                                  owner_email or OWNER_EMAIL):
            # A meeting often appears on several calendars.
            if event["id"] and event["id"] in seen:
                continue
            if event["title"].strip().lower() in ignored:
                continue
            seen.add(event["id"])
            out.append(event)
    out.sort(key=lambda e: e["start"])
    return out


def clock(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(MYT).strftime("%H:%M")
    except (TypeError, ValueError):
        return iso


def span(event: dict) -> str:
    return f"{clock(event.get('start', ''))}–{clock(event.get('end', ''))}"
