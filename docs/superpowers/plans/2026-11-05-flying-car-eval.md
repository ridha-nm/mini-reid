# Flying-car Ground Truth and Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure Mini-Reid's capture against Charanya's own Slack to-do list and its dismissal history, so every later flying-car subsystem has a baseline number.

**Architecture:** A pure Python evaluation module loads labels and extracted rows, matches task text with normalised token overlap, and reports recall plus false tasks per day. A CLI builds labels from a self-DM export and a member ledger, then writes a Markdown report.

**Tech Stack:** Python 3.15, stdlib only, existing `mini_reid.ledger`, existing pytest suite.

**Spec:** `docs/superpowers/specs/2026-11-05-flying-car-design.md`

## Global Constraints

- Python 3.15, existing `.venv`; add no dependencies.
- Pure functions; no network in the evaluation module or tests.
- Personal data lives under `data/eval/`, which is gitignored. Tests use `tmp_path`.
- One acceptance target: recall 95% or more, fewer than 1 false task per day.
- No em-dashes in user-facing report text.

## Review Focus

- A self-DM line with emoji, checkbox or numbering must become a clean task label.
- Two labels on the same day, one extracted, must deduct the miss, not inflate recall.
- Duplicate extracted rows must count once.
- A dismissed row with no id must be ignored, not counted as a false task.
- Empty labels or empty extracted rows must produce a report without division by zero.

---

### Task 1: Label loading and task matching

**Files:**
- Create: `mini_reid/evaluation.py`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `mini_reid.ledger.normalize_what(str) -> str`
- Produces: `load_labels(path: str) -> list[dict]`, `task_tokens(text: str) -> set[str]`, `task_matches(label: str, extracted: str, threshold: float = 0.8) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -v`
Expected: FAIL with `ImportError` or `NameError`.

- [ ] **Step 3: Implement in `mini_reid/evaluation.py`**

```python
def load_labels(path: str) -> list[dict]
def task_tokens(text: str) -> set[str]
def task_matches(label: str, extracted: str, threshold: float = 0.8) -> bool
```

`task_tokens` uses `normalize_what` then splits on spaces and drops tokens shorter than 2 characters. `task_matches` returns True when Jaccard overlap is at or above `threshold`, or when the smaller token set is a subset of the larger and has at least 3 tokens. `load_labels` reads JSONL and raises `ValueError` when `date`, `text` or `is_task` is missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/evaluation.py tests/test_evaluation.py
git commit -m "feat: evaluation label loading and task matching"
```

---

### Task 2: Scoring recall and false tasks

**Files:**
- Modify: `mini_reid/evaluation.py`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `task_matches`, `load_labels`
- Produces: `score(labels: list[dict], extracted: list[dict], threshold: float = 0.8) -> dict`

`labels` rows: `{date, text, is_task, id?}`. `extracted` rows: `{date, text, status, id}`. A predicted task is any extracted row whose status is not `done` or `dropped`.

- [ ] **Step 1: Write the failing tests**

```python
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
    assert result["meets_target"] is True


def test_score_handles_empty_labels():
    result = score([], [])
    assert result["recall"] is None
    assert result["meets_target"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -k score -v`
Expected: FAIL with `NameError: score`.

- [ ] **Step 3: Implement `score`**

Return exactly these keys: `positives`, `covered`, `recall`, `false_tasks`, `reviewed`, `false_per_day`, `misses`, `false_examples`, `meets_target`. `misses` is the text of uncovered positive labels, at most 20. `false_examples` is the text of false negatives, at most 20. Deduplicate extracted by `id`. Negative labels without an `id` are skipped. `meets_target` is `recall is not None and recall >= 0.95 and false_per_day < 1.0`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/evaluation.py tests/test_evaluation.py
git commit -m "feat: score capture recall and false tasks"
```

---

### Task 3: Build labels from self-DM and ledger

**Files:**
- Modify: `mini_reid/evaluation.py`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Produces: `labels_from_self_dm(messages: list[dict]) -> list[dict]`, `labels_from_ledger(rows: list[dict]) -> list[dict]`, `extracted_from_ledger(rows: list[dict]) -> list[dict]`

Self-DM message shape: `{"ts": "1793866425.785539", "text": "• send the deck\n☐ review dashboard"}`. Ledger rows are existing `ledger.json` rows.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -k "self_dm or ledger" -v`
Expected: FAIL with `NameError`.

- [ ] **Step 3: Implement**

`labels_from_self_dm` strips `•`, `*`, `-`, `[ ]`, `[x]`, numbered prefixes, and surrounding whitespace. It skips lines shorter than 3 characters. Date comes from `datetime.fromtimestamp(float(ts), MYT).date().isoformat()`, with `MYT` as `timezone(timedelta(hours=8))`.

`labels_from_ledger` keeps rows where `status == "dropped"` and `closed_how == "not_commitment"`, excludes `kind` in `{"note", "reminder"}`, and emits the negative label shape above.

`extracted_from_ledger` excludes `kind` in `{"note", "reminder"}`, uses `action` when present else `what`, date from `created_at`, and status as given.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/evaluation.py tests/test_evaluation.py
git commit -m "feat: build eval labels from self-DM and ledger"
```

---

### Task 4: CLI report and Charanya runbook

**Files:**
- Modify: `mini_reid/evaluation.py`
- Create: `docs/EVAL.md`
- Modify: `.gitignore`
- Test: `tests/test_evaluation.py`

**Interfaces:**
- Produces: `format_report(result: dict) -> str`, `main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: Write the failing test**

```python
def test_cli_writes_a_report_and_fails_below_target(tmp_path, monkeypatch):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -k cli -v`
Expected: FAIL with `NameError: main`.

- [ ] **Step 3: Implement**

`main` parses `--self-dm`, `--ledger`, `--out`, `--labels`, `--extracted`. When `--labels` and `--extracted` are given, load them. Otherwise require `--self-dm` and `--ledger`, build both lists, and score. `format_report` prints rows for date, positives, covered, recall as a percentage, false tasks, reviewed dismissals, false per day, verdict, misses and false examples. Write the report to `--out`, print it, and return `0` when `meets_target` is true else `1`.

Add a `if __name__ == "__main__": raise SystemExit(main())` block.

`.gitignore` must include `data/eval/`.

`docs/EVAL.md` documents the exact Charanya run:

```bash
mkdir -p data/eval
# Save a Slack JSON export of Charanya's self-DM to data/eval/self_dm.json
.venv/bin/python -m mini_reid.evaluation \
  --self-dm data/eval/self_dm.json \
  --ledger data/U0AG8GF46CU/ledger.json \
  --out data/eval/charanya_report.md
```

The export is a JSON object with a `messages` list of `{ts, text}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_evaluation.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/evaluation.py tests/test_evaluation.py docs/EVAL.md .gitignore
git commit -m "feat: eval CLI and Charanya runbook"
```

---

## Self-Review

Spec coverage: this plan covers subsystem 1 only, ground truth and evaluation. Subsystems 2 to 6 have no tasks here; they are named as separate plans in the spec. That is intentional.

Step scan: every step names a file, a signature or a test assertion. No TBD.

Type consistency: `score` consumes label and extracted row shapes defined in Task 1 and Task 3; Task 4 reuses the same `main` and `format_report` names.

Review Focus tests: self-DM formatting is in Task 3, same-day recall in Task 2, duplicate ids in Task 2, missing negative id in Task 2, empty input in Task 2.

Proportion: 10 tests, four files. No implementation transcript beyond signatures and match rules.
