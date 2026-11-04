"""Map every Pantas Slack member to their Jira account and work email."""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.parse
from pathlib import Path

from .sources import _get_json, load_env

DIRECTORY = "directory.json"


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (value or "").lower()).strip()


def _slack_members(token: str) -> list[dict]:
    out: list[dict] = []
    cursor = ""
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = _get_json("https://slack.com/api/users.list?"
                      + urllib.parse.urlencode(params),
                      {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            raise RuntimeError(f"users.list: {d.get('error')}")
        for u in d.get("members") or []:
            if u.get("deleted") or u.get("is_bot"):
                continue
            p = u.get("profile") or {}
            real = p.get("real_name") or ""
            display = p.get("display_name") or ""
            out.append({
                "id": u.get("id") or "",
                "name": u.get("name") or "",
                "real_name": real,
                "display_name": display,
                "email": p.get("email") or "",
            })
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return out


def _jira_search(env: dict, query: str) -> list[dict]:
    base = env.get("JIRA_BASE_URL")
    email = env.get("JIRA_EMAIL")
    token = env.get("JIRA_API_TOKEN")
    if not (base and email and token):
        return []
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    url = (f"{base.rstrip('/')}/rest/api/3/user/search?"
           + urllib.parse.urlencode({"query": query, "maxResults": 10}))
    data = _get_json(url, {"Authorization": f"Basic {auth}",
                           "Accept": "application/json"})
    return data or []


def _match(member: dict, candidates: list[dict]) -> dict | None:
    names = {_norm(member.get(k)) for k in
             ("name", "real_name", "display_name")} - {""}
    for user in candidates:
        if not user.get("active"):
            continue
        email = (user.get("emailAddress") or "").lower()
        if not email:
            continue
        display = _norm(user.get("displayName"))
        if display and display in names:
            return user
        if any(n.startswith(display) or display.startswith(n) for n in names
               if len(display) >= 4 and len(n) >= 4):
            return user
    local = _norm(member.get("name"))
    for user in candidates:
        email = (user.get("emailAddress") or "").lower()
        if email and local and _norm(email.split("@")[0]) == local:
            return user
    return None


def build(env: dict, path: str = DIRECTORY) -> dict[str, dict]:
    people: dict[str, dict] = {}
    seen: set[str] = set()
    for member in _slack_members(env["SLACK_BOT_TOKEN"]):
        if not member["id"] or member["id"] in seen:
            continue
        seen.add(member["id"])
        found = None
        for query in dict.fromkeys(filter(None, [
                member["real_name"], member["display_name"], member["name"]])):
            found = _match(member, _jira_search(env, query))
            if found:
                break
            time.sleep(0.1)
        people[member["id"]] = {
            "name": member["name"],
            "real_name": member["real_name"],
            "email": (found or {}).get("emailAddress") or member["email"],
            "jira_account_id": (found or {}).get("accountId") or "",
            "jira_name": (found or {}).get("displayName") or "",
        }
    Path(path).write_text(json.dumps(people, indent=1, ensure_ascii=False) + "\n")
    Path(path).chmod(0o600)
    return people


def lookup(user: str, path: str = DIRECTORY) -> dict:
    try:
        return json.loads(Path(path).read_text()).get(user) or {}
    except (OSError, ValueError):
        return {}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DIRECTORY)
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    people = build(load_env(".env"), args.path)
    linked = sum(1 for p in people.values() if p.get("jira_account_id"))
    emails = sum(1 for p in people.values() if p.get("email"))
    print(f"{len(people)} people, {emails} emails, {linked} Jira ids -> {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
