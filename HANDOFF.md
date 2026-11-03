# Handoff

Current state of Mini-Reid. Update after every material change. Last updated
2026-11-02; next session can start here.

## What it is

A personal commitment ledger for Ridha. Reads Slack, Gmail and Jira, keeps what someone
owes in `ledger.json`, and surfaces it as a morning to-do digest plus two-minute alerts.
A Slack bot (`@minireid`) accepts commands.

Everything runs locally on the Mac. Nothing is stored in the cloud.

## Resume here

2026-11-02: 09:15 digest includes today's meetings; the watcher sends 10-minute meeting
DMs (reply `yes` or `no <reason>`), polls DMs the bot is not in for `remind`, and ignores
`bd-triager-agent`. Tasks carry `open` / `in progress` / `blocked`. 166 tests pass.
Remaining work is the "Next, agreed" list below.

## Running now

| Agent | Cadence | Log |
|---|---|---|
| `com.minireid.bot` | always (KeepAlive) | `bot.out.log`, `bot.err.log` |
| `com.minireid.watcher` | every 120 s | `watcher.log` |
| `com.minireid.daily` | 09:15 daily | `run.log` |
| `com.minireid.model` | 06:00 daily | `model.log` |
| `com.minireid.kb` | 02:00 daily | `kb.log` |

All run from `~/mini-reid`. `~/Desktop/Mini-Reid` is a symlink. Terminal does not need
to stay open.

Slack app subscriptions saved 2026-11-01: `app_mention`, `message.im`,
`message.channels`, `message.groups`. Socket Mode; no public URL.

The watcher polls Ridha's DMs with the user token, because Slack delivers no events from
a DM the bot is not in. It searches for owner messages addressed to the bot, executes
only `remind`, and DMs the confirmation to Ridha's bot DM. State: `dm_poll_state.json`.
Expect up to one 2-minute cycle of latency; the message must contain literal
`@mini-reid` or a real `<@U…>` mention.

Calendar access is a Google scope on the same token as Gmail: `calendar.readonly`,
granted 2026-11-02. Re-run `mini_reid.google_auth` if it is revoked. Meetings come from
every visible calendar but only include events Ridha is invited to, on calendars he does
not own. Tags from `bd-triager-agent` are ignored in extraction and in the bot.

## Commands

```bash
.venv/bin/python -m mini_reid.cli --days 1 [--deliver] [--model llama3.2:3b]
.venv/bin/python -m mini_reid.watcher
.venv/bin/python -m mini_reid.google_auth   # one-time Calendar consent
.venv/bin/python -m mini_reid.kb --build | --ask "question"
.venv/bin/python -m mini_reid.scorecard
.venv/bin/python -m pytest tests/ -q
```

Slack, in the bot's DM or a channel it has been invited to:

```
add: send the deck by Friday      create a task
task: ... / todo: ...             same as add
assign: @Kasib send the deck      someone else owes it; Waiting on others
reassign: deck to Kasib           move an existing task to Waiting on others
note that ...                     remember it, no deadline
combine: #9 into #7               merge a duplicate into the task to keep
uncombine: #7                     restore everything merged into #7
undo:                             reverse the last ledger change (10 deep)
185045 / id:185045                stable row reference, survives renumbering
done: send the deck               close it
status: deck in progress          open, in progress, blocked
priority: deck 1                  P1 first; high/medium/low/none
tonote: deck                      keep as a note; dropped from the task list
due: deck by Monday               change the date
edit: deck to Send deck by Monday rename and re-date
snooze: deck 3d                   push it out
waiting: deck on Daniel           move to Waiting on others
drop: deck                        remove quietly (also remove: / delete:)
not: anything not part c          wrong item; a meeting title cancels its reminder
remind me to send the deck in 2 minutes
ask: what did we agree with Eupe  answer from your own writing, with sources
find: eupe                        search the ledger
list                              numbered open items; use #1 in later commands
notes                             list notes; they also appear in the digest
help                              the command list
```

Bot-addressed small talk ("hi", "you there?", "thanks") gets the default reply naming
`add:`, `note:` and `ask:`; nothing is stored. A request to referee a personal fight
("tell X to stop harassing", "unblock me", "treat X nicely") gets a silly guardrail
line and no ledger row; "start huddle" gets a specific refusal. `banter.json` turns on temporary
canned replies for listed users in one channel; `banter off` ends it, and the `until`
timestamp expires it anyway.

`#N` from `list` works with `status`, `done`, `due`, `snooze`, `drop`, `waiting`, `not`
and `edit`, so a rename never depends on fuzzy wording.

