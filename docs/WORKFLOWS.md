# Workflows Mini-Reid is learning

One page per behaviour, with the state files, code and tests that belong to
it. Behaviour changes should update its workflow page in the same change.

| workflow | learns / does | page |
|---|---|---|
| Capture and triage | turns messages into rows; rules + Inbox confirmation | [capture.md](workflows/capture.md) |
| Corrections and learning | `not:` reasons, classifier examples, duplicate titles, channel mutes | [corrections.md](workflows/corrections.md) |
| Slack List mirror | Task/Status/Due/Source/Assigner, two-way sync, schema rebuild | [slack-list.md](workflows/slack-list.md) |
| List and paging | 25 rows per page, Prev/Next in place, Inbox and Notes | [list-paging.md](workflows/list-paging.md) |
| Daily digest | 09:15 DM as blocks (one message), retry after 09:30 | [digest.md](workflows/digest.md) |
| Meetings | day-paged proposals in the channel, invitee picks, booked ack | [meetings.md](workflows/meetings.md) |
| Reminders | Slack-scheduled DMs plus a row on the recipient's list | [reminders.md](workflows/reminders.md) |
| Triager routing | tag the account owner on the first Demo App card, once | [triager-routing.md](workflows/triager-routing.md) |

## Where the evidence lives

- `corrections.json` + `not_reason` on rows — what was rejected and why
- `learning_events.json` — commands people actually used
- `muted_sources.json` — channels capture has stopped reading
- `routing.json` — email/domain/company → account → owners
- `triager_routed.json` — tickets already tagged
- `digest_delivered.json`, `reminder_log.json`, `created_meetings.json` —
  what was sent

## Invariants

- The owner and every authorised member get the same feature
  (`docs/MEMBER_PARITY.md`).
- Any mutation that affects a person's list syncs their Slack List
  immediately; the watcher cycle is the backstop.
- The bot stops at assignment for triager tickets; meetings stop at
  booking.
