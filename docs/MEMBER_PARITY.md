# Member parity rule

Every user-facing change ships for the owner **and** every authorised member in
the same change. A feature is not done because it works in Ridha's DM.

## What "everybody" means

- Ridha (owner, `ledger.json`).
- Every person set up with `allow: @Name` (`data/<slack_id>/ledger.json`).

## Checklist for any feature or fix

- [ ] Command path: `_apply_command` runs against the sender's ledger, not the
      owner's. Members hit the same parser and the same bulk/text helpers.
- [ ] Capture path: `members.refresh` gets the same extraction, model title
      cleanup, `inbox` status and confirmation DM as `watcher.main`.
- [ ] Buttons and modals resolve the clicker through `ledger_for_viewer`, never
      hard-code `ledger_path`.
- [ ] `list`, Inbox, Triage & update, stale pickers and the digest all read the
      member's own ledger.
- [ ] Nudges (overdue, stale, meeting) accept a `user_id` and DM that person,
      with that profile's state file.
- [ ] Tests cover the shared helper; at least one test proves two different
      ledgers cannot cross.
- [ ] Docs updated in the same commit: `CHANGES.md`, `HANDOFF.md`, `SPEC.md`,
      `README.md` where behaviour is described.
- [ ] Member-ledger smoke test before merge when the change touches capture,
      buttons or triage.

## Owner-only by design

Not every command applies to members. These stay owner-only or restricted:

- `allow:` (only Ridha may authorise people).
- Banter controls.
- Anything gated by `KB_ALLOWLIST`.

That is a permission boundary, not a parity gap.

## Current parity status (2026-11-05)

| Feature | Owner | Members |
|---|---|---|
| Capture + inbox confirmation | yes | yes |
| Add / Not a task buttons, click ack + lock | yes | yes |
| Model title cleanup | yes | yes |
| Grouped `list` + Triage & update | yes | yes |
| Stale 18:00 nudge | yes | yes |
| Overdue nudge, reminders, meetings, digest | yes | yes |
| Bulk `done:` / `not:` by refs and pasted list | yes | yes |

## How this gets enforced

- PR description must say whether members were exercised.
- A change that touches `ledger_path`, capture or Block Kit without a member
  path is a review blocker.
- This file is the source of truth; update the table when a feature lands.
