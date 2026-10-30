from datetime import datetime, timedelta, timezone

from mini_reid.clients import load_clients
from mini_reid.ledger import load
from mini_reid.slack_bot import apply_command, parse_command

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)


def test_parses_add_with_mention():
    assert parse_command("<@U123> add: Eupe item by Friday") == ("add", "Eupe item by Friday")


def test_parses_note_and_done():
    assert parse_command("<@U123> note: Daniel wants the mapping redone")[0] == "note"
    assert parse_command("<@U123> done: Eupe item")[0] == "done"


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


def test_remind_in_the_past_moves_to_tomorrow():
    from mini_reid.slack_bot import parse_remind

    fields, _ = parse_remind("send the deck at 8am", NOW)
    assert fields["remind_at"].startswith("2026-10-31T08:00")


def test_remind_without_a_date_needs_one():
    from mini_reid.slack_bot import parse_remind

    fields, _ = parse_remind("send the deck", NOW)
    assert fields is None


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
