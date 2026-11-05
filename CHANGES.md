# Changes

Append-only. Newest first.

## 2026-11-05 (schedule meetings from free/busy)

- `meet: @Kasib about BD Command Centre`, or plain `set meeting with Kasib to
  discuss BD Command Centre`, reads both calendars and offers five 30-minute
  slots in the next five working days, 09:00–18:00 MYT, as Pick buttons in the
  DM ("both free" per slot).
- Multiple attendees work: `meet: @Kasib and @Charanya about BD Command Centre`,
  `Kasib, Charanya and Arman Rahman about …`; freeBusy covers everyone and all
  are invited.
- The DM is a formal proposal: Title, With (name + email), Duration, time zone,
  an availability snapshot of both calendars' busy blocks, then Pick buttons.
  **Refresh availability** recomputes; **Cancel** drops the proposal.
- Picking a slot creates the Google Calendar event, adds a Meet link and invites
  the attendee (`sendUpdates=all`).
- `calendar.events` added to owner consent and the member relay.
- 298 tests passing.

## 2026-11-05 (source link on every confirmation DM)

- Each **Add to list / Not a task** item now shows `<source|open source>`
  (Gmail, Jira or Slack) plus sender and via, so the title can be checked before
  deciding. Shared `confirm_blocks`, so owner and every authorised member get it.
- 295 tests passing.

## 2026-11-05 (channel replies stay in the thread)

- Every channel reply now posts on the triggering message's `thread_ts`: default
  line, guardrail, banter, play, help, list and reminder questions. It used to
  reply in the main channel.
- Deleted the stray main-chat default reply in `#bd-pipeline`.
- 295 tests passing.

## 2026-11-05 (new assignments no longer fall off `list`)

- `list` cut at 25 rows; a new undated assignment sat at position 28 and was
  invisible. Limit is now 40 and undated rows are newest-first. Charanya's
  resume/assessment assignment now shows in the list.
- 295 tests passing.

## 2026-11-05 (reminders appear on the list)

- A reminder — yours or one someone sets for you — is now added to the
  recipient's ledger as `kind: reminder`, `status: open`, so it appears in
  `list` and the digest. It is marked `reminded` because Slack owns delivery,
  so the watcher cannot send a second copy.
- The resume/assessment-folder reminder was added to Ridha's list.
- 293 tests passing.

## 2026-11-05 (`not:` works on notes)

- A pasted list after `not:` now matches open **notes** as well as tasks. It
  handles note text that starts with list numbering (`9. [abc123]`), Slack
  `&amp;`, `<@U…>` ids vs typed names, and lines truncated by the list renderer.
- The reported five-note list was removed.
- 292 tests passing.

## 2026-11-05 (interactive help + morning digest catch-up)

- `help` now opens a topic picker: Capture, Update, Close, Find, Inbox,
  Reminders, Team, Fun, with **My list** and **Triage inbox** buttons and a
  **Back to topics** button. Commands are grouped by what the person wants to do.
- The 09:15 digest wrote `digest_delivered.json` only on a successful Slack DM.
  If the Mac had no DNS at 09:15, the watcher now regenerates and delivers after
  09:30, retrying every 10 minutes until it lands. That happened on 2, 3 and
  5 Nov; those days had no digest.
- 291 tests passing.

## 2026-11-05 (fuzzy "not" and bot self-messages)

- `not the time` no longer fuzzy-matches `note` and becomes a note; plain
  `not …` is unrecognised text unless it uses `not:`.
- The bot ignores its own posted messages (some arrive without `bot_id`), in
  live socket events and in the catch-up search. A self-hug reply after a
  restart had been replayed as a stranger's message and answered with the
  default line.
- Removed the stray "the time" note.
- 287 tests passing.

## 2026-11-05 (notes in `list`; play requests never captured)

- `list` now ends with a **Notes (N)** section, same short ids as the `notes`
  command. Previously notes were only visible via `notes`.
- Extraction ignores hug / high-five / fist-bump / pat requests, so a playful
  message no longer lands in the inbox asking "is this a task?".
- 287 tests passing.

## 2026-11-05 (bare-name play, and chatter is not noted)

- `give ridha a hug` now works without an `@` or a Slack mention; the play
  matcher accepts bare names known from the workspace.
- Bot-addressed chatter from other people ("drive the car") is answered with the
  default line and no longer copied into Ridha's ledger as a note. Only explicit
  commands from others are relayed.
- Removed the stale notes created by the hug and drive-the-car messages.
- 286 tests passing.

## 2026-11-05 (play requests work when tagged)

- `@mini-reid high-five @Julian` now works. The play matcher sees the mention
  first and gave up; it now strips the bot mention before matching.
- 286 tests passing.

## 2026-11-05 (list links no longer cut off)

- The list was placed in one Slack section capped at 3000 chars, which cut row
  18's URL mid-link. It now splits across multiple section blocks on line
  boundaries. Real ledger: 4353 chars → 2 sections, 23 links intact.
- 286 tests passing.

## 2026-11-05 (assign by row id no longer creates id-titled tasks)

- `assign: @Person eb8263` (or `#7`, `id:abc1`) now reassigns the matching
  existing row instead of creating a task literally titled `eb8263`. An unknown
  id gets an error and creates nothing.
- Removed the four junk rows this produced in the owner and Charanya ledgers;
  the two intended rows (`eb8263`, `1290b3`) are now assigned to Charanya.
