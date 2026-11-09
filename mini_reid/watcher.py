"""Every minute: fetch, extract, merge, and DM only what is new."""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cli import collect, load_clients, match_client, _domain
from .extract import extract
from .ledger import (apply_stalled, drop_duplicate_titles, load,
                     merge, save)
from .notify import send_dm, send_dm_to
from .sources import load_env

MYT = timezone(timedelta(hours=8))


def new_rows(items: list[dict], existing: list[dict], clients: dict, now: datetime,
             me: str | None = None) -> list[dict]:
    known = {r["id"] for r in existing}
    known_links = {r.get("source_link") for r in existing if r.get("source_link")}
    out = []
    for item in items:
        text = " ".join(filter(None, [item.get("subject"), item.get("text")]))
        channel = item.get("channel") if item.get("source") == "slack" else None
        client = (match_client(text, item.get("author", ""), clients, channel)
                  or match_client(text, item.get("to", ""), clients))
        for row in extract(item, client, now, me=me):
            if row["id"] in known:
                continue
            # The model may reword a row, changing its id. The source link is
            # the stable identity, so one message never alerts twice.
            link = row.get("source_link")
            if link and link in known_links:
                continue
            out.append(row)
            known.add(row["id"])
            if link:
                known_links.add(link)
    return out


def polish_rows(env: dict, items: list[dict], fresh: list[dict],
                now: datetime, clients) -> list[dict]:
    """Clean titles with the local model; the rule's stamp decides the status."""
    if not fresh:
        return fresh
    from .providers import OllamaProvider, extract_batch_safe

    by_nid = {i.get("native_id"): i for i in items}
    candidates = [by_nid[r["native_id"]] for r in fresh
                  if r.get("native_id") in by_nid]
    rewritten: list[dict] = []
    provider = OllamaProvider(model=env.get("OLLAMA_MODEL", "llama3.2:3b"))
    for start in range(0, len(candidates), 5):
        rows, _bad = extract_batch_safe(
            candidates[start:start + 5], provider, now, list(clients))
        rewritten.extend(rows)
    return triage_rows(fresh, rewritten)


def triage_rows(fresh: list[dict], rewritten: list[dict]) -> list[dict]:
    """The rule's capture stamp decides the status; the model only cleans the title.

    A row the rules stamped ``capture == "auto"`` is already open. Any other
    row waits in the inbox for a person. A row the model rewrote keeps its
    wording. A row the model omitted, rejected or failed on keeps the rule
    text. Nothing is dropped here: confirming or dismissing an inbox row is the
    person's click, not the model's call — and the model never adds a row.
    """
    model_by_nid = {r["native_id"]: r for r in rewritten if r.get("native_id")}
    out: list[dict] = []
    for row in fresh:
        nid = row.get("native_id")
        better = model_by_nid.pop(nid, None)
        status = "open" if row.get("capture") == "auto" else "inbox"
        if better:
            out.append(dict(better, status=status,
                            capture=row.get("capture", "inbox"),
                            capture_why=row.get("capture_why", ""),
                            from_user=row.get("from_user") or "",
                            client=row.get("client"),
                            asker=row.get("asker") or better.get("asker")))
        else:
            out.append(dict(row, status=status))
    return out


def pending_rows(rows: list[dict]) -> list[dict]:
    """Only uncertain captures get Add / Not a task buttons."""
    return [r for r in rows if (r.get("status") or "") == "inbox"]


def format_alert(rows: list[dict]) -> str:
    """One line per distinct item, even when one invite produced several emails."""
    from .render import _client_name, _source_quote, _when

    lines = [f"*{len(rows)} new*" if len(rows) > 1 else "*New*"]
    emitted: set[tuple[str, str]] = set()
    for r in rows:
        key = ((r.get("what") or "").lower().strip()[:80], r.get("client") or "")
        if key in emitted:
            continue
        emitted.add(key)
        what = (r.get("what") or "")[:120]
        who = f"from {r['asker']}" if r.get("asker") else ""
        if r.get("via"):
            who = f"{who} ({r['via']})" if who else r["via"]
        client = _client_name(r.get("client"))
        due = r.get("due") or "no date"
        link = r.get("source_link") or ""
        tail = f" — <{link}|open>" if link else ""
        parts = [f"*{what}*"]
        if who:
            parts.append(who)
        if client:
            parts.append(client)
        parts.append(due)
        when = _when(r)
        if when:
            parts.append(when)
        line = "• " + " — ".join(parts) + tail
        if r.get("source") == "slack":
            quote = _source_quote(r)
            if quote:
                line += f"\n   {quote}"
        lines.append(line)
    return "\n".join(lines)


