# Auto-Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obvious commitments enter the list without a click; uncertain ones keep waiting in Inbox.

**Architecture:** `extract()` already builds one row per captured item. Add a rules-only `auto_reason()` beside it that looks at source, kind, request language, due date and direct addressing, then stamps `capture: "auto" | "inbox"` on the row. `triage_rows()` turns that stamp into the saved status; the watcher and member cycle only attach confirm buttons for `inbox` rows.

**Tech Stack:** Python 3, existing regexes in `extract.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-05-flying-car-design.md` (subsystem 2)

## Global Constraints

- Rules only. No model, no network, no client content leaves the Mac.
- The same policy applies to the owner and every allowlisted member.
- Existing rows are never migrated; only rows captured after this change use the policy.
- Nothing is deleted: an uncertain row still lands in Inbox with its buttons.

## Review Focus

- Jira board items that are not real work (reporter noise, already handled tickets) must not flood the list — only assigned, not-Done, non-Epic issues reach `extract()`.
- A Slack mention containing "please" but no ask (e.g. "please note the office is closed") must stay in Inbox.
- Shared-alias mail that merely copies Ridha must not auto-add; direct addressing is required.
- A model rewrite must not change the capture decision; the rule row decides, the model only renames.
- Member rows must follow the same policy as the owner's.

---

### Task 1: Rules-only confidence

**Files:**
- Modify: `mini_reid/extract.py` (add `auto_reason`, call it in `extract`)
- Test: `tests/test_extract.py`

**Interfaces:**
- Produces: `auto_reason(item: dict, text: str, due: str | None, me: str | None) -> str | None` — a short reason string or `None`.
- Produces: rows carry `capture: "auto" | "inbox"` and `capture_why: str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_auto_capture_matrix():
    from mini_reid.extract import auto_reason
    slack = {"source": "slack", "kind": "mention"}
    dm = {"source": "slack", "kind": "dm"}
    mail = {"source": "gmail", "kind": "inbox",
            "to": "Ridha <ridha@pantas.com>"}
    jira = {"source": "jira", "kind": "issue"}
    assert auto_reason(jira, "Audit data units", None, None) == "jira-assigned"
    assert auto_reason(slack, "can you review the deck", None, None) == "slack-direct-ask"
    assert auto_reason(slack, "the office is closed tomorrow", None, None) is None
    assert auto_reason(dm, "send the deck", None, None) is None
    assert auto_reason(dm, "send the deck by Friday", "2026-11-06", None) == "slack-dm-ask"
    assert auto_reason(mail, "please confirm the mapping", None, "Ridha") == "email-direct-ask"
    alias = dict(mail, to="BD <bd@pantas.com>")
    assert auto_reason(alias, "please confirm the mapping", None, "Ridha") is None
```

Also assert `extract()` stamps the fields:

```python
def test_extract_stamps_capture_mode():
    item = {"source": "slack", "native_id": "s1", "kind": "mention",
            "author": "kasib", "text": "can you review the deck", "link": "l",
            "ts": "2026-10-30T08:00:00+08:00"}
    row = extract(item, None, NOW)[0]
    assert row["capture"] == "auto"
    assert row["capture_why"] == "slack-direct-ask"
```

- [ ] **Step 2: Run tests, expect failure**

Run: `python -m pytest tests/test_extract.py -q`
Expected: ImportError for `auto_reason`.

- [ ] **Step 3: Implement**

In `mini_reid/extract.py`, add:

```python
EXPLICIT_ASK = re.compile(
    REQUEST_MODAL.pattern + "|" + REQUEST_POLITE.pattern + "|" + REQUEST_NEED.pattern,
    re.I)


def auto_reason(item: dict, text: str, due: str | None,
                me: str | None) -> str | None:
    """Why this row can skip the click, or None to keep it in Inbox."""
    source = item.get("source") or ""
    kind = item.get("kind") or ""
    if source == "jira":
        return "jira-assigned"
    ask = bool(EXPLICIT_ASK.search(text or ""))
    if source == "slack" and kind == "mention" and ask:
        return "slack-direct-ask"
    if source == "slack" and kind == "dm" and (ask or due):
        return "slack-dm-ask"
    if source == "gmail" and kind == "inbox":
        needle = (me or "Ridha").split("@")[0].lower()
        direct = needle in (item.get("to") or "").lower() or needle in (text or "").lower()
        if direct and (ask or due):
            return "email-direct-ask"
    return None
```

In `extract()` just before `return [{...}]`, compute
`reason = auto_reason(item, gate_text, due, me)` and add to the row:

```python
"capture": "auto" if reason else "inbox",
"capture_why": reason or "",
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_extract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/extract.py tests/test_extract.py
git commit -m "feat: rules-only auto-capture confidence"
```

---

### Task 2: Triage respects the stamp

