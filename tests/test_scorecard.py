from mini_reid.scorecard import element_match, match, parse_expected


def test_expected_line_parses_manual_matches():
    text, alts = parse_expected(
        "Eupe platform updates | matches: eupe dashboard; eupe scope")
    assert text == "Eupe platform updates"
    assert alts == ["eupe dashboard", "eupe scope"]


def test_element_match_uses_half_the_keywords():
    row = {"what": "Prioritise December 2025 for 2025 data points"}
    assert element_match("Knight Frank December 2025 data points fixes", row)
    assert not element_match("IOI Entity Restructuring", row)


def test_match_counts_wording_elements_and_overrides():
    rows = [
        {"what": "Share Eupe dashboard handover pack"},
        {"what": "Prioritise December 2025 for 2025 data points"},
        {"what": "Review employment contract"},
    ]
    expected = [
        "Eupe platform updates | matches: eupe dashboard",
        "Knight Frank December 2025 data points fixes",
        "Review employment contract from Arman",
        "IOI Entity Restructuring",
    ]
    result = match(expected, rows)
    assert result["hit"] == 3
    assert result["how"]["override"] == 1
    assert sum(result["how"].values()) == 3
    assert result["missed"] == ["IOI Entity Restructuring"]


def test_element_match_does_not_match_ioipg_for_ioi():
    row = {"what": "Replicate KPI items for IOIPG December data collection"}
    assert not element_match("IOI Entity Restructuring", row)
