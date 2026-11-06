# Mini-Reid — weekly capability update

Append a new dated section every Friday. Each section describes what the bot
can do *now*, not a commit log.

---

## Week ending Fri 06 Nov 2026

Mini-Reid is a personal commitment ledger that runs on the Mac. It reads Slack,
Gmail and Jira, keeps what someone owes in a ledger, and answers in Slack DM.
Each person has their own ledger and their own digest; the owner and allowlisted
members never see each other's lists.

### Capture

- Sources: Slack channel mentions, Slack DMs, Gmail inbox (read and unread),
  Jira issues assigned to the person.
- **Auto-capture (rules only, no model):** obvious items open directly —
  - a Slack @mention with an explicit ask (`can/could/would/will you`, `please`
    + a request verb, `action required`, `we need/need you`);
  - a Slack DM with an explicit ask or a due date;
  - a Gmail item addressed directly in To, with an ask or a due date.
- Assigned Jira issues and everything else wait in **Inbox**. Uncertain items
  arrive as a DM with **Add to list** / **Not a task**.
- **Clear Inbox (N):** 10 pending rows at a time; tick the ones that are NOT
  tasks, the rest are added, then it advances to the next page.
- Message shortcut **Add to Mini-Reid** and 📌 reaction capture a message into
  the clicker's ledger without tagging the bot.
- Plain DM to the bot becomes a task for members, no prefix needed.
- A long paste from Ridha is saved as a note, and the reply offers **Keep as
  note** / **Make it a task** / **Discard** instead of silently noting it.
- Clients: Gmail can be filtered to the person's client list; `clients` shows it,
  `clients: Eupe, Gamuda` changes it. Portfolios GHB/GVC/SAFE supported.
- Extraction drops bots, the triager bot, calendar responses, Jira notification
  mail, sent mail, chatter, playful requests, status updates and newsletters.

### Organising

- `list` is sectioned: **My reminders**, **Reminders I sent**, **My tasks**,
  **Tagged by others**, **Inbox**, **Notes**. Numbers are global and work in
  every command; stable short ids (`abc123`) also work.
- Statuses: open, in progress, blocked, stalled, done, dropped. Priority 1–5.
  Due dates, waiting-on-others, client tags.
- Commands include `add:`, `note:`, `assign:`, `reassign:`, `done:`, `drop:`,
  `due:`, `edit:`, `snooze:`, `waiting:`, `status:`, `priority:`, `combine:`,
  `uncombine:`, `convert:`/`tonote:`, `undo:` (10 deep), `not:`, `find:`,
  `list`, `notes`, `reminders`, `clients`, `ask:`, `meet:`, `help`.
- Bulk actions: `done 7, 9`, pasted numbered lists, `not:` on several rows or
  notes. Triage modal sets one status across selected rows.
- **Done acknowledgements:** a Slack-tagged task marked done DMs the original
  asker once. Marking done in the Slack List DMs the person who did it.
- Native **Slack List mirror** per person: title, status, due, source. Edits
  flow back; deleting a List row drops the task. Every live task is mirrored
  (up to 500). Done rows are removed from the List and kept in the ledger as
  the archive. Source links for Slack rows open the message inside Slack.

### Reminders

- `remind me …`, `remind @Name …`, `add: … at 2pm`. Time optional → sent now.
- Timed reminders are scheduled in Slack (server-side), survive sleep.
- **Multi-recipient:** one shared text for several people
  (`remind @Raj, @XieYi and @Lynnette to send updates at 5pm`), or one
  `@Name <item>` line per person with a shared time line.
- Any workspace member can use `remind` — no ledger access. Every recipient
  gets their own reminder DM and a reminder row on their own list.
- Reminder audit: `reminders` shows pending, sent, and whether the DM got replies.
- Optional DND quiet hours (`RESPECT_DND=1`, off by default).

### Meetings