def fire_reminders(env: dict, ledger_path: str, now: datetime,
                   user_id: str | None = None) -> int:
    from .quiet import dnd_active

    rows = load(ledger_path)
    fired = 0
    recipient = user_id or env.get("SLACK_OWNER_ID", "")
    if dnd_active(env, recipient):
        return 0
    for r in rows:
        if r.get("kind") != "reminder" or r.get("reminded"):
            continue
        at = r.get("remind_at")
        if not at:
            continue
        try:
            when = datetime.fromisoformat(at)
        except ValueError:
            continue
        if when <= now:
            text = f"*Reminder*\n{(r.get('what') or '')[:300]}"
            if user_id:
                send_dm_to(env, user_id, text)
            else:
                send_dm(env, text)
            r["reminded"] = True
            fired += 1
    if fired:
        save(ledger_path, rows)
    return fired


MEETINGS_STATE = "meeting_reminders.json"
DM_POLL_STATE = "dm_poll_state.json"


def poll_dm_commands(env: dict, now: datetime,
                     state_path: str = DM_POLL_STATE) -> int:
    """Slack never delivers events from a DM the bot is not in. Read Ridha's
    recent DMs with the user token and act on `remind` commands addressed to
    the bot. Confirmations go to the bot DM, never spoken as Ridha."""
    from .notify import dm_channel, log_reminder, schedule_dm, send_dm_to
    from .slack_bot import (_person_name, load_users, parse_command, parse_remind,
                            split_target, unresolved_recipient)
    from .sources import _get_json, slack_me

    user_token = env.get("SLACK_USER_TOKEN")
    bot_token = env.get("SLACK_BOT_TOKEN")
    owner = env.get("SLACK_OWNER_ID")
    if not (user_token and bot_token and owner):
        return 0
    bot_id = slack_me(bot_token)
    bot_dm = dm_channel(bot_token, owner)
    users = load_users(bot_token)
    log_path = str(Path(state_path).parent / "reminder_log.json")
    state = json.loads(Path(state_path).read_text()) if Path(state_path).exists() else {}
    try:
        last = float(state.get("last_ts") or 0)
    except (TypeError, ValueError):
        last = 0.0

    # Search finds messages in DMs the bot is not in, in two calls. Reading
    # 73 DM histories every cycle would burn the user token's rate limit.
    # `after:` is exclusive and midnight is fuzzy; a one-day backstop plus
    # last_ts dedupe misses nothing around midnight.
    since = (now - timedelta(days=1)).date().isoformat()
    matches: list[dict] = []
    for query in (f"<@{bot_id}> from:me after:{since}",
                  f"@mini-reid from:me after:{since}"):
        d = _get_json(
            "https://slack.com/api/search.messages?"
            + urllib.parse.urlencode({"query": query, "count": 100}),
            {"Authorization": f"Bearer {user_token}"})
        matches.extend((d.get("messages") or {}).get("matches") or [])

    handled = 0
    for msg in sorted(matches, key=lambda m: float(m.get("ts") or 0)):
        cid = (msg.get("channel") or {}).get("id") or ""
        ts = float(msg.get("ts") or 0)
        if ts <= last or not cid.startswith("D") or cid == bot_dm:
            continue
        last = ts
        text = msg.get("text") or ""
        if msg.get("user") != owner or not re.search(
                rf"<@{bot_id}>|@mini-?reid\b", text, re.I):
            continue
        action, body = parse_command(text)
        if action != "remind":
            continue
        target, rest = split_target(body, users, owner, bare_name=True)
        if target is None:
            missing = unresolved_recipient(body, users)
            if missing:
                send_dm(env, f"I can't find {missing} in this Slack workspace. "
                             "Reminders can only DM Pantas members.")
                continue
        fields, _ = parse_remind(rest, now)
        if fields is None:
            continue
        recipient = target or owner
        who = "you" if recipient == owner else f"<@{recipient}>"
        try:
            if fields.get("immediate"):
                send_dm_to(env, recipient, f"*Reminder*\n{fields['what'][:300]}")
                log_reminder(log_path, asked_by=owner,
                             asked_by_name=_person_name(owner, users),
                             to=recipient, to_name=_person_name(recipient, users),
                             what=fields["what"], status="sent",
                             post_at=now.isoformat(timespec="seconds"))
                note = f"Reminder sent to {who}: {fields['what'][:80]}"
            else:
                at = datetime.fromisoformat(fields["remind_at"])
                sid = schedule_dm(env, recipient,
                                  f"*Reminder*\n{fields['what'][:300]}",
                                  int(at.timestamp()))
                log_reminder(log_path, asked_by=owner,
                             asked_by_name=_person_name(owner, users),
                             to=recipient, to_name=_person_name(recipient, users),
                             what=fields["what"], post_at=at.isoformat(),
                             scheduled_id=sid)
                note = f"Reminder set for {who} — {at:%a %d %b %H:%M}: {fields['what'][:80]}"
            send_dm(env, note)
            handled += 1
        except Exception as ex:  # noqa: BLE001 - report in the DM, keep polling
            print(f"  dm command failed: {type(ex).__name__}: {ex}", flush=True)
    Path(state_path).write_text(json.dumps({"last_ts": f"{last:.6f}"}))
    return handled


