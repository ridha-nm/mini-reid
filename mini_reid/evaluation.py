"""Measure capture against ground truth. Pure functions, no network."""
from __future__ import annotations

import json
from pathlib import Path

from .ledger import normalize_what


def task_tokens(text: str) -> set[str]:
    return {t for t in normalize_what(text).split() if len(t) >= 2}


def task_matches(label: str, extracted: str, threshold: float = 0.8) -> bool:
    a, b = task_tokens(label), task_tokens(extracted)
    if not a or not b:
        return False
    if a == b:
        return True
    overlap = len(a & b) / len(a | b)
    if overlap >= threshold:
        return True
    smaller = a if len(a) <= len(b) else b
    larger = b if smaller is a else a
    return len(smaller) >= 3 and smaller <= larger


def load_labels(path: str) -> list[dict]:
    labels: list[dict] = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not {"date", "text", "is_task"} <= set(row):
            raise ValueError("label needs date, text and is_task")
        labels.append(row)
    return labels
