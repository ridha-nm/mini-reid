"""Rule-based commitment extraction. No model, no network."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from .ledger import commitment_id

BOT_AUTHOR = re.compile(
    r"(demo app|\[bot\]|^jira$|automation for jira|pantas-green-release|^mini-?reid$)",
    re.I)
JIRA_NOTIFY = re.compile(r"atlassian\.net|\(jira\)|jira automation", re.I)
# The triager bot tags people on every routed issue; those are not asks.
IGNORE_CHANNELS = {"bd-triager-agent", "C0B59LA0X5M"}
REQUEST_MODAL = re.compile(r"\b(?:can|could|would|will)\s+(?:you|u)\b", re.I)
REQUEST_POLITE = re.compile(
    r"\b(?:please|pls|plz|kindly|action required)\b", re.I)
REQUEST_NEED = re.compile(
    r"\b(?:we\s+need|need\s+(?:you|your|the|a|an|it|this|that|by))\b", re.I)
# A polite word alone is politeness, not an ask: "please note the office is
# closed" must not skip the click. It needs a request verb in the same sentence.
POLITE_REQUEST = re.compile(
    r"\b(?:please|pls|plz|kindly)\b[^.!?\n]{0,60}?"
    r"\b(?:can|could|would|will|send|share|provide|confirm|review|approve|update|"
    r"check|prepare|draft|book|schedule|fix|add|remove|create|complete|finish|"
    r"submit|sign|pay|call|join|reply|respond|get|start|do|make|write|build|test|"
    r"read|open|close|look|take|follow|need)\b", re.I)
ACTION_REQUIRED = re.compile(r"\baction required\b", re.I)
EXPLICIT_ASK = re.compile(
    REQUEST_MODAL.pattern + "|" + REQUEST_NEED.pattern + "|"
    + ACTION_REQUIRED.pattern + "|" + POLITE_REQUEST.pattern,
    re.I)
IMPERATIVE = re.compile(
    r"^(?:please\s+)?(?:send|share|provide|confirm|review|approve|update|check|"
    r"prepare|draft|book|schedule|fix|add|remove|create|complete|finish|submit|"
    r"sign|pay|call|join|reply|respond|get|start|do|make|write|build|test|read|"
    r"open|close|look|take|follow|need)\b", re.I)
STATUS_PREFIX = re.compile(r"^\s*(?:update|status|fyi)\s*:", re.I)
MENTION = re.compile(r"<@[A-Z0-9]+>")
CHATTER = re.compile(
    r"\b(lol|haha+|bahaha+|im tired|i'?m tired|no worries|working on it|"
    r"noted|got it|sure|yep|yeah|okay|ok|thanks|thank you|see you|hmm)\b", re.I)
# Festive and social messages are not commitments, even when they tag people.
GREETING = re.compile(
    r"^(?:happy|merry|wishing|wish|congrats|congratulations|cheers|"
    r"have fun|well done|kudos)\b"
    r"|\b(?:wishing you|happy (?:diwali|deepavali|birthday|holidays|new year)|"
    r"merry christmas|eid mubarak|gong xi|selamat hari raya|have fun)\b", re.I)
# Playful requests to the bot are never commitments, tagged or not.
PLAY_REQUEST = re.compile(
    r"(?:\b(?:give|send)\s+"
    r"(?:<@[A-Z0-9]+(?:\|[^>]*)?>|@?[\w.'-]+)\s+(?:a\s+)?"
    r"(?:hug|high[ -]?five|fist[ -]?bump|pat on the back)\b"
    r"|\b(?:hug|high[ -]?five|fist[ -]?bump|pat on the back)\s+(?:to\s+)?"
    r"(?:<@[A-Z0-9]+(?:\|[^>]*)?>|@?[\w.'-]+))", re.I)
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
MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
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

    # An explicit day and month beats a weekday: "Thursday Nov 12" is Nov 12.
    m = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b", t)
    if m:
        day, month = int(m.group(1)), MONTHS[m.group(2)]
    else:
        m = re.search(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+"
            r"(\d{1,2})(?:st|nd|rd|th)?\b", t)
        day, month = (int(m.group(2)), MONTHS[m.group(1)]) if m else (None, None)
    if day:
        try:
            found = now.replace(month=month, day=day, hour=0, minute=0,
                                second=0, microsecond=0)
        except ValueError:
            found = None
        if found:
            if found.date() < now.date():
                found = found.replace(year=found.year + 1)
            return found.date().isoformat(), 0.9

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
        return "email"
    return "manual"


def _asker(author: str) -> str | None:
    """Name and address for mail; name alone for Slack and Jira."""
    email = re.search(r"[\w.+-]+@[\w.-]+", author or "")
    name = (author or "").split("<")[0].strip().strip('"').strip()
    if "@" in name:
        name = ""
    if name and email:
        return f"{name} ({email.group(0)})"[:80]
    if email:
        return email.group(0)[:80]
    return name[:40] if name else None


EPIC_TYPES = {"epic", "initiative", "theme"}


def looks_actionable(text: str, item: dict) -> bool:
    """Strict gate: a request, an imperative, or a channel mention.

    Questions with no ask ("do you have access?", "Den i ??") and status
    updates are not commitments. Channel mentions are kept: they are
    addressed to Ridha, and that is the signal that matters most. A draft is
    Ridha's own unsent writing, not an ask; an Epic is a container, not a task.
    """
    if item.get("kind") == "draft":
        return False
    if item.get("source") == "jira":
        return (item.get("issue_type") or "").lower() not in EPIC_TYPES
    if STATUS_PREFIX.search(text):
        return False
    asked = bool(REQUEST_MODAL.search(text) or REQUEST_POLITE.search(text)
                 or REQUEST_NEED.search(text) or IMPERATIVE.search(text))
    if item.get("source") == "slack" and item.get("kind") == "mention":
        return asked or not CHATTER.search(text)
    return asked


def auto_reason(item: dict, text: str, due: str | None,
                me: str | None) -> str | None:
    """Why this row can skip the click, or None to keep it in Inbox."""
    source = item.get("source") or ""
    kind = item.get("kind") or ""
    ask = bool(EXPLICIT_ASK.search(text or ""))
    if source == "slack" and kind == "mention" and ask:
        return "slack-direct-ask"
    if source == "slack" and kind == "dm" and (ask or due):
        return "slack-dm-ask"
    if source == "gmail" and kind == "inbox":
        needle = (me or "Ridha").split("@")[0].lower()
        # Stricter than the Inbox gate: a body mention is enough to keep the
        # mail, but only a To: address may skip the click.
        direct = needle in (item.get("to") or "").lower()
        if direct and (ask or due):
            return "email-direct-ask"
    return None


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


def extract(item: dict, client: dict | None, now: datetime,
            me: str | None = None) -> list[dict]:
    """One raw item may yield several commitments; rules yield at most one."""
    author = item.get("author") or ""
    if BOT_AUTHOR.search(author):
        return []
    if item.get("source") == "slack" and (item.get("channel") in IGNORE_CHANNELS
                                          or item.get("channel_id") in IGNORE_CHANNELS):
        return []
    # Calendar responses are not work items. One invite can generate several.
    if item.get("source") == "gmail" and re.match(
            r"^\s*(accepted|declined|tentative|invitation|updated invitation|"
            r"canceled|cancelled|new event|reminder)\s*:", item.get("subject") or "", re.I):
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
    if PLAY_REQUEST.search(text):
        return []
    # Never ingest our own digest or alerts.
    if text.startswith("Mini-Reid —") or "open commitments. Nothing sent." in text:
        return []

    marker = BOILERPLATE_TEXT.search(text)
    if marker:
        text = text[: marker.start()].strip()
        if len(text) < 12:
            return []

    gate_text = f"{item.get('subject') or ''} {text}".strip()
    if not looks_actionable(gate_text, item):
        return []
    # A greeting that tags people is still a greeting, unless it also asks.
    if (GREETING.search(gate_text)
            and not (REQUEST_MODAL.search(gate_text)
                     or REQUEST_POLITE.search(gate_text)
                     or REQUEST_NEED.search(gate_text))):
        return []

    if item.get("due"):
        due, conf = item["due"], 0.95
    else:
        due, conf = parse_due(f"{item.get('subject') or ''} {text}", now)

    # Shared-alias mail with no date and no direct address is not this user's work.
    if item.get("source") == "gmail" and item.get("kind") == "inbox" and due is None:
        to = (item.get("to") or "").lower()
        needle = ((me or "Ridha").split("@")[0]).lower()
        if needle not in to and needle not in text.lower():
            return []
    ts = item.get("created_at") or item.get("ts") or now.isoformat()
    # A subject line is a task name. The body opens with "Hi X, thanks for..."
    subject = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", item.get("subject") or "", flags=re.I)
    what_text = subject.strip() if (item.get("source") == "gmail" and subject.strip()) else text
    reason = auto_reason(item, gate_text, due, me)

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
        "from_user": item.get("from_user") or "",
        "source_link": item.get("link", ""),
        "evidence": text[:200],
        "due": due,
        "due_confidence": conf,
        "cycle": (client or {}).get("cycle"),
        "capture": "auto" if reason else "inbox",
        "capture_why": reason or "",
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
