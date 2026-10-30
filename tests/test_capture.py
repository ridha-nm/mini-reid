from datetime import datetime, timedelta, timezone

from mini_reid.capture import parse_capture
from mini_reid.clients import load_clients

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)


def test_parses_capture_with_client_and_due():
    clients = load_clients("clients.json")
    row = parse_capture("add: Eupe dashboard item by Friday", NOW, clients)
    assert row["client"] == "eupe"
    assert row["due"] == "2026-10-30"
    assert row["source"] == "manual"
    assert row["status"] == "open"


def test_same_text_is_idempotent():
    clients = load_clients("clients.json")
    a = parse_capture("add: send FSD to Kasib", NOW, clients)
    b = parse_capture("add: Send FSD to Kasib.", NOW, clients)
    assert a["id"] == b["id"]


def test_ignores_non_capture_text():
    assert parse_capture("thanks!", NOW, {}) is None
    assert parse_capture("add:", NOW, {}) is None
