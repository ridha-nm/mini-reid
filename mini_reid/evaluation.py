"""Measure capture against ground truth. Pure functions, no network."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ledger import TERMINAL, normalize_what


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


def _unique_rows(extracted: list[dict]) -> list[dict]:
    """Dedupe by id when there is one; id-less rows stay distinct."""
    rows: list[dict] = []
    seen: set[str] = set()
    for row in extracted:
        rid = row.get("id") or ""
        if rid:
            if rid in seen:
                continue
            seen.add(rid)
        rows.append(row)
    return rows


def score(labels: list[dict], extracted: list[dict],
          threshold: float = 0.8) -> dict:
    """Recall against positive labels; false tasks against reviewed dismissals."""
    rows = _unique_rows(extracted)
    by_id = {r["id"]: r for r in rows if r.get("id")}
    predicted = [r for r in rows if r.get("status") not in TERMINAL]

    positives = [l for l in labels if l.get("is_task")]
    misses: list[str] = []
    covered = 0
    used: set[int] = set()
    for label in positives:
        hit = None
        for i, row in enumerate(predicted):
            if i in used:
                continue
            if (label.get("date") and row.get("date")
                    and label["date"] != row["date"]):
                continue
            if task_matches(label.get("text") or "", row.get("text") or "",
                            threshold):
                hit = i
                break
        if hit is not None:
            used.add(hit)
            covered += 1
        elif len(misses) < 20:
            misses.append(label.get("text") or "")

    negatives = [l for l in labels
                 if not l.get("is_task") and l.get("id")]
    reviewed = [l for l in negatives if (l.get("id") or "") in by_id]
    false_rows = [l for l in reviewed
                  if by_id[l["id"]].get("status") not in TERMINAL]
    days = {l.get("date") for l in labels if l.get("date")}
    days |= {r.get("date") for r in rows if r.get("date")}
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


SELF_DM_PREFIX = re.compile(r"^\s*(?:\[[ xX]\]|\d+[.)]|[^\w\s])\s*")
MYT = timezone(timedelta(hours=8))


def labels_from_self_dm(messages: list[dict]) -> list[dict]:
    labels: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        try:
            date = datetime.fromtimestamp(float(message.get("ts") or 0),
                                          MYT).date().isoformat()
        except (TypeError, ValueError):
            continue
        for line in (message.get("text") or "").splitlines():
            text = line
            while True:
                stripped = SELF_DM_PREFIX.sub("", text)
                if stripped == text:
                    break
                text = stripped
            text = text.strip()
            if len(text) < 3:
                continue
            key = (date, normalize_what(text))
            if key in seen:
                continue
            seen.add(key)
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
    """Every captured row is a prediction; dismissal is measured separately."""
    out = []
    for row in rows:
        if row.get("kind") in {"note", "reminder"}:
            continue
        out.append({"id": row.get("id") or "", "date": _ledger_date(row),
                    "text": row.get("action") or row.get("what") or "",
                    "status": "open"})
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


def _load_jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines()
            if line.strip()]


def format_report(result: dict) -> str:
    recall = result.get("recall")
    recall_text = "n/a" if recall is None else f"{recall * 100:.1f}%"
    lines = [
        "# Capture evaluation",
        "",
        f"Positives: {result['positives']}",
        f"Covered: {result['covered']}",
        f"Recall: {recall_text}",
        f"False tasks: {result['false_tasks']}",
        f"Reviewed dismissals: {result['reviewed']}",
        f"False tasks per day: {result['false_per_day']:.2f}",
        f"Verdict: {'PASS' if result['meets_target'] else 'FAIL'}",
    ]
    if result.get("misses"):
        lines += ["", "## Missed tasks", ""]
        lines += [f"- {text}" for text in result["misses"]]
    if result.get("false_examples"):
        lines += ["", "## False tasks", ""]
        lines += [f"- {text}" for text in result["false_examples"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-dm")
    parser.add_argument("--ledger")
    parser.add_argument("--labels")
    parser.add_argument("--extracted")
    parser.add_argument("--out", default="eval_report.md")
    args = parser.parse_args(argv)

    if args.labels and args.extracted:
        labels = load_labels(args.labels)
        extracted = _load_jsonl(args.extracted)
    elif args.self_dm and args.ledger:
        messages = json.loads(Path(args.self_dm).read_text()).get("messages") or []
        rows = json.loads(Path(args.ledger).read_text())
        labels = labels_from_self_dm(messages) + labels_from_ledger(rows)
        extracted = extracted_from_ledger(rows)
    else:
        parser.error("use --labels and --extracted, or --self-dm and --ledger")

    result = score(labels, extracted)
    report = format_report(result)
    Path(args.out).write_text(report)
    print(report)
    return 0 if result["meets_target"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
