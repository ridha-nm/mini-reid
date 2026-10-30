# Handoff

Current state of Mini-Reid. Update after every material change.

## What it is

A personal commitment ledger for Ridha. Reads Slack, Gmail and Jira, extracts what
someone owes, keeps it in `ledger.json`, and surfaces it two ways: a daily digest and
a two-minute watcher for new items. A Slack bot (`@minireid`) accepts commands.

## Running now

| Agent | Cadence | Log |
|---|---|---|
| `com.minireid.bot` | live, KeepAlive | `bot.out.log`, `bot.err.log` |
| `com.minireid.watcher` | every 120 s | `watcher.log` |
| `com.minireid.daily` | 08:30 daily | `run.log` |

All three run from `~/mini-reid` via launchd. `~/Desktop/Mini-Reid` is a symlink.

## Commands

```bash
# digest, rules only
.venv/bin/python -m mini_reid.cli --days 1

# digest with local model rewrite (slow, ~8 min for 65 items)
.venv/bin/python -m mini_reid.cli --days 1 --model llama3.2:3b

# deliver to Slack DM
.venv/bin/python -m mini_reid.cli --days 1 --deliver

# capture by hand
.venv/bin/python -m mini_reid.cli --capture "add: Eupe item by Friday"

# watcher, one cycle
.venv/bin/python -m mini_reid.watcher

# tests
.venv/bin/python -m pytest tests/ -q
```

Slack commands, in a DM or a channel the bot is in:

```
add: <what> by <when>        create a task
note: <text>                 remember something, no deadline, own Notes section
done: <part of the item>     close it
due: <item> by Friday        change the date
snooze: <item> 3d            push it out (d = days, w = weeks)
waiting: <item> on Daniel    move it to Waiting on others
drop: <item>                 remove it without deleting history
find: <text>                 search the ledger
not: <item>                  wrong item, teach it to ignore this kind
list                         ten nearest open items
```

Only Ridha can change the ledger. Anyone else gets a ✅ reaction and no reply.

## Files

| File | Purpose |
|---|---|
| `SPEC.md` | the agreed design and constraints |
| `CHANGES.md` | dated log of what changed |
| `HANDOFF.md` | this file |
| `ledger.json` | the commitments, committed to git when a repo exists |
| `digest.md` | last rendered digest, markdown |
| `clients.json` | client list, domains, Slack channels |
| `slack-app-manifest.yaml` | source of truth for the Slack app |

## Credentials

`.env`, mode 600, never committed. Slack app tokens (`xapp`, `xoxb`, `xoxp`), Gmail
OAuth paths, Jira API token, `SLACK_OWNER_ID`.

## Weekly scorecard

Write what you actually owed in `expected.txt`, one per line, **before** opening
the digest on Friday. Then:

```bash
.venv/bin/python -m mini_reid.scorecard
```

It appends recall and the missed list to `scorecard.md`. This is the only real
measure of whether tuning works.

## Known limits

- Rules-only extraction copies the email opener; proper task wording needs the model.
- The 3B model takes about 8 minutes for a full pass and occasionally returns bad JSON.
- Completion is proposed from sent mail, but nothing auto-closes; `done:` confirms.
- Watcher takes ~40 s per cycle, which is why it runs every 2 minutes.
- Repo: github.com/ridha-nm/mini-reid (private). CI runs tests only, no secrets.

## Next, agreed order

1. Move the model rewrite to a 06:00 job so the 08:30 digest is already clean.
2. Completion detection from sent mail and meeting notes, proposing closure for confirmation.
3. Tighten rules so undated FYI mail stops becoming rows.
