"""Forward-looking digest renderer."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

LABELS = [
    ("overdue", "Overdue"),
    ("today", "Today and tomorrow"),
    ("week", "This week"),
    ("waiting", "Waiting on others"),
    ("undated", "No date"),
]


def _due(row: dict) -> str | None:
    return row.get("due")


def _due_label(row: dict, now: datetime) -> str:
    due = row.get("due")
    if not due:
        return "no date"
    try:
        delta = (datetime.fromisoformat(due).date() - now.date()).days
    except ValueError:
        return due
    if delta < 0:
        return f"{-delta}d overdue"
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    return f"in {delta}d · {due}"


_CLIENTS: dict[str, dict] = {}


def _client_name(slug: str | None) -> str | None:
    if not slug:
        return None
    if not _CLIENTS:
        try:
            from .clients import load_clients

            _CLIENTS.update(load_clients("clients.json"))
        except Exception:  # noqa: BLE001 - display must not fail on a missing registry
            return slug
    return (_CLIENTS.get(slug) or {}).get("name") or slug


def _when(row: dict) -> str:
    raw = row.get("created_at") or row.get("ts") or ""
    try:
        return datetime.fromisoformat(raw).strftime("%d %b %H:%M")
    except (TypeError, ValueError):
        return ""


def _source_quote(row: dict) -> str:
    """Quote the message when the task title no longer resembles it."""
    evidence = (row.get("evidence") or "").strip()
    what = (row.get("what") or "").strip()
    if not evidence or not what:
        return ""
    norm = lambda s: re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    if norm(what) in norm(evidence):
        return ""
    quote = evidence[:120].rstrip()
    return f"“{quote}{'…' if len(evidence) > 120 else ''}”"


def _line(row: dict, slack: bool = False, now: datetime | None = None) -> str:
    what = (row.get("what") or "").strip()
    if len(what) > 140:
        what = what[:137].rstrip() + "…"
    client = _client_name(row.get("client"))
    due = _due_label(row, now) if now else (_due(row) or "no date")
    link = row.get("source_link") or ""
    asker = row.get("asker")
    via = row.get("via")
    who = f"from {asker}" if asker else ""
    if via:
        who = f"{who} ({via})" if who else via
    when = _when(row)
    quote = _source_quote(row) if row.get("source") == "slack" else ""

    if slack:
        tail = f" — <{link}|open>" if link else ""
        parts = [f"*{what}*"]
        if client:
            parts.append(client)
        parts.append(due)
        if row.get("status") in {"in progress", "blocked"}:
            parts.append(row["status"])
        if who:
            parts.append(who)
        if when:
            parts.append(when)
        line = "• " + " — ".join(parts) + tail
        return f"{line}\n   {quote}" if quote else line

    tail = f"  \n  [open]({link})" if link else ""
    parts = [f"**{what}**"]
    if client:
        parts.append(client)
    parts.append(due)
    if row.get("status") in {"in progress", "blocked"}:
        parts.append(row["status"])
    if who:
        parts.append(who)
    if when:
        parts.append(when)
    line = "- " + " — ".join(parts) + tail
    return f"{line}\n  {quote}" if quote else line


def _meeting_line(meeting: dict, slack: bool) -> str:
    from .calendar import span

    title = meeting.get("title") or "Untitled meeting"
    link = meeting.get("link") or ""
    when = span(meeting)
    if slack:
        tail = f" — <{link}|join>" if link else ""
        return f"• *{when} · {title}*{tail}"
    tail = f" — [join]({link})" if link else ""
    return f"- **{when} · {title}**{tail}"


def render(rows: list[dict], now: datetime, review: list[str] | None = None,
           slack: bool = False, brief: str | None = None,
           meetings: list[dict] | None = None) -> str:
    today = now.date()
    week_end = today + timedelta(days=7)
    yesterday = now - timedelta(days=1)

    buckets: dict[str, list[dict]] = {k: [] for k, _ in LABELS}
    used: set[str] = set()
    seen_links: set[str] = set()
    seen_text: set[tuple[str, str]] = set()

    def take(key: str, row: dict) -> None:
        buckets[key].append(row)
        used.add(row["id"])
        if row.get("source_link"):
            seen_links.add(row["source_link"])
        seen_text.add(((row.get("what") or "").lower().strip()[:80],
                       row.get("client") or ""))

    for row in sorted(rows, key=lambda r: (r.get("due") or "9999-12-31", r.get("what") or "")):
        if row.get("status") in {"done", "dropped"} or row["id"] in used:
            continue
        if row.get("closure") == "proposed" or row.get("kind") == "note":
            continue
        # One source message renders once, even if re-extraction made a second id.
        if row.get("source_link") and row["source_link"] in seen_links:
            continue
        text_key = ((row.get("what") or "").lower().strip()[:80], row.get("client") or "")
        if text_key in seen_text:
            continue
        if row.get("direction") == "owed_to_me":
            take("waiting", row)
            continue
        due = row.get("due")
        if row.get("status") == "stalled" or (due and due < today.isoformat()):
            take("overdue", row)
        elif due and due <= (today + timedelta(days=1)).isoformat():
            take("today", row)
        elif due and due <= week_end.isoformat():
            take("week", row)

    # Everything open that has no deadline still belongs on the list. It used to
    # vanish after one day, which is how undated work gets lost.
    for row in sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True):
        if row["id"] in used or row.get("status") in {"done", "dropped"}:
            continue
        if (row.get("direction") == "owed_to_me" or row.get("closure") == "proposed"
                or row.get("kind") == "note"):
            continue
        take("undated", row)

    buckets["overdue"].sort(key=lambda r: r.get("due") or "9999")
    buckets["today"].sort(key=lambda r: r.get("due") or "9999")
    buckets["week"].sort(key=lambda r: r.get("due") or "9999")

    title = now.strftime("%a %d %b %Y")
    total = sum(len(v) for v in buckets.values())
    counts = (f"{total} open · {len(buckets['overdue'])} overdue · "
              f"{len(buckets['today'])} due today · {len(buckets['week'])} this week · "
              f"{len(buckets['undated'])} no date · {len(buckets['waiting'])} waiting")
    if meetings:
        counts += f" · {len(meetings)} meetings"
    if slack:
        out = [f"*Mini-Reid — {title}*", counts]
        if brief:
            out.extend(["", f"*Brief*\n{brief}"])
    else:
        out = [f"# Mini-Reid — {title}", "", counts, ""]
        if brief:
            out.extend([f"## Brief", "", brief, ""])

    if meetings:
        if slack:
            out.extend(["", f"*Meetings ({len(meetings)})*"])
            out.extend(_meeting_line(m, slack=True) for m in meetings)
        else:
            out.extend(["", f"## Meetings ({len(meetings)})", ""])
            out.extend(_meeting_line(m, slack=False) for m in meetings)

    for key, label in LABELS:
        items = buckets[key]
        if not items:
            continue
        if slack:
            out.extend(["", f"*{label} ({len(items)})*"])
            out.extend(_line(r, slack=True, now=now) for r in items)
        else:
            out.extend(["", f"## {label} ({len(items)})", ""])
            out.extend(_line(r, now=now) for r in items)

    proposed = [r for r in rows
                if r.get("closure") == "proposed" and r.get("status") not in {"done", "dropped"}]
    if proposed:
        label = "Possibly done — confirm with done: <item>"
        if slack:
            out.extend(["", f"*{label} ({len(proposed)})*"])
            out.extend(_line(r, slack=True) for r in proposed)
        else:
            out.extend(["", f"## {label} ({len(proposed)})", ""])
            out.extend(_line(r) for r in proposed)

    notes = [r for r in rows
             if r.get("kind") == "note" and r.get("status") not in {"done", "dropped"}]
    if notes:
        if slack:
            out.extend(["", f"*Notes ({len(notes)})*"])
            out.extend(f"• {r.get('what', '')[:160]}" for r in notes)
        else:
            out.extend(["", f"## Notes ({len(notes)})", ""])
            out.extend(f"- {r.get('what', '')[:160]}" for r in notes)

    if review:
        if slack:
            out.extend(["", f"*Review ({len(review)})*"])
            out.extend(f"• unknown sender domain: {d}" for d in review)
        else:
            out.extend(["", f"## Review ({len(review)})", ""])
            out.extend(f"- unknown sender domain: `{d}`" for d in review)

    return "\n".join(out)
