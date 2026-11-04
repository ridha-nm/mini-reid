from mini_reid import learning


def test_add_and_read_back(tmp_path, monkeypatch):
    p = str(tmp_path / "corrections.json")
    monkeypatch.setattr(learning, "PATH", p)
    learning.add("anything that is not part c", reason="thread chatter")
    assert learning.ignored_examples() == ["anything that is not part c"]


def test_missing_file_is_empty(tmp_path):
    assert learning.load(str(tmp_path / "nope.json")) == []


def test_remember_and_accepted_texts(tmp_path):
    p = str(tmp_path / "learning_events.json")
    learning.remember("pls send the deck by friday", "add", "U1", path=p)
    learning.remember("hi", "unknown", "U1", path=p)
    assert learning.accepted_texts(path=p) == ["pls send the deck by friday"]
