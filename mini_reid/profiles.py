"""Allowlisted Slack users and their per-user storage paths."""
from __future__ import annotations

import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROFILES = "users.json"


def load(path: str = PROFILES) -> dict[str, dict]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(profiles: dict[str, dict], path: str = PROFILES) -> None:
    tmp = Path(path).with_name(Path(path).name + ".tmp")
    tmp.write_text(json.dumps(profiles, indent=1, ensure_ascii=False) + "\n")
    tmp.chmod(0o600)
    os.replace(tmp, path)


def ledger_for(profiles: dict[str, dict], user: str, default: str) -> str:
    """The user's own ledger, or the default for the owner."""
    return (profiles.get(user) or {}).get("ledger") or default


def add_member(profiles: dict[str, dict], user: str, name: str,
               root: str = "data") -> dict:
    """Allow a user and point them at an isolated data directory."""
    entry = profiles.setdefault(user, {})
    entry.update({
        "name": name,
        "role": entry.get("role") or "member",
        "ledger": f"{root}/{user}/ledger.json",
        "creds": f"{root}/{user}/creds.json",
    })
    return entry


def issue_setup_token(profiles: dict[str, dict], user: str,
                      hours: int = 24) -> str:
    token = secrets.token_urlsafe(24)
    entry = profiles.setdefault(user, {})
    entry["setup_token"] = token
    entry["setup_expires"] = (
        datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    return token


def token_owner(profiles: dict[str, dict], token: str
                ) -> tuple[str, dict] | None:
    """Resolve a live one-time setup token without leaking timing."""
    if not token:
        return None
    for user, entry in profiles.items():
        live = entry.get("setup_token") or ""
        if not hmac.compare_digest(live, token):
            continue
        try:
            expires = datetime.fromisoformat(entry.get("setup_expires") or "")
        except ValueError:
            return None
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return (user, entry) if expires > datetime.now(timezone.utc) else None
    return None
