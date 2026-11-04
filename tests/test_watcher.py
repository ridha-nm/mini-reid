from datetime import datetime, timedelta, timezone

from mini_reid.watcher import format_alert, new_rows

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)

ITEM = {"source": "gmail", "native_id": "m1", "kind": "inbox", "author": "a@eupe.com.my",
        "text": "please confirm the waste mapping", "link": "https://x/1",
        "ts": "2026-10-30T08:00:00+08:00", "to": "Ridha <ridha@pantas.com>"}


def test_new_rows_skips_ids_already_in_ledger():
    first = new_rows([ITEM], [], {}, NOW)
    assert len(first) == 1
    again = new_rows([ITEM], first, {}, NOW)
    assert again == []


def test_new_rows_skips_rewritten_row_for_same_link():
    first = new_rows([ITEM], [], {}, NOW)
    rewritten = dict(first[0], id="different-id", what="Confirm waste mapping")
    assert new_rows([ITEM], [rewritten], {}, NOW) == []


def test_new_rows_ignores_noise():
    noise = dict(ITEM, author='"Jira" <jira@pantas.atlassian.net>')
    assert new_rows([noise], [], {}, NOW) == []


def _rule(nid: str, what: str = "Do the thing") -> dict:
    return {"id": f"id-{nid}", "native_id": nid, "what": what,
            "status": "open", "kind": "email", "source": "gmail"}


def test_triage_keeps_the_model_rewrite_but_still_waits_for_a_click():
    from mini_reid.watcher import triage_rows

    fresh = [_rule("m1")]
    model = [dict(_rule("m1"), what="Confirm the waste mapping")]
    out = triage_rows(fresh, model)
    assert [r["what"] for r in out] == ["Confirm the waste mapping"]
    assert out[0]["status"] == "inbox"


def test_triage_keeps_rows_the_model_did_not_rewrite():
    from mini_reid.watcher import triage_rows

    out = triage_rows([_rule("m1", "raw rule title")], [])
    assert [r["what"] for r in out] == ["raw rule title"]
    assert out[0]["status"] == "inbox"


def test_triage_keeps_the_rule_client_and_asker():
    from mini_reid.watcher import triage_rows

    fresh = [dict(_rule("m1"), client="eupe", asker="Daniel")]
    model = [dict(_rule("m1"), what="Review the deck", client=None, asker="")]
    out = triage_rows(fresh, model)
    assert out[0]["client"] == "eupe"
    assert out[0]["asker"] == "Daniel"


def test_stamp_confirmation_links_rows_to_the_dm(tmp_path, monkeypatch):
    from mini_reid import watcher as w
    from mini_reid.ledger import load, save

    monkeypatch.chdir(tmp_path)
    save("ledger.json", [{"id": "a", "status": "inbox"},
                         {"id": "b", "status": "inbox"}])
    w._stamp_confirmation("ledger.json", {"a"},
                          {"ts": "111.2", "channel": "D1"})
    rows = {r["id"]: r for r in load("ledger.json")}
    assert rows["a"]["confirm_ts"] == "111.2"
    assert rows["a"]["confirm_channel"] == "D1"
    assert "confirm_ts" not in rows["b"]


def test_stale_rows_wait_for_a_day_without_activity():
    from mini_reid.watcher import stale_rows

    rows = [
        {"id": "old", "what": "Old", "status": "open",
         "last_activity": "2026-10-28T09:00:00+08:00"},
        {"id": "fresh", "what": "Fresh", "status": "open",
         "last_activity": "2026-10-30T09:00:00+08:00"},
        {"id": "done", "what": "Done", "status": "done",
         "last_activity": "2026-10-27T09:00:00+08:00"},
        {"id": "maxed", "what": "Maxed", "status": "open", "nudges": 3,
         "last_activity": "2026-10-27T09:00:00+08:00"},
    ]
    assert [r["id"] for r in stale_rows(rows, NOW)] == ["old"]


