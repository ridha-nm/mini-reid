from mini_reid.kb import chunk, cosine


def test_chunk_splits_with_overlap():
    parts = chunk("a" * 2000, size=800, overlap=100)
    assert len(parts) >= 3
    assert all(len(p) <= 800 for p in parts)


def test_chunk_of_empty_is_empty():
    assert chunk("   ") == []


def test_cosine_identical_is_one():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_orthogonal_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
