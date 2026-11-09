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
    # "for <topic>" is as common as "about <topic>".
    assert parse_command(
        "set a meeting with @Kasib for BD Command Centre Planning and "
        "Improvements") == (
        "meet", "@Kasib for BD Command Centre Planning and Improvements")
    assert parse_meeting("@Kasib for BD Command Centre Planning and Improvements",
                         {"kasib": "U1"}, "U0") == (
        ["U1"], "BD Command Centre Planning and Improvements")
    people = {"kasib": "U1", "charanya": "U2", "arman rahman": "U3"}
    assert parse_meeting("Kasib, Charanya and Arman Rahman about the deck",
                         people, "U0") == (
        ["U1", "U2", "U3"], "the deck")
    assert parse_meeting("Nish and Eden on the Change Request Workflow",
                         {"nish": "U4", "eden": "U5"}, "U0") == (
        ["U4", "U5"], "the Change Request Workflow")
    # A real mention plus a stray word ("today") must still schedule.
    assert parse_meeting("<@U1> today", {"kasib": "U1"}, "U0") == (
        ["U1"], "Meeting with U1")


def test_attendees_can_pick_the_slot():
    from mini_reid.slack_bot import slot_picker_allowed

    pending = {"user": "URIDHA", "emails": ["kasib@pantas.com"]}
    by_email = {"kasib@pantas.com": "UKASIB"}
    assert slot_picker_allowed(pending, "URIDHA", by_email)
    assert slot_picker_allowed(pending, "UKASIB", by_email)
    assert not slot_picker_allowed(pending, "URANDOM", by_email)
    assert not slot_picker_allowed({}, "URIDHA", by_email)

    blocks = confirmation_blocks("BD", "2026-11-10T17:00:00+08:00",
                                 "2026-11-10T17:30:00+08:00", "", by="UKASIB")
    assert "Booked by <@UKASIB>" in blocks[0]["text"]["text"]


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


def test_day_paging_walks_the_working_week(monkeypatch):
    from mini_reid import meetings
    from mini_reid.slack_bot import day_links

    days = meetings.working_days(NOW)
    assert len(days) == 5
    assert all(datetime.fromisoformat(d).weekday() < 5 for d in days)
    assert day_links(days, days[0]) == ("", days[1])
    assert day_links(days, days[2]) == (days[1], days[3])
    assert day_links(days, days[-1]) == (days[-2], "")

    # One whole day at a time: every free 30-minute slot that day.
    monkeypatch.setattr(meetings, "busy_by_email", lambda *a, **k: {})
    monday = days[0]
    slots = propose_slots({}, ["kasib@pantas.com"], now=NOW, day=monday,
                          count=20)
    assert slots and all(s["start"].startswith(monday) for s in slots)
    assert len(slots) > 1

    # A weekend asks for nothing.
    assert propose_slots({}, ["kasib@pantas.com"], now=NOW,
                         day="2026-11-07") == []


def test_slot_blocks_pager_and_empty_day():
    blocks = slot_blocks("tok", "BD", [{"name": "Kasib", "email": "k@x"}], [],
                         day="2026-11-10", prev_day="2026-11-09",
                         next_day="2026-11-11")
    pager = next(b for b in blocks if b.get("type") == "actions")["elements"]
    assert [e["action_id"] for e in pager[:2]] == ["meet_day", "meet_day"]
    assert pager[0]["value"] == "tok|2026-11-09"
    assert pager[1]["value"] == "tok|2026-11-11"
    assert "Tue 10 Nov" in str(blocks)
    assert "_No free slot that day._" in str(blocks)


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
        "meet_edit", "meet_refresh", "meet_cancel"]
    done = confirmation_blocks("BD Command Centre", slots[0]["start"],
                               slots[0]["end"], "https://meet.google.com/x")
    assert "<https://meet.google.com/x|join>" in done[0]["text"]["text"]


def test_edit_modal_prefills_title_and_notes():
    from mini_reid.meeting_ui import edit_modal

    modal = edit_modal("tok", "BD Command Centre", "Bring the numbers")
    assert modal["callback_id"] == "meet_edit"
    assert modal["private_metadata"] == "tok"
    blocks = {b["block_id"]: b for b in modal["blocks"]}
    assert blocks["title"]["element"]["initial_value"] == "BD Command Centre"
    assert blocks["notes"]["element"]["initial_value"] == "Bring the numbers"


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


def test_busy_snapshot_skips_midnight_boundary_and_labels_all_day():
    from datetime import date

    from mini_reid.meeting_ui import _busy_on

    day = date(2026, 11, 11)
    boundary = (datetime(2026, 11, 10, 23, 0, tzinfo=MYT),
                datetime(2026, 11, 11, 0, 0, tzinfo=MYT))
    all_day = (datetime(2026, 11, 11, 0, 0, tzinfo=MYT),
               datetime(2026, 11, 12, 0, 0, tzinfo=MYT))
    assert _busy_on([boundary], day) == "free"
    assert _busy_on([all_day], day) == "all day"


def test_parse_duration_phrases():
    from mini_reid.meetings import parse_duration, strip_duration

    assert parse_duration("Change Request for 45 minutes") == 45
    assert parse_duration("deck for 1 hour") == 60
    assert parse_duration("deck for an hour") == 60
    assert parse_duration("no duration") is None
    assert strip_duration("Change Request for 45 minutes") == "Change Request"


def test_slot_blocks_show_the_chosen_duration():
    from datetime import datetime, timedelta

    from mini_reid.meeting_ui import slot_blocks

    start = datetime(2026, 11, 6, 12, 0, tzinfo=MYT)
    slots = [{"start": start.isoformat(),
              "end": (start + timedelta(minutes=45)).isoformat()}]
    blocks = slot_blocks("t", "Deck", [{"name": "A", "email": "a@x"}],
                         slots, duration=45)
    text = str(blocks)
    assert "45 minutes" in text


def test_edit_modal_includes_editable_duration():
    from mini_reid.meeting_ui import edit_modal

    view = edit_modal("t", "Deck", duration=45)
    blocks = {b.get("block_id"): b for b in view["blocks"] if b.get("block_id")}
    assert blocks["duration"]["element"]["initial_value"] == "45"
    assert blocks["duration"]["label"]["text"] == "Duration (minutes)"


def test_cancel_by_title_picks_the_nearest_match(monkeypatch):
    from mini_reid import meetings

    events = [
        {"id": "e2", "summary": "Change Request Workflow",
         "start": {"dateTime": (NOW + timedelta(hours=3)).isoformat()}},
        {"id": "e1", "summary": "Change Request Workflow",
         "start": {"dateTime": (NOW + timedelta(hours=1)).isoformat()}},
        {"id": "e3", "summary": "Unrelated",
         "start": {"dateTime": NOW.isoformat()}},
    ]
    monkeypatch.setattr(meetings, "upcoming_events",
                        lambda env, now, *a, **k: events)
    deleted = []
    monkeypatch.setattr(meetings, "delete_event",
                        lambda env, eid, *a, **k: deleted.append(eid))
    reply = meetings.cancel_by_title({}, "change request", NOW)
    assert deleted == ["e1"]
    assert reply.startswith("Cancelled: Change Request Workflow")
    assert meetings.cancel_by_title({}, "nothing like this", NOW) is None


def test_email_to_slack_reads_the_directory(tmp_path):
    import json

    from mini_reid.meetings import email_to_slack

    path = tmp_path / "directory.json"
    path.write_text(json.dumps({"U1": {"email": "a@pantas.com"}}))
    assert email_to_slack(str(path)) == {"a@pantas.com": "U1"}
