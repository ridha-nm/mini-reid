# Ideas — answering anything, flying-car edition

Date: 2026-11-05
Status: ideas only; nothing here is built unless a phase says so.

## Goal

When someone asks Mini-Reid anything, it answers from the right live source,
not only from the local knowledge base. [Brain is explicitly out of scope —
not wanted, not used.]

## What exists today

### MCP servers configured on this Mac

| Server | Gives | Status |
|---|---|---|
| `gmail` | search, read, send mail | connected |
| `bd-command-centre` | tasks, meetings, stock-take per workspace | connected |
| `databricks-sql` | SQL over Databricks | needs authentication |
| `chrome-devtools` | drive a real browser | connected |
| `penpot` | design files | connected |
| `bd-deploy` | deploy static apps | connected |
| `pantas-brain` | wiki, decisions, risks | connected, **excluded by request** |
| `slack-api` | official Slack MCP, user token, search/read/write | connected |

Not installed: Jira, Calendar, Drive, web-search MCP.

### Built-in tools in a Claude Code session

- `WebSearch`, `WebFetch` — public web.
- `Bash` with `gh`, `gcloud`, `aws`, `curl`, `jq` — GitHub, GCP, AWS APIs.
- Filesystem, git, tests.

### APIs the bot already holds tokens for

- Slack bot + user token.
- Gmail and Google Calendar (`gmail.readonly`, `calendar.readonly`).
- Jira (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`).
- `GEMINI_API_KEY` — present in `.env`, unused in code.
- Google OAuth relay for member setup.

### APIs reachable but not wired

- Google Drive/Docs/Sheets — extra OAuth scope.
- Databricks — authentication.
- Public web — Gemini key, Claude API, or a search API.
- Weather, maps, news — no keys.

## Constraints

- Client confidentiality: no client content to an external model without an
  explicit per-question opt-in. SPEC currently says no client content to a
  free-tier model and nothing outside the workspace.
- Bot runs on the Mac; no always-on cloud.
- Local 3B model can rewrite titles. It cannot reliably choose tools.
- Every tool answer must cite its source.
- Per-user allowlist already exists (`KB_ALLOWLIST`); keep it.
- No Brain integration.

## Phases

### P0 — today

`ask:` searches `kb.json` only. Extractive, 0.55 similarity floor, sources listed.

### P1 — deterministic routes (smallest useful step)

Explicit prefixes, no model routing:

- `ask slack: <q>` — live `search.messages`, channels and DMs the bot can see.
- `ask email: <q>` — live Gmail query, not just the nightly index.
- `ask jira: <q>` — JQL/live issue search.
- `ask calendar: <q>` — upcoming events for the next N days.
- `ask tasks: <q>` — BD Command Centre task query.
- Plain `ask:` stays local KB.

Each route returns 3–5 cited hits and degrades to "I do not know" on failure.
No external model.

### P2 — automatic source choice

Rules-first router: question words map to sources ("email", "ticket", "meeting",
"this week"). Optional second opinion from the local model but never the final
authority. Fallback chain: KB → Slack → Gmail → Jira. Answer labels the source
used so a wrong route is visible and correctable.

### P3 — general knowledge

Answer public/general questions with Gemini (key already present) or a search
API. External by definition: gate behind owner-only use, log every query, and
never send ledger or client text.

### P4 — agent loop with tools

A real tool-calling model with:

- read-only tools first: Slack search, Gmail search, Jira, Calendar, Databricks.
- a hard allowlist per user and per source.
- max tool calls and max spend per question.
- every call logged with question, tool, arguments hash, latency, result size.
- citations rendered under the answer, same as KB.

This is the first phase that needs an external model for routing. Decide the
privacy rule before starting.

### P5 — flying car

The assistant stops waiting to be asked:

- understands a thread, proposes the task, asks one confirmation click.
- drafts the reply or the Jira comment; human sends.
- notices commitments in outbound mail and proposes the ledger row.
- reconciles what was said in Slack against what is in Jira/Databricks.
- weekly "what changed without you" brief.
- every proactive action is a proposal with Add / Ignore, never automatic.

## Experiments to run before committing

1. ~~Slack MCP as a read-only connector~~ — enabled as `slack-api`.
2. ~~Live Slack search latency and result quality~~ — wired into owner `ask:`.
3. Slack List two-way sync under load: rate limits and lost-edit detection.
4. File ingestion from `file_shared` for `ask:` context.
5. DND/presence quiet hours for nudges and reminders.
6. Jira search via existing token: one query, cited.
7. Gemini answer quality and cost on non-client questions.
8. Databricks auth path, then one read-only SQL tool.

## Metrics

- answer hit rate on a hand-written question set.
- wrong-source rate (answered from the wrong system).
- p95 latency per route.
- external-model spend per day.
- confirmations per day vs ignored proposals.

## Open questions

1. Is any external model allowed, and for which data classes?
2. ~~Slack MCP or direct Slack API calls?~~ Both: official MCP enabled for
   Claude sessions; the bot keeps direct Web API calls.
3. Which Google scopes are acceptable for Drive/Docs/Sheets?
4. Databricks: which catalog/schema is safe to expose, and to whom?
5. Should non-owner members get tool answers at all, or only the owner?
