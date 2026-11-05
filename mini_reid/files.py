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


def _safe(name: str, file_id: str) -> str:
    base = Path(name or file_id).stem or file_id
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:80]
    return f"{file_id}_{stem}"


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
