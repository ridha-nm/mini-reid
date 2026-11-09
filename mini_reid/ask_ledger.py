"""Answer task questions from the ledger before touching Slack search."""
from __future__ import annotations

import re

PENDING = re.compile(
    r"\b(pending|open|overdue|due|tasks?|items?|to-?do|waiting|blocked|"
    r"in progress)\b", re.I)
LIVE = {"open", "in progress", "blocked", "stalled", "inbox"}


def client_hits(question: str, clients: dict) -> list[str]:
    text = (question or "").lower()
    hits = []
    for slug, cfg in clients.items():
        names = [slug, slug.replace("-", " "), cfg.get("name") or ""]
        if any(name and name.lower() in text for name in names):
            hits.append(slug)
    return hits


def answer_ledger(question: str, rows: list[dict], clients: dict) -> str | None:
    if not PENDING.search(question or ""):
        return None
    hits = client_hits(question, clients)
    tasks = [r for r in rows
             if (r.get("status") or "open").lower() in LIVE
             and r.get("kind") not in {"note", "reminder"}
             and (not hits or (r.get("client") or "").lower() in hits)]
    label = ""
    if hits:
        label = " with " + ", ".join((clients[s].get("name") or s) for s in hits)
    if not tasks:
        return f"No pending items{label}."
    tasks.sort(key=lambda r: (r.get("due") or "9999-12-31",
                              r.get("priority") or 99))
    lines = [f"*{len(tasks)} pending{label}*"]
    for row in tasks[:10]:
        title = (row.get("action") or row.get("what") or "")[:100]
        due = f" — due {row['due']}" if row.get("due") else ""
        link = row.get("source_link")
        tail = f" — <{link}|open>" if link else ""
        lines.append(f"• {title}{due}{tail}")
    if len(tasks) > 10:
        lines.append(f"… and {len(tasks) - 10} more")
    return "\n".join(lines)
