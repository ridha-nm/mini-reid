# Workflow: Slack List mirror

Every user's live tasks, mirrored into a native Slack List.

## Flow

1. `slack_lists.ensure_list` creates the List once per user with columns
   Task / Status / Due / Source / **Assigner** (`v: 2` in
   `slack_lists.json`).
2. `sync_user` pushes every live row (kind not note/reminder, status not
   inbox/done/dropped, up to 500) and deletes rows that became done or
   dropped.
3. Any mutating command, the Triage modal, Clear Inbox and the
   Add/Not-a-task buttons call `sync_slack_list` immediately; the watcher
   cycle (3 min) is the backstop.
4. Edits in the List flow back: title/status/due change the ledger on the
   next pull; deleting an item drops the task.
5. A schema change (new column) cannot be applied in place — Slack has no
   API for it — so `ensure_list` renames the old List "(archived)",
   creates a new one and clears the rows' item ids.

## Assigner

`Assigner` = mail sender email · Slack author email (user token with
`users:read.email`) · Jira reporter email · bot name when no email exists.
RIJ files every Jira ticket as `ridha@pantas.com`, so Jira RIJ rows filter by
title `[RIJ]`, not by email.

## State / code / tests

- State: `slack_lists.json`, `slack_item_id`/`slack_synced_at` on ledger rows
- Code: `slack_lists.py`, `slack_bot.sync_slack_list`
- Tests: `test_slack_lists.py`
