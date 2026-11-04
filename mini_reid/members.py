"""Capture, alert and digest for allowlisted members.

Slack coverage is limited to channels the bot has been invited to. Gmail and
Jira are used only when the member completed their own setup.
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .cli import load_clients
from .clients import match_client
from .ledger import apply_stalled, load, merge, save
from .notify import send_dm_to
from .profiles import load as load_profiles
from .render import render
from .sources import _get_json, fetch_gmail, fetch_jira, slack_user_name
from .watcher import (fire_reminders, format_alert, new_rows, nudge_overdue,
                      remind_meetings)

MYT = timezone(timedelta(hours=8))
IGNORE_CHANNELS = {"bd-triager-agent", "C0B59LA0X5M"}
SLACK_SCAN = "slack_scan.json"


def data_dir(user: str, profile: dict) -> Path:
    ledger = profile.get("ledger") or f"data/{user}/ledger.json"
    return Path(ledger).parent


def _member_path(user: str, profile: dict, name: str) -> Path:
    return data_dir(user, profile) / name


def _google_client(env: dict, profile: dict) -> str | None:
    """Refresh tokens are bound to the OAuth client that issued them."""
    return (profile.get("google_client")
            or env.get("SETUP_GOOGLE_CREDS")
            or env.get("GMAIL_CREDS"))


def client_matches(item: dict, clients: dict, allowed: set[str]) -> bool:
    """True when an email names one of the member's clients."""
    text = " ".join(filter(None, [item.get("subject"), item.get("text")]))
    found = match_client(text, item.get("author", ""), clients,
                         item.get("channel"))
    if not found:
        return False
    if found["slug"] in allowed:
        return True
    return (clients.get(found["slug"]) or {}).get("portfolio") in allowed


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1) + "\n")


