"""Slack command parsing and the Socket Mode listener."""
from __future__ import annotations

import json
import re
import threading
import urllib.parse
from datetime import timedelta
from pathlib import Path

from .capture import parse_capture
from .ledger import commitment_id, load, merge, save

# Slack sends mentions as <@U123> or <@U123|mini-reid>. Both must strip cleanly.
MENTION = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")
# Strip only the mentions that address the bot at the start. A recipient
# mention ("remind <@U123> to ...") must survive for split_target.
LEADING_MENTION = re.compile(
    r"^\s*(?:(?:<@[A-Z0-9]+(?:\|[^>]*)?>|@mini-?reid)\s*)+", re.I)
COMMANDS = {"add", "note", "done", "drop", "due", "snooze", "waiting", "find",
            "list", "not", "remind", "edit", "status", "priority", "prio",
            "combine", "uncombine", "convert", "tonote", "undo"}
MUTATING = {"add", "note", "done", "drop", "due", "snooze", "waiting", "not",
            "remind", "edit", "status", "priority", "prio", "combine", "uncombine",
            "convert", "tonote"}
IGNORE_CHANNEL_IDS = {"C0B59LA0X5M"}  # bd-triager-agent
# Successful writes acknowledged with a reaction instead of a reply.
EMOJI_ACKS = {"add": "heavy_plus_sign", "note": "memo",
              "tonote": "memo", "convert": "memo"}
STATUS_ALIASES = {
    "open": "open", "todo": "open", "pending": "open",
    "in progress": "in progress", "in-progress": "in progress",
    "inprogress": "in progress", "doing": "in progress", "active": "in progress",
    "blocked": "blocked", "block": "blocked", "stuck": "blocked",
}

TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b"
    r"|\b(?:at\s+)(\d{1,2}):(\d{2})\b", re.I)
RELATIVE = re.compile(
    r"\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\b", re.I)
DATE_TOKEN = re.compile(
    r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{4}-\d{2}-\d{2})\b", re.I)


