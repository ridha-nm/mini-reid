from mini_reid.unfurl import find_task, task_blocks, unknown_blocks


def test_find_task_matches_the_source_link_across_ledgers():
    owner = [{"id": "a", "what": "Eupe item",
              "source_link": "https://mail.google.com/mail/u/0/#all/1"}]
    member = [{"id": "b", "what": "Gamuda item",
               "source_link": "https://pantas.atlassian.net/browse/GD-7"}]
    ledgers = [("U0OWNER", owner), ("U0MEMBER", member)]
    assert find_task(ledgers, "https://mail.google.com/mail/u/0/#all/1") == (
        "U0OWNER", owner[0])
    assert find_task(
        ledgers, "https://pantas.atlassian.net/browse/GD-7") == (
        "U0MEMBER", member[0])
    assert find_task(ledgers, "https://mail.google.com/mail/u/0/#all/2") is None


def test_blank_links_never_match():
    rows = [{"id": "a", "what": "no link"}]
    assert find_task([("U0OWNER", rows)], "") is None


def test_task_blocks_show_status_and_owner_tagged_done_button():
    blocks = task_blocks({"id": "a", "what": "Eupe item", "status": "open",
                          "due": "2026-11-06"}, user="U0MEMBER")
    text = str(blocks)
    assert "Eupe item" in text
    assert "open" in text and "2026-11-06" in text
    assert "unfurl_done" in text and "U0MEMBER:a" in text


def test_unknown_link_says_it_is_not_tracked():
    assert "not on your list" in str(unknown_blocks())


def test_done_task_has_no_button():
    blocks = task_blocks({"id": "a", "what": "Eupe item", "status": "done"},
                         user="U0MEMBER")
    assert "unfurl_done" not in str(blocks)
