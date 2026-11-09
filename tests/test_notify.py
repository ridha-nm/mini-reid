from mini_reid.notify import as_blocks


def test_short_text_is_left_alone():
    assert as_blocks("one line") is None


def test_long_text_becomes_one_block_message():
    blocks = as_blocks("\n".join(f"row {i} padded out" for i in range(1000)))
    assert blocks and len(blocks) <= 50
    assert all(len(b["text"]["text"]) <= 2900 for b in blocks)
