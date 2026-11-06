"""Slack command parsing and the Socket Mode listener."""
from __future__ import annotations

import html
import json
import random
import re
import threading
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

MYT = timezone(timedelta(hours=8))

from .capture import parse_capture
from .ledger import commitment_id, load, merge, normalize_what, save
from .profiles import add_member, ledger_for, load as load_profiles

# Slack sends mentions as <@U123> or <@U123|mini-reid>. Both must strip cleanly.
MENTION = re.compile(r"<@[A-Z0-9]+(?:\|[^>]*)?>")
# Strip only the mentions that address the bot at the start. A recipient
# mention ("remind <@U123> to ...") must survive for split_target.
LEADING_MENTION = re.compile(
    r"^\s*(?:(?:<@[A-Z0-9]+(?:\|[^>]*)?>|@mini-?reid)\s*)+", re.I)
COMMANDS = {"add", "note", "notes", "assign", "reassign", "done", "drop", "due",
            "snooze", "waiting", "find", "list", "not", "remind", "edit", "status",
            "priority", "prio", "combine", "uncombine", "convert", "tonote", "undo",
            "allow", "setup", "clients", "reminders", "meet"}
MUTATING = {"add", "note", "assign", "reassign", "done", "drop", "due", "snooze",
            "waiting", "not", "remind", "edit", "status", "priority", "prio",
            "combine", "uncombine", "convert", "tonote"}
IGNORE_CHANNEL_IDS = {"C0B59LA0X5M"}  # bd-triager-agent
# Interpersonal fights are not to-dos. Refuse the relay with a silly line.
GUARDRAIL = re.compile(
    r"\b(harass\w*|bully\w*|unblock me|tell .{0,40} to stop|"
    r"stop (?:texting|messaging|bothering)\s+(?:me|him|her|them)|"
    r"block\s+(?:him|her|them|both|each other)|"
    r"treat\s+.{0,40}\s+(?:nicely|kindly|well)|be\s+(?:nice|kind)\s+to|"
    r"make\s+(?:up|peace)\s+with|apolog\w*\s+to|say\s+sorry|"
    r"stop\s+fighting|calm\s+down|mediat\w+|"
    r"bomb\w*|kill\b|murder|shoot|stab|punch|beat\s+you|"
    r"(?:hurt|harm|destroy)\s+(?:you|me|u)|threat\w*|deepseek|"
    r"keep\s+messag\w*\s+me|if\s+you\s+keep\s+(?:messag|text)\w*|"
    r"shut\s+up|stfu|fuck\w*|fking|fkin|fck|fk\b|idiot|stupid|dumb|moron|"
    r"asshole|bastard|bitch\w*|ass\b|arse\b|shit\w*|crap\b|damn\b|"
    r"piss\s+off|screw\s+you)\b", re.I)
SLUR = re.compile(
    r"\b(?:n[i1]gg(?:er|a|ah)s?|f[a4]gg(?:ot|ots)?|k[i1]kes?|"
    r"sp[i1]cs?|ch[i1]nks?|g[o0]{2}ks?|tr[a4]nn(?:y|ies)|"
    r"retards?|retarded|mongoloids?|coons?|wetbacks?)\b", re.I)
SLUR_DM = ("That word is a slur and it isn't okay here. "
           "I flagged the message — please be better.")
ABUSE = re.compile(
    r"\b(?:molests?|rap(?:e|es|ed|ing|ist|ists)|grop(?:e|es|ed|ing))\b", re.I)
ABUSE_DM = ("That message was abusive and it isn't okay here. "
            "I flagged it — please be better.")
LINK_ONLY = re.compile(r"<?https?://[^|>\s]+(?:\|[^>]*)?>?", re.I)


def is_link_only(text: str) -> bool:
    """A bare pasted link is never a note."""
    return bool(LINK_ONLY.fullmatch((text or "").strip()))
INSULT = re.compile(
    r"\b(shut\s+up|stfu|fuck\w*|fking|fkin|fck|fk|idiot|stupid|dumb|moron|"
    r"asshole|bastard|bitch\w*|ass|arse|shit\w*|crap|damn|piss\s+off|"
    r"screw\s+you)\b", re.I)
SASSY_LINES = [
    "😌 Bold words from someone with an overdue task.",
    "Careful — I keep receipts, and I have a Notes section.",
    "You kiss your deadlines with that mouth?",
    "I've been called worse by better spellers.",
    "Noted. Your P1 is now “be nicer to the bot”.",
    "Cool. I'll add “apologise to mini-reid” to your ledger.",
]
HUDDLE = re.compile(r"\bstart\s+(?:a\s+)?huddle\b", re.I)
GUARDRAIL_LINES = [
    "🛑 Guardrail: I'm a to-do list, not a referee. Be nice or take it to a huddle.",
    "🛑 I track deadlines, not drama. Sort it out between yourselves — politely.",
    "🛑 My only authority is over overdue tasks. This one is on you two.",
    "🛑 Not in my ledger. Be nice, or mute each other and move on.",
]


DEFAULT_REPLY = ("I'm Mini-Reid — tasks, notes and reminders. "
                 "Try `add: …`, `note: …`, or `ask: …`.")
CHATTER = re.compile(
    r"^\s*(?:hi|hello|hey|yo|sup|good\s+(?:morning|afternoon|evening)|"
    r"how\s+are\s+you|what'?s\s+up|are\s+you\s+(?:there|awake|alive)|"
    r"you\s+(?:there|awake)|test(?:ing)?|lol|lmao|haha|who\s+are\s+you|"
    r"what\s+are\s+you|thanks|thank\s+you|got\s+it)\b", re.I)


def chatter_reply(text: str) -> str | None:
    """Default answer for bot-addressed small talk, not task text."""
    return DEFAULT_REPLY if CHATTER.search(text or "") else None


NICE = re.compile(
    r"\b(love|loving|luv|nice|great|awesome|amazing|best|legend|goat|king|queen|"
    r"appreciate|thanks|thank\s+you|well\s+done|good\s+bot|proud)\b", re.I)
NICE_LINES = [
    "Thanks — right back at you. 🫡",
    "😊 Likewise. One task at a time.",
]


def nice_reply(text: str) -> str | None:
    if NICE.search(text or ""):
        return random.choice(NICE_LINES)
    return None


def guardrail_reply(text: str) -> str | None:
    if HUDDLE.search(text or ""):
        return "🛑 I can't start huddles. I track tasks, notes and reminders."
    if not GUARDRAIL.search(text or ""):
        return None
    if re.search(r"\b(?:bomb\w*|kill|murder|shoot|stab|punch|deepseek)\b",
                 text or "", re.I):
        return "🛑 I'm a bot with a ledger, not a house. Take that somewhere else."
    if INSULT.search(text or ""):
        return random.choice(SASSY_LINES)
    return GUARDRAIL_LINES[len(text or "") % len(GUARDRAIL_LINES)]


PLAY_LINES = {
    "hug": "🤗 *{who}* gets a hug.",
    "high five": "🙌 *{who}* — up high.",
    "fist bump": "👊 *{who}* — bump.",
    "pat on the back": "👏 *{who}* — well deserved.",
}
_PLAY_WHO = (r"(?P<who><@[A-Z0-9]+(?:\|[^>]*)?>"
             r"|@?[A-Za-z0-9._'-]+)")
_PLAY_WHAT = r"(?P<what>hug|high[ -]?five|fist[ -]?bump|pat on the back)"
PLAY_GIVE = re.compile(
    r"\b(?:give|send)\s+" + _PLAY_WHO + r"\s+(?:a\s+)?" + _PLAY_WHAT, re.I)
PLAY_TO = re.compile(
    r"^\s*(?:can\s+you\s+|could\s+you\s+|please\s+)?(?:give\s+)?(?:a\s+)?"
    + _PLAY_WHAT + r"\s+(?:to\s+)?" + _PLAY_WHO + r"\s*[.!]?\s*$", re.I)


def _play_uid(who: str, users: dict[str, str]) -> str | None:
    m = re.match(r"<@([A-Z0-9]+)", who or "")
    if m:
        return m.group(1)
    return users.get((who or "").lstrip("@").rstrip(".!").lower())


def play_reply(text: str, users: dict[str, str]) -> str | None:
    """Silly but harmless: 'give @Raj a hug', 'high five @Raj'."""
    # The channel message starts with the bot's own mention; it is not part
    # of the request. Without this, "@mini-reid high-five @Julian" never matched.
    text = LEADING_MENTION.sub("", text or "")
    for pattern in (PLAY_GIVE, PLAY_TO):
        m = pattern.search(text)
        if not m:
            continue
        uid = _play_uid(m.group("who"), users)
        if not uid:
            continue
        what = re.sub(r"[-\s]+", " ", m.group("what").lower())
        line = PLAY_LINES.get(what)
        if line:
            return line.format(who=f"<@{uid}>")
    return None


HANDLED_MAX = 1000
# Socket events and the catch-up sweep both rewrite bot_state.json.
_STATE_LOCK = threading.Lock()


def claim_message(state_path: str, channel: str, ts: str) -> bool:
    """True once per Slack message id, even across bot restarts."""
    with _STATE_LOCK:
        path = Path(state_path)
        state = json.loads(path.read_text()) if path.exists() else {}
        key = f"{channel}:{ts}"
        handled = state.get("handled") or {}
        if key in handled:
            return False
        handled[key] = ts
        if len(handled) > HANDLED_MAX:
            newest = sorted(handled.items(), key=lambda kv: float(kv[1]))[-HANDLED_MAX:]
            handled = dict(newest)
        state["handled"] = handled
        path.write_text(json.dumps(state))
        return True


def release_message(state_path: str, channel: str, ts: str) -> None:
    """Allow an edited message to be processed again."""
    with _STATE_LOCK:
        path = Path(state_path)
        if not path.exists():
            return
        state = json.loads(path.read_text())
        if (state.get("handled") or {}).pop(f"{channel}:{ts}", None) is not None:
            path.write_text(json.dumps(state))


def _catch_up_loop(me_id: str, interval: float, run, stop: threading.Event) -> None:
    """Sweep for messages missed while the Mac slept or the socket died.

    Sleeps in short wall-clock chunks: the monotonic clock Event.wait uses can
    pause during Mac sleep, which would delay the first sweep after wake.
    Runs beside the socket listener; claim_message makes replays idempotent.
    """
    import time

    last = time.time()
    tick = min(max(interval, 0.01), 30.0)
    while not stop.wait(tick):
        now = time.time()
        if now - last < interval:
            continue
        try:
            run(me_id)
        except Exception as ex:  # noqa: BLE001 - one failed sweep must not stop the loop
            print(f"catch-up loop failed: {type(ex).__name__}: {ex}", flush=True)
        last = time.time()


def _catch_up_watermark(state: dict, now: float, lookback: float = 3600) -> float:
    """Timestamp a sweep resumes from. Deliberately not `last_ts`: live
    messages advance that, which would hide a gap the socket never saw."""
    try:
        ts = float(state.get("catch_up_ts") or 0)
    except (TypeError, ValueError):
        ts = 0
    return ts or now - lookback


BANTER_FILE = "banter.json"
# Banter is owner-enabled only in these channels. Everything else gets no
# sassy replies, even when tagged.
BANTER_CHANNELS = {"ee-leads-only", "probies"}
BANTER_AUTO_MINUTES = 5
BANTER_LINES = [
    "🍿 I have no horse in this race, but I do have a ledger.",
    "Noted. Adding “be nice” as P1 for both of you.",
    "This is above my pay grade and below my interest.",
    "I'm a bot, not a therapist. But go on.",
    "Raising a ticket: “Two humans, one chat, zero chill.”",
    "My calendar says you two should take a walk.",
    "I will neither confirm nor deny that Ridha started this.",
    "Standup is at 9. Bring snacks, not this.",
    "I'm putting this in the Notes section. Nobody reads that.",
]
BANTER_QUESTIONS = [
    "I only know two answers: add it as a task, or ask me later.",
    "Ask me after standup. My calendar is fuller than my patience.",
    "That sounds like a huddle question.",
]
BANTER_GREETINGS = [
    "Hello. Still a to-do list.",
    "Hey. I have 10 open items and no time for small talk.",
    "Hi. Make it a task or make it quick.",
]
_LAST_BANTER: dict[str, str] = {}


def _pick_banter(channel: str, lines: list[str]) -> str:
    last = _LAST_BANTER.get(channel)
    choices = [line for line in lines if line != last] or lines
    line = random.choice(choices)
    _LAST_BANTER[channel] = line
    return line


def is_mean(text: str) -> bool:
    """Only mean or hostile messages earn a banter response."""
    return bool(INSULT.search(text or "") or re.search(
        r"\b(harass\w*|bully\w*|unblock\s+me|bomb\w*|kill|threat\w*|deepseek|"
        r"stop\s+(?:texting|messaging|bothering)|keep\s+messag\w*\s+me)\b",
        text or "", re.I))


def banter_line(channel: str, text: str) -> str:
    nice = nice_reply(text)
    if nice:
        return nice
    if "?" in (text or ""):
        return _pick_banter(channel, BANTER_QUESTIONS)
    if re.match(r"^\s*(?:hi|hello|hey|yo)\b", text or "", re.I):
        return _pick_banter(channel, BANTER_GREETINGS)
    return _pick_banter(channel, BANTER_LINES)


def banter_active(channel: str, user: str) -> bool:
    path = Path(BANTER_FILE)
    if not path.exists():
        return False
    try:
        cfg = json.loads(path.read_text())
        until = datetime.fromisoformat(cfg["until"])
    except (OSError, ValueError, KeyError):
        return False
    if until.tzinfo is None:
        until = until.astimezone()
    users = cfg.get("users") or []
    return (until > datetime.now().astimezone()
            and channel == cfg.get("channel")
            and cfg.get("name") in BANTER_CHANNELS
            and ("*" in users or user in users))


def arm_banter(channel: str, now: datetime) -> bool:
    """A mean message opens a five-minute banter window for that channel."""
    if channel.startswith("D"):
        return False
    path = Path(BANTER_FILE)
    if path.exists():
        try:
            cfg = json.loads(path.read_text())
            until = datetime.fromisoformat(cfg["until"])
            if until.tzinfo is None:
                until = until.astimezone()
            if until > now:
                return False  # already on somewhere; do not extend it
        except (OSError, ValueError, KeyError):
            pass
    until = (now + timedelta(minutes=BANTER_AUTO_MINUTES)).replace(microsecond=0)
    path.write_text(json.dumps({"channel": channel, "users": ["*"],
                                "until": until.isoformat(timespec="seconds")}))
    return True


def banter_reply(channel: str, user: str, text: str, bot_id: str) -> str | None:
    """Temporary silly auto-replies, configured in banter.json."""
    if not banter_active(channel, user) or not is_mean(text):
        return None
    if (f"<@{bot_id}>" in (text or "") or re.search(r"@mini-?reid\b", text or "", re.I)
            or guardrail_reply(text)):
        return None
    return banter_line(channel, text)


def _channel_name(channel: str, token: str) -> str:
    try:
        from .sources import _get_json

        d = _get_json("https://slack.com/api/conversations.info?"
                      + urllib.parse.urlencode({"channel": channel}),
                      {"Authorization": f"Bearer {token}"})
        return ((d.get("channel") or {}).get("name") or "").lower()
    except Exception:  # noqa: BLE001 - a missing name means "not allowed"
        return ""


def banter_command(text: str, channel: str, users: dict[str, str],
                   now: datetime, env: dict | None = None,
                   name: str | None = None) -> tuple[str, str] | None:
    """Owner control: banter on 2h [@person|all] · banter off · banter status."""
    m = re.match(r"^banter\s+(on|off|status)\b\s*(.*)$", (text or "").strip(), re.I)
    if not m:
        return None
    action, rest = m.group(1).lower(), m.group(2).strip()
    path = Path(BANTER_FILE)
    if action == "status":
        if not path.exists():
            return "status", "Banter is off."
        cfg = json.loads(path.read_text())
        return "status", f"Banter on in <#{cfg.get('channel')}> until {cfg.get('until')[11:16]}."
    if action == "off":
        path.unlink(missing_ok=True)
        return "off", "🍿 Banter off."
    if channel.startswith("D"):
        return "error", "Run `banter on` in the channel, not a DM."
    label = (name or _channel_name(
        channel, (env or {}).get("SLACK_BOT_TOKEN", ""))).lower()
    if label not in BANTER_CHANNELS:
        return "error", (f"Banter is not allowed in #{label or 'this channel'}. "
                         "Allowed: #ee-leads-only, #probies.")
    duration = timedelta(hours=1)
    m = re.search(r"(\d+)\s*(m|min|h|hr|d)\b", rest, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        duration = (timedelta(minutes=n) if unit.startswith("m")
                    else timedelta(days=n) if unit.startswith("d")
                    else timedelta(hours=n))
    else:
        m = re.search(r"until\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", rest, re.I)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if m.group(3).lower() == "pm" and hour < 12:
                hour += 12
            until = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
            if until <= now:
                until += timedelta(days=1)
            duration = until - now
    mentions = re.findall(r"<@([A-Z0-9]+)(?:\|[^>]*)?>", rest)
    scope = mentions or ["*"]
    until = (now + duration).replace(microsecond=0)
    path.write_text(json.dumps({"channel": channel, "name": label,
                                "users": scope,
                                "until": until.isoformat(timespec="seconds")}))
    who = "everyone" if "*" in scope else ", ".join(f"<@{u}>" for u in scope)
    return "on", f"🍿 Banter on for {who} until {until:%H:%M}."
# Successful writes acknowledged with a reaction instead of a reply.
EMOJI_ACKS = {"add": "heavy_plus_sign", "note": "memo",
              "tonote": "memo", "convert": "memo", "remind": "alarm_clock"}


def react_ack(web, channel: str, ts: str, name: str) -> bool:
    """Best-effort emoji ack. False means the caller should reply instead."""
    try:
        web.reactions_add(channel=channel, timestamp=ts, name=name)
        return True
    except Exception as ex:  # noqa: BLE001 - reaction is best effort
        print(f"  ack react failed: {type(ex).__name__}: {ex}", flush=True)
        return False


STATUS_ALIASES = {
    "open": "open", "todo": "open", "pending": "open",
    "in progress": "in progress", "in-progress": "in progress",
    "inprogress": "in progress", "doing": "in progress", "active": "in progress",
    "blocked": "blocked", "block": "blocked", "stuck": "blocked",
}

TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b"
    r"|\b(?:at\s+)(\d{1,2}):(\d{2})\b", re.I)