def expire_banter(env: dict, now: datetime) -> bool:
    """Announce and clear banter.json when its time is up."""
    from .notify import _post

    path = Path("banter.json")
    if not path.exists():
        return False
    try:
        cfg = json.loads(path.read_text())
        until = datetime.fromisoformat(cfg["until"])
    except (OSError, ValueError, KeyError):
        path.unlink(missing_ok=True)
        return False
    if until.tzinfo is None:
        until = until.astimezone()
    if until > now:
        return False
    _post("chat.postMessage", env["SLACK_BOT_TOKEN"], channel=cfg.get("channel"),
          text="🍿 Banter off.")
    path.unlink(missing_ok=True)
    return True


def _load_meetings(state_path: str, today: str) -> dict:
    state = json.loads(Path(state_path).read_text()) if Path(state_path).exists() else {}
    if state.get("date") != today or "meetings" not in state:
        return {"date": today, "meetings": {}}
    return state


def remind_meetings(env: dict, now: datetime, state_path: str = MEETINGS_STATE,
                    user_id: str | None = None,
                    token_path: str | None = None,
                    owner_email: str | None = None,
                    ignores_path: str = "calendar_ignores.json",
                    client_path: str | None = None) -> int:
    """Schedule each of today's meetings 10 minutes before it starts, once.
    Slack keeps the schedule, so a sleeping Mac still gets the DM."""
    from .calendar import meetings_for_day, span
    from .notify import schedule_dm

    today = now.date().isoformat()
    state = _load_meetings(state_path, today)
    recipient = user_id or env["SLACK_OWNER_ID"]
    sent = 0
    for meeting in meetings_for_day(env, now, token_path=token_path,
                                    owner_email=owner_email,
                                    ignores_path=ignores_path,
                                    client_path=client_path):
        mid = meeting.get("id")
        rec = state["meetings"].get(mid) if mid else None
        if not mid or rec:
            continue
        start = datetime.fromisoformat(meeting["start"])
        if start <= now:
            continue
        text = (f"*Meeting in 10 minutes*\n{span(meeting)} · {meeting['title']}"
                + (f"\n<{meeting['link']}|join>" if meeting.get("link") else "")
                + "\n\nAre you attending? Reply `yes`, `no <reason>`, "
                  "`moved <note>`, `reschedule to <time> <note>`, or "
                  "`cancel <note>`.")
        remind_at = start - timedelta(minutes=10)
        if remind_at <= now:
            if user_id:
                send_dm_to(env, recipient, text)
            else:
                send_dm(env, text)
            status = "sent"
        else:
            schedule_dm(env, recipient, text, int(remind_at.timestamp()))
            status = "scheduled"
        state["meetings"][mid] = {"title": meeting["title"], "start": meeting["start"],
                                  "status": status}
        sent += 1

    from .calendar import ignored_titles
    from .notify import _post

    ignored = ignored_titles(ignores_path)
    if ignored and not user_id:
        d = _post("chat.scheduledMessages.list", env["SLACK_BOT_TOKEN"])
        for msg in d.get("scheduled_messages") or []:
            text = msg.get("text") or ""
            if not text.startswith("*Meeting in 10 minutes*"):
                continue
            line = text.split("\n")[1] if "\n" in text else ""
            title = line.split(" · ", 1)[-1].strip().lower()
            if title in ignored:
                _post("chat.deleteScheduledMessage", env["SLACK_BOT_TOKEN"],
                      channel=msg["channel_id"], scheduled_message_id=msg["id"])
    Path(state_path).write_text(json.dumps(state))
    return sent


