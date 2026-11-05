import json
import zipfile
from io import BytesIO

from mini_reid.files import extract_text, search


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