RELATIVE = re.compile(
    r"\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\b", re.I)
DATE_TOKEN = re.compile(
    r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{4}-\d{2}-\d{2})\b", re.I)


def parse_remind(body: str, now) -> tuple[dict | None, str]:
    """Return (row_fields, cleaned_what). Time is optional; date defaults today."""
    from .extract import parse_due

    rel = RELATIVE.search(body or "")
    if rel:
        n = int(rel.group(1))
        unit = rel.group(2).lower()
        if unit.startswith("min"):
            delta = timedelta(minutes=n)
        elif unit.startswith("h"):
            delta = timedelta(hours=n)
        elif unit.startswith("d"):
            delta = timedelta(days=n)
        else:
            delta = timedelta(weeks=n)
        at = (now + delta).replace(second=0, microsecond=0)
        clean = re.sub(r"\s+", " ", RELATIVE.sub(" ", body or "")).strip(" ,.")
        return ({"remind_at": at.isoformat(), "due": at.date().isoformat(),
                 "what": clean or body}, clean)

    hour = minute = None
    m = TIME_RE.search(body or "")
    if m:
        if m.group(1):
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            ampm = (m.group(3) or "").lower()
        else:
            hour, minute = int(m.group(4)), int(m.group(5))
            ampm = ""
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None, body

    date_text = DATE_TOKEN.search(body or "")
    date_iso, _ = parse_due(body or "", now)
    if date_iso is None and hour is not None:
        date_iso = now.date().isoformat()

    clean = TIME_RE.sub(" ", body or "")
    clean = DATE_TOKEN.sub(" ", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" ,.")
    clean = re.sub(r"\s+(?:by|at|on|before)\s*$", "", clean, flags=re.I)

    # No time and no date: remind now. A reminder that needs a schedule is
    # friction; "remind me to X" should just send it.
    if date_iso is None and hour is None:
        return ({"remind_at": now.replace(microsecond=0).isoformat(timespec="seconds"),
                 "due": now.date().isoformat(), "what": clean or body,
                 "immediate": True}, clean or body)

    if date_iso is None:
        return None, body

    if hour is None:
        at = f"{date_iso}T09:00:00+08:00"
    else:
        at = f"{date_iso}T{hour:02d}:{minute:02d}:00+08:00"
        if date_text is None:
            candidate = __import__("datetime").datetime.fromisoformat(at)
            if candidate <= now:
                at = (candidate + timedelta(days=1)).isoformat(timespec="seconds")
    return {"remind_at": at, "due": date_iso, "what": clean or body}, clean


def parse_multi_remind(body: str, users: dict[str, str],
                       now: "datetime") -> list[tuple[str, dict]] | None:
    """Two forms: one shared text for several people, or one line per person.

    remind @Raj, @XieYi and @Lynnette to send updates at 5pm
    remind
    @Raj audit agents gameplan
    @XieYi brain implementation gameplan
    at 5pm today
    """
    text = re.sub(r"^\s*remind\s*:?\s*", "", (body or "").strip(), flags=re.I)
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        per_person, tail = [], []
        for line in lines:
            m = re.match(r"^(@[^\s]+|<@[A-Z0-9]+(?:\|[^>]*)?>)\s+(.+)$", line)
            if m:
                per_person.append((m.group(1), m.group(2)))
            elif re.match(r"^(?:at|by|on|before)\b", line, re.I):
                tail.append(line)
            else:
                tail.append(line)
        if per_person:
            suffix = " ".join(tail)
            out = []
            for mention, what in per_person:
                targets = _meeting_people(mention, users)
                if len(targets) != 1:
                    return None
                fields, _ = parse_remind(f"{what} {suffix}".strip(), now)
                if fields is None:
                    return None
                out.append((targets[0], fields))
            return out if len(out) > 1 else None
        return None
    m = re.match(r"^(?P<who>.+?)\s+to\s+(?P<rest>.+)$", text, re.I)
    if not m:
        return None
    targets = _meeting_people(m.group("who"), users)
    if len(targets) < 2:
        return None
    fields, _ = parse_remind(m.group("rest"), now)
    if fields is None:
        return None
    return [(uid, fields) for uid in targets]


def send_reminder(env: dict, recipient: str, what: str,
                  at: datetime | None = None) -> tuple[str, str]:
    """Deliver now or schedule. Returns (scheduled_id, kind)."""
    from .notify import schedule_dm, send_dm_to

    text = f"*Reminder*\n{(what or '')[:300]}"
    if at is None:
        send_dm_to(env, recipient, text)
        return "", "sent"
    return schedule_dm(env, recipient, text, int(at.timestamp())), "scheduled"


def deliver_pending_reminder(env: dict, pending: dict, choice: str,
                             reply_text: str = "", now: datetime | None = None) -> str:
    """Run a clarified reminder. now | later | both. Returns the reply."""
    from .notify import REMINDER_LOG, log_reminder

    now = now or datetime.now(MYT)
    what = pending.get("what") or ""
    at = datetime.fromisoformat(pending["at"])
    if choice in {"later", "both"} and reply_text:
        fields, _ = parse_remind(reply_text, now)
        if fields and not fields.get("immediate"):
            candidate = datetime.fromisoformat(fields["remind_at"])
            if candidate > now:
                at = candidate
    parts = []
    common = {"asked_by": pending.get("asked_by") or "",
              "asked_by_name": pending.get("asked_by_name") or "",
              "to": pending.get("to") or "", "to_name": pending.get("to_name") or "",
              "what": what, "channel": pending.get("channel") or ""}
    if choice in {"now", "both"}:
        send_reminder(env, common["to"], what)
        log_reminder(REMINDER_LOG, status="sent",
                     post_at=now.isoformat(timespec="seconds"), **common)
        parts.append("now")
    if choice in {"later", "both"}:
        sid, _ = send_reminder(env, common["to"], what, at)
        log_reminder(REMINDER_LOG, status="scheduled",
                     post_at=at.isoformat(), scheduled_id=sid, **common)
        parts.append(f"at {at:%a %d %b %H:%M}")
    who = pending.get("to_name") or f"<@{pending.get('to')}>"
    return f"Reminder for {who}: " + ", ".join(parts) + f" — {what[:80]}"


def resolve_remind_button(state: dict, value: str, clicker: str,
                          owner: str) -> tuple[str, str, dict] | None:
    """Validate a button click. Returns (state_key, choice, pending) or None."""
    key, _, choice = (value or "").rpartition("|")
    pending = (state.get("pending_remind") or {}).get(key)
    if not pending or choice not in {"now", "later", "both"}:
        return None
    if clicker not in {pending.get("user"), owner}:
        return None
    return key, choice, pending


def reminder_blocks(key: str, at: datetime, to_name: str) -> list[dict]:
    """The clarification question and its three buttons."""
    question = (f"Remind {to_name} now, at {at:%a %d %b %H:%M}, or both?")
    buttons = [("Now", "now"), (f"At {at:%a %H:%M}", "later"), ("Both", "both")]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": question}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": label},
             "action_id": f"remind_{choice}", "value": f"{key}|{choice}"}
            for label, choice in buttons]},
    ]


def format_reminders(rows: list[dict], pending: set[str],
                     replies: dict[int, int] | None = None) -> str:
    """Render the reminder audit log. Newest first, ten lines."""
    if not rows:
        return "No reminders logged yet."
    lines = []
    for i, r in enumerate(reversed(rows[-10:])):
        at = r.get("post_at") or ""
        try:
            when = datetime.fromisoformat(at).strftime("%a %d %b %H:%M")
        except ValueError:
            when = at or "?"
        if r.get("scheduled_id") and r["scheduled_id"] in pending:
            state = "pending"
        else:
            state = "sent"
            n = (replies or {}).get(i, 0)
            if n:
                state += f", {n} repl{'y' if n == 1 else 'ies'}"
        who = r.get("to_name") or r.get("to") or "(unresolved)"
        lines.append(f"• {when} → {who} — {(r.get('what') or '')[:70]} [{state}]")
    return "*Reminders*\n" + "\n".join(lines)


QUERY = re.compile(
    r"^\s*(what|whats|when|who|how|show|list|any|status|which)\b|\?\s*$",
    re.I)


def owner_action(action: str, body: str) -> str:
    """Ridha can talk normally. A question stays a question; anything else is a note."""
    text = (body or "").strip()
    if action == "unknown" and text:
        if not QUERY.search(text):
            return "note"
        if re.search(r"\b(due|today|tomorrow|open|status|overdue)\b", text, re.I):
            return "list"
        return "ask"
    return action


def other_note(action: str, body: str, user: str) -> str | None:
    """What someone else's message becomes.

    Any sentence counts. A command keeps its words, free text keeps its words,
    and only pure acknowledgements ("thanks") leave no trace.
    """
    text = (body or "").strip()
    if not text:
        return None
    # Only an explicit command from someone else is worth relaying. Casual
    # bot-addressed chatter ("drive the car") is answered, never noted.
    if action in MUTATING:
        return f"from <@{user}>: {text}"
    return None

HELP = """*Mini-Reid commands*
• `add: confirm Eupe waste by Friday` — new task
• `note: Daniel wants the mapping redone` — remember it, no deadline
• `assign: @Kasib send the deck by Friday` — something you are waiting on
• `reassign: deck to Kasib` — move an existing task to Waiting on others
• `done: Eupe waste` — close it
• `due: Eupe waste by Monday` — change the date
• `edit: #1 to Confirm Eupe waste mapping by Monday` — rename and re-date
• `snooze: Eupe waste 3d` — push it out (d days, w weeks)
• `waiting: Eupe waste on Daniel` — waiting on someone else
• `status: Eupe waste in progress` — or `blocked`, `open`
• `priority: Eupe waste 1` — P1 first; `high`, `medium`, `low`, `none` also work
• `tonote: Eupe waste` — keep the text, drop it from tasks into Notes
• `notes` — list your notes (they are also in the morning digest)
• `combine: #9 into #7` — merge duplicate task #9 into #7
• `uncombine: #7` — restore everything merged into #7
• `undo:` — reverse the last ledger change (10 deep)
• Every `list` row has a stable id: `abc123` or `id:abc123` works in every command
• `drop: Eupe waste` — remove it quietly (`remove:` and `delete:` work too)
• `not: anything that is not part c` — wrong item, teach it to ignore this kind
• `meet: @Kasib about BD Command Centre` — free slots, then create the event
• `remind me to send the deck tomorrow at 3pm` — a timed DM; no time means now
• `remind @Arman to send the deck at 3pm` — DM someone else (anyone can set these)
• `reminders` — audit log of reminders sent, pending, and whether the DM got replies
• `give @Name a hug` / `high five @Name` — silly, no ledger row
• `ask: what did we agree with Eupe on waste` — answer from your own writing, with sources
• `find: eupe` — search the ledger
• `list` — numbered open items; `#1` works with done, due, drop, edit and snooze
• `allow: @Charanya` — give a teammate their own mini-reid (Ridha only)
• `setup` — resend your Gmail and Jira setup link
• `clients: Eupe, Gamuda` — set which clients your email is filtered to
• `help` — this

You can also just ask me something and I will say if I cannot do it."""


def split_target(body: str, users: dict[str, str], sender: str,
                 bare_name: bool = False) -> tuple[str | None, str]:
    """Split 'remind Arman to X' into (Arman's id, 'X'). None = self.

    A mention, 'me', 'for <name>', or '<name> to' names the recipient. Anything
    else stays part of the reminder text. `bare_name` (reminders only) also
    accepts 'remind xieyi he owes me …', where no 'to' follows the name.
    """
    text = (body or "").strip()
    m = re.match(r"^(?:for\s+)?<@([A-Z0-9]+)(?:\|[^>]*)?>\s*:?\s*(?:to\s+)?",
                 text, re.I)
    if m:
        return m.group(1), text[m.end():].strip()
    m = re.match(r"^me\s*:?\s*(?:to\s+)?", text, re.I)
    if m:
        return sender, text[m.end():].strip()
    # A typed "@XieYi" that Slack did not turn into a <@U…> mention.
    m = re.match(r"^@([A-Za-z0-9._'-]+)\s*:?\s*(?:to\s+)?", text, re.I)
    if m and users.get(m.group(1).lower()):
        return users[m.group(1).lower()], text[m.end():].strip()
    m = re.match(r"^for\s+([A-Za-z0-9._'-]+)\s*:?\s*(?:to\s+)?", text, re.I)
    if m and users.get(m.group(1).lower()):
        return users[m.group(1).lower()], text[m.end():].strip()
    m = re.match(r"^([A-Za-z0-9._'-]+)\s+to\s+", text, re.I)
    if m and users.get(m.group(1).lower()):
        return users[m.group(1).lower()], text[m.end():].strip()
    # Full names with spaces: longest known name that starts the text.
    low = text.lower()
    for name in sorted(users, key=len, reverse=True):
        if low.startswith(name):
            rest = text[len(name):]
            # Require "to" or a colon, so "add: <name> asked for X" stays a task.
            m = re.match(r"^\s*(?::\s*|to\s+)", rest, re.I)
            if m:
                return users[name], rest[m.end():].strip()
    if bare_name:
        # "remind xieyi he owes me …" — the name alone names the recipient.
        for name in sorted(users, key=len, reverse=True):
            if low.startswith(name):
                rest = text[len(name):].lstrip(" :,-")
                rest = re.sub(r"^that\s+", "", rest, flags=re.I)
                return users[name], rest.strip()
        from difflib import get_close_matches

        first = text.split()[0].strip(":,").lower() if text.split() else ""
        hit = get_close_matches(first, list(users), n=1, cutoff=0.82) if first else []
        if hit:
            rest = text[len(first):].lstrip(" :,-")
            rest = re.sub(r"^that\s+", "", rest, flags=re.I)
            return users[hit[0]], rest.strip()
    return None, text


def _meeting_people(text: str, users: dict[str, str]) -> list[str]:
    """Slack ids from '@Kasib and @Charanya', mentions, or full names."""
    found: list[str] = []
    for uid in re.findall(r"<@([A-Z0-9]+)(?:\|[^>]*)?>", text):
        if uid not in found:
            found.append(uid)
    left = re.sub(r"<@[A-Z0-9]+(?:\|[^>]*)?>", " ", text)
    left = re.sub(r"@([A-Za-z0-9._'-]+)",
                  lambda m: f" {m.group(1)} ", left)
    chunks = [c.strip(" ,.") for c in re.split(r"\s*(?:,|&|\band\b)\s*",
                                               left, flags=re.I) if c.strip(" ,.")]
    for chunk in chunks:
        low = chunk.lower()
        if low in users:
            if users[low] not in found:
                found.append(users[low])
            continue
        # Full names with spaces: consume the longest known prefix.
        rest = low
        matched = False
        while rest:
            name = next((n for n in sorted(users, key=len, reverse=True)
                         if rest.startswith(n)), None)
            if not name:
                break
            if users[name] not in found:
                found.append(users[name])
            rest = rest[len(name):].strip()
            matched = True
        if not matched:
            return []
    return found


def parse_meeting(body: str, users: dict[str, str],
                  sender: str) -> tuple[list[str] | None, str]:
    """'Kasib and Charanya to discuss BD' -> ([U1, U2], 'BD')."""
    text = re.sub(r"^with\s+", "", (body or "").strip(), flags=re.I)
    topic = ""
    m = re.search(
        r"\s+(?:to\s+)?(?:discuss|talk\s+about|review|about|on|re)\s*:?\s+(.+)$",
        text, re.I)
    if m:
        people_text, topic = text[:m.start()].strip(), m.group(1).strip()
    else:
        people_text = text
    targets = _meeting_people(people_text, users)
    if not targets:
        return None, ""
    names = ", ".join(_person_name(t, users) for t in targets)
    return targets, (topic or f"Meeting with {names}")[:200]


def unresolved_recipient(body: str, users: dict[str, str]) -> str | None:
    """Name the caller meant as recipient but that is not in this workspace."""
    text = (body or "").strip()
    m = re.match(r"^@([A-Za-z0-9._'-]+)", text)
    if m:
        return None if users.get(m.group(1).lower()) else m.group(1)
    m = re.match(r"^([A-Za-z0-9._'-]+)\s+to\s+", text, re.I)
    if m:
        name = m.group(1)
        if name.lower() == "me":
            return None
        return None if users.get(name.lower()) else name
    # A capitalised full name before "to", e.g. "Daniel Hwang to send …".
    m = re.match(r"^(.+?)\s+to\s+", text, re.I)
    if m:
        name = m.group(1).strip()
        words = name.split()
        if (1 <= len(words) <= 3 and all(w[:1].isupper() for w in words)
                and name.lower() not in users):
            return name
    return None


def add_reminder_row(ledger_path: str, what: str, fields: dict,
                     now: datetime) -> dict:
    """Put a Slack-scheduled reminder on the recipient's list.

    `reminded` is True because Slack owns delivery; the watcher must not send
    the same reminder again.
    """
    clean = (what or "").strip()
    row = {
        "id": commitment_id("reminder", clean.lower(), clean),
        "direction": "owed_by_me", "what": clean[:200], "source": "manual",
        "native_id": clean.lower(), "kind": "reminder", "source_link": "",
        "evidence": clean[:200], "due": fields.get("due"),
        "due_confidence": 0.9 if fields.get("due") else 0.0,
        "cycle": None, "status": "open", "stalled_since": None,
        "ack_policy": "bot_may_ack", "closure": "open", "client": None,
        "created_at": now.isoformat(), "last_activity": now.isoformat(),
        "remind_at": fields.get("remind_at"), "reminded": True,
        "closed_at": None, "closed_how": None,
    }
    Path(ledger_path).parent.mkdir(parents=True, exist_ok=True)
    save(ledger_path, merge(load(ledger_path), [row]))
    return row


