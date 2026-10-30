"""Every minute: fetch, extract, merge, and DM only what is new."""
from __future__ import annotations

import json
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
    lines = [f"*{len(rows)} new*" if len(rows) > 1 else "*New*"]
    for r in rows:
        what = (r.get("what") or "")[:120]
        who = f" — from {r['asker']}" if r.get("asker") else ""
        client = f" — {r['client']}" if r.get("client") else ""
        due = f" — {r['due']}" if r.get("due") else ""
        link = r.get("source_link") or ""
        if "/archives/D" in link:
            link = ""
        tail = f" — <{link}|open>" if link else ""
        lines.append(f"• *{what}*{who}{client}{due}{tail}")
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


def overdue_today(rows: list[dict], now: datetime) -> list[dict]:
    today = now.date().isoformat()
    return [r for r in rows
            if r.get("direction", "owed_by_me") == "owed_by_me"
            and r.get("status") not in {"done", "dropped"}
            and r.get("kind") not in {"note", "reminder"}
            and ((r.get("due") or "") < today or r.get("status") == "stalled")]


def nudge_overdue(env: dict, ledger_path: str, now: datetime) -> int:
    """Once a day after 09:00, restate what is overdue. Silence is how things rot."""
    import json
    from pathlib import Path

    state = Path("watcher_state.json")
    today = now.date().isoformat()
    seen = json.loads(state.read_text()) if state.exists() else {}
    if now.hour < 9 or seen.get("overdue_date") == today:
        return 0
    rows = overdue_today(load(ledger_path), now)
    if rows:
        lines = "\n".join(
            f"• *{r.get('what','')[:110]}* — {r.get('client') or 'unassigned'} — "
            f"{r.get('due') or 'no date'}"
            for r in rows[:10])
        send_dm(env, f"*Still overdue ({len(rows)})*\n{lines}")
    state.write_text(json.dumps({"overdue_date": today}))
    return len(rows)


def main() -> int:
    env = load_env(".env")
    clients = load_clients("clients.json")
    now = datetime.now(MYT)
    ledger_path = "ledger.json"

    fired = fire_reminders(env, ledger_path, now)
    if fired:
        print(f"[{now:%H:%M:%S}] fired {fired} reminder(s)", flush=True)
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
            fresh = rewritten

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
