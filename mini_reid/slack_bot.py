"""Slack command parsing and the Socket Mode listener."""
from __future__ import annotations

import re
import threading
from datetime import timedelta

from .capture import parse_capture
from .ledger import commitment_id, load, merge, save

MENTION = re.compile(r"<@[A-Z0-9]+>")
COMMANDS = {"add", "note", "done", "drop", "due", "snooze", "waiting",
            "find", "list", "not"}

HELP = """*Mini-Reid commands*
• `add: confirm Eupe waste by Friday` — new task
• `note: Daniel wants the mapping redone` — remember it, no deadline
• `done: Eupe waste` — close it
• `due: Eupe waste by Monday` — change the date
• `snooze: Eupe waste 3d` — push it out (d days, w weeks)
• `waiting: Eupe waste on Daniel` — waiting on someone else
• `drop: Eupe waste` — remove it quietly
• `not: anything that is not part c` — wrong item, teach it to ignore this kind
• `find: eupe` — search the ledger
• `list` — ten nearest open items
• `help` — this

You can also just ask me something and I will say if I cannot do it."""


def parse_command(text: str) -> tuple[str, str]:
    """Return (action, body). action is one of COMMANDS, or ack|unknown|list."""
    body = MENTION.sub("", text or "").strip()
    if not body:
        return "unknown", ""
    if body.lower() in {"list", "ls", "today", "open"}:
        return "list", ""
    if body.lower() in {"help", "?", "commands"}:
        return "help", ""
    m = re.match(
        r"^(add|note|done|drop|due|snooze|waiting|find|not)\s*:\s*(.+)$", body, re.I)
    if m:
        return m.group(1).lower(), m.group(2).strip()
    if re.match(r"^(thanks|thank you|noted|ok|okay|got it)\b", body, re.I):
        return "ack", body
    return "unknown", body


def _find(rows: list[dict], target: str) -> dict | None:
    t = target.lower().strip()
    for r in rows:
        if r.get("status") in {"done", "dropped"}:
            continue
        if t and t in (r.get("what") or "").lower():
            return r
    return None


def _shift(text: str, now):
    """Parse '3d', '2w', or a date phrase into an ISO date."""
    from .extract import parse_due

    m = re.fullmatch(r"\s*(\d+)\s*([dw])\s*", text or "", re.I)
    if m:
        days = int(m.group(1)) * (7 if m.group(2).lower() == "w" else 1)
        return (now + timedelta(days=days)).date().isoformat()
    return parse_due(text, now)[0]


def apply_command(action: str, body: str, now, clients: dict, ledger_path: str) -> str:
    """Mutate the ledger and return the reply text. Pure enough to test."""
    rows = load(ledger_path)

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

    if action == "done":
        target = body.lower()
        best = None
        for r in rows:
            if r.get("status") in {"done", "dropped"}:
                continue
            if target in (r.get("what") or "").lower():
                best = r
                break
        if not best:
            return f"No open item matches “{body}”."
        best["status"] = "done"
        best["closed_at"] = now.isoformat()
        best["closed_how"] = "manual"
        save(ledger_path, rows)
        return f"Closed: {best['what'][:80]}"

    if action == "help":
        return HELP

    if action == "not":
        from . import learning

        row = _find(rows, body)
        if row:
            row["status"] = "dropped"
            row["closed_at"] = now.isoformat()
            row["closed_how"] = "not_commitment"
            save(ledger_path, rows)
            learning.add(row.get("what", ""), reason=body,
                         source=row.get("source", ""))
            return f"Removed as not a commitment: {row['what'][:80]}"
        learning.add(body, reason="manual correction", source="manual")
        return "Recorded. I will ignore similar messages from now on."

    if action == "list":
        open_rows = [r for r in rows if r.get("status") not in {"done", "dropped"}
                     and r.get("kind") != "note"]
        open_rows.sort(key=lambda r: r.get("due") or "9999")
        if not open_rows:
            return "Nothing open."
        return "Open:\n" + "\n".join(
            f"• {r['what'][:90]}" + (f" — {r['due']}" if r.get("due") else "")
            for r in open_rows[:10])

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
        row = _find(rows, m.group(1))
        if not row:
            return f"No open item matches “{m.group(1)}”."
        d = _shift(m.group(2), now)
        if not d:
            return "Could not read that date."
        row["due"] = d
        row["status"] = "open"
        row["closure"] = "open"
        row["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return f"Due {d}: {row['what'][:80]}"

    if action == "drop":
        row = _find(rows, body)
        if not row:
            return f"No open item matches “{body}”."
        row["status"] = "dropped"
        row["closed_at"] = now.isoformat()
        row["closed_how"] = "manual"
        save(ledger_path, rows)
        return f"Dropped: {row['what'][:80]}"

    if action == "waiting":
        m = re.match(r"^(.*?)\s+on\s+(.+)$", body, re.I)
        target, person = (m.group(1), m.group(2)) if m else (body, "")
        row = _find(rows, target)
        if not row:
            return f"No open item matches “{target}”."
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

    MYT = timezone(timedelta(hours=8))
    clients = load_clients("clients.json")
    owner = env.get("SLACK_OWNER_ID", "")
    web = WebClient(token=env["SLACK_BOT_TOKEN"])
    client = SocketModeClient(app_token=env["SLACK_APP_TOKEN"], web_client=web)

    seen: set[tuple[str, str]] = set()

    def handle(_socket_client, req):
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        event = (req.payload or {}).get("event") or {}
        if event.get("bot_id") or event.get("subtype"):
            return
        text = event.get("text") or ""
        user = event.get("user") or ""
        channel = event.get("channel") or ""
        ts = event.get("ts") or ""
        if not channel or not user:
            return

        # Slack retries an event until it is acknowledged. Same event, once.
        if (channel, ts) in seen:
            return
        seen.add((channel, ts))

        action, body = parse_command(text)
        print(f"[{datetime.now(MYT):%H:%M:%S}] {user} in {channel}: {text[:120]!r} -> {action}",
              flush=True)

        # Anyone other than Ridha gets a reaction, never a reply.
        if user != owner:
            try:
                web.reactions_add(channel=channel, timestamp=ts, name="white_check_mark")
            except Exception as ex:  # noqa: BLE001
                print(f"  react failed: {type(ex).__name__}: {ex}", flush=True)
            if action in COMMANDS:
                apply_command("note", f"from <@{user}>: {body}", datetime.now(MYT),
                              clients, ledger_path)
            return

        try:
            reply = apply_command(action, body, datetime.now(MYT), clients, ledger_path)
        except Exception as ex:  # noqa: BLE001 - never leave the user without a reply
            print(f"[error] {type(ex).__name__}: {ex}", flush=True)
            reply = f"Something broke: {type(ex).__name__}"
        print(f"  reply: {reply[:120]!r}", flush=True)
        web.chat_postMessage(channel=channel, text=reply)

    import logging

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client.socket_mode_request_listeners.append(handle)
    client.connect()
    ident = web.auth_test()
    print(f"[{datetime.now(MYT):%H:%M:%S}] listening as @{ident.get('user')} "
          f"({ident.get('user_id')}) in {ident.get('team')}", flush=True)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    import sys

    from .sources import load_env

    sys.exit(main(load_env(".env")))
