# Mini-Reid — Spec

Living document. Describes what is built and why, not what was hoped for.

## Outcome

Every commitment Ridha makes is tracked until he closes it. Nothing slips, nothing
lives only in his head, and routine asks are visible without him searching for them.

## Non-goals

- Never speaks as Ridha. The bot posts as itself.
- Never sends client-facing messages.
- Never closes work on its own.
- Never answers a question it cannot ground in something Ridha wrote.

## Failure modes this exists to catch

1. **Unseen ask.** Read and forgotten.
2. **Stalled work.** Started and dropped. The real case: an SRSL reply about Gamuda,
   drafted and left unsent for a week. An unread search never finds it.
3. **Channel gap.** WhatsApp and calls. No API; manual capture only.
4. **Silent close.** Done, but nothing records it, so it nags.
5. **Wrong attribution.** Shared aliases and auto-assigned boards making someone else's
   work look like his.

## Client filter

`bd@pantas.com` is a shared alias, so the recipient is not a signal. Relevance comes
from the client and from direct address.

| Group | Clients |
|---|---|
| Direct | IOI, Knight Frank, Gamuda (includes SRSL), Eupe, Kelington, TMK |
| SAFE | SFIA, Suslab, DTI |
| GHB | Bank Rakyat, Agrobank, Maybank, others as they appear |
| GVC | Kossan, POS Malaysia, Ajinomoto, others as they appear |

Matching order: sender domain, Slack channel, client name in text, then a known client
domain quoted inside the message. Unknown domains go to a review bucket; they are never
guessed.

## Decisions

| Decision | Choice |
|---|---|
| Hosting | Local Mac, launchd. No cloud, no always-on host. |
| Delivery | Slack DM only. No Telegram, no SMS. |
| Models | Local Ollama. 3B for rewording; 8B is unusable on 8 GB. |
| Who decides a commitment | Rules. The model may reword, never filter. |
| Jira scope | Issues assigned to Ridha only. Comment mentions are excluded. |
| Closure | Only `done:` or a Jira reassignment. Emails propose, never close. |
| Data | Nothing client-confidential leaves the machine. |
| Pass bar | 80% recall at first, measured weekly against a hand-written list. |

## Sources

| Source | Signal |
|---|---|
| Slack mentions | `search.messages` with the user token |
| Slack DMs | recent messages from other people to Ridha |
| Gmail inbox | all inbox mail, read or unread |
| Gmail sent | activity and closure proposals |
| Gmail drafts | ignored; Ridha's own unsent writing is not an ask |
| Jira | issues assigned to Ridha, excluding Done |
| Google Calendar | timed events today; on shared calendars only events Ridha is invited to or organises; declined and cancelled dropped |
| Excluded | tags from `bd-triager-agent`; that bot tags people on every routed issue |
| Manual | `@minireid add:` or `note:` |

Not covered: untagged asks in channels, thread replies without a mention, WhatsApp,
calls.

## The ledger

`ledger.json`, local, gitignored. One row per commitment.

