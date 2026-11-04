from datetime import datetime, timedelta, timezone

from mini_reid.profiles import (add_member, issue_setup_token, ledger_for, load,
                                save, token_owner)


def test_member_gets_an_isolated_ledger(tmp_path):
    path = str(tmp_path / "users.json")
    profiles = load(path)
    assert profiles == {}

    add_member(profiles, "UCHARANYA", "Charanya")
    save(profiles, path)

    saved = load(path)
    assert saved["UCHARANYA"]["name"] == "Charanya"
    assert saved["UCHARANYA"]["role"] == "member"
    assert ledger_for(saved, "UCHARANYA", "ledger.json") == (
        "data/UCHARANYA/ledger.json")
    assert ledger_for(saved, "URIDHA", "ledger.json") == "ledger.json"


def test_bad_profiles_file_does_not_crash(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("{not json")
    assert load(str(path)) == {}


def test_setup_token_is_one_time_and_expires():
    profiles = {}
    add_member(profiles, "UCHARANYA", "Charanya")
    token = issue_setup_token(profiles, "UCHARANYA")

    assert token_owner(profiles, token)[0] == "UCHARANYA"
    assert token_owner(profiles, "wrong") is None

    profiles["UCHARANYA"]["setup_expires"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert token_owner(profiles, token) is None
