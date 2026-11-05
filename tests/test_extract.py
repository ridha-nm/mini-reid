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
    ("by thursday nov 12", "2026-11-12"),
    ("review on 12 nov", "2026-11-12"),
    ("review on Nov 12", "2026-11-12"),
    ("no date here", None),
])
def test_parse_due(text, expected):
    assert parse_due(text, NOW)[0] == expected


def test_member_gmail_is_scoped_to_their_own_address():
    item = {"source": "gmail", "native_id": "g1", "kind": "inbox",
            "author": "Kasib <kasib@pantas.com>",
            "to": "Charanya <charanya@pantas.com>", "subject": "Deck",
            "text": "can you send the deck", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW, me="Charanya")
    item["to"] = "Ridha <ridha@pantas.com>"
    assert extract(item, None, NOW, me="Charanya") == []


def test_play_requests_are_not_commitments():
    for text in ("<@UBOT> pls give ridha a hug",
                 "high five Julian",
                 "give <@U1> a fist bump"):
        item = {"source": "slack", "native_id": text, "kind": "mention",
                "author": "kasib", "text": text, "link": "l",
                "ts": "2026-10-30T08:00:00+08:00"}
        assert extract(item, None, NOW) == []


def test_undated_ask_still_becomes_a_commitment():
    item = {"source": "slack", "native_id": "1", "kind": "mention", "author": "kasib",
            "text": "can you look at the dashboard", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    rows = extract(item, None, NOW)
    assert len(rows) == 1
    assert rows[0]["due"] is None
    assert rows[0]["evidence"] == "can you look at the dashboard"


def test_triager_channel_tags_are_ignored():
    base = {"source": "slack", "native_id": "t1", "kind": "mention", "author": "triager",
            "text": "can you review this issue", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(dict(base, channel="bd-triager-agent"), None, NOW) == []
    assert extract(dict(base, channel="other", channel_id="C0B59LA0X5M"), None, NOW) == []


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


def test_draft_is_not_a_commitment():
    item = {"source": "gmail", "native_id": "d1", "kind": "draft", "author": "Ridha",
            "text": "Thanks, noted.", "link": "l", "created_at": "2026-10-29T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_evidence_is_capped_at_200_chars():
    item = {"source": "gmail", "native_id": "4", "kind": "inbox", "author": "x@eupe.com.my",
            "to": "Ridha <ridha@pantas.com>",
            "text": "please " + "a" * 400, "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)[0]["evidence"]) == 200


def test_signature_is_stripped_from_what():
    item = {"source": "gmail", "native_id": "5", "kind": "inbox",
            "author": "x@eupe.com.my", "to": "Ridha <ridha@pantas.com>",
            "text": "please review the attached. Best regards, Ridha Mohamed Sustainability Data Analyst",
            "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW)[0]["what"] == "please review the attached."


@pytest.mark.parametrize("text", [
    "Den i ??",
    "Ridha do you have claude access to access artifact?",
    "U need help with builindg?",
    "Hows the builing building going and I try to get FSD today no promises",
    "Update: #179 has merged and I've merged it into K1 locally. OK for me to start K2 now?",
    "you speak mandarin?",
])
def test_dm_questions_and_updates_are_not_tasks(text):
    item = {"source": "slack", "native_id": "q", "kind": "dm", "author": "Kasib",
            "text": text, "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


@pytest.mark.parametrize("text", ["Get Gamuda file", "Start K2", "Send the FSD by Friday"])
def test_short_imperative_dm_is_a_task(text):
    item = {"source": "slack", "native_id": "i", "kind": "dm", "author": "Kasib",
            "text": text, "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_meeting_notes_mail_is_not_a_task():
    item = {"source": "gmail", "native_id": "mt", "kind": "inbox",
            "author": "Daniel <daniel@pantas.com>",
            "subject": "Stock Take & Action Items: Pantas <> IOI Properties - 1 Oct",
            "text": "Here are the notes from the meeting.", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_channel_mention_is_kept_even_without_request_words():
    item = {"source": "slack", "native_id": "m2", "kind": "mention", "author": "kasib",
            "text": "<@U1> FSD today no promises", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_thanks_mention_is_not_a_task():
    item = {"source": "slack", "native_id": "m3", "kind": "mention", "author": "kasib",
            "text": "<@U1> thanks", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_dm_need_the_thing_by_date_is_a_task():
    item = {"source": "slack", "native_id": "need", "kind": "dm", "author": "Kasib",
            "text": "Ridha, need the FSD by Friday", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_jira_epic_is_not_a_task():
    item = {"source": "jira", "native_id": "1", "kind": "issue", "author": "BO board",
            "text": "Eupe Corporation Berhad", "subject": "Eupe Corporation Berhad",
            "issue_type": "Epic", "link": "l", "ts": "2026-10-30T08:00:00+08:00"}
    assert extract(item, None, NOW) == []


def test_jira_task_is_kept():
    item = {"source": "jira", "native_id": "2", "kind": "issue", "author": "BO board",
            "text": "[RIJ] Configure file mappings", "issue_type": "Task",
            "subject": "[RIJ] Configure file mappings", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    assert len(extract(item, None, NOW)) == 1


def test_email_asker_keeps_the_full_address():
    item = {"source": "gmail", "native_id": "e1", "kind": "inbox",
            "author": "Quekjoelyn <bd@pantas.com>", "to": "Ridha <ridha@pantas.com>",
            "text": "please confirm the activity item descriptions", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    row = extract(item, None, NOW)[0]
    assert row["asker"] == "Quekjoelyn (bd@pantas.com)"


def test_auto_capture_matrix():
    from mini_reid.extract import auto_reason
    slack = {"source": "slack", "kind": "mention"}
    dm = {"source": "slack", "kind": "dm"}
    mail = {"source": "gmail", "kind": "inbox",
            "to": "Ridha <ridha@pantas.com>"}
    jira = {"source": "jira", "kind": "issue"}
    assert auto_reason(jira, "Audit data units", None, None) == "jira-assigned"
    assert auto_reason(slack, "can you review the deck", None, None) == "slack-direct-ask"
    assert auto_reason(slack, "the office is closed tomorrow", None, None) is None
    assert auto_reason(dm, "send the deck", None, None) is None
    assert auto_reason(dm, "send the deck by Friday", "2026-11-06", None) == "slack-dm-ask"
    assert auto_reason(mail, "please confirm the mapping", None, "Ridha") == "email-direct-ask"
    alias = dict(mail, to="BD <bd@pantas.com>")
    assert auto_reason(alias, "please confirm the mapping", None, "Ridha") is None


def test_extract_stamps_capture_mode():
    item = {"source": "slack", "native_id": "s1", "kind": "mention",
            "author": "kasib", "text": "can you review the deck", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    row = extract(item, None, NOW)[0]
    assert row["capture"] == "auto"
    assert row["capture_why"] == "slack-direct-ask"
