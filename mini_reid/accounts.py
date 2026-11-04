"""Work email -> client slugs from the BD Command Centre roster.

Source: Pantas-bd/stocktake-hub `config/config.json`. `members` on each client
is the account team.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ACCOUNTS = "accounts.json"

# The hub roster is org-wide; these are the accounts the person actually owns.
OVERRIDES = {
    "charanya@pantas.com": ["knight-frank", "allianz", "setia", "eupe"],
}

CANDIDATES = [
    os.path.expanduser("~/Downloads/IOI Stock Takes/stocktake-hub/config/config-live.json"),
    os.path.expanduser("~/Downloads/IOI Stock Takes/stocktake-hub/config/config.json"),
    os.path.expanduser("~/projects/stocktake-hub/config/config-live.json"),
    os.path.expanduser("~/stocktake-hub/config/config-live.json"),
]

# Portfolios are kept as clients too; child clients carry a `portfolio` tag.


def source_path(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    if os.environ.get("BD_CONFIG"):
        return os.environ["BD_CONFIG"]
    return next((p for p in CANDIDATES if Path(p).exists()), None)


def build(source: str, path: str = ACCOUNTS) -> dict[str, list[str]]:
    cfg = json.loads(Path(source).read_text())
    people: dict[str, list[str]] = {}
    for slug, client in (cfg.get("clients") or {}).items():
        for email in client.get("members") or []:
            key = (email or "").strip().lower()
            if key:
                people.setdefault(key, []).append(slug)
    people.update(OVERRIDES)
    people = {k: sorted(set(v)) for k, v in people.items()}
    Path(path).write_text(json.dumps(people, indent=1) + "\n")
    Path(path).chmod(0o600)
    return people


def clients_for(email: str, path: str = ACCOUNTS) -> list[str]:
    key = (email or "").strip().lower()
    if key in OVERRIDES:
        return OVERRIDES[key]
    try:
        return json.loads(Path(path).read_text()).get(key) or []
    except (OSError, ValueError):
        return []


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="stocktake-hub config/config.json")
    ap.add_argument("--path", default=ACCOUNTS)
    args = ap.parse_args()
    source = source_path(args.source)
    if not source:
        print("No stocktake-hub config found. Pass --source.")
        return 2
    people = build(source, args.path)
    print(f"{len(people)} people -> {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
