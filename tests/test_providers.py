from datetime import datetime, timedelta, timezone

import pytest

from mini_reid.providers import extract_batch

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)
ITEMS = [{"source": "slack", "native_id": "D1:1", "kind": "mention", "author": "kasib",
          "text": "get FSD today", "link": "l", "ts": "2026-10-30T08:00:00+08:00"}]


class Stub:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def complete(self, prompt: str) -> dict:
        self.calls += 1
        return self.data


def test_builds_rows_from_model_output():
    stub = Stub({"items": [{"id": "D1:1", "is_commitment": True,
                            "what": "get FSD to Kasib", "due": "2026-10-30", "client": None}]})
    rows = extract_batch(ITEMS, stub, NOW)
    assert len(rows) == 1
    assert rows[0]["what"] == "get FSD to Kasib"
    assert rows[0]["due"] == "2026-10-30"
    assert stub.calls == 1


def test_one_call_for_many_items():
    items = ITEMS * 5
    items = [dict(i, native_id=f"D1:{n}") for n, i in enumerate(items)]
    stub = Stub({"items": [{"id": i["native_id"], "is_commitment": True,
                            "what": "x", "due": None, "client": None} for i in items]})
    assert len(extract_batch(items, stub, NOW)) == 5
    assert stub.calls == 1


def test_non_commitment_is_dropped():
    stub = Stub({"items": [{"id": "D1:1", "is_commitment": False, "what": "", "due": None}]})
    assert extract_batch(ITEMS, stub, NOW) == []


class SplitStub:
    """Fails whenever more than one item is sent, succeeds on a single item."""

    def complete(self, prompt: str) -> dict:
        import re

        ids = re.findall(r'"id": "(X\d+)"', prompt)
        if len(ids) > 1:
            raise ValueError("bad json")
        return {"items": [{"id": ids[0], "is_commitment": True,
                           "what": f"task {ids[0]}", "due": None, "client": None}]}


def test_bad_batch_splits_until_every_item_is_recovered():
    from mini_reid.providers import extract_batch_safe

    items = [dict(ITEMS[0], native_id=f"X{n}") for n in range(4)]
    rows, failed = extract_batch_safe(items, SplitStub(), NOW)
    assert failed == []
    assert len(rows) == 4


def test_malformed_output_raises():
    with pytest.raises(ValueError):
        extract_batch(ITEMS, Stub({"nope": True}), NOW)
