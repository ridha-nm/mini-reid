from datetime import datetime, timedelta, timezone

from mini_reid import mutes
from mini_reid.extract import extract

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 9, 9, 0, tzinfo=MYT)


def _row(**kw):
    row = {"source": "slack", "via": "#feature-release", "status": "dropped",
           "closed_how": "not_commitment"}
    row.update(kw)
    return row


def test_channel_that_is_mostly_rejects_gets_muted(tmp_path):
    path = str(tmp_path / "muted.json")
    rows = [_row() for _ in range(3)]
    assert mutes.learn(rows, path) == ["feature-release"]
    assert mutes.is_muted("#feature-release", path)

    # A channel that also yields real tasks is left alone (exactly 75%).
    mixed = [_row(via="#bd-team") for _ in range(3)]
    mixed.append(_row(via="#bd-team", status="open", closed_how=None))
    assert mutes.learn(mixed, path) == []
    # Two rejects are not enough on their own.
    assert mutes.learn([_row(via="#probies") for _ in range(2)], path) == []


def test_muted_channel_is_not_captured(monkeypatch):
    monkeypatch.setattr("mini_reid.mutes.is_muted", lambda key, path=mutes.PATH:
                        key.lstrip("#") == "feature-release")
    item = {"source": "slack", "native_id": "C1:1", "kind": "mention",
            "channel": "feature-release", "author": "deploy status app",
            "text": "can you verify the release notes", "link": "l",
            "ts": NOW.isoformat()}
    assert extract(item, None, NOW) == []