def record_meeting_reply(text: str, now: datetime,
                         state_path: str = MEETINGS_STATE) -> str | None:
    """`yes`, `no <reason>` or `moved` in a DM answers the nearest reminder.

    `moved` covers "it might have moved", "rescheduled", "postponed" and
    "time changed". It records the note without guessing the new time.
    """
    today = now.date().isoformat()
    state = _load_meetings(state_path, today)
    raw = (text or "").strip()
    yes = re.match(r"^(yes|y|attending|will attend)\b", raw, re.I)
    no = re.match(r"^(no|n|not attending|can't|cannot|skip|decline)\b(.*)$", raw, re.I)
    moved = re.search(
        r"\b(?:moved|rescheduled|postponed|time (?:has |might have )?changed)\b(.*)$",
        raw, re.I)
    if not (yes or no or moved):
        return None
    candidates = []
    for mid, rec in state["meetings"].items():
        if rec.get("status") not in {"scheduled", "sent"}:
            continue
        start = datetime.fromisoformat(rec["start"])
        if now - timedelta(minutes=30) <= start <= now + timedelta(minutes=30):
            candidates.append((start, mid, rec))
    if not candidates:
        return None
    _, mid, rec = min(candidates, key=lambda c: abs(c[0] - now))
    note = ((no.group(2) if no else moved.group(1) if moved else "")
            .strip(" ,:-"))
    if moved and not no:
        rec["status"] = "moved"
        if note:
            rec["note"] = note[:200]
        Path(state_path).write_text(json.dumps(state))
        return f"Marked as moved: {rec['title']}" + (f" — {note}" if note else "")
    reason = note
    rec["status"] = "attending" if yes else "declined"
    if reason:
        rec["reason"] = reason[:200]
    Path(state_path).write_text(json.dumps(state))
    if yes:
        return f"Attending: {rec['title']}"
    return f"Not attending: {rec['title']}" + (f" — {reason}" if reason else "")


def overdue_today(rows: list[dict], now: datetime) -> list[dict]:
    today = now.date().isoformat()
    out = []
    for r in rows:
        due = r.get("due") or ""
        if (r.get("direction", "owed_by_me") != "owed_by_me"
                or r.get("status") in {"done", "dropped", "inbox"}
                or r.get("kind") in {"note", "reminder"}
                or r.get("closure") == "proposed"):
            continue
        # An empty due date is not "before today": undated work stays in No date.
        if (due and due < today) or r.get("status") == "stalled":
            out.append(r)
    return out


STALE_STATUSES = {"open", "in progress", "blocked", "stalled"}
STALE_NUDGE_HOUR = 18
STALE_MAX_NUDGES = 3


def stale_rows(rows: list[dict], now: datetime) -> list[dict]:
    """Live rows untouched today, nudged at most three times."""
    from .ledger import _dt

    out = []
    for row in rows:
        status = (row.get("status") or "open").lower()
        if status not in STALE_STATUSES or row.get("kind") == "note":
            continue
        if int(row.get("nudges") or 0) >= STALE_MAX_NUDGES:
            continue
        activity = _dt(row.get("last_activity") or row.get("created_at"))
        if activity is None or activity.date() >= now.date():
            continue
        out.append(row)
    return out


TRIAGER_CHANNEL = "C0B59LA0X5M"
TRIAGER_STATE = "triager_routed.json"
TRIAGER_APP = "demo app"


