# Flying-car Mini-Reid: design

Date: 2026-11-05
Status: design approved. Subsystems 1 (eval harness) and 2 (auto-capture,
rules-only) shipped on 2026-11-05. Subsystems 3-6 remain.

## Outcome

Mini-Reid becomes the primary source for tasks, meetings and day-to-day events,
and plans the day. Charanya stops writing her own Slack to-do list because
Mini-Reid captures every task she would have written.

## Conventions we are willing to break

- Tagging before capture.
- A click per item before it can enter the list.
- Slack DM as the only interface.
- Fixed 09:15 digest and fixed nudge times.
- Meetings and reminders only on explicit request.
- Owner-only meeting scheduling.
- A local model that only rewrites titles.
- A Mac-only runtime that sleeps.

## Real constraints

- Other people's calendars are visible only through shared freeBusy.
- Client confidentiality and no external model without an explicit opt-in.
- Slack cannot embed Google Calendar or toggle Gemini meeting notes.
- Google Calendar/Meet APIs define what an invite can contain.

## Unreasonable version

Zero tagging and zero clicks for obvious items, continuous ingestion of every
signal, inferred commitments and meeting intent, booking before being asked,
automatic replanning when the day slips. Reaching it needs cloud uptime,
calendar/mail/Slack tools, and labelled data for routing and extraction.

## Proof

Charanya runs Mini-Reid in parallel with her self-written Slack to-do list for
one week. Acceptance:

- 95% or more of the tasks she would have written are captured.
- Fewer than one false task per day.
- By day five she stops writing her own list.

Judged by: Charanya.

## Subsystems and order

1. Ground truth and evaluation harness. This plan.
2. Auto-capture extraction and confidence policy. Depends on 1.
3. Always-on cloud ingestion and storage. Depends on 1 and 2.
4. Guarded action layer (book, remind, write). Depends on 3.
5. Planner and proactive day management. Depends on 4.
6. One-week Charanya pilot. Depends on 5.

Each subsystem gets its own plan and produces working, testable software.

## Data handling

Ground truth and message exports live under `data/eval/` which is gitignored.
No client content leaves the Mac for evaluation. Export files are read-only
inputs; generated reports contain counts and task text only when read locally.
