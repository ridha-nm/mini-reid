# Workflow: meetings

`meet:` from first request to booked event.

## Flow

1. `parse_meeting` splits guests from topic. Topic separators: `about`,
   `on`, `for`, `regarding`, `re`, `review`, `to discuss`. Stray words
   ("today") never drop a resolved guest. Guests may be mentions, `@Name`
   or full names; comma/`and` separated.
2. `propose_slots(day=…)` checks freeBusy for one working day at a time, all
   free 30-minute slots (up to 20). The proposal opens on the first working
   day that has a slot and pages the next five weekdays with
   `◀ Previous day` / `Next day ▶`.
3. The proposal is posted **in the channel where the request was made**
   (threaded), not in Ridha's DM; it shows Title/With/Duration/Time zone, a
   busy snapshot and **Pick** buttons.
4. Anyone **on the invite** (organiser or attendee, resolved by email via
   directory/profiles) may pick a slot. Non-invitees get an ephemeral note.
5. Picking creates the Google event with a Meet link, updates the proposal
   message in place, and posts a `✅ Scheduled: … Booked by @who`
   acknowledgement into the thread.
6. `remember_meeting` keeps the record for reminders, RSVP and
   reschedule/cancel; creator stays the organiser.
7. Error replies (no free slot, calendar read failure) stay private to the
   organiser.

## State / code / tests

- State: `created_meetings.json`, `meeting_reminders.json`,
  `pending_meet` in `bot_state.json`
- Code: `meetings.py` `meeting_ui.py` `slack_bot` (meet block, `meet_day`,
  `meet_slot`)
- Tests: `test_meetings.py` (paging, guest parsing, confirmed picks)
