import json
import zipfile
from io import BytesIO

from mini_reid.files import ack_messages, extract_text, search, summarize


def test_summary_goes_to_the_owner_only():
    record = {"name": "deck.pdf", "summary": "The deck covers pricing."}
    msgs = dict(ack_messages("U2", "U1", [record]))
    assert "pricing" not in msgs["U2"]
    assert "deck.pdf" in msgs["U2"]
    assert "pricing" in msgs["U1"]
    assert "ask:" in msgs["U1"]


def test_owner_upload_gets_one_summary_message():
    record = {"name": "deck.pdf", "summary": "The deck covers pricing."}
    msgs = ack_messages("U1", "U1", [record])
    assert len(msgs) == 1
    assert "pricing" in msgs[0][1]


def test_summary_keeps_whole_sentences_within_the_limit():
    text = "First sentence. Second sentence with detail. " + "Filler " * 100
    summary = summarize(text)
    assert summary.startswith("First sentence. Second sentence")
    assert len(summary) <= 280


def test_extracts_plain_text_and_markdown():
    assert "hello" in extract_text("note.txt", b"hello world")
    assert "deck" in extract_text("brief.md", b"# deck")


def test_extracts_docx_text():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml",
                         "<w:document><w:t>Interview checklist</w:t></w:document>")
    assert "Interview checklist" in extract_text("a.docx", buffer.getvalue())


def test_unknown_file_type_is_skipped():
    assert extract_text("photo.png", b"\x89PNG") == ""


def test_search_finds_a_saved_file_and_snippet(tmp_path):
    (tmp_path / "f1_close_the_deal.txt").write_text(
        "The close the deal checklist covers pricing and legal review.")
    (tmp_path / "f1.json").write_text(json.dumps(
        {"name": "checklist.txt", "permalink": "https://slack/x"}))
    hits = search("what is in the close the deal checklist", str(tmp_path))
    assert hits and hits[0]["name"] == "checklist.txt"
    assert hits[0]["permalink"] == "https://slack/x"
    assert "pricing" in hits[0]["text"]


def test_search_needs_two_words(tmp_path):
    (tmp_path / "a.txt").write_text("deck review")
    assert search("deck", str(tmp_path)) == []


def test_generic_file_question_returns_the_latest_ingest(tmp_path):
    (tmp_path / "old.json").write_text(json.dumps(
        {"name": "old.pdf", "summary": "Old summary.", "permalink": "x"}))
    (tmp_path / "new.json").write_text(json.dumps(
        {"name": "new.xlsx", "summary": "Entity structure update.",
         "permalink": "y"}))
    import os
    os.utime(tmp_path / "old.json", (1, 1))
    os.utime(tmp_path / "new.json", (2, 2))
    hits = search("waht is this file about", str(tmp_path))
    assert hits and hits[0]["name"] == "new.xlsx"
    assert "Entity structure" in hits[0]["text"]
