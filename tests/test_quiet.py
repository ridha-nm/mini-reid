from mini_reid import quiet


def test_dnd_active_reads_slack_when_enabled(monkeypatch):
    monkeypatch.setattr(quiet, "_get_json",
                        lambda url, headers: {"ok": True, "dnd_enabled": True})
    assert quiet.dnd_active(
        {"SLACK_BOT_TOKEN": "x", "RESPECT_DND": "1"}, "U1") is True


def test_dnd_is_off_by_default(monkeypatch):
    monkeypatch.setattr(quiet, "_get_json",
                        lambda url, headers: {"ok": True, "dnd_enabled": True})
    assert quiet.dnd_active({"SLACK_BOT_TOKEN": "x"}, "U1") is False


def test_dnd_missing_scope_is_not_quiet(monkeypatch):
    monkeypatch.setattr(quiet, "_get_json",
                        lambda url, headers: {"ok": False,
                                              "error": "missing_scope"})
    assert quiet.dnd_active({"SLACK_BOT_TOKEN": "x"}, "U1") is False


def test_dnd_without_token_is_not_quiet():
    assert quiet.dnd_active({}, "U1") is False