def route_triager(env: dict, now: datetime,
                  state_path: str = TRIAGER_STATE,
                  post=None, fetch=None) -> int:
    """Tag the account owners on new Demo App tickets in the triager channel.

    Only Demo App's "*Solution proposed*" cards route. SLA notices, the weekly
    rotation, closed tickets and human chatter are ignored."""
    from . import routing

    state_file = Path(state_path)
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    if not state.get("since_ts"):
        # First run: start from now so the backlog is not replied to at once.
        state["since_ts"] = f"{now.timestamp():.6f}"
        state_file.write_text(json.dumps(state))
        return 0
    blocked_at = state.get("blocked_at") or ""
    if blocked_at:
        try:
            if (now - datetime.fromisoformat(blocked_at)).total_seconds() < 3600:
                return 0
        except ValueError:
            pass
    if fetch is None:
        token = env.get("SLACK_USER_TOKEN")
        if not token:
            return 0

        def fetch(oldest: str) -> list[dict]:
            from .sources import _get_json

            out: list[dict] = []
            cursor = ""
            for _ in range(10):          # up to 1,000 messages per cycle
                params = {"channel": TRIAGER_CHANNEL, "oldest": oldest,
                          "limit": 100}
                if cursor:
                    params["cursor"] = cursor
                d = _get_json(
                    "https://slack.com/api/conversations.history?"
                    + urllib.parse.urlencode(params),
                    {"Authorization": f"Bearer {token}"})
                out.extend(d.get("messages") or [])
                cursor = (d.get("response_metadata") or {}).get(
                    "next_cursor") or ""
                if not cursor:
                    break
            return out
    try:
        messages = fetch(state["since_ts"])
    except Exception as ex:  # noqa: BLE001 - try again next cycle
        print(f"[{now:%H:%M:%S}] triager read: {type(ex).__name__}: {ex}",
              flush=True)
        return 0
    if post is None:
        from .notify import _post

        token = env["SLACK_BOT_TOKEN"]

        def post(channel: str, text: str, thread_ts: str) -> None:
            d = _post("chat.postMessage", token, channel=channel, text=text,
                      thread_ts=thread_ts)
            if not d.get("ok"):
                raise RuntimeError(d.get("error"))
    routing_data = routing.ensure_fresh()
    by_email = routing_data.get("emails") or {}
    by_domain = routing_data.get("domains") or {}
    by_company = routing_data.get("companies") or {}
    routed = state.setdefault("tickets", {})
    stats = state.setdefault("stats", {"total": 0, "fallback": 0,
                                       "unmapped": {}})
    closed: set[str] = set()
    for message in messages:
        if ((message.get("bot_profile") or {}).get("name") or "").lower() \
                != TRIAGER_APP:
            continue
        flat = routing.flatten_message(message)
        if "*Closed*" not in flat:
            continue
        key = routing.parse_card(flat)["key"]
        if key:
            closed.add(key)
    sent = 0
    for message in messages:
        ts = message.get("ts") or ""
        if ts:
            state["since_ts"] = max(state.get("since_ts") or "0", ts)
        text = message.get("text") or ""
        app = ((message.get("bot_profile") or {}).get("name") or "").lower()
        if app != TRIAGER_APP:
            continue
        flat = routing.flatten_message(message)
        # Initial card: legacy Acknowledged/Solution-proposed text, or the
        # newer Block Kit "New ticket:" card.
        initial = ("*Acknowledged*" in flat
                   or "*Solution proposed*" in flat
                   or text.strip().startswith("New ticket:"))
        if not initial:
            continue
        # Never tag follow-ups or closed cards.
        if ("*Closed*" in flat or ":speech_balloon:" in flat
                or " replied:" in flat):
            continue
        card = routing.parse_card(flat)
        if not card["key"] or card["key"] in routed:
            continue
        if card["key"] in closed:
            # Resolved inside this replay window: no tag needed.
            routed[card["key"]] = now.isoformat()
            continue
        route = by_email.get(card["email"])
        if not route and "@" in card["email"]:
            route = by_domain.get(card["email"].rpartition("@")[2])
        if not route:
            # No email on the card: match the company (then organisation) name.
            route = (routing.lookup_company(by_company, card.get("company") or "")
                     or routing.lookup_company(by_company,
                                               card.get("organisation") or ""))
        fallback = False
        if not route:
            # Unknown requester: Ridha triages it by hand.
            route = {"anchor": "Unmapped", "programme": "-",
                     "owners": ["ridha@pantas.com"]}
            fallback = True
            name = (card.get("company") or card.get("organisation")
                    or card["email"] or "unknown")[:60]
            stats["unmapped"][name] = stats["unmapped"].get(name, 0) + 1
        ids = routing.owner_ids(route["owners"]) or routing.owner_ids(
            routing.PROGRAMME_OWNERS.get(route["programme"], []))
        owners = " ".join(f"<@{uid}>" for uid in ids) or ", ".join(route["owners"])
        reply = (f"*{card['key']}* — {card['title']}\n"
                 f"Requester: {card['email']} · {route['anchor']} "
                 f"({route['programme']})\nOwner: {owners}")
        try:
            post(TRIAGER_CHANNEL, reply, message.get("thread_ts") or ts)
        except Exception as ex:  # noqa: BLE001 - retry once the bot can post
            state["blocked_at"] = now.isoformat()
            state_file.write_text(json.dumps(state))
            print(f"[{now:%H:%M:%S}] triager route: {type(ex).__name__}: {ex}",
                  flush=True)
            return sent
        routed[card["key"]] = now.isoformat()
        state["tickets"] = dict(list(routed.items())[-1000:])
        state_file.write_text(json.dumps(state))   # never tag it twice
        stats["total"] += 1
        stats["fallback"] += 1 if fallback else 0
        stats["unmapped"] = dict(sorted(stats["unmapped"].items(),
                                        key=lambda kv: -kv[1])[:20])
        sent += 1
    state["tickets"] = dict(list(routed.items())[-1000:])
    _alert_routing(env, state, now)
    state_file.write_text(json.dumps(state))
    return sent


def _alert_routing(env: dict, state: dict, now: datetime) -> None:
    """DM Ridha when routing relies on fallbacks or the exports are stale."""
    from . import routing

    stats = state.get("stats") or {}
    total = int(stats.get("total") or 0)
    fallback = int(stats.get("fallback") or 0)
    age = routing.exports_age_days()
    if not (routing.needs_alert(total, fallback) or age > routing.EXPORT_MAX_AGE_DAYS):
        return
    last = state.get("alerted_at") or ""
    try:
        if last and (now - datetime.fromisoformat(last)).total_seconds() < 86400:
            return
    except ValueError:
        pass
    names = ", ".join(list((stats.get("unmapped") or {}))[:8]) or "-"
    text = ("*Routing check*\n"
            f"Last {total} triager tickets: {fallback} had no account match"
            + (f" ({fallback / total:.0%})." if total else ".")
            + (f"\nUnmapped companies: {names}." if names else "")
            + (f"\nExports are {age:.0f} days old — send fresh ChildCompany, "
               "ChildCompanyUser and lite_user_collection_report exports."
               if age > routing.EXPORT_MAX_AGE_DAYS else "")
            + "\nReply with aliases (company → account) for any that should route.")
    try:
        from .notify import send_dm

        send_dm(env, text)
        state["alerted_at"] = now.isoformat()
    except Exception as ex:  # noqa: BLE001 - alerting must not stop routing
        print(f"[{now:%H:%M:%S}] routing alert: {type(ex).__name__}: {ex}",
              flush=True)


