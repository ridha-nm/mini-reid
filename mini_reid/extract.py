"""Rule-based commitment extraction. No model, no network."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .ledger import commitment_id

BOT_AUTHOR = re.compile(
    r"(demo app|\[bot\]|^jira$|automation for jira|pantas-green-release|^mini-?reid$)",
    re.I)
JIRA_NOTIFY = re.compile(r"atlassian\.net|\(jira\)|jira automation", re.I)
ASK = re.compile(
    r"\?|\b(please|pls|plz|can you|can u|could you|kindly|confirm|review|send|share|"
    r"provide|update|follow up|action|need you|let us know|let me know|approve|"
    r"join|huddle|call|check)\b", re.I)
MENTION = re.compile(r"<@[A-Z0-9]+>")
CHATTER = re.compile(
    r"\b(lol|haha+|bahaha+|im tired|i'?m tired|no worries|working on it|"
    r"noted|got it|sure|yep|yeah|okay|ok|thanks|thank you|see you|hmm)\b", re.I)
BOILERPLATE_TEXT = re.compile(
    r"accounts\.google\.com|gmail is email that|unsubscribe", re.I)
SIGNATURE = re.compile(
    r"(ridha mohamed\s+sustainability data analyst|best regards,?\s*ridha|"
    r"mobile\. \+60|web\. www\.pantas\.com|address\. unit)",
    re.I,
)
WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def parse_due(text: str, now: datetime) -> tuple[str | None, float]:
    """Return (ISO date, confidence). Never invents a date."""
    t = (text or "").lower()

    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text or "")
    if m:
        return m.group(1), 0.95

    if "end of next week" in t:
        days_to_friday = (4 - now.weekday()) % 7
        return (now + timedelta(days=days_to_friday + 7)).date().isoformat(), 0.7

    if re.search(r"\btoday\b|\beod\b|\beob\b", t):
        return now.date().isoformat(), 0.7
    if re.search(r"\btomorrow\b", t):
        return (now + timedelta(days=1)).date().isoformat(), 0.7

    for name, idx in WEEKDAYS.items():
        if re.search(r"\b" + name + r"\b", t):
            return (now + timedelta(days=(idx - now.weekday()) % 7)).date().isoformat(), 0.7

    return None, 0.0


def via_for(item: dict) -> str:
    """Where it reached Ridha, and why it is his rather than the BD alias's."""
    if item.get("kind") == "dm":
        return "DM"
    if item.get("source") == "slack":
        return f"#{item.get('channel') or 'slack'}"
    if item.get("source") == "jira":
        return "Jira"
    if item.get("source") == "gmail":
        to = (item.get("to") or "").lower()
        return "direct" if "ridha" in to else "bd@pantas.com"
    return "manual"


def _asker(author: str) -> str | None:
    raw = (author or "").split("<")[0].strip().strip('"').strip()
    if raw and "@" not in raw:
        return raw[:40]
    m = re.search(r"([A-Za-z][A-Za-z.'-]+)@", author or "")
    return m.group(1).replace(".", " ").title()[:40] if m else None


def _clean(text: str) -> str:
    import html

    text = html.unescape(text or "")
    text = MENTION.sub("", text)
    m = SIGNATURE.search(text)
    if m:
        text = text[: m.start()]
    # URLs carry "?" and query junk. They are not questions and not task text.
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"<(?:https?://)[^>]*>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract(item: dict, client: dict | None, now: datetime) -> list[dict]:
    """One raw item may yield several commitments; rules yield at most one."""
    author = item.get("author") or ""
    if BOT_AUTHOR.search(author):
        return []
    # Sent mail is activity, not a new commitment. It updates the ledger later.
    if item.get("kind") == "sent":
        return []
    # Jira notification mail duplicates the Jira API source.
    if JIRA_NOTIFY.search(author) and item.get("source") == "gmail":
        return []
    text = _clean(item.get("text") or "")
    if len(text) < 8:
        return []
    # Never ingest our own digest or alerts.
    if text.startswith("Mini-Reid —") or "open commitments. Nothing sent." in text:
        return []

    marker = BOILERPLATE_TEXT.search(text)
    if marker:
        text = text[: marker.start()].strip()
        if len(text) < 12:
            return []

    # A DM is a conversation. Only an actual ask, question or dated request counts.
    # Search can also return a DM message as a "mention", so check the flag too.
    if item.get("is_dm") or item.get("kind") == "dm":
        if len(text) < 20 and "?" not in text:
            return []
        if CHATTER.search(text) and "?" not in text:
            return []
    # An inbox email only becomes a commitment when it actually asks for something.
    if item.get("source") == "gmail" and item.get("kind") == "inbox" and not ASK.search(text):
        return []

    if item.get("due"):
        due, conf = item["due"], 0.95
    else:
        due, conf = parse_due(f"{item.get('subject') or ''} {text}", now)

    # A DM only counts when it actually asks for something, or carries a date.
    if (item.get("is_dm") or item.get("kind") == "dm") and not (ASK.search(text) or due):
        return []

    # Shared-alias mail with no date and no direct address is not Ridha's work.
    if item.get("source") == "gmail" and item.get("kind") == "inbox" and due is None:
        to = (item.get("to") or "").lower()
        if "ridha" not in to and "ridha" not in text.lower():
            return []
    ts = item.get("created_at") or item.get("ts") or now.isoformat()
    # A subject line is a task name. The body opens with "Hi X, thanks for..."
    subject = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", item.get("subject") or "", flags=re.I)
    what_text = subject.strip() if (item.get("source") == "gmail" and subject.strip()) else text

    return [{
        "id": commitment_id(item.get("source", ""), item.get("native_id", ""), what_text),
        "direction": item.get("direction", "owed_by_me"),
        "what": what_text[:200],
        # A draft is Ridha replying, so the asker is whoever he is replying to.
        "asker": _asker(item.get("to") or "") if item.get("kind") == "draft" else _asker(author),
        "via": via_for(item),
        "source": item.get("source", ""),
        "native_id": item.get("native_id", ""),
        "kind": item.get("kind", ""),
        "source_link": item.get("link", ""),
        "evidence": text[:200],
        "due": due,
        "due_confidence": conf,
        "cycle": (client or {}).get("cycle"),
        "status": "open",
        "stalled_since": None,
        "ack_policy": "bot_may_ack",
        "closure": "open",
        "client": (client or {}).get("slug"),
        "created_at": ts,
        "last_activity": ts,
        "closed_at": None,
        "closed_how": None,
    }]