def test_stale_nudge_asks_once_a_day_and_counts_up(tmp_path, monkeypatch):
    from mini_reid import watcher as w
    from mini_reid.ledger import load, save

    monkeypatch.chdir(tmp_path)
    sent = []
    monkeypatch.setattr(w, "send_dm",
                        lambda env, text, blocks=None: sent.append((text, blocks)))
    save("ledger.json", [{"id": "a", "what": "Old thing", "status": "open",
                          "last_activity": "2026-10-28T09:00:00+08:00"}])
    evening = NOW.replace(hour=19)
    assert w.nudge_stale({}, "ledger.json", evening, "state.json") == 1
    assert sent and sent[0][1]
    row = load("ledger.json")[0]
    assert row["nudges"] == 1
    assert w.nudge_stale({}, "ledger.json", evening, "state.json") == 0
    assert load("ledger.json")[0]["nudges"] == 1


def test_brief_counts_and_names_the_most_urgent():
    from mini_reid.kb import brief

    rows = [
        {"id": "a", "what": "Send FSD", "client": "kasib", "due": "2026-10-27", "status": "open"},
        {"id": "b", "what": "Clarify waste categories", "client": "gamuda",
         "due": "2026-10-30", "status": "open"},
        {"id": "c", "what": "Later thing", "client": "ioi", "due": "2026-12-01", "status": "open"},
    ]
    text = brief(rows, NOW)
    assert "1 overdue" in text          # 27 Oct; the 30 Oct item is due today
    assert "1 due today or tomorrow" in text
    assert "Send FSD" in text
    assert "Overdue by client" in text


def test_overdue_today_excludes_notes_and_done():
    from mini_reid.watcher import overdue_today

    rows = [
        {"id": "a", "what": "late task", "due": "2026-10-29", "status": "open"},
        {"id": "b", "what": "today task", "due": "2026-10-30", "status": "open"},
        {"id": "c", "what": "a note", "due": "2026-10-01", "status": "open", "kind": "note"},
        {"id": "d", "what": "done task", "due": "2026-10-01", "status": "done"},
    ]
    out = overdue_today(rows, NOW)
    assert [r["id"] for r in out] == ["a"]


def test_overdue_today_ignores_undated_rows():
    from mini_reid.watcher import overdue_today

    rows = [
        {"id": "a", "what": "no date", "due": None, "status": "open"},
        {"id": "b", "what": "empty date", "due": "", "status": "open"},
    ]
    assert overdue_today(rows, NOW) == []


def test_overdue_nudge_uses_same_row_as_digest(tmp_path, monkeypatch):
    from mini_reid import watcher as w
    from mini_reid.ledger import save

    monkeypatch.chdir(tmp_path)
    sent = []
    monkeypatch.setattr(w, "send_dm", lambda env, text: sent.append(text))
    save("ledger.json", [
        {"id": "a", "what": "Send FSD", "client": "eupe", "due": "2026-10-28",
         "status": "open", "asker": "Daniel", "via": "email",
         "source_link": "https://x/1", "created_at": "2026-10-27T08:00:00+08:00"},
        {"id": "b", "what": "Undated thing", "due": None, "status": "open",
         "asker": "BO board", "via": "Jira", "source_link": "https://x/2"},
    ])
    assert w.nudge_overdue({}, "ledger.json", NOW) == 1
    text = sent[0]
    assert "Send FSD" in text
    assert "from Daniel (email)" in text
    assert "https://x/1" in text
    assert "Undated thing" not in text


