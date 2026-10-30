from mini_reid.closure import propose_closures


def row(**kw):
    base = {"id": "a", "what": "Confirm Eupe waste mapping categories", "status": "open",
            "closure": "open", "source_link": "https://x/1"}
    base.update(kw)
    return base


def test_proposes_when_sent_mail_matches():
    sent = [("Hi Daniel, the waste mapping categories are confirmed and updated.", "https://x/sent")]
    out = propose_closures([row()], sent)
    assert out[0]["closure"] == "proposed"
    assert out[0]["closure_evidence"] == "https://x/sent"


def test_does_not_close_anything():
    sent = [("waste mapping categories confirmed", "https://x/sent")]
    out = propose_closures([row()], sent)
    assert out[0]["status"] == "open"


def test_unrelated_sent_mail_proposes_nothing():
    sent = [("lunch order for friday", "https://x/sent")]
    assert propose_closures([row()], sent)[0]["closure"] == "open"


def test_done_rows_are_untouched():
    sent = [("waste mapping categories confirmed", "https://x/sent")]
    out = propose_closures([row(status="done")], sent)
    assert out[0].get("closure") == "open"
