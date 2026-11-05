from datetime import datetime, timezone

from mini_reid import members

NOW = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


def test_client_filter_keeps_only_member_clients():
    from mini_reid.clients import load_clients

    clients = load_clients("clients.json")
    eupe = {"author": "Someone <x@eupe.com.my>", "subject": "Deck"}
    internal = {"author": "Arman <arman@pantas.com>",
                "subject": "Gamuda review"}
    assert members.client_matches(eupe, clients, {"eupe"})
    assert not members.client_matches(eupe, clients, {"gamuda"})
    assert members.client_matches(internal, clients, {"gamuda"})
    maybank = {"author": "X <x@maybank.com>", "subject": "Deck"}
    assert members.client_matches(maybank, clients, {"ghb"})
    assert not members.client_matches(maybank, clients, {"gvc"})


def test_only_member_mentions_in_bot_channels(tmp_path, monkeypatch):
    profile = {"name": "Charanya", "ledger": str(tmp_path / "data/U1/ledger.json")}
    ts = NOW.timestamp()
    messages = [
        {"ts": str(ts - 10), "user": "U2", "text": "<@U1> send the deck tomorrow"},
        {"ts": str(ts - 9), "user": "U1", "text": "<@U1> note to self"},
        {"ts": str(ts - 8), "bot_id": "B1", "text": "<@U1> bot message"},
        {"ts": str(ts - 7), "user": "U3", "text": "no mention here"},
    ]
    monkeypatch.setattr(members, "_bot_channels", lambda env: [
        {"id": "C1", "name": "general", "is_member": True}])
    monkeypatch.setattr(members, "_history",
                        lambda env, channel, oldest: messages)
    monkeypatch.setattr(members, "slack_user_name", lambda token, user: "Kasib")

    items = members.slack_mentions({"SLACK_BOT_TOKEN": "x"}, "U1", profile, 1, NOW)
    assert len(items) == 1
    assert items[0]["author"] == "Kasib"
    assert items[0]["native_id"] == f"C1:{ts - 10}"
    assert "/archives/C1/" in items[0]["link"]

    # A second scan resumes after the newest message and does not re-report.
    monkeypatch.setattr(members, "_history", lambda env, channel, oldest: messages)
    assert members.slack_mentions(
        {"SLACK_BOT_TOKEN": "x"}, "U1", profile, 1, NOW) == []


def test_member_refresh_keeps_the_auto_capture_decision(tmp_path, monkeypatch):
    from mini_reid.ledger import load

    profile = {"name": "Charanya", "ledger": str(tmp_path / "ledger.json")}
    item = {"source": "jira", "native_id": "j1", "kind": "issue",
            "author": "Bo", "text": "Audit data units", "link": "https://x/j1",
            # Current time: refresh uses the real clock and apply_stalled would
            # otherwise stall the row once the hardcoded date ages out.
            "ts": datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(members, "collect", lambda *a, **k: ([item], []))
    monkeypatch.setattr("mini_reid.providers.extract_batch_safe",
                        lambda items, provider, now, clients: ([], []))
    monkeypatch.setattr(members, "send_dm_to",
                        lambda env, uid, text, blocks=None: None)
    monkeypatch.setattr("mini_reid.slack_lists.sync_user",
                        lambda env, uid, name, path: 0)

    out = members.refresh({}, "U1", profile)

    assert [r["capture"] for r in out] == ["auto"]
    assert [r["status"] for r in out] == ["open"]
    assert load(profile["ledger"])[0]["status"] == "open"
