# Handoff

Current state of Mini-Reid. Update after every material change. Last updated
2026-11-05; next session can start here.

## What it is

A personal commitment ledger for Ridha. Reads Slack, Gmail and Jira, keeps what someone
owes in `ledger.json`, and surfaces it as a morning to-do digest plus two-minute alerts.
A Slack bot (`@minireid`) accepts commands.

Everything runs locally on the Mac. Nothing is stored in the cloud.

## Resume here

2026-11-03: 09:15 digest includes today's meetings; the watcher sends 10-minute meeting
DMs (reply `yes`, `no <reason>` or `moved`), polls DMs the bot is not in for `remind`, and ignores
`bd-triager-agent`. Tasks carry `open` / `in progress` / `blocked`, priority 1-5, stable
ids, combine/uncombine and 10-deep undo. Notes have their own list; `assign:` and
`reassign:` track what others owe. Banter is off by default and auto-arms for five
minutes on meanness. A small Naive Bayes classifier separates tasks from chatter.
Multi-user is in: owner-only `allow: @Name` writes `users.json`, DMs a one-time setup
link, and starts member capture. Each member has `data/<slack_id>/` with ledger, digest,
reminders and credentials. Slack coverage is bot-visible channels only. Jira is
automatic from the shared token; Gmail uses the Cloud Run relay and one Google consent.
Each profile may carry a `clients` list; Gmail is filtered to those clients by sender
domain or text, dropping unrelated external mail. `accounts.json` from the BD Command
Centre roster fills it at `allow:`; the member can correct it with
`clients: Eupe, Gamuda` or inspect it with `clients`. GHB/GVC/SAFE are portfolios with
their member-company domains; child clients carry a `portfolio` tag. Charanya is
overridden to Eupe, Setia, Allianz, DNex, Edotco and Knight Frank. 342 tests pass.

2026-11-04: every new candidate lands as `inbox` and waits for a click — the
new-item DM has **Add to list** / **Not a task** per item. The model never decides;
it only rewrites the title. Confirm → `open` and ✅ on the source message; dismiss →
`dropped`. The click edits the DM in place with the outcome, rebuilds buttons for
remaining items, and refuses to toggle a row already settled. Unanswered rows stay in
the list Inbox and its **Triage & update** modal.
`list` groups by status and due date and reads due dates relatively (`3d overdue`,
`today`, `in 2d`). Open rows untouched for a day get an 18:00 DM with an inline status
picker, at most three times. `done`/`not` accept bulk refs (`7, 9`, `#7 #9`,
`id:abc1`). Catch-up sweeps every `CATCHUP_SECONDS` (default 300) using its own
`catch_up_ts` watermark, so messages missed while the Mac slept or the socket dropped
are replayed; live messages still advance `last_ts`. Remaining build phases are in
`SPEC.md`: P2 cycles, P4 closure confirmation, P7 stock-take hub.

2026-11-05: `meet:` (or plain "set meeting with X to discuss Y") checks both
calendars with freeBusy, offers five 30-minute slots, and creates the Google event
with a Meet link and attendee invite. Requires `calendar.events` consent.
2026-11-05: `help` is a topic picker with My list / Triage buttons; every channel
reply stays in the triggering thread; pasted `done:`/`not:` lists match tasks and
notes (including notes that start with `9. [abc123]`); a reminder adds an open
reminder row to the recipient's list; `list` shows 40 rows, undated newest first;
a missed 09:15 digest is rebuilt and delivered after 09:30 until Slack accepts it;
`assign:` by row id reassigns and mirrors the title; Triage has Select all / Clear;
a meeting reply can be `moved` / `rescheduled` / `postponed`. Member parity is
recorded in `docs/MEMBER_PARITY.md`.

2026-11-05: `ask:` routes pending/open/due/task questions to the ledger first,
with count, due and links, filtered by client name; other questions use live
Slack search then the KB.
2026-11-05: App Home is a per-person dashboard: counts, top 3 focus, Open Slack
List, Triage Inbox, Refresh, quick commands. Not the full task list. Unknown
viewers get a capabilities page with Request access (DMs Ridha with the exact
`allow:` line) and Message Ridha; no cross-ledger exposure.
2026-11-05: `ask:` tries live Slack Real-time Search first for Ridha, with
channel/text/permalink, then falls back to the local KB. Each user's ledger is
mirrored into a native Slack List (“Mini-Reid — Name”) with title, status, due
and source; created once, shared write, incremental last 50. Bot scopes
`lists:read`/`lists:write`. `list` replies include an **Open Slack List** button
with that user's deep link. Sync is two-way: Slack edits to title/status/due win
on the next pull; deleting a List row drops the ledger row; dropped/Inbox rows
are deleted from the List.