def nudge_stale(env: dict, ledger_path: str, now: datetime,
                state_path: str = "watcher_state.json",
                user_id: str | None = None) -> int:
    """Evening DM: ask what happened to tasks that saw no update today."""
    from .ledger import save
    from .triage_ui import stale_blocks

    from .quiet import dnd_active

    state = Path(state_path)
    today = now.date().isoformat()
    seen = json.loads(state.read_text()) if state.exists() else {}
    if now.hour < STALE_NUDGE_HOUR or seen.get("stale_date") == today:
        return 0
    if dnd_active(env, user_id or env.get("SLACK_OWNER_ID", "")):
        return 0
    rows = stale_rows(load(ledger_path), now)
    state.write_text(json.dumps({**seen, "stale_date": today}))
    if not rows:
        return 0
    shown = rows[:5]
    text = f"*No update today ({len(rows)})*\nStill open — what happened?"
    if user_id:
        send_dm_to(env, user_id, text, blocks=stale_blocks(shown))
    else:
        send_dm(env, text, blocks=stale_blocks(shown))
    for row in shown:
        row["nudges"] = int(row.get("nudges") or 0) + 1
        row["last_nudged"] = today
    save(ledger_path, _merge_nudges(ledger_path, shown))
    return len(rows)


def _merge_nudges(ledger_path: str, shown: list[dict]) -> list[dict]:
    """Persist the nudge counters without dropping rows added meanwhile."""
    rows = load(ledger_path)
    by_id = {r["id"]: r for r in shown}
    for row in rows:
        if row["id"] in by_id:
            row["nudges"] = by_id[row["id"]]["nudges"]
            row["last_nudged"] = by_id[row["id"]]["last_nudged"]
    return rows


def nudge_overdue(env: dict, ledger_path: str, now: datetime,
                  user_id: str | None = None,
                  state_path: str = "watcher_state.json") -> int:
    """Once a day after 09:00, restate what is overdue. Silence is how things rot."""
    from .render import _line

    from .quiet import dnd_active

    state = Path(state_path)
    today = now.date().isoformat()
    seen = json.loads(state.read_text()) if state.exists() else {}
    if now.hour < 9 or seen.get("overdue_date") == today:
        return 0
    if dnd_active(env, user_id or env.get("SLACK_OWNER_ID", "")):
        return 0
    rows = overdue_today(load(ledger_path), now)
    if rows:
        # Same row renderer as the digest: client name, due, sender, time, link.
        lines = "\n".join(_line(r, slack=True, now=now) for r in rows[:10])
        text = f"*Still overdue ({len(rows)})*\n{lines}"
        if user_id:
            send_dm_to(env, user_id, text)
        else:
            send_dm(env, text)
    state.write_text(json.dumps({"overdue_date": today}))
    return len(rows)


def _stamp_confirmation(ledger_path: str, ids: set[str], sent) -> None:
    """Remember which DM carries each row's buttons, so a click can edit it.

    Reloads first: a click may land between the alert send and this stamp, and
    only the confirmation fields are touched.
    """
    ts = sent.get("ts") if isinstance(sent, dict) else ""
    if not ts:
        return
    rows = load(ledger_path)
    changed = False
    for row in rows:
        if row.get("id") in ids:
            row["confirm_ts"] = ts
            row["confirm_channel"] = sent.get("channel") or ""
            changed = True
    if changed:
        save(ledger_path, rows)


DIGEST_RETRY_HOUR = (9, 30)
DIGEST_RETRY_SECONDS = 600


def digest_due(now: datetime, marker_path: str = "digest_delivered.json") -> bool:
    """A digest should exist today and, after 09:30, must have been delivered."""
    if (now.hour, now.minute) < DIGEST_RETRY_HOUR:
        return False
    path = Path(marker_path)
    if not path.exists():
        return True
    try:
        return json.loads(path.read_text()).get("date") != now.date().isoformat()
    except (json.JSONDecodeError, OSError):
        return True


