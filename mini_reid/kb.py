"""Local knowledge base: embed what Ridha has written, retrieve, answer with citations."""
from __future__ import annotations

import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .sources import _get_json, _gmail_list as gmail_list, gmail_access

INDEX = "kb.json"
EMBED_MODEL = "nomic-embed-text"
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
    import html as _html

    text = _html.unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    out, start = [], 0
    while start < len(text):
        out.append(text[start:start + size])
        start += size - overlap
    return out


def _doc(source: str, title: str, link: str, text: str, date: str = "") -> list[dict]:
    return [{"source": source, "title": title, "link": link, "text": part, "date": date}
            for part in chunk(text)]


BOILERPLATE = re.compile(
    r"gmail is email that|accounts\.google\.com|unsubscribe|view this email in",
    re.I)


ADDR = re.compile(r"[^;<>]{0,60}<[^<>@\s]+@[^<>]+>;?\s*")


def strip_email_junk(text: str) -> str:
    """Remove headers, address lists and boilerplate at answer time as well."""
    t = re.sub(r"https?://\S+", " ", text or "")
    for marker in ("Subject:", "subject:"):
        i = t.rfind(marker)
        if i != -1:
            t = t[i + len(marker):]
            m = re.search(r"(Dear |Hi |Hello )", t)
            if m:
                t = t[m.start():]
            break
    t = ADDR.sub(" ", t)
    t = re.sub(r"(From|To|Cc|Bcc|Date|Sent):\s*", " ", t)
    b = BOILERPLATE.search(t)
    if b:
        t = t[:b.start()]
    return re.sub(r"\s+", " ", t).strip()


def usable(text: str) -> bool:
    """Drop passages that are headers, links or Google boilerplate."""
    body = re.sub(r"https?://\S+", " ", text or "")
    return len(re.findall(r"[A-Za-z]{3,}", body)) >= 12 and not BOILERPLATE.search(body)


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
            from datetime import datetime as _dt

            try:
                when = _dt.fromtimestamp(float(m.get("ts", 0))).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                when = ""
            docs += _doc("slack", (m.get("channel") or {}).get("name", "slack"),
                         m.get("permalink") or "", text, when)
        if len(matches) < 100:
            break
        page += 1
    return docs[:limit]


def gmail_inbox_docs(env: dict, limit: int = 200) -> list[dict]:
    """Received mail. Without this, replies like 'reverted with comments' are invisible."""
    access = gmail_access(env)
    ids = gmail_list(access, "in:inbox -in:spam -in:trash", limit)
    return _gmail_docs(access, ids, limit)


def gmail_sent_docs(env: dict, limit: int = 200) -> list[dict]:
    access = gmail_access(env)
    ids = gmail_list(access, "in:sent", limit)
    return _gmail_docs(access, ids, limit)


def _gmail_docs(access: str, ids: list[str], limit: int) -> list[dict]:
    docs = []
    for n, mid in enumerate(ids):
        url = (f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?"
               + urllib.parse.urlencode({"format": "full"}))
        msg = None
        for attempt in range(3):
            try:
                msg = _get_json(url, {"Authorization": f"Bearer {access}"})
                break
            except Exception:  # noqa: BLE001 - transient quota, 5xx and timeouts
                time.sleep(2 ** attempt)
        if msg is None:
            skipped = globals().get("_skipped", 0) + 1
            globals()["_skipped"] = skipped
            continue
        if n and n % 20 == 0:
            time.sleep(1)
        if msg is None:
            continue
        text = _plain_text(msg.get("payload") or {})
        text = re.sub(r"<[^>]+>", " ", text)
        text = __import__("html").unescape(text)
        text = re.sub(r"(?im)^\s*(from|to|cc|bcc|subject|date|sent):.*$", " ", text)
        text = re.sub(r">[>\s]*>", " ", text)   # quoted-reply markers
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        from datetime import datetime as _dt

        try:
            when = _dt.fromtimestamp(int(msg.get("internalDate", 0)) / 1000).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            when = ""
        docs += _doc("gmail", "sent mail",
                     f"https://mail.google.com/mail/u/0/#all/{mid}", text, when)
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
    existing = existing or []

    def keep(source: str) -> list[dict]:
        """A source that fails must not erase what we already had."""
        return [d for d in existing if d.get("source") == source]

    docs = local_docs(roots)
    if use_slack and env.get("SLACK_USER_TOKEN"):
        try:
            docs += slack_sent_docs(env["SLACK_USER_TOKEN"])
        except Exception as ex:  # noqa: BLE001 - one dead source must not stop the build
            print(f"slack index failed: {type(ex).__name__}; keeping previous", flush=True)
            docs += keep("slack")
    if use_gmail:
        try:
            docs += gmail_sent_docs(env)
        except Exception as ex:  # noqa: BLE001
            print(f"gmail sent index failed: {type(ex).__name__}; keeping previous", flush=True)
            docs += keep("gmail")
        try:
            docs += gmail_inbox_docs(env)
        except Exception as ex:  # noqa: BLE001
            print(f"gmail inbox index failed: {type(ex).__name__}", flush=True)

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
        d = dict(d, score=round(cosine(q, d.get("vec") or []), 3))
        out.append(d)
        if len(out) >= k:
            break
    return out


