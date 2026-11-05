from datetime import datetime, timedelta, timezone

from mini_reid.home_ui import home_blocks

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 5, 19, 0, tzinfo=MYT)


def test_home_shows_tasks_and_buttons():
    rows = [{"id": "a1", "what": "Send the deck", "status": "open",
             "created_at": "2026-11-05T09:00:00+08:00"}]
    blocks = home_blocks(rows, NOW, "https://slack/lists/T1/F1")
    text = str(blocks)
    assert "Send the deck" in text
    assert "Open Slack List" in text
    assert "home_refresh" in text


def test_home_survives_an_empty_ledger():
    blocks = home_blocks([], NOW)
    assert "Nothing open." in str(blocks)
