"""Slack channels that keep producing rejects, muted for capture.

Learnt from `not:` history, not configured: a channel is muted once it has at
least MIN_REJECTS rejects and at least 3 in 4 of everything it yielded was
rejected. Deleting its key from the file unmutes it.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

PATH = "muted_sources.json"
MIN_REJECTS = 3

_cache: dict[str, tuple[float, frozenset[str]]] = {}


def load(path: str = PATH) -> frozenset[str]:
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return frozenset()
    hit = _cache.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        keys = frozenset(json.loads(Path(path).read_text()))
    except (OSError, ValueError):
        keys = frozenset()
    _cache[path] = (mtime, keys)
    return keys


def is_muted(key: str, path: str = PATH) -> bool:
    return (key or "").lower().lstrip("#") in load(path)


def learn(rows: list[dict], path: str = PATH) -> list[str]:
    """Mute channels that are mostly rejects. Returns the newly muted keys."""
    rejected: Counter = Counter()
    kept: Counter = Counter()
    for row in rows:
        via = row.get("via") or ""
        if row.get("source") != "slack" or not via.startswith("#"):
            continue
        key = via.lstrip("#").lower()
        if row.get("closed_how") == "not_commitment":
            rejected[key] += 1
        elif row.get("status") != "dropped":
            kept[key] += 1   # open work AND completed work both count
    muted = set(load(path))
    added: list[str] = []
    for key, n in rejected.items():
        if n < MIN_REJECTS or key in muted:
            continue
        if n * 4 <= (n + kept.get(key, 0)) * 3:  # 75% or less rejected
            continue
        muted.add(key)
        added.append(key)
    if added:
        Path(path).write_text(json.dumps(sorted(muted), indent=1) + "\n")
        _cache.pop(path, None)
    return added
