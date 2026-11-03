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
| `due`, `status` | date; open, in progress, blocked, stalled, done, dropped |
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

The model is optional and only rewrites `what`. Given filtering authority it deleted
real asks and kept jokes.

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
join link, and "Are you attending?". Reply `yes` or `no <reason>`; the answer is
recorded in `meeting_reminders.json` and confirmed in the DM. Slack keeps the schedule,
so a sleeping Mac does not lose it. Each meeting is reminded once.

A separate overdue nudge runs once a day, on the first watcher cycle after 09:00, and
uses the same row renderer as the digest, link included. Only a real past due date or a
stalled status counts as overdue; undated rows stay in No date.

## Bot commands

`add:`, `task:`, `todo:`, `assign: <person> <what>`, `reassign: <item> to <person>`,
`note that`, `status: <item> in progress | blocked | open`,
`priority: <item> 1-5 | high | medium | low | none`, `tonote: <item>` (or `convert:`),
`combine: <duplicate> into <keep>`, `uncombine: <keep>`, `undo:`, `done:`, `due:`,
`edit: <item> to <new name> [by <when>]`, `snooze:`, `waiting:`,
`drop:` (also `remove:` / `delete:`), `not:` (also dismisses a meeting reminder and
ignores that title), `remind` (absolute or `in 2 minutes`),
`ask:`, `find:`, `list`, `notes`, `help`.

- Only Ridha mutates the ledger.
- Anyone who tags or DMs the bot can set a reminder for themselves or any teammate in
  the Pantas workspace: `remind me …`, `remind @Arman …`, `remind Arman Rahman …`,
  `add: … at 2pm`. The time is optional; without one the DM is sent immediately. Timed
  reminders are scheduled in Slack (server-side), stay private, and never enter Ridha's
  ledger or digest. An unknown name gets a reply, never a silent reminder to the sender.
- `list` numbers open items; `#N` works with `combine`, `done`, `due`, `snooze`, `drop`,
  `waiting`, `not`, `status` and `edit`. Each row also carries a stable short id
  (`[185045]`); `185045` or `id:185045` resolves regardless of numbering changes.
- `combine: <duplicate> into <keep>` drops the duplicate with `closed_how: merged` and
  records it under `merged_from` on the kept row. `uncombine: <keep>` restores them. No
  automatic dedupe: related asks can describe different deliverables.
- `undo:` reverses the last mutating command. Ten snapshots are kept in
  `ledger_undo.json`; background watcher merges are not snapshots.
- Successful `add:` gets ➕ and `note:` / `tonote:` gets 📝 as a reaction instead of a
  text reply. Failures still reply with the reason. Other commands reply as before.
- Requests to police a personal fight ("tell X to stop harassing", "unblock me") get a
  silly guardrail reply in the channel and no ledger row. The bot is a to-do list, not
  a referee.
- Bot-addressed small talk ("hi", "you there?", "thanks") gets a default reply naming
  `add:`, `note:` and `ask:`; it is not stored.
- Temporary banter mode (`banter.json`: channel, user ids, expiry) answers every message
  from those users in that channel with a canned line. Ridha ends it with `banter off`.
  It expires automatically.
- Any other message from someone else gets a ✅ and, if they write something, a note
  plus an instant DM to Ridha. No reply to them.
- Plain sentences from Ridha become notes; questions go to the knowledge base; due or
  status questions go to the list.
- Catch-up on wake answers questions asked while the Mac slept, marked late. Old
  commands are never replayed.

### Slack app

Socket Mode. Bot events: `app_mention`, `message.im`, `message.channels`,
`message.groups`. Channel messages that do not mention the bot are ignored. An edit that
still mentions the bot gets a ✅; if Ridha changed the text, the command is re-run once
(except `remind` and `undo`, which would duplicate). Commands are otherwise never
replayed. Replies to Ridha's own commands go to his DM, never to the channel, so a
command does not ping everyone. The channel only gets the ➕ / 📝 reaction where
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
| Sleep gaps | events missed while asleep; catch-up covers questions |
| Gmail token expiry | weekly refresh; failures show under Source errors |
| Auto-assigned Jira | board named instead of a person; reassignment closes the row |
| Shared alias noise | read-mail and DM filters; `not:` teaches the rest |

## Open questions

1. Whether comment-level Jira mentions are worth the extra query cost.
2. Whether thread replies deserve indexing.
3. How long closed rows are retained before pruning.
4. Whether an 8B or paid model is justified for synthesis.
