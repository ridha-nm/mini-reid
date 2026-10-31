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
| `com.minireid.daily` | 08:30 daily | `run.log` |
| `com.minireid.model` | 06:00 daily | `model.log` |
| `com.minireid.kb` | 02:00 daily | `kb.log` |

All run from `~/mini-reid`. `~/Desktop/Mini-Reid` is a symlink. Terminal does not need
to stay open.

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
snooze: deck 3d                   push it out
waiting: deck on Daniel           move to Waiting on others
drop: deck                        remove quietly
not: anything not part c          wrong item; teaches it to ignore that kind
remind me to send the deck in 2 minutes
ask: what did we agree with Eupe  answer from your own writing, with sources
find: eupe                        search the ledger
list                              ten nearest open items
help                              the command list
```

Plain sentences from Ridha become notes; questions go to the knowledge base; due or
status questions go to the list.

## Digest layout

Counts header, brief, then Overdue, Today and tomorrow, This week, Waiting on others,
No date, Notes, Review. Each row: task, client name, relative due, sender and channel,
link.

## Completion rules

Nothing closes by itself.

- `done:` closes a row.
- Reassigning a Jira issue closes it on the next run (`jira_reassigned`).
- A sent email only marks `closure: proposed`; it stays open until confirmed.
- An unsent draft becomes `stalled`, never done.

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

## Repo

`github.com/ridha-nm/mini-reid`, private. CI runs tests only; no secrets in GitHub.

## Next, agreed

1. Use it for a week. Collect `not:` corrections and Friday's `expected.txt`.
2. Tune from the scorecard: recall below 80% means extraction misses work; many `not:`
   corrections means it is too noisy.
3. Only then consider thread indexing or comment-level Jira mentions.
