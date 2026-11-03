# Mini-Reid

A personal commitment ledger. It reads Slack, Gmail, Jira and Google Calendar, keeps
what you owe in `ledger.json`, and puts it in front of you three ways: a morning to-do
digest, alerts for new items, and a Slack bot you can talk to.

It runs on this Mac only. No cloud. Nothing leaves the machine except calls to Slack,
Gmail, Jira and Google Calendar.

## What it does

- **Morning digest** (09:15, Slack DM): counts, a short brief, today's meetings with
  join links, then Overdue, Today, This week, Waiting on others, No date, Notes.
- **Watcher** (every 2 min): new Slack mentions, DMs to you, inbox mail including
  already-read mail, and Jira issues assigned to you. New items get a DM and, where the
  bot is in the channel, a ✅ on the source message. The first cycle after 09:00 also
  DMs any overdue rows once a day. Each meeting gets a DM 10 minutes before it starts,
  with the join link and "Are you attending?". Answer `yes` or `no <reason>` in the DM.
  The watcher also polls Ridha's DMs for `remind` commands in conversations the bot is
  not part of.
- **Bot** (`@minireid`): add, note, tonote, status, priority, combine, uncombine, undo,
  done, due, edit, snooze, waiting, drop, not, remind, find, list, ask, help. `list` prints a
  stable short id per row; `185045` or `id:185045` works in every command; `undo:`
  reverses the last change. Priority 1-5 sorts the digest and list. Only you can change the ledger. Anyone can set a private reminder for
  themselves or a teammate — those never enter your ledger.
- **Knowledge base**: local retrieval over your sent Slack, sent mail, received mail and
  local documents. `ask:` returns passages from your own writing, with sources.

## Run

```bash
cd ~/mini-reid

.venv/bin/python -m mini_reid.cli --days 1            # digest, rules only
.venv/bin/python -m mini_reid.cli --days 1 --deliver  # digest to Slack DM
.venv/bin/python -m mini_reid.watcher                 # one watcher cycle
.venv/bin/python -m mini_reid.google_auth             # one-time Calendar consent
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
ignored unless it addresses the bot. Tags from `bd-triager-agent` are ignored. Slack
sends no events from DMs the bot is not in, so the watcher polls them for `remind`
commands with the user token.

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
| `meeting_reminders.json` | today's meeting reminders and attendance answers |
| `dm_poll_state.json` | last DM command read by the watcher |
| `calendar_ignores.json` | meeting titles dismissed with `not:` |
| `expected.txt` | Friday's manual list for the scorecard |

## Credentials

`.env` holds the Mini-Reid Slack app tokens (`xapp`, `xoxb`, `xoxp`), Google OAuth paths,
the Jira API token and `SLACK_OWNER_ID`. Rotate the Slack user token if it is ever
exposed; it can read every DM. The Google token carries Gmail scopes plus
`calendar.readonly`; `mini_reid.google_auth` re-adds the Calendar scope.

## Known limits

- The local 3B model is used only to reword tasks. It is not trusted to decide what is
  a commitment, because it deleted real asks and kept jokes.
- 8B local is unusable on 8 GB: about five minutes per answer.
- Answers are extractive. They quote your own writing; they do not compose prose.
- Nothing runs while the Mac sleeps. Catch-up answers questions on wake, late.
