# Mini-Reid setup

Two ways to use Mini-Reid:

1. **Join an existing bot** — you are a teammate on someone else's instance.
2. **Run your own** — you own the Mac, the Slack app and the credentials.

---

## 1. Join an existing bot (teammate)

1. Ask the owner to run this in Slack, tagging you:

   ```
   @mini-reid allow: @YourName
   ```

   The bot DMs you a one-time setup link (24 hours).
2. Open the link. Connect Google (Gmail read-only + Calendar read-only).
   Jira activates automatically from the workspace token, scoped to your
   Jira account.
3. Run `help` in the DM. You get your own private ledger, reminders,
   meeting reminders and morning digest. Nothing is shared with the owner.

Ask the owner to invite `@mini-reid` to any channel where people tag you;
the bot only reads channels it has joined.

---

## 2. Run your own

### Prerequisites

- macOS (the daemons use `launchd`; the Python code runs anywhere)
- Python 3.11+
- Slack workspace admin (to create the app)
- Optional: Google Cloud project for the member OAuth relay

### Clone and install

```bash
git clone https://github.com/ridha-nm/mini-reid.git
cd mini-reid
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
cp .env.example .env
chmod 600 .env
```

### Slack app

1. Create an app at <https://api.slack.com/apps> → **From an app manifest**.
   Paste `slack-app-manifest.yaml`. Change the display name if you want.
2. **Settings → Socket Mode**: enable. Create an app-level token with
   `connections:write` → put it in `.env` as `SLACK_APP_TOKEN`.
3. **Settings → Interactivity**: must be **on** for reminder clarification
   buttons. Socket Mode needs no request URL.
4. **OAuth & Permissions**: install to the workspace → copy the bot token
   (`xoxb-…`) to `SLACK_BOT_TOKEN`.
5. Create a user token with `search:read`, `im:history`, `users:read`
   (`xoxp-…`) → `SLACK_USER_TOKEN`. It is used to read DMs the bot is not in
   and to search missed mentions. Treat it as sensitive: it can read DMs.
6. Your Slack member ID → `SLACK_OWNER_ID` (Profile → More → Copy member ID).
7. Workspace subdomain → `SLACK_TEAM` (e.g. `gopantas`).

Invite `@mini-reid` to the channels you want it to watch. It cannot read
channels it has not joined.

### Google (Gmail + Calendar)

Create an OAuth **Web application** client in Google Cloud:

- Enable Gmail API and Google Calendar API.
- Consent screen: **Internal** (workspace only) avoids token expiry and
  verification.
- Redirect URI: your relay callback (see below) or
  `http://localhost:44000/oauth2callback` for the paste-back fallback.
- Download the client JSON to a path outside the repo (mode 600) and set
  `SETUP_GOOGLE_CREDS=/path/to/client.json`.

For your own mailbox, either use `SETUP_GOOGLE_CREDS` through the setup page
or point `GMAIL_CREDS` / `GMAIL_TOKEN` at an existing token.

### Member setup relay (optional but recommended)

Members connect Google through a small Cloud Run relay so the browser can
reach an HTTPS callback:

```bash
gcloud run deploy mini-reid-setup \
  --source cloud --region asia-southeast1 --allow-unauthenticated
```

Set `RELAY_URL` to the service URL and a random `RELAY_KEY` in `.env`.
`cloud/relay.py` reads the OAuth client ID from an env var and the secret
from Secret Manager; no tokens are logged.

Without a relay, set `SETUP_BASE_URL` to an HTTPS address teammates can
reach (Tailscale Funnel or Caddy) and use the local setup server on
`SETUP_PORT` (default 8765).

### Jira (optional)

Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>
and set `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`. Rows are scoped to
each member's own Jira account.

### Environment

Everything the code reads is in `.env.example`. Minimum for the bot:

```
SLACK_APP_TOKEN, SLACK_BOT_TOKEN, SLACK_USER_TOKEN, SLACK_OWNER_ID, SLACK_TEAM
```

Optional: `KB_ALLOWLIST` (comma-separated Slack IDs allowed to use `ask:`),
`KB_PATHS` (extra local knowledge sources), `OLLAMA_MODEL` (local rewording
model), `CATCHUP_SECONDS` (catch-up sweep interval, default 300; 0 disables),
`SETUP_*`, `RELAY_*`, `JIRA_*`, `GMAIL_*`.

### Run

```bash
.venv/bin/python -m mini_reid.slack_bot        # bot + setup page
.venv/bin/python -m mini_reid.watcher          # one watcher cycle
.venv/bin/python -m mini_reid.cli --days 1     # digest, no delivery
.venv/bin/python -m pytest -q
```

### Install the macOS daemons

The committed plists carry the original author's path. Replace it with yours
and load them:

```bash
ROOT="$PWD"
for p in com.minireid.*.plist; do
  sed "s#/Users/ridhamohamed/mini-reid#$ROOT#g" "$p" \
    > "$HOME/Library/LaunchAgents/$p"
done
for label in bot watcher daily model kb; do
  launchctl bootout "gui/$(id -u)/com.minireid.$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" \
    "$HOME/Library/LaunchAgents/com.minireid.$label.plist"
done
launchctl list | grep minireid
```

`run_model.sh` and `run_kb.sh` are optional; omit those two labels if you do
not use the local model or knowledge base.

### First member

```bash
# In the bot DM:
allow: @Teammate
```

The bot creates `data/<slack_id>/`, DMs a setup link, and starts that
member's capture, reminders and digest.

### Verify

```bash
tail -f bot.out.log watcher.log
python -m mini_reid.directory      # Slack → email → Jira ids
python -m mini_reid.accounts       # email → client accounts
```

---

## What to keep private

`.env`, `users.json`, `directory.json`, `accounts.json`, `ledger*.json`,
`data/`, `reminder_log.json`, `bot_state.json`, logs and `kb.json` contain
credentials or private work data and are ignored by git. Never commit them.
