from mini_reid import slack_lists
from mini_reid.ledger import load, save


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
