# Workflow: reminders

`remind` creates a Slack-scheduled DM and a visible row.

## Flow

1. `parse_remind` reads who, what and when ("in 2 minutes", "at 3pm",
   "tomorrow"); a leading "now" is dropped for an immediate reminder.
2. One person or many: shared text, or one `@Name <item>` line each.
3. `schedule_dm` asks Slack to post at the time (survives the Mac sleeping)
   and `log_reminder` appends to the audit log; `add_reminder_row` puts a
   `kind=reminder` row on the recipient's list so both sides see it.
4. `watcher.fire_reminders` is the local fallback (rows with `remind_at`,
   not `reminded`), honouring Slack DND when `RESPECT_DND=1`.
5. `sent_reminders` shows the last three on the sender's `list` under
   **Reminders I sent**. Replies to a reminder DM are counted
   (`dm_reply_count`) for the audit view.
6. Ambiguous reminder text triggers a clarifying question; the next plain
   reply is taken as the answer (`pending_remind` in `bot_state.json`).

## State / code / tests

- State: `reminder_log.json`, `pending_remind` in `bot_state.json`,
  `data/<uid>/meeting_reminders.json`
- Code: `slack_bot` (`parse_remind`, `send_reminder`), `notify.py`,
  `watcher.fire_reminders`
- Tests: `test_slack_bot.py`, `test_notify.py`, `test_watcher.py`
