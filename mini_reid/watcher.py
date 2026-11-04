"""Every minute: fetch, extract, merge, and DM only what is new."""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cli import collect, load_clients, match_client, _domain
from .extract import extract
from .ledger import apply_stalled, load, merge, save
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


def triage_rows(fresh: list[dict], rewritten: list[dict]) -> list[dict]:
    """Every rule-captured row waits for a person; the model only cleans the title.

    A row the model rewrote keeps its wording. A row the model omitted, rejected
    or failed on keeps the rule text. Nothing is dropped here: confirming or
    dismissing is the person's click, not the model's call.
    """
    model_by_nid = {r["native_id"]: r for r in rewritten if r.get("native_id")}
    seen = {r.get("native_id") for r in fresh}
    out: list[dict] = []
    for row in fresh:
        nid = row.get("native_id")
        better = model_by_nid.pop(nid, None)
        if better:
            out.append(dict(better, status="inbox",
                            client=row.get("client"),
                            asker=row.get("asker") or better.get("asker")))
        else:
            out.append(dict(row, status="inbox"))
    out.extend(dict(r, status="inbox") for nid, r in model_by_nid.items()
               if nid not in seen)
    return out


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
    rows = load(ledger_path)
    fired = 0
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
                + "\n\nAre you attending? Reply `yes` or `no <reason>`.")
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
    """`yes` or `no <reason>` in a DM answers the nearest meeting reminder."""
    today = now.date().isoformat()
    state = _load_meetings(state_path, today)
    raw = (text or "").strip()
    yes = re.match(r"^(yes|y|attending|will attend)\b", raw, re.I)
    no = re.match(r"^(no|n|not attending|can't|cannot|skip|decline)\b(.*)$", raw, re.I)
    if not (yes or no):
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
    reason = (no.group(2) if no else "").strip(" ,:-")
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


def nudge_stale(env: dict, ledger_path: str, now: datetime,
                state_path: str = "watcher_state.json") -> int:
    """Evening DM: ask what happened to tasks that saw no update today."""
    from .ledger import save
    from .triage_ui import stale_blocks

    state = Path(state_path)
    today = now.date().isoformat()
    seen = json.loads(state.read_text()) if state.exists() else {}
    if now.hour < STALE_NUDGE_HOUR or seen.get("stale_date") == today:
        return 0
    rows = stale_rows(load(ledger_path), now)
    state.write_text(json.dumps({**seen, "stale_date": today}))
    if not rows:
        return 0
    shown = rows[:5]
    text = f"*No update today ({len(rows)})*\nStill open — what happened?"
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

    state = Path(state_path)
    today = now.date().isoformat()
    seen = json.loads(state.read_text()) if state.exists() else {}
    if now.hour < 9 or seen.get("overdue_date") == today:
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

    items, errors = collect(days=1, offline=False)
    existing = load(ledger_path)
    fresh = new_rows(items, existing, clients, now)

    # Rewrite and filter through the local model before alerting. Rules alone
    # copy email openers and keep thread chatter that is not a commitment.
    if fresh:
        from .providers import OllamaProvider, extract_batch_safe

        by_nid = {i.get("native_id"): i for i in items}
        candidates = [by_nid[r["native_id"]] for r in fresh if r.get("native_id") in by_nid]
        rewritten: list[dict] = []
        provider = OllamaProvider(model=env.get("OLLAMA_MODEL", "llama3.2:3b"))
        for start in range(0, len(candidates), 5):
            rows, _bad = extract_batch_safe(
                candidates[start:start + 5], provider, now, list(clients))
            rewritten.extend(rows)
        fresh = triage_rows(fresh, rewritten)

    if fresh:
        ledger = apply_stalled(merge(existing, fresh), now)
        save(ledger_path, ledger)
        from .triage_ui import confirm_blocks

        send_dm(env, format_alert(fresh), blocks=confirm_blocks(fresh))
        print(f"[{now:%H:%M:%S}] asked to confirm {len(fresh)} new", flush=True)
    try:
        from .members import cycle as member_cycle

        handled = member_cycle(env, now)
        if handled:
            print(f"[{now:%H:%M:%S}] members checked: {handled}", flush=True)
    except Exception as ex:  # noqa: BLE001 - member work must not stop the owner
        print(f"[{now:%H:%M:%S}] member cycle: {type(ex).__name__}: {ex}", flush=True)
    print(f"[{now:%H:%M:%S}] checked {len(items)} items, {len(fresh)} new", flush=True)
    if errors:
        print(f"[{now:%H:%M:%S}] source errors: {errors}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
