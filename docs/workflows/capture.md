# Workflow: capture and triage

How a message becomes a task.

## Flow

1. `sources.py` pulls items: Slack search (`<@me>`), DMs the bot is not in,
   Gmail, Jira. `watcher.py` (owner) and `members.refresh` (members) call it.
2. `extract.extract` turns one item into at most one row. Rules decide:
   bots, calendar replies, sent mail, Jira notification mail, greetings,
   play requests, links-only, short chatter and muted channels are dropped.
3. `auto_reason` marks obvious rows `open`; everything else lands `inbox`.
4. The model (optional) only rewrites the title — never decides capture.
5. `inbox` rows get a DM with **Add to list** / **Not a task** buttons
   (10 per message). **Clear Inbox (N)** pages 10 at a time from `list`.
6. `merge` + `dedupe_by_link` + `drop_duplicate_titles` keep one row per
   ask; `apply_stalled` moves untouched open rows to `stalled`.

## Learned behaviour

- `learning.remember` records commands people actually used as training
  examples; `classifier.py` scores candidate text from ledger + corrections.
- `extract.ACTION_VERB`: a one/two-word Slack DM is chatter unless it carries
  an action verb ("Send deck" kept, "GG" dropped).
- `mutes.py`: a channel that is mostly `not:` rejects is muted for capture
  (`muted_sources.json`, delete a key to unmute).
- A trailing `*Sent using* @mini-reid` footer is a signature, not a command.

## State / code / tests

- State: `ledger.json`, `data/<uid>/ledger.json`, `bot_state.json`,
  `learning_events.json`, `corrections.json`, `muted_sources.json`
- Code: `sources.py` `extract.py` `classifier.py` `triage_ui.py` `members.py`
- Tests: `test_extract.py` `test_classifier.py` `test_mutes.py`
  `test_triage_ui.py` `test_members.py`
