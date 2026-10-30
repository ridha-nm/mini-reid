from datetime import datetime, timedelta, timezone

from mini_reid.ledger import apply_stalled, commitment_id, merge

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)


def row(**kw):
    base = {
        "id": "x",
        "status": "open",
        "due": None,
        "kind": "mention",
        "created_at": "2026-10-29T09:00:00+08:00",
        "last_activity": "2026-10-29T09:00:00+08:00",
    }
    base.update(kw)
    return base


def test_id_ignores_case_and_punctuation():
    assert commitment_id("slack", "1", "Send the FSD.") == commitment_id(
        "slack", "1", "send  the fsd"
    )


def test_id_changes_with_source_id():
    assert commitment_id("slack", "1", "x") != commitment_id("gmail", "1", "x")


def test_merge_is_idempotent():
    r = row(id="a")
    assert len(merge(merge([], [r]), [r])) == 1


def test_done_never_reopens():
    done = row(id="a", status="done")
    assert merge([done], [row(id="a", status="open")])[0]["status"] == "done"


def test_merge_keeps_original_created_at():
    old = row(id="a", created_at="2026-10-01T09:00:00+08:00")
    new = row(id="a", created_at="2026-10-29T09:00:00+08:00")
    assert merge([old], [new])[0]["created_at"] == "2026-10-01T09:00:00+08:00"


def test_dedupe_by_link_keeps_one_row_per_message():
    from mini_reid.ledger import dedupe_by_link

    a = row(id="a", source_link="https://x/1", created_at="2026-10-30T08:00:00+08:00")
    b = row(id="b", source_link="https://x/1", created_at="2026-10-30T09:00:00+08:00")
    out = dedupe_by_link([a, b])
    assert len(out) == 1 and out[0]["id"] == "b"


def test_dedupe_by_link_keeps_done_row():
    from mini_reid.ledger import dedupe_by_link

    a = row(id="a", source_link="https://x/1", status="done")
    b = row(id="b", source_link="https://x/1", status="open")
    assert dedupe_by_link([a, b])[0]["id"] == "a"


def test_draft_older_than_one_day_is_stalled():
    out = apply_stalled([row(kind="draft", created_at="2026-10-29T08:00:00+08:00")], NOW)
    assert out[0]["status"] == "stalled"
    assert out[0]["stalled_reason"] == "draft_older_than_one_day"


def test_fresh_draft_is_not_stalled():
    out = apply_stalled([row(kind="draft", created_at="2026-10-29T10:00:00+08:00")], NOW)
    assert out[0]["status"] == "open"


def test_past_due_is_stalled():
    out = apply_stalled([row(due="2026-10-29")], NOW)
    assert out[0]["status"] == "stalled"
    assert out[0]["stalled_reason"] == "past_due"


def test_due_today_is_not_stalled():
    out = apply_stalled([row(due="2026-10-30")], NOW)
    assert out[0]["status"] == "open"


def test_no_activity_for_five_working_days_is_stalled():
    out = apply_stalled([row(last_activity="2026-10-23T09:00:00+08:00")], NOW)
    assert out[0]["status"] == "stalled"
    assert out[0]["stalled_reason"] == "no_activity"
