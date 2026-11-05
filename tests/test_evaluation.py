import pytest

from mini_reid.evaluation import load_labels, task_matches


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