- `meet: @A and @B about <topic>` (also `on`, `to discuss`, `review`) reads all
  calendars, shows busy blocks, offers five free slots at the requested duration,
  lets you edit title/duration/notes, then creates the Google event with a Meet link and invites
  everyone. Meeting reply: `yes`, `no <reason>`, `moved <note>`, or
  `reschedule to <time> <note>` (moves the event, keeps the duration, notifies
  attendees) or `cancel <note>`.
- Any duration: `meet: @A about X for 45 minutes` / `for 1 hour` (15–180), or
  change it in the **Edit** modal alongside title and notes.
- 10-minute reminder DM before each meeting. Attendees of bot-created meetings
  get their own DM with **Attending** / **Can't attend** buttons.

### Asking questions

- `ask:` order: ledger → ingested Slack files → live Slack search → local
  knowledge base. Answers are extractive with sources, never invented.
- Anyone outside the member list can ask a general question: the answer is a
  private DM from the local knowledge base only (no ledger, files or live
  Slack).
- File ingestion: share a file (text, Markdown, CSV, JSON, PDF, DOCX, XLSX) in
  a channel the bot is in; react 📄 to ingest older files. Summary goes to the
  owner only.
- `ask:` can answer pending/open/due/task questions with counts, dates and
  links, filtered by client.
- Weekly scorecard and a local Naive Bayes classifier learn from `not:`
  corrections.

### Team

- Owner runs `allow: @Name`; each member gets an isolated ledger, Gmail/Jira
  credentials, reminders, nudges and 09:15 digest.
- Member parity: capture, auto-capture, triage, sections, Clear Inbox, Slack
  List mirror, done acknowledgements and acknowledgements behave the same for
  owner and members.
- **App Home** dashboard: per-person task stats, meetings, top focus items,
  Open Slack List, Triage Inbox, Refresh. Non-members get a capabilities page
  with Request access and Message Ridha.
- `/mini-reid` slash command: list, help, add, remind, meet; replies in DM.

### Delivery and reliability

- 09:15 digest DM with counts, brief, meetings, overdue/today/this week/no date,
  waiting and notes. Failed digests retry after 09:30.
- Overdue nudge after 09:00, 18:00 stale nudge with inline status picker (max
  three per row), meeting reminders.
- Catch-up sweep replays commands the socket missed while the Mac slept.
- Everything runs locally on the Mac and only while it is awake. No cloud
  database; client content does not leave the machine for extraction.
- 400 tests pass.

### Changed this week

- Auto-capture shipped: obvious rows skip the click; Inbox keeps the rest.
- List split into the six sections above; global numbering.
- Clear Inbox paged modal.
- Done acknowledgements in both directions.
- Multi-recipient and per-person reminders; non-members may use `remind`.
- Slack List links open in the Slack app.
- Stopped model-invented rows (chatter DMs, boilerplate mail) from becoming
  open tasks.
- Jira issues now ask for approval before joining the list; long pastes offer
  Keep as note / Make it a task / Discard.
- Meeting attendees get RSVP buttons; the organiser can reschedule or cancel
  with a note, pick any duration when setting the meeting or in Edit, and cancel
  any upcoming meeting by name with `cancel: <name>`.
- Slack List now mirrors every live task (was capped at 50); done rows drop off
  it and stay archived in the ledger.
- Non-members can ask general questions privately (KB only); immediate
  reminders drop a leading "now"; festive greetings no longer become tasks.
- Removed Gmail/Jira link unfurls: unused, and they rendered a card per task
  link in the digest.

### Known limits

- Mac must be awake; sleep pauses capture, digests and reminders until the next
  cycle.
- Slack coverage is channels the bot has been invited to; untagged channel asks
  and untagged thread replies are not captured.
- Gmail and Jira need the person's setup; email senders cannot be DM'd for
  acknowledgements.
- Auto-capture is deliberately narrow — imperative-only channel mentions,
  undated DMs without an explicit ask, and shared-alias mail stay in Inbox.
- WhatsApp and calls are manual capture only.
- Answers are extractive; the local model only rewrites task titles.
