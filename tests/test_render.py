from datetime import datetime, timedelta, timezone

from mini_reid.render import render

MYT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 30, 9, 0, tzinfo=MYT)

ROW = {"id": "a", "what": "send the FSD", "due": "2026-10-30", "status": "open",
       "source_link": "https://x/1", "client": "gamuda", "direction": "owed_by_me"}


def test_slack_render_uses_slack_markup():
    out = render([ROW], NOW, ["unknown.example"], slack=True)
    assert out.startswith("*Mini-Reid")
    assert "*send the FSD*" in out
    assert "<https://x/1|open>" in out
    assert "## " not in out
    assert "[open](" not in out


def test_notes_get_their_own_section_not_the_task_buckets():
    note = {"id": "n1", "what": "Daniel wants the mapping redone", "kind": "note",
            "status": "open", "due": None, "source_link": "", "direction": "owed_by_me"}
    out = render([note], NOW, [], slack=True)
    assert "*Notes (1)*" in out
    assert "*Today and tomorrow" not in out
    assert "*New since yesterday" not in out


def test_brief_appears_above_the_sections():
    out = render([ROW], NOW, [], slack=True, brief="Eupe is the urgent one today.")
    assert "*Brief*" in out
    assert out.index("*Brief*") < out.index("*Today and tomorrow")


def test_markdown_render_still_uses_markdown():
    out = render([ROW], NOW, [], slack=False)
    assert out.startswith("# Mini-Reid")
    assert "[open](https://x/1)" in out