2026-11-05 flying-car baseline: `mini_reid.evaluation` scores capture against
Charanya's self-written list, with `benchmark: false` for tasks that have no
Slack/Gmail/Jira signal. Her 7-task snapshot: 3 benchmarked, strict recall 0/3.
Runbook in `docs/EVAL.md`. That zero is the reason for the auto-capture plan.

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

One reply per Slack message id. `bot_state.json` holds a persistent `handled` map, claimed
before any response, so duplicate events (`app_mention` plus `message.channels`), socket
redelivery or a restart cannot answer twice. A changed edit releases its claim once.

Multi-user: `users.json` (gitignored) maps Slack user id to name, role and paths. Owner
runs `allow: @Name`; the bot writes `data/<slack_id>/` and DMs a one-time setup link.
Members cannot read or write `ledger.json`. `directory.json` (gitignored, 600) maps
Slack id → name, email and Jira account; rebuild with `python -m mini_reid.directory`.
`allow:` reads it, so Jira works immediately from the shared workspace token scoped by
account id. The watcher scans bot-visible channels for each member's mentions, uses
their Gmail only after OAuth, and runs their reminders, meeting reminders, overdue
nudge and 09:15 digest. Their new items get the same model title cleanup, inbox
confirmation DM, click acknowledgement/lock, grouped `list` with **Triage & update**,
and 18:00 stale nudge; every button resolves the member's own ledger. A member's
plain DM to the bot is added as a task, no `add:` prefix, so they can stop writing
their own Slack list. The **Add to Mini-Reid** message shortcut and the 📌
(`CAPTURE_REACTION`) reaction capture a message into the clicker's ledger.
Parity rule and checklist: `docs/MEMBER_PARITY.md` — no feature is done unless
it works for every authorised member in the same change.

Google setup uses the Cloud Run relay `mini-reid-setup` in project
`rij-agent-march2026` (`cloud/relay.py`, source deploy, min/max instances 1). Link:
`{RELAY_URL}/setup?state=<setup-token>`. Google callback `{RELAY_URL}/callback`; the code
is held in memory and the bot polls `/take` every 5s with `RELAY_KEY`. OAuth client is
Web application, Internal; JSON in `SETUP_GOOGLE_CREDS`, secret in Secret Manager
`mini-reid-oauth-client-secret`. Relay URL:
`https://mini-reid-setup-355354179016.asia-southeast1.run.app`. The local setup page on
`SETUP_PORT` remains as a fallback.

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
assign: @Kasib 1290b3             same, but an existing row id reassigns it
reassign: deck to Kasib           move an existing task to Waiting on others
note that ...                     remember it, no deadline
combine: #9 into #7               merge a duplicate into the task to keep
uncombine: #7                     restore everything merged into #7
undo:                             reverse the last ledger change (10 deep)
185045 / id:185045                stable row reference, survives renumbering
done: send the deck               close it; bulk refs: done 7, 9 / #7 #9
done: <pasted list>               one bullet per line; closes every matched title
not: <pasted list>                same, removes several at once
status: deck in progress          open, in progress, blocked
priority: deck 1                  P1 first; high/medium/low/none
tonote: deck                      keep as a note (also convert:)
banter on 2h [@person|all]        sassy reply to tagged abuse; off/status too
due: deck by Monday               change the date
edit: deck to Send deck by Monday rename and re-date
snooze: deck 3d                   push it out
waiting: deck on Daniel           move to Waiting on others
drop: deck                        remove quietly (also remove: / delete:)
not: anything not part c          wrong item; also takes bulk refs; meeting title cancels reminder
remind me to send the deck in 2 minutes
ask: what did we agree with Eupe  answer from your own writing, with sources
find: eupe                        search the ledger
list                              grouped open items + Inbox + Notes, Triage button
notes                             list notes; they also appear in the digest
help                              topic picker: Capture / Update / Close / Find …
```

Bot-addressed small talk ("hi", "you there?", "thanks") gets the default reply naming
`add:`, `note:` and `ask:`; praise gets a short kind reply. Nothing is stored. A request to referee a personal fight
("tell X to stop harassing", "unblock me", "treat X nicely"), threats and insults gets a
silly guardrail line and no ledger row; "start huddle" gets a specific refusal.

Banter is manual-only and off by default. `banter on 2h [@person|all]`, `banter off`,
`banter status` control it; the watcher announces expiry. Only an addressed message that
is also mean gets a sassy line. Untagged messages never get a reply, mean or not. Banter
is allowed only in `#ee-leads-only` and `#probies`.

