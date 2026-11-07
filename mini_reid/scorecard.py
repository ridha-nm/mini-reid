"""Weekly recall check: what you owed vs what the ledger caught.

Write one commitment per line in `expected.txt` on Friday, before opening the
digest. A line may name the elements that prove capture:

    Eupe platform updates | matches: eupe dashboard, eupe change request

Then run:  .venv/bin/python -m mini_reid.scorecard
"""
from __future__ import annotations

import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .closure import _words
from .ledger import load

MYT = timezone(timedelta(hours=8))
EXPECTED = "expected.txt"
LEDGER = "ledger.json"
OUT = "scorecard.md"

TOKEN = re.compile(r"[A-Za-z0-9]+")
OVERRIDE = re.compile(r"^(?P<text>.+?)(?:\s*\|\s*matches:\s*(?P<alts>.+))?$",
                      re.I)
STOP = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at",
    "by", "with", "from", "after", "before", "into", "over", "under", "is",
    "are", "was", "were", "be", "been", "being", "this", "that", "these",
    "those", "it", "its", "my", "me", "i", "we", "you", "your", "our",
    "their", "his", "her", "them", "they", "as", "if", "then", "than", "so",
    "such", "not", "no", "but", "also", "full", "new", "fixes", "fix",
    "updates", "update", "issues", "issue", "requests", "request",
}


def parse_expected(line: str) -> tuple[str, list[str]]:
    m = OVERRIDE.match((line or "").strip())
    if not m:
        return (line or "").strip(), []
    text = m.group("text").strip()
    alts = [a.strip() for a in re.split(r"[;,]", m.group("alts") or "")
            if a.strip()]
    return text, alts


def keywords(text: str) -> set[str]:
    out = set()
    for token in TOKEN.findall(text or ""):
        low = token.lower()
        if len(low) >= 4 and low not in STOP:
            out.add(low)
        elif token.isupper() and len(token) >= 2:
            out.add(low)
    return out


def row_text(row: dict) -> str:
    return " ".join(str(row.get(k) or "") for k in (
        "what", "action", "asker", "client", "epic_title")).lower()


def element_match(want: str, row: dict) -> bool:
    """At least half the expected keywords appear somewhere in the row."""
    keys = keywords(want)
    if not keys:
        return False
    blob = row_text(row)
    hits = {key for key in keys
            if re.search(rf"\b{re.escape(key)}\b", blob)}
    return len(hits) >= max(2, math.ceil(len(keys) * 0.5))


def match(expected: list[str], rows: list[dict], threshold: float = 0.5) -> dict:
    hits, misses = [], []
    how = {"wording": 0, "elements": 0, "override": 0}
    for raw in expected:
        want, overrides = parse_expected(raw)
        blob_alts = [alt.lower() for alt in overrides]
        found = None
        for row in rows:
            blob = row_text(row)
            if any(alt in blob for alt in blob_alts):
                found = "override"
                break
            words = _words(want)
            if words and len(words & _words(row.get("what") or "")) / len(words) >= threshold:
                found = "wording"
                break
            if element_match(want, row):
                found = "elements"
                break
        if found:
            hits.append(want)
            how[found] += 1
        else:
            misses.append(want)
    total = len(expected)
    return {
        "total": total,
        "hit": len(hits),
        "recall": round(len(hits) / total, 3) if total else 0.0,
        "missed": misses,
        "how": how,
    }


def main(argv: list[str] | None = None) -> int:
    expected_path = Path(EXPECTED)
    if not expected_path.exists():
        print(f"No {EXPECTED}. Write one commitment per line, then rerun.")
        return 2

    expected = [ln.strip() for ln in expected_path.read_text().splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    rows = load(LEDGER)
    cutoff = datetime.now(MYT) - timedelta(days=7)
    recent = []
    for r in rows:
        try:
            if datetime.fromisoformat(r.get("created_at", "")) >= cutoff:
                recent.append(r)
        except ValueError:
            continue

    result = match(expected, recent)
    stamp = datetime.now(MYT).strftime("%Y-%m-%d")
    block = [
        f"## {stamp}",
        "",
        f"- expected: {result['total']}",
        f"- caught: {result['hit']}",
        f"- recall: {result['recall']:.0%}",
        f"- matched by: wording {result['how']['wording']}, "
        f"elements {result['how']['elements']}, "
        f"override {result['how']['override']}",
        "",
    ]
    if result["missed"]:
        block.append("Missed:")
        block.extend(f"- {m}" for m in result["missed"])
        block.append("")

    with Path(OUT).open("a") as fh:
        fh.write("\n".join(block) + "\n")
    print("\n".join(block))
    return 0


if __name__ == "__main__":
    sys.exit(main())