- Assigning by id also mirrors the **task title** into the assignee's ledger
  (never the id), and DMs them the real task. Charanya's ledger now carries
  both tasks.
- 285 tests passing.

## 2026-11-05 (select all in the triage modal)

- The triage modal has **Select all** and **Clear** buttons. Select all rebuilds
  the modal with every selectable row pre-ticked; the chosen status is kept.
  Slack checkboxes have no shift-select, so this is the supported shortcut.
- 282 tests passing.

## 2026-11-05 (multiline `not:` and pasted-list edge cases)

- Fixed a multiline `not:` being parsed as `note` (and answering "Noted.")
  because the command regex stopped at the first newline. Colon commands now
  read the whole message.
- Pasted list lines keep their `[abc123]` short id, so duplicate titles are
  disambiguated by the id the list already shows.
- A line whose row is already done/dropped is skipped instead of failing the
  batch; other lines still apply.
- Slack HTML entities (`&amp;`) are unescaped before title matching.
- 279 tests passing.

## 2026-11-05 (meeting moved replies)

- A meeting reminder can now be answered with `moved`, `rescheduled`,
  `postponed`, `time changed`, or a phrase such as "it might have moved to
  3pm". The meeting is marked `moved`, the note is stored, and the DM confirms.
- The reminder text lists `yes`, `no <reason>` and `moved`.
- Same parser and member state path for the owner and every authorised member.
- 276 tests passing.

## 2026-11-05 (mass done from a pasted list)

- `done:` and `not:` accept a pasted digest/list: one bullet per line, metadata
  after an em dash ignored, ledger short ids stripped. Titles match on
  normalised text, then unique prefix. All-or-nothing: one unknown or ambiguous
  title changes nothing and names the offending line.
- Works for the owner and every authorised member through the shared command path.
- Member parity rule written down: `docs/MEMBER_PARITY.md`.
- 274 tests passing.

## 2026-11-05 (authorised members get the same flow)

- Members now get title cleanup from the local model, the `inbox` confirmation
  DM with **Add to list** / **Not a task**, and the click/edit/lock behaviour.
- `list` sends the **Triage & update** button to members, and its modal,
  submission and stale pickers resolve the clicker's own ledger instead of the
  owner's.
- Members get the 18:00 stale nudge with inline status pickers.
- 271 tests passing.

## 2026-11-05 (confirm clicks acknowledge and lock)

- Clicking **Add to list** / **Not a task** now edits the DM itself: shows
  `Added to the list: <task>` or `Not a task: <task>` and rebuilds buttons for
  the items still waiting on that message. No items left → buttons removed.
- A row already settled ignores further clicks; it cannot be toggled by a stale
  button. The message says "Already handled".
- Each inbox row stores `confirm_ts` / `confirm_channel` when its DM is sent, so
  a click can edit the right message. `send_dm` / `send_dm_to` now return Slack's
  response instead of only the channel id.
- 269 tests passing.

## 2026-11-05 (watcher fetches in parallel)

- Slack DM histories, per-message Gmail reads and author-name lookups now run
  in an 8-worker thread pool instead of serial HTTP calls. Measured on this Mac:
  Slack DMs 27.3 s → 3.7 s, Gmail 36.0 s → 6.7 s; sources total 65 s → 12 s.
- No behaviour change: same items, same order-insensitive parse.
- 264 tests passing.

## 2026-11-04 (confirm every new task)

- The model no longer decides what is a task. Rules capture every candidate; the
  model only rewrites the title for readability and must return one item per
  message. It has no `is_commitment` field left.
- Every new row lands as `status: "inbox"` and stays out of the digest, overdue
  nudge and numbered list until a person confirms it.
- The new-item DM carries one section per item with **Add to list** and **Not a
  task** buttons (up to 10 per DM; the rest stay in the list Inbox). Confirm →
  `open` and ✅ on the source Slack message. Dismiss → `dropped` / `not_commitment`.
- Member DMs use the same flow; the click resolves the member's own ledger.
- `list` due dates read relatively: `3d overdue`, `today`, `in 1d`, `in 6d`,
  then an absolute date.
- Digest counts add `N to confirm`; inbox rows are excluded from every bucket.
- Design note: `docs/superpowers/specs/2026-11-04-task-confirmation-design.md`.
- 262 tests passing.

## 2026-11-04 (triage inbox, bulk close, stale nudges)

- Watcher triage: when the model rewrites an item it stays a task; when the
  model never saw it (rejected) it is dropped; when the model failed on it the
  row is parked as `status: "inbox"` for a person to decide. Only real tasks
  get the ✅ reaction and the new-item DM; inbox rows get their own nudge.
- `list` now groups by In progress / Blocked / Overdue / Due today / This week /
  Later / No date, with an Inbox section. Same numbering as the old list, so
  `done 4` still works.
- The list reply carries a **Triage & update** button: pick rows, choose a
  status once, apply in bulk. Checkboxes are chunked 10 per block (Slack's
  limit) and capped at 40 selectable rows.
- Evening stale nudge (18:00, DM, max 3 per row): open / in progress / blocked
  rows with no activity today get an inline status picker per row.
- `done` and `not` accept bulk refs: `done 7, 9`, `#7 #9`, `id:abc1, id:def2`.
- Status changes stamp `last_activity`; triage resets the nudge counter.
- `send_dm`/`send_dm_to`/bot replies accept Block Kit `blocks`.
- 258 tests passing.

## 2026-11-04 (never miss a message again)

