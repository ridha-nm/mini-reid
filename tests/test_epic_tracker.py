from datetime import datetime, timedelta, timezone

from mini_reid import epic_tracker

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 7, 21, 0, tzinfo=MYT)


def test_status_mapping():
    assert epic_tracker.status_for("To Do") == "open"
    assert epic_tracker.status_for("In Progress") == "in progress"
    assert epic_tracker.status_for("Peer Review") == "in progress"
    assert epic_tracker.status_for("Blocked") == "blocked"
    assert epic_tracker.status_for("Done", "done") == "done"


def test_assigned_by_me_reads_changelog():
    mine = [{"author": {"accountId": "ME"},
             "items": [{"field": "assignee", "toString": "Julian"}]}]
    theirs = [{"author": {"accountId": "OTHER"},
               "items": [{"field": "assignee", "toString": "Julian"}]}]
    assert epic_tracker.assigned_by_me(mine, "ME") is True
    assert epic_tracker.assigned_by_me(theirs, "ME") is False


def test_latest_comment_reads_adf():
    fields = {"comment": {"comments": [
        {"author": {"displayName": "Julian"},
         "created": "2026-11-07T10:00:00+08:00",
         "body": {"type": "doc", "content": [
             {"type": "paragraph", "content": [
                 {"type": "text", "text": "Root cause found"}]}]}},
    ]}}
    got = epic_tracker.latest_comment(fields)
    assert got["author"] == "Julian"
    assert "Root cause found" in got["text"]


def test_chatter_keeps_latest_message_per_key(monkeypatch):
    monkeypatch.setattr(epic_tracker, "_channel_id", lambda e, n, c: "C1")
    monkeypatch.setattr(epic_tracker, "_channel_history", lambda e, c, o: [
        {"ts": "100.1", "text": "old GRE-1 update"},
        {"ts": "200.2", "text": "new GRE-1 status and GRE-2"},
    ])
    cache = {"backfilled": {"C1": True}, "chatter_at": {"C1": "50.0"}}
    got = epic_tracker._slack_chatter(
        {}, "software-related-issues", {"GRE-1", "GRE-2"}, cache)
    assert "new GRE-1" in got["GRE-1"]["text"]
    assert "GRE-2" in got["GRE-2"]["text"]
    assert float(cache["chatter_at"]["C1"]) == 200.2
