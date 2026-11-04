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


def test_list_blocks_offer_a_triage_button():
    blocks = list_blocks([_row("a1", "Real task"),
                          _row("b2", "Maybe", status="inbox")], NOW)
    buttons = [b for b in blocks if b.get("type") == "actions"]
    assert buttons
    action = buttons[0]["elements"][0]
    assert action["action_id"] == "triage_open"
    assert "Triage" in action["text"]["text"]


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
