# Mini-Reid — Build Spec

Status: agreed 30 Oct 2026. Supersedes the earlier problem-framing notes.

## Outcome

Every commitment Ridha makes is tracked to closure. Nothing slips, nothing lives only
in his head, and routine internal asks get acknowledged without him.

## The unreasonable version

Zero missed commitments. Zero chasing. Continuous, before anyone notices.

That needs a different system, not a bigger prompt. The daily digest is one output of
it, not the system itself.

## What this is

A persistent commitment ledger with three faces:

1. **Watch** — reads Slack, Gmail, Jira, calendar and meeting notes.
2. **Remember** — extracts commitments into a ledger that survives between runs.
3. **Act** — posts a forward-looking digest, acknowledges small internal asks, and
   escalates anything that needs a human.

## Non-goals

- Never speaks as Ridha. The bot posts under its own identity.
- Never sends client-facing messages.
- Never creates a commitment on Ridha's behalf.
- Never answers a question it cannot ground in the ledger or a linked document.
- No autonomous sends of substance. Acknowledgement only.

## Failure modes this must catch

Five ways work goes missing. The first is the one everyone builds for. The rest are why
the first one alone does not fix the problem.

1. **Unseen ask.** A message arrives, it is read, it is forgotten.
2. **Stalled work.** It is seen, started, and dropped halfway. The real case: an SRSL
   reply about Gamuda was drafted and left unsent for a week. The draft was already
   "read", so an unread search will never find it. This is a first-class state, not an
   edge case.
3. **Channel gap.** The ask arrives where nothing can read it: WhatsApp (Eupe dashboard
   items), a corridor, a call. No API exists for a personal WhatsApp account. This must
   be captured manually or it is invisible.
4. **Recurring cycle.** Gamuda biweekly produces the same categories every fortnight.
   Treated as one-off items, carry-over is lost and the last cycle silently expires.
5. **Silent close.** The work is finished but nothing marks it done, so the ledger nags.

## Client filter

`bd@pantas.com` is a shared BD alias. Everyone in BD receives it, so the recipient
field is not a signal. Relevance is judged by client and by direct address.

Source of truth is **Ridha's full list**, not the hub's member field. The hub currently
records him against four clients only; the list below is authoritative and the hub is
out of date.

| Group | Clients |
|---|---|
| Direct | IOI, Knight Frank, Gamuda, Eupe, Kelington, TMK |
| SAFE | SFIA, Suslab, DTI |
| GHB | Bank Rakyat, Agrobank, Maybank, and other banks as they appear |
| GVC | Kossan, POS Malaysia, Ajinomoto, and other GVC accounts as they appear |

Known sender domains: `ioiproperties.com.my`, `gamuda.com.my`, `gamudaland.com.my`,
`gamuda.com.au`, `my.knightfrank.com`, `eupe.com.my`, `kelingtongroup.com`,
`tmkchemical.com`, `pos.com.my`, `kossan.com.my`, `suslab.net`,
`dtinfrastructure.com.au`.

Unknown today: SFIA, Ajinomoto, and the GHB banks. These are never guessed. An
unmatched sender domain lands in a review bucket and Ridha confirms it once, after
which it is remembered.

Matching rules:

| Signal | Bucket |
|---|---|
| Client match, and Ridha in To, Cc, or the greeting | Needs a look |
| Client match, `bd@pantas.com` only | FYI, collapsed |
| No client match, but Ridha addressed directly | Needs a look, never dropped |
| No client match, alias only | Collapsed, not deleted |

## Decisions already made

| Decision | Choice |
|---|---|
| Reply authority | Acknowledge and answer small asks only, in the bot's own name |
| Audience | Internal Slack only |
| Delivery | Slack DM and channel post only. Telegram dropped in v1. |
| Data handling | Client content never goes to a free-tier model |
| Hosting | v1 runs locally on Ridha's Mac via launchd, while the machine is on. No cloud, no model calls. GitHub Actions and always-on move to P2. |
| Model provider | Paid Gemini Flash, behind a small provider interface. GitHub Models was retired on 30 July 2026, so there is no free `GITHUB_TOKEN` route any more. Azure AI Foundry is the drop-in alternative. Free tiers remain unsuitable for client data. |
| Prototype | Forward-looking 7-day digest built from the ledger |
| Pass bar | 95% of real tasks and deadlines captured, over two weeks |

## Architecture

```
sources ──> extract ──> ledger.json ──> render ──> Slack / Telegram
                          │
                          └──> act (acknowledge, answer, escalate)
```

### 1. Sources

