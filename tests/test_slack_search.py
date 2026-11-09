from mini_reid.slack_search import format_hits, search


def test_format_hits_keeps_channel_text_and_link():
    hits = [{"channel_name": "eupe-working-group",
             "content": "We agreed to use weight for waste",
             "permalink": "https://slack/x"}]
    text = format_hits(hits)
    assert "eupe-working-group" in text
    assert "use weight for waste" in text
    assert "<https://slack/x|open>" in text


def test_format_hits_skips_empty_content():
    assert format_hits([{"content": "  ", "permalink": "x"}]) == ""


def test_search_returns_empty_without_a_user_token(monkeypatch):
    assert search({}, "anything") == []
