"""Local knowledge base: embed what Ridha has written, retrieve, answer with citations."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path

from .sources import _get_json, _gmail_list as gmail_list, gmail_access

INDEX = "kb.json"
EMBED_MODEL = "nomic-embed-text"
GEN_MODEL = "llama3.2:3b"
OLLAMA = "http://localhost:11434"

TEXT_SUFFIXES = {".md", ".txt"}
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_FILES = {"kb.json", "ledger.json", "digest.md", "expected.txt", "scorecard.md"}


def embed(text: str, model: str = EMBED_MODEL) -> list[float]:
    req = urllib.request.Request(
        f"{OLLAMA}/api/embeddings",
        data=json.dumps({"model": model, "prompt": text[:8000]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["embedding"]


def chunk(text: str, size: int = 800, overlap: int = 100) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start + size])
        start += size - overlap
    return out


def _doc(source: str, title: str, link: str, text: str) -> list[dict]:
    return [{"source": source, "title": title, "link": link, "text": part}
            for part in chunk(text)]


def local_docs(roots: list[str]) -> list[dict]:
    docs = []
    for root in roots:
        p = Path(root).expanduser()
        files = [p] if p.is_file() else [
            f for f in p.rglob("*")
            if f.is_file() and f.suffix in TEXT_SUFFIXES
            and not any(part in SKIP_DIRS for part in f.parts)
            and f.name not in SKIP_FILES
        ]
        for f in files:
            try:
                docs += _doc("local", f.name, str(f), f.read_text(errors="ignore"))
            except OSError:
                continue
    return docs


def slack_sent_docs(token: str, limit: int = 300) -> list[dict]:
    docs, page = [], 1
    while len(docs) < limit:
        url = ("https://slack.com/api/search.messages?"
               + urllib.parse.urlencode({"query": "from:me", "count": 100,
                                         "page": page, "sort": "timestamp",
                                         "sort_dir": "desc"}))
        d = _get_json(url, {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            break
        matches = (d.get("messages") or {}).get("matches") or []
        for m in matches:
            text = (m.get("text") or "").strip()
            if len(text) < 20:
                continue
            docs += _doc("slack", (m.get("channel") or {}).get("name", "slack"),
                         m.get("permalink") or "", text)
        if len(matches) < 100:
            break
        page += 1
    return docs[:limit]


def gmail_sent_docs(env: dict, limit: int = 200) -> list[dict]:
    access = gmail_access(env)
    ids = gmail_list(access, "in:sent", limit)
    docs = []
    for mid in ids:
        url = (f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?"
               + urllib.parse.urlencode({"format": "full"}))
        msg = _get_json(url, {"Authorization": f"Bearer {access}"})
        text = _plain_text(msg.get("payload") or {})
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", __import__("html").unescape(text)).strip()
        if len(text) < 40:
            continue
        docs += _doc("gmail", "sent mail",
                     f"https://mail.google.com/mail/u/0/#all/{mid}", text)
    return docs[:limit]


def _plain_text(part: dict) -> str:
    import base64

    data = (part.get("body") or {}).get("data")
    if data:
        try:
            return base64.urlsafe_b64decode(data + "===").decode(errors="ignore")
        except Exception:  # noqa: BLE001
            return ""
    return " ".join(_plain_text(p) for p in part.get("parts") or [])


def _key(text: str) -> str:
    import hashlib

    return hashlib.sha1(text[:400].encode()).hexdigest()


def build(roots: list[str], env: dict, use_slack: bool = True,
          use_gmail: bool = True, existing: list[dict] | None = None) -> list[dict]:
    docs = local_docs(roots)
    if use_slack and env.get("SLACK_USER_TOKEN"):
        try:
            docs += slack_sent_docs(env["SLACK_USER_TOKEN"])
        except Exception as ex:  # noqa: BLE001 - one dead source must not stop the build
            print(f"slack index failed: {type(ex).__name__}", flush=True)
    if use_gmail:
        try:
            docs += gmail_sent_docs(env)
        except Exception as ex:  # noqa: BLE001
            print(f"gmail index failed: {type(ex).__name__}", flush=True)

    cached = {_key(d["text"]): d["vec"] for d in (existing or []) if d.get("vec")}
    seen = set()
    index = []
    embedded = 0
    for d in docs:
        key = _key(d["text"])
        if key in seen:
            continue
        seen.add(key)
        if key in cached:
            d["vec"] = cached[key]
        else:
            d["vec"] = embed(d["text"])
            embedded += 1
        index.append(d)
    print(f"passages: {len(index)} ({embedded} newly embedded)", flush=True)
    return index


def save(index: list[dict], path: str = INDEX) -> None:
    Path(path).write_text(json.dumps(index, ensure_ascii=False))


def load(path: str = INDEX) -> list[dict]:
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else []


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0


def search(index: list[dict], question: str, k: int = 8) -> list[dict]:
    q = embed(question)
    scored = sorted(index, key=lambda d: cosine(q, d.get("vec") or []), reverse=True)
    # One passage per source document. Otherwise one long email fills every slot.
    out, seen = [], set()
    for d in scored:
        key = d.get("link") or d["text"][:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
        if len(out) >= k:
            break
    return out


PROMPT = """Answer the question using ONLY the passages below. Do not use outside
knowledge. If the passages only partly answer, say what is known and what is missing.
If nothing relevant is there, say exactly: I do not know.
Every sentence that states a fact must end with its passage number like [1].
Be concise: three sentences at most.

Passages:
{passages}

Question: {question}
Answer:"""


def answer(question: str, index: list[dict], generator=None, k: int = 8) -> tuple[str, list[dict]]:
    hits = search(index, question, k)
    passages = "\n".join(
        f"[{i + 1}] ({h['source']}) {h['text'][:700]}" for i, h in enumerate(hits))
    prompt = PROMPT.format(passages=passages, question=question)

    if generator is None:
        req = urllib.request.Request(
            f"{OLLAMA}/api/generate",
            data=json.dumps({"model": GEN_MODEL, "prompt": prompt,
                             "stream": False,
                             "options": {"temperature": 0}}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            text = json.load(r)["response"]
    else:
        text = generator(prompt)
    return text.strip(), hits


def main(argv: list[str] | None = None) -> int:
    import argparse

    from .sources import load_env

    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--ask", help="question to answer from the index")
    ap.add_argument("--paths", default="")
    args = ap.parse_args(argv)

    env = load_env(".env")
    if args.build:
        roots = [p for p in (args.paths or env.get("KB_PATHS", ".")).split(",") if p]
        index = build([r.strip() for r in roots], env, existing=load())
        save(index)
        print(f"indexed {len(index)} passages -> {INDEX}")
        return 0

    if args.ask:
        index = load()
        if not index:
            print("No index. Run: python -m mini_reid.kb --build")
            return 2
        text, hits = answer(args.ask, index)
        print(text)
        print("\nSources:")
        for i, h in enumerate(hits, 1):
            print(f"[{i}] {h['source']} · {h['link']}")
        return 0

    print("Use --build or --ask \"question\"")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