def _bot_channels(env: dict) -> list[dict]:
    token = env["SLACK_BOT_TOKEN"]
    out: list[dict] = []
    cursor = ""
    while True:
        params = {"types": "public_channel,private_channel",
                  "exclude_archived": "true", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = _get_json("https://slack.com/api/conversations.list?"
                      + urllib.parse.urlencode(params),
                      {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            raise RuntimeError(f"conversations.list: {d.get('error')}")
        out.extend(c for c in d.get("channels") or [] if c.get("is_member"))
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return out


def _history(env: dict, channel: str, oldest: float) -> list[dict]:
    token = env["SLACK_BOT_TOKEN"]
    out: list[dict] = []
    cursor = ""
    while len(out) < 1000:
        params = {"channel": channel, "oldest": f"{oldest:.6f}", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = _get_json("https://slack.com/api/conversations.history?"
                      + urllib.parse.urlencode(params),
                      {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            raise RuntimeError(f"conversations.history: {d.get('error')}")
        out.extend(d.get("messages") or [])
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return out


def slack_mentions(env: dict, user: str, profile: dict, days: int,
                   now: datetime) -> list[dict]:
    """Mentions in channels the bot is in, since the last scan."""
    path = _member_path(user, profile, SLACK_SCAN)
    state = _read_json(path, {})
    oldest = (now - timedelta(days=days)).timestamp()
    team = env.get("SLACK_TEAM", "gopantas")
    out: list[dict] = []
    for ch in _bot_channels(env):
        cid = ch.get("id") or ""
        name = ch.get("name") or cid
        if not cid or name in IGNORE_CHANNELS or cid in IGNORE_CHANNELS:
            continue
        last = float(state.get(cid) or oldest)
        messages = _history(env, cid, last)
        newest = last
        for msg in messages:
            ts = float(msg.get("ts") or 0)
            if ts <= last:
                continue
            newest = max(newest, ts)
            if msg.get("bot_id") or msg.get("subtype"):
                continue
            author = msg.get("user") or ""
            text = msg.get("text") or ""
            if not author or author == user or f"<@{user}>" not in text:
                continue
            out.append({
                "source": "slack",
                "native_id": f"{cid}:{msg.get('ts')}",
                "kind": "mention",
                "channel": name,
                "channel_id": cid,
                "author": slack_user_name(env["SLACK_BOT_TOKEN"], author),
                "ts": datetime.fromtimestamp(ts, MYT).isoformat(),
                "text": text.strip(),
                "link": f"https://{team}.slack.com/archives/{cid}/"
                        f"p{str(msg.get('ts') or '').replace('.', '')}",
                "is_dm": False,
                "thread_ts": msg.get("thread_ts"),
                "direction": "owed_by_me",
            })
        state[cid] = newest
    _write_json(path, state)
    return out


def collect(env: dict, user: str, profile: dict, days: int,
            now: datetime) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    try:
        items += slack_mentions(env, user, profile, days, now)
    except Exception as ex:  # noqa: BLE001 - one dead source must not stop the rest
        errors.append(f"Slack: {ex}")

    token = _member_path(user, profile, "google_token.json")
    if token.exists():
        try:
            mail = fetch_gmail(days, env, token_path=str(token),
                               client_path=_google_client(env, profile))
            allowed = set(profile.get("clients") or [])
            if allowed:
                clients = load_clients("clients.json")
                mail = [i for i in mail if client_matches(i, clients, allowed)]
            items += mail
        except Exception as ex:  # noqa: BLE001
            errors.append(f"Gmail: {ex}")

    jira = _member_path(user, profile, "jira.json")
    try:
        if jira.exists():
            items += fetch_jira(days, env, creds=_read_json(jira, {}),
                                me=profile.get("name"))
        elif profile.get("jira_account_id") and env.get("JIRA_API_TOKEN"):
            # One workspace token, scoped to this member's assignee id.
            items += fetch_jira(days, env, me=profile.get("name"),
                                assignee=profile["jira_account_id"])
    except Exception as ex:  # noqa: BLE001
        errors.append(f"Jira: {ex}")
    return items, errors


def refresh(env: dict, user: str, profile: dict, days: int = 1) -> list[dict]:
    """Fetch, merge and alert new items for one member."""
    now = datetime.now(MYT)
    items, errors = collect(env, user, profile, days, now)
    ledger_path = profile.get("ledger") or f"data/{user}/ledger.json"
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    existing = load(ledger_path)
    clients = load_clients("clients.json")
    fresh = new_rows(items, existing, clients, now,
                     me=profile.get("email") or profile.get("name"))
    if fresh:
        fresh = [dict(row, status="inbox") for row in fresh]
        save(ledger_path, apply_stalled(merge(existing, fresh), now))
        from .triage_ui import confirm_blocks

        send_dm_to(env, user, format_alert(fresh), blocks=confirm_blocks(fresh))
    if errors:
        print(f"  member source errors: {errors}", flush=True)
    return fresh


def deliver_digest(env: dict, user: str, profile: dict,
                   now: datetime | None = None) -> str:
    now = now or datetime.now(MYT)
    refresh(env, user, profile)
    ledger_path = profile.get("ledger") or f"data/{user}/ledger.json"
    rows = load(ledger_path)
    meetings: list[dict] = []
    token = _member_path(user, profile, "google_token.json")
    if token.exists():
        try:
            from .calendar import meetings_for_day

            meetings = meetings_for_day(
                env, now, token_path=str(token),
                owner_email=profile.get("email"),
                ignores_path=str(_member_path(user, profile,
                                               "calendar_ignores.json")),
                client_path=_google_client(env, profile))
        except Exception as ex:  # noqa: BLE001 - calendar must not block the digest
            print(f"  member calendar failed: {type(ex).__name__}: {ex}", flush=True)
    text = render(rows, now, [], slack=True, brief=None, meetings=meetings)
    out = _member_path(user, profile, "digest.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    send_dm_to(env, user, text)
    return text


def cycle(env: dict, now: datetime) -> int:
    """Watcher work for every allowlisted member. Owner runs separately."""
    profiles = load_profiles()
    owner = env.get("SLACK_OWNER_ID", "")
    handled = 0
    for user, profile in profiles.items():
        if user == owner:
            continue
        try:
            d = data_dir(user, profile)
            d.mkdir(parents=True, exist_ok=True)
            fire_reminders(env, profile.get("ledger") or
                           f"data/{user}/ledger.json", now, user)
            token = d / "google_token.json"
            if token.exists():
                remind_meetings(
                    env, now, str(d / "meeting_reminders.json"), user,
                    token_path=str(token),
                    owner_email=profile.get("email"),
                    ignores_path=str(d / "calendar_ignores.json"),
                    client_path=_google_client(env, profile))
            nudge_overdue(env, profile.get("ledger") or
                          f"data/{user}/ledger.json", now, user,
                          str(d / "watcher_state.json"))
            refresh(env, user, profile)
            handled += 1
        except Exception as ex:  # noqa: BLE001 - one member must not stop the rest
            print(f"  member cycle failed ({user}): {type(ex).__name__}: {ex}",
                  flush=True)
    return handled


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .sources import load_env

    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", action="store_true",
                    help="deliver each member's morning digest")
    args = ap.parse_args(argv)
    env = load_env(".env")
    now = datetime.now(MYT)
    profiles = load_profiles()
    owner = env.get("SLACK_OWNER_ID", "")
    if args.digest:
        for user, profile in profiles.items():
            if user == owner:
                continue
            try:
                deliver_digest(env, user, profile, now)
            except Exception as ex:  # noqa: BLE001 - one member must not block the rest
                print(f"digest failed ({user}): {type(ex).__name__}: {ex}", flush=True)
    else:
        cycle(env, now)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
