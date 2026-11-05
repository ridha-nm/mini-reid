# Mini-Reid

A personal commitment ledger. It reads Slack, Gmail, Jira and Google Calendar, keeps
what you owe in `ledger.json`, and puts it in front of you three ways: a morning to-do
digest, alerts for new items, and a Slack bot you can talk to.

It runs on this Mac only. No cloud. Nothing leaves the machine except calls to Slack,
Gmail, Jira and Google Calendar.

## What it does

- **Morning digest** (09:15, Slack DM): counts, a short brief, today's meetings with
  join links, then Overdue, Today, This week, Waiting on others, No date, Notes.
  If delivery fails (no DNS at 09:15), the watcher rebuilds and delivers after 09:30,
  retrying every 10 minutes until Slack accepts it.
- **Watcher** (every 2 min): new Slack mentions, DMs to you, inbox mail including
  already-read mail, and Jira issues assigned to you. Every new item waits as Inbox and
  gets a DM with the sender, an **open source** link and **Add to list** / **Not a
  task**; the click updates that DM with the outcome and removes its buttons, Add
  opens it on the list and ✅s the source. Nothing reaches the digest until confirmed. The first cycle after 09:00 also
  DMs any overdue rows once a day. Each meeting gets a DM 10 minutes before it starts,
  with the join link and "Are you attending?". Answer `yes`, `no <reason>`, or
  `moved` / `rescheduled` / `postponed` in the DM.
  The watcher also polls Ridha's DMs for `remind` commands in conversations the bot is
  not part of.
- **Bot** (`@minireid`): add, assign, reassign, note, tonote/convert, status, priority,
  combine, uncombine, undo, done, due, edit, snooze, waiting, drop, not, remind,
  meet, find, list, notes, ask, clients, help. `meet: @Kasib about X` (or
  `meet: @Kasib and @Charanya about X`) checks every calendar, shows a busy snapshot
  with formal details, offers free slots, lets you edit the title/notes, and creates
  the Meet invite for everyone. `clients` shows the email filter;
  `clients: Eupe, Gamuda` replaces it. Portfolios GHB/GVC/SAFE are accepted.
  `banter on/off/status` controls sassy replies; only tagged abuse triggers one.
  Untagged messages are always ignored. Banter is allowed only in `#ee-leads-only`
  and `#probies`.
  `list` prints a stable short id per row, grouped by status and due date with
  relative due labels (`3d overdue`, `today`, `in 2d`), plus an Inbox section for
  items awaiting confirmation, then Notes; its **Triage & update** button lets you
  set a status on several rows at once, with **Select all** / **Clear**. `185045` or `id:185045` works in every command;
  `done`/`not` also take bulk refs (`done 7, 9`) or a pasted list, one bullet per
  line; the `[abc123]` ids in the paste pick the exact rows, and titles are
  matched as a fallback. `not:` also matches notes.
  `undo:` reverses the last change. Priority 1-5 sorts the digest and list.
  `help` opens a topic picker grouped by intent, with My list and Triage buttons.
  `/mini-reid` opens the list ephemerally; `/mini-reid add: …`, `remind …`,
  `meet: …` run in DM.
  Open rows untouched for a day get an evening DM (max 3 per row) with an inline
  status picker. Optional DND quiet hours for nudges/reminders: `RESPECT_DND=1`
  (off by default).
  Successful `add:` reacts ➕; `note:` / `tonote:` react 📝; `remind:` reacts ⏰.
  Your command replies go to your DM, not the channel; channel replies to anyone else
  stay in the triggering thread. Only you can change your ledger.
  Anyone can set a private
  reminder for themselves or a teammate — it never becomes a task for the sender;
  the recipient gets it on their own list as a reminder row.
  Tagged messages work in plain language too (`please mark the deck done`,
  `can you remind xieyi he owes me the gameplan`), with typo-tolerant commands
  and names. An ambiguous `by Friday 2pm` asks **Now / At Friday / Both** with
  buttons; `now and again Friday 2pm` sends both without asking. `reminders`
  lists the audit log: pending, sent, and how many replies the DM got.
  Silly requests work too (`give @Raj a hug`). Profanity gets a defensive
  reply; slurs get 🚩 on the message and a private DM. Accepted commands are
  logged locally and feed the task-vs-chatter classifier — no external training.
