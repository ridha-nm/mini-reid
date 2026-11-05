from datetime import datetime, timedelta, timezone

from mini_reid.meeting_ui import confirmation_blocks, slot_blocks
from mini_reid.meetings import propose_slots

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 6, 9, 0, tzinfo=MYT)  # Friday


def test_meeting_phrase_parses_to_meet():
    from mini_reid.slack_bot import parse_command, parse_meeting

    assert parse_command("set meeting with Kasib to discuss BD Command Centre") == (
        "meet", "Kasib to discuss BD Command Centre")
    assert parse_command("meet: @Kasib about BD Command Centre") == (
        "meet", "@Kasib about BD Command Centre")
    assert parse_meeting("Kasib to discuss BD Command Centre",
                         {"kasib": "U1"}, "U0") == (
        ["U1"], "BD Command Centre")
    assert parse_meeting("with Kasib about the dashboard",
                         {"kasib": "U1"}, "U0") == (["U1"], "the dashboard")
    people = {"kasib": "U1", "charanya": "U2", "arman rahman": "U3"}
    assert parse_meeting("Kasib, Charanya and Arman Rahman about the deck",
                         people, "U0") == (
        ["U1", "U2", "U3"], "the deck")


def test_propose_slots_skips_busy_and_weekend(monkeypatch):
    from mini_reid import meetings

    busy = {
        "ridha@pantas.com": [
            (datetime(2026, 11, 6, 9, 0, tzinfo=MYT),
             datetime(2026, 11, 6, 10, 0, tzinfo=MYT))],
        "kasib@pantas.com": [
            (datetime(2026, 11, 6, 10, 0, tzinfo=MYT),
             datetime(2026, 11, 6, 11, 0, tzinfo=MYT))],
    }
    monkeypatch.setattr(meetings, "busy_by_email",
                        lambda *a, **k: busy)
    slots = propose_slots({}, ["kasib@pantas.com"], now=NOW)
    assert slots
    starts = [datetime.fromisoformat(s["start"]) for s in slots]
    assert all(s.weekday() < 5 for s in starts)
    for s in starts:
        assert not (s < datetime(2026, 11, 6, 11, 0, tzinfo=MYT)
                    < s + timedelta(minutes=30))


def test_slot_and_confirmation_blocks():
    slots = [{"start": "2026-11-06T11:00:00+08:00",
              "end": "2026-11-06T11:30:00+08:00"}]
    blocks = slot_blocks("tok", "BD Command Centre",
                         [{"name": "Kasib", "email": "kasib@pantas.com"}], slots)
    pick = next(b for b in blocks if b.get("accessory"))
    assert pick["accessory"]["action_id"] == "meet_slot"
    assert pick["accessory"]["value"] == "tok|2026-11-06T11:00:00+08:00"
    assert "11:00–11:30" in pick["text"]["text"]
    assert "BD Command Centre" in str(blocks[1])
    controls = next(b for b in blocks if b.get("type") == "actions")
    assert [e["action_id"] for e in controls["elements"]] == [
        "meet_refresh", "meet_cancel"]
    done = confirmation_blocks("BD Command Centre", slots[0]["start"],
                               slots[0]["end"], "https://meet.google.com/x")
    assert "<https://meet.google.com/x|join>" in done[0]["text"]["text"]


def test_slot_blocks_show_both_calendars_busy():
    from datetime import datetime

    slots = [{"start": "2026-11-06T11:00:00+08:00",
              "end": "2026-11-06T11:30:00+08:00"}]
    busy = {
        "ridha@pantas.com": [(datetime(2026, 11, 6, 9, 0, tzinfo=MYT),
                              datetime(2026, 11, 6, 10, 0, tzinfo=MYT))],
        "kasib@pantas.com": [(datetime(2026, 11, 6, 10, 0, tzinfo=MYT),
                             datetime(2026, 11, 6, 11, 0, tzinfo=MYT))],
    }
    text = str(slot_blocks("tok", "BD Command Centre",
                           [{"name": "Kasib", "email": "kasib@pantas.com"}],
                           slots, busy))
    assert "Availability snapshot" in text
    assert "09:00–10:00" in text and "10:00–11:00" in text
