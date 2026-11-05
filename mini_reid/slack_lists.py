"""Mirror a user's ledger into a native Slack List, incrementally."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ledger import load, save

STATE = "slack_lists.json"
MYT = timezone(timedelta(hours=8))
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


_TEAM_ID = ""


def list_url(env: dict, user: str, state_path: str = STATE) -> str | None:
    """Deep link to the user's Slack List."""
    global _TEAM_ID
    cfg = _state(state_path).get(user) or {}
    list_id = cfg.get("list_id")
    if not list_id:
        return None
    if not _TEAM_ID:
        try:
            token = env["SLACK_BOT_TOKEN"]
            req = urllib.request.Request(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=15) as response:
                _TEAM_ID = json.load(response).get("team_id") or ""
        except Exception:  # noqa: BLE001 - link is optional
            return None
    team = env.get("SLACK_TEAM", "gopantas")
    return f"https://{team}.slack.com/lists/{_TEAM_ID}/{list_id}"


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


def _item_values(item: dict) -> dict:
    """Title, status and due as Slack currently shows them."""
    out = {}
    for field in item.get("fields") or []:
        key = field.get("key")
        if key == "title" and field.get("text"):
            out["title"] = field["text"].strip()[:200]
        elif key == "status" and field.get("select"):
            out["status"] = field["select"][0]
        elif key == "due" and field.get("date"):
            out["due"] = field["date"][0]
    return out


def apply_list_changes(rows: list[dict], items: list[dict],
                       now) -> int:
    """Apply Slack List edits back to the ledger. Deleted items become dropped."""
    by_item = {r["slack_item_id"]: r for r in rows
               if r.get("slack_item_id")}
    seen = set()
    changed = 0
    for item in items:
        row = by_item.get(item.get("id"))
        if not row:
            continue
        seen.add(item["id"])
        values = _item_values(item)
        if values.get("title") and values["title"] != (
                row.get("action") or row.get("what")):
            row["action"] = values["title"]
            changed += 1
        if values.get("status") and values["status"] != (
                row.get("status") or "open"):
            row["status"] = values["status"]
            if values["status"] in {"done", "dropped"}:
                row["closed_at"] = now.isoformat()
                row["closed_how"] = ("manual" if values["status"] == "done"
                                     else "not_commitment")
            changed += 1
        if values.get("due") and values["due"] != row.get("due"):
            row["due"] = values["due"]
            changed += 1
        try:
            row["last_activity"] = datetime.fromtimestamp(
                int(item.get("updated_timestamp") or 0), MYT).isoformat()
        except (TypeError, ValueError):
            row["last_activity"] = now.isoformat()
        row["slack_synced_at"] = row["last_activity"]
    for item_id, row in by_item.items():
        if item_id in seen or (row.get("status") or "open") == "dropped":
            continue
        # A row removed from the List is no longer a task.
        row["status"] = "dropped"
        row["closed_at"] = now.isoformat()
        row["closed_how"] = "not_commitment"
        row["last_activity"] = now.isoformat()
        row.pop("slack_item_id", None)
        changed += 1
    return changed


def _list_items(token: str, list_id: str) -> list[dict]:
    items: list[dict] = []
    cursor = ""
    for _ in range(10):
        body = {"list_id": list_id, "limit": 100}
        if cursor:
            body["cursor"] = cursor
        data = _post("slackLists.items.list", token, body)
        if not data.get("ok"):
            raise RuntimeError(f"slackLists.items.list: {data.get('error')}")
        items.extend(data.get("items") or [])
        cursor = (data.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return items


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
    pulled = apply_list_changes(rows, _list_items(token, cfg["list_id"]),
                                datetime.now(MYT))
    tasks = [r for r in rows if r.get("kind") not in {"note", "reminder"}]
    tasks.sort(key=lambda r: r.get("last_activity") or "", reverse=True)
    changed = pulled
    for row in tasks[:limit]:
        status = (row.get("status") or "open").lower()
        if status in {"dropped", "inbox"}:
            if row.get("slack_item_id"):
                try:
                    data = _post("slackLists.items.delete", token, {
                        "list_id": cfg["list_id"],
                        "id": row["slack_item_id"]})
                    if data.get("ok"):
                        row.pop("slack_item_id", None)
                        row["slack_synced_at"] = row.get("last_activity") or ""
                        changed += 1
                    else:
                        print(f"  slack list delete: {data.get('error')}",
                              flush=True)
                except Exception as ex:  # noqa: BLE001 - keep syncing others
                    print(f"  slack list delete failed: "
                          f"{type(ex).__name__}: {ex}", flush=True)
            continue
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
