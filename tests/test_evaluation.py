import pytest

from mini_reid.evaluation import (extracted_from_ledger, labels_from_ledger,
                                  labels_from_self_dm, load_labels, main,
                                  score, task_matches)


def test_task_matches_accepts_a_more_specific_extracted_title():
    assert task_matches("send the deck", "send the deck to Eupe by Friday")


def test_task_matches_rejects_unrelated_text():
    assert not task_matches("send the deck", "review the dashboard")


def test_task_matches_ignores_case_and_punctuation():
    assert task_matches("Review EUPE dashboard", "review the eupe dashboard")


def test_load_labels_rejects_a_row_without_is_task(tmp_path):
    path = tmp_path / "labels.jsonl"
    path.write_text('{"date": "2026-11-05", "text": "send the deck"}\n')
    with pytest.raises(ValueError):
        load_labels(str(path))


def test_score_finds_a_covered_positive_and_a_false_task():
    labels = [
        {"date": "2026-11-05", "text": "send the deck", "is_task": True, "id": ""},
        {"date": "2026-11-05", "text": "review the dashboard", "is_task": True, "id": ""},
        {"date": "2026-11-05", "text": "random chatter", "is_task": False, "id": "x1"},
    ]
    extracted = [
        {"date": "2026-11-05", "text": "send the deck to Eupe", "status": "open", "id": "e1"},
        {"date": "2026-11-05", "text": "random chatter", "status": "open", "id": "x1"},
    ]
    result = score(labels, extracted)
    assert result["recall"] == 0.5
    assert result["false_tasks"] == 1
    assert result["false_per_day"] == 1.0
    assert result["meets_target"] is False


def test_score_does_not_count_a_dropped_extracted_row_as_a_task():
    labels = [{"date": "2026-11-05", "text": "noise", "is_task": False, "id": "x1"}]
    extracted = [{"date": "2026-11-05", "text": "noise", "status": "dropped", "id": "x1"}]
    result = score(labels, extracted)
    assert result["false_tasks"] == 0
    assert result["meets_target"] is False


def test_score_handles_empty_labels():
    result = score([], [])
    assert result["recall"] is None
    assert result["meets_target"] is False


def test_self_dm_lines_become_positive_labels():
    messages = [{"ts": "1793866425.785539",
                 "text": "• send the deck\n☐ review the dashboard\n"}]
    labels = labels_from_self_dm(messages)
    assert [l["text"] for l in labels] == ["send the deck", "review the dashboard"]
    assert all(l["is_task"] is True for l in labels)
    assert labels[0]["date"] == "2026-11-05"


def test_ledger_dismissals_become_negative_labels_and_predictions():
    rows = [
        {"id": "a1", "what": "noise", "status": "dropped",
         "closed_how": "not_commitment", "created_at": "2026-11-05T09:00:00+08:00"},
        {"id": "a2", "what": "real task", "status": "open",
         "created_at": "2026-11-05T10:00:00+08:00"},
        {"id": "a3", "what": "a note", "kind": "note", "status": "open",
         "created_at": "2026-11-05T11:00:00+08:00"},
    ]
    assert labels_from_ledger(rows) == [{
        "id": "a1", "date": "2026-11-05", "text": "noise", "is_task": False,
        "source": "dismissed"}]
    extracted = extracted_from_ledger(rows)
    assert [r["id"] for r in extracted] == ["a1", "a2"]


def test_cli_writes_a_report_and_fails_below_target(tmp_path):
    self_dm = tmp_path / "self_dm.json"
    self_dm.write_text('{"messages": [{"ts": "1793866425.785539", '
                       '"text": "send the deck"}]}')
    ledger = tmp_path / "ledger.json"
    ledger.write_text("[]")
    out = tmp_path / "report.md"
    code = main(["--self-dm", str(self_dm), "--ledger", str(ledger),
                 "--out", str(out)])
    assert code == 1
    text = out.read_text()
    assert "Recall" in text and "0.0%" in text
