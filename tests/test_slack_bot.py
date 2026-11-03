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
    assert parse_command("@minireid remind @arman on K3 at 2pm") == (
        "remind", "@arman on K3 at 2pm")


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


def test_combine_merges_duplicate_into_kept_row(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Boon Hee generic activity data for concrete", NOW, clients, ledger)
    apply_command("add", "Suggest suitable activity item for project usage", NOW,
                  clients, ledger)
    reply = apply_command("combine",
                          "generic activity data into suitable activity item",
                          NOW, clients, ledger)
    rows = load(ledger)
    assert len(rows) == 2
    duplicate = next(r for r in rows if "generic activity data" in r["what"])
    keep = next(r for r in rows if "suitable activity item" in r["what"])
    assert duplicate["status"] == "dropped"
    assert duplicate["closed_how"] == "merged"
    assert duplicate["merged_into"] == keep["id"]
    assert keep["status"] == "open"
    assert keep["merged_from"][0]["what"].startswith("Boon Hee")
    assert reply.startswith("Combined:")


def test_combine_parses_with_numbers():
    assert parse_command("<@U123> combine: #9 into #7") == ("combine", "#9 into #7")


def test_assign_creates_a_waiting_on_row(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    reply = apply_command("assign", "@Kasib send the deck by Friday", NOW,
                          clients, ledger)
    row = load(ledger)[0]
    assert row["direction"] == "owed_to_me"
    assert row["asker"] == "Kasib"
    assert row["assigned_to"] == "Kasib"
    assert row["due"] == "2026-10-30"
    assert reply.startswith("Assigned to Kasib:")


def test_assign_accepts_name_to_phrasing():
    assert parse_command("<@U123> assign: Kasib to send the deck") == (
        "assign", "Kasib to send the deck")
    assert parse_command("<@U123> reassign: deck to Kasib") == (
        "reassign", "deck to Kasib")


def test_assign_accepts_a_slack_mention(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    reply = apply_command("assign", "<@U09CCJW1JL8> Stop HARASSING MINI REID", NOW,
                          {}, ledger, {"kasib": "U09CCJW1JL8"})
    row = load(ledger)[0]
    assert row["assigned_to"] == "kasib"
    assert reply.startswith("Assigned to kasib:")


def test_reassign_moves_an_existing_task_to_waiting_on_others(tmp_path):
    from mini_reid.render import render

    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Send the deck by Friday", NOW, clients, ledger)
    reply = apply_command("reassign", "deck to Kasib", NOW, clients, ledger)
    row = load(ledger)[0]
    assert row["direction"] == "owed_to_me"
    assert row["assigned_to"] == "Kasib"
    assert row["asker"] == "Kasib"
    assert reply.startswith("Reassigned to Kasib:")
    out = render([row], NOW, [], slack=True)
    assert "*Waiting on others (1)*" in out


def test_banter_reply_respects_channel_user_expiry_and_mentions(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from mini_reid.slack_bot import BANTER_LINES, banter_reply

    monkeypatch.chdir(tmp_path)
    Path("banter.json").write_text(json.dumps({
        "channel": "C1", "users": ["U1"],
        "until": "2099-01-01T00:00:00+08:00"}))
    # Neutral chatter gets no banter; only mean messages do.
    assert banter_reply("C1", "U1", "hello", "UBOT") is None
    assert banter_reply("C2", "U1", "you are stupid", "UBOT") is None
    Path("banter.json").write_text(json.dumps({
        "channel": "C1", "users": ["*"],
        "until": "2099-01-01T00:00:00+08:00"}))
    assert banter_reply("C1", "U2", "hello", "UBOT") is None
    from mini_reid.slack_bot import is_mean

    assert is_mean("you are stupid")
    assert is_mean("shut up")
    assert not is_mean("how would you describe yourself")


def test_mean_message_arms_five_minutes_without_extending(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from mini_reid.slack_bot import arm_banter

    monkeypatch.chdir(tmp_path)
    assert arm_banter("C1", NOW)
    cfg = json.loads(Path("banter.json").read_text())
    assert cfg["until"] == "2026-10-30T09:05:00+08:00"
    assert not arm_banter("C1", NOW)  # already on; do not extend


def test_banter_command_controls_scope_and_duration(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from mini_reid.slack_bot import banter_command

    monkeypatch.chdir(tmp_path)
    kind, _ = banter_command("banter on 2h", "C1", {}, NOW)
    cfg = json.loads(Path("banter.json").read_text())
    assert kind == "on"
    assert cfg["channel"] == "C1" and cfg["users"] == ["*"]
    assert cfg["until"] == "2026-10-30T11:00:00+08:00"

    kind, _ = banter_command("banter on 30m <@U1>", "C1", {}, NOW)
    cfg = json.loads(Path("banter.json").read_text())
    assert cfg["users"] == ["U1"]
    assert cfg["until"] == "2026-10-30T09:30:00+08:00"

    kind, _ = banter_command("banter off", "C1", {}, NOW)
    assert kind == "off"
    assert not Path("banter.json").exists()


def test_claim_message_is_persistent_and_releasable(tmp_path):
    from mini_reid.slack_bot import claim_message, release_message

    state = str(tmp_path / "bot_state.json")
    assert claim_message(state, "C1", "1.000")
    assert not claim_message(state, "C1", "1.000")
    assert claim_message(state, "C1", "2.000")
    assert claim_message(state, "C2", "1.000")
    release_message(state, "C1", "1.000")
    assert claim_message(state, "C1", "1.000")


def test_nice_messages_get_a_nice_reply():
    from mini_reid.slack_bot import NICE_LINES, nice_reply

    assert nice_reply("fkin loving @mini-reid") in NICE_LINES
    assert nice_reply("good bot, thanks") in NICE_LINES
    assert nice_reply("loving the dashboard") in NICE_LINES
    assert nice_reply("remind @Kasib to call at 2pm") is None


def test_default_reply_for_smalltalk_only():
    from mini_reid.slack_bot import DEFAULT_REPLY, chatter_reply

    assert chatter_reply("hi") == DEFAULT_REPLY
    assert chatter_reply("hey mini-reid, you there?") == DEFAULT_REPLY
    assert chatter_reply("test") == DEFAULT_REPLY
    assert chatter_reply("add: send the deck by Friday") is None
    assert chatter_reply("note: Daniel wants the mapping redone") is None
    assert chatter_reply("remind @Kasib to call at 2pm") is None


def test_literal_handle_counts_as_addressed_in_a_channel():
    from mini_reid.slack_bot import is_bot_addressed

    assert is_bot_addressed({"channel": "C1", "text": "@mini-reid hi"}, "UBOT")
    assert is_bot_addressed({"channel": "C1", "text": "@minireid hi"}, "UBOT")
    assert not is_bot_addressed({"channel": "C1", "text": "mini-reid hi"}, "UBOT")


def test_guardrail_refuses_interpersonal_relay():
    from mini_reid.slack_bot import guardrail_reply

    assert guardrail_reply("please tell xie yi to stop harassing his colleagues")
    assert guardrail_reply("@mini-reid pls stop raj to stop harassing me")
    assert guardrail_reply("ok @mini-reid unblock me")
    assert guardrail_reply("@mini-reid please treat raj nicely")
    assert guardrail_reply("@mini-reid start huddle with xieyi") == (
        "🛑 I can't start huddles. I track tasks, notes and reminders.")
    assert guardrail_reply("im going to fkin bomb ur house and use deepseek") == (
        "🛑 I'm a bot with a ledger, not a house. Take that somewhere else.")
    from mini_reid.slack_bot import SASSY_LINES

    assert guardrail_reply("Shut the fuck up @mini-reid") in SASSY_LINES
    assert guardrail_reply("Stupid bitch ass @mini-reid") in SASSY_LINES
    assert guardrail_reply("remind @XieYi to send the deck") is None
    assert guardrail_reply("add: stop the deployment by Friday") is None


def test_notes_lists_notes_not_tasks(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "A real task", NOW, clients, ledger)
    apply_command("note", "a remembered fact", NOW, clients, ledger)
    apply_command("add", "A second task", NOW, clients, ledger)
    apply_command("tonote", "A second task", NOW, clients, ledger)
    out = apply_command("notes", "", NOW, clients, ledger)
    assert "a remembered fact" in out
    assert "A second task" in out
    assert "A real task" not in out
    assert parse_command("notes") == ("notes", "")


def test_adding_a_dropped_task_again_reopens_it(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "let Boon Hee know of his access fixes", NOW, clients, ledger)
    apply_command("drop", "Boon Hee", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "dropped"
    reply = apply_command("add", "let Boon Hee know of his access fixes", NOW,
                          clients, ledger)
    rows = load(ledger)
    assert len(rows) == 1
    assert rows[0]["status"] == "open"
    assert rows[0]["closed_how"] is None
    assert reply.startswith("Reopened.")


def test_tonote_converts_a_task_and_keeps_it_reachable_by_id(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "GHB invoicing cycle complete", NOW, clients, ledger)
    task_id = load(ledger)[0]["id"]
    apply_command("priority", "GHB invoicing cycle complete 1", NOW, clients, ledger)
    reply = apply_command("tonote", task_id[:6], NOW, clients, ledger)
    row = load(ledger)[0]
    assert reply.startswith("Converted to note:")
    assert row["kind"] == "note"
    assert row["due"] is None
    assert "priority" not in row
    # A note is not in the numbered list, but its stable id still resolves.
    apply_command("drop", task_id[:6], NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "dropped"


def test_tonote_is_parsed():
    assert parse_command("<@U123> tonote: #4") == ("tonote", "#4")
    assert parse_command("<@U123> convert: GHB invoicing")[0] == "convert"


def test_priority_sets_ranks_and_clears(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Focus task", NOW, clients, ledger)
    assert apply_command("priority", "Focus task 1", NOW, clients, ledger).startswith("P1:")
    assert load(ledger)[0]["priority"] == 1
    apply_command("priority", "Focus task low", NOW, clients, ledger)
    assert load(ledger)[0]["priority"] == 5
    assert apply_command("priority", "Focus task none", NOW, clients, ledger).startswith(
        "Priority cleared:")
    assert "priority" not in load(ledger)[0]


def test_priority_command_is_parsed():
    assert parse_command("<@U123> priority: #3 1") == ("priority", "#3 1")
    assert parse_command("<@U123> prio: Eupe item high")[0] == "prio"


def test_undo_reverses_mutations_and_stops_when_empty(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "First task", NOW, clients, ledger)
    apply_command("add", "Second task", NOW, clients, ledger)
    assert apply_command("undo", "", NOW, clients, ledger) == (
        "Undone the last ledger change.")
    assert len(load(ledger)) == 1
    apply_command("undo", "", NOW, clients, ledger)
    assert load(ledger) == []
    assert apply_command("undo", "", NOW, clients, ledger) == "Nothing to undo."


def test_undo_restores_an_edited_title(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Original title", NOW, clients, ledger)
    apply_command("edit", "Original title to Renamed title", NOW, clients, ledger)
    assert load(ledger)[0]["what"] == "Renamed title"
    apply_command("undo", "", NOW, clients, ledger)
    assert load(ledger)[0]["what"] == "Original title"


def test_uncombine_restores_the_duplicate(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Boon Hee generic activity data for concrete", NOW, clients, ledger)
    apply_command("add", "Suggest suitable activity item for project usage", NOW,
                  clients, ledger)
    apply_command("combine", "generic activity data into suitable activity item",
                  NOW, clients, ledger)
    reply = apply_command("uncombine", "suitable activity item", NOW, clients, ledger)
    rows = load(ledger)
    assert all(r["status"] == "open" for r in rows)
    assert len(rows) == 2
    assert reply.startswith("Restored 1 item(s)")


def test_stable_id_resolves_after_reordering(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "First task", NOW, clients, ledger)
    first_id = load(ledger)[0]["id"]
    apply_command("add", "Second task", NOW, clients, ledger)
    apply_command("done", "Second task", NOW, clients, ledger)
    reply = apply_command("done", f"id:{first_id[:6]}", NOW, clients, ledger)
    assert "Closed: First task" == reply
    assert load(ledger)[0]["status"] == "done"


def test_bracketed_id_from_list_is_accepted(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Bracket task", NOW, clients, ledger)
    row_id = load(ledger)[0]["id"]
    reply = apply_command("done", f"[{row_id[:6]}]", NOW, clients, ledger)
    assert reply == "Closed: Bracket task"


def test_bare_short_id_works_without_the_prefix(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "First task", NOW, clients, ledger)
    apply_command("add", "Second task", NOW, clients, ledger)
    rows = load(ledger)
    first = next(r for r in rows if r["what"] == "First task")
    reply = apply_command("done", first["id"][:6], NOW, clients, ledger)
    assert reply == "Closed: First task"


def test_status_sets_in_progress_blocked_and_open(tmp_path):
    ledger = str(tmp_path / "ledger.json")
    clients = load_clients("clients.json")
    apply_command("add", "Eupe dashboard item by Friday", NOW, clients, ledger)
    reply = apply_command("status", "dashboard item in progress", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "in progress"
    assert "in progress" in reply
    apply_command("status", "dashboard item blocked", NOW, clients, ledger)
    assert load(ledger)[0]["status"] == "blocked"
    apply_command("status", "dashboard item open", NOW, clients, ledger)
    row = load(ledger)[0]
    assert row["status"] == "open"
    assert "stalled_since" not in row


def test_not_dismisses_a_meeting_reminder(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from mini_reid.calendar import ignored_titles

    monkeypatch.chdir(tmp_path)
    Path("meeting_reminders.json").write_text(json.dumps({
        "date": "2026-10-30",
        "meetings": {"m1": {"title": "Chiropractor", "start": "2026-10-30T12:00:00+08:00",
                            "status": "scheduled"}}}))
    reply = apply_command("not", "Chiropractor", NOW, {}, "ledger.json")
    assert reply == "Ignored meeting: Chiropractor"
    assert "chiropractor" in ignored_titles()


def test_status_command_is_parsed():
    assert parse_command("<@U123> status: Eupe item blocked") == (
        "status", "Eupe item blocked")


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


USERS = {"arman": "UARMAN", "arman rahman": "UARMAN", "ridha": "URIDHA"}


def test_split_target_accepts_a_full_name_with_a_space():
    from mini_reid.slack_bot import split_target

    assert split_target("arman rahman to submit timesheet at 2pm", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet at 2pm")
    assert split_target("Arman Rahman: submit timesheet", USERS, "URIDHA") == (
        "UARMAN", "submit timesheet")


def test_unresolved_recipient_is_named_not_silently_sent_to_sender():
    from mini_reid.slack_bot import unresolved_recipient

    assert unresolved_recipient("Daniel Hwang to send the file", USERS) == "Daniel Hwang"
    assert unresolved_recipient("@XieYi to check the deck", USERS) == "XieYi"
    assert unresolved_recipient("me to send the deck", USERS) is None
    assert unresolved_recipient("send the deck to Daniel at 2pm", USERS) is None


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
