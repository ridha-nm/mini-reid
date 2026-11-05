from datetime import datetime, timedelta, timezone

from mini_reid.triage_ui import apply_triage, list_blocks, triage_modal

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=MYT)


def _row(rid, what, **kw):
    row = {"id": rid, "what": what, "status": "open"}
    row.update(kw)
    return row


def _option_values(block):
    return [o["value"] for o in block["accessory"]["options"]] if "accessory" in block \
        else [o["value"] for o in block["element"]["options"]]


def test_long_list_splits_without_cutting_links():
    from mini_reid.triage_ui import SECTION_LIMIT

    rows = [_row(f"id{i:02d}", "A very long task title " * 5,
                 source_link=f"https://example.com/{i}/a-long-enough-link")
            for i in range(25)]
    blocks = list_blocks(rows, NOW)
    sections = [b for b in blocks if b.get("type") == "section"]
    assert len(sections) > 1
    assert all(len(b["text"]["text"]) <= SECTION_LIMIT for b in sections)
    joined = "\n".join(b["text"]["text"] for b in sections)
    assert "https://example.com/24/a-long-enough-link" in joined


def test_list_blocks_offer_a_triage_button():
    blocks = list_blocks([_row("a1", "Real task"),
                          _row("b2", "Maybe", status="inbox")], NOW)
    buttons = [b for b in blocks if b.get("type") == "actions"]
    assert buttons
    action = buttons[0]["elements"][0]
    assert action["action_id"] == "triage_open"
    assert "Triage" in action["text"]["text"]


def test_confirm_blocks_offer_add_and_dismiss_per_item():
    from mini_reid.triage_ui import confirm_blocks

    rows = [_row("aaaa11", "Send the deck", asker="Kasib", due="2026-11-06"),
            _row("bbbb22", "Maybe a task")]
    blocks = confirm_blocks(rows)
    actions = [b for b in blocks if b.get("type") == "actions"]
    assert len(actions) == 2
    first = actions[0]["elements"]
    assert [b["action_id"] for b in first] == ["confirm_task", "reject_task"]
    assert [b["value"] for b in first] == ["aaaa11", "aaaa11"]
    assert "Send the deck" in blocks[1]["text"]["text"]
    assert "Kasib" in blocks[1]["text"]["text"]


def test_confirm_blocks_cap_the_batch_and_point_at_the_inbox():
    from mini_reid.triage_ui import CONFIRM_MAX, confirm_blocks

    rows = [_row(f"id{i:02d}", f"Task {i}") for i in range(CONFIRM_MAX + 2)]
    blocks = confirm_blocks(rows)
    assert len([b for b in blocks if b.get("type") == "actions"]) == CONFIRM_MAX
    assert "2 more" in blocks[-1]["text"]["text"]


def test_apply_confirmation_never_toggles_a_settled_row():
    from mini_reid.triage_ui import apply_confirmation

    rows = [_row("aaaa11", "One", status="open")]
    out, row, count = apply_confirmation(rows, "aaaa11", "dropped", NOW)
    assert count == 0
    assert row["status"] == "open"
    assert out[0]["status"] == "open"


def test_remaining_confirmations_stay_on_the_same_message():
    from mini_reid.triage_ui import remaining_confirmations

    rows = [_row("a", "A", status="inbox", confirm_ts="111"),
            _row("b", "B", status="open", confirm_ts="111"),
            _row("c", "C", status="inbox", confirm_ts="222")]
    assert [r["id"] for r in remaining_confirmations(rows, "111")] == ["a"]
    assert remaining_confirmations(rows, "") == []


def test_confirmation_update_shows_outcome_and_remaining_buttons():
    from mini_reid.triage_ui import confirmation_update_blocks

    blocks = confirmation_update_blocks(
        _row("a", "First task"), "open",
        [_row("b", "Second task", status="inbox")])
    assert "Added to the list" in blocks[0]["text"]["text"]
    assert "First task" in blocks[0]["text"]["text"]
    actions = [b for b in blocks if b.get("type") == "actions"]
    assert len(actions) == 1
    assert actions[0]["elements"][0]["value"] == "b"