- **Teammates**: Ridha runs `allow: @Charanya`. The bot creates an isolated profile,
  DMs a one-time setup link, and starts capture for that member. Their commands, ledger,
  Slack mention alerts, reminders, meeting reminders and 09:15 digest stay private;
  new items get the same confirmation buttons, grouped list/triage and stale nudges.
  A member can DM the bot plain text and it becomes a task; no prefix needed.
  Right-click any message and choose **Add to Mini-Reid**, or react with 📌, to
  capture it without tagging the bot. 📌 sends an `Added:` DM, and both show under
  **Just added** at the top of `list`.
  Jira activates automatically from the shared workspace token, scoped to their Jira
  account. Gmail uses a hosted Google OAuth page: one click, consent, done. The Cloud
  Run relay holds the code for seconds and the Mac picks it up. A profile's `clients`
  list filters member Gmail to those clients by domain or text; `allow:` fills it from
  the BD Command Centre roster. Slack coverage is only channels the bot has been invited
  to. `python -m mini_reid.directory` rebuilds Slack → email → Jira;
  `python -m mini_reid.accounts` rebuilds email → client accounts from the
  stocktake-hub config.
- **Knowledge base**: local retrieval over your sent Slack, sent mail, received mail and
  local documents. `ask:` answers pending/open/due questions from the ledger first,
  then ingested Slack files (PDF, DOCX, XLSX, text), then live Slack Real-time
  Search, then the local passages.
- **App Home**: per-person dashboard with a table of 10 task stats, today's
  meetings, top 3 focus items, Open Slack List, Triage Inbox and Refresh. Non-authorised users get a capabilities page with
  **Request access** (DMs you an **Authorise** button) and **Message Ridha**,
  never another ledger.
- **Slack List mirror**: each user's ledger is mirrored into a native Slack List with
  title, status, due and source; created once and updated every watcher cycle.
  `list` includes an **Open Slack List** button. Edits in the List flow back to
  the ledger; deleting a row there drops the task; non-tasks are removed.

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
`message.groups` (manifest: `slack-app-manifest.yaml`). Interactivity is on for the
reminder clarification buttons. The two message subscriptions exist so an edited
mention can be acknowledged with ✅; every other channel message is ignored unless it
addresses the bot. Each message id is answered once; `bot_state.json` tracks handled
ids across restarts. On startup, catch-up replays missed channel mentions and DMs —
every command type, not only questions. Tags from `bd-triager-agent` are ignored.
Slack sends no events from DMs the bot is not in, so the watcher polls them for
`remind` commands with the user token.

Setting up another person or your own instance: see `SETUP.md`.

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
| `users.json` | allowlist and per-user paths, local only |
| `directory.json` | Slack id → name, email and Jira account, local only |
| `accounts.json` | work email → client slugs from the BD roster, local only |
| `data/<slack_id>/` | a teammate's ledger, digest and Google/Jira credentials |
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

Member Google setup runs through the Cloud Run relay `mini-reid-setup`
(`cloud/relay.py`, project `rij-agent-march2026`, region `asia-southeast1`). Links look
like `{RELAY_URL}/setup?state=…`. Google redirects to `{RELAY_URL}/callback`; the relay
holds the code in memory and the bot polls `/take` every 5 seconds with `RELAY_KEY`.
`RELAY_URL` and `RELAY_KEY` live in `.env`. The relay reads its client ID from an env var
and its client secret from Secret Manager.

The OAuth client is a **Web application** type whose JSON is at `SETUP_GOOGLE_CREDS`
(mode 600) with redirect URI `{RELAY_URL}/callback`. Consent type is **Internal**, so
tokens are long-lived and no verification is needed. Member secrets live in
`data/<slack_id>/` with mode 600.

## Known limits

- The local 3B model is used only to reword tasks. It is not trusted to decide what is
  a commitment, because it deleted real asks and kept jokes.
- 8B local is unusable on 8 GB: about five minutes per answer.
- Answers are extractive. They quote your own writing; they do not compose prose.
- Nothing runs while the Mac sleeps. Catch-up replays missed commands on wake, late.