- Catch-up now sweeps every `CATCHUP_SECONDS` (default 300) while the bot runs,
  not only at startup. Messages sent while the Mac slept or the socket was down
  are replayed once it wakes.
- Catch-up keeps its own `catch_up_ts` watermark. Live messages still advance
  `last_ts`; tying sweeps to that would skip a gap the socket never delivered
  (it hid the 17:51 and 18:00 messages today).
- Mention search paginates up to 10 pages and DM history reads 200 messages per
  conversation. `claim_message`/`_mark` share a lock so a sweep and a socket
  event cannot clobber `bot_state.json`.
- 237 tests passing.

## 2026-11-04 (play replies stay in thread)

- Hug / high-five / fist-bump replies now post as a thread reply on the
  message that asked for them, not a new channel message.
- 235 tests passing.

## 2026-11-04 (commands after chatter)

- A bot mention anywhere in the message now counts. `AHAHHA @mini-reid remind
  <@Eden> to go to bed!` parses as a reminder instead of becoming a note; the
  recipient's own mention still survives for `split_target`.
- Laughter prefixes (`AHAHHA`, `haha`, `hehe`, `lol`, `lmao`, `rofl`) are
  stripped before verb matching, and a literal `@mini-reid` mid-message is
  recognised.
- 235 tests passing.

## 2026-11-04 (reminder clarifications, natural language, catch-up)

- Reminder ambiguity: `by Friday 2pm` asks **Now / At Friday / Both** with Slack
  buttons (unique action ids; text reply `now` / `later` / `both` also works).
  `now and again …` sends both without asking.
- `reminder_log.json` audit: pending, sent, replies. `reminders` command lists it.
- Plain language after a tag: politeness prefixes, typo-tolerant verbs and names,
  and mappings for done/drop/note/find/assign/waiting/due/snooze.
- Catch-up now replays every command type across channel mentions and all bot DMs,
  not only `ask:`; pending clarifications survive restarts.
- Explicit day+month (`thursday nov 12`) now beats the weekday in due parsing.
- Setup docs for new operators and teammates (`SETUP.md`), `requirements.txt`,
  complete `.env.example`; interactivity enabled in the manifest. 228 tests passing.
- Learning: accepted commands are logged locally (`learning_events.json`) and,
  with every member ledger, feed the existing naive-Bayes task classifier.
- Safety: slurs get a 🚩 reaction and a private DM asking the person to be
  better; profanity directed at the bot keeps the existing sassy defence.
  Abuse verbs (molest, rape, grope) are treated the same as slurs instead of
  becoming ledger notes.
- Fun: `give @Name a hug`, `high five @Name`, `fist bump @Name` reply in
  channel with no ledger row. 232 tests passing.

## 2026-11-03 (banter channel allowlist)

- Banter can only be enabled in `#ee-leads-only` and `#probies`. Every other channel is
  rejected at the command and at reply time.
- `software-related-issues` cannot banter. 213 tests passing.

## 2026-11-03 (no untagged replies)

- Deleted the bot's untagged sassy message in `software-related-issues`
  (`1793718297.690999`). No ledger row was created by it.
- Removed auto-banter and the untagged reply path entirely. Untagged channel messages
  now get no reply, mean or not.
- Manual `banter on` now only affects messages that address the bot and are mean.
- 213 tests passing.

## 2026-11-03 (members declare their accounts)

- Added `clients:` / `accounts:` command. Members can inspect or override their email
  filter: `clients: Eupe, Gamuda`. Unknown names are rejected.
- Setup-complete DM now states the active filter or asks the member to set one.
- `allow:` DM now includes numbered setup steps and the `clients` commands.
- Charanya's override now includes Eupe: Knight Frank, Allianz, Setia, Eupe.
- 213 tests passing.

## 2026-11-03 (per-person client accounts)

- Added `mini_reid/accounts.py` + `accounts.json` (gitignored, 600): work email → client
  slugs, built from the live BD Command Centre / stocktake-hub roster
  (`config-live.json`). `allow:` fills the profile's `clients` from it. GHB/GVC/SAFE are
  portfolios and skipped.
- Charanya's override: Knight Frank, Allianz, Setia, Eupe.
- Expanded `clients.json` from 16 to 38 entries using the live roster: 35 clients plus
  GHB/GVC/SAFE portfolios. Added Allianz, Setia, DNex, KWAP, PNB Enterprise, Edotco,
  Sime Darby Property, AmBank FE/EE, Aemulus and Canon. Portfolio domains are the union
  of their member companies; child clients carry a `portfolio` tag.
- Gmail filter now keeps only mail matching the member's accounts. One-day check:
  Charanya 52 messages → 5 Setia/Knight Frank/Allianz.
- 212 tests passing.

## 2026-11-03 (hosted Gmail setup)

- Added `cloud/relay.py`, deployed to Cloud Run `mini-reid-setup` in
  `rij-agent-march2026` (asia-southeast1, min/max 1). Fixed HTTPS setup page and Google
  callback; codes and Jira form held in memory only.
- Bot polls the relay every 5s with `RELAY_KEY` and finishes the token exchange.
- Created Internal Web-application OAuth client with redirect
  `https://mini-reid-setup-355354179016.asia-southeast1.run.app/callback`; JSON at
  `~/.minireid-oauth-web.json`, client secret in Secret Manager.
- Setup links now point at the relay. No paste, no Tailscale, no inbound to the Mac.
- Refresh tokens are bound to the OAuth client that issued them. Each profile stores
  `google_client`; Charanya stays on the original Desktop client, relay users use the
  new Web client. Fixed a 401 caused by refreshing her token with the wrong client.
