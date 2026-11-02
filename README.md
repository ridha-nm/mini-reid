# Mini-Reid

A personal commitment ledger. It reads Slack, Gmail and Jira, keeps what you owe in
`ledger.json`, and puts it in front of you three ways: a morning to-do digest, alerts
for new items, and a Slack bot you can talk to.

It runs on this Mac only. No cloud. Nothing leaves the machine except calls to Slack,
Gmail and Jira.

## What it does

- **Morning digest** (09:15, Slack DM): counts, a short brief, then Overdue, Today,
  This week, Waiting on others, No date, Notes.
- **Watcher** (every 2 min): new Slack mentions, DMs to you, inbox mail including
  already-read mail, and Jira issues assigned to you. New items get a DM and, where the
  bot is in the channel, a ✅ on the source message.
- **Bot** (`@minireid`): add, note, done, due, edit, snooze, waiting, drop, not, remind,
  find, list, ask, help. Only you can change the ledger. Anyone can set a private reminder for
  themselves or a teammate — those never enter your ledger.
- **Knowledge base**: local retrieval over your sent Slack, sent mail, received mail and
  local documents. `ask:` returns passages from your own writing, with sources.

## Run

```bash
cd ~/mini-reid

.venv/bin/python -m mini_reid.cli --days 1            # digest, rules only
.venv/bin/python -m mini_reid.cli --days 1 --deliver  # digest to Slack DM
.venv/bin/python -m mini_reid.watcher                 # one watcher cycle
.venv/bin/python -m mini_reid.kb --build              # rebuild the knowledge index
.venv/bin/python -m mini_reid.kb --ask "what did we agree with Eupe on waste"
.venv/bin/python -m pytest tests/ -q                  # tests
```

`./run.sh` is the digest job. `./run_bot.sh` is the listener. `./run_watcher.sh` is one
watcher pass.

## Slack app

Socket Mode. Bot events: `app_mention`, `message.im`, `message.channels`,
`message.groups` (manifest: `slack-app-manifest.yaml`). The two message subscriptions
exist so an edited mention can be acknowledged with ✅; every other channel message is
ignored unless it addresses the bot.

## Agents

| launchd label | Cadence | Log |
|---|---|---|
| `com.minireid.bot` | always, KeepAlive | `bot.out.log`, `bot.err.log` |
| `com.minireid.watcher` | every 120 s | `watcher.log` |
| `com.minireid.daily` | 09:15 daily | `run.log` |
| `com.minireid.model` | 06:00 daily | `model.log` |
| `com.minireid.kb` | 02:00 daily | `kb.log` |

Check them with `launchctl list | grep minireid`.

## Files

| File | What |
|---|---|
| `.env` | secrets, mode 600, never committed |
| `ledger.json` | the commitments, local only |
| `digest.md` | last rendered digest |
| `clients.json` | client names, domains, Slack channels |
| `kb.json` | knowledge index, local only |
| `corrections.json` | items you marked `not:` |
| `expected.txt` | Friday's manual list for the scorecard |

## Credentials

`.env` holds the Mini-Reid Slack app tokens (`xapp`, `xoxb`, `xoxp`), Gmail OAuth paths,
the Jira API token and `SLACK_OWNER_ID`. Rotate the Slack user token if it is ever
exposed; it can read every DM.

## Known limits

- The local 3B model is used only to reword tasks. It is not trusted to decide what is
  a commitment, because it deleted real asks and kept jokes.
- 8B local is unusable on 8 GB: about five minutes per answer.
- Answers are extractive. They quote your own writing; they do not compose prose.
- Nothing runs while the Mac sleeps. Catch-up answers questions on wake, late.
