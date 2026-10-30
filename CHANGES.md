# Changes

Append-only. Newest first. One entry per working session or material change.

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
