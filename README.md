# Mini-Reid

Daily digest of everything that needs you, pulled from Slack and Gmail. Read-only.

**Nothing is ever sent.** No reply, no reaction, no label change.

## Run

```bash
python3 -m mini_reid.cli --days 1                      # rules only
python3 -m mini_reid.cli --days 1 --model llama3.2:3b  # + local model on unclear items
python3 -m mini_reid.cli --capture "add: Eupe item by Friday"
python3 -m mini_reid.slack_bot                         # Socket Mode listener
```

Tests: `.venv/bin/python -m pytest tests/ -q`

`digest.py` is the original read-only prototype. `mini_reid.cli` supersedes it.

## Files

| File | What |
|---|---|
| `digest.py` | the whole thing — collectors, triage, render |
| `.env` | secrets. `chmod 600`. Gitignored. Never commit. |
| `digest.md` | output, regenerated each run. Gitignored. |

## Credentials

Reuses existing read-only creds for the first pass:

- Slack — user token via `SLACK_ENV`
- Gmail — OAuth refresh token via `GMAIL_CREDS` / `GMAIL_TOKEN`. The script only calls
  read endpoints, but the current token also carries `gmail.send`. Swap in a read-only
  token before this runs unattended.
- Jira — **not connected.** Add `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` to `.env`.
  Create a token at <https://id.atlassian.com/manage-profile/security/api-tokens>.

Replace with the agent's own credentials before this leaves your machine.

## The Gemini key

`GEMINI_API_KEY` is **not used yet** — the digest is deterministic, so no message
content leaves this machine.

When drafting is added, the free tier is a problem: Google's free tier reserves the
right to use your inputs to improve its products. Your mail and Slack contain
client-confidential material (IOI, Eupe, SRSL, Gamuda). Use a paid tier for any
path that sends client content to a model.

## Not built yet

- Telegram delivery + urgent alerts
- GitHub Actions schedule
- Draft replies (approval-gated)
- Jira collector (code exists, needs credentials)
