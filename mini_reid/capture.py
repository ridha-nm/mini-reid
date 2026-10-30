"""Manual capture door: 'add: Eupe dashboard item by Friday'."""
from __future__ import annotations

from datetime import datetime

from .clients import match_client
from .extract import parse_due
from .ledger import commitment_id, normalize_what


def parse_capture(text: str, now: datetime, clients: dict | None = None) -> dict | None:
    if not text or not text.strip().lower().startswith("add:"):
        return None
    body = text.strip()[4:].strip()
    if not body:
        return None

    due, conf = parse_due(body, now)
    client = match_client(body, "", clients or {})
    norm = normalize_what(body)
    return {
        "id": commitment_id("manual", norm, body),
        "direction": "owed_by_me",
        "what": body[:200],
        "source": "manual",
        "native_id": norm,
        "kind": "manual",
        "source_link": "",
        "evidence": body[:200],
        "due": due,
        "due_confidence": conf,
        "cycle": None,
        "status": "open",
        "stalled_since": None,
        "ack_policy": "bot_may_ack",
        "closure": "open",
        "client": (client or {}).get("slug"),
        "created_at": now.isoformat(),
        "last_activity": now.isoformat(),
        "closed_at": None,
        "closed_how": None,
    }
