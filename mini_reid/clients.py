"""Client registry and matching. Pure, no network."""
from __future__ import annotations

import json
import re
from pathlib import Path

_EMAIL = re.compile(r"@([A-Za-z0-9.-]+)")


def load_clients(path: str = "clients.json") -> dict[str, dict]:
    return json.loads(Path(path).read_text())


def _domain(sender: str) -> str | None:
    m = _EMAIL.search(sender or "")
    return m.group(1).lower().rstrip(".") if m else None


def _domain_match(sender: str, client: dict) -> bool:
    dom = _domain(sender)
    if not dom:
        return False
    return any(dom == d.lower() or dom.endswith("." + d.lower())
               for d in client.get("domains", []))


def _text_match(text: str, client: dict) -> bool:
    low = (text or "").lower()
    terms = [client.get("name", "")] + list(client.get("aliases", []))
    for term in terms:
        if not term:
            continue
        if re.search(r"\b" + re.escape(term.lower()) + r"\b", low):
            return True
    return False


def match_client(text: str, sender: str, clients: dict[str, dict],
                 channel: str | None = None) -> dict | None:
    """Return {slug, name, group, matched_by} or None.

    Order: sender domain, then Slack channel, then client name in text.
    Unknown senders return None. The caller records them for review; this
    function never guesses a client.
    """
    for slug, c in clients.items():
        if _domain_match(sender, c):
            return {"slug": slug, "name": c["name"], "group": c["group"],
                    "matched_by": "domain"}
    if channel:
        for slug, c in clients.items():
            if channel in c.get("slack_channels", []):
                return {"slug": slug, "name": c["name"], "group": c["group"],
                        "matched_by": "channel"}
    for slug, c in clients.items():
        if _text_match(text, c):
            return {"slug": slug, "name": c["name"], "group": c["group"],
                    "matched_by": "text"}
    return None
