"""Mirror a user's ledger into a native Slack List, incrementally."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .ledger import load, save

STATE = "slack_lists.json"
STATUSES = [
    ("open", "Open", "yellow"),
    ("in progress", "In progress", "blue"),
    ("blocked", "Blocked", "red"),
    ("done", "Done", "green"),
    ("dropped", "Not a task", "blue"),
]


def _post(method: str, token: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"https://slack.com/api/{method}", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def _rich(text: str) -> list[dict]:
    return [{"type": "rich_text", "elements": [{
        "type": "rich_text_section",
        "elements": [{"type": "text", "text": (text or "")[:200]}]}]}]


def _state(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_state(path: str, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=1))


def ensure_list(env: dict, user: str, name: str,
                state_path: str = STATE) -> dict:
    state = _state(state_path)
    if user in state:
        return state[user]
    token = env["SLACK_BOT_TOKEN"]
    schema = [
        {"key": "title", "name": "Task", "type": "text",
         "is_primary_column": True},
        {"key": "status", "name": "Status", "type": "select",
         "options": {"format": "single_select", "choices": [
             {"value": value, "label": label, "color": color}
             for value, label, color in STATUSES]}},
        {"key": "due", "name": "Due", "type": "date"},
        {"key": "source", "name": "Source", "type": "link"},
    ]
    data = _post("slackLists.create", token, {
        "name": f"Mini-Reid — {name}"[:100], "schema": schema})
    if not data.get("ok"):
        raise RuntimeError(f"slackLists.create: {data.get('error')}")
    columns = {c.get("key"): c for c in
               (data.get("list_metadata") or {}).get("schema") or []}
    choices = {}
    for choice in ((columns.get("status") or {}).get("options") or {}) \
            .get("choices") or []:
        key = choice.get("value") or choice.get("label")
        if key:
            choices[key] = choice.get("id") or key
    state[user] = {
        "list_id": data.get("list_id"),
        "columns": {k: v.get("id") for k, v in columns.items() if v.get("id")},
        "status_choices": choices,
    }
    _save_state(state_path, state)
    try:
        _post("slackLists.access.set", token, {
            "list_id": state[user]["list_id"],
            "access_level": "write", "user_ids": [user]})
    except Exception:  # noqa: BLE001 - sharing is best effort
        pass
    return state[user]


def _fields(env: dict, cfg: dict, row: dict) -> list[dict]:
    cols = cfg.get("columns") or {}
    out = []
    if cols.get("title"):
        out.append({"column_id": cols["title"],
                    "rich_text": _rich(row.get("action") or row.get("what"))})
    status = (row.get("status") or "open").lower()
    choice = (cfg.get("status_choices") or {}).get(status)
    if cols.get("status") and choice:
        out.append({"column_id": cols["status"], "select": [choice]})
    if cols.get("due") and row.get("due"):
        out.append({"column_id": cols["due"], "date": [row["due"]]})
    if cols.get("source") and row.get("source_link"):
        out.append({"column_id": cols["source"], "link": [{
            "original_url": row["source_link"], "display_as_url": False,
            "display_name": "open source"}]})
    return out


def sync_user(env: dict, user: str, name: str, ledger_path: str,
              state_path: str = STATE, limit: int = 50) -> int:
    """Create or update Slack List rows for the most recent ledger rows."""
    cfg = ensure_list(env, user, name, state_path)
    token = env["SLACK_BOT_TOKEN"]
    rows = load(ledger_path)
    tasks = [r for r in rows if r.get("kind") not in {"note", "reminder"}]
    tasks.sort(key=lambda r: r.get("last_activity") or "", reverse=True)
    changed = 0
    for row in tasks[:limit]:
        fields = _fields(env, cfg, row)
        if not fields:
            continue
        try:
            if row.get("slack_item_id"):
                if (row.get("slack_synced_at") or "") >= (row.get("last_activity") or ""):
                    continue
                data = _post("slackLists.items.update", token, {
                    "list_id": cfg["list_id"],
                    "cells": [dict(f, row_id=row["slack_item_id"]) for f in fields]})
            else:
                data = _post("slackLists.items.create", token, {
                    "list_id": cfg["list_id"], "initial_fields": fields})
                if data.get("ok"):
                    row["slack_item_id"] = (data.get("item") or {}).get("id")
            if not data.get("ok"):
                print(f"  slack list sync: {data.get('error')}", flush=True)
                continue
            row["slack_synced_at"] = row.get("last_activity") or ""
            changed += 1
        except Exception as ex:  # noqa: BLE001 - sync must not block capture
            print(f"  slack list sync failed: {type(ex).__name__}: {ex}",
                  flush=True)
    if changed:
        save(ledger_path, rows)
    return changed
