"""Model providers. Local by default: nothing leaves the machine."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime

from .ledger import commitment_id

SCHEMA = {
    "items": [
        {
            "id": "the id you were given",
            "is_commitment": True,
            "what": "the task as a short imperative, max 120 chars, rewritten not copied",
            "from": "who asked, first name or team, empty if unclear",
            "due": "YYYY-MM-DD or null",
            "client": "client slug or null",
        }
    ]
}

PROMPT = """You extract commitments from work messages.

For each message decide if someone owes something:
- is_commitment is true only if a person was asked to do something, or promised to do something.
- Ignore status updates, FYIs, automated notices, meeting notes with no action, greetings, and thanks.
- Ignore replies that only acknowledge, agree, joke, or mention someone in passing.
- Ignore anything that is a description of work already done.
- due is null unless the text states or clearly implies a date.
- what is the actual task, rewritten in your own words as a short imperative. Never copy the greeting, the email header, the signature or the opening line. Max 120 characters.
- from is the person or team who asked.
- client is one of: {clients}, or null.

Ridha has previously said these are NOT commitments. Ignore the same kind of message:
{ignored}

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


def _batch_prompt(items: list[dict], now: datetime, clients: list[str]) -> str:
    from .learning import ignored_examples

    payload = [{"id": i["native_id"], "text": (i.get("text") or "")[:500],
                "from": i.get("author", "")} for i in items]
    ignored = ignored_examples()
    return PROMPT.format(
        clients=", ".join(clients),
        ignored="\n".join(f"- {x}" for x in ignored) if ignored else "- none yet",
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
    data = provider.complete(_batch_prompt(items, now, clients or []))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError(f"model returned unexpected shape: {str(data)[:200]}")

    valid_clients = set(clients or [])
    by_id = {i["native_id"]: i for i in items}
    rows = []
    for out in data["items"]:
        src = by_id.get(out.get("id"))
        if not src or not out.get("is_commitment"):
            continue
        what = (out.get("what") or "").strip()
        if not what:
            continue
        rows.append({
            "id": commitment_id(src.get("source", ""), src["native_id"], what),
            "direction": "owed_by_me",
            "what": what[:200],
            "asker": (out.get("from") or "").strip()[:40] or None,
            "source": src.get("source", ""),
            "native_id": src["native_id"],
            "kind": src.get("kind", ""),
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
