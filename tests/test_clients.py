import pytest

from mini_reid.clients import load_clients, match_client


@pytest.fixture(scope="module")
def c():
    return load_clients("clients.json")


def test_matches_domain(c):
    m = match_client("x", "daniel.hwang@ioiproperties.com.my", c)
    assert (m["slug"], m["matched_by"]) == ("ioi", "domain")


def test_matches_subdomain_domain(c):
    m = match_client("x", "a@gamudaland.com.my", c)
    assert m["slug"] == "gamuda"


def test_matches_client_name_under_shared_alias(c):
    m = match_client("Eupe waste migration confirmation", "bd@pantas.com", c)
    assert (m["slug"], m["matched_by"]) == ("eupe", "text")


def test_matches_slack_channel(c):
    m = match_client("hi", "", c, channel="ioi-properties-working-group")
    assert (m["slug"], m["matched_by"]) == ("ioi", "channel")


def test_srsl_domain_maps_to_gamuda(c):
    m = match_client("x", "wanadlinamira@srslrt.com.my", c)
    assert (m["slug"], m["matched_by"]) == ("gamuda", "domain")


def test_client_domain_inside_text_is_matched(c):
    m = match_client("Forwarded thread from daniel@eupe.com.my about waste",
                     "someone@unknown.example", c)
    assert m["slug"] == "eupe"
    assert m["matched_by"] in {"text", "domain_in_text"}


def test_unknown_domain_is_none(c):
    assert match_client("hello", "someone@unknown.example", c) is None


def test_short_alias_does_not_match_inside_a_word(c):
    # "pos" must not match "purpose", "IOI" must not match "oioi"
    assert match_client("purpose built", "x@unknown.example", c) is None
