from datetime import datetime, timedelta, timezone

from mini_reid.clients import load_clients
from mini_reid.ledger import load
from mini_reid.slack_bot import apply_command, parse_command

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)


def test_parses_add_with_mention():
    assert parse_command("<@U123> add: Eupe item by Friday") == ("add", "Eupe item by Friday")


def test_mention_with_label_is_stripped():
    assert parse_command("<@U0CEE242B5E|mini-reid> add: send the deck") == (
        "add", "send the deck")


def test_recipient_mention_survives_command_parsing():
    assert parse_command("<@UBOT> remind <@UARMAN> to submit the timesheet at 2pm") == (
        "remind", "<@UARMAN> to submit the timesheet at 2pm")


def test_natural_add_phrasings():
    assert parse_command("<@U1> add this to my todo: send the deck") == ("add", "send the deck")
    assert parse_command("<@U1> task: send the deck") == ("add", "send the deck")
    assert parse_command("<@U1> add the FSD review by Friday") == (
        "add", "the FSD review by Friday")


def test_note_that_phrasing():
    assert parse_command("<@U1> note that Daniel wants the mapping redone") == (
        "note", "Daniel wants the mapping redone")


def test_parses_note_and_done():
    assert parse_command("<@U123> note: Daniel wants the mapping redone")[0] == "note"
    assert parse_command("<@U123> done: Eupe item")[0] == "done"


def test_remove_is_an_alias_for_drop():
    assert parse_command("<@U123> remove: a note I no longer want") == (
        "drop", "a note I no longer want")
    assert parse_command("<@U123> delete: a note I no longer want")[0] == "drop"


def test_parses_acknowledgement():
    assert parse_command("<@U123> thanks!")[0] == "ack"


def test_unknown_text():
    assert parse_command("<@U123> what is the weather")[0] == "unknown"