def _prefer_client(question: str, hits: list[dict]) -> list[dict]:
    """If the question names a client, keep only that client's passages."""
    try:
        from .clients import load_clients, match_client

        clients = load_clients("clients.json")
        m = match_client(question, "", clients)
        if not m:
            return hits
        c = clients[m["slug"]]
        terms = [c.get("name", "")] + list(c.get("aliases", []))
        channels = [x for x in c.get("slack_channels", []) if x.startswith(("C", "D", "G"))]

        def relevant(h: dict) -> bool:
            text = (h.get("text") or "").lower()
            link = h.get("link") or ""
            return (any(t and t.lower() in text for t in terms)
                    or any(ch in link for ch in channels))

        kept = [h for h in hits if relevant(h)]
        # Project notes about a client are not the client's own record.
        primary = [h for h in kept if h.get("source") != "local"]
        chosen = primary or kept
        if len(chosen) < 3:
            # Filtering too hard starves the answer. Top up from the unfiltered hits.
            chosen = chosen + [h for h in hits if h not in chosen]
        return chosen
    except Exception:  # noqa: BLE001 - a broken registry must not break answering
        return hits


MIN_SCORE = 0.55
# 8B is too slow on an 8 GB M2 (5 minutes, then a timeout). Override with KB_MODEL.
SYNTH_MODEL = "llama3.2:3b"

SYNTH_PROMPT = """Answer the question using ONLY the passages. Write two or three
sentences. End every sentence that states a fact with its passage number like [2].
Passages are in date order. If they conflict, the most recent one wins: report the
current state, not the earlier one. If the passages do not contain the answer,
reply exactly: I do not know.

Passages:
{passages}

Question: {question}
Answer:"""


BRIEF_PROMPT = """Write Ridha's morning brief in three sentences at most.
Use only the items listed. Put the most urgent first. Name the client and the date.
No links, no bullet points, no preamble.

Items:
{items}
"""


def brief(rows: list[dict], model: str = SYNTH_MODEL, limit: int = 12) -> str | None:
    """A short written summary of the day. None if the model is unavailable."""
    open_rows = [r for r in rows if r.get("status") not in {"done", "dropped"}]
    open_rows.sort(key=lambda r: (r.get("due") or "9999", r.get("what") or ""))
    items = "\n".join(
        f"- {r.get('what', '')[:120]} | {r.get('client') or 'unassigned'} | "
        f"{r.get('due') or 'no date'} | {r.get('status')}"
        for r in open_rows[:limit])
    if not items:
        return None
    try:
        req = urllib.request.Request(
            f"{OLLAMA}/api/generate",
            data=json.dumps({"model": model,
                             "prompt": BRIEF_PROMPT.format(items=items),
                             "stream": False,
                             "options": {"temperature": 0, "num_predict": 300}}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            text = (json.load(r).get("response") or "").strip()
    except Exception:  # noqa: BLE001 - the digest must render without a summary
        return None
    return text if 20 < len(text) < 800 else None


def synthesize(question: str, hits: list[dict], model: str = SYNTH_MODEL) -> str | None:
    """Grounded summary with citations. Returns None if the output is unusable."""
    passages = "\n".join(
        f"[{i}] ({h.get('date') or h['source']}) {h['text'][:600]}"
        for i, h in enumerate(hits, 1))
    prompt = SYNTH_PROMPT.format(passages=passages, question=question)
    try:
        req = urllib.request.Request(
            f"{OLLAMA}/api/generate",
            data=json.dumps({"model": model, "prompt": prompt, "stream": False,
                             "options": {"temperature": 0}}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            text = (json.load(r).get("response") or "").strip()
    except Exception:  # noqa: BLE001 - fall back to extractive
        return None

    text = re.sub(r"^Here (?:are|is)[^.:\n]*[.:]\s*", "", text, flags=re.I).strip()
    low = text.lower()
    if low.startswith("i do not know"):
        return text
    if not re.search(r"\[\d\]", text) or len(text) > 1200:
        return None
    return text


def answer(question: str, index: list[dict], generator=None, k: int = 8) -> tuple[str, list[dict]]:
    """Return the most relevant things you actually wrote, verbatim, with sources.

    No generation. A question below the similarity floor gets "I do not know."
    """
    hits = search(index, question, k * 4)
    hits = _prefer_client(question, hits)
    # Project notes answer questions about Mini-Reid itself, not about work.
    if not re.search(r"mini[- ]reid|handoff|spec|this project", question, re.I):
        hits = [h for h in hits if h.get("source") != "local"]
    cleaned = []
    for h in hits:
        body = strip_email_junk(h.get("text") or "")
        if h.get("score", 0) >= MIN_SCORE and usable(body):
            cleaned.append(dict(h, text=body))
    hits, seen = [], set()
    for h in cleaned:
        key = h["text"][:120].lower()
        if key in seen:
            continue  # same email quoted in a reply chain
        seen.add(key)
        hits.append(h)
        if len(hits) == 3:
            break
    hits = sorted(hits, key=lambda h: h.get("date") or "9999")
    if not hits:
        return "I do not know.", []

    summary = synthesize(question, hits)
    if summary and len(summary) > 30:
        return summary, hits

    lines = []
    for h in hits:
        body = h["text"][:300]
        when = f" · {h['date']}" if h.get("date") else ""
        lines.append(f"• {body}{when}")
    return "\n".join(lines), hits


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
