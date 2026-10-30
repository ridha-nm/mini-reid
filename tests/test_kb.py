from mini_reid.kb import chunk, cosine


def test_chunk_splits_with_overlap():
    parts = chunk("a" * 2000, size=800, overlap=100)
    assert len(parts) >= 3
    assert all(len(p) <= 800 for p in parts)


def test_chunk_unescapes_entities():
    assert "daniel.sim@eupe.com.my" in chunk("To: Daniel &lt;daniel.sim@eupe.com.my&gt;")[0]


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


def test_failed_source_keeps_previous_passages(monkeypatch, tmp_path):
    from mini_reid import kb

    monkeypatch.setattr(kb, "embed", lambda text: [1.0, 0.0])
    monkeypatch.setattr(kb, "local_docs", lambda roots: [])
    monkeypatch.setattr(kb, "slack_sent_docs", lambda token, limit=300: (_ for _ in ()).throw(RuntimeError("down")))
    existing = [{"source": "slack", "title": "old", "link": "l", "text": "keep me", "vec": [1.0, 0.0]}]

    out = kb.build([], {"SLACK_USER_TOKEN": "x"}, use_gmail=False, existing=existing)

    assert len(out) == 1 and out[0]["text"] == "keep me"


def test_cosine_identical_is_one():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_orthogonal_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
