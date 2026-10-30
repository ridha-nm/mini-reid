"""Propose closures by matching open rows against what Ridha actually sent."""
from __future__ import annotations

import re

STOP = set(
    "the and for with from this that have will your you are was were please our "
    "their they been into about after before would could should there here".split()
)

TERMINAL = {"done", "dropped"}


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", (s or "").lower()) if w not in STOP}


def propose_closures(rows: list[dict], sent: list[tuple[str, str]],
                     threshold: float = 0.6, min_hits: int = 2) -> list[dict]:
    """Never closes anything. Marks a row closure=proposed with the evidence link."""
    out = []
    for r in rows:
        r = dict(r)
        if r.get("status") in TERMINAL or r.get("closure") == "proposed":
            out.append(r)
            continue
        words = _words(r.get("what") or "")
        if not words:
            out.append(r)
            continue
        best, evidence = 0.0, None
        for text, link in sent:
            hits = len(words & _words(text))
            if hits < min_hits:
                continue
            score = hits / len(words)
            if score > best:
                best, evidence = score, link
        if best >= threshold:
            r["closure"] = "proposed"
            r["closure_evidence"] = evidence
        out.append(r)
    return out
