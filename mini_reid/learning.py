"""Corrections Ridha makes, kept as examples the model is told to imitate."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PATH = "corrections.json"
MAX_KEPT = 200


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
