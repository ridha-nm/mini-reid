#!/usr/bin/env python3
"""Mini-Reid: what needs Ridha today, from Slack + Gmail (+ Jira when creds exist).

Read-only. Writes digest.md. Sends nothing, ever.

    python3 digest.py            # last 24h
    python3 digest.py --days 3
    python3 digest.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # ponytail: system CA bundle is fine if certifi is absent
    SSL_CTX = ssl.create_default_context()

ROOT = Path(__file__).resolve().parent
MYT = timezone(timedelta(hours=8))

DEFAULT_SLACK_ENV = "~/Downloads/IOI Stock Takes/stocktake-hub/slack-connector/.env"
DEFAULT_GMAIL_CREDS = "~/.gmail-mcp/credentials.json"
DEFAULT_GMAIL_TOKEN = "~/.gmail-mcp/token.json"

# Senders that never need a human. Extend as noise shows up.
NOISE_SENDERS = re.compile(
    r"(no-?reply|do-?not-?reply|newsletter|notifications?@|@insideapple|"
    r"@email\.|marketing@|updates@|digest@)",
    re.I,
)
URGENT_WORDS = re.compile(
    r"\b(urgent|asap|blocker|blocked|escalat|today|eod|deadline|overdue|"
    r"can you|could you|need you|please confirm|confirm by)\b",
    re.I,
)
# Jira/automation notifications are status spam unless they name you.
JIRA_NOTIFY = re.compile(r"atlassian\.net|\(jira\)|jira automation", re.I)
JIRA_MATTERS = re.compile(r"mentioned you|assigned to you|is due|due soon|overdue", re.I)


# ---------------------------------------------------------------- config

def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


CFG = {**load_env(ROOT / ".env")}


def _p(key: str, default: str) -> Path:
    return Path(os.path.expanduser(CFG.get(key) or default))


def _get(url: str, token: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                time.sleep(int(ex.headers.get("Retry-After") or 0) or 2 ** attempt)
                continue
            raise
    raise RuntimeError(f"retries exhausted: {url}")


# ---------------------------------------------------------------- slack

def slack_token() -> str:
    tok = CFG.get("SLACK_USER_TOKEN")
    if tok:
        return tok
    env = load_env(_p("SLACK_ENV", DEFAULT_SLACK_ENV))
    if not env.get("SLACK_USER_TOKEN"):
        raise RuntimeError("no SLACK_USER_TOKEN in .env or SLACK_ENV")
    return env["SLACK_USER_TOKEN"]


def slack_api(method: str, token: str, **params) -> dict:
    url = f"https://slack.com/api/{method}?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}),
                timeout=60,
                context=SSL_CTX,
            ) as r:
                d = json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code == 429:
                time.sleep(3)
                continue
            raise
        if d.get("ok"):
            return d
        if d.get("error") == "ratelimited":
            time.sleep(min(60, 2 ** attempt))
            continue
        raise RuntimeError(f"slack {method}: {d.get('error')}")
    raise RuntimeError("slack retries exhausted")


def collect_slack(days: int) -> list[dict]:
    token = slack_token()
    me = slack_api("auth.test", token)["user_id"]
    since = (datetime.now(MYT) - timedelta(days=days)).strftime("%Y-%m-%d")

    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    page = 1
    while len(out) < 400:
        d = slack_api(
            "search.messages",
            token,
            query=f"<@{me}> after:{since}",
            count=100,
            page=page,
            sort="timestamp",
            sort_dir="desc",
        )
        matches = (d.get("messages") or {}).get("matches") or []
        for m in matches:
            ch = m.get("channel") or {}
            key = (ch.get("id") or "", m.get("ts") or "")
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "source": "slack",
                    "channel": ch.get("name") or ch.get("id") or "?",
                    "channel_id": ch.get("id") or "",
                    "is_dm": bool(re.fullmatch(r"U[A-Z0-9]+", ch.get("name") or "")),
                    "author": m.get("username") or m.get("user") or "?",
                    "ts": datetime.fromtimestamp(float(m["ts"]), MYT),
                    "text": (m.get("text") or "").strip(),
                    "link": m.get("permalink") or "",
                    "to_me_directly": True,
                }
            )
        if len(matches) < 100:
            break
        page += 1
        time.sleep(1.2)
    return out


# ---------------------------------------------------------------- gmail

def gmail_access() -> str:
    creds = json.loads(_p("GMAIL_CREDS", DEFAULT_GMAIL_CREDS).read_text())
    inst = creds.get("installed") or creds.get("web")
    tok = json.loads(_p("GMAIL_TOKEN", DEFAULT_GMAIL_TOKEN).read_text())
    data = urllib.parse.urlencode(
        {
            "client_id": inst["client_id"],
            "client_secret": inst["client_secret"],
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(inst["token_uri"], data=data)
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        return json.load(r)["access_token"]


def collect_gmail(days: int) -> list[dict]:
    access = gmail_access()
    q = f"is:unread newer_than:{days}d -in:spam -in:trash -category:promotions"
    url = (
        "https://gmail.googleapis.com/gmail/v1/users/me/messages?"
        + urllib.parse.urlencode({"q": q, "maxResults": 50})
    )
    listing = _get(url, access)
    out: list[dict] = []
    for stub in listing.get("messages") or []:
        mid = stub["id"]
        meta_url = (
            f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?"
            + urllib.parse.urlencode({"format": "metadata"})
            + "&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=To&metadataHeaders=Date"
        )
        msg = _get(meta_url, access)
        hdrs = {
            h["name"].lower(): h["value"]
            for h in (msg.get("payload") or {}).get("headers") or []
        }
        out.append(
            {
                "source": "gmail",
                "id": mid,
                "channel": "email",
                "author": hdrs.get("from", "?"),
                "subject": hdrs.get("subject", "(no subject)"),
                "to": hdrs.get("to", ""),
                "text": msg.get("snippet", ""),
                "link": f"https://mail.google.com/mail/u/0/#inbox/{mid}",
                "to_me_directly": "ridha" in hdrs.get("to", "").lower(),
                "when": datetime.fromtimestamp(int(msg["internalDate"]) / 1000, MYT),
            }
        )
    return out


# ---------------------------------------------------------------- jira

def collect_jira(days: int) -> tuple[list[dict], str | None]:
    base = CFG.get("JIRA_BASE_URL")
    email = CFG.get("JIRA_EMAIL")
    token = CFG.get("JIRA_API_TOKEN")
    if not (base and email and token):
        return [], "not connected (no JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN in .env)"

    import base64

    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    jql = (
        f"(assignee = currentUser() OR comment ~ currentUser()) "
        f"AND updated >= -{days}d ORDER BY updated DESC"
    )
    url = (
        f"{base.rstrip('/')}/rest/api/3/search?"
        + urllib.parse.urlencode({"jql": jql, "maxResults": 50, "fields": "summary,status,priority,duedate,updated"})
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as r:
            data = json.load(r)
    except urllib.error.HTTPError as ex:
        return [], f"auth/HTTP error {ex.code}"

    out = []
    for issue in data.get("issues") or []:
        f = issue.get("fields") or {}
        out.append(
            {
                "source": "jira",
                "channel": "jira",
                "author": issue.get("key", "?"),
                "subject": f.get("summary", ""),
                "text": f"{f.get('status', {}).get('name', '')} · {f.get('priority', {}).get('name', '') or 'no priority'}",
                "due": f.get("duedate"),
                "link": f"{base.rstrip('/')}/browse/{issue.get('key')}",
                "to_me_directly": True,
            }
        )
    return out, None


# ---------------------------------------------------------------- triage

def bucket_slack(r: dict) -> str | None:
    if r["author"] in {"demo app"} or not r["text"]:
        return None
    if r["is_dm"] or URGENT_WORDS.search(r["text"]):
        return "now"
    if "?" in r["text"]:
        return "today"
    return "fyi"


def bucket_gmail(r: dict) -> str | None:
    if NOISE_SENDERS.search(r["author"]):
        return None
    if JIRA_NOTIFY.search(r["author"]):
        return "now" if JIRA_MATTERS.search(r["subject"]) else "fyi"
    if not r["to_me_directly"]:
        return "fyi"
    if URGENT_WORDS.search(f'{r["subject"]} {r["text"]}'):
        return "now"
    return "today"


def _dedupe_key(r: dict) -> str:
    """One broadcast sent to six people is one line, not six."""
    if r["source"] == "gmail":
        return "gmail|" + re.sub(r"^(re|fwd?):\s*", "", r["subject"].strip().lower())
    return f'{r["source"]}|{r["channel"]}|{r["author"]}|' + r["text"][:80].lower()


def triage(records: list[dict]) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = {"now": [], "today": [], "fyi": []}
    for r in records:
        b = bucket_slack(r) if r["source"] == "slack" else (
            bucket_gmail(r) if r["source"] == "gmail"
            else ("now" if r.get("due") else "today")
        )
        if b:
            buckets[b].append(r)

    for b, items in buckets.items():
        merged: dict[str, dict] = {}
        for r in items:
            k = _dedupe_key(r)
            if k in merged:
                merged[k]["dupes"] = merged[k].get("dupes", 1) + 1
            else:
                r["dupes"] = 1
                merged[k] = r
        buckets[b] = sorted(
            merged.values(),
            key=lambda r: r.get("ts") or r.get("when") or datetime.now(MYT),
            reverse=True,
        )
    return buckets


# ---------------------------------------------------------------- render

LABELS = {
    "now": "Needs you now",
    "today": "Needs a look today",
    "fyi": "FYI",
}


def render(buckets: dict[str, list[dict]], jira_note: str | None, days: int) -> str:
    now = datetime.now(MYT).strftime("%a %d %b %Y, %H:%M MYT")
    total = sum(len(v) for v in buckets.values())
    lines = [f"# Mini-Reid — {now}", "", f"{total} items in the last {days}d. Nothing sent.", ""]

    for key in ("now", "today", "fyi"):
        items = buckets[key]
        if not items:
            continue
        lines.append(f"## {LABELS[key]} ({len(items)})")
        lines.append("")
        for r in items:
            tag = f" ×{r['dupes']}" if r.get("dupes", 1) > 1 else ""
            if r["source"] == "slack":
                who = f"*{r['author']}* in #{r['channel']}{tag}"
                body = r["text"].replace("\n", " ")
                lines.append(f"- {who} — {body}  \n  [open]({r['link']})")
            elif r["source"] == "gmail":
                who = f"*{r['author']}*{tag}"
                body = f"**{r['subject']}** — {r['text']}"
                lines.append(f"- {who} — {body}  \n  [open]({r['link']})")
            else:
                lines.append(f"- *{r['author']}* — {r['subject']} ({r['text']}){tag}  \n  [open]({r['link']})")
        lines.append("")

    if jira_note:
        lines.append(f"_Jira: {jira_note}_")
    return "\n".join(lines)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    records: list[dict] = []
    errors: list[str] = []

    try:
        records += collect_slack(args.days)
    except Exception as ex:  # noqa: BLE001 - a broken source must not kill the digest
        errors.append(f"Slack: {ex}")
    try:
        records += collect_gmail(args.days)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"Gmail: {ex}")

    jira, jira_note = collect_jira(args.days)
    records += jira
    if errors:
        jira_note = " · ".join(filter(None, [jira_note, *errors]))

    text = render(triage(records), jira_note, args.days)
    out = ROOT / "digest.md"
    out.write_text(text)
    print(text)
    print(f"\n-> {out}")
    return 0


# ---------------------------------------------------------------- checks

def selftest() -> int:
    def slack(author, text, is_dm=False, channel="bd-team"):
        return {"source": "slack", "author": author, "text": text, "is_dm": is_dm, "channel": channel}

    def mail(author, subject, to_me=True):
        return {"source": "gmail", "author": author, "subject": subject, "text": "", "to_me_directly": to_me}

    assert bucket_slack(slack("demo app", "hello")) is None
    assert bucket_slack(slack("kasib", "Hows the building going?", channel="U09CCJW1JL8", is_dm=True)) == "now"
    assert bucket_slack(slack("arman", "can you confirm this")) == "now"
    assert bucket_slack(slack("azleena", "Flights are booked")) == "fyi"
    assert bucket_slack(slack("eden", "what do you think?")) == "today"
    assert bucket_gmail(mail("News@insideapple.apple.com", "New MacBook")) is None
    assert bucket_gmail(mail("daniel.sim@eupe.com.my", "please confirm waste migration")) == "now"
    assert bucket_gmail(mail("x@pantas.com", "FYI thread", to_me=False)) == "fyi"
    # Jira status spam is FYI; a Jira mention is not.
    assert bucket_gmail(mail('"kasib (Jira)" <jira@pantas.atlassian.net>', "[JIRA] (BO-8839) RIJ tender")) == "fyi"
    assert bucket_gmail(mail('"kasib (Jira)" <jira@pantas.atlassian.net>', "[JIRA] (BO-1) kasib mentioned you")) == "now"
    print("selftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
