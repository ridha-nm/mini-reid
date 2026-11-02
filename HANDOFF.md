# Handoff

Current state of Mini-Reid. Update after every material change.

## What it is

A personal commitment ledger for Ridha. Reads Slack, Gmail and Jira, keeps what someone
owes in `ledger.json`, and surfaces it as a morning to-do digest plus two-minute alerts.
A Slack bot (`@minireid`) accepts commands.

Everything runs locally on the Mac. Nothing is stored in the cloud.

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

## Commands

```bash
.venv/bin/python -m mini_reid.cli --days 1 [--deliver] [--model llama3.2:3b]
.venv/bin/python -m mini_reid.watcher
.venv/bin/python -m mini_reid.kb --build | --ask "question"
.venv/bin/python -m mini_reid.scorecard
.venv/bin/python -m pytest tests/ -q
```

Slack, in the bot's DM or a channel it has been invited to:

```
add: send the deck by Friday      create a task
task: ... / todo: ...             same as add
note that ...                     remember it, no deadline
done: send the deck               close it
due: deck by Monday               change the date
edit: deck to Send deck by Monday rename and re-date
snooze: deck 3d                   push it out
waiting: deck on Daniel           move to Waiting on others
drop: deck                        remove quietly
not: anything not part c          wrong item; teaches it to ignore that kind
remind me to send the deck in 2 minutes
ask: what did we agree with Eupe  answer from your own writing, with sources
find: eupe                        search the ledger
list                              numbered open items; use #1 in later commands
help                              the command list
```

`#N` from `list` works with `done`, `due`, `snooze`, `drop`, `waiting`, `not` and
`edit`, so a rename never depends on fuzzy wording.

Plain sentences from Ridha become notes; questions go to the knowledge base; due or
status questions go to the list.

A command run in a channel is answered in the channel and mirrored to Ridha's DM, so it
raises a Slack notification. Editing a message that still mentions the bot gets a ✅;
edits are never replayed, so a command cannot be applied twice.

Anyone who tags or DMs the bot can set a reminder for themselves or a teammate:
`remind me to … at 2pm`, `remind @Arman to … at 2pm`, `add: … at 2pm`. Every reminder,
including Ridha's own, is scheduled server-side with Slack, so it fires on time even when
the Mac sleeps. Other people's reminders never touch Ridha's ledger or digest. Slack
keeps the queue; there is no local copy yet, so there is no cancel or list.

## Digest layout

Counts header, brief, then Overdue, Today and tomorrow, This week, Waiting on others,
No date, Notes, Review. Each row: task, client name, relative due, sender and channel,
source time, link. Email senders keep their address; a rewritten Slack title quotes the
original message.

## Completion rules

Nothing closes by itself.

- `done:` closes a row.
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

## Repo

`github.com/ridha-nm/mini-reid`, private. CI runs tests only; no secrets in GitHub.

## Next, agreed

1. Week starting 2026-11-01: use it daily. Collect `not:` corrections and Friday's
   `expected.txt`.
2. Tune from the scorecard: recall below 80% means extraction misses work; many `not:`
   corrections means it is too noisy.
3. Only then consider thread indexing or comment-level Jira mentions.
