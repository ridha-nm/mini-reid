"""Forward-looking digest renderer."""
from __future__ import annotations

from datetime import datetime, timedelta

LABELS = [
    ("overdue", "Overdue"),
    ("today", "Today and tomorrow"),
    ("week", "This week"),
    ("waiting", "Waiting on others"),
    ("new", "New since yesterday"),
]


def _due(row: dict) -> str | None:
    return row.get("due")


def _line(row: dict, slack: bool = False) -> str:
    what = (row.get("what") or "").strip()
    if len(what) > 140:
        what = what[:137].rstrip() + "…"
    client = row.get("client") or "unassigned"
    due = _due(row) or "no date"
    link = row.get("source_link") or ""
    asker = row.get("asker")
    who = f" — from {asker}" if asker else ""
    if slack:
        # A DM already tells you who it was from. No link needed.
        if "/archives/D" in link:
            link = ""
        tail = f" — <{link}|open>" if link else ""
        return f"• *{what}*{who} — {client} — {due}{tail}"
    tail = f"  \n  [open]({link})" if link else ""
    return f"- **{what}** — {client} — {due}{tail}"


def render(rows: list[dict], now: datetime, review: list[str] | None = None,
           slack: bool = False) -> str:
    today = now.date()
    week_end = today + timedelta(days=7)
    yesterday = now - timedelta(days=1)

    buckets: dict[str, list[dict]] = {k: [] for k, _ in LABELS}
    used: set[str] = set()
    seen_links: set[str] = set()

    def take(key: str, row: dict) -> None:
        buckets[key].append(row)
        used.add(row["id"])
        if row.get("source_link"):
            seen_links.add(row["source_link"])

    for row in sorted(rows, key=lambda r: (r.get("due") or "9999-12-31", r.get("what") or "")):
        if row.get("status") in {"done", "dropped"} or row["id"] in used:
            continue
        if row.get("closure") == "proposed" or row.get("kind") == "note":
            continue
        # One source message renders once, even if re-extraction made a second id.
        if row.get("source_link") and row["source_link"] in seen_links:
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

    for row in rows:
        if row["id"] in used or row.get("status") in {"done", "dropped"}:
            continue
        if (row.get("direction") == "owed_to_me" or row.get("closure") == "proposed"
                or row.get("kind") == "note"):
            continue
        created = row.get("created_at") or ""
        if created and datetime.fromisoformat(created) >= yesterday:
            take("new", row)

    title = now.strftime("%a %d %b %Y, %H:%M MYT")
    total = sum(len(v) for v in buckets.values())
    if slack:
        out = [f"*Mini-Reid — {title}*", f"{total} open commitments. Nothing sent."]
    else:
        out = [f"# Mini-Reid — {title}", "", f"{total} open commitments. Nothing sent.", ""]

    for key, label in LABELS:
        items = buckets[key]
        if not items:
            continue
        if slack:
            out.extend(["", f"*{label} ({len(items)})*"])
            out.extend(_line(r, slack=True) for r in items)
        else:
            out.extend(["", f"## {label} ({len(items)})", ""])
            out.extend(_line(r) for r in items)

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
