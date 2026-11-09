# Task confirmation on arrival

Date: 2026-11-04
Status: implemented

## Intent

Nothing reaches the task list until Ridha says it is a task. The model's job is
readability, not judgement: it rewrites a captured message into a clean title, and
Ridha clicks **Add to list** or **Not a task**. This stays until the local model is
good enough to be trusted with the decision.

## What happens to a new item

1. Rules capture a candidate (Slack mention, DM, Gmail, Jira).
2. The local model rewrites the title for readability. It is told every message is a
   candidate and it must return one item per message. It cannot drop an item.
3. The row is stored with `status: "inbox"`. It is excluded from the digest buckets,
   overdue nudges and the numbered list.
4. The watcher DMs one section per item with **Add to list** / **Not a task**
   buttons, up to ten per message. Fallback text carries the same list.
5. **Add to list** → `status: "open"`, `last_activity` stamped, nudges reset, and the
   source Slack message gets ✅. **Not a task** → `status: "dropped"`,
   `closed_how: "not_commitment"`.
6. Unanswered items stay in the Inbox section of `list`, where the existing
   **Triage & update** modal can also settle them.

## Model prompt

- No `is_commitment` field. The model no longer decides.
- Titles start with a verb, sentence case, max 100 chars, no greeting, signature,
  email header, quoted history or trailing period.
- Keep names, numbers, dates and document names a person needs to act.
- `due` only when the text states or clearly implies a date.

## Non-goals

- No confidence scoring or auto-accept threshold.
- No per-item message update after a click; a batch DM keeps its buttons. Clicking
  again is idempotent (the row changes status again, no duplicate row).
- Member DMs use the same flow; the ledger is resolved from the clicker's profile.

## Parts deliberately reused

- `inbox` status, Inbox section in `list`, triage modal, `apply_triage`,
  `send_dm(..., blocks=...)`.
- Rules capture; the naive-Bayes classifier remains separate.

## Where it lives

- `mini_reid/watcher.py` — `triage_rows`, confirmation DM
- `mini_reid/members.py` — same flow per member
- `mini_reid/providers.py` — title-only prompt and schema
- `mini_reid/triage_ui.py` — `confirm_blocks`
- `mini_reid/slack_bot.py` — `confirm_task` / `reject_task` actions
- `mini_reid/render.py` — inbox excluded, "N to confirm" count
- `mini_reid/listview.py` — relative due labels

## Tests

`tests/test_watcher.py`, `test_providers.py`, `test_triage_ui.py`,
`test_listview.py`, `test_render.py`. Suite: 343 passing as of 2026-11-05.
