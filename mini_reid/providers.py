"""Model providers. Local by default: nothing leaves the machine."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from .extract import via_for
from .ledger import commitment_id

SCHEMA = {
    "items": [
        {
            "id": "the id you were given",
            "what": "a clean one-line task title, max 100 chars",
            "from": "who asked, first name or team, empty if unclear",
            "due": "YYYY-MM-DD or null",
        }
    ]
}

PROMPT = """You tidy work messages into task titles for a personal to-do list.

A person decides what becomes a task, not you. Every message is a candidate:
return one item for every message, using the id you were given. Never drop a
message and never judge whether it is a commitment.

Rewrite what as a title a person can scan in a list:
- Start with a verb in sentence case: Send, Confirm, Review, Prepare,
  Follow up with, Check, Share, Set up.
- Put the object first after the verb, then the person or project if needed.
- Keep names, numbers, dates, document names and place names a person needs
  to act. Drop anything else.
- Remove greetings, thanks, signatures, email headers (RE:, FW:), quoted
  history, emoji and filler words.
- Do not repeat the due date in what; put it in due when the text states or
  clearly implies one.
- One line, max 100 characters, no trailing period, no surrounding quotes.
- If the message has no ask, still return the clearest short title of what it
  says; the person can dismiss it.

from is the person or team who asked, first name, empty if unclear.
due is YYYY-MM-DD or null.

Examples:
"hey could you review the K3 deck by Thu?" -> what "Review the K3 deck"
"RE: Timesheet submission" -> what "Submit the timesheet"
"Please confirm if 4:30 works for your team tomorrow" -> what "Confirm 4:30 meeting with your team"

Today is {today} ({weekday}).
Return JSON exactly matching: {schema}
No prose. Only JSON.

Messages:
{items}
"""


class OllamaProvider:
    def __init__(self, model: str = "llama3.2:3b", url: str = "http://localhost:11434"):
        self.model = model
        self.url = url.rstrip("/")

    def complete(self, prompt: str) -> dict:
        req = urllib.request.Request(
            f"{self.url}/api/generate",
            data=json.dumps({
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0, "num_predict": 2000},
            }).encode(),
            headers={"Content-Type": "application/json"},
        )
        last: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    body = json.load(r)
                return json.loads(body["response"])
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError, json.JSONDecodeError) as ex:
                last = ex
                time.sleep(2 ** attempt)
        raise last  # type: ignore[misc]


def _val(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    return None if s.lower() in {"", "null", "none", "n/a"} else s


def _batch_prompt(items: list[dict], now: datetime) -> str:
    payload = [{"id": i["native_id"], "text": (i.get("text") or "")[:500],
                "from": i.get("author", "")} for i in items]
    return PROMPT.format(
        today=now.date().isoformat(),
        weekday=now.strftime("%A"),
        schema=json.dumps(SCHEMA),
        items=json.dumps(payload, ensure_ascii=False),
    )


def extract_batch_safe(items: list[dict], provider, now: datetime,
                       clients: list[str] | None = None
                       ) -> tuple[list[dict], list[dict]]:
    """Return (rows, failed_items). A bad response is split until the culprit is isolated."""
    try:
        return extract_batch(items, provider, now, clients), []
    except Exception:  # noqa: BLE001 - the caller decides how to fall back
        if len(items) <= 1:
            return [], items
        mid = len(items) // 2
        left_rows, left_failed = extract_batch_safe(items[:mid], provider, now, clients)
        right_rows, right_failed = extract_batch_safe(items[mid:], provider, now, clients)
        return left_rows + right_rows, left_failed + right_failed


def extract_batch(items: list[dict], provider, now: datetime,
                  clients: list[str] | None = None) -> list[dict]:
    """One call for many items. Malformed output raises; it never returns []."""
    if not items:
        return []
    data = provider.complete(_batch_prompt(items, now))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"model returned unexpected shape: {str(data)[:200]}")

    by_id = {i["native_id"]: i for i in items}
    rows = []
    for out in data["items"]:
        src = by_id.get(out.get("id"))
        if not src:
            continue
        what = (out.get("what") or "").strip()
        if not what:
            continue
        rows.append({
            "id": commitment_id(src.get("source", ""), src["native_id"], what),
            "direction": "owed_by_me",
            "what": what[:200],
            "asker": (out.get("from") or "").strip()[:40] or None,
            "via": via_for(src),
            "source": src.get("source", ""),
            "native_id": src["native_id"],
            "kind": src.get("kind", ""),
            "from_user": src.get("from_user") or "",
            "source_link": src.get("link", ""),
            "evidence": (src.get("text") or "")[:200],
            "due": _val(out.get("due")),
            "due_confidence": 0.8 if _val(out.get("due")) else 0.0,
            "cycle": None,
            "status": "open",
            "stalled_since": None,
            "ack_policy": "bot_may_ack",
            "closure": "open",
            # Client attribution belongs to the rule matcher, not the model. The 3B
            # model invented "ioi" for DMs that had nothing to do with IOI.
            "client": None,
            "created_at": src.get("ts") or now.isoformat(),
            "last_activity": src.get("ts") or now.isoformat(),
            "closed_at": None,
            "closed_how": None,
        })
    return rows
