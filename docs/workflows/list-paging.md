# Workflow: list and paging

The `list` reply and its Inbox.

## Flow

1. `ordered_rows` keeps live statuses (open/stalled/in progress/blocked),
   groups by section then due bucket, newest first inside a bucket.
2. `format_list` renders **25 rows per page**; the footer shows `Page N/M`.
   Page numbering continues across pages. Page 1 also carries
   **Reminders I sent**, **Inbox** and **Notes**.
3. `list_blocks` splits text into Slack sections on line boundaries
   (2,900 chars each) and adds the pager: `◀ Previous` / `Next ▶`
   (`meet_day`-style action `list_page`, value = page index).
4. A page click rebuilds from the clicker's ledger and `chat_update`s the
   same message — no new DM.
5. Inbox rows are never numbered; they carry their own count and the
   **Clear Inbox** button. Titles are shown up to 200 chars.

## State / code / tests

- State: none (reads the ledger on every click)
- Code: `listview.py`, `triage_ui.list_blocks`, `slack_bot` `list_page`
- Tests: `test_listview.py`, `test_triage_ui.py`
