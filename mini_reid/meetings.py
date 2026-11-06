"""Propose and create meetings from Google Calendar free/busy."""
from __future__ import annotations

import json
import re
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


CREATED = "created_meetings.json"


def load_created(path: str = CREATED) -> dict:
    from pathlib import Path
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_meeting(event: dict, topic: str, start: str, end: str,
                     attendees: list[dict], creator: str, notes: str = "",
                     path: str = CREATED) -> None:
    """Keep what the reminder and reschedule flows need after creation."""
    eid = event.get("id") or ""
    if not eid:
        return
    from pathlib import Path

    data = load_created(path)
    data[eid] = {
        "title": topic[:200], "start": start, "end": end,
        "link": event.get("hangoutLink") or event.get("htmlLink") or "",
        "notes": notes[:8000], "attendees": attendees, "creator": creator,
        "rsvps": data.get(eid, {}).get("rsvps") or {},
        "attendee_reminded": False,
    }
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False))


def update_event(env: dict, event_id: str, start: str, end: str,
                 notes: str | None = None, token_path: str | None = None,
                 client_path: str | None = None) -> dict:
    """Move an existing event and tell every attendee."""
    access = gmail_access(env, token_path, client_path)
    body: dict = {
        "start": {"dateTime": start, "timeZone": "Asia/Kuala_Lumpur"},
        "end": {"dateTime": end, "timeZone": "Asia/Kuala_Lumpur"},
    }
    if notes is not None:
        body["description"] = notes[:8000]
    url = ("https://www.googleapis.com/calendar/v3/calendars/primary/events/"
           + urllib.parse.quote(event_id, safe="") + "?"
           + urllib.parse.urlencode({"sendUpdates": "all"}))
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="PATCH",
        headers={"Authorization": f"Bearer {access}",
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def email_to_slack(path: str = "directory.json") -> dict[str, str]:
    """Work email → Slack user id, for attendee reminders."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    out = {}
    for uid, rec in (data or {}).items():
        email = ((rec or {}).get("email") or "").lower()
        if email:
            out[email] = uid
    return out


def reschedule_nearest(env: dict, new_start: datetime, note: str,
                       now: datetime, created_path: str = CREATED,
                       state_path: str = "meeting_reminders.json"
                       ) -> str | None:
    """Move the meeting whose start is closest to now, keeping its duration."""
    from pathlib import Path as _Path

    data = load_created(created_path)
    best = None
    for eid, rec in data.items():
        try:
            start = datetime.fromisoformat(rec.get("start") or "")
        except ValueError:
            continue
        gap = abs((start - now).total_seconds())
        if gap <= 90 * 60 and (best is None or gap < best[0]):
            best = (gap, eid, rec, start)
    if not best:
        return None
    _, eid, rec, old_start = best
    try:
        old_end = datetime.fromisoformat(rec.get("end") or "")
        duration = old_end - old_start
    except ValueError:
        duration = timedelta(minutes=SLOT_MINUTES)
    new_end = new_start + duration
    notes = rec.get("notes") or ""
    if note:
        notes = (notes + "\n" if notes else "") + note
    update_event(env, eid, new_start.isoformat(), new_end.isoformat(),
                 notes=notes or None)
    rec["start"] = new_start.isoformat()
    rec["end"] = new_end.isoformat()
    rec["notes"] = notes
    rec["attendee_reminded"] = False
    _Path(created_path).write_text(json.dumps(data, indent=1,
                                              ensure_ascii=False))
    # The 10-minute reminder keys off the event id; move its start too.
    try:
        state = json.loads(_Path(state_path).read_text())
        if eid in (state.get("meetings") or {}):
            state["meetings"][eid]["start"] = new_start.isoformat()
            state["meetings"][eid]["status"] = "scheduled"
            _Path(state_path).write_text(json.dumps(state))
    except (OSError, ValueError):
        pass
    by_email = email_to_slack()
    from .notify import send_dm_to

    text = (f"*Rescheduled*\n{new_start:%a %d %b %H:%M}–{new_end:%H:%M} · "
            f"{rec.get('title', '')}" + (f"\n_{note}_" if note else ""))
    for person in rec.get("attendees") or []:
        uid = by_email.get((person.get("email") or "").lower())
        if not uid or uid == rec.get("creator"):
            continue
        try:
            send_dm_to(env, uid, text)
        except Exception:  # noqa: BLE001 - one bad DM must not block the move
            continue
    return (f"Rescheduled: {rec.get('title', '')} — "
            f"{new_start:%a %d %b %H:%M}" + (f" ({note})" if note else ""))


DURATION_RE = re.compile(
    r"\b(?:for\s+)?(\d{1,3})\s*(?:min|mins|minutes)\b"
    r"|\b(?:for\s+)?(\d{1,2})\s*(?:hours?|hrs?)\b"
    r"|\b(?:for\s+)?an?\s+hour\b", re.I)


def parse_duration(text: str) -> int | None:
    m = DURATION_RE.search(text or "")
    if not m:
        return None
    if m.group(1):
        minutes = int(m.group(1))
    elif m.group(2):
        minutes = int(m.group(2)) * 60
    else:
        minutes = 60
    return max(15, min(180, minutes))


def strip_duration(text: str) -> str:
    return re.sub(r"\s+", " ", DURATION_RE.sub(" ", text or "")).strip(" ,-")


def delete_event(env: dict, event_id: str, token_path: str | None = None,
                 client_path: str | None = None,
                 calendar_id: str = "primary") -> None:
    access = gmail_access(env, token_path, client_path)
    url = ("https://www.googleapis.com/calendar/v3/calendars/"
           + urllib.parse.quote(calendar_id, safe="") + "/events/"
           + urllib.parse.quote(event_id, safe="") + "?"
           + urllib.parse.urlencode({"sendUpdates": "all"}))
    req = urllib.request.Request(
        url, method="DELETE",
        headers={"Authorization": f"Bearer {access}"})
    with urllib.request.urlopen(req, timeout=30):
        return None


def cancel_nearest(env: dict, now: datetime, note: str = "",
                   created_path: str = CREATED,
                   state_path: str = "meeting_reminders.json"
                   ) -> str | None:
    """Cancel the bot-created meeting whose start is closest to now."""
    from pathlib import Path as _Path

    data = load_created(created_path)
    best = None
    for eid, rec in data.items():
        try:
            start = datetime.fromisoformat(rec.get("start") or "")
        except ValueError:
            continue
        gap = abs((start - now).total_seconds())
        if gap <= 3 * 60 * 60 and (best is None or gap < best[0]):
            best = (gap, eid, rec, start)
    if not best:
        return None
    _, eid, rec, start = best
    delete_event(env, eid)
    data.pop(eid, None)
    _Path(created_path).write_text(json.dumps(data, indent=1,
                                              ensure_ascii=False))
    try:
        state = json.loads(_Path(state_path).read_text())
        rec_state = (state.get("meetings") or {}).pop(eid, None)
        if rec_state:
            _Path(state_path).write_text(json.dumps(state))
    except (OSError, ValueError):
        pass
    by_email = email_to_slack()
    from .notify import send_dm_to

    text = (f"*Cancelled*\n{rec.get('title', '')} · {start:%a %d %b %H:%M}"
            + (f"\n_{note}_" if note else ""))
    for person in rec.get("attendees") or []:
        uid = by_email.get((person.get("email") or "").lower())
        if not uid or uid == rec.get("creator"):
            continue
        try:
            send_dm_to(env, uid, text)
        except Exception:  # noqa: BLE001 - one DM must not block the cancel
            continue
    return (f"Cancelled: {rec.get('title', '')}"
            + (f" — {note}" if note else ""))


def cancel_by_reminder(env: dict, now: datetime, note: str = "",
                       state_path: str = "meeting_reminders.json"
                       ) -> str | None:
    """Cancel a calendar meeting known only from the reminder state."""
    from pathlib import Path as _Path

    try:
        state = json.loads(_Path(state_path).read_text())
    except (OSError, ValueError):
        return None
    best = None
    for mid, rec in (state.get("meetings") or {}).items():
        if rec.get("status") not in {"scheduled", "sent", "attending"}:
            continue
        try:
            start = datetime.fromisoformat(rec.get("start") or "")
        except ValueError:
            continue
        gap = abs((start - now).total_seconds())
        if gap <= 3 * 60 * 60 and (best is None or gap < best[0]):
            best = (gap, mid, rec, start)
    if not best:
        return None
    _, mid, rec, start = best
    delete_event(env, mid)
    (state.get("meetings") or {}).pop(mid, None)
    _Path(state_path).write_text(json.dumps(state))
    return (f"Cancelled: {rec.get('title', '')} · {start:%H:%M}"
            + (f" — {note}" if note else ""))


def upcoming_events(env: dict, now: datetime, days: int = 14,
                    query: str = "", token_path: str | None = None,
                    client_path: str | None = None) -> list[dict]:
    """Events in the next `days` across every readable calendar."""
    from .calendar import _calendar_list
    from .sources import _get_json

    access = gmail_access(env, token_path, client_path)
    start = now.astimezone(timezone.utc).isoformat()
    end = (now + timedelta(days=days)).astimezone(timezone.utc).isoformat()
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for cal in _calendar_list(access):
        cid = cal.get("id")
        if not cid:
            continue
        url = ("https://www.googleapis.com/calendar/v3/calendars/"
               + urllib.parse.quote(cid, safe="") + "/events?"
               + urllib.parse.urlencode({
                   "timeMin": start, "timeMax": end, "singleEvents": "true",
                   "orderBy": "startTime", "maxResults": 100,
                   "fields": "items(id,summary,start,status)"}))
        try:
            data = _get_json(url, {"Authorization": f"Bearer {access}"})
        except Exception:  # noqa: BLE001 - one bad calendar must not hide the rest
            continue
        for event in data.get("items") or []:
            if event.get("status") == "cancelled":
                continue
            key = (cid, event.get("id") or "")
            if key in seen:
                continue
            seen.add(key)
            event["_calendar"] = cid
            out.append(event)
    return out


def cancel_by_title(env: dict, query: str, now: datetime, days: int = 14,
                    token_path: str | None = None,
                    client_path: str | None = None) -> str | None:
    """Cancel the nearest upcoming event whose title contains the query."""
    q = (query or "").strip().lower()
    if not q:
        return None
    matches = [e for e in upcoming_events(env, now, days, query,
                                          token_path, client_path)
               if q in (e.get("summary") or "").lower()]
    if not matches:
        return None

    def start_of(event: dict) -> datetime:
        raw = (event.get("start") or {}).get("dateTime") or ""
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return now

    event = min(matches, key=start_of)
    start = start_of(event)
    delete_event(env, event.get("id") or "", token_path, client_path,
                 calendar_id=event.get("_calendar") or "primary")
    return (f"Cancelled: {event.get('summary') or query} · "
            f"{start:%a %d %b %H:%M}")
