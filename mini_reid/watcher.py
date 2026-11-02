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
from .notify import react, send_dm
from .sources import load_env

MYT = timezone(timedelta(hours=8))


def new_rows(items: list[dict], existing: list[dict], clients: dict, now: datetime) -> list[dict]:
    known = {r["id"] for r in existing}
    known_links = {r.get("source_link") for r in existing if r.get("source_link")}
    out = []
    for item in items:
        text = " ".join(filter(None, [item.get("subject"), item.get("text")]))
        channel = item.get("channel") if item.get("source") == "slack" else None
        client = (match_client(text, item.get("author", ""), clients, channel)
                  or match_client(text, item.get("to", ""), clients))
        for row in extract(item, client, now):
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


def fire_reminders(env: dict, ledger_path: str, now: datetime) -> int:
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
            send_dm(env, f"*Reminder*\n{(r.get('what') or '')[:300]}")
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
    from .notify import schedule_dm
    from .slack_bot import (load_users, parse_command, parse_remind, split_target,
                            unresolved_recipient)
    from .sources import _get_json, slack_me

    user_token = env.get("SLACK_USER_TOKEN")
    bot_token = env.get("SLACK_BOT_TOKEN")
    owner = env.get("SLACK_OWNER_ID")
    if not (user_token and bot_token and owner):
        return 0
    bot_id = slack_me(bot_token)
    users = load_users(bot_token)
    state = json.loads(Path(state_path).read_text()) if Path(state_path).exists() else {}
    last: dict[str, str] = state.get("channels") or {}
    try:
        since = datetime.fromisoformat(state.get("polled_at", ""))
    except ValueError:
        since = now - timedelta(minutes=5)
    ims = _get_json(
        "https://slack.com/api/conversations.list?"
        + urllib.parse.urlencode({"types": "im", "limit": 200}),
        {"Authorization": f"Bearer {user_token}"})
    handled = 0
    for ch in ims.get("channels") or []:
        cid = ch.get("id")
        if not cid or ch.get("user") == bot_id or ch.get("is_archived"):
            continue  # the bot's own DM already arrives as an event
        # Only DMs touched since the last poll. 73 histories every two minutes
        # would burn the user token's rate limit for no gain.
        if (ch.get("updated") or 0) < since.timestamp() * 1000:
            continue
        oldest = last.get(cid) or f"{since.timestamp():.6f}"
        d = _get_json(
            "https://slack.com/api/conversations.history?"
            + urllib.parse.urlencode(
                {"channel": cid, "oldest": oldest, "limit": 50}),
            {"Authorization": f"Bearer {user_token}"})
        for msg in sorted(d.get("messages") or [], key=lambda m: float(m.get("ts") or 0)):
            ts = msg.get("ts") or ""
            if float(ts or 0) <= float(last.get(cid) or 0):
                continue
            last[cid] = ts
            if msg.get("bot_id") or msg.get("subtype") or msg.get("user") != owner:
                continue
            text = msg.get("text") or ""
            if not re.search(rf"<@{bot_id}>|@mini-?reid\b", text, re.I):
                continue
            action, body = parse_command(text)
            if action != "remind":
                continue
            target, rest = split_target(body, users, owner)
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
                    send_dm(env, recipient, f"*Reminder*\n{fields['what'][:300]}")
                    note = f"Reminder sent to {who}: {fields['what'][:80]}"
                else:
                    at = datetime.fromisoformat(fields["remind_at"])
                    schedule_dm(env, recipient, f"*Reminder*\n{fields['what'][:300]}",
                                int(at.timestamp()))
                    note = f"Reminder set for {who} — {at:%a %d %b %H:%M}: {fields['what'][:80]}"
                send_dm(env, note)
                handled += 1
            except Exception as ex:  # noqa: BLE001 - report in the DM, keep polling
                print(f"  dm command failed: {type(ex).__name__}: {ex}", flush=True)
    Path(state_path).write_text(json.dumps(
        {"channels": last, "polled_at": now.isoformat()}))
    return handled


