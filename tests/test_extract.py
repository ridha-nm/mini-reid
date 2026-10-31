from datetime import datetime, timedelta, timezone

import pytest

from mini_reid.extract import extract, parse_due

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)  # a Friday


@pytest.mark.parametrize("text,expected", [
    ("send by 2026-11-02", "2026-11-02"),
    ("please confirm by Friday", "2026-10-30"),
    ("can you look at this today", "2026-10-30"),
    ("done by tomorrow", "2026-10-31"),
    ("by end of next week", "2026-11-06"),
    ("no date here", None),
])
def test_parse_due(text, expected):
    assert parse_due(text, NOW)[0] == expected


def test_undated_ask_still_becomes_a_commitment():
    item = {"source": "slack", "native_id": "1", "kind": "mention", "author": "kasib",
            "text": "can you look at the dashboard", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    rows = extract(item, None, NOW)
    assert len(rows) == 1
    assert rows[0]["due"] is None
    assert rows[0]["evidence"] == "can you look at the dashboard"


def test_bot_message_is_not_a_commitment():
    item = {"source": "slack", "native_id": "2", "kind": "mention", "author": "demo app",
            "text": "<@U1> build finished", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_mention_markup_is_stripped_from_what_and_evidence():
    item = {"source": "slack", "native_id": "3", "kind": "mention", "author": "kasib",
            "text": "<@U0A33EDVAKH> send the FSD by 2026-11-02", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    row = extract(item, {"slug": "gamuda", "cycle": "gamuda-biweekly"}, NOW)[0]
    assert row["what"] == "send the FSD by 2026-11-02"
    assert row["client"] == "gamuda"
    assert row["cycle"] == "gamuda-biweekly"
    assert row["due"] == "2026-11-02"


def test_sent_mail_is_activity_not_a_commitment():
    item = {"source": "gmail", "native_id": "s1", "kind": "sent", "author": "Ridha <ridha@pantas.com>",
            "text": "Hi Amira, please check on your end", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_jira_notification_mail_is_skipped():
    item = {"source": "gmail", "native_id": "j1", "kind": "inbox",
            "author": '"kasib (Jira)" <jira@pantas.atlassian.net>',
            "text": "[JIRA] BO-8839 kasib mentioned you please review", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_informational_mail_without_an_ask_is_skipped():
    item = {"source": "gmail", "native_id": "m1", "kind": "inbox", "author": "a@eupe.com.my",
            "text": "Notes from the meeting are attached for your records.", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_calendar_response_is_not_a_commitment():
    item = {"source": "gmail", "native_id": "c1", "kind": "inbox", "author": "Myra <myra@pantas.com>",
            "subject": "Accepted: Django MCP: Scope, Discussion and Timeline @ Mon Nov 2",
            "text": "Myra Annatasha has accepted this invitation.",
            "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_dm_conversation_is_not_a_commitment():
    item = {"source": "slack", "native_id": "dm1", "kind": "dm", "author": "Julian",
            "text": "oh if you have claude then the earlier ops mcp doc can access here",
            "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_dm_ask_is_a_commitment():
    item = {"source": "slack", "native_id": "dm2", "kind": "dm", "author": "XieYi",
            "text": "CAN U JOIN 10AM INTERVIEW", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_shared_alias_undated_mail_not_addressed_is_skipped():
    item = {"source": "gmail", "native_id": "a1", "kind": "inbox", "author": "x@eupe.com.my",
            "to": "bd@pantas.com", "text": "please send the report for reference",
            "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_dated_alias_mail_is_kept():
    item = {"source": "gmail", "native_id": "a2", "kind": "inbox", "author": "x@eupe.com.my",
            "to": "bd@pantas.com", "text": "please send the report by 2026-11-02",
            "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_draft_is_kept_even_without_an_ask():
    item = {"source": "gmail", "native_id": "d1", "kind": "draft", "author": "Ridha",
            "text": "Thanks, noted.", "link": "l", "created_at": "2026-10-29T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_evidence_is_capped_at_200_chars():
    item = {"source": "gmail", "native_id": "4", "kind": "inbox", "author": "x@eupe.com.my",
            "to": "Ridha <ridha@pantas.com>",
            "text": "please " + "a" * 400, "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)[0]["evidence"]) == 200


def test_signature_is_stripped_from_what():
    item = {"source": "gmail", "native_id": "5", "kind": "draft", "author": "Ridha",
            "text": "Thanks, noted on the below. Best regards, Ridha Mohamed Sustainability Data Analyst",
            "link": "l", "created_at": "2026-10-29T08:00:00+08:00"}
    assert extract(item, None, NOW)[0]["what"] == "Thanks, noted on the below."