def maybe_deliver_digest(now: datetime,
                         state_path: str = "watcher_state.json") -> int:
    """If the 09:15 digest never reached Slack, build and deliver it now.

    The launchd job fails silently when the Mac has no DNS at 09:15 (it did on
    2, 3 and 5 Nov). The watcher retries every 10 minutes until it succeeds.
    """
    if not digest_due(now):
        return 0
    state = Path(state_path)
    seen = json.loads(state.read_text()) if state.exists() else {}
    last = float(seen.get("digest_attempt") or 0)
    if last and now.timestamp() - last < DIGEST_RETRY_SECONDS:
        return 0
    seen["digest_attempt"] = now.timestamp()
    state.write_text(json.dumps(seen))

    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "mini_reid.cli", "--days", "1", "--deliver"],
            cwd=root, capture_output=True, text=True, timeout=600)
    except Exception as ex:  # noqa: BLE001 - retry on the next watcher cycle
        print(f"[{now:%H:%M:%S}] digest retry failed: {type(ex).__name__}: {ex}",
              flush=True)
        return 0
    if "delivered to Slack DM" in proc.stdout:
        print(f"[{now:%H:%M:%S}] digest delivered late", flush=True)
        return 1
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-2:]
    print(f"[{now:%H:%M:%S}] digest retry failed: {' | '.join(tail)}", flush=True)
    return 0


def main() -> int:
    import fcntl

    # Two overlapping runs (launchd + a manual one) both read old state and
    # schedule the same reminder twice. One watcher at a time.
    lock = open(".watcher.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another watcher is running", flush=True)
        return 0

    env = load_env(".env")
    clients = load_clients("clients.json")
    now = datetime.now(MYT)
    ledger_path = "ledger.json"

    fired = fire_reminders(env, ledger_path, now)
    if fired:
        print(f"[{now:%H:%M:%S}] fired {fired} reminder(s)", flush=True)
    try:
        reminded = remind_meetings(env, now)
        from .profiles import load as load_profiles

        attendees = remind_attendees(env, now, profiles=load_profiles())
        reminded += attendees
        if reminded:
            print(f"[{now:%H:%M:%S}] scheduled {reminded} meeting reminder(s)", flush=True)
    except Exception as ex:  # noqa: BLE001 - calendar must not stop the watcher
        print(f"[{now:%H:%M:%S}] meeting reminders: {type(ex).__name__}: {ex}", flush=True)
    try:
        if expire_banter(env, now):
            print(f"[{now:%H:%M:%S}] banter expired", flush=True)
    except Exception as ex:  # noqa: BLE001
        print(f"[{now:%H:%M:%S}] banter expiry: {type(ex).__name__}: {ex}", flush=True)
    try:
        polled = poll_dm_commands(env, now)
        if polled:
            print(f"[{now:%H:%M:%S}] handled {polled} DM command(s)", flush=True)
    except Exception as ex:  # noqa: BLE001 - DM polling must not stop the watcher
        print(f"[{now:%H:%M:%S}] dm poll: {type(ex).__name__}: {ex}", flush=True)
    nudged = nudge_overdue(env, ledger_path, now)
    if nudged:
        print(f"[{now:%H:%M:%S}] overdue nudge: {nudged}", flush=True)
    try:
        stale = nudge_stale(env, ledger_path, now)
        if stale:
            print(f"[{now:%H:%M:%S}] stale nudge: {stale}", flush=True)
    except Exception as ex:  # noqa: BLE001 - a nudge must not stop capture
        print(f"[{now:%H:%M:%S}] stale nudge: {type(ex).__name__}: {ex}", flush=True)
    try:
        maybe_deliver_digest(now)
    except Exception as ex:  # noqa: BLE001 - digest retry must not stop capture
        print(f"[{now:%H:%M:%S}] digest check: {type(ex).__name__}: {ex}",
              flush=True)

    items, errors = collect(days=1, offline=False)
    try:
        routed = route_triager(env, now)
        if routed:
            print(f"[{now:%H:%M:%S}] triager tickets routed: {routed}",
                  flush=True)
    except Exception as ex:  # noqa: BLE001 - routing must not stop capture
        print(f"[{now:%H:%M:%S}] triager route: {type(ex).__name__}: {ex}",
              flush=True)
    existing = load(ledger_path)
    fresh = new_rows(items, existing, clients, now)

    # Rules capture; the model only cleans titles. The stamp decides the status.
    fresh = polish_rows(env, items, fresh, now, clients)
    fresh = drop_duplicate_titles(existing, fresh)
    try:
        from .mutes import learn as learn_mutes

        newly_muted = learn_mutes(apply_stalled(merge(existing, fresh), now))
        if newly_muted:
            print(f"[{now:%H:%M:%S}] muted channel(s): "
                  f"{', '.join(newly_muted)}", flush=True)
    except Exception as ex:  # noqa: BLE001 - muting must not stop capture
        print(f"[{now:%H:%M:%S}] mute learn: {type(ex).__name__}: {ex}",
              flush=True)

    if fresh:
        ledger = apply_stalled(merge(existing, fresh), now)
        save(ledger_path, ledger)
        from .triage_ui import confirm_blocks

        pending = pending_rows(fresh)
        sent = send_dm(env, format_alert(fresh),
                       blocks=confirm_blocks(pending) if pending else None)
        _stamp_confirmation(ledger_path, {r["id"] for r in pending}, sent)
        print(f"[{now:%H:%M:%S}] asked to confirm {len(pending)} new", flush=True)
    try:
        from .epic_tracker import sync as sync_epics

        tracked = sync_epics(env, ledger_path)
        if tracked:
            print(f"[{now:%H:%M:%S}] epic tickets tracked: {tracked}",
                  flush=True)
    except Exception as ex:  # noqa: BLE001 - tracking must not stop capture
        print(f"[{now:%H:%M:%S}] epic tracker: {type(ex).__name__}: {ex}",
              flush=True)
    try:
        from .slack_lists import sync_user as sync_slack_list

        synced = sync_slack_list(env, env.get("SLACK_OWNER_ID", ""), "Ridha",
                                 ledger_path)
        if synced:
            print(f"[{now:%H:%M:%S}] slack list synced: {synced}", flush=True)
    except Exception as ex:  # noqa: BLE001 - list sync must not stop capture
        print(f"[{now:%H:%M:%S}] slack list: {type(ex).__name__}: {ex}",
              flush=True)
    try:
        from .members import cycle as member_cycle

        handled = member_cycle(env, now)
        if handled:
            print(f"[{now:%H:%M:%S}] members checked: {handled}", flush=True)
    except Exception as ex:  # noqa: BLE001 - member work must not stop the owner
        print(f"[{now:%H:%M:%S}] member cycle: {type(ex).__name__}: {ex}", flush=True)
    try:
        from .members import ack_done
        from .profiles import load as load_profiles

        acked = ack_done(env, load_profiles(),
                         env.get("SLACK_OWNER_ID", ""), ledger_path, now)
        if acked:
            print(f"[{now:%H:%M:%S}] done acks sent: {acked}", flush=True)
    except Exception as ex:  # noqa: BLE001 - ack must not stop capture
        print(f"[{now:%H:%M:%S}] done ack: {type(ex).__name__}: {ex}",
              flush=True)
    print(f"[{now:%H:%M:%S}] checked {len(items)} items, {len(fresh)} new", flush=True)
    if errors:
        print(f"[{now:%H:%M:%S}] source errors: {errors}", flush=True)
    return 0


