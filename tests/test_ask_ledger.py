from mini_reid.ask_ledger import answer_ledger, client_hits

CLIENTS = {"gamuda": {"name": "Gamuda"}, "eupe": {"name": "Eupe"}}


def _row(rid, what, client, **kw):
    row = {"id": rid, "what": what, "client": client, "status": "open"}
    row.update(kw)
    return row


def test_open_items_question_answers_from_the_ledger():
    rows = [_row("a", "Send the deck", "gamuda", due="2026-11-06"),
            _row("b", "Eupe item", "eupe")]
    text = answer_ledger("do I have pending items with gamuda", rows, CLIENTS)
    assert "1 pending with Gamuda" in text
    assert "Send the deck" in text
    assert "Eupe item" not in text


def test_general_question_does_not_hit_the_ledger():
    assert answer_ledger("what did we agree with Eupe on waste", [], CLIENTS) is None


def test_missing_client_returns_a_clear_no_items_line():
    assert answer_ledger("any pending items for gamuda", [], CLIENTS) == (
        "No pending items with Gamuda.")


def test_client_detection_accepts_slug_and_name():
    assert client_hits("pending eupe items", CLIENTS) == ["eupe"]
    assert client_hits("pending gamuda items", CLIENTS) == ["gamuda"]