| Field | Meaning |
|---|---|
| `id` | sha1 of source, native id and normalised wording |
| `what` | task text: email subject for mail, message text for Slack |
| `asker`, `via` | who sent it, and where it reached him (DM, #channel, direct, alias, Jira board) |
| `client` | slug from the rule matcher only |
| `due`, `status` | date; open, in progress, blocked, stalled, done, dropped; `inbox` = waiting for a person to triage |
| `priority` | 1-5, absent when unranked; 1 is first |
| `kind` | mention, dm, inbox, draft, issue, note, reminder |
| `closure` | open, proposed |
| `remind_at` | when a reminder fires |

Rules:

- Merge is idempotent; terminal statuses never reopen, except that `add:` with the same
  wording explicitly reopens a done or dropped row.
- Stalled: past due, or five working days without activity.
- Undated tasks stay on the list until closed. They do not expire.
- A Jira row closes when the issue is no longer assigned. Skipped if the Jira fetch
  failed, so a network blip cannot close the board.

## Extraction

Rules decide. A message needs a request signal: `can/could/would/will you`, `please`,
`need you/the/…`, an imperative opener (`send`, `confirm`, `get`, `start`, …), or it is
a channel mention. Channel mentions are always kept unless they are pure chatter.

- Kept: requests, first-person commitments, Gmail with a direct address or a dated
  request, Jira assignments.
- Rejected: bots, `bd-triager-agent` tags, calendar responses, Jira notification mail,
  sent mail, chatter,
  questions with no ask ("do you have access?"), status updates ("Update: …"), other
  people's own plans ("I try to get … today"), Google boilerplate, URLs, newsletters.

Rules capture. Every captured row starts as `status: inbox` and waits for a person.
The optional local model only rewrites the title for readability; it is told every
message is a candidate and returns one item per message. It cannot drop a row and has
no commitment verdict. A row the model rewrote keeps the cleaner wording; a row it
omitted or failed on keeps the rule text. Either way it stays in the inbox until
confirmed (**Add to list**) or dismissed (**Not a task**).

A tiny Naive Bayes classifier (`mini_reid/classifier.py`) gives a second opinion on
bot-addressed social text, trained from the ledger, `not:` corrections and seed
phrases. It can suppress a social note or send the default reply; it never filters
extracted commitments.

## Digest

09:15 to Slack DM. Counts header, deterministic brief (counts, three most urgent,
overdue by client), then today's meetings with time, title and join link:

**Meetings · Overdue · Today and tomorrow · This week · Waiting on others · No date ·
Notes · Possibly done · Review**

Each row: task, client name, relative due (`2d overdue`, `today`, `in 3d`), priority
when set (`[P1]`), status when it is in progress or blocked, sender and channel, source
time, link. Priority sorts before due date inside every section; `list` uses the same
order. Email senders keep their full address. A Slack row quotes the original message
when the task title was rewritten.

The watcher schedules a Slack DM 10 minutes before each meeting starts: time, title,
join link, and "Are you attending?". Reply `yes`, `no <reason>`, or `moved` /
`rescheduled` / `postponed`; a note after the word is kept. The answer is
recorded in `meeting_reminders.json` and confirmed in the DM. Slack keeps the schedule,
so a sleeping Mac does not lose it. Each meeting is reminded once.

A separate overdue nudge runs once a day, on the first watcher cycle after 09:00, and
uses the same row renderer as the digest, link included. Only a real past due date or a
stalled status counts as overdue; undated rows stay in No date.

New items do not enter a digest bucket until confirmed. The capture DM carries one
section per item with **Add to list** / **Not a task** (at most ten per DM); the rest
wait in the list Inbox. The header counts unanswered rows as `N to confirm`.

A stale nudge runs at 18:00: open, in progress, blocked and stalled rows with no
activity today are DMed, up to five at a time, each with an inline status picker. A row
is nudged at most three times; a status change through triage or the picker resets the
count. Inbox rows are never nudged as stale or overdue.

`list` is grouped as In progress / Blocked / Overdue / Due today / This week / Later /
No date, followed by Inbox. The reply carries a **Triage & update** button that opens a
modal: select rows (checkboxes chunked ten per Slack block, at most forty selectable),
choose one status, apply once. **Select all** / **Clear** rebuild the modal with every
row ticked or none; Slack has no shift-select.

## Bot commands

`add:`, `task:`, `todo:`, `assign: <person> <what>` (a row ref such as
`eb8263` or `#7` reassigns that row and mirrors its title into the assignee's
ledger), `reassign: <item> to <person>`,
`note that`, `status: <item> in progress | blocked | open`,
`priority: <item> 1-5 | high | medium | low | none`, `tonote: <item>` (or `convert:`),
`combine: <duplicate> into <keep>`, `uncombine: <keep>`, `undo:`, `done:`, `due:`,
`edit: <item> to <new name> [by <when>]`, `snooze:`, `waiting:`,
`drop:` (also `remove:` / `delete:`), `not:` (also dismisses a meeting reminder and
ignores that title), `remind` (absolute or `in 2 minutes`),
`ask:`, `find:`, `list`, `notes`, `allow: @Name`, `banter on|off|status`, `help`.

- `done` and `not` accept several refs at once: `done 7, 9`, `#7 #9`,
  `id:abc1, id:def2`. One bad ref rejects the whole batch and changes nothing.
- Both also accept a pasted digest/list: one bullet per line, metadata after an
  em dash ignored, `[abc123]` short id used when present. Titles match normalised
  text, then a unique prefix; Slack HTML entities are unescaped. A row already
  done/dropped is skipped. One unknown or ambiguous title rejects the batch.
- A new item's DM offers **Add to list** / **Not a task** per item. Add sets the row
  `open` and ✅s the source Slack message; Not a task sets `dropped` /
  `not_commitment`. The click edits the DM to name the outcome and rebuilds buttons
  for the items still waiting on that message; when none remain the buttons are
  removed. A settled row ignores further clicks, so a stale button cannot toggle it.
  The list's **Triage & update** modal can settle unanswered rows.
- The owner mutates `ledger.json`; an allowlisted member mutates only their own
  `data/<slack_id>/ledger.json`. Nobody can read another user's ledger.
- `allow: @Name` is owner-only. It writes `users.json`, creates the member's isolated
  paths, and DMs a one-time setup link. Re-running it resends the link until setup is
  complete. Non-allowlisted users keep the old note-to-Ridha path; they cannot use
  ledger commands.
- The member watcher reads mentions in channels the bot is in, plus their own Gmail and
  Jira. Jira uses the shared workspace token, queried by the member's Jira account id;
  Gmail uses the member's own OAuth token. Their reminders, meeting reminders, overdue
  nudge, 18:00 stale nudge and 09:15 digest go only to their DM. New items use the same
  model title cleanup and inbox confirmation DM; `list`, its **Triage & update** modal
  and stale pickers all resolve that member's ledger, never the owner's.
- `directory.json` (gitignored, mode 600) maps Slack id → name, email and Jira account.
  Rebuild with `python -m mini_reid.directory`. `allow:` reads it first, so any Pantas
  member can be set up without typing their email or Jira id.
- A profile may carry `clients`, a list of `clients.json` slugs. Member Gmail is kept
  only when the sender domain or message text matches one of them. Slack and Jira are
  not filtered by this list. `accounts.json` (from the BD Command Centre / stocktake-hub
  roster) maps work email → clients; `allow:` fills the profile from it. Members can
  override it with `clients: Eupe, Gamuda` or inspect it with `clients`. Portfolios
  GHB/GVC/SAFE match their member-company domains; a child match also satisfies its
  portfolio. Charanya is overridden to Knight Frank, Allianz, Setia and Eupe.
- Setup page: `{RELAY_URL}/setup?state=<setup-token>` on Cloud Run. Google redirects to
  `{RELAY_URL}/callback`; the relay holds the code in memory and the bot polls
  `/take` with `RELAY_KEY`. Google consent is one-time and offline; the refresh token
  lives in the member's data directory. Jira is automatic and the form is only a
  fallback.
- Anyone who tags or DMs the bot can set a reminder for themselves or any teammate in
  the Pantas workspace: `remind me …`, `remind @Arman …`, `remind Arman Rahman …`,
  `add: … at 2pm`. The time is optional; without one the DM is sent immediately. Timed
  reminders are scheduled in Slack (server-side), stay private, and never enter Ridha's
  ledger or digest. An unknown name gets a reply, never a silent reminder to the sender.
  A successful reminder is acknowledged with a ⏰ reaction on the command message.
- `list` numbers open items; `#N` works with `combine`, `done`, `due`, `snooze`, `drop`,
  `waiting`, `not`, `status` and `edit`. Each row also carries a stable short id
  (`[185045]`); `185045` or `id:185045` resolves regardless of numbering changes.
- `combine: <duplicate> into <keep>` drops the duplicate with `closed_how: merged` and
  records it under `merged_from` on the kept row. `uncombine: <keep>` restores them. No
  automatic dedupe: related asks can describe different deliverables.
- `undo:` reverses the last mutating command. Ten snapshots are kept in
  `ledger_undo.json`; background watcher merges are not snapshots.
- Successful `add:` gets ➕, `note:` / `tonote:` gets 📝, and `remind:` gets ⏰ as a
  reaction instead of a text reply. Failures still reply with the reason. Other
  commands reply as before.
- Requests to police a personal fight ("tell X to stop harassing", "unblock me",
  "treat X nicely", "make peace", threats, insults and profanity) get a silly or
  semi-mean guardrail reply in the channel and no ledger row. The bot is a to-do list,
  not a referee. "Start huddle" gets "I can't start huddles."
- Bot-addressed small talk ("hi", "you there?", "thanks") gets a default reply naming
  `add:`, `note:` and `ask:`; it is not stored.
- Praise or kindness ("good bot", "loving mini-reid") gets a short kind reply back.
- Banter is manual-only and **off** by default. `banter on 2h [@person|all]`,
  `banter off`, `banter status` control it; the watcher announces expiry. Only a message
  that both addresses the bot and is mean gets a sassy line. Untagged messages never get
  a reply, mean or not. Banter can only be enabled in `#ee-leads-only` and `#probies`;
  every other channel is rejected.
- Any other message from someone else gets a ✅ and, if they write something, a note
  plus an instant DM to Ridha. No reply to them.
- Plain sentences from Ridha become notes; questions go to the knowledge base; due or
  status questions go to the list.
- Catch-up on wake answers questions asked while the Mac slept, marked late. Old
  commands are never replayed.

### Slack app

Socket Mode. Bot events: `app_mention`, `message.im`, `message.channels`,
`message.groups`. Every Slack message id is claimed once in `bot_state.json` before a
reply, so Slack delivering both `app_mention` and `message.channels` (or a restart
replaying an event) cannot produce a second response. An edit releases the claim once so
the corrected text can run. Channel messages that do not mention the bot are ignored. An edit that
still mentions the bot gets a ✅; if Ridha changed the text, the command is re-run once
(except `remind` and `undo`, which would duplicate). Commands are otherwise never
replayed. Replies to Ridha's own commands go to his DM, never to the channel, so a
command does not ping everyone. The channel only gets the ➕ / 📝 / ⏰ reaction where
applicable.

Slack sends no events from a DM the bot is not in, so the watcher polls Ridha's recently
active DMs with the user token every two minutes. Only owner-authored messages that
address the bot are read, and only `remind` runs. The confirmation goes to the bot DM,
because posting in the source DM would speak as Ridha.

## Knowledge base

Local index of Ridha's Slack messages, sent mail, received mail and local documents.
Embeddings via `nomic-embed-text`.

Answers are verbatim passages with sources. A 0.55 similarity floor decides when to say
"I do not know". Measured: real questions score 0.63 to 0.81; off-topic peaks at 0.46.
Rebuild nightly at 02:00, incremental.

## Phases

| Phase | Status |
|---|---|
| P0 read-only digest | done, superseded |
| P1 ledger, stalled detection, capture door | done |
| P2 model rewrite, cycles | rewrite done; cycles not |
| P3 Slack bot, acknowledgements | done |
| P4 closure proposals | partial: proposals exist, confirmation via `done:` |
| P5 grounded Q&A | done, extractive |
| P6 learning from corrections | done: `not:` feeds the prompt |
| P7 stock-take hub | not started |

## Acceptance criteria

- **Recall:** at least 80% of a hand-written weekly list, measured with the scorecard.
- **Precision:** no more than 2 in 10 rows wrong; wrong rows are removed with `not:`.
- **No silent closes:** every closed row is `done:` or `jira_reassigned`.
- **Attribution:** every row names a person and a channel, or the Jira board.
- **Evidence:** every row has a working link.
- **Failure is loud:** a dead source appears under Source errors in the digest.

## Constraints

- Client confidentiality: no client content to a free-tier model.
- The bot is identifiable and never impersonates Ridha.
- Internal Slack only.
- Nothing is sent to anyone outside the workspace.

## Risks

| Risk | Reality today |
|---|---|
| Local model quality | 3B rewrites only; 8B too slow on 8 GB |
| Sleep gaps | socket pauses during sleep; the periodic catch-up sweep replays missed commands and questions |
| Gmail token expiry | weekly refresh; failures show under Source errors |
| Auto-assigned Jira | board named instead of a person; reassignment closes the row |
| Shared alias noise | read-mail and DM filters; `not:` teaches the rest |

## Open questions

1. Whether comment-level Jira mentions are worth the extra query cost.
2. Whether thread replies deserve indexing.
3. How long closed rows are retained before pruning.
4. Whether an 8B or paid model is justified for synthesis.
