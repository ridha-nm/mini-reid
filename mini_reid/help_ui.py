"""Help that starts from what the person needs to do, not a command dump."""
from __future__ import annotations

TOPICS: dict[str, tuple[str, str, list[str]]] = {
    "capture": (
        "Capture something",
        "Put a task, note or reminder in.",
        ["`add: send the deck by Friday` — a task",
         "`note: Daniel wants the mapping redone` — no deadline",
         "`assign: @Kasib send the deck` — someone else owes it",
         "`remind me to call Arman at 3pm` — a timed DM"],
    ),
    "organise": (
        "Update or organise",
        "Change the wording, date, owner or order.",
        ["`status: deck in progress` — open / in progress / blocked",
         "`priority: deck 1` — 1 first, 5 last, `none` clears",
         "`due: deck by Monday` — new date",
         "`edit: deck to Send deck by Monday` — rename and re-date",
         "`snooze: deck 3d` — push it out",
         "`waiting: deck on Daniel` — move to Waiting on others",
         "`combine: #9 into #7` / `uncombine: #7` — duplicates"],
    ),
    "close": (
        "Close or remove",
        "Finish it, drop it, or tell me it was never a task.",
        ["`done: deck` — close it",
         "`done 7, 9` — several at once",
         "Paste a list after `done:` or `not:` — one row per line",
         "`drop: deck` — remove quietly",
         "`not: something that is not part c` — wrong item; teaches the filter",
         "`undo:` — reverse the last change, 10 deep"],
    ),
    "find": (
        "Find and view",
        "See what is open, search, or ask your own notes.",
        ["`list` — grouped tasks, Inbox and Notes",
         "`find: eupe` — search the ledger",
         "`notes` — notes only",
         "`ask: what did we agree with Eupe on waste` — answers from your writing",
         "Every list row has a short id: `abc123` works in every command"],
    ),
    "inbox": (
        "Confirm new items",
        "Nothing reaches the list until you say so.",
        ["New-item DM — **Add to list** or **Not a task**",
         "`list` → **Triage & update** — set a status on several rows",
         "**Select all** / **Clear** in the triage modal",
         "Unanswered rows wait in the Inbox section of `list`"],
    ),
    "meet": (
        "Schedule a meeting",
        "I read everyone's calendars and offer free slots, then create the event and invite.",
        ["`meet: @Kasib about BD Command Centre`",
         "`meet: @Kasib and @Charanya about the deck` — multiple people",
         "`meet: @Kasib about the deck for 45 minutes` — any duration 15–180",
         "`cancel: Change Request` — cancel the nearest matching meeting",
         "or just `set meeting with Kasib to discuss BD Command Centre`",
         "I propose five 30-minute slots in the next five working days",
         "Pick a slot — Google Calendar event + Meet link + invite sent"],
    ),
    "remind": (
        "Reminders and meetings",
        "Timed DMs, other people, and meeting replies.",
        ["`remind me to send the deck in 2 minutes` — Slack schedules it",
         "`remind @Arman to send the deck at 3pm` — DM someone else",
         "`reminders` — sent, pending, replied",
         "Meeting DM — reply `yes`, `no <reason>`, `moved <note>`, or "
         "`reschedule to <time> <note>`"],
    ),
    "team": (
        "Team and setup",
        "Your own ledger, mail and Jira.",
        ["`allow: @Charanya` — give a teammate their own Mini-Reid (owner only)",
         "`clients: Eupe, Gamuda` — filter your Gmail to those clients",
         "`clients` — show the current filter",
         "`setup` — resend your Gmail / Jira setup link"],
    ),
    "fun": (
        "Fun",
        "Harmless, no ledger row.",
        ["`give @Raj a hug`",
         "`high five @Raj`",
         "`fist bump @Raj`",
         "`pat @Raj on the back`",
         "`banter on 2h` — sassy replies in allowed channels only"],
    ),
}


def home_blocks() -> list[dict]:
    options = [{"text": {"type": "plain_text", "text": label[:75]},
                "value": key} for key, (label, _, _) in TOPICS.items()]
    return [
        {"type": "section",
         "text": {"type": "mrkdwn",
                  "text": "*What do you need to do?* Pick a topic, or jump straight in."}},
        {"type": "actions", "elements": [
            {"type": "button", "action_id": "help_list",
             "text": {"type": "plain_text", "text": "My list"}},
            {"type": "button", "action_id": "triage_open",
             "text": {"type": "plain_text", "text": "Triage inbox"},
             "style": "primary"},
        ]},
        {"type": "actions", "elements": [{
            "type": "static_select",
            "action_id": "help_topic",
            "placeholder": {"type": "plain_text", "text": "Choose a topic"},
            "options": options,
        }]},
    ]


def topic_blocks(key: str) -> list[dict]:
    label, blurb, examples = TOPICS.get(key) or TOPICS["capture"]
    blocks = [
        {"type": "section",
         "text": {"type": "mrkdwn", "text": f"*{label}*\n{blurb}"}},
        {"type": "section",
         "text": {"type": "mrkdwn", "text": "\n".join(f"• {x}" for x in examples)}},
        {"type": "actions", "elements": [
            {"type": "button", "action_id": "help_home",
             "text": {"type": "plain_text", "text": "Back to topics"}},
        ]},
    ]
    return blocks


def topic_text(key: str) -> str:
    label, blurb, examples = TOPICS.get(key) or TOPICS["capture"]
    return f"*{label}*\n{blurb}\n" + "\n".join(f"• {x}" for x in examples)
