"""Slack Do Not Disturb checks for nudges."""
from __future__ import annotations

from .sources import _get_json


def dnd_active(env: dict, user: str) -> bool:
    """True while Slack says this user is in Do Not Disturb.

    Off unless RESPECT_DND is truthy; messages keep flowing by default.
    """
    if (env.get("RESPECT_DND") or "0").lower() not in {"1", "true", "yes"}:
        return False
    token = env.get("SLACK_BOT_TOKEN")
    if not token or not user:
        return False
    try:
        data = _get_json(
            f"https://slack.com/api/dnd.info?user={user}",
            {"Authorization": f"Bearer {token}"})
    except Exception:  # noqa: BLE001 - never block a notification on this
        return False
    return bool(data.get("ok") and data.get("dnd_enabled"))