def _load_meetings(state_path: str, today: str) -> dict:
    state = json.loads(Path(state_path).read_text()) if Path(state_path).exists() else {}
    if state.get("date") != today or "meetings" not in state:
        return {"date": today, "meetings": {}}
    return state


def remind_meetings(env: dict, now: datetime, state_path: str = MEETINGS_STATE) -> int:
    """Schedule each of today's meetings 10 minutes before it starts, once.
    Slack keeps the schedule, so a sleeping Mac still gets the DM."""
    from .calendar import meetings_for_day, span
    from .notify import schedule_dm

    today = now.date().isoformat()
    state = _load_meetings(state_path, today)
    sent = 0
    for meeting in meetings_for_day(env, now):
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
            send_dm(env, text)
            status = "sent"
        else:
            schedule_dm(env, env["SLACK_OWNER_ID"], text, int(remind_at.timestamp()))
            status = "scheduled"
        state["meetings"][mid] = {"title": meeting["title"], "start": meeting["start"],
                                  "status": status}
        sent += 1
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
                or r.get("status") in {"done", "dropped"}
                or r.get("kind") in {"note", "reminder"}
                or r.get("closure") == "proposed"):
            continue
        # An empty due date is not "before today": undated work stays in No date.
        if (due and due < today) or r.get("status") == "stalled":
            out.append(r)
    return out


def nudge_overdue(env: dict, ledger_path: str, now: datetime) -> int:
    """Once a day after 09:00, restate what is overdue. Silence is how things rot."""
    from .render import _line

    state = Path("watcher_state.json")
    today = now.date().isoformat()
    seen = json.loads(state.read_text()) if state.exists() else {}
    if now.hour < 9 or seen.get("overdue_date") == today:
        return 0
    rows = overdue_today(load(ledger_path), now)
    if rows:
        # Same row renderer as the digest: client name, due, sender, time, link.
        lines = "\n".join(_line(r, slack=True, now=now) for r in rows[:10])
        send_dm(env, f"*Still overdue ({len(rows)})*\n{lines}")
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
        polled = poll_dm_commands(env, now)
        if polled:
            print(f"[{now:%H:%M:%S}] handled {polled} DM command(s)", flush=True)
    except Exception as ex:  # noqa: BLE001 - DM polling must not stop the watcher
        print(f"[{now:%H:%M:%S}] dm poll: {type(ex).__name__}: {ex}", flush=True)
    nudged = nudge_overdue(env, ledger_path, now)
    if nudged:
        print(f"[{now:%H:%M:%S}] overdue nudge: {nudged}", flush=True)

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
            rows, _ = extract_batch_safe(
                candidates[start:start + 5], provider, now, list(clients))
            rewritten.extend(rows)
        if rewritten:
            by_nid = {r["native_id"]: r for r in rewritten}
            merged = []
            for r in fresh:
                better = by_nid.pop(r["native_id"], None)
                if better:
                    better = dict(better, client=r.get("client"), asker=r.get("asker"))
                merged.append(better or r)
            fresh = merged + list(by_nid.values())

    if fresh:
        ledger = apply_stalled(merge(existing, fresh), now)
        save(ledger_path, ledger)
        for r in fresh:
            if r.get("source") != "slack":
                continue
            channel_id, _, ts = (r.get("native_id") or "").partition(":")
            try:
                react(env["SLACK_BOT_TOKEN"], channel_id, ts)
            except Exception as ex:  # noqa: BLE001 - reaction is best effort
                print(f"  react failed: {ex}", flush=True)
        send_dm(env, format_alert(fresh))
        print(f"[{now:%H:%M:%S}] alerted {len(fresh)} new", flush=True)
    print(f"[{now:%H:%M:%S}] checked {len(items)} items, {len(fresh)} new", flush=True)
    if errors:
        print(f"[{now:%H:%M:%S}] source errors: {errors}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
