from datetime import datetime, timedelta, timezone

from mini_reid.render import render

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)

ROW = {"id": "a", "what": "send the FSD", "due": "2026-10-30", "status": "open",
       "source_link": "https://x/1", "client": "gamuda", "direction": "owed_by_me"}


def test_meetings_render_as_rows_with_join_links():
    meetings = [{"id": "m1", "title": "Eupe catch-up",
                 "start": "2026-10-30T09:30:00+08:00",
                 "end": "2026-10-30T10:00:00+08:00",
                 "link": "https://meet.google.com/abc"}]
    slack = render([ROW], NOW, [], slack=True, meetings=meetings)
    assert "*Meetings (1)*" in slack
    assert "09:30–10:00 · Eupe catch-up" in slack
    assert "<https://meet.google.com/abc|join>" in slack
    assert slack.index("*Meetings") < slack.index("*Today and tomorrow")
    md = render([ROW], NOW, [], meetings=meetings)
    assert "## Meetings (1)" in md
    assert "[join](https://meet.google.com/abc)" in md


def test_slack_render_uses_slack_markup():
    out = render([ROW], NOW, ["unknown.example"], slack=True)
    assert out.startswith("*Mini-Reid")
    assert "*send the FSD*" in out
    assert "<https://x/1|open>" in out
    assert "## " not in out
    assert "[open](" not in out


def test_inbox_rows_wait_for_confirmation_and_are_counted():
    pending = dict(ROW, id="p1", status="inbox", what="Maybe a task")
    out = render([ROW, pending], NOW, [], slack=True)
    assert "Maybe a task" not in out
    assert "1 to confirm" in out
    assert "send the FSD" in out


def test_notes_get_their_own_section_not_the_task_buckets():
    note = {"id": "n1", "what": "Daniel wants the mapping redone", "kind": "note",
            "status": "open", "due": None, "source_link": "", "direction": "owed_by_me"}
    out = render([note], NOW, [], slack=True)
    assert "*Notes (1)*" in out
    assert "*Today and tomorrow" not in out
    assert "*New since yesterday" not in out


def test_line_shows_person_channel_and_client_name():
    row = dict(ROW, asker="Daniel", via="direct", client="ioi")
    out = render([row], NOW, [], slack=True)
    assert "from Daniel (direct)" in out
    assert "IOI Properties" in out


def test_brief_appears_above_the_sections():
    out = render([ROW], NOW, [], slack=True, brief="Eupe is the urgent one today.")
    assert "*Brief*" in out
    assert out.index("*Brief*") < out.index("*Today and tomorrow")


def test_priority_is_shown_and_sorts_first():
    low = dict(ROW, id="low", what="low focus", due="2026-10-30", priority=3)
    high = dict(ROW, id="high", what="high focus", due="2026-10-30", priority=1)
    out = render([low, high], NOW, [], slack=True)
    assert "[P1] high focus" in out
    assert "[P3] low focus" in out
    assert out.index("[P1] high focus") < out.index("[P3] low focus")


def test_row_shows_in_progress_or_blocked_status():
    row = dict(ROW, status="in progress")
    assert "in progress" in render([row], NOW, [], slack=True)
    row["status"] = "blocked"
    assert "blocked" in render([row], NOW, [], slack=True)


def test_markdown_render_still_uses_markdown():
    out = render([ROW], NOW, [], slack=False)
    assert out.startswith("# Mini-Reid")
    assert "[open](https://x/1)" in out


def test_slack_line_shows_sender_time_and_source_quote():
    row = dict(ROW, source="slack", asker="Kasib", via="DM",
               what="Get Gamuda file",
               evidence="Hi @Ridha, I'm starting K1 now (provider-neutral extractor).",
               created_at="2026-11-01T02:14:48+08:00")
    out = render([row], NOW, [], slack=True)
    assert "from Kasib (DM)" in out
    assert "01 Nov 02:14" in out
    assert "starting K1 now" in out
    assert "<https://x/1|open>" in out
