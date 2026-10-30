"""Weekly recall check: what you owed vs what the ledger caught.

Write one commitment per line in `expected.txt` on Friday, before opening the
digest. Then run:  .venv/bin/python -m mini_reid.scorecard
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .closure import _words
from .ledger import load

MYT = timezone(timedelta(hours=8))
EXPECTED = "expected.txt"
LEDGER = "ledger.json"
OUT = "scorecard.md"


def match(expected: list[str], rows: list[dict], threshold: float = 0.5) -> dict:
    hits, misses = [], []
    for want in expected:
        words = _words(want)
        best = 0.0
        for r in rows:
            if not words:
                continue
            best = max(best, len(words & _words(r.get("what") or "")) / len(words))
        (hits if best >= threshold else misses).append(want)
    total = len(expected)
    return {
        "total": total,
        "hit": len(hits),
        "recall": round(len(hits) / total, 3) if total else 0.0,
        "missed": misses,
    }


def main(argv: list[str] | None = None) -> int:
    expected_path = Path(EXPECTED)
    if not expected_path.exists():
        print(f"No {EXPECTED}. Write one commitment per line, then rerun.")
        return 2

    expected = [ln.strip() for ln in expected_path.read_text().splitlines() if ln.strip()]
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