def test_add_writes_to_ledger(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    reply = apply_command("add", "Eupe dashboard item by Friday", NOW, clients, ledger)
    rows = load(ledger)
    assert len(rows) == 1
    assert rows[0]["client"] == "eupe"
    assert rows[0]["due"] == "2026-10-30"
    assert "Added" in reply


def test_done_closes_matching_item(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item by Friday", NOW, clients, ledger)
    reply = apply_command("done", "dashboard item", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "done"
    assert "Closed" in reply


def test_done_accepts_a_fragment_not_the_exact_title(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Confirm Eupe waste mapping categories", NOW, clients, ledger)
    reply = apply_command("done", "waste mapping", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "done"
    assert "Closed" in reply


def test_ambiguous_command_asks_which_one(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Confirm Eupe waste mapping categories", NOW, clients, ledger)
    apply_command("add", "Confirm Eupe dashboard categories", NOW, clients, ledger)
    reply = apply_command("done", "confirm eupe categories", NOW, clients, ledger)
    assert reply.startswith("Which one?")


def test_not_drops_the_row_and_records_a_correction(tmp_path, monkeypatch):
    from mini_reid import learning

    monkeypatch.setattr(learning, "PATH", str(tmp_path / "corrections.json"))
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "anything that is not part c", NOW, clients, ledger)
    reply = apply_command("not", "anything that is not part c", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "dropped"
    assert load(ledger)[0]["closed_how"] == "not_commitment"
    assert "not a commitment" in reply
    assert learning.ignored_examples() == ["anything that is not part c"]


def test_other_people_can_only_leave_a_note():
    from mini_reid.slack_bot import other_note

    assert other_note("add", "check the dashboard", "U999").startswith("from <@U999>")
    assert other_note("done", "eupe item", "U999").startswith("from <@U999>")
    assert other_note("list", "", "U999") is None
    assert other_note("find", "eupe", "U999") is None
    assert other_note("ack", "thanks", "U999") is None


def test_remind_is_parsed_without_prefix():
    assert parse_command("<@U1> remind me to send the deck tomorrow at 3pm")[0] == "remind"


def test_remind_at_parses_date_and_time():
    from mini_reid.slack_bot import parse_remind

    fields, clean = parse_remind("send the deck tomorrow at 3pm", NOW)
    assert fields["remind_at"].startswith("2026-10-31T15:00")
    assert clean == "send the deck"


def test_remind_accepts_relative_minutes():
    from mini_reid.slack_bot import parse_remind

    fields, clean = parse_remind("check the ledger in 2 minutes", NOW)
    assert fields["remind_at"].startswith("2026-10-30T09:02")
    assert clean == "check the ledger"


def test_remind_accepts_relative_hours():
    from mini_reid.slack_bot import parse_remind

    fields, _ = parse_remind("call Daniel in 3 hours", NOW)
    assert fields["remind_at"].startswith("2026-10-30T12:00")


def test_remind_in_the_past_moves_to_tomorrow():
    from mini_reid.slack_bot import parse_remind

    fields, _ = parse_remind("send the deck at 8am", NOW)
    assert fields["remind_at"].startswith("2026-10-31T08:00")


def test_remind_without_a_time_sends_now():
    from mini_reid.slack_bot import parse_remind

    fields, clean = parse_remind("send the deck", NOW)
    assert fields is not None
    assert fields["immediate"] is True
    assert fields["remind_at"].startswith("2026-10-30T09:00")
    assert fields["what"] == "send the deck"
    assert clean == "send the deck"


def test_owner_can_speak_plainly_but_questions_stay_questions():
    from mini_reid.slack_bot import owner_action

    assert owner_action("unknown", "remind me to send the deck") == "note"
    assert owner_action("unknown", "book the SFF flights") == "note"
    assert owner_action("unknown", "what is due today?") == "list"
    assert owner_action("unknown", "why is this here?") == "ask"
    assert owner_action("unknown", "show me the dashboard items") == "ask"
    assert owner_action("list", "") == "list"


def test_plain_sentence_becomes_a_note():
    from mini_reid.slack_bot import other_note

    note = other_note("unknown", "please remind ridha to send the deck", "U999")
    assert note == "from <@U999>: please remind ridha to send the deck"


def test_help_lists_commands(tmp_path):
    assert parse_command("<@U1> help") == ("help", "")
    text = apply_command("help", "", NOW, {}, str(tmp_path / "ledger.json"))
    assert "add:" in text and "snooze:" in text


def test_list_is_a_bare_command():
    assert parse_command("<@U123> list") == ("list", "")


def test_due_changes_the_date(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("due", "Eupe dashboard item by Friday", NOW, clients, ledger)
    assert load(ledger)[0]["due"] == "2026-10-30"


def test_snooze_accepts_relative_days(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("snooze", "Eupe dashboard item 3d", NOW, clients, ledger)
    assert load(ledger)[0]["due"] == "2026-11-02"


def test_waiting_flips_direction(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("waiting", "Eupe dashboard item on Daniel", NOW, clients, ledger)
    row = load(ledger)[0]
    assert row["direction"] == "owed_to_me"
    assert row["asker"] == "Daniel"


def test_drop_removes_without_deleting(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("drop", "Eupe dashboard item", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "dropped"


def test_find_returns_matches(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    assert "Eupe dashboard item" in apply_command("find", "eupe", NOW, clients, ledger)


def test_done_with_no_match_says_so(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    reply = apply_command("done", "nothing like this", NOW, {}, ledger)
    assert "No open item" in reply


def test_edit_that_still_mentions_the_bot_is_acked():
    from mini_reid.slack_bot import edit_ack_target

    event = {
        "type": "message", "subtype": "message_changed", "channel": "C1",
        "message": {"type": "message", "user": "U1", "ts": "1793414394.221409",
                    "text": "<@UBOT> add: take leave",
                    "edited": {"ts": "1793414401.000000"}},
    }
    assert edit_ack_target(event, "UBOT") == ("C1", "1793414394.221409")


def test_edit_that_drops_the_mention_or_is_a_bot_message_is_ignored():
    from mini_reid.slack_bot import edit_ack_target

    dropped = {
        "subtype": "message_changed", "channel": "C1",
        "message": {"user": "U1", "ts": "1", "text": "<@URIDHA> take note"},
    }
    assert edit_ack_target(dropped, "UBOT") is None
    assert edit_ack_target({"subtype": "message_deleted", "channel": "C1"}, "UBOT") is None
    bot = {
        "subtype": "message_changed", "channel": "C1",
        "message": {"bot_id": "B1", "user": "U1", "ts": "1", "text": "<@UBOT> hi"},
    }
    assert edit_ack_target(bot, "UBOT") is None


def test_channel_messages_need_a_mention_but_dms_do_not():
    from mini_reid.slack_bot import is_bot_addressed

    assert is_bot_addressed({"channel": "D1", "text": "add: take leave"}, "UBOT")
    assert is_bot_addressed({"channel": "C1", "text": "<@UBOT> add: take leave"}, "UBOT")
    assert not is_bot_addressed({"channel": "C1", "text": "add: take leave"}, "UBOT")


USERS = {"arman": "UARMAN", "ridha": "URIDHA", "daniel hwang": "UDANIEL"}


def test_split_target_accepts_a_full_name_with_a_space():
    from mini_reid.slack_bot import split_target

    assert split_target("daniel hwang to submit timesheet at 2pm", USERS, "URIDHA") == (
        "UDANIEL", "submit timesheet at 2pm")
    assert split_target("Daniel Hwang: submit timesheet", USERS, "URIDHA") == (
        "UDANIEL", "submit timesheet")


def test_split_target_accepts_mention_me_for_and_bare_name():
    from mini_reid.slack_bot import split_target

    assert split_target("<@UARMAN> to submit timesheet at 2pm", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet at 2pm")
    assert split_target("@arman to submit timesheet at 2pm", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet at 2pm")
    assert split_target("@Arman: submit timesheet at 2pm", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet at 2pm")
    assert split_target("me to submit timesheet at 2pm", USERS, "UARMAN") == (
        "UARMAN", "submit timesheet at 2pm")
    assert split_target("for arman: submit timesheet at 2pm", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet at 2pm")
    assert split_target("arman to submit timesheet at 2pm", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet at 2pm")


def test_split_target_leaves_ordinary_text_alone():
    from mini_reid.slack_bot import split_target

    assert split_target("send the deck to Daniel at 2pm", USERS, "URIDHA") == (
        None, "send the deck to Daniel at 2pm")
    assert split_target("talk to Daniel at 2pm", USERS, "URIDHA") == (
        None, "talk to Daniel at 2pm")


def test_reminders_are_scheduled_for_others_and_non_owners():
    from mini_reid.slack_bot import should_schedule_reminder

    owner = "URIDHA"
    assert should_schedule_reminder("remind", "UARMAN", owner, None)
    assert should_schedule_reminder("add", "UARMAN", owner, None)
    assert should_schedule_reminder("remind", owner, owner, "UARMAN")
    assert should_schedule_reminder("add", owner, owner, "UARMAN")
    assert should_schedule_reminder("remind", owner, owner, None)
    assert not should_schedule_reminder("add", owner, owner, None)
    assert not should_schedule_reminder("note", "UARMAN", owner, None)


def test_edit_renames_and_sets_a_deadline(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    reply = apply_command(
        "edit", "dashboard item to Confirm Eupe dashboard by Friday", NOW, clients, ledger)
    row = load(ledger)[0]
    assert row["what"] == "Confirm Eupe dashboard"
    assert row["due"] == "2026-10-30"
    assert "Edited" in reply


def test_edit_can_rename_without_a_date(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("edit", "dashboard item to Confirm Eupe dashboard", NOW, clients, ledger)
    row = load(ledger)[0]
    assert row["what"] == "Confirm Eupe dashboard"
    assert row["due"] is None


def test_list_numbers_items_and_edit_by_number(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("add", "Gamuda file", NOW, clients, ledger)
    listing = apply_command("list", "", NOW, clients, ledger)
    assert "1." in listing and "2." in listing
    apply_command("edit", "#2 to Get Gamuda export by Friday", NOW, clients, ledger)
    row = [r for r in load(ledger) if r["what"] == "Get Gamuda export"][0]
    assert row["due"] == "2026-10-30"


def test_done_accepts_a_list_number(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item", NOW, clients, ledger)
    apply_command("add", "Gamuda file", NOW, clients, ledger)
    apply_command("done", "#1", NOW, clients, ledger)
    rows = load(ledger)
    assert [r["status"] for r in rows if r["what"] == "Eupe dashboard item"] == ["done"]
    assert [r["status"] for r in rows if r["what"] == "Gamuda file"] == ["open"]


def test_owner_reminders_use_slack_scheduling_now():
    from mini_reid.slack_bot import should_schedule_reminder

    assert should_schedule_reminder("remind", "URIDHA", "URIDHA", None)


def test_list_shows_sender_and_link(tmp_path):
    from mini_reid.ledger import save

    ledger = str(tmp_path / "ledger.json")
    save(ledger, [{"id": "x", "what": "Send FSD", "status": "open", "kind": "mention",
                   "due": None, "asker": "Kasib", "via": "#probies",
                   "source_link": "https://x/1", "direction": "owed_by_me"}])
    text = apply_command("list", "", NOW, {}, ledger)
    assert "from Kasib (#probies)" in text
    assert "https://x/1" in text
