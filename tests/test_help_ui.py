from mini_reid.help_ui import TOPICS, home_blocks, topic_blocks, topic_text


def test_home_offers_a_topic_picker_and_quick_actions():
    blocks = home_blocks()
    select = [e for b in blocks if b.get("type") == "actions"
              for e in b["elements"] if e.get("action_id") == "help_topic"][0]
    assert [o["value"] for o in select["options"]] == list(TOPICS)
    buttons = [e.get("action_id") for b in blocks if b.get("type") == "actions"
               for e in b["elements"] if e.get("type") == "button"]
    assert buttons == ["help_list", "triage_open"]


def test_every_topic_returns_examples_and_a_back_button():
    for key in TOPICS:
        blocks = topic_blocks(key)
        assert "Back to topics" in str(blocks[-1])
        assert any("`" in b["text"]["text"] for b in blocks
                   if b.get("type") == "section")
        assert topic_text(key).startswith(f"*{TOPICS[key][0]}*")


def test_unknown_topic_falls_back_instead_of_breaking():
    assert topic_text("nope") == topic_text("capture")
