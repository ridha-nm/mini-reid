from datetime import datetime, timedelta, timezone

from mini_reid.slack_bot import (add_slack_capture, capture_modal,
                                 capture_reaction)

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 5, 19, 0, tzinfo=MYT)


def test_capture_row_links_the_source_message_and_dedupes(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    row = add_slack_capture(
        ledger, "Submit health screening claims", "C1", "1793866425.785539",
        "U2", {"charanya": "U2"}, NOW,
        permalink="https://slack/x", via="shortcut")
    assert row["source"] == "slack"
    assert row["source_link"] == "https://slack/x"
    assert row["native_id"] == "C1:1793866425.785539"
    assert row["via"] == "shortcut"
    assert row["status"] == "open"
    add_slack_capture(ledger, "Submit health screening claims", "C1",
                      "1793866425.785539", "U2", {"charanya": "U2"}, NOW)
    from mini_reid.ledger import load
    assert len(load(ledger)) == 1


def test_capture_modal_prefills_the_message_title():
    view = capture_modal("10 am interview",
                         {"channel": "C1", "ts": "1.2",
                          "permalink": "https://slack/x"})
    assert view["callback_id"] == "mini_reid_capture"
    assert view["blocks"][-1]["element"]["initial_value"] == "10 am interview"
    assert "https://slack/x" in str(view["blocks"])


def test_capture_reaction_only_accepts_the_configured_emoji():
    event = {"type": "reaction_added", "reaction": "pushpin",
             "user": "U2", "item": {"type": "message", "channel": "C1",
                                    "ts": "1.2"}}
    assert capture_reaction(event, "pushpin") == ("C1", "1.2", "U2")
    assert capture_reaction(event, "white_check_mark") is None
    event["item"]["type"] = "file"
    assert capture_reaction(event, "pushpin") is None