**Files:**
- Modify: `mini_reid/watcher.py:63-84` (`triage_rows`)
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: row fields `capture`, `capture_why` from Task 1.
- Produces: `triage_rows()` rows with `status` equal to `"open"` when `capture == "auto"`, else `"inbox"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_triage_auto_capture_skips_the_click():
    from mini_reid.watcher import triage_rows
    fresh = [dict(_rule("m1"), capture="auto", capture_why="jira-assigned")]
    out = triage_rows(fresh, [])
    assert out[0]["status"] == "open"


def test_model_rewrite_cannot_change_the_capture_decision():
    from mini_reid.watcher import triage_rows
    fresh = [dict(_rule("m1"), capture="auto")]
    model = [dict(_rule("m1"), what="Review the deck")]
    out = triage_rows(fresh, model)
    assert out[0]["what"] == "Review the deck"
    assert out[0]["status"] == "open"
    assert out[0]["capture"] == "auto"
```

Update the two existing triage tests: `_rule()` carries no `capture`, so their `status == "inbox"` assertions stay valid.

- [ ] **Step 2: Run tests, expect failure**

Run: `python -m pytest tests/test_watcher.py -q`
Expected: FAIL, status is `"inbox"`.

- [ ] **Step 3: Implement**

In `triage_rows`, replace the fixed inbox assignment:

```python
        status = "open" if row.get("capture") == "auto" else "inbox"
        if better:
            out.append(dict(better, status=status,
                            capture=row.get("capture", "inbox"),
                            capture_why=row.get("capture_why", ""),
                            client=row.get("client"),
                            asker=row.get("asker") or better.get("asker")))
        else:
            out.append(dict(row, status=status))
```

and for model-only rows keep `status="inbox"` (the rule gate never offered them).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_watcher.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/watcher.py tests/test_watcher.py
git commit -m "feat: triage honours auto-capture stamps"
```

---

### Task 3: Alert only asks for the uncertain rows

**Files:**
- Modify: `mini_reid/watcher.py:635-642` (owner cycle)
- Modify: `mini_reid/members.py:202-209` (member cycle)
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: statuses from Task 2.
- Produces: `pending_rows(rows: list[dict]) -> list[dict]` in `watcher.py`; `confirm_blocks()` receives only `inbox` rows; `_stamp_confirmation()` stamps only those ids.

- [ ] **Step 1: Write the failing test**

```python
def test_pending_rows_are_the_ones_needing_a_click():
    from mini_reid.watcher import pending_rows
    rows = [{"id": "a", "status": "open"}, {"id": "b", "status": "inbox"}]
    assert [r["id"] for r in pending_rows(rows)] == ["b"]
```

- [ ] **Step 2: Run test, expect failure**

Run: `python -m pytest tests/test_watcher.py -q`
Expected: ImportError for `pending_rows`.

- [ ] **Step 3: Implement**

In `mini_reid/watcher.py`, above `format_alert`:

```python
def pending_rows(rows: list[dict]) -> list[dict]:
    """Only uncertain captures get Add / Not a task buttons."""
    return [r for r in rows if (r.get("status") or "") == "inbox"]
```

Owner cycle:

```python
        pending = pending_rows(fresh)
        sent = send_dm(env, format_alert(fresh),
                       blocks=confirm_blocks(pending) if pending else None)
        _stamp_confirmation(ledger_path, {r["id"] for r in pending}, sent)
```

Member cycle: import `pending_rows` with the other watcher helpers, delete
`fresh = [dict(row, status="inbox") ...]`, and apply the same `pending` split
before `confirm_blocks` and `_stamp_confirmation`.

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mini_reid/watcher.py mini_reid/members.py tests/test_watcher.py
git commit -m "feat: confirm only uncertain captures"
```

---

### Task 4: Document the policy

**Files:**
- Modify: `CHANGES.md` (newest-first entry)
- Modify: `HANDOFF.md` (resume note + test count)

- [ ] **Step 1: Add the CHANGES entry**

State the auto rules in plain lines, the three reasons
(`jira-assigned`, `slack-direct-ask`, `slack-dm-ask`, `email-direct-ask`),
and that everything else still waits in Inbox.

- [ ] **Step 2: Update HANDOFF**

Replace the "every new candidate waits for a click" sentence with the new
policy, and update the test count.

- [ ] **Step 3: Commit**

```bash
git add CHANGES.md HANDOFF.md
git commit -m "docs: auto-capture policy"
```

---

## Self-review

- Spec coverage: subsystem 2 asks for extraction plus a confidence policy; rules-only was the chosen path. Cloud runtime, action layer and planner stay out of scope.
- No task defines a function it does not use: `auto_reason`, `capture`, `capture_why`, `pending` are all consumed downstream.
- Types consistent: reason is `str | None`, capture is the literal `"auto" | "inbox"`.
- Review focus has a test each: Jira gate lives in `looks_actionable` (already tested), the "please but no ask" case is in the matrix, alias mail is in the matrix, model rewrite is Task 2, member parity is Task 3 (same code path).
- Proportion: four small tasks, one new pure function; no new module or dependency.