def remind_attendees(env: dict, now: datetime,
                     created_path: str = "created_meetings.json",
                     profiles: dict | None = None) -> int:
    """DM every Slack attendee of a bot-created meeting 10 minutes before."""
    from .meetings import email_to_slack, load_created
    from .notify import schedule_dm

    data = load_created(created_path)
    by_email = email_to_slack()
    for uid, profile in (profiles or {}).items():
        email = (profile.get("email") or "").lower()
        if email:
            by_email[email] = uid
    sent = 0
    changed = False
    for eid, rec in data.items():
        if rec.get("attendee_reminded"):
            continue
        try:
            start = datetime.fromisoformat(rec.get("start") or "")
        except ValueError:
            continue
        rec["attendee_reminded"] = now.isoformat()
        changed = True
        if start <= now:
            continue
        end = datetime.fromisoformat(rec.get("end") or rec.get("start") or "")
        when = start - timedelta(minutes=10)
        if when <= now:
            when = now + timedelta(seconds=30)
        text = (f"*Meeting in 10 minutes*\n{start:%H:%M}–{end:%H:%M} · "
                f"{rec.get('title', '')}"
                + (f"\n<{rec['link']}|join>" if rec.get("link") else "")
                + "\n\nAre you attending?")
        blocks = [
            {"type": "section", "text": {"type": "mrkdwn", "text": text}},
            {"type": "actions", "elements": [
                {"type": "button", "action_id": "meet_rsvp_yes",
                 "value": eid,
                 "text": {"type": "plain_text", "text": "Attending"},
                 "style": "primary"},
                {"type": "button", "action_id": "meet_rsvp_no",
                 "value": eid,
                 "text": {"type": "plain_text", "text": "Can't attend"},
                 "style": "danger"},
            ]},
        ]
        for person in rec.get("attendees") or []:
            uid = by_email.get((person.get("email") or "").lower())
            if not uid or uid == rec.get("creator"):
                continue
            try:
                schedule_dm(env, uid, text, int(when.timestamp()), blocks=blocks)
                sent += 1
            except Exception as ex:  # noqa: BLE001 - one DM must not stop others
                print(f"  attendee reminder failed: "
                      f"{type(ex).__name__}: {ex}", flush=True)
    if changed:
        Path(created_path).write_text(json.dumps(data, indent=1,
                                                 ensure_ascii=False))
    return sent

if __name__ == "__main__":
    raise SystemExit(main())


