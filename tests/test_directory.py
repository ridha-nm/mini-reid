from mini_reid.directory import _match, lookup


def test_matches_jira_short_display_name():
    member = {"name": "charanya", "real_name": "Charanya Nair",
              "display_name": ""}
    found = _match(member, [
        {"active": True, "displayName": "charanya",
         "emailAddress": "charanya@pantas.com", "accountId": "1"},
        {"active": False, "displayName": "Charanya Nair",
         "emailAddress": "old@pantas.com", "accountId": "2"},
    ])
    assert found["accountId"] == "1"


def test_missing_directory_returns_empty(tmp_path):
    assert lookup("U1", str(tmp_path / "nope.json")) == {}
