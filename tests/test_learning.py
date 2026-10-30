from mini_reid import learning


def test_add_and_read_back(tmp_path, monkeypatch):
    p = str(tmp_path / "corrections.json")
    monkeypatch.setattr(learning, "PATH", p)
    learning.add("anything that is not part c", reason="thread chatter")
    assert learning.ignored_examples() == ["anything that is not part c"]


def test_missing_file_is_empty(tmp_path):
    assert learning.load(str(tmp_path / "nope.json")) == []
