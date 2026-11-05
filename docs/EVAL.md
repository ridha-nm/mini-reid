# Capture evaluation

Measures Mini-Reid's capture against Charanya's own Slack to-do list.

## Data needed

1. A Slack JSON export of Charanya's **self-DM** (the DM she has with herself),
   saved as `data/eval/self_dm.json`:

```json
{"messages": [{"ts": "1793866425.785539", "text": "• send the deck\n☐ review dashboard"}]}
```

A full Slack workspace export is a zip of per-conversation/per-day JSON files,
each shaped `{"messages": [...]}`. Merge the self-DM message lists into one
`messages` array before running; this tool reads exactly one JSON object.

2. Her member ledger at `data/U0AG8GF46CU/ledger.json`. Rows she dismissed with
   **Not a task** are captured predictions that were wrong, so they count as
   false tasks. Every other non-note/non-reminder row counts as a captured
   prediction.

## Benchmark labels

A task with no Slack, Gmail or Jira evidence cannot be captured and must not
count against recall. Set `"benchmark": false` on that label:

```json
{"date": "", "text": "10 am interview", "is_task": true, "benchmark": false}
```

The report shows `Manual-only labels excluded` and scores recall only on
benchmark labels.

Both stay on this Mac. `data/eval/` is gitignored.

## Run

```bash
mkdir -p data/eval
.venv/bin/python -m mini_reid.evaluation \
  --self-dm data/eval/self_dm.json \
  --ledger data/U0AG8GF46CU/ledger.json \
  --out data/eval/charanya_report.md
```

Exit code 0 means the target was met; 1 means it was not.

## Target

- Recall 95% or more of her self-written tasks.
- Fewer than one false task per day.
- Charanya judges the result and, by day five of the pilot, stops writing her
  own list.

## Report

`charanya_report.md` contains positives, covered, recall, false tasks, reviewed
dismissals, false tasks per day, a PASS/FAIL verdict, the missed tasks and the
false task examples.