def parse_remind(body: str, now) -> tuple[dict | None, str]:
    """Return (row_fields, cleaned_what). Time is optional; date defaults today."""
    from .extract import parse_due

    rel = RELATIVE.search(body or "")
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("min"):
            delta = timedelta(minutes=n)
        elif unit.startswith("h"):
            delta = timedelta(hours=n)
        elif unit.startswith("d"):
            delta = timedelta(days=n)
        else:
            delta = timedelta(weeks=n)
        at = (now + delta).replace(second=0, microsecond=0)
        clean = re.sub(r"\s+", " ", RELATIVE.sub(" ", body or "")).strip(" ,.")
        return ({"remind_at": at.isoformat(), "due": at.date().isoformat(),
                 "what": clean or body}, clean)

    hour = minute = None
    m = TIME_RE.search(body or "")
    if m:
        if m.group(1):
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            ampm = (m.group(3) or "").lower()
        else:
            hour, minute = int(m.group(4)), int(m.group(5))
            ampm = ""
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None, body

    date_text = DATE_TOKEN.search(body or "")
    date_iso, _ = parse_due(body or "", now)
    if date_iso is None and hour is not None:
        date_iso = now.date().isoformat()

    clean = TIME_RE.sub(" ", body or "")
    clean = DATE_TOKEN.sub(" ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" ,.")

    # No time and no date: remind now. A reminder that needs a schedule is
    # friction; "remind me to X" should just send it.
    if date_iso is None and hour is None:
        return ({"remind_at": now.replace(microsecond=0).isoformat(timespec="seconds"),
                 "due": now.date().isoformat(), "what": clean or body,
                 "immediate": True}, clean or body)

    if date_iso is None:
        return None, body

    if hour is None:
        at = f"{date_iso}T09:00:00+08:00"
    else:
        at = f"{date_iso}T{hour:02d}:{minute:02d}:00+08:00"
        if date_text is None:
            candidate = __import__("datetime").datetime.fromisoformat(at)
            if candidate <= now:
                at = (candidate + timedelta(days=1)).isoformat(timespec="seconds")
    return {"remind_at": at, "due": date_iso, "what": clean or body}, clean


QUERY = re.compile(
    r"^\s*(what|when|who|how|show|list|any|status|which)\b|\?\s*$", re.I)


def owner_action(action: str, body: str) -> str:
    """Ridha can talk normally. A question stays a question; anything else is a note."""
    text = (body or "").strip()
    if action == "unknown" and text:
        if not QUERY.search(text):
            return "note"
        if re.search(r"\b(due|today|tomorrow|open|status|overdue)\b", text, re.I):
            return "list"
        return "ask"
    return action


def other_note(action: str, body: str, user: str) -> str | None:
    """What someone else's message becomes.

    Any sentence counts. A command keeps its words, free text keeps its words,
    and only pure acknowledgements ("thanks") leave no trace.
    """
    text = (body or "").strip()
    if not text:
        return None
    if action in MUTATING or action == "unknown":
        return f"from <@{user}>: {text}"
    return None

HELP = """*Mini-Reid commands*
• `add: confirm Eupe waste by Friday` — new task
• `note: Daniel wants the mapping redone` — remember it, no deadline
• `done: Eupe waste` — close it
• `due: Eupe waste by Monday` — change the date
• `edit: #1 to Confirm Eupe waste mapping by Monday` — rename and re-date
• `snooze: Eupe waste 3d` — push it out (d days, w weeks)
• `waiting: Eupe waste on Daniel` — waiting on someone else
• `status: Eupe waste in progress` — or `blocked`, `open`
• `priority: Eupe waste 1` — P1 first; `high`, `medium`, `low`, `none` also work
• `tonote: Eupe waste` — keep the text, drop it from tasks into Notes
• `combine: #9 into #7` — merge duplicate task #9 into #7
• `uncombine: #7` — restore everything merged into #7
• `undo:` — reverse the last ledger change (10 deep)
• Every `list` row has a stable id: `abc123` or `id:abc123` works in every command
• `drop: Eupe waste` — remove it quietly (`remove:` and `delete:` work too)
• `not: anything that is not part c` — wrong item, teach it to ignore this kind
• `remind me to send the deck tomorrow at 3pm` — a timed DM; no time means now
• `remind @Arman to send the deck at 3pm` — DM someone else (anyone can set these)
• `ask: what did we agree with Eupe on waste` — answer from your own writing, with sources
• `find: eupe` — search the ledger
• `list` — numbered open items; `#1` works with done, due, drop, edit and snooze
• `help` — this

You can also just ask me something and I will say if I cannot do it."""


def split_target(body: str, users: dict[str, str],
                 sender: str) -> tuple[str | None, str]:
    """Split 'remind Arman to X' into (Arman's id, 'X'). None = self.

    A mention, 'me', 'for <name>', or '<name> to' names the recipient. Anything
    else stays part of the reminder text.
    """
    text = (body or "").strip()
    m = re.match(r"^(?:for\s+)?<@([A-Z0-9]+)(?:\|[^>]*)?>\s*:?\s*(?:to\s+)?",
                 text, re.I)
    if m:
        return m.group(1), text[m.end():].strip()
    m = re.match(r"^me\s*:?\s*(?:to\s+)?", text, re.I)
    if m:
        return sender, text[m.end():].strip()
    # A typed "@XieYi" that Slack did not turn into a <@U…> mention.
    m = re.match(r"^@([A-Za-z0-9._'-]+)\s*:?\s*(?:to\s+)?", text, re.I)
    if m and users.get(m.group(1).lower()):
        return users[m.group(1).lower()], text[m.end():].strip()
    m = re.match(r"^for\s+([A-Za-z0-9._'-]+)\s*:?\s*(?:to\s+)?", text, re.I)
    if m and users.get(m.group(1).lower()):
        return users[m.group(1).lower()], text[m.end():].strip()
    m = re.match(r"^([A-Za-z0-9._'-]+)\s+to\s+", text, re.I)
    if m and users.get(m.group(1).lower()):
        return users[m.group(1).lower()], text[m.end():].strip()
    # Full names with spaces: longest known name that starts the text.
    low = text.lower()
    for name in sorted(users, key=len, reverse=True):
        if low.startswith(name):
            rest = text[len(name):]
            # Require "to" or a colon, so "add: <name> asked for X" stays a task.
            m = re.match(r"^\s*(?::\s*|to\s+)", rest, re.I)
            if m:
                return users[name], rest[m.end():].strip()
    return None, text


def unresolved_recipient(body: str, users: dict[str, str]) -> str | None:
    """Name the caller meant as recipient but that is not in this workspace."""
    text = (body or "").strip()
    m = re.match(r"^@([A-Za-z0-9._'-]+)", text)
    if m:
        return None if users.get(m.group(1).lower()) else m.group(1)
    m = re.match(r"^([A-Za-z0-9._'-]+)\s+to\s+", text, re.I)
    if m:
        name = m.group(1)
        if name.lower() == "me":
            return None
        return None if users.get(name.lower()) else name
    # A capitalised full name before "to", e.g. "Daniel Hwang to send …".
    m = re.match(r"^(.+?)\s+to\s+", text, re.I)
    if m:
        name = m.group(1).strip()
        words = name.split()
        if (1 <= len(words) <= 3 and all(w[:1].isupper() for w in words)
                and name.lower() not in users):
            return name
    return None


def should_schedule_reminder(action: str, requester: str, owner: str,
                             target: str | None) -> bool:
    """All reminders are Slack-scheduled. `add:` only leaves the owner's ledger
    when it names another person or comes from someone else."""
    if action == "remind":
        return True
    if action == "add":
        return requester != owner or (target is not None and target != owner)
    return False


def load_users(token: str) -> dict[str, str]:
    """Lowercased workspace name -> user id. Ambiguous names are left out."""
    from .sources import _get_json

    found: dict[str, set[str]] = {}
    cursor = ""
    while True:
        url = "https://slack.com/api/users.list?limit=200"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor)
        d = _get_json(url, {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            break
        for u in d.get("members") or []:
            if u.get("deleted") or u.get("is_bot"):
                continue
            p = u.get("profile") or {}
            names = {u.get("name") or "", p.get("display_name") or "",
                     p.get("real_name") or "",
                     (p.get("real_name") or "").split(" ")[0]}
            for name in names:
                key = name.strip().lower()
                if key:
                    found.setdefault(key, set()).add(u["id"])
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return {k: next(iter(v)) for k, v in found.items() if len(v) == 1}


def is_bot_addressed(event: dict, bot_user_id: str) -> bool:
    """DMs reach the bot directly; channel messages must mention it."""
    channel = event.get("channel") or ""
    if channel.startswith("D"):
        return True
    return bool(bot_user_id) and f"<@{bot_user_id}>" in (event.get("text") or "")


def edit_ack_target(event: dict, bot_user_id: str) -> tuple[str, str] | None:
    """An edit that still mentions the bot gets a ✅. It is not re-run.

    Slack never refires app_mention for an edited message, so without this the
    edit is invisible. Replaying the command would duplicate ledger rows.
    """
    if event.get("subtype") != "message_changed" or not bot_user_id:
        return None
    msg = event.get("message") or {}
    if msg.get("bot_id") or not msg.get("user"):
        return None
    channel = event.get("channel") or ""
    ts = msg.get("ts") or ""
    if not (channel and ts) or f"<@{bot_user_id}>" not in (msg.get("text") or ""):
        return None
    return channel, ts


def parse_command(text: str) -> tuple[str, str]:
    """Return (action, body). action is one of COMMANDS, or ack|unknown|list."""
    body = LEADING_MENTION.sub("", text or "").strip()
    if not body:
        return "unknown", ""
    if body.lower() in {"list", "ls", "today", "open"}:
        return "list", ""
    if body.lower() in {"help", "?", "commands"}:
        return "help", ""
    m = re.match(
        r"^(add|task|todo|to-do|note|done|drop|remove|delete|due|snooze|waiting|"
        r"find|not|remind|ask|edit|status|priority|prio|combine|uncombine|"
        r"convert|tonote|undo)\s*:\s*(.*)$", body, re.I)
    if m:
        act = m.group(1).lower()
        if act in {"task", "todo", "to-do"}:
            act = "add"
        elif act in {"remove", "delete"}:
            act = "drop"
        return act, m.group(2).strip()
    m = re.match(r"^(?:please\s+)?remind(?:\s+me)?(?:\s+to)?\s+(.+)$", body, re.I)
    if m:
        return "remind", m.group(1).strip()

    # Natural ways to say "put this on my list".
    m = re.match(
        r"^(?:add|task|todo|to-do)\s+(?:this\s+)?"
        r"(?:to\s+(?:my\s+)?(?:to-?do(?:\s+list)?|list|tasks?)\s*:?\s*)?(.+)$",
        body, re.I)
    if m:
        return "add", m.group(1).strip()
    m = re.match(r"^note\s+(?:that\s+)?(.+)$", body, re.I)
    if m:
        return "note", m.group(1).strip()

    if re.match(r"^(thanks|thank you|noted|ok|okay|got it)\b", body, re.I):
        return "ack", body
    return "unknown", body


def _candidates(rows: list[dict], target: str) -> list[dict]:
    """Substring first, then word-overlap. Few words is enough."""
    from .closure import _words

    t = (target or "").lower().strip()
    if not t:
        return []
    open_rows = [r for r in rows if r.get("status") not in {"done", "dropped"}]
    exact = [r for r in open_rows if t in (r.get("what") or "").lower()]
    if exact:
        return exact

    want = _words(t)
    if not want:
        return []
    scored = []
    for r in open_rows:
        have = _words(r.get("what") or "")
        score = len(want & have) / len(want)
        if score >= 0.6:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored]


def _ref(row: dict) -> str:
    """Sender, channel and source link for a list line."""
    who = f"from {row['asker']}" if row.get("asker") else ""
    if row.get("via"):
        who = f"{who} ({row['via']})" if who else row["via"]
    out = f" — {who}" if who else ""
    if row.get("source_link"):
        out += f" — <{row['source_link']}|open>"
    return out


def _open_sorted(rows: list[dict]) -> list[dict]:
    """The order `list` prints; numbers stay stable across commands."""
    open_rows = [r for r in rows if r.get("status") not in {"done", "dropped"}
                 and r.get("kind") != "note"]
    open_rows.sort(key=lambda r: (r.get("priority") or 99, r.get("due") or "9999"))
    return open_rows


def _pick(rows: list[dict], target: str) -> tuple[dict | None, str | None]:
    """Return (row, error). `#N` picks from the numbered list; `id:abc123`
    is stable across edits and reordering."""
    t = (target or "").strip()
    m = re.fullmatch(r"(?:id:)?([0-9a-f]{4,40})", t, re.I)
    if m:
        prefix = m.group(1).lower()
        hits = [r for r in rows if r.get("status") not in {"done", "dropped"}
                and r["id"].startswith(prefix)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, f"{prefix} matches more than one item. Use more characters."
        if t.lower().startswith("id:"):
            return None, f"No open item matches id:{prefix}."
        # Not a known id: fall through, a short title could look like hex.
    m = re.fullmatch(r"#(\d+)", t)
    if m:
        items = _open_sorted(rows)
        i = int(m.group(1))
        if 1 <= i <= len(items):
            return items[i - 1], None
        return None, f"No open item #{i}."
    found = _candidates(rows, target)
    if not found:
        return None, f"No open item matches “{target}”."
    t = (target or "").lower().strip()
    if len(found) > 1 and t not in (found[0].get("what") or "").lower():
        listing = "\n".join(f"• {r['what'][:80]}" for r in found[:3])
        return None, f"Which one?\n{listing}\nAdd a word that only fits one."
    return found[0], None


def _shift(text: str, now):
    """Parse '3d', '2w', or a date phrase into an ISO date."""
    from .extract import parse_due

    m = re.fullmatch(r"\s*(\d+)\s*([dw])\s*", text or "", re.I)
    if m:
        days = int(m.group(1)) * (7 if m.group(2).lower() == "w" else 1)
        return (now + timedelta(days=days)).date().isoformat()
    return parse_due(text, now)[0]


UNDO_DEPTH = 10


def _undo_path(ledger_path: str) -> Path:
    return Path(ledger_path).with_name(Path(ledger_path).stem + "_undo.json")


def _push_undo(ledger_path: str, before: str) -> None:
    path = _undo_path(ledger_path)
    data = json.loads(path.read_text()) if path.exists() else {}
    stack = data.get("snapshots") or []
    stack.append(before or "[]")
    path.write_text(json.dumps({"snapshots": stack[-UNDO_DEPTH:]}))


def apply_command(action: str, body: str, now, clients: dict, ledger_path: str) -> str:
    """Run a command, and snapshot the ledger before any mutation so `undo:`
    can reverse it."""
    path = Path(ledger_path)
    before = path.read_text() if path.exists() else ""
    reply = _apply_command(action, body, now, clients, ledger_path)
    if action in MUTATING:
        after = path.read_text() if path.exists() else ""
        if after and after != before:
            _push_undo(ledger_path, before)
    return reply


def _apply_command(action: str, body: str, now, clients: dict, ledger_path: str) -> str:
    """Mutate the ledger and return the reply text. Pure enough to test."""
    rows = load(ledger_path)

    if action == "undo":
        path = _undo_path(ledger_path)
        stack = (json.loads(path.read_text()).get("snapshots") or []) if path.exists() else []
        if not stack:
            return "Nothing to undo."
        Path(ledger_path).write_text(stack.pop())
        path.write_text(json.dumps({"snapshots": stack}))
        return "Undone the last ledger change."

    if action == "add":
        row = parse_capture(f"add: {body}", now, clients)
        if row is None:
            return "Could not read that. Use: add: <what> by <when>"
        save(ledger_path, merge(rows, [row]))
        due = f" · due {row['due']}" if row["due"] else ""
        client = f"{row['client']} · " if row["client"] else ""
        return f"Added. {client}{row['what']}{due}"

    if action == "note":
        row = {
            "id": commitment_id("manual", body.lower(), body),
            "direction": "owed_by_me", "what": body[:200], "source": "manual",
            "native_id": body.lower(), "kind": "note", "source_link": "",
            "evidence": body[:200], "due": None, "due_confidence": 0.0,
            "cycle": None, "status": "open", "stalled_since": None,
            "ack_policy": "bot_may_ack", "closure": "open", "client": None,
            "created_at": now.isoformat(), "last_activity": now.isoformat(),
            "closed_at": None, "closed_how": None,
        }
        save(ledger_path, merge(rows, [row]))
        return "Noted."

    if action in {"convert", "tonote"}:
        row, err = _pick(rows, body)
        if err:
            return err
        row["kind"] = "note"
        row["due"] = None
        row["status"] = "open"
        row["last_activity"] = now.isoformat()
        for key in ("priority", "stalled_since", "stalled_reason"):
            row.pop(key, None)
        save(ledger_path, rows)
        return f"Converted to note: {row['what'][:80]}"

    if action in {"priority", "prio"}:
        m = re.match(r"^(.*?)\s+(?:to\s+)?(p?[1-5]|high|medium|med|low|none|clear)$",
                     body or "", re.I)
        if not m:
            return "Use: priority: <item> 1-5 | high | medium | low | none"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        word = m.group(2).lower().lstrip("p")
        value = {"high": 1, "medium": 3, "med": 3, "low": 5,
                 "none": None, "clear": None}.get(word, None)
        if value is None and word not in {"none", "clear"}:
            value = int(word)
        if value is None:
            row.pop("priority", None)
        else:
            row["priority"] = value
        row["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        if value is None:
            return f"Priority cleared: {row['what'][:80]}"
        return f"P{value}: {row['what'][:80]}"

    if action == "combine":
        m = re.match(r"^(.*?)\s+(?:into|with|\+)\s+(.*)$", body or "", re.I)
        if not m:
            return "Use: combine: <duplicate> into <keep>   e.g. combine: #9 into #7"
        duplicate, err = _pick(rows, m.group(1))
        if err:
            return err
        keep, err = _pick(rows, m.group(2))
        if err:
            return err
        if duplicate["id"] == keep["id"]:
            return "Those are the same item."
        duplicate["status"] = "dropped"
        duplicate["closed_at"] = now.isoformat()
        duplicate["closed_how"] = "merged"
        duplicate["merged_into"] = keep["id"]
        keep.setdefault("merged_from", []).append({
            "id": duplicate["id"], "what": duplicate.get("what"),
            "source_link": duplicate.get("source_link")})
        keep["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return (f"Combined: {duplicate['what'][:70]} → {keep['what'][:70]}\n"
                f"Kept #{_open_sorted(rows).index(keep) + 1}: {keep['what'][:80]}")

    if action == "uncombine":
        keep, err = _pick(rows, body)
        if err:
            return err
        merged = keep.pop("merged_from", [])
        if not merged:
            return "Nothing is merged into that item."
        by_id = {r["id"]: r for r in rows}
        restored = []
        for entry in merged:
            row = by_id.get(entry.get("id"))
            if not row:
                continue
            row["status"] = "open"
            row["last_activity"] = now.isoformat()
            for key in ("closed_at", "closed_how", "merged_into"):
                row.pop(key, None)
            restored.append(row["what"][:70])
        save(ledger_path, rows)
        return (f"Restored {len(restored)} item(s):\n"
                + "\n".join(f"• {w}" for w in restored))

    if action == "status":
        m = re.match(
            r"^(.*?)\s+(?:to\s+)?(in[ -]?progress|inprogress|doing|active|"
            r"blocked|block|stuck|open|todo|pending)\s*$", body, re.I)
        if not m:
            return "Use: status: <item> in progress | blocked | open"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        status = STATUS_ALIASES[m.group(2).lower().replace("  ", " ")]
        row["status"] = status
        row["status_updated_at"] = now.isoformat()
        row["last_activity"] = now.isoformat()
        if status == "open":
            row.pop("stalled_since", None)
            row.pop("stalled_reason", None)
        save(ledger_path, rows)
        return f"Status: {row['what'][:80]} — {status}"

    if action == "done":
        best, err = _pick(rows, body)
        if err:
            return err
        best["status"] = "done"
        best["closed_at"] = now.isoformat()
        best["closed_how"] = "manual"
        save(ledger_path, rows)
        return f"Closed: {best['what'][:80]}"

    if action == "help":
        return HELP

    if action == "remind":
        fields, clean = parse_remind(body, now)
        if fields is None:
            return "Use: remind: send the deck tomorrow at 3pm"
        row = {
            "id": commitment_id("reminder", clean.lower(), clean),
            "direction": "owed_by_me", "what": clean[:200], "source": "manual",
            "native_id": clean.lower(), "kind": "reminder", "source_link": "",
            "evidence": body[:200], "due": fields["due"], "due_confidence": 0.9,
            "cycle": None, "status": "open", "stalled_since": None,
            "ack_policy": "bot_may_ack", "closure": "open", "client": None,
            "created_at": now.isoformat(), "last_activity": now.isoformat(),
            "remind_at": fields["remind_at"], "reminded": False,
            "closed_at": None, "closed_how": None,
        }
        save(ledger_path, merge(rows, [row]))
        return f"Reminder set for {fields['remind_at'][:16].replace('T', ' ')}: {clean[:80]}"

    if action == "not":
        from . import learning
        from .calendar import ignore_title

        # `not:` also dismisses a meeting reminder. No ledger row exists for a
        # meeting, so match the title recorded in today's reminder state.
        state_path = Path("meeting_reminders.json")
        if state_path.exists():
            meetings = json.loads(state_path.read_text())
            target = (body or "").strip().lower()
            for rec in (meetings.get("meetings") or {}).values():
                title = (rec.get("title") or "").strip()
                if target and (target in title.lower() or title.lower() in target):
                    ignore_title(title)
                    rec["status"] = "ignored"
                    state_path.write_text(json.dumps(meetings))
                    return f"Ignored meeting: {title[:80]}"

        row, err = _pick(rows, body)
        if row:
            row["status"] = "dropped"
            row["closed_at"] = now.isoformat()
            row["closed_how"] = "not_commitment"
            save(ledger_path, rows)
            learning.add(row.get("what", ""), reason=body,
                         source=row.get("source", ""))
            return f"Removed as not a commitment: {row['what'][:80]}"
        if err and err.startswith("Which one?"):
            return err
        learning.add(body, reason="manual correction", source="manual")
        return "Recorded. I will ignore similar messages from now on."

    if action == "list":
        open_rows = _open_sorted(rows)
        if not open_rows:
            return "Nothing open."
        return "Open:\n" + "\n".join(
            f"{i}. [{r['id'][:6]}]"
            + (f" [P{r['priority']}]" if isinstance(r.get("priority"), int) else "")
            + f" {r['what'][:90]}"
            + (f" — {r['due']}" if r.get("due") else "")
            + (f" — {r['status']}" if r.get("status") in {"in progress", "blocked"}
               else "")
            + _ref(r)
            for i, r in enumerate(open_rows[:25], 1))

    if action == "find":
        hits = [r for r in rows
                if body.lower() in f"{r.get('what','')} {r.get('client','')}".lower()]
        if not hits:
            return f"No matches for “{body}”."
        return "\n".join(
            f"• {r['what'][:100]}" + (f" — {r['due']}" if r.get("due") else "")
            for r in hits[:8])

    if action in {"due", "snooze"}:
        m = re.match(
            r"^(.*?)\s+(?:by\s+)?(\d+\s*[dw]|today|tomorrow|monday|tuesday|wednesday|"
            r"thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})\s*$", body, re.I)
        if not m:
            return "Use: due: <item> by Friday   or   snooze: <item> 3d"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        d = _shift(m.group(2), now)
        if not d:
            return "Could not read that date."
        row["due"] = d
        row["status"] = "open"
        row["closure"] = "open"
        row["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return f"Due {d}: {row['what'][:80]}"

    if action == "edit":
        from .extract import parse_due

        m = re.match(r"^(.*)\s+to\s+(.+)$", body or "", re.I)
        if not m:
            return "Use: edit: <item> to <new name> [by <when>]"
        target, new = m.group(1).strip(), m.group(2).strip()
        row, err = _pick(rows, target)
        if err:
            return err
        due = None
        b = re.match(r"^(.*?)\s+by\s+(.+)$", new, re.I)
        if b:
            d = parse_due(b.group(2), now)[0]
            if d:
                due = d
                new = b.group(1).strip()
        if not new:
            return "Use: edit: <item> to <new name> [by <when>]"
        row["what"] = new[:200]
        row["last_activity"] = now.isoformat()
        if due:
            row["due"] = due
            row["status"] = "open"
            row["closure"] = "open"
        save(ledger_path, rows)
        return f"Edited: {new[:80]}" + (f" · due {due}" if due else "")

    if action == "drop":
        row, err = _pick(rows, body)
        if err:
            return err
        row["status"] = "dropped"
        row["closed_at"] = now.isoformat()
        row["closed_how"] = "manual"
        save(ledger_path, rows)
        return f"Dropped: {row['what'][:80]}"

    if action == "waiting":
        m = re.match(r"^(.*?)\s+on\s+(.+)$", body, re.I)
        target, person = (m.group(1), m.group(2)) if m else (body, "")
        row, err = _pick(rows, target)
        if err:
            return err
        row["direction"] = "owed_to_me"
        if person:
            row["asker"] = person.strip()[:40]
        save(ledger_path, rows)
        return f"Waiting on {person or 'them'}: {row['what'][:70]}"

    return ("Commands: add:, note:, done:, drop:, due: <item> by <when>, "
            "snooze: <item> 3d, waiting: <item> on <person>, find: <text>, list")


def main(env: dict, ledger_path: str = "ledger.json") -> int:
    from datetime import datetime, timedelta, timezone

    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web import WebClient

    from .clients import load_clients
    from .notify import send_dm

    MYT = timezone(timedelta(hours=8))
    clients = load_clients("clients.json")
    owner = env.get("SLACK_OWNER_ID", "")
    web = WebClient(token=env["SLACK_BOT_TOKEN"])
    client = SocketModeClient(app_token=env["SLACK_APP_TOKEN"], web_client=web)
    try:
        users = load_users(env["SLACK_BOT_TOKEN"])
    except Exception as ex:  # noqa: BLE001 - names degrade to mentions only
        print(f"user list unavailable: {type(ex).__name__}", flush=True)
        users = {}

    def post_reply(channel: str, text: str, notify: bool = True,
                   private: bool = False) -> None:
        """Post in place; DM a copy when the command came from a channel.
        `private` sends only to Ridha's DM, so a channel is not pinged."""
        if private and not channel.startswith("D"):
            try:
                send_dm(env, text)
            except Exception as ex:  # noqa: BLE001
                print(f"  dm reply failed: {type(ex).__name__}", flush=True)
            return
        web.chat_postMessage(channel=channel, text=text)
        if not notify or channel.startswith("D"):
            return
        try:
            send_dm(env, text)
        except Exception as ex:  # noqa: BLE001 - the channel reply already went out
            print(f"  dm mirror failed: {type(ex).__name__}", flush=True)

    seen: set[tuple[str, str]] = set()
    STATE = "bot_state.json"

    def _state() -> dict:
        import json
        from pathlib import Path as P

        f = P(STATE)
        return json.loads(f.read_text()) if f.exists() else {}

    def _mark(ts: str) -> None:
        import json
        from pathlib import Path as P

        s = _state()
        try:
            if not s.get("last_ts") or float(ts) > float(s["last_ts"]):
                s["last_ts"] = ts
                P(STATE).write_text(json.dumps(s))
        except ValueError:
            pass

    def process(channel: str, user: str, text: str, ts: str, late: bool = False) -> None:
        if (channel, ts) in seen or channel in IGNORE_CHANNEL_IDS:
            return
        seen.add((channel, ts))

        action, body = parse_command(text)
        allow = {u.strip() for u in env.get("KB_ALLOWLIST", "").split(",") if u.strip()}
        if user == owner:
            action = owner_action(action, body)
        elif action == "unknown" and QUERY.search(body) and user in allow:
            action = "ask"  # allowlisted people can ask in plain language too

        # Replaying old commands after a wake invents side effects. Only questions.
        if late and action != "ask":
            return

        if action == "ask":
            allow = {u.strip() for u in env.get("KB_ALLOWLIST", "").split(",") if u.strip()}
            if user != owner and user not in allow:
                web.chat_postMessage(
                    channel=channel,
                    text="You are not on the list for that. Ask Ridha to add you.")
                return
            try:
                from .kb import answer as kb_answer
                from .kb import load as kb_load

                index = kb_load()
                if not index:
                    reply = "Knowledge base is empty. Ridha needs to run the index build."
                else:
                    body_text, hits = kb_answer(body, index)
                    sources = "\n".join(
                        f"[{i}] {h['source']} · {h['link']}"
                        for i, h in enumerate(hits, 1) if h.get("link"))
                    reply = f"{body_text}\n\n{sources}"
            except Exception as ex:  # noqa: BLE001
                reply = f"Could not answer: {type(ex).__name__}"
            if late:
                reply = "_(answered late, I was offline)_\n" + reply
            post_reply(channel, reply[:3900], notify=user == owner,
                       private=user == owner)
            _mark(ts)
            return

        print(f"[{datetime.now(MYT):%H:%M:%S}] {user} in {channel}: {text[:120]!r} -> {action}",
              flush=True)

        target, rest = (split_target(body, users, user)
                        if action in {"add", "remind"} else (None, body))
        if action == "remind" and target is None:
            missing = unresolved_recipient(body, users)
            if missing:
                post_reply(channel, f"I can't find {missing} in this Slack workspace. "
                                    "Reminders can only DM Pantas members.",
                           notify=False, private=user == owner)
                _mark(ts)
                return
        if should_schedule_reminder(action, user, owner, target):
            fields, _ = parse_remind(rest, datetime.now(MYT))
            if fields is None:
                post_reply(channel, "Use: remind <name> to <what> at 2pm "
                                    "(or add: <what> at 2pm)",
                           notify=False, private=user == owner)
                _mark(ts)
                return
            recipient = target or user
            who = "you" if recipient == user else f"<@{recipient}>"
            if fields.get("immediate"):
                try:
                    from .notify import send_dm

                    send_dm(env, recipient, f"*Reminder*\n{fields['what'][:300]}")
                except Exception as ex:  # noqa: BLE001 - report, never retry blindly
                    print(f"  immediate remind failed: {type(ex).__name__}: {ex}", flush=True)
                    post_reply(channel, f"Could not send that: {type(ex).__name__}",
                               notify=False, private=user == owner)
                    _mark(ts)
                    return
                reply = f"Reminder sent to {who}: {fields['what'][:80]}"
                post_reply(channel, reply, notify=user == owner, private=user == owner)
                _mark(ts)
                return
            at = datetime.fromisoformat(fields["remind_at"])
            if at <= datetime.now(MYT):
                post_reply(channel, "That time is in the past.",
                           notify=False, private=user == owner)
                _mark(ts)
                return
            try:
                from .notify import schedule_dm

                schedule_dm(env, recipient,
                            f"*Reminder*\n{fields['what'][:300]}",
                            int(at.timestamp()))
            except Exception as ex:  # noqa: BLE001 - report, never retry blindly
                print(f"  schedule failed: {type(ex).__name__}: {ex}", flush=True)
                post_reply(channel, f"Could not schedule that: {type(ex).__name__}",
                           notify=False, private=user == owner)
                _mark(ts)
                return
            reply = f"Reminder set for {who} — {at:%a %d %b %H:%M}: {fields['what'][:80]}"
            post_reply(channel, reply, notify=user == owner, private=user == owner)
            _mark(ts)
            return

        if user == owner and channel.startswith("D"):
            try:
                from .watcher import record_meeting_reply

                meeting_reply = record_meeting_reply(body, datetime.now(MYT))
            except Exception as ex:  # noqa: BLE001 - a bad state file must not block the bot
                print(f"  meeting reply failed: {type(ex).__name__}: {ex}", flush=True)
                meeting_reply = None
            if meeting_reply:
                post_reply(channel, meeting_reply)
                _mark(ts)
                return

        if user != owner:
            if not late:
                try:
                    web.reactions_add(channel=channel, timestamp=ts, name="white_check_mark")
                except Exception as ex:  # noqa: BLE001
                    print(f"  react failed: {type(ex).__name__}: {ex}", flush=True)
            if action == "help":
                web.chat_postMessage(channel=channel, text=HELP)
                _mark(ts)
                return
            note = other_note(action, body, user)
            if note:
                apply_command("note", note, datetime.now(MYT), clients, ledger_path)
                try:
                    from .notify import send_dm

                    send_dm(env, f"*Note from <@{user}>*\n{(body or '').strip()[:500]}")
                except Exception as ex:  # noqa: BLE001
                    print(f"  note dm failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        try:
            reply = apply_command(action, body, datetime.now(MYT), clients, ledger_path)
        except Exception as ex:  # noqa: BLE001 - never leave the user without a reply
            print(f"[error] {type(ex).__name__}: {ex}", flush=True)
            reply = f"Something broke: {type(ex).__name__}"
        print(f"  reply: {reply[:120]!r}", flush=True)
        if action in EMOJI_ACKS and reply.startswith(
                ("Added.", "Noted.", "Converted to note:")):
            try:
                web.reactions_add(channel=channel, timestamp=ts,
                                  name=EMOJI_ACKS[action])
                _mark(ts)
                return
            except Exception as ex:  # noqa: BLE001 - fall back to the text reply
                print(f"  ack react failed: {type(ex).__name__}: {ex}", flush=True)
        if late:
            reply = "_(answered late, I was offline)_\n" + reply
        post_reply(channel, reply, private=True)
        _mark(ts)

    def handle(_socket_client, req):
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        event = (req.payload or {}).get("event") or {}
        if event.get("bot_id"):
            return
        if event.get("subtype"):
            ack = edit_ack_target(event, bot_user_id)
            if ack:
                try:
                    web.reactions_add(channel=ack[0], timestamp=ack[1],
                                      name="white_check_mark")
                except Exception as ex:  # noqa: BLE001 - reaction is best effort
                    print(f"  edit react failed: {type(ex).__name__}: {ex}", flush=True)
            return
        text = event.get("text") or ""
        user = event.get("user") or ""
        channel = event.get("channel") or ""
        ts = event.get("ts") or ""
        if not channel or not user:
            return
        # message.channels/message.groups deliver every channel message. Only
        # act on ones that address the bot; DMs need no mention.
        if not is_bot_addressed(event, bot_user_id):
            return
        process(channel, user, text, ts)

    def catch_up(me_id: str) -> None:
        """Answer questions asked while the Mac was asleep. Best effort, late."""
        token = env.get("SLACK_USER_TOKEN")
        if not token or not me_id:
            return
        last = float(_state().get("last_ts") or 0)
        if not last:
            # First run: look back one hour, not zero. Otherwise a message sent just
            # before the restart is invisible forever.
            import time
            from pathlib import Path as P
            import json as _json

            last = time.time() - 3600
            P(STATE).write_text(_json.dumps({"last_ts": f"{last:.6f}"}))

        from .sources import _get_json

        url = ("https://slack.com/api/search.messages?"
               + urllib.parse.urlencode({"query": f"<@{me_id}>", "count": 50,
                                         "sort": "timestamp", "sort_dir": "desc"}))
        try:
            d = _get_json(url, {"Authorization": f"Bearer {token}"})
        except Exception as ex:  # noqa: BLE001
            print(f"catch-up search failed: {type(ex).__name__}", flush=True)
            return
        if not d.get("ok"):
            print(f"catch-up search error: {d.get('error')}", flush=True)
            return

        late = 0
        for m in reversed((d.get("messages") or {}).get("matches") or []):
            try:
                if float(m.get("ts", 0)) <= last:
                    continue
            except ValueError:
                continue
            ch = (m.get("channel") or {}).get("id")
            user = m.get("user")
            text = m.get("text") or ""
            if ch and user:
                process(ch, user, text, m["ts"], late=True)
                late += 1
        # DMs carry no literal mention, so search never returns them. Read the DM
        # channel directly.
        try:
            from .notify import _post as slack_post
            from .sources import _get_json as slack_get

            bot = env["SLACK_BOT_TOKEN"]
            opened = slack_post("conversations.open", bot, users=env["SLACK_OWNER_ID"])
            dm = (opened.get("channel") or {}).get("id")
            if dm:
                hist = slack_get(
                    "https://slack.com/api/conversations.history?"
                    + urllib.parse.urlencode({"channel": dm, "oldest": f"{last:.6f}", "limit": 50}),
                    {"Authorization": f"Bearer {bot}"})
                for m in reversed(hist.get("messages") or []):
                    if m.get("bot_id") or m.get("subtype") or not m.get("user"):
                        continue
                    process(dm, m["user"], m.get("text") or "", m["ts"], late=True)
                    late += 1
        except Exception as ex:  # noqa: BLE001
            print(f"catch-up DM read failed: {type(ex).__name__}", flush=True)

        if late:
            print(f"catch-up: processed {late} missed message(s)", flush=True)

    import logging

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client.socket_mode_request_listeners.append(handle)
    ident = web.auth_test()
    bot_user_id = ident.get("user_id") or ""
    client.connect()
    print(f"[{datetime.now(MYT):%H:%M:%S}] listening as @{ident.get('user')} "
          f"({ident.get('user_id')}) in {ident.get('team')}", flush=True)
    try:
        catch_up(ident.get("user_id"))
    except Exception as ex:  # noqa: BLE001 - catch-up must never stop the listener
        print(f"catch-up failed: {type(ex).__name__}: {ex}", flush=True)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    import sys

    from .sources import load_env

    sys.exit(main(load_env(".env")))
