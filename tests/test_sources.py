from mini_reid.sources import parse_gmail_messages, parse_jira_issues, parse_slack_search


def test_parses_channel_mention_and_dm():
    payload = {"messages": {"matches": [
        {"channel": {"id": "C1", "name": "ioi-properties-working-group"},
         "username": "daniel", "ts": "1793341041.642809", "text": "<@U1> please confirm",
         "permalink": "https://x/1"},
        {"channel": {"id": "D1", "name": "U09CCJW1JL8"},
         "username": "kasib", "ts": "1793341042.000001", "text": "hows it going",
         "permalink": "https://x/2"},
    ]}}

    items = parse_slack_search(payload)

    assert len(items) == 2
    assert items[0]["channel"] == "ioi-properties-working-group"
    assert items[0]["is_dm"] is False
    assert items[1]["is_dm"] is True
    assert items[1]["native_id"] == "D1:1793341042.000001"
    assert items[0]["ts"].endswith("+08:00")


def test_slack_deduplicates_same_message():
    match = {"channel": {"id": "C1", "name": "gamuda"}, "username": "a",
             "ts": "1793341041.1", "text": "x", "permalink": "l"}
    assert len(parse_slack_search({"messages": {"matches": [match, match]}})) == 1


def test_dm_history_keeps_other_people_and_drops_me_and_bots():
    from mini_reid.sources import parse_slack_dm_history

    data = {"messages": [
        {"user": "UOTHER", "ts": "1793341041.1", "text": "can you send the deck"},
        {"user": "UME", "ts": "1793341042.1", "text": "sure"},
        {"bot_id": "B1", "ts": "1793341043.1", "text": "bot"},
    ]}
    items = parse_slack_dm_history("D1", data, "UME")
    assert len(items) == 1
    assert items[0]["native_id"] == "D1:1793341041.1"
    assert items[0]["is_dm"] is True


def _msg(mid, sender, subject, internal_ms, snippet="hello"):
    return {
        "id": mid,
        "internalDate": str(internal_ms),
        "snippet": snippet,
        "payload": {"headers": [
            {"name": "From", "value": sender},
            {"name": "Subject", "value": subject},
            {"name": "To", "value": "bd@pantas.com"},
        ]},
    }


def test_gmail_keeps_kind_and_created_at():
    msgs = [_msg("m1", "a@eupe.com.my", "Waste", 1793341041000)]
    inbox = parse_gmail_messages(msgs, "inbox")[0]
    draft = parse_gmail_messages(msgs, "draft")[0]
    assert inbox["kind"] == "inbox" and draft["kind"] == "draft"
    assert draft["created_at"].endswith("+08:00")
    assert inbox["author"] == "a@eupe.com.my"


def test_jira_maps_issue_key_due_and_status():
    data = {"issues": [{"id": "1001", "key": "BO-8834", "fields": {
        "summary": "Gamuda Biweekly Minutes", "duedate": "2026-11-06",
        "status": {"name": "To Do"}, "reporter": {"displayName": "Ridha"},
        "updated": "2026-10-30T10:00:00+08:00"}}]}
    item = parse_jira_issues(data, "https://pantas.atlassian.net")[0]
    assert item["link"].endswith("/browse/BO-8834")
    assert item["due"] == "2026-11-06"
    assert item["status"] == "To Do"


def test_jira_member_sees_the_other_person_as_asker():
    data = {"issues": [{"id": "1", "key": "BO-1", "fields": {
        "summary": "x", "status": {"name": "To Do"},
        "assignee": {"displayName": "Charanya Nair"},
        "reporter": {"displayName": "Kasib"},
        "project": {"key": "BO"}}}]}
    item = parse_jira_issues(data, "https://x", me="Charanya")[0]
    assert item["author"] == "Kasib"


def test_jira_auto_assigned_item_names_the_board():
    data = {"issues": [{"id": "1", "key": "BO-1", "fields": {
        "summary": "x", "status": {"name": "To Do"},
        "assignee": {"displayName": "Ridha Mohamed"},
        "reporter": {"displayName": "Ridha Mohamed"},
        "project": {"key": "BO"}}}]}
    item = parse_jira_issues(data, "https://x")[0]
    assert item["author"] == "BO board"


def test_dm_history_pages_through_the_whole_window(monkeypatch):
    from mini_reid import sources

    pages = [
        {"ok": True, "messages": [{"ts": "1"}, {"ts": "2"}],
         "response_metadata": {"next_cursor": "abc"}},
        {"ok": True, "messages": [{"ts": "3"}],
         "response_metadata": {"next_cursor": ""}},
    ]
    calls = []

    def fake_get(url, headers):
        calls.append(url)
        return pages.pop(0)

    monkeypatch.setattr(sources, "_get_json", fake_get)
    msgs = sources._dm_history("tok", "D1", 100.0)
    assert [m["ts"] for m in msgs] == ["1", "2", "3"]
    assert "cursor=abc" in calls[1]


def test_gmail_fetches_every_listed_message(monkeypatch):
    from mini_reid import sources

    monkeypatch.setattr(sources, "gmail_access", lambda *a, **k: "tok")
    monkeypatch.setattr(sources, "_gmail_list",
                        lambda access, query: ["m1", "m2"]
                        if "in:inbox" in query else [])

    def message(access, mid):
        return {"id": mid, "internalDate": "1793341041000",
                "payload": {"headers": [
                    {"name": "From", "value": "a@eupe.com.my"},
                    {"name": "Subject", "value": "deck"}]}}

    monkeypatch.setattr(sources, "_gmail_message", message)
    out = sources.fetch_gmail(1, {})
    assert {i["native_id"] for i in out} == {"m1", "m2"}


def test_slack_dm_fetch_reads_every_conversation(monkeypatch):
    from mini_reid import sources

    monkeypatch.setattr(sources, "_get_json", lambda *a, **k: {"channels": [
        {"id": "D1", "user": "U2"}, {"id": "D2", "user": "U3"}]})
    monkeypatch.setattr(sources, "_dm_history", lambda token, cid, oldest: [
        {"ts": "1793341041.0",
         "user": "U2" if cid == "D1" else "U3", "text": "hi"}])
    monkeypatch.setattr(sources, "slack_user_name",
                        lambda token, uid: {"U2": "Kasib", "U3": "Raj"}[uid])

    out = sources.fetch_slack_dms(1, "tok", "U1")
    assert {i["native_id"] for i in out} == {
        "D1:1793341041.0", "D2:1793341041.0"}
    assert {i["author"] for i in out} == {"Kasib", "Raj"}


def test_jira_keeps_the_issue_type():
    data = {"issues": [{"id": "1", "key": "BO-1", "fields": {
        "summary": "Eupe Corporation Berhad", "issuetype": {"name": "Epic"}}}]}
    assert parse_jira_issues(data, "https://x")[0]["issue_type"] == "Epic"


def test_triager_channel_is_ignored_at_the_source():
    match = {"channel": {"id": "C0B59LA0X5M", "name": "bd-triager-agent"},
             "username": "demo app", "ts": "1.1", "text": "<@U1> ticket",
             "permalink": "l"}
    assert parse_slack_search({"messages": {"matches": [match]}}) == []
