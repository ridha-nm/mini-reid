"""Ingest files shared in Slack: download, extract text, search locally."""
from __future__ import annotations

import html
import json
import re
import subprocess
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path

FILES_DIR = "data/slack_files"
MAX_BYTES = 10 * 1024 * 1024
TEXT_SUFFIX = {".txt", ".md", ".csv", ".json", ".log", ".yaml", ".yml"}


def _get(url: str, token: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def extract_text(name: str, data: bytes) -> str:
    suffix = Path(name or "").suffix.lower()
    if suffix in TEXT_SUFFIX:
        return data.decode("utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            proc = subprocess.run(
                ["pdftotext", "-", "-"], input=data, capture_output=True,
                timeout=120)
            return proc.stdout.decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001 - parser missing or failed
            return ""
    if suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                xml = archive.read("word/document.xml").decode(
                    "utf-8", errors="ignore")
            return html.unescape(re.sub(r"<[^>]+>", " ", xml))
        except Exception:  # noqa: BLE001
            return ""
    if suffix == ".xlsx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = [n for n in archive.namelist()
                         if n.startswith("xl/sharedStrings")]
                xml = " ".join(archive.read(n).decode("utf-8", errors="ignore")
                               for n in names)
            return html.unescape(re.sub(r"<[^>]+>", " ", xml))
        except Exception:  # noqa: BLE001
            return ""
    return ""


def summarize(text: str, limit: int = 280) -> str:
    """First whole sentences up to limit; a readable ack, not a model call."""
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", clean):
        candidate = f"{out} {sentence}".strip()
        if len(candidate) > limit:
            break
        out = candidate
    return (out or clean[:limit]).strip()


def _safe(name: str, file_id: str) -> str:
    base = Path(name or file_id).stem or file_id
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:80]
    return f"{file_id}_{stem}"


def ack_messages(actor: str, owner: str,
                 records: list[dict]) -> list[tuple[str, str]]:
    """Actor gets names only; the owner gets names plus summaries."""
    if not records:
        return []
    names = ", ".join(f"*{r['name']}*" for r in records)
    out = []
    if actor and actor != owner:
        out.append((actor, f"Ingested: {names}"))
    if owner:
        detail = "\n".join(
            f"*{r['name']}*\n_{r.get('summary') or ''}_" for r in records)
        out.append((owner, f"Ingested:\n{detail}\n"
                           "Ask me about them with `ask:`."))
    return out


def message_files(env: dict, channel: str, ts: str) -> list[dict]:
    """Files attached to the Slack message behind a reaction."""
    from .sources import _get_json

    for key in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN"):
        token = env.get(key)
        if not token:
            continue
        url = ("https://slack.com/api/conversations.history?"
               + urllib.parse.urlencode({"channel": channel, "oldest": ts,
                                         "latest": ts, "inclusive": "true",
                                         "limit": 1}))
        try:
            data = _get_json(url, {"Authorization": f"Bearer {token}"})
        except Exception:  # noqa: BLE001 - try the next token
            continue
        for message in data.get("messages") or []:
            if message.get("ts") == ts:
                return message.get("files") or []
    return []


def ingest(env: dict, file_id: str, root: str = FILES_DIR) -> dict | None:
    token = env.get("SLACK_BOT_TOKEN")
    if not token or not file_id:
        return None
    info = json.loads(_get(
        "https://slack.com/api/files.info?"
        + urllib.parse.urlencode({"file": file_id}), token))
    if not info.get("ok"):
        raise RuntimeError(f"files.info: {info.get('error')}")
    meta = info.get("file") or {}
    url = meta.get("url_private") or meta.get("url_private_download")
    if not url:
        return None
    data = _get(url, token)
    if len(data) > MAX_BYTES:
        return None
    name = meta.get("name") or file_id
    text = extract_text(name, data)
    if len(text.strip()) < 40:
        return None
    folder = Path(root)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe(name, file_id)
    (folder / f"{stem}.txt").write_text(text)
    record = {"id": file_id, "name": name, "permalink": meta.get("permalink") or "",
              "path": str(folder / f"{stem}.txt"),
              "summary": summarize(text),
              "created": meta.get("created") or 0}
    (folder / f"{file_id}.json").write_text(json.dumps(record))
    return record


def search(question: str, root: str = FILES_DIR, limit: int = 3) -> list[dict]:
    words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", question or "")}
    if len(words) < 2:
        return []
    folder = Path(root)
    if not folder.exists():
        return []
    hits = []
    for path in folder.glob("*.txt"):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        low = text.lower()
        score = sum(1 for word in words if word in low)
        if score < 2:
            continue
        at = min((low.find(word) for word in words if word in low), default=0)
        snippet = " ".join(text[max(0, at - 120):at + 380].split())
        record = {}
        meta = path.name.split("_", 1)[0] + ".json"
        meta_path = folder / meta
        if meta_path.exists():
            try:
                record = json.loads(meta_path.read_text())
            except ValueError:
                record = {}
        hits.append({"name": record.get("name") or path.stem,
                     "permalink": record.get("permalink") or "",
                     "text": snippet, "score": score})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:limit]