def test_confirmation_update_removes_buttons_when_done():
    from mini_reid.triage_ui import confirmation_update_blocks

    blocks = confirmation_update_blocks(_row("a", "First task"), "dropped", [])
    assert not [b for b in blocks if b.get("type") == "actions"]
    assert "Nothing left" in blocks[-1]["text"]["text"]


def test_triage_modal_offers_select_all_and_clear():
    modal = triage_modal([_row("a", "One")])
    buttons = [b for b in modal["blocks"] if b.get("type") == "actions"][0]
    assert [e["action_id"] for e in buttons["elements"]] == [
        "triage_select_all", "triage_clear"]


def test_select_all_preselects_every_option():
    modal = triage_modal([_row("a", "One"), _row("b", "Two")], select_all=True)
    boxes = [b for b in modal["blocks"]
             if b.get("type") == "input"
             and b["element"].get("type") == "checkboxes"][0]
    assert [o["value"] for o in boxes["element"]["initial_options"]] == ["a", "b"]


def test_select_all_keeps_the_chosen_verdict():
    modal = triage_modal([_row("a", "One")], select_all=True,
                         default_verdict="dropped")
    select = [b for b in modal["blocks"]
              if b.get("type") == "input"
              and b["element"].get("type") == "static_select"][0]
    assert select["element"]["initial_option"]["value"] == "dropped"


def test_triage_modal_chunks_more_than_ten_items():
    rows = [_row(f"id{i:02d}", f"Task {i}", status="inbox") for i in range(23)]
    modal = triage_modal(rows)
    checkbox_blocks = [b for b in modal["blocks"]
                       if b.get("type") == "input"
                       and b["element"].get("type") == "checkboxes"]
    assert len(checkbox_blocks) == 3
    assert len(_option_values(checkbox_blocks[0])) == 10
    assert len(_option_values(checkbox_blocks[-1])) == 3
    select = [b for b in modal["blocks"]
              if b.get("type") == "input"
              and b["element"].get("type") == "static_select"]
    assert [o["value"] for o in select[0]["element"]["options"]] == [
        "open", "in progress", "done", "blocked", "dropped"]


def test_stale_value_round_trips_row_and_status():
    from mini_reid.triage_ui import parse_stale_value, stale_value

    value = stale_value("abc123", "in progress")
    assert parse_stale_value(value) == ("abc123", "in progress")
    assert parse_stale_value("abc123|nonsense") is None
    assert parse_stale_value("") is None


def test_stale_blocks_offer_a_status_picker_per_task():
    from mini_reid.triage_ui import stale_blocks

    blocks = stale_blocks([_row("aaaa11", "Send the deck", due="2026-11-01")])
    picker = blocks[0]["accessory"]
    assert picker["action_id"] == "stale_set"
    assert picker["options"][0]["value"] == "aaaa11|open"
    assert [o["value"].split("|")[1] for o in picker["options"]] == [
        "open", "in progress", "done", "blocked", "dropped"]


def test_apply_triage_marks_every_selected_row():
    rows = [_row("aaaa11", "One", status="inbox"),
            _row("bbbb22", "Two", status="inbox"),
            _row("cccc33", "Three")]
    out, summary = apply_triage(rows, ["aaaa11", "bbbb22"], "dropped", NOW)
    assert [r["status"] for r in out] == ["dropped", "dropped", "open"]
    assert summary == 2
    assert out[0]["closed_how"] == "not_commitment"


def test_apply_triage_completed_sets_closed_fields():
    rows = [_row("aaaa11", "One")]
    out, _ = apply_triage(rows, ["aaaa11"], "done", NOW)
    assert out[0]["status"] == "done"
    assert out[0]["closed_at"] == NOW.isoformat()
    assert out[0]["last_activity"] == NOW.isoformat()
