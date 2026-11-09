import json
from datetime import datetime, timedelta, timezone

from mini_reid import routing
from mini_reid.watcher import route_triager

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 9, 19, 0, tzinfo=MYT)
CARD = (":bulb: *Solution proposed* by <@U1> PHD-1561: Can't access the site "
        "*Requester:* creativlystudiofinance@gmail.com *Organization:* Unmapped "
        "*Assigned to:* <@U029RLGND8D>")


def test_card_fields_parse():
    card = routing.parse_card(CARD)
    assert card["key"] == "PHD-1561"
    assert card["email"] == "creativlystudiofinance@gmail.com"
    assert card["title"].startswith("Can't access the site")


def test_programme_rules():
    assert routing.programme("EXIM Bank (GHB)") == "GHB"
    assert routing.programme("EXIM Bank (GEGI Programme)") == "GHB"
    assert routing.programme("DTI-Spark (Anchor)") == "SAFE"
    assert routing.programme("AmBank Holdings Berhad",
                             {"ambank holdings berhad"}) == "GVC"
    # Gamuda is an enterprise account, not a Lite programme.
    assert routing.programme("Gamuda Bhd", {"ambank holdings berhad"}) == "ENT"


def _msg(text, ts="1794225000.0", app="Demo App"):
    return {"ts": ts, "thread_ts": None, "text": text,
            "bot_profile": {"name": app}}


def test_route_tags_owners_and_falls_back_to_ridha(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "emails": {"aida@omi.com.my": {
            "anchor": "MBM Resources Bhd", "programme": "ENT",
            "owners": ["azleena@pantas.com"]}},
        "domains": {}})
    monkeypatch.setattr(routing, "owner_ids",
                        lambda owners, path="directory.json":
                        ["U074G1N15J9"] if owners == ["azleena@pantas.com"]
                        else ["U0A33EDVAKH"])
    state = tmp_path / "state.json"
    state.write_text('{"since_ts": "1"}')
    posts = []
    route_triager({}, NOW, str(state),
                  post=lambda ch, text, ts: posts.append(text),
                  fetch=lambda oldest: [_msg(CARD)])
    assert posts and "<@U0A33EDVAKH>" in posts[0]     # unmapped -> Ridha


def test_closed_cards_and_other_apps_are_not_routed(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "emails": {}, "domains": {}})
    state = tmp_path / "s.json"
    state.write_text('{"since_ts": "1"}')
    closed = _msg(CARD.replace("*Solution proposed*", "*Closed*"))
    sla = _msg("SLA Breach: PHD-1", ts="1794225001.0")
    other = _msg(CARD, ts="1794225002.0", app="Some Other App")
    posts = []
    route_triager({}, NOW, str(state),
                  post=lambda ch, text, ts: posts.append(text),
                  fetch=lambda oldest: [closed, sla, other])
    assert posts == []


def test_first_card_per_ticket_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "emails": {}, "domains": {}})
    state = tmp_path / "s.json"
    state.write_text('{"since_ts": "1"}')
    posts = []
    ack = _msg(CARD.replace("*Solution proposed*", "*Acknowledged*"),
               ts="1794225000.0")
    proposal = _msg(CARD, ts="1794225005.0")
    route_triager({}, NOW, str(state),
                  post=lambda ch, text, ts: posts.append((text, ts)),
                  fetch=lambda oldest: [ack, proposal])
    assert len(posts) == 1
    assert posts[0][1] == "1794225000.0"     # replies under the ack card


def test_followup_cards_are_never_tagged(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "emails": {}, "domains": {}, "companies": {}})
    state = tmp_path / "s.json"
    state.write_text('{"since_ts": "1"}')
    reply = _msg(":speech_balloon: Ridha Mohamed replied:\nHi there, … "
                 "PHD-1561: Can't access *Requester:* x@y.com *Company:* A")
    posts = []
    route_triager({}, NOW, str(state),
                  post=lambda ch, text, ts: posts.append(text),
                  fetch=lambda oldest: [reply])
    assert posts == []


def test_company_lookup_ignores_generic_names():
    companies = {"pantas trial access (nct alliance)": {"anchor": "X"},
                 "gamuda land leisure sdn bhd": {"anchor": "Gamuda"}}
    assert routing.lookup_company(companies, "Pantas") is None
    assert routing.lookup_company(
        companies, "GAMUDA LAND LEISURE SDN BHD")["anchor"] == "Gamuda"


def test_alias_command_saves_a_route(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "companies": {"gamuda bhd": {"anchor": "Gamuda Bhd",
                                     "programme": "ENT",
                                     "owners": ["ridha@pantas.com"]}}})
    route = routing.add_alias("Horizon Hills Development Sdn Bhd", "Gamuda")
    assert route["anchor"] == "Gamuda Bhd"
    saved = json.loads((tmp_path / routing.ALIASES).read_text())
    assert saved["horizon hills development sdn bhd"]["owners"] == [
        "ridha@pantas.com"]


def test_backlog_is_replayed_but_closed_tickets_are_skipped(
        tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "emails": {}, "domains": {}, "companies": {}})
    state = tmp_path / "s.json"
    state.write_text('{"since_ts": "1"}')
    ack = _msg(CARD.replace("*Solution proposed*", "*Acknowledged*"),
               ts="1794225000.0")
    closed = _msg(CARD.replace("*Solution proposed*", "*Closed*"),
                  ts="1794225100.0")
    posts = []
    route_triager({}, NOW, str(state),
                  post=lambda ch, text, ts: posts.append(text),
                  fetch=lambda oldest: [ack, closed])
    assert posts == []
    assert "PHD-1561" in json.loads(state.read_text())["tickets"]


def test_block_kit_new_ticket_card_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(routing, "ensure_fresh", lambda path=routing.OUT: {
        "emails": {}, "domains": {}, "companies": {}})
    state = tmp_path / "s.json"
    state.write_text('{"since_ts": "1"}')
    blocks = [
        {"type": "header",
         "text": {"type": "plain_text", "text":
                  "PHD-1562: cannot log in, need token but i dont have"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": "*Requester:*\ncomiarico1977@gmail.com"},
            {"type": "mrkdwn", "text": "*Organization:*\nUnmapped"}]},
        {"type": "section", "fields": [
            {"type": "mrkdwn",
             "text": "*Company:*\nMang R Calamansi Juice Processing"}]},
    ]
    message = {"ts": "1794228620.189219", "thread_ts": None,
               "text": "New ticket: PHD-1562", "blocks": blocks,
               "bot_profile": {"name": "Demo App"}}
    posts = []
    route_triager({}, NOW, str(state),
                  post=lambda ch, text, ts: posts.append((text, ts)),
                  fetch=lambda oldest: [message])
    assert posts and posts[0][0].startswith("*PHD-1562*")
    assert posts[0][1] == "1794228620.189219"
