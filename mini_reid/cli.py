"""End-to-end run: fetch, extract, merge, render."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .capture import parse_capture
from .clients import load_clients, match_client
from .closure import propose_closures
from .extract import extract
from .ledger import apply_stalled, dedupe_by_link, load, merge, reconcile_jira, save
from .render import render
from .sources import (fetch_gmail, fetch_jira, fetch_slack, fetch_slack_dms,
                      load_env, slack_me)

MYT = timezone(timedelta(hours=8))
LEDGER = "ledger.json"
DIGEST = "digest.md"
IGNORE_DOMAINS = {"pantas.com", "gmail.com", "google.com", "googlegroups.com",
                  "atlassian.net", "atlassian.com", "id.atlassian.com", "slack.com",
                  "github.com"}


def _domain(sender: str) -> str | None:
    m = re.search(r"@([A-Za-z0-9.-]+)", sender or "")
    return m.group(1).lower().rstrip(".") if m else None


def collect(days: int, offline: bool) -> tuple[list[dict], list[str]]:
    if offline:
        return json.loads(Path("tests/fixtures/offline_items.json").read_text()), []
    env = load_env(".env")
    items: list[dict] = []
    errors: list[str] = []

    try:
        token = env.get("SLACK_USER_TOKEN")
        if not token:
            raise RuntimeError("SLACK_USER_TOKEN missing. Add Mini-Reid's xoxp token to .env")
        me = slack_me(token)
        items += fetch_slack(days, token, me)
        items += fetch_slack_dms(days, token, me)
    except Exception as ex:  # noqa: BLE001 - one dead source must not kill the run
        errors.append(f"Slack: {ex}")
    try:
        items += fetch_gmail(days, env)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"Gmail: {ex}")
    try:
        items += fetch_jira(days, env)
    except Exception as ex:  # noqa: BLE001
        errors.append(f"Jira: {ex}")
    return items, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--capture", help="add a commitment: 'add: Eupe item by Friday'")
    ap.add_argument("--model", help="local model for unclear items, e.g. llama3.2:3b")
    ap.add_argument("--deliver", action="store_true", help="DM the digest to Ridha")
    ap.add_argument("--no-brief", action="store_true", help="skip the written summary")
    ap.add_argument("--ledger", default=LEDGER)
    ap.add_argument("--out", default=DIGEST)
    args = ap.parse_args(argv)

    now = datetime.now(MYT)
    clients = load_clients("clients.json")
    known_domains = {d.lower() for c in clients.values() for d in c.get("domains", [])}

    items, errors = collect(args.days, args.offline)

    review: set[str] = set()
    incoming: list[dict] = []
    rule_rows: list[dict] = []

    if args.capture:
        captured = parse_capture(args.capture, now, clients)
        if captured is None:
            print("Not a capture. Use: --capture \"add: <what> by <when>\"")
            return 2
        incoming.append(captured)
    for item in items:
        text = " ".join(filter(None, [item.get("subject"), item.get("text")]))
        channel = item.get("channel") if item.get("source") == "slack" else None
        client = (match_client(text, item.get("author", ""), clients, channel)
                  or match_client(text, item.get("to", ""), clients))
        if client is None and item.get("source") == "gmail":
            dom = _domain(item.get("author", ""))
            ignored = any(dom == d or (dom and dom.endswith("." + d)) for d in IGNORE_DOMAINS)
            if dom and dom not in known_domains and not ignored:
                review.add(dom)
        rule_rows.extend(extract(item, client, now))

    if args.model:
        from .providers import OllamaProvider, extract_batch_safe

        provider = OllamaProvider(model=args.model)
        model_rows: list[dict] = []
        failed: list[dict] = []
        attempted: set[str] = set()
        candidates = [i for i in items if i.get("kind") != "sent"]
        for start in range(0, len(candidates), 5):
            chunk = candidates[start:start + 5]
            rows, bad = extract_batch_safe(chunk, provider, now, list(clients))
            model_rows.extend(rows)
            failed.extend(bad)
            bad_ids = {b.get("native_id") for b in bad}
            attempted |= {i.get("native_id") for i in chunk} - bad_ids
        if failed:
            errors.append(f"Model: {len(failed)} item(s) fell back to rules")
        # Rules decide what is a commitment. The model only improves the wording.
        # The 3B model deleted real asks and kept jokes when it was given authority.
        by_nid = {r["native_id"]: r for r in model_rows}
        merged: list[dict] = []
        for r in rule_rows:
            better = by_nid.pop(r["native_id"], None) if r["native_id"] in attempted else None
            if better:
                # Client comes from rules, never from the model. It invents "ioi".
                better = dict(better, client=r.get("client"), asker=r.get("asker"))
            merged.append(better or r)
        incoming += merged + list(by_nid.values())
    else:
        incoming += rule_rows

    ledger = dedupe_by_link(apply_stalled(merge(load(args.ledger), incoming), now))
    jira_items = [i for i in items if i.get("source") == "jira"]
    if jira_items:
        ledger = reconcile_jira(ledger, {i.get("native_id") for i in jira_items}, now)
    sent = [(i.get("text") or "", i.get("link") or "") for i in items
            if i.get("kind") == "sent"]
    if sent:
        ledger = propose_closures(ledger, sent)
    save(args.ledger, ledger)

    meetings: list[dict] = []
    if not args.offline:
        try:
            from .calendar import meetings_for_day

            meetings = meetings_for_day(load_env(".env"), now)
        except Exception as ex:  # noqa: BLE001 - calendar must not block the ledger
            errors.append(f"Calendar: {type(ex).__name__}: {ex}")

    brief_text = None
    if not args.no_brief:
        try:
            from .kb import brief as make_brief

            brief_text = make_brief(ledger, now)
        except Exception as ex:  # noqa: BLE001 - a missing summary must not block the digest
            errors.append(f"Brief: {type(ex).__name__}")

    out = render(ledger, now, sorted(review), brief=brief_text, meetings=meetings)
    slack_out = render(ledger, now, sorted(review), slack=True, brief=brief_text,
                       meetings=meetings)
    if errors:
        out += "\n## Source errors\n\n" + "\n".join(f"- {e}" for e in errors) + "\n"
        slack_out += "\n\n*Source errors*\n" + "\n".join(f"• {e}" for e in errors)
    Path(args.out).write_text(out)
    if args.deliver:
        from .notify import send_dm

        try:
            send_dm(load_env(".env"), slack_out)
            print("delivered to Slack DM")
        except Exception as ex:  # noqa: BLE001 - delivery failure must be loud
            errors.append(f"Delivery: {ex}")
            print(f"delivery failed: {ex}")
    print(out)
    print(f"\n-> {args.out} ({len(ledger)} ledger rows, {len(incoming)} extracted this run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
