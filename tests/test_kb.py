from mini_reid.kb import chunk, cosine


def test_chunk_splits_with_overlap():
    parts = chunk("a" * 2000, size=800, overlap=100)
    assert len(parts) >= 3
    assert all(len(p) <= 800 for p in parts)


def test_chunk_of_empty_is_empty():
    assert chunk("   ") == []


def test_rebuild_reuses_cached_vectors(tmp_path, monkeypatch):
    from mini_reid import kb

    calls = []
    monkeypatch.setattr(kb, "embed", lambda text: (calls.append(text) or [1.0, 0.0]))
    doc = tmp_path / "a.md"
    doc.write_text("hello world, this is a document")

    first = kb.build([str(doc)], {}, use_slack=False, use_gmail=False)
    second = kb.build([str(doc)], {}, use_slack=False, use_gmail=False, existing=first)

    assert len(calls) == 1
    assert second[0]["vec"] == first[0]["vec"]


def test_cosine_identical_is_one():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_orthogonal_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
