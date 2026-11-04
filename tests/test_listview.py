from datetime import datetime, timedelta, timezone

from mini_reid.listview import format_list, ordered_rows

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 4, 10, 0, tzinfo=MYT)


def _row(rid, what, **kw):
    row = {"id": rid, "what": what, "status": "open"}
    row.update(kw)
    return row


def test_ordered_rows_groups_by_status_then_due():
    rows = [
        _row("later", "Later thing", due="2026-11-20"),
        _row("today", "Today thing", due="2026-11-04"),
        _row("progress", "In progress thing", status="in progress"),
        _row("overdue", "Overdue thing", due="2026-11-01"),
    ]
    assert [r["id"] for r in ordered_rows(rows, NOW)] == [
        "progress", "overdue", "today", "later"]


def test_list_prefers_the_distilled_action_over_the_raw_text():
    rows = [_row("a1", "raw email subject", action="Reply to Bazil re Dec points")]
    text = format_list(rows, NOW)
    assert "Reply to Bazil re Dec points" in text
    assert "raw email subject" not in text


def test_list_groups_have_headers_and_stable_numbers():
    rows = [
        _row("a1", "Overdue thing", due="2026-11-01"),
        _row("b2", "Today thing", due="2026-11-04"),
        _row("c3", "Undated thing"),
    ]
    text = format_list(rows, NOW)
    assert "Overdue" in text and "Due today" in text and "No date" in text
    assert "1. [a1]" in text
    assert "2. [b2]" in text
    assert "3. [c3]" in text


def test_inbox_items_are_separated_and_not_numbered():
    rows = [
        _row("task1", "Real task"),
        _row("maybe1", "Maybe a task", status="inbox"),
    ]
    text = format_list(rows, NOW)
    assert "Inbox — needs decision (1)" in text
    assert "[maybe1]" in text
    assert "2. [maybe1]" not in text


def test_list_hides_notes_done_and_dropped():
    rows = [
        _row("n1", "a note", kind="note"),
        _row("d1", "done task", status="done"),
        _row("x1", "dropped task", status="dropped"),
    ]
    assert format_list(rows, NOW) == "Nothing open."


def test_due_dates_read_relative():
    rows = [
        _row("late", "Overdue thing", due="2026-11-01"),
        _row("today", "Today thing", due="2026-11-04"),
        _row("soon", "Soon thing", due="2026-11-06"),
    ]
    text = format_list(rows, NOW)
    assert "3d overdue" in text
    assert "today" in text.lower()
    assert "in 2d" in text


def test_list_line_shows_client_and_priority():
    rows = [_row("a1", "Send the deck", client="eupe", priority=1)]
    line = format_list(rows, NOW)
    assert "Eupe" in line
    assert "P1" in line
