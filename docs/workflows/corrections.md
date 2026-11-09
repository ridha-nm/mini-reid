# Workflow: corrections and learning

What Mini-Reid learns from `not:`, and how.

## Flow

1. `not:` closes a row (`status=dropped`, `closed_how=not_commitment`).
2. Single-row `not:` replies with five reason buttons — **Duplicate /
   Chatter / FYI / Handled elsewhere / Not mine**. The click stores
   `not_reason` on the row and the label as the correction's reason.
3. `learning.add` keeps up to 200 corrections in `corrections.json`; the
   classifier uses their `what` text as **negative examples**
   (`classifier._examples`); `learning.remember` keeps accepted command text
   as positive examples in `learning_events.json`.
4. Bulk `not:` writes one correction per row with reason `bulk not` (no
   buttons — the row is ambiguous).
5. Repeated titles are not re-captured (`drop_duplicate_titles`: normalised
   title + client against live rows; short titles exempt).
6. Channels learn silence: ≥3 rejects and >75% rejected mutes the channel.

## Cadence

- Corrections apply at the next extraction run; no model is trained.
- Mutes are re-evaluated every watcher cycle.
- `not:` on meetings dismisses the meeting reminder instead (no ledger row).

## State / code / tests

- State: `corrections.json`, `learning_events.json`, `muted_sources.json`
- Code: `learning.py` `classifier.py` `mutes.py` `ledger.drop_duplicate_titles`
- Tests: `test_learning.py` `test_classifier.py` `test_mutes.py`
  `test_ledger.py`