def test_poll_dm_commands_reads_a_dm_the_bot_is_not_in(tmp_path, monkeypatch):
    from mini_reid import slack_bot
    from mini_reid import sources
    from mini_reid import watcher as w

    monkeypatch.setattr(sources, "slack_me", lambda token: "UBOT")
    monkeypatch.setattr(slack_bot, "load_users", lambda token: {"kasib": "UKASIB"})
    monkeypatch.setattr("mini_reid.notify.dm_channel", lambda token, uid: "DBOT")

    def fake_json(url, headers, retries=4):
        return {"messages": {"matches": [{
            "ts": "100.0", "user": "URIDHA", "channel": {"id": "D1"},
            "text": "@mini-reid remind @Kasib on K3 at 2pm"}]}}

    monkeypatch.setattr(sources, "_get_json", fake_json)
    scheduled, sent = [], []
    monkeypatch.setattr("mini_reid.notify.schedule_dm",
                        lambda env, uid, text, at: scheduled.append((uid, text, at)))
    monkeypatch.setattr(w, "send_dm", lambda env, text: sent.append(text))
    env = {"SLACK_USER_TOKEN": "u", "SLACK_BOT_TOKEN": "b", "SLACK_OWNER_ID": "URIDHA"}
    state = str(tmp_path / "dm_poll.json")

    assert w.poll_dm_commands(env, NOW, state) == 1
    assert scheduled[0][0] == "UKASIB"
    assert "on K3" in scheduled[0][1]
    assert "Reminder set for <@UKASIB>" in sent[0]
    assert w.poll_dm_commands(env, NOW, state) == 0


def test_poll_dm_immediate_reminder_reaches_the_recipient(tmp_path, monkeypatch):
    from mini_reid import slack_bot
    from mini_reid import sources
    from mini_reid import watcher as w

    monkeypatch.setattr(sources, "slack_me", lambda token: "UBOT")
    monkeypatch.setattr(slack_bot, "load_users", lambda token: {"kasib": "UKASIB"})
    monkeypatch.setattr("mini_reid.notify.dm_channel", lambda token, uid: "DBOT")

    def fake_json(url, headers, retries=4):
        return {"messages": {"matches": [{
            "ts": "200.0", "user": "URIDHA", "channel": {"id": "D1"},
            "text": "@mini-reid remind @Kasib to send the file"}]}}

    monkeypatch.setattr(sources, "_get_json", fake_json)
    to_user, sent = [], []
    monkeypatch.setattr("mini_reid.notify.send_dm_to",
                        lambda env, uid, text: to_user.append((uid, text)))
    monkeypatch.setattr(w, "send_dm", lambda env, text: sent.append(text))
    env = {"SLACK_USER_TOKEN": "u", "SLACK_BOT_TOKEN": "b", "SLACK_OWNER_ID": "URIDHA"}
    state = str(tmp_path / "dm_poll.json")

    assert w.poll_dm_commands(env, NOW, state) == 1
    assert to_user[0][0] == "UKASIB"
    assert "send the file" in to_user[0][1]
    assert "Reminder sent to <@UKASIB>" in sent[0]


def test_fire_reminders_sends_once(tmp_path, monkeypatch):
    from mini_reid import watcher as w
    from mini_reid.ledger import save

    sent = []
    monkeypatch.setattr(w, "send_dm", lambda env, text: sent.append(text))
    ledger = str(tmp_path / "ledger.json")
    save(ledger, [{"id": "r1", "kind": "reminder", "what": "send the deck",
                   "remind_at": "2026-10-30T08:00:00+08:00", "reminded": False}])

    assert w.fire_reminders({}, ledger, NOW) == 1
    assert w.fire_reminders({}, ledger, NOW) == 0
    assert len(sent) == 1


def test_alert_collapses_identical_items():
    from mini_reid.watcher import format_alert

    row = {"what": "Accepted: Django MCP", "client": None, "due": None, "source_link": ""}
    text = format_alert([row, dict(row), dict(row)])
    assert text.count("Accepted: Django MCP") == 1


def test_alert_is_compact_and_has_a_link():
    rows = new_rows([ITEM], [], {}, NOW)
    text = format_alert(rows)
    assert "confirm the waste mapping" in text
    assert "https://x/1" in text


def test_slack_alert_shows_sender_time_link_and_source_quote():
    row = {"source": "slack", "what": "Get Gamuda file", "client": None, "due": None,
           "asker": "Kasib", "via": "DM", "source_link": "https://x/slack",
           "evidence": "Hi @Ridha, I'm starting K1 now (provider-neutral extractor).",
           "created_at": "2026-11-01T02:14:48+08:00"}
    text = format_alert([row])
    assert "from Kasib (DM)" in text
    assert "01 Nov 02:14" in text
    assert "https://x/slack" in text
    assert "starting K1 now" in text