| Source | Access | Status |
|---|---|---|
| Slack | Bot token, `channels:history`, `im:history`, `chat:write` | new bot, creds posted |
| Gmail Inbox | OAuth refresh token, read-only | works |
| Gmail Sent | same token, read-only | **new:** closure signal |
| Gmail Drafts | `drafts.list`, read-only | **new:** stalled-work signal |
| Jira | API token | missing |
| Calendar | `calendar.readonly` | token exists, unused |
| Meeting notes | Gmail (Gemini, Fathom recaps) | arrive already |
| WhatsApp | none | **manual capture only** |
| Stock-take hub | reconciled status | not deployed yet, integrate later |

Two entrances to the ledger:

- **Automatic** where a readable source exists.
- **Manual** where it does not. A three-second capture door: DM the bot
  `add: Eupe dashboard item X by Friday` and it lands in the ledger with Ridha as the
  source. This also covers the corridor and the phone call.

### Slack identities

Two tokens from one Mini-Reid app, deliberately separated:

- **Reader:** the Mini-Reid user token (`xoxp`). It can call `search.messages` and see
  Ridha's DMs. A bot token cannot do either. It is never used to post.
- **Poster:** the Mini-Reid bot (`xoxb`). It posts the digest and acknowledgements under
  its own name. It never impersonates Ridha and never DM's an external person.

The stock-take connector is no longer used. Mini-Reid owns its own app, scopes and
tokens, so revoking it cannot break anything else.

A bot token cannot search and cannot see 1:1 DMs. That is why both tokens come from the
same app, and why impersonation is not the workaround.

Threads matter more than mentions. A commitment made in reply to someone else is
invisible to `search.messages`. Read `conversations.replies` for any thread that
touches Ridha.

### 2. The ledger (the missing organ)

Everything today is stateless. The digest is regenerated and forgotten. Without
persistence there is no reminder, no follow-up and no learning.

```json
{
  "id": "sha1(source + native_id + normalized_what)",
  "direction": "owed_by_me | owed_to_me",
  "what": "Send the FSD to Kasib",
  "source": "slack | gmail | jira | calendar | notes | manual",
  "source_link": "https://gopantas.slack.com/archives/...",
  "evidence": "exact quoted text",
  "due": "2026-10-31",
  "due_confidence": 0.8,
  "cycle": "gamuda-biweekly | null",
  "status": "open | stalled | blocked | done | dropped",
  "stalled_since": null,
  "ack_policy": "bot_may_ack | never",
  "closure": "open | proposed | confirmed",
  "created_at": "2026-10-30T09:12:00+08:00",
  "closed_at": null,
  "closed_how": "sent_email | meeting_note | manual"
}
```

Rules:

- One row per commitment. The id is `sha1(source + native_id + normalized_what)`, so one
  message may produce several rows, including one `owed_by_me` and one `owed_to_me`.
  Re-extraction is idempotent: same source plus same normalised wording yields the same
  id, even if the model paraphrases first.
- Evidence is a verbatim quote capped at 200 characters plus the permalink. Stored in
  the private repo. Full message bodies are never stored.
- Status transitions are append-only. Never delete, mark `dropped`.
- `owed_by_me` drives the digest. `owed_to_me` drives follow-ups.
- **Stalled is a status, not an absence.** Three triggers: a draft older than one day;
  an open row past its due date; an open row with no activity for five working days.
  "Touched" means Ridha posted in the thread or emailed on it after the commitment.
  This is why P1 reads Sent mail, not just the Inbox.
- **A recurring cycle carries over.** Items from the last Gamuda cycle that are still
  open appear in the next one, marked overdue against their original date.
- **Closure is proposed, not assumed.** A sent email or a meeting note raises
  `closure: proposed`. Only a matching confirmation or an unambiguous match sets
  `done`. A wrong close is worse than a wrong open.

Storage: `ledger.json` committed back to the private repo each run. Laziest thing that
survives an ephemeral runner. Upgrade to SQLite on a VPS if volume or write conflicts
become real.

### 3. Extraction

Two passes:

- **Rules first.** Explicit dates, `can you`, `please`, `by Friday`, Jira assignments,
  calendar invites with an ask. Cheap, deterministic, auditable.
- **Model second.** Only for thread-level commitments the rules miss. This is where a
  paid no-training tier is required, because thread content includes client material.

Every extracted row keeps its evidence quote so a wrong row is visible, not silent.

### 4. Rendering

Daily, forward-looking, not backward:

- **Overdue** — past due, still open.
- **Due today and tomorrow.**
- **Due this week.**
- **Waiting on others** — `owed_to_me`, where a follow-up is due.
- **New since yesterday.**

