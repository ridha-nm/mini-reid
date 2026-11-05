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


def score(labels: list[dict], extracted: list[dict],
          threshold: float = 0.8) -> dict:
    """Recall against positive labels; false tasks against reviewed dismissals."""
    by_id: dict[str, dict] = {}
    for row in extracted:
        by_id.setdefault(row.get("id") or "", row)
    predicted = [r for r in by_id.values()
                 if r.get("status") not in {"done", "dropped"}]

    positives = [l for l in labels if l.get("is_task")]
    misses: list[str] = []
    covered = 0
    for label in positives:
        hit = any(
            (not label.get("date") or not row.get("date")
             or label.get("date") == row.get("date"))
            and task_matches(label.get("text") or "", row.get("text") or "",
                             threshold)
            for row in predicted
        )
        if hit:
            covered += 1
        elif len(misses) < 20:
            misses.append(label.get("text") or "")

    negatives = [l for l in labels
                 if not l.get("is_task") and l.get("id")]
    reviewed = [l for l in negatives if (l.get("id") or "") in by_id]
    false_rows = [l for l in reviewed
                  if by_id[l["id"]].get("status") not in {"done", "dropped"}]
    days = {l.get("date") for l in negatives if l.get("date")}
    recall = (covered / len(positives)) if positives else None
    false_per_day = (len(false_rows) / len(days)) if days else 0.0
    return {
        "positives": len(positives),
        "covered": covered,
        "recall": recall,
        "false_tasks": len(false_rows),
        "reviewed": len(reviewed),
        "false_per_day": false_per_day,
        "misses": misses,
        "false_examples": [l.get("text") or "" for l in false_rows[:20]],
        "meets_target": (recall is not None and recall >= 0.95
                         and false_per_day < 1.0),
    }


SELF_DM_BULLET = __import__("re").compile(
    r"^\s*(?:[•*\-–☐☑]|\[[ xX]\]|\d+[.)])\s*")


def labels_from_self_dm(messages: list[dict]) -> list[dict]:
    from datetime import datetime, timedelta, timezone

    myt = timezone(timedelta(hours=8))
    labels: list[dict] = []
    for message in messages:
        try:
            date = datetime.fromtimestamp(float(message.get("ts") or 0),
                                          myt).date().isoformat()
        except (TypeError, ValueError):
            date = ""
        for line in (message.get("text") or "").splitlines():
            text = SELF_DM_BULLET.sub("", line).strip()
            if len(text) < 3:
                continue
            labels.append({"date": date, "text": text, "is_task": True,
                           "source": "self_dm", "id": ""})
    return labels


def _ledger_date(row: dict) -> str:
    return (row.get("created_at") or "")[:10]


def labels_from_ledger(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if (row.get("status") != "dropped"
                or row.get("closed_how") != "not_commitment"
                or row.get("kind") in {"note", "reminder"}):
            continue
        out.append({"id": row.get("id") or "", "date": _ledger_date(row),
                    "text": row.get("what") or "", "is_task": False,
                    "source": "dismissed"})
    return out


def extracted_from_ledger(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if row.get("kind") in {"note", "reminder"}:
            continue
        out.append({"id": row.get("id") or "", "date": _ledger_date(row),
                    "text": row.get("action") or row.get("what") or "",
                    "status": row.get("status") or "open"})
    return out


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
