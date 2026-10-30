from datetime import datetime, timedelta, timezone

from mini_reid.watcher import format_alert, new_rows

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)

ITEM = {"source": "gmail", "native_id": "m1", "kind": "inbox", "author": "a@eupe.com.my",
        "text": "please confirm the waste mapping", "link": "https://x/1",
        "ts": "2026-10-30T08:00:00+08:00", "to": "Ridha <ridha@pantas.com>"}


def test_new_rows_skips_ids_already_in_ledger():
    first = new_rows([ITEM], [], {}, NOW)
    assert len(first) == 1
    again = new_rows([ITEM], first, {}, NOW)
    assert again == []


def test_new_rows_skips_rewritten_row_for_same_link():
    first = new_rows([ITEM], [], {}, NOW)
    rewritten = dict(first[0], id="different-id", what="Confirm waste mapping")
    assert new_rows([ITEM], [rewritten], {}, NOW) == []


def test_new_rows_ignores_noise():
    noise = dict(ITEM, author='"Jira" <jira@pantas.atlassian.net>')
    assert new_rows([noise], [], {}, NOW) == []


def test_fire_reminders_sends_once(tmp_path, monkeypatch):
    from mini_reid import watcher as w
    from mini_reid.ledger import save

    sent = []
    monkeypatch.setattr(w, "send_dm", lambda env, text: sent.append(text))
    ledger = str(tmp_path / "ledger.json")
    save(ledger, [{"id": "r1", "kind": "reminder", "what": "send the deck",
                   "remind_at": "2026-10-30T08:00:00+08:00", "reminded": False}])

    assert w.fire_reminders({}, ledger, NOW) == 1
    assert w.fire_reminders({}, ledger, NOW) == 0
    assert len(sent) == 1


def test_alert_is_compact_and_has_a_link():
    rows = new_rows([ITEM], [], {}, NOW)
    text = format_alert(rows)
    assert "confirm the waste mapping" in text
    assert "https://x/1" in text
