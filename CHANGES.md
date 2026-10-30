# Changes

Append-only. Newest first. One entry per working session or material change.

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
