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
