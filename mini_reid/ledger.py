"""Commitment ledger: identity, merge, and status transitions."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

MYT = timezone(timedelta(hours=8))
TERMINAL = {"done", "dropped"}
STALL_AFTER_WORKING_DAYS = 5


def normalize_what(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def commitment_id(source: str, native_id: str, what: str) -> str:
    key = f"{source}|{native_id}|{normalize_what(what)}"
    return hashlib.sha1(key.encode()).hexdigest()


def load(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text())


def save(path: str, rows: list[dict]) -> None:
    Path(path).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")


def dedupe_by_link(rows: list[dict]) -> list[dict]:
    """One row per source message. Prefers a terminal row, then the newest."""
    kept: dict[str, dict] = {}
    loose: list[dict] = []
    for r in rows:
        link = r.get("source_link")
        if not link:
            loose.append(r)
            continue
        cur = kept.get(link)
        if cur is None:
            kept[link] = r
            continue
        cur_terminal = cur.get("status") in TERMINAL
        new_terminal = r.get("status") in TERMINAL
        if new_terminal or (not cur_terminal and
                            (r.get("created_at") or "") >= (cur.get("created_at") or "")):
            kept[link] = r
    return loose + list(kept.values())


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError:
        try:
            d = datetime.fromisoformat(value + "T00:00:00")
        except ValueError:
            return None
    return d.replace(tzinfo=MYT) if d.tzinfo is None else d


def merge(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Idempotent merge keyed on id. Terminal statuses never regress."""
    by_id = {r["id"]: dict(r) for r in existing}
    for r in incoming:
        incoming_row = dict(r)
        cur = by_id.get(incoming_row["id"])
        if cur is None:
            by_id[incoming_row["id"]] = incoming_row
            continue
        if cur.get("status") in TERMINAL:
            continue
        merged = {**cur, **incoming_row}
        merged["created_at"] = cur.get("created_at") or incoming_row.get("created_at")
        by_id[incoming_row["id"]] = merged
    return list(by_id.values())


def _working_days_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    days = 0
    cur = start
    while cur < end:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            days += 1
    return days


def apply_stalled(rows: list[dict], now: datetime) -> list[dict]:
    """Mark open rows stalled on three triggers; set stalled_since once."""
    today = now.date()
    out = []
    for r in rows:
        r = dict(r)
        if r.get("status") != "open":
            out.append(r)
            continue
        reason = None
        created = _dt(r.get("created_at"))
        activity = _dt(r.get("last_activity")) or created
        due = _dt(r.get("due"))

        if r.get("kind") == "draft" and created and now - created >= timedelta(days=1):
            reason = "draft_older_than_one_day"
        elif due and due.date() < today:
            reason = "past_due"
        elif activity and _working_days_between(activity.date(), today) >= STALL_AFTER_WORKING_DAYS:
            reason = "no_activity"

        if reason:
            r["status"] = "stalled"
            r["stalled_since"] = r.get("stalled_since") or now.isoformat()
            r["stalled_reason"] = reason
        out.append(r)
    return out
