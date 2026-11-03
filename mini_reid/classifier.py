"""Tiny task-vs-chatter classifier. No dependencies, no network.

Naive Bayes over words and word pairs, trained on the ledger's own rows,
the `not:` corrections and a small seed set. It is a second opinion for
social messages, never the authority for what becomes a commitment.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

TOKEN = re.compile(r"[a-z0-9']+")

POSITIVE_SEED = [
    "send the deck by friday",
    "can you review the dashboard",
    "please confirm the waste mapping",
    "update max by noon",
    "book a meeting with the client",
    "provide the SME audience profile",
    "configure file mappings for the project",
    "follow up with the client on the invoice",
    "share the report when ready",
    "pay the invoice before the end of the month",
    "reply to Daniel about the proposal",
    "prepare the slides for the workshop",
    "check the dashboard numbers",
    "submit the timesheet",
    "fix the login issue",
    "start the K3 migration",
    "review the PR and merge",
    "let the client know the timeline",
    "confirm the scope by tomorrow",
    "get the file from Kasib",
]
NEGATIVE_SEED = [
    "hi",
    "hello",
    "hey there",
    "good morning",
    "you there",
    "are you awake",
    "who are you",
    "what are you",
    "thanks",
    "thank you",
    "got it",
    "lol",
    "haha",
    "test",
    "what's up",
    "please treat raj nicely",
    "start huddle with xieyi",
    "unblock me",
    "stop harassing me",
    "tell him to stop",
    "make peace with him",
    "stop fighting",
    "calm down",
    "apologise to her",
    "say sorry",
    "den i",
    "you speak mandarin",
    "loving mini-reid",
    "love you",
    "good bot",
    "nice bot",
    "you are great",
]


def _tokens(text: str) -> list[str]:
    words = TOKEN.findall((text or "").lower())
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def _examples(ledger_path: str = "ledger.json",
              corrections_path: str = "corrections.json") -> tuple[list[str], list[str]]:
    pos, neg = list(POSITIVE_SEED), list(NEGATIVE_SEED)
    try:
        rows = json.loads(Path(ledger_path).read_text())
    except (OSError, ValueError):
        rows = []
    for row in rows:
        what = row.get("what") or ""
        if (len(what) >= 8 and row.get("status") in {"open", "stalled", "done"}
                and row.get("kind") not in {"note", "reminder"}
                and row.get("closed_how") not in {"not_commitment", "merged"}):
            pos.append(what)
    try:
        corrections = json.loads(Path(corrections_path).read_text())
    except (OSError, ValueError):
        corrections = []
    for item in corrections:
        if item.get("what"):
            neg.append(item["what"])
    return pos, neg


def _fit(pos: list[str], neg: list[str]) -> tuple[dict, dict, set]:
    vocab: set[str] = set()
    counts = {"pos": {}, "neg": {}}
    totals = {"pos": 0, "neg": 0}
    for label, texts in (("pos", pos), ("neg", neg)):
        for text in texts:
            for token in _tokens(text):
                vocab.add(token)
                counts[label][token] = counts[label].get(token, 0) + 1
                totals[label] += 1
    return counts, totals, vocab


def task_score(text: str, ledger_path: str = "ledger.json",
               corrections_path: str = "corrections.json") -> float:
    """Probability in 0..1 that `text` is task-like rather than chatter."""
    pos, neg = _examples(ledger_path, corrections_path)
    counts, totals, vocab = _fit(pos, neg)
    tokens = [t for t in _tokens(text) if t in vocab]
    if not tokens:
        return 0.5
    alpha, size = 1.0, max(len(vocab), 1)
    log_pos = log_neg = math.log(0.5)
    for token in tokens:
        log_pos += math.log((counts["pos"].get(token, 0) + alpha)
                            / (totals["pos"] + alpha * size))
        log_neg += math.log((counts["neg"].get(token, 0) + alpha)
                            / (totals["neg"] + alpha * size))
    return 1 / (1 + math.exp(max(-60.0, min(60.0, log_neg - log_pos))))


if __name__ == "__main__":
    import sys

    samples = sys.argv[1:] or [
        "send the deck by Friday",
        "can you review the dashboard",
        "please treat raj nicely",
        "start huddle with xieyi",
        "hi",
    ]
    for sample in samples:
        print(f"{task_score(sample):.3f}  {sample}")
