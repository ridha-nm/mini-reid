from datetime import datetime, timedelta, timezone

from mini_reid import slack_lists
from mini_reid.ledger import load, save

NOW = datetime(2026, 11, 5, 19, 0, tzinfo=timezone(timedelta(hours=8)))


def test_ensure_list_maps_columns_and_status_choices(tmp_path, monkeypatch):
    calls = []

    def fake(method, token, body):
        calls.append(method)
        if method == "slackLists.create":
            return {"ok": True, "list_id": "F1", "list_metadata": {"schema": [
                {"key": "title", "id": "ColT"},
                {"key": "status", "id": "ColS",
                 "options": {"choices": [
                     {"value": "open", "label": "Open", "id": "OptO"}]}},
                {"key": "due", "id": "ColD"},
                {"key": "source", "id": "ColL"},
            ]}}
        return {"ok": True}

    monkeypatch.setattr(slack_lists, "_post", fake)
    cfg = slack_lists.ensure_list({"SLACK_BOT_TOKEN": "x"}, "U1", "Ridha",
                                  str(tmp_path / "state.json"))
    assert cfg["list_id"] == "F1"
    assert cfg["columns"] == {"title": "ColT", "status": "ColS",
                              "due": "ColD", "source": "ColL"}
    assert cfg["status_choices"] == {"open": "OptO"}
    assert calls == ["slackLists.create", "slackLists.access.set"]


def test_slack_list_edits_flow_back_to_the_ledger():
    rows = [{"id": "a", "what": "Old title", "status": "open",
             "due": "2026-11-06", "slack_item_id": "Rec1",
             "last_activity": "2026-11-05T09:00:00+08:00"}]
    item = {"id": "Rec1", "updated_timestamp": "1793866425", "fields": [
        {"key": "title", "text": "New title"},
        {"key": "status", "select": ["done"]},
        {"key": "due", "date": ["2026-11-07"]},
    ]}
    assert slack_lists.apply_list_changes(rows, [item], NOW) == 3
    assert rows[0]["action"] == "New title"
    assert rows[0]["status"] == "done"
    assert rows[0]["due"] == "2026-11-07"


def test_removing_a_row_from_the_list_drops_the_task():
    rows = [{"id": "a", "what": "Deleted in Slack", "status": "open",
             "slack_item_id": "Rec1"}]
    assert slack_lists.apply_list_changes(rows, [], NOW) == 1
    assert rows[0]["status"] == "dropped"
    assert "slack_item_id" not in rows[0]


def test_sync_deletes_dropped_and_inbox_rows(tmp_path, monkeypatch):
    state = str(tmp_path / "state.json")
    ledger = str(tmp_path / "ledger.json")
    save(ledger, [
        {"id": "a", "what": "Not a task", "status": "dropped",
         "slack_item_id": "RecDrop", "last_activity": "2026-11-05T10:00:00+08:00"},
        {"id": "b", "what": "Waiting", "status": "inbox",
         "slack_item_id": "RecInbox", "last_activity": "2026-11-05T10:00:00+08:00"},
    ])
    calls = []

    def fake(method, token, body):
        calls.append((method, body))
        if method == "slackLists.create":
            return {"ok": True, "list_id": "F1", "list_metadata": {"schema": [
                {"key": "title", "id": "ColT"}]}}
        if method == "slackLists.items.list":
            return {"ok": True, "items": [{"id": "RecDrop"},
                                          {"id": "RecInbox"}]}
        return {"ok": True}

    monkeypatch.setattr(slack_lists, "_post", fake)
    assert slack_lists.sync_user({"SLACK_BOT_TOKEN": "x"}, "U1", "Ridha",
                                 ledger, state) == 2
    deleted = [b["id"] for m, b in calls if m == "slackLists.items.delete"]
    assert deleted == ["RecDrop", "RecInbox"]
    assert all("slack_item_id" not in r for r in load(ledger))


def test_sync_creates_missing_rows_and_updates_changed_ones(tmp_path, monkeypatch):
    state = str(tmp_path / "state.json")
    ledger = str(tmp_path / "ledger.json")
    save(ledger, [{"id": "a", "what": "Send the deck", "status": "open",
                   "due": "2026-11-06", "last_activity": "2026-11-05T10:00:00+08:00"}])

    def fake(method, token, body):
        if method == "slackLists.create":
            return {"ok": True, "list_id": "F1", "list_metadata": {"schema": [
                {"key": "title", "id": "ColT"},
                {"key": "status", "id": "ColS",
                 "options": {"choices": [
                     {"value": "open", "label": "Open", "id": "OptO"}]}},
                {"key": "due", "id": "ColD"},
                {"key": "source", "id": "ColL"},
            ]}}
        if method == "slackLists.items.list":
            return {"ok": True, "items": [{"id": "Rec1"}]}
        if method == "slackLists.items.create":
            return {"ok": True, "item": {"id": "Rec1"}}
        return {"ok": True}

    monkeypatch.setattr(slack_lists, "_post", fake)
    assert slack_lists.sync_user({"SLACK_BOT_TOKEN": "x"}, "U1", "Ridha",
                                 ledger, state) == 1
    row = load(ledger)[0]
    assert row["slack_item_id"] == "Rec1"
    assert row["slack_synced_at"] == "2026-11-05T10:00:00+08:00"
    assert slack_lists.sync_user({"SLACK_BOT_TOKEN": "x"}, "U1", "Ridha",
                                 ledger, state) == 0


def test_list_url_uses_the_app_deep_link(tmp_path, monkeypatch):
    state = tmp_path / "lists.json"
    state.write_text('{"U1": {"list_id": "F1"}}')
    monkeypatch.setattr(slack_lists, "_TEAM_ID", "T1")
    assert slack_lists.list_url({"SLACK_BOT_TOKEN": "x"}, "U1",
                                str(state)) == "slack://list?team=T1&id=F1"