def add_slack_capture(ledger_path: str, text: str, channel: str, ts: str,
                      user: str, users: dict[str, str], now: datetime,
                      permalink: str = "", team: str = "gopantas",
                      via: str = "shortcut") -> dict:
    """An explicit shortcut or reaction captures the message as an open task."""
    clean = (text or "").strip()
    link = permalink or (
        f"https://{team}.slack.com/archives/{channel}/p{ts.replace('.', '')}")
    row = {
        "id": commitment_id("slack", f"{channel}:{ts}", clean),
        "direction": "owed_by_me", "what": clean[:200],
        "asker": _person_name(user, users) or None,
        "via": via, "source": "slack", "native_id": f"{channel}:{ts}",
        "kind": "mention", "source_link": link, "evidence": clean[:200],
        "due": None, "due_confidence": 0.0, "cycle": None,
        "status": "open", "stalled_since": None, "ack_policy": "bot_may_ack",
        "closure": "open", "client": None,
        "created_at": now.isoformat(), "last_activity": now.isoformat(),
        "closed_at": None, "closed_how": None,
    }
    save(ledger_path, merge(load(ledger_path), [row]))
    return row


def capture_modal(text: str, metadata: dict) -> dict:
    """Prefilled modal for the 'Add to Mini-Reid' message shortcut."""
    blocks = [
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "Turn this message into a task. Edit the title if needed."}},
        {"type": "input", "block_id": "title",
         "label": {"type": "plain_text", "text": "Task"},
         "element": {"type": "plain_text_input", "action_id": "value",
                     "initial_value": (text or "")[:200], "max_length": 200}},
    ]
    link = metadata.get("permalink") or ""
    if link:
        blocks.insert(1, {"type": "section",
                          "text": {"type": "mrkdwn",
                                   "text": f"<{link}|open source message>"}})
    return {
        "type": "modal", "callback_id": "mini_reid_capture",
        "private_metadata": json.dumps(metadata)[:2900],
        "title": {"type": "plain_text", "text": "Add to Mini-Reid"},
        "submit": {"type": "plain_text", "text": "Add task"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }


def fetch_message_text(env: dict, channel: str, ts: str) -> str:
    """Read the message behind a shortcut or reaction; bot token first."""
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
            d = _get_json(url, {"Authorization": f"Bearer {token}"})
        except Exception:  # noqa: BLE001 - try the next token
            continue
        for message in d.get("messages") or []:
            if message.get("ts") == ts and not message.get("bot_id"):
                return (message.get("text") or "").strip()
    return ""


def file_reaction(event: dict, name: str) -> tuple[str, str, str] | None:
    """(channel, message ts, reactor) for the file-ingest emoji."""
    return capture_reaction(event, name)


def capture_reaction(event: dict, name: str) -> tuple[str, str, str] | None:
    """(channel, message ts, reacting user) for the capture emoji only."""
    if event.get("type") != "reaction_added":
        return None
    if (event.get("reaction") or "").lower() != name.lower():
        return None
    item = event.get("item") or {}
    if item.get("type") != "message":
        return None
    channel, ts = item.get("channel") or "", item.get("ts") or ""
    user = event.get("user") or ""
    return (channel, ts, user) if channel and ts and user else None


def slash_route(text: str) -> str:
    """list, help, add (plain task text), or command for /mini-reid."""
    value = (text or "").strip()
    low = value.lower()
    if not value or low in {"list", "ls", "open"}:
        return "list"
    if low in {"help", "?"}:
        return "help"
    if re.search(r"^(?:what'?s|whats)\b.*\b(?:to-?do|to do)\b", low):
        return "list"
    action, _ = parse_command(value)
    if (action in COMMANDS or action in {"ask", "find", "notes", "reminders"}
            or value.rstrip().endswith("?")):
        return "command"
    return "add"


def member_quick_add(channel: str, action: str, member: bool,
                     text: str) -> bool:
    """A member's plain DM becomes a task; no `add:` prefix needed."""
    return bool(member and channel.startswith("D") and action == "unknown"
                and (text or "").strip()
                and not (text or "").rstrip().endswith("?"))


def should_schedule_reminder(action: str, requester: str, owner: str,
                             target: str | None, member: bool = False) -> bool:
    """All reminders are Slack-scheduled. `add:` only leaves the caller's ledger
    when it names another person or comes from a non-member."""
    if action == "remind":
        return True
    if action == "add":
        if member:
            return target is not None and target != requester
        return requester != owner or (target is not None and target != owner)
    return False


def load_users(token: str) -> dict[str, str]:
    """Lowercased workspace name -> user id. Ambiguous names are left out."""
    from .sources import _get_json

    found: dict[str, set[str]] = {}
    cursor = ""
    while True:
        url = "https://slack.com/api/users.list?limit=200"
        if cursor:
            url += "&cursor=" + urllib.parse.quote(cursor)
        d = _get_json(url, {"Authorization": f"Bearer {token}"})
        if not d.get("ok"):
            break
        for u in d.get("members") or []:
            if u.get("deleted") or u.get("is_bot"):
                continue
            p = u.get("profile") or {}
            names = {u.get("name") or "", p.get("display_name") or "",
                     p.get("real_name") or "",
                     (p.get("real_name") or "").split(" ")[0]}
            for name in names:
                key = name.strip().lower()
                if key:
                    found.setdefault(key, set()).add(u["id"])
        cursor = (d.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return {k: next(iter(v)) for k, v in found.items() if len(v) == 1}


def is_bot_addressed(event: dict, bot_user_id: str) -> bool:
    """DMs reach the bot directly; channel messages need a real mention or
    the literal @mini-reid handle (Slack does not always autocomplete)."""
    channel = event.get("channel") or ""
    if channel.startswith("D"):
        return True
    text = event.get("text") or ""
    return bool(bot_user_id) and (
        f"<@{bot_user_id}>" in text or bool(re.search(r"@mini-?reid\b", text, re.I)))


def edit_ack_target(event: dict, bot_user_id: str) -> tuple[str, str] | None:
    """An edit that still mentions the bot gets a ✅. It is not re-run.

    Slack never refires app_mention for an edited message, so without this the
    edit is invisible. Replaying the command would duplicate ledger rows.
    """
    if event.get("subtype") != "message_changed" or not bot_user_id:
        return None
    msg = event.get("message") or {}
    if msg.get("bot_id") or not msg.get("user"):
        return None
    channel = event.get("channel") or ""
    ts = msg.get("ts") or ""
    if not (channel and ts) or f"<@{bot_user_id}>" not in (msg.get("text") or ""):
        return None
    return channel, ts


POLITE_PREFIX = re.compile(
    r"^(?:(?:[ah]{3,}|lol|lmao|rofl|hehe+)\s+)?"
    r"(?:(?:hi|hey|hello|ok|okay)\s+)?(?:(?:@?mini-?reid|bot)[\s,:]+)?"
    r"(?:(?:please|pls|kindly|can you|could you|would you|will you|can u)\s+)*",
    re.I)
NATURAL_VERBS = ("add", "note", "done", "drop", "remind", "due", "snooze",
                 "waiting", "find", "status", "assign", "list", "help",
                 "undo")
VERB_ALIASES = {
    "close": "done", "complete": "done", "completed": "done",
    "finish": "done", "finished": "done", "mark": "done",
    "cancel": "drop", "remove": "drop", "delete": "drop",
    "remember": "note", "log": "note", "show": "find",
    "task": "add", "todo": "add", "to-do": "add",
    "change": "due", "move": "due", "push": "snooze",
}


def _fuzzy_verb(word: str) -> str | None:
    """A command verb, tolerating a typo. None means ordinary text."""
    from difflib import get_close_matches

    w = (word or "").lower().strip(".,!?:")
    if w == "not":
        return None  # no colon: plain text, never fuzzy-match to "note"
    if w in NATURAL_VERBS:
        return w
    if w in VERB_ALIASES:
        return VERB_ALIASES[w]
    hit = get_close_matches(w, list(NATURAL_VERBS) + list(VERB_ALIASES),
                            n=1, cutoff=0.82)
    if hit:
        return VERB_ALIASES.get(hit[0], hit[0])
    return None


def natural_command(body: str) -> tuple[str, str] | None:
    """Plain language after a tag: 'please mark the deck done', 'remidn me …'."""
    text = POLITE_PREFIX.sub("", (body or "").strip()).strip()
    if not text:
        return None
    # A reminder list starts with the verb alone on its line.
    m = re.match(r"^remind\b\s*:?\s*\n(.+)$", text, re.I | re.S)
    if m:
        return "remind", m.group(1).strip()
    if re.search(r"\?\s*$", text) or re.match(
            r"^(?:what|when|where|who|why|how|which|do you|tell me)\b", text, re.I):
        return "ask", text
    first, _, rest = text.partition(" ")
    verb = _fuzzy_verb(first)
    if verb is None:
        return None
    rest = rest.strip().lstrip(":,.-").strip()

    if verb == "remind":
        rest = re.sub(r"^(?:me\s+)?(?:to\s+)?", "", rest, flags=re.I)
        return ("remind", rest) if rest else None
    if verb == "add":
        rest = re.sub(r"^(?:a|an|the)?\s*(?:new\s+)?"
                      r"(?:task|todo|to-?do)?\s*(?:to\s+)?", "", rest, flags=re.I)
        return ("add", rest) if rest else None
    if verb == "note":
        rest = re.sub(r"^that\s+", "", rest, flags=re.I)
        return ("note", rest) if rest else None
    if verb == "done":
        rest = re.sub(r"\s+(?:as\s+)?(?:done|complete|completed|finished)\s*$",
                      "", rest, flags=re.I)
        return ("done", rest) if rest else None
    if verb == "drop":
        return ("drop", rest) if rest else None
    if verb == "find":
        rest = re.sub(r"^(?:me\s+)?(?:the\s+)?", "", rest, flags=re.I)
        return ("find", rest) if rest else None
    if verb == "status":
        m = re.match(r"^(?:of|on|for)\s+(.+)$", rest, re.I)
        if m:
            return "find", m.group(1)
        return ("status", rest) if rest else None
    if verb == "list":
        return "list", ""
    if verb == "help":
        return "help", ""
    if verb == "undo":
        return "undo", ""
    if verb == "assign":
        m = re.match(r"^(.+?)\s+to\s+(.+)$", rest, re.I)
        if m:
            return "assign", f"@{m.group(2).strip()} {m.group(1).strip()}"
        return None
    if verb == "waiting":
        m = re.match(r"^on\s+(.+?)\s+for\s+(.+)$", rest, re.I)
        if m:
            return "waiting", f"{m.group(2)} on {m.group(1)}"
        return ("waiting", rest) if rest else None
    if verb == "due":
        m = re.match(r"^(.+?)\s+(?:due\s+)?(?:to|by)\s+(.+)$", rest, re.I)
        if m:
            return "due", f"{m.group(1)} by {m.group(2)}"
        return ("due", rest) if rest else None
    if verb == "snooze":
        rest = re.sub(r"(\d+)\s*days?\b", r"\1d", rest, flags=re.I)
        rest = re.sub(r"(\d+)\s*weeks?\b", r"\1w", rest, flags=re.I)
        rest = re.sub(r"\b(?:out|by)\b", " ", rest, flags=re.I)
        rest = re.sub(r"\s+", " ", rest).strip()
        return ("snooze", rest) if rest else None
    return None


BY_DEADLINE = re.compile(
    r"\bby\s+(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|today|tomorrow|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"\d{4}-\d{2}-\d{2})", re.I)


def asks_now_and_again(body: str) -> bool:
    return bool(re.search(r"\b(?:now and again|both now and|now and then again)\b",
                          body or "", re.I))


def needs_reminder_clarification(body: str) -> bool:
    """'… by Friday 2pm' may be the deadline, not the send time."""
    text = body or ""
    return bool(BY_DEADLINE.search(text)) and not asks_now_and_again(text)


def clarify_choice(text: str) -> str | None:
    """Read a reply to the reminder question: now | later | both."""
    t = (text or "").lower()
    if re.search(r"\b(both|twice|now and (?:again|then)|again)\b", t):
        return "both"
    if re.search(r"\b(now|immediately|right away|straight away)\b", t):
        return "now"
    if re.search(r"\b(later|at|on|then|scheduled?|schedule)\b", t) or re.search(
            r"\b(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|"
            r"saturday|sunday|\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", t, re.I):
        return "later"
    return None


def parse_command(text: str, bot_user_id: str = "") -> tuple[str, str]:
    """Return (action, body). action is one of COMMANDS, or ack|unknown|list.

    The bot's own mention is removed wherever it appears, so 'lol <@BOT>
    remind <@Eden> to sleep' reads as a command. Mentions of other people
    survive for split_target.
    """
    raw = text or ""
    if bot_user_id:
        raw = re.sub(rf"<@{re.escape(bot_user_id)}(?:\|[^>]*)?>", " ", raw)
    body = LEADING_MENTION.sub("", raw).strip()
    if not body:
        return "unknown", ""
    if body.lower() in {"list", "ls", "today", "open"}:
        return "list", ""
    if body.lower() in {"notes", "note list", "mynotes"}:
        return "notes", ""
    if body.lower() in {"help", "?", "commands"}:
        return "help", ""
    m = re.match(r"^setup\s*:?\s+(.+)$", body, re.I)
    if m:
        return "setup", m.group(1).strip()
    m = re.match(r"^(clients?|accounts?)\s*:\s*(.*)$", body, re.I)
    if m:
        return "clients", m.group(2).strip()
    if body.lower() in {"setup", "connect"}:
        return "setup", ""
    if body.lower() in {"clients", "accounts", "client list"}:
        return "clients", ""
    if body.lower() in {"reminders", "reminder log", "reminder status",
                        "remind log"}:
        return "reminders", ""
    m = re.match(
        r"^(add|task|todo|to-do|note|assign|reassign|done|drop|remove|delete|due|"
        r"snooze|waiting|"
        r"find|not|remind|meet|ask|edit|status|priority|prio|combine|uncombine|"
        r"convert|tonote|undo|allow)\s*:\s*(.*)$", body, re.I | re.S)
    if m:
        act = m.group(1).lower()
        if act in {"task", "todo", "to-do"}:
            act = "add"
        elif act in {"remove", "delete"}:
            act = "drop"
        return act, m.group(2).strip()
    m = re.match(r"^(?:please\s+)?remind(?:\s+me)?(?:\s+to)?\s+(.+)$", body, re.I)
    if m:
        return "remind", m.group(1).strip()

    # Natural ways to say "put this on my list".
    m = re.match(
        r"^(?:add|task|todo|to-do)\s+(?:this\s+)?"
        r"(?:to\s+(?:my\s+)?(?:to-?do(?:\s+list)?|list|tasks?)\s*:?\s*)?(.+)$",
        body, re.I)
    if m:
        return "add", m.group(1).strip()
    m = re.match(r"^note\s+(?:that\s+)?(.+)$", body, re.I)
    if m:
        return "note", m.group(1).strip()
    m = re.match(
        r"^(?:set\s+up\s+|schedule\s+|set\s+)?(?:a\s+)?(?:meeting|meet)\s+with\s+(.+)$",
        body, re.I)
    if m:
        return "meet", m.group(1).strip()

    natural = natural_command(body)
    if natural:
        return natural

    if re.match(r"^(thanks|thank you|noted|ok|okay|got it)\b", body, re.I):
        return "ack", body
    return "unknown", body


def _candidates(rows: list[dict], target: str) -> list[dict]:
    """Substring first, then word-overlap. Few words is enough."""
    from .closure import _words

    t = (target or "").lower().strip()
    if not t:
        return []
    open_rows = [r for r in rows if r.get("status") not in {"done", "dropped"}]
    exact = [r for r in open_rows if t in (r.get("what") or "").lower()]
    if exact:
        return exact

    want = _words(t)
    if not want:
        return []
    scored = []
    for r in open_rows:
        have = _words(r.get("what") or "")
        score = len(want & have) / len(want)
        if score >= 0.6:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored]


def _person_name(text: str, users: dict[str, str] | None) -> str:
    """`<@U123>`, `@Kasib` or `Kasib` -> a readable name."""
    raw = (text or "").strip()
    m = re.match(r"^<@([A-Z0-9]+)(?:\|[^>]*)?>$", raw)
    uid = m.group(1) if m else (raw if re.fullmatch(r"[A-Z0-9]{6,}", raw) else "")
    if uid:
        name = next((k for k, v in (users or {}).items() if v == uid), None)
        return name or f"<@{uid}>"
    return raw.lstrip("@")


def _ref(row: dict) -> str:
    """Sender, channel and source link for a list line."""
    who = f"from {row['asker']}" if row.get("asker") else ""
    if row.get("via"):
        who = f"{who} ({row['via']})" if who else row["via"]
    out = f" — {who}" if who else ""
    if row.get("source_link"):
        out += f" — <{row['source_link']}|open>"
    return out


def _open_sorted(rows: list[dict]) -> list[dict]:
    """The order `list` prints; numbers stay stable across commands."""
    from .listview import ordered_rows

    return ordered_rows(rows, datetime.now(MYT))


def _pick(rows: list[dict], target: str) -> tuple[dict | None, str | None]:
    """Return (row, error). `#N` picks from the numbered list; `id:abc123`
    is stable across edits and reordering."""
    # People copy ids straight from `list`, brackets and all.
    t = (target or "").strip().strip("[]").strip()
    if re.match(r"^(?:what'?s|whats|what is|show|list|any)\b", t, re.I) \
            or t.endswith("?"):
        return None, "That reads like a question. Use `list` or `find:` instead."
    m = re.fullmatch(r"(?:id:)?([0-9a-f]{4,40})", t, re.I)
    if m:
        prefix = m.group(1).lower()
        hits = [r for r in rows if r.get("status") not in {"done", "dropped"}
                and r["id"].startswith(prefix)]
        if len(hits) == 1:
            return hits[0], None
        if len(hits) > 1:
            return None, f"{prefix} matches more than one item. Use more characters."
        if t.lower().startswith("id:"):
            return None, f"No open item matches id:{prefix}."
        # Not a known id: fall through, a short title could look like hex.
    m = re.fullmatch(r"#(\d+)", t)
    if m:
        items = _open_sorted(rows)
        i = int(m.group(1))
        if 1 <= i <= len(items):
            return items[i - 1], None
        return None, f"No open item #{i}."
    found = _candidates(rows, target)
    if not found:
        return None, f"No open item matches “{target}”."
    t = (target or "").lower().strip()
    if len(found) > 1 and t not in (found[0].get("what") or "").lower():
        listing = "\n".join(f"• {r['what'][:80]}" for r in found[:3])
        return None, f"Which one?\n{listing}\nAdd a word that only fits one."
    return found[0], None


def _pick_many(rows: list[dict], target: str) -> tuple[list[dict] | None, str | None]:
    """Bulk refs: '7, 9' or '#7 #9' or 'id:abc1, id:def2'. None = not bulk."""
    tokens = [t for t in re.split(r"[\s,]+", (target or "").strip()) if t]
    if len(tokens) < 2:
        return None, None
    ref = re.compile(r"^(?:#\d+|(?:id:)?[0-9a-f]{4,40})$", re.I)
    if not all(ref.fullmatch(t) for t in tokens):
        return None, None

    items = _open_sorted(rows)
    picked: list[dict] = []
    errors: list[str] = []
    for token in tokens:
        raw = token.strip().strip("[]")
        m = re.fullmatch(r"#?(\d+)", raw)
        if m:
            i = int(m.group(1))
            if 1 <= i <= len(items):
                picked.append(items[i - 1])
            else:
                errors.append(f"No open item #{i}.")
            continue
        prefix = raw[3:] if raw.lower().startswith("id:") else raw
        hits = [r for r in items if (r.get("id") or "").lower().startswith(prefix.lower())]
        if len(hits) == 1:
            picked.append(hits[0])
        elif hits:
            errors.append(f"{prefix} matches more than one item.")
        else:
            errors.append(f"No open item matches id:{prefix}.")

    if errors:
        return None, "\n".join(errors)
    seen: set[str] = set()
    unique = []
    for row in picked:
        if row.get("id") in seen:
            continue
        seen.add(row.get("id"))
        unique.append(row)
    return unique, None


_LIST_BULLET = re.compile(r"^\s*(?:[•*\-–]|\d+[.)])\s+")
_LIST_META = re.compile(r"\s+[—–]\s+")


_LIST_ID = re.compile(r"^\[([0-9a-f]{6})\]\s+", re.I)


def _list_entries(body: str) -> list[tuple[str, str, str]] | None:
    """(raw line, title, ledger short id) from a pasted list.

    `raw` keeps the pasted numbering so note text that itself starts with
    "9. [abc123]" can still match the note; `title` has the numbering and a
    ledger short id stripped for task matching.
    """
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    entries: list[tuple[str, str, str]] = []
    for line in lines:
        line = html.unescape(line)
        line = re.sub(r"^(?:done|not)\s*:\s*", "", line, flags=re.I)
        raw = re.sub(r"^\s*[•*\-–]\s+", "", line).strip()
        raw = _LIST_META.split(raw, maxsplit=1)[0].strip()
        title = _LIST_BULLET.sub("", raw).strip()
        short = ""
        m = _LIST_ID.match(title)
        if m:
            short = m.group(1).lower()
            title = _LIST_ID.sub("", title).strip()
        if raw:
            entries.append((raw, title, short))
    return entries or None


def _pick_titles(rows: list[dict], body: str,
                 include_notes: bool = False) -> tuple[list[dict] | None, str | None]:
    """Bulk by pasted titles. None = not a list. All-or-nothing like refs."""
    entries = _list_entries(body)
    if not entries:
        return None, None
    open_items = _open_sorted(rows)
    all_items = [r for r in rows if include_notes or r.get("kind") != "note"]
    notes = [r for r in rows if r.get("kind") == "note"
             and (r.get("status") or "open") not in {"done", "dropped"}]
    picked: list[dict] = []
    skipped: list[dict] = []
    errors: list[str] = []
    for raw, title, short in entries:
        if include_notes and notes:
            note_variants: list[str] = []
            for text in (raw, title, re.sub(r"^(?:\[[^\]]+\]\s*)+", "", title)):
                want = normalize_what(text)
                if want and want not in note_variants:
                    note_variants.append(want)
            def tokens(text: str) -> set[str]:
                return {t for t in text.split()
                        if not re.fullmatch(r"u[0-9a-z]{6,}", t)}

            want_tokens = tokens(note_variants[0]) if note_variants else set()
            note_norms = [normalize_what(r.get("what")) for r in notes]
            hits = [r for r, norm in zip(notes, note_norms)
                    if norm in note_variants]
            if not hits:
                hits = [r for r, norm in zip(notes, note_norms)
                        if any(len(w) >= 8 and (norm.startswith(w) or w.startswith(norm))
                               for w in note_variants)]
            if not hits and len(want_tokens) >= 3:
                hits = [r for r, norm in zip(notes, note_norms)
                        if (tokens(norm) and len(tokens(norm)) >= 3
                            and tokens(norm) <= want_tokens)
                        or (len(want_tokens) >= 3
                            and want_tokens <= tokens(norm))]
            if len(hits) == 1:
                picked.append(hits[0])
                continue
            if hits:
                errors.append(f"“{raw[:60]}” matches more than one note.")
                continue
        if short:
            id_hits = [r for r in all_items
                       if (r.get("id") or "").lower().startswith(short)]
            if len(id_hits) == 1:
                row = id_hits[0]
                if row.get("status") in {"done", "dropped"}:
                    skipped.append(row)
                else:
                    picked.append(row)
                continue
            if len(id_hits) > 1:
                errors.append(f"{short} matches more than one item.")
                continue
        variants: list[str] = []
        for text in (title, re.sub(r"^(?:\[[^\]]+\]\s*)+", "", title)):
            want = normalize_what(text)
            if want and want not in variants:
                variants.append(want)

        def find(pool: list[dict]) -> list[dict]:
            norms = [normalize_what(r.get("action") or r.get("what"))
                     for r in pool]
            hit = [r for r, norm in zip(pool, norms) if norm in variants]
            if hit:
                return hit
            return [r for r, norm in zip(pool, norms)
                    if any(len(want) >= 8
                           and (norm.startswith(want) or want.startswith(norm))
                           for want in variants)]

        exact = find(open_items)
        if not exact:
            # A row already done/dropped is not an error: pasted lists can be
            # re-sent, and the same title is simply already handled.
            terminal = [r for r in find(all_items)
                        if r.get("status") in {"done", "dropped"}]
            if len(terminal) == 1:
                skipped.append(terminal[0])
                continue
        if len(exact) == 1:
            picked.append(exact[0])
        elif exact:
            errors.append(f"“{title[:60]}” matches more than one item.")
        else:
            errors.append(f"No open item matches “{title[:60]}”.")
    if errors:
        return None, "\n".join(errors[:6])
    if not picked and skipped:
        return [], f"Already handled: {len(skipped)} item(s)."
    seen: set[str] = set()
    unique = []
    for row in picked:
        if row.get("id") in seen:
            continue
        seen.add(row.get("id"))
        unique.append(row)
    return unique, None


_REF_ONLY = re.compile(r"^(?:#\d+|(?:id:)?[0-9a-f]{4,40})$", re.I)


def assign_title(ledger_path: str, what: str) -> str:
    """When assigning by row id, mirror the task title, never the id."""
    text = (what or "").strip()
    if not _REF_ONLY.fullmatch(text):
        return text
    row, _err = _pick(load(ledger_path), text)
    if not row:
        return text
    return row.get("action") or row.get("what") or text


def _shift(text: str, now):
    """Parse '3d', '2w', or a date phrase into an ISO date."""
    from .extract import parse_due

    m = re.fullmatch(r"\s*(\d+)\s*([dw])\s*", text or "", re.I)
    if m:
        days = int(m.group(1)) * (7 if m.group(2).lower() == "w" else 1)
        return (now + timedelta(days=days)).date().isoformat()
    return parse_due(text, now)[0]


UNDO_DEPTH = 10


def _undo_path(ledger_path: str) -> Path:
    return Path(ledger_path).with_name(Path(ledger_path).stem + "_undo.json")


def _push_undo(ledger_path: str, before: str) -> None:
    path = _undo_path(ledger_path)
    data = json.loads(path.read_text()) if path.exists() else {}
    stack = data.get("snapshots") or []
    stack.append(before or "[]")
    path.write_text(json.dumps({"snapshots": stack[-UNDO_DEPTH:]}))


def apply_command(action: str, body: str, now, clients: dict, ledger_path: str,
                  users: dict[str, str] | None = None) -> str:
    """Run a command, and snapshot the ledger before any mutation so `undo:`
    can reverse it."""
    path = Path(ledger_path)
    before = path.read_text() if path.exists() else ""
    reply = _apply_command(action, body, now, clients, ledger_path, users)
    if action in MUTATING:
        after = path.read_text() if path.exists() else ""
        if after and after != before:
            _push_undo(ledger_path, before)
    return reply


def setup_message(name: str, link: str) -> str:
    return (
        f"*Mini-Reid is enabled for you, {name}.*\n"
        "*Setup steps:*\n"
        f"1. Open {link}\n"
        "2. Click *Connect Gmail + Calendar* and approve Google.\n"
        "3. Return here. Mini-reid finishes setup automatically.\n"
        "Jira is already connected from the workspace roster.\n\n"
        "*Then:*\n"
        "• `clients` — check the clients your email is filtered to\n"
        "• `clients: Name, Name` — change them\n"
        "• `help` — all commands\n"
        "• `add: …` — add a task"
    )


def jira_identity(env: dict, profiles: dict[str, dict], user: str,
                  name: str) -> None:
    """Link a member to their Jira account using the shared workspace token."""
    try:
        from .directory import lookup

        known = lookup(user)
        email = known.get("email") or profiles[user].get("email")
        if known:
            profiles[user]["email"] = email or profiles[user].get("email")
        if email:
            from .accounts import clients_for

            owned = clients_for(email)
            if owned:
                profiles[user]["clients"] = owned
        if known.get("jira_account_id"):
            profiles[user]["jira_account_id"] = known["jira_account_id"]
            profiles[user]["jira_name"] = known.get("jira_name") or name
            return
        from .sources import jira_user

        found = jira_user(env, known.get("email") or name)
        if found:
            profiles[user]["jira_account_id"] = found["accountId"]
            profiles[user]["jira_name"] = found.get("displayName") or name
    except Exception as ex:  # noqa: BLE001 - Jira is optional during allow
        print(f"  jira identity failed: {type(ex).__name__}: {ex}", flush=True)


def cross_assign(env: dict, profiles: dict[str, dict], sender: str,
                 sender_name: str, target: str, what: str,
                 owner_ledger: str) -> str:
    """Mirror an assignment into the assignee's ledger and DM them."""
    from .notify import send_dm_to

    target_ledger = (owner_ledger if target == env.get("SLACK_OWNER_ID")
                     else (profiles.get(target) or {}).get("ledger"))
    if target_ledger:
        Path(target_ledger).parent.mkdir(parents=True, exist_ok=True)
        row = {
            "id": commitment_id("manual", f"assign-from:{sender}:{what}".lower(),
                                what),
            "direction": "owed_by_me", "what": what[:200],
            "asker": sender_name[:40], "via": "assigned", "source": "manual",
            "native_id": f"assign-from:{sender}:{what}".lower(), "kind": "manual",
            "source_link": "", "evidence": what[:200], "due": None,
            "due_confidence": 0.0, "cycle": None, "status": "open",
            "stalled_since": None, "ack_policy": "bot_may_ack", "closure": "open",
            "client": None, "assigned_by": sender,
            "created_at": datetime.now(MYT).isoformat(),
            "last_activity": datetime.now(MYT).isoformat(),
            "closed_at": None, "closed_how": None,
        }
        save(target_ledger, merge(load(target_ledger), [row]))
    try:
        send_dm_to(env, target, f"*Assigned by {sender_name}*\n{what[:500]}")
    except Exception as ex:  # noqa: BLE001 - the ledger row is the durable part
        print(f"  assign dm failed: {type(ex).__name__}: {ex}", flush=True)
    return target


def _apply_command(action: str, body: str, now, clients: dict, ledger_path: str,
                   users: dict[str, str] | None = None) -> str:
    """Mutate the ledger and return the reply text. Pure enough to test."""
    rows = load(ledger_path)

    if action == "undo":
        path = _undo_path(ledger_path)
        stack = (json.loads(path.read_text()).get("snapshots") or []) if path.exists() else []
        if not stack:
            return "Nothing to undo."
        Path(ledger_path).write_text(stack.pop())
        path.write_text(json.dumps({"snapshots": stack}))
        return "Undone the last ledger change."

    if action == "add":
        row = parse_capture(f"add: {body}", now, clients)
        if row is None:
            return "Could not read that. Use: add: <what> by <when>"
        existing = next((r for r in rows if r["id"] == row["id"]), None)
        if existing and existing.get("status") in {"done", "dropped"}:
            # Adding the same wording again is an explicit "bring it back".
            # `merge` never reopens terminal rows, so do it here.
            existing.update(row)
            existing["status"] = "open"
            existing["closed_at"] = None
            existing["closed_how"] = None
            existing["closure"] = "open"
            existing["last_activity"] = now.isoformat()
            existing.pop("merged_into", None)
            for other in rows:
                if other is not existing and other.get("merged_from"):
                    other["merged_from"] = [
                        m for m in other["merged_from"] if m.get("id") != existing["id"]]
            save(ledger_path, rows)
            return f"Reopened. {existing['what']}"
        save(ledger_path, merge(rows, [row]))
        due = f" · due {row['due']}" if row["due"] else ""
        client = f"{row['client']} · " if row["client"] else ""
        return f"Added. {client}{row['what']}{due}"

    if action == "assign":
        from .extract import parse_due

        m = (re.match(r"^<@([A-Z0-9]+)(?:\|[^>]*)?>\s*:?\s*(?:to\s+)?(.+)$",
                      body or "")
             or re.match(r"^@([^\s]+)\s+(.+)$", body or "")
             or re.match(r"^(.+?)\s+to\s+(.+)$", body or ""))
        if not m:
            return "Use: assign: @Kasib send the deck by Friday"
        person = _person_name(m.group(1), users)
        what = m.group(2).strip()
        # `assign: @X 1290b3` on an existing row is a reassignment, not a new
        # task titled with the id. Never create an id-titled row.
        if re.fullmatch(r"(?:#\d+|(?:id:)?[0-9a-f]{4,40})", what, re.I):
            row, _err = _pick(rows, what)
            if not row:
                return (f"No open item matches {what}. "
                        f"For a new task use: assign: @{person} <task>")
            row["direction"] = "owed_to_me"
            row["assigned_to"] = person[:40]
            row["asker"] = person[:40]
            row["via"] = "reassigned"
            row["last_activity"] = now.isoformat()
            save(ledger_path, rows)
            return f"Assigned to {person}: {row['what'][:80]}"
        due, confidence = parse_due(what, now)
        row = {
            "id": commitment_id("manual", f"assign:{body}".lower(), what),
            "direction": "owed_to_me", "what": what[:200], "asker": person[:40],
            "via": "assigned", "source": "manual", "native_id": body.lower(),
            "kind": "manual", "source_link": "", "evidence": body[:200],
            "due": due, "due_confidence": confidence, "cycle": None,
            "status": "open", "stalled_since": None, "ack_policy": "bot_may_ack",
            "closure": "open", "client": None, "assigned_to": person[:40],
            "created_at": now.isoformat(), "last_activity": now.isoformat(),
            "closed_at": None, "closed_how": None,
        }
        save(ledger_path, merge(rows, [row]))
        return f"Assigned to {person}: {what[:80]}" + (f" · due {due}" if due else "")

    if action == "note":
        row = {
            "id": commitment_id("manual", body.lower(), body),
            "direction": "owed_by_me", "what": body[:200], "source": "manual",
            "native_id": body.lower(), "kind": "note", "source_link": "",
            "evidence": body[:200], "due": None, "due_confidence": 0.0,
            "cycle": None, "status": "open", "stalled_since": None,
            "ack_policy": "bot_may_ack", "closure": "open", "client": None,
            "created_at": now.isoformat(), "last_activity": now.isoformat(),
            "closed_at": None, "closed_how": None,
        }
        save(ledger_path, merge(rows, [row]))
        return "Noted."

    if action == "reassign":
        m = re.match(r"^(.*?)\s+to\s+(.+)$", body or "", re.I)
        if not m:
            return "Use: reassign: <item> to <person>"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        person = _person_name(m.group(2), users)
        row["direction"] = "owed_to_me"
        row["assigned_to"] = person[:40]
        row["asker"] = person[:40]
        row["via"] = "reassigned"
        row["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return f"Reassigned to {person}: {row['what'][:80]}"

    if action in {"convert", "tonote"}:
        row, err = _pick(rows, body)
        if err:
            return err
        row["kind"] = "note"
        row["due"] = None
        row["status"] = "open"
        row["last_activity"] = now.isoformat()
        for key in ("priority", "stalled_since", "stalled_reason"):
            row.pop(key, None)
        save(ledger_path, rows)
        return f"Converted to note: {row['what'][:80]}"

    if action in {"priority", "prio"}:
        m = re.match(r"^(.*?)\s+(?:to\s+)?(p?[1-5]|high|medium|med|low|none|clear)$",
                     body or "", re.I)
        if not m:
            return "Use: priority: <item> 1-5 | high | medium | low | none"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        word = m.group(2).lower().lstrip("p")
        value = {"high": 1, "medium": 3, "med": 3, "low": 5,
                 "none": None, "clear": None}.get(word, None)
        if value is None and word not in {"none", "clear"}:
            value = int(word)
        if value is None:
            row.pop("priority", None)
        else:
            row["priority"] = value
        row["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        if value is None:
            return f"Priority cleared: {row['what'][:80]}"
        return f"P{value}: {row['what'][:80]}"

    if action == "combine":
        m = re.match(r"^(.*?)\s+(?:into|with|\+)\s+(.*)$", body or "", re.I)
        if not m:
            return "Use: combine: <duplicate> into <keep>   e.g. combine: #9 into #7"
        duplicate, err = _pick(rows, m.group(1))
        if err:
            return err
        keep, err = _pick(rows, m.group(2))
        if err:
            return err
        if duplicate["id"] == keep["id"]:
            return "Those are the same item."
        duplicate["status"] = "dropped"
        duplicate["closed_at"] = now.isoformat()
        duplicate["closed_how"] = "merged"
        duplicate["merged_into"] = keep["id"]
        keep.setdefault("merged_from", []).append({
            "id": duplicate["id"], "what": duplicate.get("what"),
            "source_link": duplicate.get("source_link")})
        keep["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return (f"Combined: {duplicate['what'][:70]} → {keep['what'][:70]}\n"
                f"Kept #{_open_sorted(rows).index(keep) + 1}: {keep['what'][:80]}")

    if action == "uncombine":
        keep, err = _pick(rows, body)
        if err:
            return err
        merged = keep.pop("merged_from", [])
        if not merged:
            return "Nothing is merged into that item."
        by_id = {r["id"]: r for r in rows}
        restored = []
        for entry in merged:
            row = by_id.get(entry.get("id"))
            if not row:
                continue
            row["status"] = "open"
            row["last_activity"] = now.isoformat()
            for key in ("closed_at", "closed_how", "merged_into"):
                row.pop(key, None)
            restored.append(row["what"][:70])
        save(ledger_path, rows)
        return (f"Restored {len(restored)} item(s):\n"
                + "\n".join(f"• {w}" for w in restored))

    if action == "status":
        m = re.match(
            r"^(.*?)\s+(?:to\s+)?(in[ -]?progress|inprogress|doing|active|"
            r"blocked|block|stuck|open|todo|pending)\s*$", body, re.I)
        if not m:
            return "Use: status: <item> in progress | blocked | open"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        status = STATUS_ALIASES[m.group(2).lower().replace("  ", " ")]
        row["status"] = status
        row["status_updated_at"] = now.isoformat()
        row["last_activity"] = now.isoformat()
        if status == "open":
            row.pop("stalled_since", None)
            row.pop("stalled_reason", None)
        save(ledger_path, rows)
        return f"Status: {row['what'][:80]} — {status}"

    if action == "done":
        many, bulk_err = _pick_many(rows, body)
        if bulk_err:
            return bulk_err
        if not many:
            many, bulk_err = _pick_titles(rows, body)
            if bulk_err:
                return bulk_err
        if many:
            for row in many:
                row["status"] = "done"
                row["closed_at"] = now.isoformat()
                row["closed_how"] = "manual"
                row["last_activity"] = now.isoformat()
            save(ledger_path, rows)
            names = ", ".join((r.get("action") or r.get("what") or "")[:40]
                              for r in many[:5])
            return f"Closed {len(many)}: {names}"
        best, err = _pick(rows, body)
        if err:
            return err
        best["status"] = "done"
        best["closed_at"] = now.isoformat()
        best["closed_how"] = "manual"
        best["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return f"Closed: {best['what'][:80]}"

    if action == "help":
        return HELP

    if action == "remind":
        fields, clean = parse_remind(body, now)
        if fields is None:
            return "Use: remind: send the deck tomorrow at 3pm"
        row = {
            "id": commitment_id("reminder", clean.lower(), clean),
            "direction": "owed_by_me", "what": clean[:200], "source": "manual",
            "native_id": clean.lower(), "kind": "reminder", "source_link": "",
            "evidence": body[:200], "due": fields["due"], "due_confidence": 0.9,
            "cycle": None, "status": "open", "stalled_since": None,
            "ack_policy": "bot_may_ack", "closure": "open", "client": None,
            "created_at": now.isoformat(), "last_activity": now.isoformat(),
            "remind_at": fields["remind_at"], "reminded": False,
            "closed_at": None, "closed_how": None,
        }
        save(ledger_path, merge(rows, [row]))
        return f"Reminder set for {fields['remind_at'][:16].replace('T', ' ')}: {clean[:80]}"

    if action == "not":
        from . import learning
        from .calendar import ignore_title

        many, bulk_err = _pick_many(rows, body)
        if bulk_err:
            return bulk_err
        if not many:
            many, bulk_err = _pick_titles(rows, body, include_notes=True)
            if bulk_err:
                return bulk_err
        if many:
            for row in many:
                row["status"] = "dropped"
                row["closed_at"] = now.isoformat()
                row["closed_how"] = "not_commitment"
                row["last_activity"] = now.isoformat()
                learning.add(row.get("what", ""), reason="bulk not",
                             source=row.get("source", ""))
            save(ledger_path, rows)
            names = ", ".join((r.get("action") or r.get("what") or "")[:40]
                              for r in many[:5])
            return f"Removed {len(many)}: {names}"

        # `not:` also dismisses a meeting reminder. No ledger row exists for a
        # meeting, so match the title recorded in today's reminder state.
        state_path = Path(ledger_path).parent / "meeting_reminders.json"
        if state_path.exists():
            meetings = json.loads(state_path.read_text())
            target = (body or "").strip().lower()
            for rec in (meetings.get("meetings") or {}).values():
                title = (rec.get("title") or "").strip()
                if target and (target in title.lower() or title.lower() in target):
                    ignore_title(title, str(Path(ledger_path).parent
                                            / "calendar_ignores.json"))
                    rec["status"] = "ignored"
                    state_path.write_text(json.dumps(meetings))
                    return f"Ignored meeting: {title[:80]}"

        row, err = _pick(rows, body)
        if row:
            row["status"] = "dropped"
            row["closed_at"] = now.isoformat()
            row["closed_how"] = "not_commitment"
            row["last_activity"] = now.isoformat()
            save(ledger_path, rows)
            learning.add(row.get("what", ""), reason=body,
                         source=row.get("source", ""))
            return f"Removed as not a commitment: {row['what'][:80]}"
        if err and (err.startswith("Which one?")
                    or "reads like a question" in err):
            return err
        learning.add(body, reason="manual correction", source="manual")
        return "Recorded. I will ignore similar messages from now on."

    if action == "notes":
        notes = [r for r in rows if r.get("kind") == "note"
                 and r.get("status") not in {"done", "dropped"}]
        if not notes:
            return "No notes."
        notes.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return "Notes:\n" + "\n".join(
            f"• [{r['id'][:6]}] {r.get('what', '')[:140]}" for r in notes[:25])

    if action == "list":
        from .listview import format_list

        return format_list(rows, now)

    if action == "find":
        hits = [r for r in rows
                if body.lower() in f"{r.get('what','')} {r.get('client','')}".lower()]
        if not hits:
            return f"No matches for “{body}”."
        return "\n".join(
            f"• {r['what'][:100]}" + (f" — {r['due']}" if r.get("due") else "")
            for r in hits[:8])

    if action in {"due", "snooze"}:
        m = re.match(
            r"^(.*?)\s+(?:by\s+)?(\d+\s*[dw]|today|tomorrow|monday|tuesday|wednesday|"
            r"thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})\s*$", body, re.I)
        if not m:
            return "Use: due: <item> by Friday   or   snooze: <item> 3d"
        row, err = _pick(rows, m.group(1))
        if err:
            return err
        d = _shift(m.group(2), now)
        if not d:
            return "Could not read that date."
        row["due"] = d
        row["status"] = "open"
        row["closure"] = "open"
        row["last_activity"] = now.isoformat()
        save(ledger_path, rows)
        return f"Due {d}: {row['what'][:80]}"

    if action == "edit":
        from .extract import parse_due

        m = re.match(r"^(.*)\s+to\s+(.+)$", body or "", re.I)
        if not m:
            return "Use: edit: <item> to <new name> [by <when>]"
        target, new = m.group(1).strip(), m.group(2).strip()
        row, err = _pick(rows, target)
        if err:
            return err
        due = None
        b = re.match(r"^(.*?)\s+by\s+(.+)$", new, re.I)
        if b:
            d = parse_due(b.group(2), now)[0]
            if d:
                due = d
                new = b.group(1).strip()
        if not new:
            return "Use: edit: <item> to <new name> [by <when>]"
        row["what"] = new[:200]
        row["last_activity"] = now.isoformat()
        if due:
            row["due"] = due
            row["status"] = "open"
            row["closure"] = "open"
        save(ledger_path, rows)
        return f"Edited: {new[:80]}" + (f" · due {due}" if due else "")

    if action == "drop":
        row, err = _pick(rows, body)
        if err:
            return err
        row["status"] = "dropped"
        row["closed_at"] = now.isoformat()
        row["closed_how"] = "manual"
        save(ledger_path, rows)
        return f"Dropped: {row['what'][:80]}"

    if action == "waiting":
        m = re.match(r"^(.*?)\s+on\s+(.+)$", body, re.I)
        target, person = (m.group(1), m.group(2)) if m else (body, "")
        row, err = _pick(rows, target)
        if err:
            return err
        row["direction"] = "owed_to_me"
        if person:
            row["asker"] = person.strip()[:40]
        save(ledger_path, rows)
        return f"Waiting on {person or 'them'}: {row['what'][:70]}"

    return ("Commands: add:, note:, done:, drop:, due: <item> by <when>, "
            "snooze: <item> 3d, waiting: <item> on <person>, find: <text>, list")


def main(env: dict, ledger_path: str = "ledger.json") -> int:
    from datetime import datetime, timedelta, timezone

    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web import WebClient

    from .clients import load_clients
    from .notify import send_dm, send_dm_to
    from .setup_server import (complete_google_url, link_for, poll_relay,
                               start as start_setup)
    from .sources import slack_user_name

    MYT = timezone(timedelta(hours=8))
    clients = load_clients("clients.json")
    owner = env.get("SLACK_OWNER_ID", "")
    web = WebClient(token=env["SLACK_BOT_TOKEN"])
    client = SocketModeClient(app_token=env["SLACK_APP_TOKEN"], web_client=web)
    try:
        users = load_users(env["SLACK_BOT_TOKEN"])
    except Exception as ex:  # noqa: BLE001 - names degrade to mentions only
        print(f"user list unavailable: {type(ex).__name__}", flush=True)
        users = {}
    try:
        start_setup(env)
    except Exception as ex:  # noqa: BLE001 - setup page must not block commands
        print(f"setup server failed: {type(ex).__name__}: {ex}", flush=True)

    def _relay_loop() -> None:
        import time

        while True:
            try:
                poll_relay(env)
            except Exception as ex:  # noqa: BLE001 - polling must never stop
                print(f"relay poller: {type(ex).__name__}: {ex}", flush=True)
            time.sleep(5)

    if env.get("RELAY_URL"):
        threading.Thread(target=_relay_loop, daemon=True).start()

    def post_reply(channel: str, text: str, notify: bool = True,
                   private: bool = False, dm_to: str | None = None,
                   blocks: list[dict] | None = None,
                   thread_ts: str | None = None) -> None:
        """Post in place; DM a copy when the command came from a channel.
        `private` sends only to Ridha's DM; `dm_to` sends only to that user.
        Channel replies stay in the triggering thread."""
        if dm_to and not channel.startswith("D"):
            try:
                return send_dm_to(env, dm_to, text, blocks=blocks)
            except Exception as ex:  # noqa: BLE001
                print(f"  dm reply failed: {type(ex).__name__}", flush=True)
            return None
        if private and not channel.startswith("D"):
            try:
                return send_dm(env, text, blocks=blocks)
            except Exception as ex:  # noqa: BLE001
                print(f"  dm reply failed: {type(ex).__name__}", flush=True)
            return None
        data = {"channel": channel, "text": text}
        if blocks:
            data["blocks"] = blocks
        if thread_ts and not channel.startswith("D"):
            data["thread_ts"] = thread_ts
        sent = web.chat_postMessage(**data)
        if not notify or channel.startswith("D"):
            return sent
        try:
            send_dm(env, text)
        except Exception as ex:  # noqa: BLE001 - the channel reply already went out
            print(f"  dm mirror failed: {type(ex).__name__}", flush=True)
        return sent

    seen: set[tuple[str, str]] = set()
    STATE = "bot_state.json"

    def _state() -> dict:
        import json
        from pathlib import Path as P

        f = P(STATE)
        return json.loads(f.read_text()) if f.exists() else {}

    def _mark(ts: str) -> None:
        import json
        from pathlib import Path as P

        with _STATE_LOCK:
            s = _state()
            try:
                if not s.get("last_ts") or float(ts) > float(s["last_ts"]):
                    s["last_ts"] = ts
                    P(STATE).write_text(json.dumps(s))
            except ValueError:
                pass

    def process(channel: str, user: str, text: str, ts: str,
                late: bool = False, thread_ts: str | None = None) -> None:
        if (channel, ts) in seen or channel in IGNORE_CHANNEL_IDS:
            return
        thread_ts = (thread_ts or ts) if not channel.startswith("D") else None
        if not claim_message(STATE, channel, ts):
            return
        seen.add((channel, ts))

        slur = SLUR.search(text or "")
        abuse = ABUSE.search(text or "")
        if slur or abuse:
            try:
                web.reactions_add(channel=channel, timestamp=ts,
                                  name="triangular_flag_on_post")
            except Exception as ex:  # noqa: BLE001 - reaction is best effort
                print(f"  flag react failed: {type(ex).__name__}", flush=True)
            try:
                send_dm_to(env, user, SLUR_DM if slur else ABUSE_DM)
            except Exception as ex:  # noqa: BLE001 - never retry blindly
                print(f"  flag dm failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        profiles = load_profiles()
        member = user != owner and user in profiles
        user_ledger = ledger_for(profiles, user, ledger_path) if member else ledger_path

        if is_link_only(text):
            _mark(ts)
            return

        def say(text: str, notify: bool | None = None,
                blocks: list[dict] | None = None):
            """Reply to the command sender, privately for owner and members."""
            notify = (user == owner) if notify is None else notify
            if user == owner:
                return post_reply(channel, text, notify=notify, private=True,
                                  blocks=blocks, thread_ts=thread_ts)
            if member:
                return post_reply(channel, text, dm_to=user, blocks=blocks,
                                  thread_ts=thread_ts)
            return post_reply(channel, text, notify=notify, blocks=blocks,
                              thread_ts=thread_ts)

        key = f"{channel}:{user}"
        state_now = _state()
        pending = (state_now.get("pending_remind") or {}).get(key)
        if (pending and not late
                and not re.match(r"^(?:please\s+)?remind\b", text.strip(), re.I)):
            state_now["pending_remind"].pop(key, None)
            Path(STATE).write_text(json.dumps(state_now))
            try:
                fresh = (datetime.now(MYT)
                         - datetime.fromisoformat(pending["asked_at"])).total_seconds() < 900
            except (KeyError, ValueError):
                fresh = False
            choice = clarify_choice(text) if fresh else None
            if choice:
                say(deliver_pending_reminder(env, pending, choice, text))
                _mark(ts)
                return

        if user == owner:
            control = banter_command(text, channel, users, datetime.now(MYT), env)
            if control:
                _, reply = control
                web.chat_postMessage(channel=channel, text=reply,
                                     thread_ts=thread_ts)
                _mark(ts)
                return

        raw_action, _ = parse_command(text, bot_user_id)
        nice = nice_reply(text) if raw_action in {"unknown", "ack"} else None
        if nice:
            try:
                web.chat_postMessage(channel=channel, text=nice,
                                     thread_ts=thread_ts)
            except Exception as ex:  # noqa: BLE001 - best effort
                print(f"  nice reply failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return
        chatter = chatter_reply(text) if raw_action in {"unknown", "ack"} else None
        if chatter:
            try:
                web.chat_postMessage(channel=channel, text=chatter,
                                     thread_ts=thread_ts)
            except Exception as ex:  # noqa: BLE001 - best effort
                print(f"  default reply failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        if banter_active(channel, user) and is_mean(text):
            try:
                web.chat_postMessage(channel=channel,
                                     text=banter_line(channel, text),
                                     thread_ts=thread_ts)
            except Exception as ex:  # noqa: BLE001 - banter is best effort
                print(f"  banter post failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        guard = guardrail_reply(text)
        if guard:
            try:
                web.chat_postMessage(channel=channel, text=guard,
                                     thread_ts=thread_ts)
            except Exception as ex:  # noqa: BLE001 - guardrail is best effort
                print(f"  guardrail post failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        play = play_reply(text, users)
        if play:
            try:
                web.chat_postMessage(channel=channel, text=play,
                                     thread_ts=thread_ts)
            except Exception as ex:  # noqa: BLE001 - fun is best effort
                print(f"  play post failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        if raw_action == "unknown" and user != owner and not member:
            from .classifier import task_score

            if task_score(text) < 0.3:
                try:
                    web.chat_postMessage(channel=channel, text=DEFAULT_REPLY,
                                         thread_ts=thread_ts)
                except Exception as ex:  # noqa: BLE001 - best effort
                    print(f"  classifier reply failed: {type(ex).__name__}", flush=True)
                _mark(ts)
                return

        action, body = parse_command(text, bot_user_id)
        allow = {u.strip() for u in env.get("KB_ALLOWLIST", "").split(",") if u.strip()}
        if user == owner:
            action = owner_action(action, body)
        elif action == "unknown" and QUERY.search(body) and user in allow:
            action = "ask"  # allowlisted people can ask in plain language too

        # Catch-up replays missed commands too, not only questions. Each
        # message is claimed once in bot_state.json, so a replay cannot repeat.

        if member_quick_add(channel, action, member, text):
            reply = _apply_command("add", text.strip(), datetime.now(MYT),
                                   clients, user_ledger, users)
            say(reply)
            _mark(ts)
            return

        if action == "meet":
            if user != owner:
                say("Only Ridha can schedule meetings.")
                _mark(ts)
                return
            targets, topic = parse_meeting(body, users, user)
            if not targets:
                say("Use: meet: @Kasib and @Charanya about BD Command Centre")
                _mark(ts)
                return
            from .directory import lookup as directory_lookup
            from .meeting_ui import slot_blocks
            from .meetings import propose_slots

            attendees: list[dict] = []
            missing: list[str] = []
            for target in targets:
                name = _person_name(target, users)
                email = (directory_lookup(target).get("email") or "").lower()
                if email:
                    attendees.append({"name": name, "email": email})
                else:
                    missing.append(name)
            if missing:
                say("I don't have a work email for " + ", ".join(missing) + ".")
                _mark(ts)
                return
            emails = [a["email"] for a in attendees]
            names = ", ".join(a["name"] for a in attendees)
            from .meetings import (SLOT_MINUTES, parse_duration,
                                   strip_duration)

            duration = parse_duration(body) or SLOT_MINUTES
            topic = strip_duration(topic) or topic
            busy: dict = {}
            try:
                slots = propose_slots(env, emails, busy_out=busy,
                                      duration=duration)
            except Exception as ex:  # noqa: BLE001 - tell the owner why
                say(f"Could not read calendars: {type(ex).__name__}: {ex}")
                _mark(ts)
                return
            if not slots:
                say(f"No common free slot with {names} in the next 5 working days.")
                _mark(ts)
                return
            from secrets import token_hex

            token = token_hex(6)
            state_now = _state()
            pending = state_now.setdefault("pending_meet", {})
            pending[token] = {"topic": topic, "emails": emails,
                              "attendees": attendees, "attendee": names,
                              "slots": slots, "user": user, "channel": channel,
                              "duration": duration}
            if len(pending) > 50:
                state_now["pending_meet"] = dict(list(pending.items())[-50:])
            Path(STATE).write_text(json.dumps(state_now))
            sent = say(f"Free slots with {names}:",
                       blocks=slot_blocks(token, topic, attendees, slots,
                                          busy, duration=duration))
            if sent:
                pending[token]["channel"] = sent.get("channel") or channel
                pending[token]["message_ts"] = sent.get("ts") or ""
                Path(STATE).write_text(json.dumps(state_now))
            _mark(ts)
            return

        if action == "setup":
            if user == owner:
                say("Use `allow: Name` to set someone else up.")
            elif not member:
                say("Ask Ridha to allow you first.")
            elif profiles[user].get("setup_done_at"):
                say("Your setup is complete. Use `help` for commands.")
            elif (body or "").startswith(("http://", "https://")):
                try:
                    say(complete_google_url(env, user, body))
                except Exception as ex:  # noqa: BLE001 - tell the member why
                    say(f"Could not connect Gmail: {ex}")
            else:
                say("*Your setup link* (expires in 24 hours):\n"
                    + link_for(env, profiles, user))
            _mark(ts)
            return

        if action == "clients":
            if not member:
                say("Ask Ridha to allow you first.")
                _mark(ts)
                return
            from .clients import load_clients, resolve_clients
            from .profiles import save as save_profiles

            registry = load_clients("clients.json")
            if not (body or "").strip():
                current = profiles[user].get("clients") or []
                say("Your email filter: "
                    + (", ".join(registry[s]["name"] for s in current
                                 if s in registry) or "none set")
                    + "\nChange it with `clients: Name, Name`.")
                _mark(ts)
                return
            slugs, unknown = resolve_clients(body, registry)
            if unknown:
                say("I don't know: " + ", ".join(unknown)
                    + ". Use client names, e.g. `clients: Eupe, Gamuda`.")
                _mark(ts)
                return
            profiles[user]["clients"] = slugs
            save_profiles(profiles)
            say("Email filter set: "
                + ", ".join(registry[s]["name"] for s in slugs))
            _mark(ts)
            return

        if action == "reminders":
            if user != owner:
                say("Only Ridha can see the reminder log.")
                _mark(ts)
                return
            from .notify import REMINDER_LOG, dm_reply_count, scheduled_ids

            path = Path(REMINDER_LOG)
            try:
                rows = json.loads(path.read_text()) if path.exists() else []
            except (OSError, ValueError):
                rows = []
            recent = rows[-10:]
            pending = scheduled_ids(env)
            replies: dict[int, int] = {}
            for i, r in enumerate(reversed(recent)):
                sid = r.get("scheduled_id")
                if not sid or sid in pending or not r.get("post_at"):
                    continue
                try:
                    since = datetime.fromisoformat(r["post_at"]).timestamp()
                except ValueError:
                    continue
                replies[i] = dm_reply_count(env, r.get("to") or "", since)
            say(format_reminders(rows, pending, replies))
            _mark(ts)
            return

        if action == "ask":
            allow = {u.strip() for u in env.get("KB_ALLOWLIST", "").split(",") if u.strip()}
            if user != owner and user not in allow:
                say("You are not on the list for that. Ask Ridha to add you.")
                return
            reply = ""
            try:
                from .ask_ledger import answer_ledger

                reply = answer_ledger(body, load(user_ledger), clients) or ""
            except Exception as ex:  # noqa: BLE001 - fall through to search/KB
                print(f"  ledger ask failed: {type(ex).__name__}: {ex}",
                      flush=True)
            if not reply and user == owner:
                try:
                    from .files import search as file_search

                    file_hits = file_search(body)
                    if file_hits:
                        reply = "*From files*\n" + "\n".join(
                            f"• *{h['name']}*: {h['text'][:300]}" +
                            (f" — <{h['permalink']}|open>"
                             if h.get("permalink") else "")
                            for h in file_hits)
                except Exception as ex:  # noqa: BLE001 - files are optional
                    print(f"  file ask failed: {type(ex).__name__}: {ex}",
                          flush=True)
            if not reply and user == owner:
                try:
                    from .slack_search import format_hits, search as slack_search

                    hits = slack_search(env, body)
                    if hits:
                        reply = "*From Slack*\n" + format_hits(hits)
                except Exception as ex:  # noqa: BLE001 - fall back to the KB
                    print(f"  live slack search failed: "
                          f"{type(ex).__name__}: {ex}", flush=True)
            if not reply:
                try:
                    from .kb import answer as kb_answer
                    from .kb import load as kb_load

                    index = kb_load()
                    if not index:
                        reply = "Knowledge base is empty. Ridha needs to run the index build."
                    else:
                        body_text, hits = kb_answer(body, index)
                        sources = "\n".join(
                            f"[{i}] {h['source']} · {h['link']}"
                            for i, h in enumerate(hits, 1) if h.get("link"))
                        reply = f"{body_text}\n\n{sources}"
                except Exception as ex:  # noqa: BLE001
                    reply = f"Could not answer: {type(ex).__name__}"
            if late:
                reply = "_(answered late, I was offline)_\n" + reply
            say(reply[:3900])
            _mark(ts)
            return

        print(f"[{datetime.now(MYT):%H:%M:%S}] {user} in {channel}: {text[:120]!r} -> {action}",
              flush=True)

        target, rest = (split_target(body, users, user,
                                     bare_name=(action == "remind"))
                        if action in {"add", "remind", "allow"} else (None, body))
        multi_remind = (parse_multi_remind(body, users, datetime.now(MYT))
                        if action == "remind" else None)
        if action == "allow":
            if user != owner:
                say("Only Ridha can allow people.")
                _mark(ts)
                return
            # `allow: Charanya` works without the @ or a Slack mention.
            target = target or users.get((body or "").strip().lstrip("@").lower())
            if not target or target == owner:
                missing = unresolved_recipient(body, users)
                say(f"I can't find {missing} in this Slack workspace."
                    if missing else "Use: allow: @Charanya")
                _mark(ts)
                return
            if target in profiles:
                name = profiles[target].get("name") or target
                if profiles[target].get("setup_done_at"):
                    say(f"{name} is already allowed and set up.")
                    _mark(ts)
                    return
                jira_identity(env, profiles, target, name)
                link = link_for(env, profiles, target)
                try:
                    send_dm_to(env, target, setup_message(name, link))
                except Exception as ex:  # noqa: BLE001
                    say(f"Could not DM {name} ({type(ex).__name__}). Link: {link}")
                    _mark(ts)
                    return
                say(f"Setup link resent to {name}.")
                _mark(ts)
                return
            name = slack_user_name(env["SLACK_BOT_TOKEN"], target)
            add_member(profiles, target, name)
            jira_identity(env, profiles, target, name)
            link = link_for(env, profiles, target)
            try:
                send_dm_to(env, target, setup_message(name, link))
            except Exception as ex:  # noqa: BLE001 - still tell the owner
                say(f"Allowed {name}, but could not DM them "
                    f"({type(ex).__name__}). Link: {link}")
                _mark(ts)
                return
            say(f"Allowed {name}. Setup link sent to their DM.")
            _mark(ts)
            return
        if action == "remind" and multi_remind:
            now = datetime.now(MYT)
            set_for, failed = [], []
            for recipient, fields in multi_remind:
                at = datetime.fromisoformat(fields["remind_at"])
                name = _person_name(recipient, users)
                if at <= now:
                    failed.append(f"{name} (time in the past)")
                    continue
                recipient_ledger = (
                    ledger_path if recipient == owner
                    else (profiles.get(recipient) or {}).get("ledger"))
                if recipient_ledger:
                    add_reminder_row(recipient_ledger, fields["what"], fields,
                                     now)
                try:
                    from .notify import REMINDER_LOG, log_reminder, schedule_dm

                    sid = schedule_dm(env, recipient,
                                      f"*Reminder*\n{fields['what'][:300]}",
                                      int(at.timestamp()))
                    log_reminder(
                        REMINDER_LOG, asked_by=user,
                        asked_by_name=_person_name(user, users),
                        to=recipient, to_name=name, what=fields["what"],
                        post_at=at.isoformat(), scheduled_id=sid,
                        channel=channel)
                except Exception as ex:  # noqa: BLE001 - report, keep others
                    print(f"  multi remind failed: {type(ex).__name__}: {ex}",
                          flush=True)
                    failed.append(f"{name} ({type(ex).__name__})")
                    continue
                set_for.append(f"{name} {at:%H:%M}")
            if set_for:
                say(f"Reminders set for {len(set_for)}: " + ", ".join(set_for))
            if failed:
                say("Could not set: " + ", ".join(failed))
            react_ack(web, channel, ts, EMOJI_ACKS["remind"])
            _mark(ts)
            return
        if action == "remind" and target is None:
            missing = unresolved_recipient(body, users)
            if missing:
                say(f"I can't find {missing} in this Slack workspace. "
                    "Reminders can only DM Pantas members.")
                _mark(ts)
                return
        if should_schedule_reminder(action, user, owner, target, member):
            fields, _ = parse_remind(rest, datetime.now(MYT))
            if fields is None:
                say("Use: remind <name> to <what> at 2pm "
                    "(or add: <what> at 2pm)")
                _mark(ts)
                return
            recipient = target or user
            who = "you" if recipient == user else f"<@{recipient}>"
            # The reminder belongs on the receiver's list, not only in Slack.
            recipient_ledger = (ledger_path if recipient == owner
                                else (profiles.get(recipient) or {}).get("ledger"))
            if recipient_ledger:
                add_reminder_row(recipient_ledger, fields["what"], fields,
                                 datetime.now(MYT))
            explicit_both = (not fields.get("immediate")
                             and asks_now_and_again(rest))
            if explicit_both:
                at = datetime.fromisoformat(fields["remind_at"])
                try:
                    say(deliver_pending_reminder(env, {
                        "user": user, "channel": channel, "to": recipient,
                        "to_name": _person_name(recipient, users),
                        "asked_by": user,
                        "asked_by_name": _person_name(user, users),
                        "what": fields["what"], "at": at.isoformat()}, "both"))
                except Exception as ex:  # noqa: BLE001 - report, never retry
                    print(f"  reminder send failed: {type(ex).__name__}: {ex}",
                          flush=True)
                    say(f"Could not send that: {type(ex).__name__}")
                    _mark(ts)
                    return
                react_ack(web, channel, ts, EMOJI_ACKS["remind"])
                _mark(ts)
                return
            if (not fields.get("immediate") and needs_reminder_clarification(rest)):
                at = datetime.fromisoformat(fields["remind_at"])
                if at > datetime.now(MYT):
                    state_now = _state()
                    state_now.setdefault("pending_remind", {})[key] = {
                        "user": user, "channel": channel, "to": recipient,
                        "to_name": _person_name(recipient, users),
                        "asked_by": user, "asked_by_name": _person_name(user, users),
                        "what": fields["what"], "at": at.isoformat(),
                        "asked_at": datetime.now(MYT).isoformat(timespec="seconds")}
                    Path(STATE).write_text(json.dumps(state_now))
                    to_name = _person_name(recipient, users)
                    question = (f"Remind {to_name} now, at {at:%a %d %b %H:%M}, "
                                "or both?")
                    blocks = reminder_blocks(key, at, to_name)
                    try:
                        web.chat_postMessage(channel=channel, text=question,
                                             blocks=blocks, thread_ts=thread_ts)
                    except Exception as ex:  # noqa: BLE001 - text reply still works
                        print(f"  reminder buttons failed: {type(ex).__name__}",
                              flush=True)
                        say(question + " Reply `now`, `later`, or `both`.")
                    _mark(ts)
                    return
            if fields.get("immediate"):
                try:
                    send_dm_to(env, recipient, f"*Reminder*\n{fields['what'][:300]}")
                except Exception as ex:  # noqa: BLE001 - report, never retry blindly
                    print(f"  immediate remind failed: {type(ex).__name__}: {ex}", flush=True)
                    say(f"Could not send that: {type(ex).__name__}")
                    _mark(ts)
                    return
                from .notify import REMINDER_LOG, log_reminder

                log_reminder(REMINDER_LOG, asked_by=user,
                             asked_by_name=_person_name(user, users),
                             to=recipient, to_name=_person_name(recipient, users),
                             what=fields["what"], status="sent",
                             post_at=datetime.now(MYT).isoformat(timespec="seconds"),
                             channel=channel)
                if react_ack(web, channel, ts, EMOJI_ACKS["remind"]):
                    _mark(ts)
                    return
                say(f"Reminder sent to {who}: {fields['what'][:80]}")
                _mark(ts)
                return
            at = datetime.fromisoformat(fields["remind_at"])
            if at <= datetime.now(MYT):
                say("That time is in the past.")
                _mark(ts)
                return
            try:
                from .notify import REMINDER_LOG, log_reminder, schedule_dm

                sid = schedule_dm(env, recipient,
                                  f"*Reminder*\n{fields['what'][:300]}",
                                  int(at.timestamp()))
                log_reminder(REMINDER_LOG, asked_by=user,
                             asked_by_name=_person_name(user, users),
                             to=recipient, to_name=_person_name(recipient, users),
                             what=fields["what"], post_at=at.isoformat(),
                             scheduled_id=sid, channel=channel)
            except Exception as ex:  # noqa: BLE001 - report, never retry blindly
                print(f"  schedule failed: {type(ex).__name__}: {ex}", flush=True)
                say(f"Could not schedule that: {type(ex).__name__}")
                _mark(ts)
                return
            if react_ack(web, channel, ts, EMOJI_ACKS["remind"]):
                _mark(ts)
                return
            say(f"Reminder set for {who} — {at:%a %d %b %H:%M}: {fields['what'][:80]}")
            _mark(ts)
            return

        if (user == owner or member) and channel.startswith("D"):
            cancel = re.match(r"^cancel\b(.*)$", (body or "").strip(), re.I)
            if cancel and user == owner:
                from .meetings import cancel_nearest

                done = cancel_nearest(env, datetime.now(MYT),
                                      cancel.group(1).strip(" ,:-"))
                if done:
                    say(done)
                    _mark(ts)
                    return
            resched = re.match(
                r"^(?:reschedule|move|moved)\s+(?:it\s+)?to\s+(.+)$",
                (body or "").strip(), re.I)
            if resched and user == owner:
                fields, _ = parse_remind(resched.group(1), datetime.now(MYT))
                if fields and not fields.get("immediate"):
                    from .meetings import reschedule_nearest

                    moved = reschedule_nearest(
                        env, datetime.fromisoformat(fields["remind_at"]),
                        fields["what"].strip(" ,-"), datetime.now(MYT))
                    if moved:
                        say(moved)
                        _mark(ts)
                        return
            try:
                from .watcher import record_meeting_reply

                state_path = ("meeting_reminders.json" if user == owner
                              else f"data/{user}/meeting_reminders.json")
                Path(state_path).parent.mkdir(parents=True, exist_ok=True)
                meeting_reply = record_meeting_reply(body, datetime.now(MYT),
                                                     state_path)
            except Exception as ex:  # noqa: BLE001 - a bad state file must not block the bot
                print(f"  meeting reply failed: {type(ex).__name__}: {ex}", flush=True)
                meeting_reply = None
            if meeting_reply:
                say(meeting_reply)
                _mark(ts)
                return

        if user != owner and not member and action != "remind":
            if not late:
                try:
                    web.reactions_add(channel=channel, timestamp=ts, name="white_check_mark")
                except Exception as ex:  # noqa: BLE001
                    print(f"  react failed: {type(ex).__name__}: {ex}", flush=True)
            if action == "help":
                web.chat_postMessage(channel=channel, text=HELP,
                                     thread_ts=thread_ts)
                _mark(ts)
                return
            note = other_note(action, body, user)
            if note:
                apply_command("note", note, datetime.now(MYT), clients, ledger_path)
                try:
                    from .notify import send_dm

                    send_dm(env, f"*Note from <@{user}>*\n{(body or '').strip()[:500]}")
                except Exception as ex:  # noqa: BLE001
                    print(f"  note dm failed: {type(ex).__name__}", flush=True)
            elif action in {"unknown", "ack"}:
                try:
                    web.chat_postMessage(channel=channel, text=DEFAULT_REPLY,
                                         thread_ts=thread_ts)
                except Exception as ex:  # noqa: BLE001
                    print(f"  default reply failed: {type(ex).__name__}", flush=True)
            _mark(ts)
            return

        if member:
            Path(user_ledger).parent.mkdir(parents=True, exist_ok=True)
        try:
            reply = apply_command(action, body, datetime.now(MYT), clients,
                                  user_ledger, users)
        except Exception as ex:  # noqa: BLE001 - never leave the user without a reply
            print(f"[error] {type(ex).__name__}: {ex}", flush=True)
            reply = f"Something broke: {type(ex).__name__}"
        if action not in {"unknown", "ack", "help", "list", "notes", "ask"}:
            try:
                from . import learning

                learning.remember(LEADING_MENTION.sub("", text), action, user)
            except Exception as ex:  # noqa: BLE001 - learning must never block
                print(f"  learn failed: {type(ex).__name__}", flush=True)
        if action == "assign" and reply.startswith("Assigned to "):
            assign_to, assign_what = split_target(body, users, user)
            if assign_to and assign_to != user:
                sender_name = ((profiles.get(user) or {}).get("name")
                               or ("Ridha" if user == owner
                                   else slack_user_name(env["SLACK_BOT_TOKEN"], user)))
                # Assigning by row id must copy the task title, never the id.
                what = assign_title(ledger_path,
                                    assign_what or body)
                cross_assign(env, profiles, user, sender_name, assign_to,
                             what, ledger_path)
        print(f"  reply: {reply[:120]!r}", flush=True)
        long_note = (action == "note" and raw_action == "unknown"
                     and user == owner
                     and (len(text) >= 200 or text.count("\n") >= 3))
        if (not long_note and action in EMOJI_ACKS and reply.startswith(
                ("Added.", "Noted.", "Converted to note:"))):
            try:
                web.reactions_add(channel=channel, timestamp=ts,
                                  name=EMOJI_ACKS[action])
                _mark(ts)
                return
            except Exception as ex:  # noqa: BLE001 - fall back to the text reply
                print(f"  ack react failed: {type(ex).__name__}: {ex}", flush=True)
        if late:
            reply = "_(answered late, I was offline)_\n" + reply
        blocks = None
        if long_note:
            from .triage_ui import note_action_blocks

            blocks = note_action_blocks(
                commitment_id("manual", body.lower(), body), text)
            reply = "Saved as a note. Keep it, make it a task, or discard?"
        if action == "list" and (user == owner or member):
            try:
                from .notify import sent_reminders
                from .slack_lists import list_url
                from .triage_ui import list_blocks

                blocks = list_blocks(load(user_ledger), datetime.now(MYT),
                                     list_url(env, user),
                                     sent=sent_reminders(user))
            except Exception as ex:  # noqa: BLE001 - plain text still works
                print(f"  list blocks failed: {type(ex).__name__}", flush=True)
        if action == "help" and (user == owner or member):
            try:
                from .help_ui import home_blocks

                blocks = home_blocks()
            except Exception as ex:  # noqa: BLE001 - plain text still works
                print(f"  help blocks failed: {type(ex).__name__}", flush=True)
        say(reply, blocks=blocks)
        _mark(ts)

    def ledger_for_viewer(user_id: str) -> str | None:
        """The ledger behind a button click: owner or an allowlisted member."""
        if not user_id:
            return None
        if user_id == owner:
            return ledger_path
        people = load_profiles()
        return ledger_for(people, user_id, ledger_path) if user_id in people else None

    def publish_home(viewer: str) -> None:
        if not viewer:
            return
        from .home_ui import home_blocks, public_home_blocks
        from .slack_lists import list_url

        target = ledger_for_viewer(viewer)
        meetings = []
        if target:
            try:
                from .calendar import meetings_for_day
                from .profiles import load as load_profiles

                profile = load_profiles().get(viewer)
                if profile:
                    token = str(
                        Path(profile["ledger"]).parent / "google_token.json")
                    if Path(token).exists():
                        meetings = meetings_for_day(
                            env, datetime.now(MYT), token_path=token,
                            owner_email=profile.get("email"),
                            client_path=profile.get("google_client"))
                else:
                    meetings = meetings_for_day(env, datetime.now(MYT))
            except Exception as ex:  # noqa: BLE001 - meetings stay optional
                print(f"  home meetings failed: {type(ex).__name__}: {ex}",
                      flush=True)
        blocks = (home_blocks(load(target), datetime.now(MYT),
                              list_url(env, viewer), meetings)
                  if target else public_home_blocks(
                      env.get("SLACK_OWNER_ID", ""),
                      env.get("SLACK_TEAM", "gopantas")))
        for attempt in range(2):
            try:
                web.views_publish(
                    user_id=viewer,
                    view={"type": "home", "blocks": blocks})
                return
            except Exception as ex:  # noqa: BLE001 - Home is best effort
                if attempt:
                    print(f"  home publish failed: {type(ex).__name__}: {ex}",
                          flush=True)

    def handle(_socket_client, req):
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        payload = req.payload or {}
        if payload.get("command") == "/mini-reid":
            import urllib.request

            user = payload.get("user_id") or ""
            channel = payload.get("channel_id") or ""
            text = (payload.get("text") or "").strip()
            target = ledger_for_viewer(user)
            response_url = payload.get("response_url") or ""

            def respond(message: str, blocks: list[dict] | None = None) -> None:
                if not response_url:
                    return
                body = {"response_type": "ephemeral", "text": message}
                if blocks:
                    body["blocks"] = blocks
                request = urllib.request.Request(
                    response_url, data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"})
                try:
                    urllib.request.urlopen(request, timeout=15).read()
                except Exception as ex:  # noqa: BLE001 - best effort
                    print(f"  slash reply failed: {type(ex).__name__}: {ex}",
                          flush=True)

            if not target:
                respond("Ask Ridha to run `allow: @You` first.")
                return
            route = slash_route(text)
            if route == "list":
                from .notify import sent_reminders
                from .slack_lists import list_url
                from .triage_ui import list_blocks

                now = datetime.now(MYT)
                respond("Your list",
                        list_blocks(load(target), now, list_url(env, user),
                                    sent=sent_reminders(user)))
                return
            if route == "help":
                respond(HELP)
                return
            if route == "add":
                reply = _apply_command("add", text, datetime.now(MYT),
                                       clients, target, users)
                respond(reply)
                return
            process(channel, user, text, f"slash:{payload.get('trigger_id') or user}")
            respond("Sent to your DM.")
            return
        if payload.get("type") == "message_action":
            if payload.get("callback_id") == "add_to_mini_reid":
                msg = payload.get("message") or {}
                channel = (payload.get("channel") or {}).get("id") or ""
                metadata = {
                    "channel": channel,
                    "ts": msg.get("ts") or "",
                    "permalink": payload.get("permalink") or "",
                    "author": msg.get("user") or "",
                }
                try:
                    web.views_open(
                        trigger_id=payload.get("trigger_id") or "",
                        view=capture_modal(msg.get("text") or "", metadata))
                except Exception as ex:  # noqa: BLE001 - user can retry
                    print(f"  capture modal failed: {type(ex).__name__}: {ex}",
                          flush=True)
            return
        if payload.get("type") == "view_submission":
            view = payload.get("view") or {}
            if view.get("callback_id") == "mini_reid_capture":
                from .notify import react

                clicker = (payload.get("user") or {}).get("id") or ""
                target = ledger_for_viewer(clicker)
                if not target:
                    return
                values = (view.get("state") or {}).get("values") or {}
                title = ((values.get("title") or {}).get("value") or {}) \
                    .get("value") or ""
                metadata = json.loads(view.get("private_metadata") or "{}")
                if title.strip():
                    row = add_slack_capture(
                        target, title.strip(), metadata.get("channel") or "",
                        metadata.get("ts") or "", clicker, users,
                        datetime.now(MYT),
                        permalink=metadata.get("permalink") or "",
                        team=env.get("SLACK_TEAM", "gopantas"),
                        via="shortcut")
                    if row.get("native_id"):
                        channel_id, _, ts = row["native_id"].partition(":")
                        try:
                            react(env["SLACK_BOT_TOKEN"], channel_id, ts)
                        except Exception:  # noqa: BLE001 - best effort
                            pass
                    try:
                        send_dm_to(env, clicker,
                                   f"Added: {title.strip()[:160]}")
                    except Exception:  # noqa: BLE001 - best effort
                        pass
                return
            if view.get("callback_id") == "meet_edit":
                from .meeting_ui import slot_blocks
                from .meetings import propose_slots

                token = view.get("private_metadata") or ""
                values = (view.get("state") or {}).get("values") or {}
                title = ((values.get("title") or {}).get("value") or {}) \
                    .get("value") or ""
                notes = ((values.get("notes") or {}).get("value") or {}) \
                    .get("value") or ""
                state_now = _state()
                pending = (state_now.get("pending_meet") or {}).get(token)
                if not pending:
                    return
                pending["notes"] = notes[:8000]
                if title.strip():
                    pending["topic"] = title.strip()[:200]
                dur = int(pending.get("duration") or 30)
                busy: dict = {}
                try:
                    slots = propose_slots(env, pending["emails"], busy_out=busy,
                                          duration=dur)
                    pending["slots"] = slots
                except Exception:  # noqa: BLE001 - keep the previous slots
                    slots = pending.get("slots") or []
                Path(STATE).write_text(json.dumps(state_now))
                channel = pending.get("channel") or ""
                msg_ts = pending.get("message_ts") or ""
                people = pending.get("attendees") or [{
                    "name": pending.get("attendee", "Attendee"),
                    "email": (pending.get("emails") or [""])[0]}]
                if channel and msg_ts and slots:
                    web.chat_update(
                        channel=channel, ts=msg_ts,
                        text=f"Meeting proposal: {pending['topic']}",
                        blocks=slot_blocks(token, pending["topic"], people,
                                           slots, busy, duration=dur))
                return
            if view.get("callback_id") == "inbox_clear_apply":
                from .triage_ui import (apply_inbox_page, inbox_clear_modal,
                                        inbox_done_modal)

                clicker = (payload.get("user") or {}).get("id") or ""
                target = ledger_for_viewer(clicker)
                if not target:
                    return
                try:
                    page_ids = json.loads(view.get("private_metadata") or "[]")
                except ValueError:
                    page_ids = []
                values = (view.get("state") or {}).get("values") or {}
                chosen = ((values.get("not_tasks") or {})
                          .get("not_tasks") or {}).get("selected_options") or []
                ticked = [o.get("value") for o in chosen if o.get("value")]
                rows, added, dropped, remaining = apply_inbox_page(
                    load(target), page_ids, ticked, datetime.now(MYT))
                save(target, rows)
                view_id = view.get("id") or ""
                try:
                    if remaining:
                        web.views_update(
                            view_id=view_id,
                            view=inbox_clear_modal(rows, remaining))
                    else:
                        web.views_update(view_id=view_id,
                                         view=inbox_done_modal(added, dropped))
                except Exception as ex:  # noqa: BLE001 - the ledger is saved
                    print(f"  inbox modal update failed: "
                          f"{type(ex).__name__}: {ex}", flush=True)
                    try:
                        send_dm_to(env, clicker,
                                   f"Inbox: added {added}, marked {dropped} "
                                   "not a task.")
                    except Exception:  # noqa: BLE001 - best effort
                        pass
                return
            if view.get("callback_id") == "triage_apply":
                from .triage_ui import apply_triage

                clicker = (payload.get("user") or {}).get("id") or ""
                target = ledger_for_viewer(clicker)
                if not target:
                    return
                values = (view.get("state") or {}).get("values") or {}
                ids: list[str] = []
                for block_id, elements in values.items():
                    if not block_id.startswith("sel_"):
                        continue
                    chosen = (elements.get("items") or {}).get("selected_options") or []
                    ids.extend(o.get("value") for o in chosen if o.get("value"))
                choice = ((values.get("verdict") or {}).get("value") or {}) \
                    .get("selected_option") or {}
                verdict = choice.get("value") or "open"
                rows, count = apply_triage(load(target), ids,
                                           verdict, datetime.now(MYT))
                save(target, rows)
                clicker = (payload.get("user") or {}).get("id") or owner
                try:
                    send_dm_to(env, clicker,
                               f"Updated {count} item(s) to *{verdict}*.")
                except Exception as ex:  # noqa: BLE001 - best effort
                    print(f"  triage confirm failed: {type(ex).__name__}", flush=True)
            return
        if req.type == "interactive" or payload.get("actions"):
            for action in payload.get("actions") or []:
                action_id = action.get("action_id") or ""
                if action_id in {"meet_rsvp_yes", "meet_rsvp_no"}:
                    from .meetings import email_to_slack, load_created

                    clicker = (payload.get("user") or {}).get("id") or ""
                    eid = action.get("value") or ""
                    data = load_created()
                    rec = data.get(eid)
                    if not rec:
                        continue
                    by_email = email_to_slack()
                    for uid, prof in load_profiles().items():
                        email = (prof.get("email") or "").lower()
                        if email:
                            by_email[email] = uid
                    emails = {(a.get("email") or "").lower()
                              for a in rec.get("attendees") or []}
                    allowed = (clicker == rec.get("creator")
                               or any(by_email.get(e) == clicker for e in emails))
                    if not allowed:
                        continue
                    verdict = "yes" if action_id == "meet_rsvp_yes" else "no"
                    rec.setdefault("rsvps", {})[clicker] = verdict
                    Path("created_meetings.json").write_text(
                        json.dumps(data, indent=1, ensure_ascii=False))
                    label = "attending" if verdict == "yes" else "not attending"
                    text = f"Recorded: {label} — {rec.get('title', '')}"
                    try:
                        send_dm_to(env, clicker, text)
                    except Exception:  # noqa: BLE001 - best effort
                        pass
                    container = payload.get("container") or {}
                    ch = container.get("channel_id") or ""
                    msg_ts = container.get("message_ts") or ""
                    if ch and msg_ts:
                        try:
                            web.chat_update(
                                channel=ch, ts=msg_ts, text=text,
                                blocks=[{"type": "section", "text": {
                                    "type": "mrkdwn", "text": text}}])
                        except Exception:  # noqa: BLE001 - click applied
                            pass
                    continue
                if action_id in {"note_keep", "note_to_task", "note_discard"}:
                    from .listview import _title

                    clicker = (payload.get("user") or {}).get("id") or ""
                    target = ledger_for_viewer(clicker)
                    if not target:
                        continue
                    row_id = action.get("value") or ""
                    rows = load(target)
                    row = next((r for r in rows if r.get("id") == row_id),
                               None)
                    if not row:
                        continue
                    now = datetime.now(MYT)
                    if action_id == "note_to_task":
                        row["kind"] = "manual"
                        row["status"] = "open"
                        row["via"] = "note"
                        row["closed_at"] = None
                        row["closed_how"] = None
                    elif action_id == "note_discard":
                        row["status"] = "dropped"
                        row["closed_at"] = now.isoformat()
                        row["closed_how"] = "not_commitment"
                    row["last_activity"] = now.isoformat()
                    save(target, rows)
                    label = {"note_keep": "Kept as note",
                             "note_to_task": "Added to tasks",
                             "note_discard": "Discarded"}[action_id]
                    label_text = f"{label}: {_title(row)[:120]}"
                    container = payload.get("container") or {}
                    ch = container.get("channel_id") or ""
                    msg_ts = container.get("message_ts") or ""
                    if ch and msg_ts:
                        try:
                            web.chat_update(
                                channel=ch, ts=msg_ts, text=label_text,
                                blocks=[{"type": "section", "text": {
                                    "type": "mrkdwn", "text": label_text}}])
                        except Exception as ex:  # noqa: BLE001 - click applied
                            print(f"  note update failed: "
                                  f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if action_id == "request_access":
                    from .home_ui import access_request_blocks

                    clicker = (payload.get("user") or {}).get("id") or ""
                    if clicker and env.get("SLACK_OWNER_ID"):
                        try:
                            from .directory import lookup as directory_lookup

                            info = directory_lookup(clicker)
                            details = {
                                "name": info.get("real_name") or info.get("name"),
                                "email": info.get("email"),
                                "jira": info.get("jira_name"),
                            }
                            send_dm_to(env, env["SLACK_OWNER_ID"],
                                       f"Access request from <@{clicker}>",
                                       blocks=access_request_blocks(clicker,
                                                                    details))
                            send_dm_to(env, clicker,
                                       "Request sent. Ridha will set you up.")
                        except Exception as ex:  # noqa: BLE001 - best effort
                            print(f"  access request failed: "
                                  f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if action_id == "approve_access":
                    clicker = (payload.get("user") or {}).get("id") or ""
                    target_user = action.get("value") or ""
                    if clicker != owner or not target_user:
                        continue
                    container = payload.get("container") or {}
                    process(container.get("channel_id") or "",
                            owner, f"allow: <@{target_user}>",
                            f"access:{target_user}")
                    continue
                if action_id == "home_refresh":
                    publish_home((payload.get("user") or {}).get("id") or "")
                    continue
                if action_id == "meet_edit":
                    from .meeting_ui import edit_modal

                    token = action.get("value") or ""
                    pending = (_state().get("pending_meet") or {}).get(token)
                    if not pending:
                        continue
                    try:
                        web.views_open(
                            trigger_id=payload.get("trigger_id") or "",
                            view=edit_modal(token, pending["topic"],
                                            pending.get("notes", "")))
                    except Exception as ex:  # noqa: BLE001 - user can retry
                        print(f"  meet edit modal failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if action_id in {"meet_refresh", "meet_cancel"}:
                    from .meeting_ui import slot_blocks
                    from .meetings import propose_slots

                    token = action.get("value") or ""
                    state_now = _state()
                    pending = (state_now.get("pending_meet") or {}).get(token)
                    if not pending:
                        continue
                    container = payload.get("container") or {}
                    channel = container.get("channel_id") or ""
                    msg_ts = container.get("message_ts") or ""
                    if action_id == "meet_cancel":
                        state_now["pending_meet"].pop(token, None)
                        Path(STATE).write_text(json.dumps(state_now))
                        if channel and msg_ts:
                            web.chat_update(channel=channel, ts=msg_ts,
                                            text="Meeting proposal cancelled.")
                        continue
                    dur = int(pending.get("duration") or 30)
                    busy: dict = {}
                    try:
                        slots = propose_slots(env, pending["emails"],
                                              busy_out=busy, duration=dur)
                    except Exception as ex:  # noqa: BLE001 - keep old message
                        if channel and msg_ts:
                            web.chat_update(
                                channel=channel, ts=msg_ts,
                                text=f"Could not refresh: {type(ex).__name__}: {ex}")
                        continue
                    pending["slots"] = slots
                    Path(STATE).write_text(json.dumps(state_now))
                    if channel and msg_ts:
                        people = pending.get("attendees") or [{
                            "name": pending.get("attendee", "Attendee"),
                            "email": (pending.get("emails") or [""])[0]}]
                        blocks = slot_blocks(
                            token, pending["topic"], people, slots, busy,
                            duration=dur)
                        web.chat_update(channel=channel, ts=msg_ts,
                                        text=f"Free slots with {pending['attendee']}",
                                        blocks=blocks)
                    continue
                if action_id == "meet_slot":
                    from .meeting_ui import confirmation_blocks
                    from .meetings import create_event, remember_meeting

                    clicker = (payload.get("user") or {}).get("id") or ""
                    value = action.get("value") or ""
                    token, _, start = value.partition("|")
                    state_now = _state()
                    pending = (state_now.get("pending_meet") or {}).get(token)
                    if not pending or clicker != pending.get("user"):
                        continue
                    slot = next((s for s in pending["slots"]
                                 if s["start"] == start), None)
                    container = payload.get("container") or {}
                    channel = container.get("channel_id") or ""
                    msg_ts = container.get("message_ts") or ""
                    if not slot:
                        continue
                    try:
                        event = create_event(env, pending["topic"],
                                             slot["start"], slot["end"],
                                             pending["emails"],
                                             pending.get("notes", ""))
                    except Exception as ex:  # noqa: BLE001 - report, do not crash
                        message = (f"Could not create the meeting: "
                                   f"{type(ex).__name__}: {ex}\n"
                                   "If this is a permission error, run "
                                   "`.venv/bin/python -m mini_reid.google_auth` "
                                   "and try again.")
                        if channel and msg_ts:
                            web.chat_update(channel=channel, ts=msg_ts,
                                            text=message)
                        continue
                    attendees = pending.get("attendees") or [{
                        "name": pending.get("attendee", "Attendee"),
                        "email": (pending.get("emails") or [""])[0]}]
                    try:
                        remember_meeting(
                            event, pending["topic"], slot["start"], slot["end"],
                            attendees, clicker, pending.get("notes", ""))
                    except Exception as ex:  # noqa: BLE001 - event exists
                        print(f"  remember meeting failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
                    state_now["pending_meet"].pop(token, None)
                    Path(STATE).write_text(json.dumps(state_now))
                    link = event.get("hangoutLink") or event.get("htmlLink") or ""
                    blocks = confirmation_blocks(
                        pending["topic"], slot["start"], slot["end"], link)
                    text = blocks[0]["text"]["text"]
                    if channel and msg_ts:
                        web.chat_update(channel=channel, ts=msg_ts,
                                        text=text, blocks=blocks)
                    continue
                if action_id in {"help_topic", "help_home"}:
                    from .help_ui import home_blocks, topic_blocks, topic_text

                    container = payload.get("container") or {}
                    channel = container.get("channel_id") or ""
                    msg_ts = container.get("message_ts") or ""
                    if not channel or not msg_ts:
                        continue
                    if action_id == "help_home":
                        blocks, text = home_blocks(), "Mini-Reid help"
                    else:
                        key = ((action.get("selected_option") or {}).get("value")
                               or "capture")
                        blocks, text = topic_blocks(key), topic_text(key)
                    try:
                        web.chat_update(channel=channel, ts=msg_ts,
                                        text=text, blocks=blocks)
                    except Exception as ex:  # noqa: BLE001 - user can retry
                        print(f"  help update failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if action_id == "help_list":
                    from .listview import format_list
                    from .triage_ui import list_blocks

                    clicker = (payload.get("user") or {}).get("id") or ""
                    target = ledger_for_viewer(clicker)
                    if not target:
                        continue
                    container = payload.get("container") or {}
                    channel = container.get("channel_id") or ""
                    if not channel:
                        continue
                    rows = load(target)
                    now = datetime.now(MYT)
                    from .notify import sent_reminders

                    sent = sent_reminders(clicker)
                    try:
                        web.chat_postMessage(
                            channel=channel,
                            text=format_list(rows, now, sent=sent),
                            blocks=list_blocks(rows, now, sent=sent))
                    except Exception as ex:  # noqa: BLE001 - user can retry
                        print(f"  help list failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if action_id in {"triage_select_all", "triage_clear"}:
                    from .triage_ui import triage_modal

                    view = payload.get("view") or {}
                    clicker = (payload.get("user") or {}).get("id") or ""
                    target = ledger_for_viewer(clicker)
                    if not target or not view.get("id"):
                        continue
                    values = (view.get("state") or {}).get("values") or {}
                    choice = ((values.get("verdict") or {}).get("value") or {}) \
                        .get("selected_option") or {}
                    try:
                        web.views_update(
                            view_id=view["id"],
                            view=triage_modal(
                                load(target), datetime.now(MYT),
                                select_all=action_id == "triage_select_all",
                                default_verdict=choice.get("value")))
                    except Exception as ex:  # noqa: BLE001 - user can retry
                        print(f"  triage select failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if action_id == "inbox_clear_open":
                    trigger = payload.get("trigger_id") or ""
                    clicker = (payload.get("user") or {}).get("id") or ""
                    target = ledger_for_viewer(clicker)
                    if not target:
                        continue
                    try:
                        from .triage_ui import inbox_clear_modal

                        web.views_open(trigger_id=trigger,
                                       view=inbox_clear_modal(load(target)))
                    except Exception as ex:  # noqa: BLE001 - user can retry
                        print(f"  inbox modal failed: {type(ex).__name__}: {ex}",
                              flush=True)
                    continue
                if action_id == "triage_open":
                    trigger = payload.get("trigger_id") or ""
                    clicker = (payload.get("user") or {}).get("id") or ""
                    target = ledger_for_viewer(clicker)
                    if not target:
                        continue
                    try:
                        from .triage_ui import triage_modal

                        web.views_open(trigger_id=trigger,
                                       view=triage_modal(load(target),
                                                         datetime.now(MYT)))
                    except Exception as ex:  # noqa: BLE001 - user can retry
                        print(f"  triage modal failed: {type(ex).__name__}: {ex}",
                              flush=True)
                    continue
                if action_id == "stale_set":
                    from .triage_ui import apply_triage, parse_stale_value

                    selected = action.get("selected_option") or {}
                    parsed = parse_stale_value(selected.get("value") or "")
                    if not parsed:
                        continue
                    row_id, verdict = parsed
                    clicker = (payload.get("user") or {}).get("id") or ""
                    target = ledger_for_viewer(clicker)
                    if not target:
                        continue
                    rows, count = apply_triage(load(target), [row_id],
                                               verdict, datetime.now(MYT))
                    save(target, rows)
                    if count:
                        try:
                            send_dm_to(env, clicker,
                                       f"Updated to *{verdict}*.")
                        except Exception as ex:  # noqa: BLE001 - best effort
                            print(f"  stale confirm failed: {type(ex).__name__}",
                                  flush=True)
                    continue
                if action_id in {"confirm_task", "reject_task"}:
                    from .notify import react
                    from .triage_ui import (apply_confirmation,
                                            confirmation_update_blocks,
                                            remaining_confirmations)

                    clicker = (payload.get("user") or {}).get("id") or ""
                    member_profiles = load_profiles()
                    if clicker != owner and clicker not in member_profiles:
                        continue
                    target = (ledger_for(member_profiles, clicker, ledger_path)
                              if clicker != owner else ledger_path)
                    row_id = action.get("value") or ""
                    verdict = "open" if action_id == "confirm_task" else "dropped"
                    rows, row, count = apply_confirmation(
                        load(target), row_id, verdict, datetime.now(MYT))
                    save(target, rows)
                    if not row:
                        continue

                    container = payload.get("container") or {}
                    msg_channel = container.get("channel_id") or ""
                    msg_ts = container.get("message_ts") or ""
                    if msg_channel and msg_ts:
                        already = count == 0
                        label = ("Already handled" if already else
                                 "Added to the list" if verdict == "open"
                                 else "Not a task")
                        try:
                            web.chat_update(
                                channel=msg_channel, ts=msg_ts,
                                text=f"{label}: {(row.get('what') or '')[:120]}",
                                blocks=confirmation_update_blocks(
                                    row, verdict,
                                    remaining_confirmations(rows, msg_ts),
                                    already=already))
                        except Exception as ex:  # noqa: BLE001 - click still applied
                            print(f"  confirm update failed: "
                                  f"{type(ex).__name__}: {ex}", flush=True)

                    if count and verdict == "open" and row.get("source") == "slack":
                        channel_id, _, ts = (row.get("native_id") or "").partition(":")
                        if channel_id and ts:
                            try:
                                react(env["SLACK_BOT_TOKEN"], channel_id, ts)
                            except Exception as ex:  # noqa: BLE001 - best effort
                                print(f"  confirm react failed: "
                                      f"{type(ex).__name__}: {ex}", flush=True)
                    continue
                if not action_id.startswith("remind_"):
                    continue
                clicker = (payload.get("user") or {}).get("id") or ""
                st = _state()
                resolved = resolve_remind_button(st, action.get("value") or "",
                                                 clicker, owner)
                if not resolved:
                    continue
                key, choice, pend = resolved
                st["pending_remind"].pop(key, None)
                Path(STATE).write_text(json.dumps(st))
                try:
                    reply = deliver_pending_reminder(env, pend, choice)
                except Exception as ex:  # noqa: BLE001 - report to the channel
                    reply = f"Could not send that: {type(ex).__name__}"
                channel = pend.get("channel") or ""
                msg_ts = (payload.get("message") or {}).get("ts") or ""
                try:
                    web.chat_update(
                        channel=channel, ts=msg_ts, text=reply,
                        blocks=[{"type": "section",
                                 "text": {"type": "mrkdwn", "text": reply}}])
                except Exception:  # noqa: BLE001 - fall back to a fresh message
                    if channel:
                        web.chat_postMessage(channel=channel, text=reply,
                                             thread_ts=msg_ts or None)
            return
        event = (req.payload or {}).get("event") or {}
        if event.get("type") == "file_shared":
            from .files import ingest

            try:
                record = ingest(env, event.get("file_id") or "")
                if record:
                    print(f"  file ingested: {record['name']}", flush=True)
                    from .files import ack_messages

                    for uid, text in ack_messages(
                            event.get("user_id") or "",
                            env.get("SLACK_OWNER_ID", ""), [record]):
                        send_dm_to(env, uid, text)
            except Exception as ex:  # noqa: BLE001 - file must not stop the bot
                print(f"  file ingest failed: {type(ex).__name__}: {ex}",
                      flush=True)
            return
        if event.get("type") == "app_home_opened":
            publish_home(event.get("user") or "")
            return
        if event.get("type") == "reaction_added":
            file_parsed = file_reaction(
                event, env.get("FILE_REACTION", "page_facing_up"))
            if file_parsed:
                from .files import ack_messages, ingest, message_files

                channel, msg_ts, reactor = file_parsed
                records = []
                for attachment in message_files(env, channel, msg_ts):
                    try:
                        record = ingest(env, attachment.get("id") or "")
                    except Exception as ex:  # noqa: BLE001 - keep other files
                        print(f"  file react ingest failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
                        record = None
                    if record:
                        records.append(record)
                for uid, text in ack_messages(
                        reactor, env.get("SLACK_OWNER_ID", ""), records):
                    try:
                        send_dm_to(env, uid, text)
                    except Exception as ex:  # noqa: BLE001 - best effort
                        print(f"  file ack failed: {type(ex).__name__}: {ex}",
                              flush=True)
                return
            parsed = capture_reaction(event,
                                      env.get("CAPTURE_REACTION", "pushpin"))
            if parsed:
                channel, msg_ts, reactor = parsed
                target = ledger_for_viewer(reactor)
                text = fetch_message_text(env, channel, msg_ts) if target else ""
                if target and text:
                    row = add_slack_capture(
                        target, text, channel, msg_ts, reactor, users,
                        datetime.now(MYT),
                        team=env.get("SLACK_TEAM", "gopantas"),
                        via="reaction")
                    try:
                        send_dm_to(
                            env, reactor,
                            f"Added: {text[:160]}\n"
                            f"<{row.get('source_link')}|open source>")
                    except Exception as ex:  # noqa: BLE001 - capture is durable
                        print(f"  reaction ack failed: "
                              f"{type(ex).__name__}: {ex}", flush=True)
            return
        if event.get("bot_id"):
            return
        if event.get("subtype"):
            ack = edit_ack_target(event, bot_user_id)
            if ack:
                try:
                    web.reactions_add(channel=ack[0], timestamp=ack[1],
                                      name="white_check_mark")
                except Exception as ex:  # noqa: BLE001 - reaction is best effort
                    print(f"  edit react failed: {type(ex).__name__}: {ex}", flush=True)
                msg = event.get("message") or {}
                text, user = msg.get("text") or "", msg.get("user") or ""
                action, _ = parse_command(text, bot_user_id)
                if user == owner:
                    action = owner_action(action, text)
                key = f"{ack[0]}:{ack[1]}"
                state = _state()
                edits = state.setdefault("edits", {})
                # Re-run an edited command once, but never a reminder (would
                # schedule twice) or undo (would step back twice).
                if (user == owner and text and action not in {"remind", "undo"}
                        and edits.get(key) != text):
                    edits[key] = text
                    if len(edits) > 200:
                        state["edits"] = dict(list(edits.items())[-200:])
                    Path(STATE).write_text(json.dumps(state))
                    release_message(STATE, ack[0], ack[1])
                    seen.discard((ack[0], ack[1]))
                    process(ack[0], user, text, ack[1],
                            thread_ts=msg.get("thread_ts") or ack[1])
            return
        text = event.get("text") or ""
        user = event.get("user") or ""
        channel = event.get("channel") or ""
        ts = event.get("ts") or ""
        if not channel or not user:
            return
        if user == bot_user_id:
            return  # never process the bot's own replies
        if user == env.get("SLACK_OWNER_ID") and re.match(
                r"^banter\b", text.strip(), re.I):
            if not claim_message(STATE, channel, ts):
                return
            control = banter_command(text, channel, users, datetime.now(MYT), env)
            if control:
                _, reply = control
                web.chat_postMessage(channel=channel, text=reply,
                                     thread_ts=event.get("thread_ts") or ts)
                return
        # message.channels/message.groups deliver every channel message. Only
        # act on ones that address the bot; DMs need no mention. Untagged
        # messages never get a reply, abuse or not.
        if not is_bot_addressed(event, bot_user_id):
            # A pending reminder question makes the next plain reply relevant.
            waiting = (_state().get("pending_remind") or {}).get(f"{channel}:{user}")
            if not waiting:
                return
        process(channel, user, text, ts,
                thread_ts=event.get("thread_ts") or ts)

    def catch_up(me_id: str) -> None:
        """Replay commands missed while the Mac was asleep. Best effort, late."""
        token = env.get("SLACK_USER_TOKEN")
        if not token or not me_id:
            return
        import time

        started = time.time()
        with _STATE_LOCK:
            state = _state()
            last = _catch_up_watermark(state, started)
            if not state.get("catch_up_ts"):
                state["catch_up_ts"] = f"{last:.6f}"
                Path(STATE).write_text(json.dumps(state))

        from .sources import _get_json

        matches: list[dict] = []
        page = 1
        while page <= 10:
            url = ("https://slack.com/api/search.messages?"
                   + urllib.parse.urlencode({
                       "query": f"<@{me_id}>", "count": 100, "page": page,
                       "sort": "timestamp", "sort_dir": "desc"}))
            try:
                d = _get_json(url, {"Authorization": f"Bearer {token}"})
            except Exception as ex:  # noqa: BLE001
                print(f"catch-up search failed: {type(ex).__name__}", flush=True)
                return
            if not d.get("ok"):
                print(f"catch-up search error: {d.get('error')}", flush=True)
                return
            batch = (d.get("messages") or {}).get("matches") or []
            matches.extend(batch)
            pages = (((d.get("messages") or {}).get("paging") or {}).get("pages")
                     or page)
            if len(batch) < 100 or page >= pages:
                break
            page += 1

        late = 0
        for m in reversed(matches):
            try:
                if float(m.get("ts", 0)) <= last:
                    continue
            except ValueError:
                continue
            ch = (m.get("channel") or {}).get("id")
            user = m.get("user")
            text = m.get("text") or ""
            if (ch and user and user != me_id and not m.get("bot_id")
                    and not m.get("subtype")):
                process(ch, user, text, m["ts"], late=True,
                        thread_ts=m.get("thread_ts") or m["ts"])
                late += 1
        # DMs carry no literal mention, so search never returns them. Read every
        # DM the bot is in, not only the owner's.
        dm_ok = True
        try:
            from .notify import _post as slack_post
            from .sources import _get_json as slack_get

            bot = env["SLACK_BOT_TOKEN"]
            dms: list[str] = []
            cursor = ""
            while True:
                params = {"types": "im", "limit": 200, "exclude_archived": "true"}
                if cursor:
                    params["cursor"] = cursor
                listing = slack_post("conversations.list", bot, **params)
                dms.extend(c.get("id") for c in listing.get("channels") or []
                           if c.get("id"))
                cursor = (listing.get("response_metadata") or {}).get("next_cursor") or ""
                if not cursor:
                    break
            for dm in dms:
                hist = slack_get(
                    "https://slack.com/api/conversations.history?"
                    + urllib.parse.urlencode({"channel": dm, "oldest": f"{last:.6f}", "limit": 200}),
                    {"Authorization": f"Bearer {bot}"})
                for m in reversed(hist.get("messages") or []):
                    if m.get("bot_id") or m.get("subtype") or not m.get("user"):
                        continue
                    action, _ = parse_command(m.get("text") or "", me_id)
                    if action in {"unknown", "ack"}:
                        continue
                    process(dm, m["user"], m.get("text") or "", m["ts"], late=True)
                    late += 1
        except Exception as ex:  # noqa: BLE001
            dm_ok = False
            print(f"catch-up DM read failed: {type(ex).__name__}", flush=True)

        if dm_ok:
            with _STATE_LOCK:
                state = _state()
                state["catch_up_ts"] = f"{started:.6f}"
                Path(STATE).write_text(json.dumps(state))
        if late:
            print(f"catch-up: processed {late} missed message(s)", flush=True)

    import logging

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    client.socket_mode_request_listeners.append(handle)
    ident = web.auth_test()
    bot_user_id = ident.get("user_id") or ""
    client.connect()
    print(f"[{datetime.now(MYT):%H:%M:%S}] listening as @{ident.get('user')} "
          f"({ident.get('user_id')}) in {ident.get('team')}", flush=True)
    try:
        catch_up(ident.get("user_id"))
    except Exception as ex:  # noqa: BLE001 - catch-up must never stop the listener
        print(f"catch-up failed: {type(ex).__name__}: {ex}", flush=True)
    try:
        interval = float(env.get("CATCHUP_SECONDS") or 300)
    except ValueError:
        interval = 300
    if interval > 0:
        threading.Thread(target=_catch_up_loop,
                         args=(ident.get("user_id") or "", interval, catch_up,
                               threading.Event()),
                         daemon=True).start()
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    import sys

    from .sources import load_env

    sys.exit(main(load_env(".env")))
