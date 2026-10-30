from mini_reid.scorecard import match

ROWS = [
    {"what": "Confirm Eupe waste mapping categories"},
    {"what": "Send FSD to Kasib"},
]


def test_match_counts_hits_and_misses():
    r = match(["Confirm Eupe waste mapping categories", "Book the SFF flights"], ROWS)
    assert r["total"] == 2
    assert r["hit"] == 1
    assert r["recall"] == 0.5
    assert r["missed"] == ["Book the SFF flights"]


def test_paraphrase_still_matches():
    r = match(["confirm waste mapping categories for Eupe"], ROWS)
    assert r["hit"] == 1


def test_empty_expected_is_zero_not_crash():
    assert match([], ROWS)["recall"] == 0.0