Each line: what, who, due, source link. Nothing else.

### 5. Acting

Allowed without approval:

- Acknowledge an ask: "Noted, Ridha has this. He will confirm by <date>." Only when the
  ask is matched to a ledger row **and** `ack_policy` is `bot_may_ack`.
- Answer from the ledger: status of a tracked item, a link to a document.
- Escalate to Ridha when ungrounded.

**Acknowledgement policy: allow by default, deny list overrides.** The bot may
acknowledge small asks in its own name, except for people on the deny list. Named today:
**Syaheedah** and **Max**. If either tags Ridha, the bot stays silent and flags the
message; Ridha replies himself. The deny list grows only from his explicit corrections,
never from inference. A per-channel deny entry works the same way.

Acknowledgement is still limited to asks matched to a ledger row. It never creates a
commitment, never answers without a citation, and never leaves the internal workspace.

Not allowed:

- Any client-facing message.
- Any new commitment.
- Any answer that is not grounded in a ledger row or a linked document.
- Any DM from the bot to a person outside the internal workspace.

## Phases

| Phase | Deliverable | Verification |
|---|---|---|
| P0 | Read-only digest (done) | runs, produces digest.md |
| P1 | Ledger + forward 7-day digest + stalled detection (drafts and Sent mail) + manual capture door. Rules only, no model. | 80% of a blind manual list, including drafts |
| P2 | Model extraction for thread commitments; recurring cycles declared in config | 95% recall, fixture set, precision |
| P3 | Slack bot posts digest; acknowledgements with the deny list enforced | bot identity, never Syaheedah or Max |
| P4 | Closure proposals from Sent mail and meeting notes | proposals reviewed, no silent closes |
| P5 | Grounded Q&A on tracked items | every answer cites a row |
| P6 | Learning from approvals and corrections | approved edits change future drafts |
| P7 | Stock-take hub integration | once the hub is deployed |

## Acceptance criteria

- **P1 pass:** the forward 7-day digest contains at least 80% of the commitments Ridha
  actually has, including stalled drafts and manually captured items, measured against a
  list he writes on Friday before seeing the digest.
- **P2 pass:** 95% recall on the same measure, across readable sources only.
- **Precision:** no more than 2 in 10 rows marked wrong or already done.
- **Stalled:** any draft older than one day surfaces. The SRSL case would have shown on
  day two.
- **Evidence:** 100% of rows carry a verbatim quote and a working link.
- **Identity:** 0 messages posted as Ridha. Audit log proves it.
- **Acknowledgement:** 0 acknowledgements for Syaheedah, Max, or anyone added to the
  deny list.
- **Closure:** 0 silent closes. Every `done` is either confirmed or an unambiguous match.
- **Grounding:** 0 bot answers without a cited ledger row.
- **Failure is loud:** an auth expiry or failed run produces an alert that run.

## Constraints

Real:

- Client confidentiality. No client content to any free-tier model.
- The bot is identifiable and never impersonates Ridha.
- Internal Slack only.
- Every claim traceable to a quote.

Convention, changeable later:

- Daily cadence, mentions as signal, read-only access, one credential per source.

## Risks

| Risk | Mitigation |
|---|---|
| 95% recall unreachable with rules alone | P2 model pass, fixture set, weekly manual audit |
| GitHub cron drift (5 to 15 min) | acceptable for daily digest; move to VPS if alerts must be instant |
| Bot cannot read channels it was not invited to | join explicitly, list channels in config |
| Slack rate limits on thread reads | incremental reads since last cursor |
| False commitments ("we should do X") | require an explicit assignee or ask, keep evidence quote |
| Ledger in repo exposes work items | private repo only; no message bodies, only task titles and links |

## Builder calls made

Settled here rather than bounced back, so the plan can start:

- One message may hold several commitments. Id includes the normalised wording.
- Stalled has three triggers and needs Sent mail in P1.
- Cycles arrive in P2, declared in `clients.json`. Not P1.
- The review bucket surfaces in the digest. Confirming is a DM to the bot
  (`domain acme.com = kelington`), and the mapping is remembered.
- Availability drops out of small asks. Calendar is not in scope. Small asks are:
  status of a tracked row, and a document link.
- 95% is measured over readable sources only, against a list Ridha writes on Friday
  before seeing the digest. Writing it from the digest would be circular.

## Open questions

1. Paid model provider and monthly ceiling.
2. Which channels the bot joins on day one.
3. Sender domains for SFIA, Ajinomoto, and the GHB banks. Confirmed once, then
   remembered.
4. Where document links come from: Drive search, or pasted into the capture door.
5. How long closed rows are retained before pruning.