- Per-profile `clients` filter. Gmail is kept only when sender domain or text matches
  one of those clients. Charanya: POS Malaysia, Gamuda, Agrobank, Kossan, Knight Frank,
  Bank Rakyat, Eupe. 52 messages in one day → 9 kept.
- 210 tests passing.

## 2026-11-03 (member directory + shared Jira)

- `python -m mini_reid.directory` builds `directory.json` (gitignored, 600): Slack id,
  name, email and Jira account id for every active Pantas member. Current build: 39
  people, 36 emails, 36 Jira ids.
- `allow:` uses the directory, so Jira is active immediately from the shared workspace
  token queried by the member's account id. No member Jira token needed.
- `assign:` now mirrors the task into the assignee's ledger and DMs them.
- `setup <redirected-url>` completes Gmail OAuth by DM, without the setup page.
- Fixed `allow:` re-send raising `UnboundLocalError` instead of DMing the link.
- 209 tests passing.

## 2026-11-03 (multi-user activation)

- `allow: @Name` now creates the profile, issues a 24-hour setup token and DMs the
  member a setup link. Re-running `allow:` resends the link until setup completes.
- Per-member watcher: mentions in channels the bot is in, own Gmail and Jira when
  connected, reminders, meeting reminders, overdue nudge and 09:15 digest.
- Setup page on `SETUP_PORT` (8765): Google one-time OAuth plus Jira API-token form.
  Google uses the HTTPS callback when `SETUP_BASE_URL` is HTTPS; otherwise it uses the
  registered loopback redirect and the member pastes the redirected URL back once.
- Member Google tokens and Jira credentials live under `data/<slack_id>/`, mode 600.
- `members --digest` added to the 09:15 job. 206 tests passing.

## 2026-11-03 (multi-user phase 1)

- Owner-only `allow: @Name` writes `users.json` and creates an isolated
  `data/<slack_id>/ledger.json` for that member.
- Allowlisted members run the same commands against their own ledger; replies go to their
  DM. Non-allowlisted users keep the note-to-Ridha path.
- A member's `add:` with no recipient stays in their ledger instead of becoming a
  reminder. `users.json` and `data/` are gitignored.
- Per-user watcher, digest, Gmail, Jira and self-serve setup remain later phases.
- 202 tests passing.

## 2026-11-03 (remind emoji ack)

- A successful `remind` now gets an ⏰ reaction on the command message instead of a text
  reply; a failed reaction still falls back to the reply.
- Backfilled the ⏰ on the 15:22 remind message, which had run before the change.
- Corrected Raj's DM from that command: stripped the trailing meta instruction and
  deleted the duplicate resend, leaving one clean reminder.
- 199 tests passing.

## 2026-11-03 (banter auto-arms for five minutes)

- Banter is off by default. A mean or hostile message opens a five-minute window for
  that channel; further meanness does not extend it. Watcher announces expiry.
- Manual `banter on/off/status` still available.
- 198 tests passing.

## 2026-11-03 (banter only when mean)

