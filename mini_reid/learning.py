"""Corrections Ridha makes, kept as examples the model is told to imitate."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PATH = "corrections.json"
EVENTS = "learning_events.json"
MAX_KEPT = 200
MAX_EVENTS = 500


def load(path: str | None = None) -> list[dict]:
    p = Path(path or PATH)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return []


def add(what: str, reason: str = "", source: str = "", path: str | None = None) -> dict:
    path = path or PATH
    rows = load(path)
    entry = {
        "what": (what or "").strip()[:200],
        "reason": (reason or "").strip()[:200],
        "source": source,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    rows.append(entry)
    Path(path).write_text(json.dumps(rows[-MAX_KEPT:], indent=1, ensure_ascii=False) + "\n")
    return entry


def ignored_examples(limit: int = 10, path: str | None = None) -> list[str]:
    rows = load(path)
    return [r["what"] for r in rows if r.get("what")][-limit:]


def remember(text: str, action: str, user: str = "",
             path: str | None = None) -> None:
    """Record a command people actually used, as a training example.

    The classifier treats these as task-like text, so phrasing that worked
    once scores higher next time. No model is trained; this is the same
    naive-Bayes feedback loop the `not:` corrections already feed.
    """
    path = path or EVENTS
    rows = load(path)
    rows.append({"text": (text or "").strip()[:300], "action": action,
                 "user": user,
                 "at": datetime.now().astimezone().isoformat(timespec="seconds")})
    Path(path).write_text(json.dumps(rows[-MAX_EVENTS:], indent=1,
                                     ensure_ascii=False) + "\n")


def accepted_texts(limit: int = 300, path: str | None = None) -> list[str]:
    rows = load(path)
    ignore = {"not", "undo", "help", "list", "notes", "ask", "ack", "unknown"}
    return [r["text"] for r in rows
            if r.get("text") and r.get("action") not in ignore][-limit:]
