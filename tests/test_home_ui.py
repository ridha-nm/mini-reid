from datetime import datetime, timedelta, timezone

from mini_reid.home_ui import (access_request_blocks, home_blocks,
                               public_home_blocks)

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 5, 19, 0, tzinfo=MYT)


def test_home_shows_counts_focus_and_buttons():
    rows = [{"id": "a1", "what": "Send the deck", "status": "open",
             "created_at": "2026-11-05T09:00:00+08:00"}]
    blocks = home_blocks(rows, NOW, "https://slack/lists/T1/F1")
    text = str(blocks)
    assert "1 open" in text
    assert "Send the deck" in text
    assert "Open Slack List" in text
    assert "Triage Inbox" in text
    assert "home_refresh" in text


def test_home_shows_only_three_focus_items():
    rows = [{"id": f"a{i}", "what": f"Task {i}", "status": "open",
             "due": "2026-11-01", "created_at": "2026-11-05T09:00:00+08:00"}
            for i in range(5)]
    text = str(home_blocks(rows, NOW))
    assert "Task 0" in text and "Task 2" in text
    assert "Task 3" not in text


def test_home_survives_an_empty_ledger():
    blocks = home_blocks([], NOW)
    assert "Nothing urgent." in str(blocks)
    assert "0 open" in str(blocks)


def test_access_request_carries_details_and_authorise_button():
    blocks = access_request_blocks("U2", {
        "name": "Charanya Nair", "email": "charanya@pantas.com",
        "jira": "charanya"})
    text = str(blocks)
    assert "Charanya Nair" in text
    assert "charanya@pantas.com" in text
    button = blocks[2]["elements"][0]
    assert button["action_id"] == "approve_access"
    assert button["value"] == "U2"
    assert "setup" in button["text"]["text"]


def test_public_home_explains_setup_and_offers_access():
    text = str(public_home_blocks("U1", "gopantas"))
    assert "What Mini-Reid can do" in text
    assert "Available to you now" in text
    assert "Unlocked when Ridha allows you" in text
    assert "request_access" in text
    assert "https://gopantas.slack.com/team/U1" in text
    assert "Send the deck" not in text