`#N` from `list` works with `status`, `done`, `due`, `snooze`, `drop`, `waiting`, `not`
and `edit`, so a rename never depends on fuzzy wording.

Plain sentences from Ridha become notes; questions go to the knowledge base; due or
status questions go to the list.

Ridha's command replies go to his DM, never to the channel, so a command does not ping
everyone. Successful `add:` is acknowledged in the channel with ➕, `note:` / `tonote:`
with 📝, and `remind:` with ⏰; failures go to his DM. Other people's explicit
commands still answer in the channel, always as a thread reply on their message —
never in the main chat. Casual chatter ("drive the car") gets the default line in
that thread and is never copied into Ridha's ledger as a note. Editing a message that still mentions the bot gets a ✅; when the text changed,
the command is re-run once, except `remind` and `undo`. Repeated edits of the same text
are ignored, so a command is not applied twice.

Anyone who tags or DMs the bot can set a reminder for themselves or any teammate in the
Pantas workspace: `remind me to … at 2pm`, `remind @Arman to … at 2pm`,
`remind Arman Rahman to …`, `add: … at 2pm`. The time is optional; without one the DM is
sent immediately. Timed reminders, including Ridha's own, are scheduled server-side with
Slack, so they fire on time even when the Mac sleeps. Every reminder is also added to
the recipient's list as `kind: reminder`, open, with `reminded: True` so the watcher
does not send it twice. An unknown name gets a reply, not a
silent reminder to the sender. Other people's reminders never touch Ridha's ledger or
digest. Slack keeps the queue; there is no local copy yet, so there is no cancel or list.

## Digest layout

Counts header, brief, today's meetings (time, title, join link), then Overdue, Today and
tomorrow, This week, Waiting on others, No date, Notes, Review. Each task row: task,
client name, relative due, sender and channel, source time, link. Email senders keep
their address; a rewritten Slack title quotes the original message.

The watcher schedules a DM 10 minutes before each meeting with the join link and "Are
you attending?". Reply `yes`, `no <reason>`, or `moved` / `rescheduled` /
`postponed` (a note like "moved to 3pm" is kept); it is recorded in
`meeting_reminders.json` and confirmed in the DM. Slack keeps the schedule, so the Mac
can sleep. A single-instance lock (`.watcher.lock`) stops overlapping runs from
scheduling duplicates.

The daily overdue nudge (first watcher cycle after 09:00) uses the same row renderer as
the digest, so it carries the same sender, time and link. Undated rows are not overdue;
only a real past due date or a stalled status is.

The 09:15 job writes `digest_delivered.json` only after Slack accepts the DM. If
it fails (no DNS on 2, 3 and 5 Nov), the watcher regenerates and delivers after
09:30, retrying every 10 minutes until the marker says today is done.

A new item does not enter any digest bucket until it is confirmed. The capture DM
shows each item with **Add to list** / **Not a task**; unanswered items stay in the
list Inbox and are counted as `N to confirm` in the digest header.

A stale nudge runs at 18:00 for open / in progress / blocked / stalled rows whose
`last_activity` is older than today. It DMs up to five rows, each with an inline status
picker, and stops after three nudges per row. Any status change through triage resets
the counter.

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

The weekly review is also the classifier's training loop: the Naive Bayes model
rebuilds from `ledger.json` and `corrections.json` on every call, so new `not:`
corrections and fixed rows improve it without a separate train step. Use
`python -m mini_reid.classifier "phrase"` to inspect scores when a social message was
kept or a real ask was missed.

## Known limits

- The 3B model only rewrites titles. It does not decide what is a task and cannot drop
  a captured row; every candidate waits in the inbox for a person's click.
- 8B local is unusable on 8 GB (about five minutes per answer).
- Answers are extractive, not composed.
- Untagged asks in channels and thread replies without a mention are not captured.
- WhatsApp and calls are manual capture only.
- macOS sleep pauses the socket; the catch-up sweep (every `CATCHUP_SECONDS`, default
  300) replays commands and questions missed while asleep or disconnected.
- Watcher takes about 55 s per cycle after parallel source fetches (sources ~12 s;
  the member cycle and meeting scheduling make up the rest), inside the two-minute
  interval. Before the parallel fix a cycle ran 2+ minutes.
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
342 tests passing as of 2026-11-05.

## Next, agreed

1. Week starting 2026-11-01: use it daily. Collect `not:` corrections and Friday's
   `expected.txt`.
2. Tune from the scorecard: recall below 80% means extraction misses work; many `not:`
   corrections means it is too noisy.
3. Only then consider thread indexing or comment-level Jira mentions.
