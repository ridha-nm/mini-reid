import json

from mini_reid.accounts import OVERRIDES, build, clients_for


def test_charanya_override():
    assert clients_for("Charanya@pantas.com") == [
        "knight-frank", "allianz", "setia", "eupe"]
    assert OVERRIDES["charanya@pantas.com"] == [
        "knight-frank", "allianz", "setia", "eupe"]


def test_build_maps_hub_members(tmp_path):
    source = tmp_path / "config.json"
    source.write_text(json.dumps({"clients": {
        "setia": {"members": ["a@pantas.com", "b@pantas.com"]},
        "allianz": {"members": ["a@pantas.com"]},
        "safe": {"members": ["a@pantas.com"]},
    }}))
    out = tmp_path / "accounts.json"
    people = build(str(source), str(out))
    assert people["a@pantas.com"] == ["allianz", "safe", "setia"]
    assert people["b@pantas.com"] == ["setia"]
    assert json.loads(out.read_text())["a@pantas.com"] == [
        "allianz", "safe", "setia"]