- Banter mode now answers only mean or hostile messages. Neutral chatter ("how would you
  describe yourself") gets silence.
- 197 tests passing.

## 2026-11-03 (banter upgrade)

- `banter on 2h [@person|all]`, `banter off`, `banter status` from Slack; no file editing.
- Replies are context-aware (question, greeting, praise, generic) and never repeat the
  previous line in that channel.
- Enabling is announced immediately; the watcher announces expiry.
- 197 tests passing.

## 2026-11-03 (banter for everyone until 2pm)

- `users: ["*"]` enables banter for everyone in a channel. On in `C0B0STVFTD2` until
  14:00 today at Arman's request; expires automatically.
- 196 tests passing.

## 2026-11-03 (banter off)

- Banter mode switched off. The bot only answers messages that address it: real
  mention, literal `@mini-reid`, or a DM. Re-enable `banter.json` only if XieYi spams
  again.
- 196 tests passing.

## 2026-11-03 (sass for swearing)

- Swearing or insulting the bot now gets a semi-mean silly line ("Bold words from
  someone with an overdue task.") instead of a note. Covers fuck/shit/bitch/ass/stupid
  and friends.
- 196 tests passing.

## 2026-11-03 (insults are not notes)

- Profanity and insults ("shut up", "stfu", "fuck", "idiot") now hit the guardrail
  ("Language. I'm a to-do list, not a punchbag.") instead of becoming notes.
- Dropped the insult note from the ledger.
- 196 tests passing.

## 2026-11-03 (no double replies)

- Every Slack message id is claimed in `bot_state.json` before a response, so duplicate
  events, socket redelivery or a restart cannot answer twice. Edits release the claim
  once for the corrected text.
- 196 tests passing.

## 2026-11-03 (be nice back)

- Praise and kindness ("loving mini-reid", "good bot", "thanks") get a short kind reply;
  it is not stored as a note.
- 195 tests passing.

## 2026-11-03 (literal handle, hostile banter)

- Channel messages with a literal `@mini-reid` now count as addressed; Slack does not
  always autocomplete the bot handle.
- Banter-listed users get the guardrail on hostile messages even without a mention.
- Classifier seeds cover praise ("loving mini-reid") so it gets the default reply.
- 194 tests passing.

## 2026-11-03 (learned task classifier, threat guardrail)

- Added `mini_reid/classifier.py`: pure-Python Naive Bayes over words and word pairs,
  trained from ledger rows, `not:` corrections and seed phrases. Social bot-addressed
  messages below 0.3 get the default reply and no note; commitments are never filtered.
- Guardrail now catches threats ("bomb", "kill", "deepseek", "if you keep messaging me")
  and hostile messages bypass banter mode.
- Dropped the threat note from the ledger.
- Weekly review doubles as the training loop: the model rebuilds from the ledger and
  `not:` corrections on every call, so no separate train step.
- 193 tests passing.

## 2026-11-03 (wider guardrail)

- Guardrail now catches "treat X nicely", "be nice to", "make peace with", "apologise",
  "say sorry", "stop fighting", "calm down", "mediate".
- "start huddle" gets a specific "I can't start huddles" reply instead of a note.
- Removed the stray huddle note from the ledger.
- 191 tests passing.

## 2026-11-03 (default reply for small talk)

- Bot-addressed greetings, "you there?", "test", thanks and similar get a default reply
  naming `add:`, `note:` and `ask:`. Nothing is stored.
- 191 tests passing.

## 2026-11-03 (banter mode)

- `banter.json` answers every message from listed users in one channel with a canned
  silly line until its `until` timestamp; Ridha can say `banter off`.
- Posted the guardrail line in the group chat and enabled one hour of banter for XieYi
  and Raj.
- 190 tests passing.

## 2026-11-03 (silly guardrail)

- "Tell X to stop harassing", "unblock me", "block both" and similar get a wry
  guardrail line in the channel instead of a ledger row. The bot does not referee
  personal fights.
- 189 tests passing.

## 2026-11-03 (reassign and mention targets)

- `reassign: <item> to <person>` moves an existing task to Waiting on others and records
  `assigned_to`.
- `assign:` now accepts a real `<@U…>` mention; `@XieYi` plain text already worked.
- 188 tests passing.

## 2026-11-03 (assign tasks to others)

- `assign: @Kasib send the deck by Friday` creates a row in Waiting on others with
  `direction: owed_to_me`, `assigned_to` and a parsed due date. `Kasib to …` also works.
- `remind` still sends a Slack DM; `assign` only tracks what they owe.
- 186 tests passing.

## 2026-11-03 (immediate reminders fixed)

- An immediate reminder to someone else called `send_dm` with a recipient it does not
  accept, raising `TypeError`; nothing was sent. Added `send_dm_to` and used it in both
  the bot and the DM poll.
- 184 tests passing.

## 2026-11-03 (notes command)

- `notes` lists notes on demand. They remain out of `list` task numbering and appear in
  the digest Notes section.
- 183 tests passing.

## 2026-11-03 (re-add reopens)

- Adding a task whose exact wording was previously done or dropped now reopens that row.
  Before, `merge` kept it terminal while the bot still replied "Added.", so the task
  vanished from `list`.
- 182 tests passing.

## 2026-11-03 (edited commands retry)

- Editing a bot-addressed message now re-runs the command once when the text changed,
  so a fixed typo takes effect. `remind` and `undo` are skipped to avoid duplicates.
- Row ids copied from `list` with brackets (`[2a308c]`) are accepted.
- 181 tests passing.

## 2026-11-03 (no channel pings)

- Replies to Ridha's own commands now go only to his DM; the channel gets just the
  ➕ / 📝 reaction. Reminder and error replies follow the same rule.
- 180 tests passing.

## 2026-11-03 (emoji acks for add and note)

- Successful `add:` gets a ➕ reaction; `note:` and `tonote:` get 📝. No text reply on
  success. Failures still reply with the reason.
- 180 tests passing.

## 2026-11-03 (task to note)

- `tonote: <item>` (alias `convert:`) turns an open task into a note: keeps the text and
  source, clears due date and priority, moves it to the Notes section. Stable ids still
  resolve it afterwards.
- 180 tests passing.

## 2026-11-03 (task priority)

- `priority: <item> 1-5` ranks a task; `high` / `medium` / `low` / `none` alias 1 / 3 /
  5 / clear. `[P1]` shows on the row and the digest/list sort priority before due date.
- 178 tests passing.

## 2026-11-03 (undo)

- `undo:` reverses the last mutating bot command. The ledger is snapshotted before each
  change; ten snapshots live in `ledger_undo.json`. Background watcher merges are not
  snapshotted.
- 174 tests passing.

## 2026-11-03 (stable ids and uncombine)

- `list` prints a stable short id per row; `185045` and `id:185045` both resolve
  regardless of how the numbered list shifts after edits, in every command that picks a
  row.
- `uncombine: <keep>` restores every row merged into it.
- 172 tests passing.

## 2026-11-03 (combine related tasks)

- `combine: <duplicate> into <keep>` merges two related rows. The duplicate is dropped
  with `closed_how: merged` and recorded in `merged_from` on the kept row. `#N` works
  for both sides.
- 170 tests passing.

## 2026-11-02 (not: dismisses meetings)

- `not: <meeting title>` cancels that meeting's pending reminder and persists the title
  in `calendar_ignores.json`, so it stays out of the digest and future reminders.
- Deleted the already-sent Chiropractor reminder DM.
- 168 tests passing.

## 2026-11-02 (only Ridha's meetings)

- Events with no attendees on a shared calendar are other people's diary entries.
  They are dropped unless Ridha is an attendee or the organiser. Removes the
  `Chiropractor` and `Personal block` rows.
- Deleted the pending `Personal block` reminder; the `Chiropractor` reminder had
  already fired.
- 166 tests passing.

## 2026-11-02 (triager channel ignored)

- Tags from `bd-triager-agent` (`C0B59LA0X5M`) no longer become ledger rows, and the
  bot ignores events from that channel.
- README, SPEC and HANDOFF record the current state, DM polling, meeting replies,
  Calendar consent and the 09:15 digest.
- Shared HTTP helper retries 5xx as well as 429, so a transient Calendar 503 does not
  blank the Meetings section.
- 166 tests passing.

## 2026-11-02 (task status)

- `status: <item> in progress | blocked | open` updates a task. The digest and `list`
  show the status on the row. `open` clears any stalled flags.
- 165 tests passing.

## 2026-11-02 (today's meetings)

- Digest gains a Meetings section: time, title and join link for today's timed events,
  across every visible Google Calendar. Declined, cancelled, all-day and focus-time
  items are dropped.
- Watcher schedules a Slack DM 10 minutes before each meeting with the join link and
  "Are you attending?". Deduped in `meeting_reminders.json`; Slack keeps the schedule.
- `mini_reid/google_auth` adds `calendar.readonly` to the existing Google token and
  keeps every Gmail scope.
- Meeting reminders say `yes` or `no <reason>`; the reply is recorded in
  `meeting_reminders.json` and confirmed in the DM.
- The watcher polls Ridha's recently active DMs with the user token, because Slack sends
  no events from a DM the bot is not in. Only owner `remind` messages are executed, and
  the confirmation goes to the bot DM.
- 162 tests passing.

## 2026-11-02 (reminders only reach Pantas members)

- A named recipient who is not in the workspace now gets a reply, instead of the
  reminder silently going to the sender. Slack DMs cannot reach people outside Pantas.
- Docs use workspace members in the examples; Daniel Hwang is an IOI contact.
- 153 tests passing.

## 2026-11-02 (reminders for anyone, immediate by default)

- A reminder recipient is no longer swallowed by mention stripping. `remind <@U…>`,
  typed `@handle`, and full names with spaces all resolve to the right person.
- Time is optional: `remind me to send the deck` sends the DM immediately; a time
  still schedules it in Slack.
- `remove:` and `delete:` are aliases for `drop:`, so removing a note no longer
  creates another note.
- `github.com` sender domains are ignored; `exim.com.my` maps to EXIM Bank under GHB.
- 152 tests passing.

## 2026-11-02 (overdue nudge follows the digest)

- The daily overdue DM now uses the digest row renderer: client name, relative
  due, sender with address, source time and an `open` link on every row.
- Fixed undated rows being counted as overdue: an empty due date no longer
  compares as before today. Those rows stay in No date.
- Digest moved to 09:15, after Ridha reaches work.
- 149 tests passing.

## 2026-11-01 (ready for the week)

- Slack app subscriptions saved: `app_mention`, `message.im`, `message.channels`,
  `message.groups`. Edits can now be acked; no bot restart needed.
- README, SPEC and HANDOFF record the subscriptions, the edit-ack dependency, and the
  week-start plan.
- 147 tests passing.

## 2026-11-01 (source context everywhere)

- Slack task lines show sender, channel, message time and link. When the model
  rewrote the title, the original message is quoted underneath.
- Email rows keep the full sender address: `Name (address)`, plus the Gmail link.
- `list` shows sender, channel and link on every numbered row.
- 147 tests passing.

## 2026-11-01 (drafts and epics are not tasks)

- Gmail drafts no longer become commitments. A draft is Ridha's own unsent
  writing, not an ask; the `[Action Required] Descriptions…` row was an old reply
  that already said the work was done.
- Jira issues carry `issuetype`. Epics, initiatives and themes are containers,
  not tasks, and are dropped. That removes `RIJ-Agent Tasks - Ridha` and
  `Eupe Corporation Berhad`.
- Dropped the three rows and recorded the corrections.
- 143 tests passing.

## 2026-11-01 (signal over noise)

- Strict actionability gate: a message becomes a task only if it asks for
  something ("can you", "please", "need the", an imperative opener), or is a
  channel mention. Questions with no ask, status updates, and other people's
  own plans are dropped. Channel mentions stay: they are the signal that matters.
- `list` numbers items. `#N` works with `done`, `due`, `snooze`, `drop`, `waiting`,
  `not`, and `edit` — so a rename does not depend on guessing the wording.
- Every reminder, including Ridha's own, is now a Slack server-side scheduled
  message. Watcher timing no longer delays a reminder.
- Cleaned seven non-tasks out of the ledger and recorded them as `not:` corrections.
- 140 tests passing.

## 2026-10-31 (edit, late DM alerts)

- `edit: <item> to <new name> [by <when>]` renames a task and, when a date is
  given, re-dates and reopens it.
- DM history is now paginated. Slack returns the oldest page first, so a busy DM
  hid later messages until the sliding window surfaced them hours later. That is
  why yesterday's DMs alerted this afternoon.
- 124 tests passing.

## 2026-10-31 (shared reminders)

- Anyone who tags or DMs the bot can set a reminder for themselves or a teammate:
  `remind me to … at 2pm`, `remind @Arman to … at 2pm`, `add: … at 2pm`.
- Reminders are scheduled with Slack `chat.scheduleMessage`, so they fire on time even
  when the Mac is asleep. The bot opens the DM with the recipient itself.
- Other people's reminders are private: no ledger row, no digest entry, no note to Ridha.
- Names resolve from the workspace user list; a mention is exact.
- 121 tests passing.

## 2026-10-31 (bot notifications, edit acks)

- Bot command replies from a channel are mirrored to Ridha's DM, so `add:` raises a
  notification immediately instead of waiting for the 08:30 digest.
- Edited messages that still mention the bot get a ✅. Edits are acknowledged, never
  replayed, so a command cannot be applied twice.
- Slack app now subscribes `message.channels` and `message.groups`; other channel
  messages are ignored unless they address the bot.
- 118 tests passing.

## 2026-10-31 (docs)

- README, SPEC and HANDOFF rewritten to match what is actually built.
- Plan document marked implemented and superseded.
- 115 tests passing. One entry per working session or material change.

## 2026-10-31 (to-do digest)

- Digest reads as a to-do list: counts header, Overdue, Today, This week, Waiting,
  No date. Relative due labels ("2d overdue", "today", "in 3d").
- Undated tasks no longer vanish after a day; they sit in "No date" until closed.
- Nothing closes on its own. A draft that never went out stays open; a sent email only
  proposes closure. Only `done:` or a Jira reassignment closes a row.
- 115 tests passing.

## 2026-10-31 (jira precision, links)

- Jira includes only issues assigned to Ridha. Comment mentions on other people's
  issues no longer surface (the Ramtin triage case).
- Every task line carries an open link again, including Slack DMs.
- 113 tests passing.

## 2026-10-31 (jira loop)

- Jira rows name the board when the issue is auto-assigned ("BO board"), and the real
  person when there is one.
- Jira query lists everything currently assigned, not only recently updated.
- Reassigning an issue closes its ledger row on the next run (`jira_reassigned`), so it
  leaves the digest automatically. Skipped entirely if the Jira fetch fails.
- 113 tests passing.

## 2026-10-31 (calendar noise)

- Calendar accept/decline/invite emails are dropped; one invite no longer becomes three tasks.
- Alerts collapse identical items.
- Jira rows show the assignee, not Ridha as reporter.
- A clean rebuild for the last 24 hours produced 5 real rows.
- 111 tests passing.

## 2026-10-31 (attribution and noise)

- Every line shows where it came from: person, then channel, DM, direct mail or
  bd@pantas.com alias, then the client name rather than its slug.
- Client attribution belongs to the rule matcher; the model no longer assigns clients.
- URL query strings no longer count as questions; URLs stripped from task text.
- DMs kept only when they ask something or carry a date.
- CI fixed: brief takes its date as an argument, so tests are clock-independent.
- 109 tests passing.

## 2026-10-31 (trustworthy digest)

- Jokes and short DM chatter no longer become tasks; Google boilerplate stripped.
- Duplicate tasks collapse in the digest.
- Brief is deterministic: counts, three most urgent, overdue by client. No model.
- Rules decide what is a commitment; the 3B model only improves wording. Given
  authority it deleted real asks and kept jokes.
- Gmail uses the subject line as the task name instead of the email's opening line.
- 106 tests passing.

## 2026-10-31 (names and better retrieval)

- Slack user IDs resolved to display names in DM captures.
- Model cannot return a client that is not a real slug; ID echoes are discarded.
- Index rebuilt with received mail: 753 passages (389 Gmail).
- Answers expand a hit back to its full message, so the answering sentence is not
  lost to chunking.
- Top overall match is never discarded by the client filter.
- 103 tests passing.

## 2026-10-31 (self-tag hardening)

- Slack mention form `<@U123|mini-reid>` now strips correctly; it previously fell through
  to a note instead of a command.
- Natural add phrasings: `task:`, `todo:`, `add this to my todo:`, `add <thing>`.
- `note that ...` works.
- 103 tests passing.

## 2026-10-31 (core coverage)

- Gmail now reads all inbox mail, not only unread. Opened-and-unanswered no longer slips.
- Slack DMs to Ridha are indexed as commitments; mentions never appear in a DM.
- Daily overdue nudge after 09:00, once per day, so aging work does not go quiet.
- 100 tests passing.

## 2026-10-31 (digest brief)

- Morning digest now opens with a written three-sentence Brief, then the sections.
- Ask synthesis uses the fast local model; 8B proved unusable on 8 GB (5 min, timeout).
- Gmail fetch no longer aborts the whole index on a single timeout.
- Synthesis strips model preamble.
- 98 tests passing.

## 2026-10-31 (better answers)

- Passages are cleaned at answer time: headers, address lists, URLs and Google
  boilerplate removed even if the index is stale.
- Unusable passages are dropped rather than shown.
- Passages carry dates; answers show when something was said.
- Synthesis step added: 8B local model writes 2-3 sentences with mandatory citations;
  rejected output falls back to verbatim excerpts.
- 97 tests passing.

## 2026-10-31 (catch-up)

- Catch-up on wake: on startup the bot answers questions addressed to it while the Mac
  was asleep, marked "answered late, I was offline". State in `bot_state.json`.
- SRSL mapped to Gamuda (`srslrt.com.my`), and client matching now also looks for a
  known client domain quoted inside the message.
- 96 tests passing.

## 2026-10-31 (index rebuilt)

- Index rebuilt: 561 passages, 200 Gmail with quote markers stripped.
- Project notes (SPEC, CHANGES, HANDOFF) no longer appear in work answers; they still
  answer questions about Mini-Reid itself.
- 94 tests passing.

## 2026-10-31 (search-style answers)

- Answers are the top 1-3 things Ridha actually wrote, verbatim, with sources.
- Similarity floor 0.55: below it, "I do not know." Measured: real questions score
  0.63-0.81, off-topic tops out at 0.46.
- Client named in the question scopes retrieval, with a top-up when filtering starves it.
- Gmail quoted-reply markers stripped.
- Tested five scenarios: IOI deadline, Gamuda dashboard, SRSL pending, DTI-Spark,
  and an off-topic control. The control correctly refused.
- 94 tests passing.

## 2026-10-31 (extractive answers)

- Answers are now verbatim excerpts from the best passage, with the source link. No
  generated text, so nothing can be invented.
- Client named in the question filters retrieval to that client; project notes are
  deprioritised over the client's own record.
- A failed index source keeps its previous passages and retries per message.
- Finding: the 3B model is unreliable at selecting and summarising. Extractive is the
  honest ceiling until a larger model is tested.
- 94 tests passing.

## 2026-10-31 (kb answers)

- Retrieval returns one passage per source document; long emails no longer fill every slot.
- Gmail passages strip HTML before indexing.
- Answer prompt now gives partial answers when evidence is partial, instead of always
  "I do not know".
- First real answer verified: Eupe waste mapping, citing the source message.
- 93 tests passing.

## 2026-10-31 (kb refresh)

- Knowledge index rebuilds itself nightly at 02:00 via `com.minireid.kb`.
- Rebuild is incremental: unchanged passages reuse their vectors.
- Decisions: knowledge stays local. GitHub Actions runs tests only; indexing in CI would
  require the Slack user and Gmail tokens in repository secrets.
- 93 tests passing.

## 2026-10-31 (knowledge base)

- `kb.py`: local retrieval over Ridha's own Slack messages, Gmail sent mail and local documents.
- Embeddings via Ollama `nomic-embed-text`; answers via `llama3.2:3b` with numbered citations.
- Slack command `ask: <question>`, allowed for Ridha and anyone in `KB_ALLOWLIST`.
- Full index build runs locally; `kb.json` is gitignored and never leaves the machine.
- 92 tests passing.

## 2026-10-31 (early)

- `remind:` and "remind me to ..." with a parsed time. Watcher fires it as a DM once.
- Plain sentences from Ridha become notes; questions route to list or help.
- Other people's plain sentences become notes with an instant DM. `list`/`find`/`help`
  from others no longer create empty notes.
- 88 tests passing.

## 2026-10-30 (night, final)

- Item matching is fuzzy: a fragment or any word order works, and an ambiguous match
  asks which one instead of guessing.
- 80 tests passing.

## 2026-10-30 (night, later)

- Model batches now split on failure until the bad item is isolated, so one malformed
  response no longer leaves a whole batch as raw text.
- 78 tests passing.

## 2026-10-30 (night)

- `not:` command: drops a false positive and records it in `corrections.json`.
- Those corrections are fed back into the model prompt as examples to ignore.
- `help` command and command list.
- `scorecard.py`: weekly recall check against a hand-written `expected.txt`.
- Watcher now rewrites new items through the model before alerting, and dedupes by source link.
- CI workflow runs tests on GitHub; live agent stays local.
- 77 tests passing.

## 2026-10-30 (late)

- Notes moved to their own digest section. They no longer sit among tasks.
- New Slack commands: `list`, `find:`, `due: <item> by <when>`, `snooze: <item> 3d`, `drop:`, `waiting: <item> on <person>`. Plus existing `add:`, `note:`, `done:`.
- Completion proposals: open rows are matched against sent mail. A strong match marks `closure: proposed` and appears under "Possibly done — confirm". Nothing auto-closes.
- Rule tightened: shared-alias email with no date and no direct address to Ridha no longer becomes a row.
- `com.minireid.model` installed: local model rewrite at 06:00, before the 08:30 digest.
- Model provider retries on HTTP/timeout/JSON errors; `null` client values normalised.
- 69 tests passing.

## 2026-10-30 (evening)

- Built `mini_reid` package: clients, ledger, extract, sources, render, cli, capture, slack_bot, providers, notify, watcher.
- Persistent `ledger.json` with stable ids, idempotent merge, terminal statuses that never reopen.
- Stalled detection: draft older than 1 day, past due, 5 working days without activity.
- Slack reader via user token (search + DMs); bot posts via bot token; one app, two tokens.
- Gmail reader across inbox, sent, drafts. Jira reader via API, verified against `pantas.atlassian.net`.
- Rules extraction: bots, Jira notification mail, sent mail and no-ask email filtered out; signatures stripped; HTML entities decoded; evidence capped at 200 chars.
- Local model rewrite via Ollama `llama3.2:3b` behind a provider interface. Chunked 5 per call, per-batch failure tolerated.
- Slack delivery: mrkdwn renderer, `*bold*` task, `from <person>`, only `open` is linked, DM items carry no link.
- Watcher every 2 minutes: new items only, ✅ reaction on the source Slack message, DM alert.
- Daily digest 08:30 to Slack DM.
- capture door: `add:` / `note:` / `done:` from Slack DM or mention; only the owner may mutate.
- Duplicate collapse by source link; duplicate Slack event suppression.
- Fixed: listener signature for slack_sdk, bot self-ingestion (digest captured as a task), duplicate rows after HTML unescape.
- Deleted 20 test bot messages from the DM; ledger rebuilt clean at 20 rows.
- Moved project to `~/mini-reid` with a Desktop symlink because launchd cannot run from `~/Desktop`.
- 56 tests passing.
