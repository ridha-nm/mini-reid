from datetime import datetime, timedelta, timezone

import mini_reid.calendar as cal

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=MYT)


def event(**kw):
    base = {
        "id": "e1", "summary": "Eupe catch-up",
        "status": "confirmed",
        "start": {"dateTime": "2026-11-02T09:30:00+08:00"},
        "end": {"dateTime": "2026-11-02T10:00:00+08:00"},
        "hangoutLink": "https://meet.google.com/abc",
        "htmlLink": "https://calendar.google.com/event?eid=1",
    }
    base.update(kw)
    return base


def test_ignore_title_persists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cal.ignore_title("Chiropractor")
    assert "chiropractor" in cal.ignored_titles()
    cal.ignore_title("Personal block")
    assert cal.ignored_titles() == {"chiropractor", "personal block"}


def test_parse_keeps_timed_meeting_and_join_link():
    out = cal.parse_events({"items": [event()]}, "Work", "2026-11-02", owned=True)
    assert len(out) == 1
    assert out[0]["title"] == "Eupe catch-up"
    assert out[0]["link"] == "https://meet.google.com/abc"
    assert cal.span(out[0]) == "09:30–10:00"


def test_shared_calendar_keeps_only_events_ridha_is_invited_to():
    theirs = event(id="theirs", attendees=[
        {"email": "arman@pantas.com", "self": True, "responseStatus": "accepted"}])
    mine = event(id="mine", attendees=[
        {"email": "ridha@pantas.com", "self": True, "responseStatus": "accepted"}])
    no_attendees = event(id="empty", attendees=[])
    out = cal.parse_events({"items": [theirs, mine, no_attendees]}, "Arman", "2026-11-02")
    assert [e["id"] for e in out] == ["mine"]
    owned = cal.parse_events({"items": [theirs, no_attendees]}, "Ridha", "2026-11-02",
                             owned=True)
    assert [e["id"] for e in owned] == ["theirs", "empty"]


def test_parse_drops_all_day_cancelled_declined_and_focus_time():
    items = [
        event(id="allday", start={"date": "2026-11-02"}, end={"date": "2026-11-03"}),
        event(id="cancelled", status="cancelled"),
        event(id="declined", attendees=[{"self": True, "responseStatus": "declined"}]),
        event(id="focus", eventType="focusTime"),
    ]
    assert cal.parse_events({"items": items}, "Work", "2026-11-02") == []


def test_parse_falls_back_to_conference_video_then_html_link():
    conference = event(id="e2", hangoutLink=None, conferenceData={
        "entryPoints": [{"entryPointType": "video", "uri": "https://zoom/x"}]})
    assert cal.parse_events({"items": [conference]}, "Work", "2026-11-02",
                            owned=True)[0]["link"] == "https://zoom/x"
    without = event(id="e3", hangoutLink=None, htmlLink="")
    assert cal.parse_events({"items": [without]}, "Work", "2026-11-02",
                            owned=True)[0]["link"] == ""


def test_meeting_reply_records_yes_and_no_with_reason(tmp_path):
    import json

    from mini_reid.watcher import record_meeting_reply

    state = {"date": "2026-11-02", "meetings": {
        "m1": {"title": "Eupe catch-up", "status": "scheduled",
               "start": "2026-11-02T09:10:00+08:00"}}}
    path = tmp_path / "meetings.json"
    path.write_text(json.dumps(state))
    assert record_meeting_reply("yes", NOW, str(path)) == "Attending: Eupe catch-up"
    assert json.loads(path.read_text())["meetings"]["m1"]["status"] == "attending"

    state["meetings"]["m1"]["status"] = "scheduled"
    path.write_text(json.dumps(state))
    assert record_meeting_reply("no, client call", NOW, str(path)) == (
        "Not attending: Eupe catch-up — client call")
    saved = json.loads(path.read_text())["meetings"]["m1"]
    assert saved["status"] == "declined"
    assert saved["reason"] == "client call"


def test_meeting_reply_ignores_text_with_no_nearby_meeting(tmp_path):
    from mini_reid.watcher import record_meeting_reply

    path = tmp_path / "meetings.json"
    path.write_text('{"date": "2026-11-02", "meetings": {"m1": '
                    '{"title": "Later", "status": "scheduled", '
                    '"start": "2026-11-02T18:00:00+08:00"}}}')
    assert record_meeting_reply("yes", NOW, str(path)) is None
    assert record_meeting_reply("maybe", NOW, str(path)) is None


def test_remind_meetings_schedules_once_and_sends_late_discovery_now(tmp_path, monkeypatch):
    from mini_reid import watcher

    meetings = [
        {"id": "later", "title": "Later", "start": "2026-11-02T09:30:00+08:00",
         "end": "2026-11-02T10:00:00+08:00", "link": "https://meet/x"},
        {"id": "soon", "title": "Soon", "start": "2026-11-02T09:05:00+08:00",
         "end": "2026-11-02T09:20:00+08:00", "link": ""},
    ]
    monkeypatch.setattr(cal, "meetings_for_day",
                        lambda env, now, **kwargs: meetings)
    scheduled, sent = [], []
    monkeypatch.setattr(watcher, "send_dm", lambda env, text: sent.append(text))
    monkeypatch.setattr("mini_reid.notify.schedule_dm",
                        lambda env, uid, text, at: scheduled.append((uid, text, at)))
    state = str(tmp_path / "meetings.json")

    assert watcher.remind_meetings({"SLACK_OWNER_ID": "U1"}, NOW, state) == 2
    assert len(scheduled) == 1 and len(sent) == 1
    assert "Are you attending?" in scheduled[0][1]
    assert watcher.remind_meetings({"SLACK_OWNER_ID": "U1"}, NOW, state) == 0