Plain sentences from Ridha become notes; questions go to the knowledge base; due or
status questions go to the list.

Ridha's command replies go to his DM, never to the channel, so a command does not ping
everyone. Successful `add:` is acknowledged in the channel with ➕ and `note:` /
`tonote:` with 📝; failures go to his DM. Other people's commands still answer in the
channel. Editing a message that still mentions the bot gets a ✅; when the text changed,
the command is re-run once, except `remind` and `undo`. Repeated edits of the same text
are ignored, so a command is not applied twice.

Anyone who tags or DMs the bot can set a reminder for themselves or any teammate in the
Pantas workspace: `remind me to … at 2pm`, `remind @Arman to … at 2pm`,
`remind Arman Rahman to …`, `add: … at 2pm`. The time is optional; without one the DM is
sent immediately. Timed reminders, including Ridha's own, are scheduled server-side with
Slack, so they fire on time even when the Mac sleeps. An unknown name gets a reply, not a
silent reminder to the sender. Other people's reminders never touch Ridha's ledger or
digest. Slack keeps the queue; there is no local copy yet, so there is no cancel or list.

## Digest layout

Counts header, brief, today's meetings (time, title, join link), then Overdue, Today and
tomorrow, This week, Waiting on others, No date, Notes, Review. Each task row: task,
client name, relative due, sender and channel, source time, link. Email senders keep
their address; a rewritten Slack title quotes the original message.

The watcher schedules a DM 10 minutes before each meeting with the join link and "Are
you attending?". Reply `yes` or `no <reason>`; it is recorded in
`meeting_reminders.json` and confirmed in the DM. Slack keeps the schedule, so the Mac
can sleep. A single-instance lock (`.watcher.lock`) stops overlapping runs from
scheduling duplicates.

The daily overdue nudge (first watcher cycle after 09:00) uses the same row renderer as
the digest, so it carries the same sender, time and link. Undated rows are not overdue;
only a real past due date or a stalled status is.

## Completion rules

Nothing closes by itself.

- `done:` closes a row. Adding the same wording again reopens a closed or dropped row.
- Reassigning a Jira issue closes it on the next run (`jira_reassigned`).
- A sent email only marks `closure: proposed`; it stays open until confirmed.
- Email drafts are not commitments. Only an incoming ask becomes a row.

## Knowledge base

Index contains Slack messages Ridha sent, Gmail sent and received, and local documents.
Local embeddings (`nomic-embed-text`). Answers are verbatim passages with sources, above
a 0.55 similarity floor; below it the answer is "I do not know". Rebuild nightly at
02:00 and incrementally.

`KB_ALLOWLIST` in `.env` lists Slack user ids allowed to use `ask:`; empty means only
Ridha.

## Weekly scorecard

Write what you actually owed in `expected.txt`, one per line, before opening the digest
on Friday. Then:

```bash
.venv/bin/python -m mini_reid.scorecard
```

It appends recall and missed items to `scorecard.md`.

## Known limits

- 3B model only rewords tasks; it is not trusted to filter.
- 8B local is unusable on 8 GB (about five minutes per answer).
- Answers are extractive, not composed.
- Untagged asks in channels and thread replies without a mention are not captured.
- WhatsApp and calls are manual capture only.
- macOS sleep pauses everything; catch-up answers missed questions on wake.
- Watcher takes about 40 s per cycle, hence the two-minute interval.
- Edited-message ✅ depends on the app keeping `message.channels`/`message.groups`. A
  reinstall can rotate the bot token; update `.env` and restart the bot if it stops.
- Extraction is rules-first. A real ask the gate misses is captured with `add:`.
- `mini_reid/classifier.py` is a tiny Naive Bayes second opinion for social messages.
  It is trained from local ledger rows, `not:` corrections and seed phrases; it only
  suppresses social notes/default replies and never filters commitments.
- DMs the bot is not in only run `remind`, and only after a 2-minute poll. `add:`,
  `status:` and the rest need the bot DM or a channel.
- The DM poll uses Slack search, which is eventually consistent; a command can take one
  extra cycle to appear.
- Meetings only work for the Google account whose token is in `GMAIL_TOKEN`; Slack or
  Outlook calendars are not read.

## Repo

`github.com/ridha-nm/mini-reid`, private. CI runs tests only; no secrets in GitHub.
166 tests passing as of 2026-11-02.

## Next, agreed

1. Week starting 2026-11-01: use it daily. Collect `not:` corrections and Friday's
   `expected.txt`.
2. Tune from the scorecard: recall below 80% means extraction misses work; many `not:`
   corrections means it is too noisy.
3. Only then consider thread indexing or comment-level Jira mentions.
