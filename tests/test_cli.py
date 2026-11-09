"""The daily CLI run must not reopen or restamp existing ledger rows."""
from mini_reid.cli import triage_incoming


def test_existing_inbox_row_stays_inbox_without_capture_keys():
    old = {"id": "a", "status": "inbox"}
    incoming = [{"id": "a", "status": "open",
                 "capture": "auto", "capture_why": "jira-assigned"}]
    out = triage_incoming(incoming, [old])
    assert out[0]["status"] == "inbox"
    assert "capture" not in out[0]
    assert "capture_why" not in out[0]


def test_new_auto_row_opens():
    out = triage_incoming([{"id": "b", "status": "open", "capture": "auto",
                            "capture_why": "slack-direct-ask"}], [])
    assert out[0]["status"] == "open"


def test_new_uncertain_row_waits_in_inbox():
    out = triage_incoming([{"id": "c", "status": "open", "capture": "inbox",
                            "capture_why": ""}], [])
    assert out[0]["status"] == "inbox"


def test_manual_row_without_capture_stays_open():
    out = triage_incoming([{"id": "d", "status": "open"}], [])
    assert out[0]["status"] == "open"
