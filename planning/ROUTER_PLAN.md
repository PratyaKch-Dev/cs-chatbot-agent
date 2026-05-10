# Router Refactor Plan

## Goal

Split the current monolithic LLM router into focused components:
- **Context Resolver** — conversation state, no LLM
- **SetFit Router** — intent classification, no tokens
- **LLM fallback** — ambiguous cases only, ~20 lines
- **Config-driven orchestrator** — troubleshooting stages from YAML
- **Confirmation + CS handoff** — only where it adds value

---

## Component Map

```
User message
      │
Message Type Handler          (done — image/sticker/file)
      │
Context Resolver              (NEW — step 2)
      │
SetFit Router                 (NEW — phase B)
  + Confidence Gate
  + LLM Fallback (shrunk)     (step 6)
      │
Orchestrator                  (step 5 — config-driven)
      │
  chitchat     → YAML template
  missing_info → clarification
  faq          → Qdrant → optional rewrite → answer → optional confirmation
  troubleshoot → stage_order from YAML → answer → confirmation → handoff
```

---

## 1. `config/troubleshooting_flows.yaml`

```yaml
# ── Global defaults ────────────────────────────────────────────────────────────
global:
  confirmation:
    faq_low_confidence_threshold: 0.4   # append confirmation when grounding < this

  faq_handoff:                           # used when low-confidence FAQ user replies "ยังไม่ได้"
    enabled: true
    handoff_to: cs

# ── Troubleshooting flows ──────────────────────────────────────────────────────
troubleshooting_withdrawal:
  stage_order:
    - api_check
    - confirmation
  api_check:
    tools: [user_profile_api, attendance_api]
    diagnose: [blacklist, inactive, sync_pending, attendance_issue, deduction_issue]
  confirmation:
    enabled: true
  handoff:
    enabled: true
    handoff_to: cs

troubleshooting_signup:
  stage_order:
    - faq_first
    - confirmation
  faq_first:
    qdrant_filter: [login, non_login]
    skip_confirmation_if_score_above: 0.75  # high-confidence → return immediately
  confirmation:
    enabled: true
  handoff:
    enabled: true
    handoff_to: cs

troubleshooting_cant_find_company:
  stage_order:
    - faq_first
    - confirmation
  faq_first:
    qdrant_filter: [login, non_login]
    skip_confirmation_if_score_above: 0.75
  confirmation:
    enabled: true
  handoff:
    enabled: true
    handoff_to: cs

troubleshooting_money_not_arrived:
  stage_order:
    - faq_first
    - confirmation
  faq_first:
    qdrant_filter: [feature_sod]
    skip_confirmation_if_score_above: 0.75
  confirmation:
    enabled: true
  handoff:
    enabled: true
    handoff_to: cs
```

**Key points:**
- `stage_order` = bot's execution list — iterates in order, never relies on YAML object ordering
- `confirmation` is the last stage — it returns immediately and waits for user reply
- `handoff` is **not** in `stage_order` — it runs only when the Context Resolver produces `FlowAction.TRIGGER_HANDOFF` (user replied no). The orchestrator reads `handoff.enabled` at that point.

---

## 2. Context Resolver `pipeline/context_resolver.py`

Renamed from "Redis Context Resolver" — this module owns conversation state interpretation, not just Redis loading.

### Two sub-responsibilities

**Memory Loader** — load from Redis:
- `active_context` (topic, status, last_root_cause, employee_id, faq_context)
- `history` (last 3 turns)
- `summary` (rolling recap)
- `pending_image` (from `chat:pending_image:*`)

**Context Interpreter** — detect `flow_action` (no LLM):

**When `active_context.status == "awaiting_confirmation"` (resolver handles reply first):**

| User reply | FlowAction produced |
|---|---|
| yes-words: ได้แล้ว / โอเค / ขอบคุณ | `END_FLOW` |
| no-words: ยังไม่ได้ / ยังมีปัญหา | `TRIGGER_HANDOFF` |
| other (new topic) | `TOPIC_SHIFT` |

**Normal turn (status == "active" or no active_context):**

| FlowAction | Condition |
|---|---|
| `END_FLOW` | ขอบคุณ / ได้แล้ว / โอเค / ลาก่อน |
| `CONTINUE_FLOW` | active_context exists + short/ambiguous ("ตอนนี้ล่ะ", "เช็คอีกที") |
| `TOPIC_SHIFT` | active_context exists + clearly different domain |
| `NEW` | no active_context |
| `AMBIGUOUS` | unclear → pass to LLM fallback |

**Build `enriched_query` — deterministic, no LLM:**

```python
FLOW_QUERY_MAP = {
    "troubleshooting_withdrawal":        "ตรวจสอบปัญหาเบิกเงิน",
    "troubleshooting_signup":            "ตรวจสอบปัญหาสมัครใช้งาน",
    "troubleshooting_cant_find_company": "ตรวจสอบปัญหาหาบริษัทไม่เจอ",
    "troubleshooting_money_not_arrived": "ตรวจสอบปัญหาเงินยังไม่เข้า",
}

if flow_action == FlowAction.CONTINUE_FLOW:
    prefix = FLOW_QUERY_MAP.get(active_intent, active_intent)
    enriched_query = f"{prefix} {message} อีกครั้ง"
else:
    # TOPIC_SHIFT | NEW | AMBIGUOUS — use raw message as-is
    enriched_query = message
```

Used as SetFit input — gives the classifier context for short/ambiguous messages without any LLM call.

### FlowAction enum

```python
class FlowAction(str, Enum):
    END_FLOW        = "end_flow"        # user satisfied or said goodbye
    TRIGGER_HANDOFF = "trigger_handoff" # user replied "no" → run handoff
    CONTINUE_FLOW   = "continue_flow"   # same topic, same flow
    TOPIC_SHIFT     = "topic_shift"     # new topic → close old flow
    NEW             = "new"             # no active context
    AMBIGUOUS       = "ambiguous"       # unclear → LLM fallback
```

`AWAITING_CONFIRMATION` does **not** belong here — it is a Redis status, not a flow action.

### active_context.status values (Redis)

```
"active"                → normal flow in progress
"awaiting_confirmation" → bot asked "ตอบโจทย์ไหมคะ", waiting for user reply
"escalated"             → handed off to CS
"resolved"              → user confirmed answer was helpful
```

**How they relate:**
- Orchestrator **writes** `active_context.status = "awaiting_confirmation"` when confirmation stage runs
- Resolver **reads** that status on the next turn — but first checks age:

```python
MAX_CONFIRMATION_AGE_MINUTES = 30   # defined in context_resolver.py

if status == "awaiting_confirmation":
    age = now - active_context["updated_at"]
    if age > MAX_CONFIRMATION_AGE_MINUTES:
        # stale — treat as new query, ignore old confirmation state
        flow_action = FlowAction.NEW
    else:
        # still valid — route yes/no reply
        ...
```

Without this: user disappears for 2 days, returns with "ยังไม่ได้" about something else — old confirmation triggers a wrong handoff.

- yes-words → `FlowAction.END_FLOW`
- no-words  → `FlowAction.TRIGGER_HANDOFF`
- other     → `FlowAction.TOPIC_SHIFT`

### active_context full shape (Redis)

```python
{
    "source":           "faq" | "troubleshooting" | "handoff",  # ← branching key
    "intent":           "faq" | "troubleshooting_withdrawal" | ...,
    "topic":            "withdrawal_issue",
    "status":           "active" | "awaiting_confirmation" | "escalated" | "resolved",
    "last_root_cause":  "attendance_issue",        # troubleshooting path
    "employee_id":      "EMP001",                  # troubleshooting path, never overwritten
    "retry_count":      0,                         # incremented on "ยังไม่ได้" / "เช็คอีกที"
    "faq_context": {                               # faq_first + low-confidence FAQ
        "last_query":   "ตรวจสอบปัญหาเบิกเงิน",
        "last_answer":  "...(FAQ answer text)...",
        "top_doc_ids":  ["doc_1", "doc_2"],
        "score":        0.31,
    },
    "handoff_reason":   "user_not_resolved" | "retry_limit" | "faq_low_confidence" | None,
    "flow_started_at":  "2026-05-10T14:00:00+07:00",  # set once on NEW flow, never overwritten
    "updated_at":       "2026-05-10T14:30:00+07:00",  # updated every turn (stale check)
}
```

`retry_count` is incremented by the orchestrator when `flow_action == TRIGGER_HANDOFF` but before handoff runs:
```python
if retry_count >= 2:
    auto_handoff()   # skip confirmation loop, escalate immediately
```

`source` is the primary branching key — use it instead of combining `intent + status`:
```python
if active_context["source"] == "faq":      ...
if active_context["source"] == "troubleshooting": ...
if active_context["source"] == "handoff":  ...
```

### Output dataclass

```python
@dataclass
class ContextResolution:
    flow_action:      FlowAction  # typed enum — no free strings
    resolver_reason:  str         # human-readable debug string
    resolver_version: str         # "v1", "v2", ... — bump when logic changes
    enriched_query:   str         # for SetFit + retrieval
    active_intent:    str         # current flow label if continuing
    pending_image:    str         # loaded here, passed downstream
    history:          list[dict]
    summary:          str
    active_context:   dict

RESOLVER_VERSION = "v1"          # module-level constant — log with every resolution
```

`resolver_reason` examples — critical for production debugging:
```
"awaiting_confirmation_expired_30min"
"awaiting_confirmation_yes_word"
"awaiting_confirmation_no_word"
"awaiting_confirmation_topic_shift"
"short_followup_after_active_context"
"end_word_detected"
"domain_shift_detected"
"no_active_context_new_query"
"ambiguous_no_context"
```

---

## 3. Confirmation — when it applies

**Enabled for:**
- All `troubleshooting_*` flows (via `stage_order`)
- FAQ when grounding score < 0.4 (low-confidence answer)

**Not enabled for:**
- `chitchat_*` — unnecessary after greeting/thanks/goodbye
- Normal FAQ (confident answer, score ≥ 0.4)
- `missing_info` — still asking for input

```yaml
# global defaults (read by orchestrator)
confirmation:
  faq_low_confidence_threshold: 0.4
```

**Prompt appended to answer:**
```
ตอบโจทย์ไหมคะ? 😊
• ได้แล้วค่ะ
• ยังไม่ได้ / ยังมีปัญหาอยู่
```

**Redis state saved:** `active_context.status = "awaiting_confirmation"`

**Context Resolver handles the reply:**
- yes-words (ได้แล้ว / โอเค / ขอบคุณ) → `end_flow`
- no-words (ยังไม่ได้ / ยังมีปัญหา) → `trigger_handoff`
- other → `topic_shift` (user changed subject)

---

## 4. CS Handoff

**Input to `_run_handoff_summary(active_context)`:**

```python
# What the LLM receives from active_context:
{
    "source":          "troubleshooting",              # primary branching key
    "intent":          "troubleshooting_withdrawal",
    "topic":           "withdrawal_issue",
    "last_root_cause": "attendance_issue",             # troubleshooting path
    "faq_context": {                                   # faq_first or low-confidence FAQ
        "last_query":  "ตรวจสอบปัญหาเบิกเงิน",
        "last_answer": "...(FAQ answer text)...",
        "score":       0.31,
    },
    "status":     "awaiting_confirmation",
    "updated_at": "2026-05-10T14:30:00+07:00",
}
```

**LLM generates short structured summary:**

```
สรุปปัญหาของคุณ:
• ปัญหา: เบิกเงินไม่ได้
• FAQ ที่แนะนำแล้ว: วิธีเบิกค่าจ้างล่วงหน้า
• ตรวจสอบแล้ว: บัญชีปกติ ไม่พบ attendance issue
• ผลลัพธ์: ผู้ใช้แจ้งว่ายังไม่ได้รับการแก้ไข

กำลังโอนให้เจ้าหน้าที่ช่วยเหลือต่อค่ะ 🙏
```

```
Freshchat API escalate (placeholder log until webhook ready)
active_context.status = "escalated"
```

---

## 5. Config-driven Orchestrator

### StageInput — passed to every stage

```python
@dataclass
class StageInput:
    message:        str
    enriched_query: str
    pending_image:  str    # from ContextResolution — empty string if none
    active_context: dict
    language:       str
    tenant_id:      str
    user_id:        str
```

`pending_image` flows into every stage:
- `faq_first` — augments retrieval query + prepended to RAG context
- `api_check` — typically ignored for diagnosis, kept in StageInput for handoff summary
- `handoff` — included in summary if non-empty

### FlowAction dispatch (top-level orchestrator)

```python
# Decision 1: Orchestrator behavior per FlowAction
if resolution.flow_action == FlowAction.END_FLOW:
    mark_active_context_resolved()
    return template("glad_to_help", language)

if resolution.flow_action == FlowAction.TRIGGER_HANDOFF:
    # Decision 2: Orchestrator increments retry_count — "Resolver detects, orchestrator acts"
    retry_count = active_context.get("retry_count", 0) + 1
    save_active_context({"retry_count": retry_count, "updated_at": now_iso()})
    if retry_count >= 2:
        save_active_context({"handoff_reason": "retry_limit"})
        return _run_handoff_summary(stage_input)   # auto-escalate, skip re-confirmation
    flow_cfg = flows.get(resolution.active_intent) or global_cfg["faq_handoff"]
    if flow_cfg.get("handoff", {}).get("enabled"):
        save_active_context({"handoff_reason": "user_not_resolved"})
        return _run_handoff_summary(stage_input)

if resolution.flow_action == FlowAction.CONTINUE_FLOW:
    if active_context.get("source") == "faq":
        # Decision 3: FAQ follow-up — replaces old _run_faq_followup
        return _run_faq(
            query=resolution.enriched_query,
            previous_faq_context=active_context.get("faq_context"),
            stage_input=stage_input,
        )
    # troubleshooting continue — resume from current flow config
    flow_config = flows[resolution.active_intent]
    # fall through to stage_order execution below

if resolution.flow_action == FlowAction.TOPIC_SHIFT:
    close_active_context(status="stale")           # close old topic cleanly
    # fall through as NEW query

if resolution.flow_action in (FlowAction.NEW, FlowAction.TOPIC_SHIFT):
    # route normally via label → flow_config lookup
    ...

if resolution.flow_action == FlowAction.AMBIGUOUS:
    label = _llm_fallback(resolution.enriched_query, language)
    flow_config = flows.get(label)
    # fall through to stage_order execution
```

### stage_order execution

```python
# stage_trace — runtime-only (no Redis), invaluable for debugging escalation decisions
stage_trace: list[dict] = []

# Orchestrator reads troubleshooting_flows.yaml and executes stage_order in sequence:
for stage in flow_config["stage_order"]:

    if stage == "faq_first":
        faq_cfg    = flow_config["faq_first"]
        faq_answer = _run_faq_with_filter(faq_cfg, stage_input)
        save_active_context({
            "source": "troubleshooting",
            "faq_context": {
                "last_query":   stage_input.enriched_query,
                "last_answer":  faq_answer.text,
                "top_doc_ids":  faq_answer.doc_ids,
                "score":        faq_answer.grounding_score,
            },
            "updated_at": now_iso(),
        })
        skip_threshold = faq_cfg.get("skip_confirmation_if_score_above", 0.75)
        stage_trace.append({"stage": "faq_first", "score": faq_answer.grounding_score,
                             "result": "skip_confirmation" if faq_answer.grounding_score > skip_threshold else "confirmation_needed"})
        if faq_answer.grounding_score > skip_threshold:
            return faq_answer                      # high confidence — skip confirmation
        answer = faq_answer

    elif stage == "api_check":
        answer = _run_api_check(flow_config["api_check"], stage_input)
        stage_trace.append({"stage": "api_check", "root_cause": answer.root_cause})

    elif stage == "confirmation":
        answer.text = _append_confirmation(answer.text)
        save_active_context({"status": "awaiting_confirmation", "updated_at": now_iso()})
        stage_trace.append({"stage": "confirmation", "result": "waiting"})
        return answer                              # returns here, waits for user reply

# ── Plain FAQ path — grounding check before returning ─────────────────────────
threshold = global_cfg["confirmation"]["faq_low_confidence_threshold"]
if route == "faq" and answer.grounding_score < threshold:
    answer.text = _append_confirmation(answer.text)
    save_active_context({
        "source":  "faq",
        "intent":  "faq",
        "topic":   answer.topic,
        "status":  "awaiting_confirmation",
        "handoff_reason": "faq_low_confidence",    # set now — used if user later replies "ยังไม่ได้"
        "faq_context": {
            "last_query":   stage_input.enriched_query,
            "last_answer":  answer.text,
            "score":        answer.grounding_score,
        },
        "updated_at": now_iso(),
    })
return answer
```

- `TRIGGER_HANDOFF` checked first — it's a reply to the previous turn, not a new query
- `retry_count` owned by orchestrator — resolver detects the intent, orchestrator writes the counter
- `CONTINUE_FLOW + source=="faq"` replaces old `_run_faq_followup` — same path, enriched_query carries context
- `pending_image` threaded through `StageInput` to every stage — no implicit globals
- `stage_order` runs top to bottom — `confirmation` always last, always returns early
- Adding a new troubleshooting flow = one YAML block, zero code changes

---

## 6. Shrink LLM Router Prompt

**Current `_ROUTER_SYSTEM`:** 177 lines
- Intent classification rules
- conv_state detection
- search_query vocabulary (100+ examples)
- key distinctions

**After refactor `_LLM_FALLBACK_SYSTEM`:** ~20 lines
- Label list only
- 3-line rule: troubleshooting = live account lookup needed, faq = everything else
- Return `{ intent, reason }` — no search_query

```python
_LLM_FALLBACK_SYSTEM = """\
Salary Hero chatbot router. Return JSON only.
Used only for low-confidence or ambiguous messages.

Labels:
  chitchat_greeting | chitchat_thanks | chitchat_goodbye
  chitchat_frustrated | chitchat_confused
  faq
  troubleshooting_withdrawal | troubleshooting_signup
  troubleshooting_cant_find_company | troubleshooting_money_not_arrived
  missing_info

Rules:
  troubleshooting_* = user needs live account/transaction lookup
  faq = all knowledge questions, how-to, conditions, errors
  missing_info = message too vague to classify

{"intent":"<label>","reason":"<short>"}"""
```

**search_query** moves to FAQ path — lazy rewrite:
```
enriched_query → Qdrant
top score < 0.35 → LLM rewrite → Qdrant again
score still low → escalate / missing_info
```
No LLM cost on the 80% of FAQ queries that hit directly.

---

## 7. SetFit Router (Phase B — after Phase A is stable)

```
Training pipeline:
  solutions_faq.csv → build_router_dataset.py → router_train_auto.csv
  → manual review → router_train.csv
  → train_setfit.py → model/setfit_router/

Inference:
  enriched_query → SetFit → (label, confidence)
  confidence ≥ 0.75 → use label
  confidence < 0.75 → LLM fallback
```

Model: `paraphrase-multilingual-MiniLM-L12-v2` (Thai + EN, 120MB, ~5ms)

---

## Implementation Order

```
Step 1  config/troubleshooting_flows.yaml
        + new subtypes added to router label map

Step 2  pipeline/context_resolver.py
        Memory Loader + Context Interpreter
        flow_action detection (no LLM)
        enriched_query builder

Step 3  Confirmation prompt + awaiting_confirmation Redis state
        Context Resolver handles yes/no reply routing

Step 4  CS handoff: LLM summary + placeholder log
        (Freshchat escalation API wired when webhook ready)

Step 5  Config-driven orchestrator
        Reads stage_order from YAML, executes stages

Step 6  Shrink _ROUTER_SYSTEM → _LLM_FALLBACK_SYSTEM (~20 lines)
        Move search_query rewrite to FAQ path (lazy, score-gated)

Step 7  SetFit training pipeline + router (Phase B)
        After steps 1–6 are stable in production
```

---

## Files Changed (Phase A)

| File | Change |
|------|--------|
| `config/troubleshooting_flows.yaml` | New — full flow config |
| `pipeline/context_resolver.py` | New — Memory Loader + Context Interpreter |
| `pipeline/router.py` | Shrink to ~20-line fallback prompt, add new labels |
| `pipeline/orchestrator.py` | Read stage_order, run stages, confirmation logic |
| `memory/active_context.py` | Add `awaiting_confirmation` + `escalated` status |
| `pipeline/handoff.py` | New — LLM summary + Freshchat placeholder |
| `llm/templates.py` | Add confirmation prompt TH/EN |

## Files Changed (Phase B)

| File | Change |
|------|--------|
| `data/router/build_router_dataset.py` | New — auto-generate from solutions_faq.csv |
| `data/router/router_train.csv` | New — reviewed training set |
| `scripts/train_setfit.py` | New — train + evaluate + save model |
| `pipeline/setfit_router.py` | New — load model, inference, confidence gate |

---

## Current Implementation (v2) — Problems Found & Design Changes

> This section documents what the original plan got wrong, production bugs discovered, and how the architecture evolved.

---

### Problem 1 — Context Resolver was over-classifying (rule-based CONTINUE_FLOW/TOPIC_SHIFT)

**What the original plan said:** The resolver would detect CONTINUE_FLOW (short message + active context) and TOPIC_SHIFT (domain keyword mismatch) deterministically using word lists.

**What went wrong:**
- `_is_short_followup()` false-positives: "เปลี่ยนเบอร์ยังไง" (how-to question) was 1 Thai token → `len(split()) < 5` → CONTINUE_FLOW → routed to troubleshooting recheck instead of FAQ
- `_is_domain_shift()` missed corrections: "เบิกเงินครับไม่ใช่เครม" has both withdrawal AND claim signals → domain shift not detected → old cached_faq context not cleared → wrong context poisoned the next answer
- Preamble words ("สอบถามหน่อย") triggered AMBIGUOUS which fell through to SetFit with no active context hint → wrong labels
- `_CORRECTION_WORDS` list was incomplete (couldn't catch all forms of "I meant X not Y" in Thai)

**Fix (v2 resolver):** Simplified `_interpret()` to only emit END_FLOW / TRIGGER_HANDOFF / NEW. All followup vs new-topic classification moved to the LLM router via `is_new: bool` field. The resolver only handles deterministic cases it can get right: goodbye words and awaiting_confirmation yes/no replies.

```
Before: resolver emits NEW | AMBIGUOUS | CONTINUE_FLOW | TOPIC_SHIFT | END_FLOW | TRIGGER_HANDOFF
After:  resolver emits NEW | END_FLOW | TRIGGER_HANDOFF (only)
        LLM router sets is_new=True (new topic) or is_new=False (followup)
```

---

### Problem 2 — CONTINUE_FLOW branch used wrong routing key

**What the original plan said:** CONTINUE_FLOW would reuse the same handler as the active topic (troubleshooting → recheck, faq → followup).

**What went wrong:** The orchestrator's CONTINUE_FLOW branch used `active_ctx["source"]` to decide troubleshooting vs FAQ. But `save_faq_context()` never wrote `source` — only `intent`. So `source` was always `None` → always fell into troubleshooting recheck even for FAQ followups.

**Fix:** CONTINUE_FLOW branch replaced entirely by `not decision.is_new` gate. Routing uses `decision.route` (LLM-decided) with `active_intent == "troubleshooting"` fallback:

```python
if not decision.is_new and decision.route not in (CHITCHAT, MISSING_INFO):
    go_ts = (decision.route == TROUBLESHOOTING
             or (active_intent == "troubleshooting" and decision.confidence < 0.8))
    answer = _run_troubleshooting_recheck(...) if go_ts else _run_faq_followup(...)
```

---

### Problem 3 — Fallback answer "ขออภัย" cascading into cached_faq

**What the original plan said:** Save FAQ context after every answer so followup has previous Q&A.

**What went wrong:** When the bot returned a fallback answer ("ขออภัย ไม่มีข้อมูลในส่วนนี้") it was still being saved to `cached_faq`. On the next turn:
1. Fallback text injected as `[Previous answer]` into retrieval context
2. LLM sees "no info" + fallback in context → outputs fallback again
3. `grounding_score` calculated by word overlap → score = 1.0 (fallback text appears verbatim in injected context)
4. Score > 0 → saved to `cached_faq` again → loop continues indefinitely

**Fix:** Text-based fallback detection instead of score-based:

```python
_FALLBACK_SUBSTRINGS = ("ไม่มีข้อมูลในส่วนนี้", "ไม่พบข้อมูลที่เกี่ยวข้อง")
if not any(s in answer.text for s in _FALLBACK_SUBSTRINGS):
    save_faq_context(...)   # only save real answers
```

Also: TOPIC_SHIFT now calls `clear_context()` to discard stale `cached_faq`. With v2 resolver this maps to: when `decision.is_new=True` and active_ctx exists, clear context before routing.

---

### Problem 4 — LLM router truncation on Gemini 2.5 Flash

**What the original plan said:** Router uses `max_tokens=60` — JSON output is only ~20 tokens.

**What went wrong:** Gemini 2.5 Flash is a **thinking model**. Thinking tokens count against `max_output_tokens`. With a 60-token budget, the model used ~58 tokens for internal reasoning, leaving only 1-2 tokens for the actual JSON. Observed outputs: `"H"`, `"Here is"` — not parseable JSON.

**Symptoms in trace log:** `out=1` or `out=2` with `router_call.reply = "Here is"` → JSON parse failed → `reason: fallback:intent=greeting` always → `is_new` always True → followup detection broken.

**Fix:** Increase `max_tokens` at LLM call sites to account for thinking overhead:

| Call site | Before | After | Reasoning |
|---|---|---|---|
| Router (`router.py`) | 60 | 512 | ~450 thinking + ~30 JSON output |
| Summarizer (`summarizer.py`) | 300 | 1024 | ~700 thinking + ~200 summary text |
| Answer generator | 1024 | 1024 | Already sufficient |

Also attempted: `thinking_config: {thinking_budget: 0}` in google.py generation_config. Rejected — disabling thinking causes Gemini 2.5 Flash to freeze after a few preamble tokens and output garbage. The model needs thinking to produce valid structured output.

---

### Problem 5 — "ดีครับ" routed as FAQ followup

**Root cause chain:**
1. Active context = FAQ topic (withdrawal question answered)
2. User says "ดีครับ" (chitchat affirmation)
3. Resolver: CONTINUE_FLOW (short message + active context)
4. Router: CHITCHAT
5. Orchestrator: CONTINUE_FLOW branch runs faq_followup regardless of router label
6. `_run_faq_followup()` retrieves nothing useful, gets fallback answer

**Fix (compound):**
- v2 resolver removes CONTINUE_FLOW entirely
- Orchestrator's `not decision.is_new` branch explicitly excludes CHITCHAT/MISSING_INFO:
  ```python
  if not decision.is_new and decision.route not in (Route.CHITCHAT, Route.MISSING_INFO):
      # followup path
  ```
- Chitchat during active context now falls through to the normal CHITCHAT handler

---

### v2 Router Architecture (current)

```
User message
      │
Context Resolver (v2)
  ├── END_FLOW: goodbye / "ขอบคุณ" / awaiting_confirmation + yes-word → template response, done
  ├── TRIGGER_HANDOFF: awaiting_confirmation + no-word → handoff summary, done
  └── NEW (everything else) → continue to router
      │
LLM Router (full context-aware)
  Input: message + 4 turns history + active_context + pending_image
  Output: { intent, reason, is_new: true|false }
  SetFit pre-check: fast path when NO active_context AND NO image (is_new always True from SetFit)
  SetFit skipped when: active_context set ("setfit:skip(ctx)") or image present ("setfit:skip(img)")
  SetFit low_conf: LLM fallback with "setfit:low_conf" prefix in reason
      │
Orchestrator dispatch
  ├── not decision.is_new + not CHITCHAT/MISSING_INFO → followup path
  │     ├── TROUBLESHOOTING or active_intent=="troubleshooting" → _run_troubleshooting_recheck
  │     └── else → _run_faq_followup
  ├── decision.is_new + active_ctx + not CHITCHAT → clear context (topic shift)
  ├── CHITCHAT → template response
  ├── MISSING_INFO → clarification template
  ├── TROUBLESHOOTING → staged flow from YAML
  └── FAQ → RAG retrieval → lazy rewrite if score < 0.35 → answer
```

### Pending image gate (v2)

```
Before (v1): gate on resolver flow_action (CONTINUE_FLOW/AMBIGUOUS) — decided before router
After  (v2): router sees raw pending_image via image_situation param
             gate on decision.is_new — applied AFTER router call
             is_new=False → use image (followup context)
             is_new=True  → discard image (new topic, image is stale)
```

### SetFit role (v2)

SetFit is used ONLY when there is no active_context and no pending_image — i.e., completely fresh new queries. In those cases `is_new` is always `True` (there is nothing to follow up on), so SetFit doesn't need to return `is_new` — it's implicit. When active_context exists, the LLM handles the full decision including `is_new`.

---

### Trace improvements (v2)

The pipeline trace (`logs/faq_trace.log`) now shows:

```
RESOLVER  new  (active_context_let_llm_decide)

ROUTE   FAQ  [followup]  label=faq  1240ms  in=564 out=45
[SYS]   Salary Hero chatbot router. Classify the user's current message...
[SYS]   ... (33 more lines)

→       Recent history:
→       User: เบิกเงินยังไงครับ
→       Bot: พนักงานสามารถขอเบิกค่าจ้างล่วงหน้าได้ที่แอปพลิเคชัน...
→       Message: ลองอีกทีได้มั้ย
←       {"intent":"faq","reason":"setfit:skip(ctx) → followup on same withdrawal topic","is_new":false}
        reason: setfit:skip(ctx) → setfit:skip(ctx) → followup on same withdrawal topic
```

Key fields added:
- `RESOLVER` section: flow_action + reason from context_resolver
- `[followup]` / `[new]` tag on ROUTE line
- `label=` showing LLM-returned intent label
- SetFit skip reason prepended to route reason: `setfit:skip(ctx)` / `setfit:skip(img)` / `setfit:low_conf`
- System prompt collapsed to 5 lines (+ "N more lines" indicator)
- Summary wrapped at 90 chars for readability

---

## Current Implementation (v3) — May 2026 — Smart Retrieval, Pinning, Hybrid Handoff

After v2 stabilized the routing decision flow, v3 focused on three classes of issues:
**FAQ retrieval accuracy, troubleshooting subtype routing, and user-controlled escalation.**

### Problem 1 — Vocabulary gap in retrieval

**What broke:** Vector + BGE rerank scored synonyms apart enough that the wrong article won.
- `ขอวิธีเบิกค่าจ้างล่วงหน้า` (exact phrase) → score 0.731 ✓
- `ขอวิธีการเบิกเงิน` (paraphrase) → score 0.563 → returned conditions article ✗
- `เบิกเงินได้กี่ครั้งต่อเดือนหรอ` → top=0.606 wrong article, rank-2=0.591 correct article (gap only 0.015)

The user explicitly rejected synonym CSV rows ("doesn't scale, have to update every time").

**Fix — multi-stage smart retrieval pipeline (`pipeline/orchestrator.py`):**

1. **Vector search → BGE rerank → top 3** (existing, unchanged for happy path)
2. **LLM smart rerank** when scores in gray zone OR rank-1/rank-2 gap < 0.05.
   Picks best of top-3 or returns `-1` if none truly answer.
3. **BGE full-scan fallback** — Qdrant `scroll()` over the entire tenant catalog
   (cached 5 min) → BGE rerank top-5 → LLM picker. Recovers articles that
   weren't in the top-25 vector hits at all.
4. **BGE-trust safety net** — when LLM picker says `-1` but BGE top score ≥ 0.45,
   trust BGE instead of clearing. Catches Flash-Lite being too literal on
   paraphrases like `ถอน` vs `เบิก`.
5. **Image-attach gating** — n-gram overlap (≥ 30%) between LLM answer and top
   doc. Stops "wrong image on novel answer" bug like
   `โหลดแอปได้ที่ไหน` → bot writes Play Store link but image was from `ประวัติเบิกเงิน`.

### Problem 2 — Stale duplicates poisoning Qdrant

**What broke:** indexer used positional IDs and `upsert`, never deleting.
After flexben-filter rolled out (15 rows removed), the OLD rows at higher
indices stayed in Qdrant. Multiple OTP rows existed; LLM picker rejected the
right one by accident, queries returned no results.

**Fix:** indexer (`indexers/index_solutions.py`) now deletes-and-recreates the
collection on every run. Always a clean state.

### Problem 3 — Tenant config mismatch

**What broke:** `tenants.yaml` had `company_id: "hns"` and
`vector_collections.th: "hns_th"`, but the CSV had `company_id: "happy_nest_space"`.
Indexer built `happy_nest_space_th`; chatbot queried `hns_th` (defaults-only).
HNS users never saw HNS-specific articles.

**Fix:**
- `tenants.yaml`: `company_id: "happy_nest_space"`, `vector_collections.th: "happy_nest_space_th"`
- `rag/retriever.py`: collection name now read from tenants.yaml `vector_collections`,
  with fallback to `{tenant_id}_{language}` for backwards compat.

### Problem 4 — Flexben articles leaking into HNS

15 `feature_flexben` articles were tagged `default`, so they landed in every
tenant's collection — including HNS, which doesn't have flexben.

**Fix:** added `excluded_source_types: [feature_flexben]` to the hns tenant
config. Indexer reads this and filters defaults before building per-tenant
collections.

### Problem 5 — Troubleshooting subtypes that should be FAQ

The router was emitting 5 troubleshooting labels (`withdrawal`, `signup`,
`cant_find_company`, `money_not_arrived`, `cant_receive_otp`) but only
`withdrawal` actually needs live API data. The other 4 have answers in the
FAQ catalog already. Forcing them through the API agent was wasteful and
returned generic templates.

**Fix:**
- `pipeline/router.py` `_LABEL_TO_ROUTE`: only `troubleshooting_withdrawal`
  routes to TROUBLESHOOTING; the other 4 route to FAQ.
- The label is preserved as `template_key` for analytics/tracing.
- `pipeline/orchestrator.py` adds `_TROUBLESHOOTING_FAQ_TITLES` mapping
  label → exact FAQ article title. **Pinned-FAQ shortcut** runs before any
  retrieval: if the label is in this map, look up the article by exact
  Question match (cached) and return it verbatim with image. ~0ms, deterministic.
- The pin fires regardless of `is_new` so followups also hit it.
- `agent/planner.py` `_TOOL_STRATEGY` retains the other labels as placeholders
  with empty tool lists, so future "FAQ-first then API" hybrids only need a
  one-line route flip in the router.

### Problem 6 — SetFit was misaligned

SetFit was trained on a stale label set (no `troubleshooting_cant_receive_otp`)
and the encoder file was 470 MB. Maintenance cost > value, especially since
LLM-only routing with Flash-Lite is fast and free of label drift.

**Fix:**
- Removed `model/setfit_router/` (encoder + tokenizer, 487 MB) from the repo
  scope. The training script and `head.pkl` are kept so SetFit can be retrained
  if ever needed.
- Router falls back gracefully when the model isn't loaded — `setfit_router.predict()`
  returns `None`, the router calls the LLM directly.

### Problem 7 — `is_new=True` paraphrases nuking troubleshooting context

The LLM router classified each variation of "still not working" (`ยังเจออยู่`,
`เจออยู่`, `บอก hr แล้ว…`) as a fresh topic. The orchestrator's topic-shift
code wiped active_ctx → `retry_count` reset to 0 every turn → handoff loop
never reached MAX.

**Fix (`pipeline/orchestrator.py:322`):**
```python
same_troubleshooting_topic = (
    decision.route == Route.TROUBLESHOOTING
    and active_ctx.get("intent") == "troubleshooting"
    and active_ctx.get("sub_type") == decision.template_key
)
if same_troubleshooting_topic and decision.is_new:
    decision.is_new = False   # keep retry_count alive
```

### Problem 8 — `save_troubleshooting_context` overwriting `retry_count`

Every recheck called `save_troubleshooting_context()`, which built a fresh
dict with no retry_count → counter wiped. Compounding with Problem 7, the
counter was being reset by two mechanisms.

**Fix (`memory/active_context.py`):** when the saved sub_type matches the
existing one, preserve `retry_count` and `handoff_reason` from the existing
context instead of overwriting.

### Problem 9 — Auto-handoff felt aggressive

Original v3 design auto-escalated after MAX retries. Users wanted to stay in
control of when to talk to a human.

**Fix — user-controlled handoff:**
- `MAX_TROUBLESHOOTING_RETRIES = 3` is now a **threshold for revealing the
  transfer button**, not for auto-escalation.
- After 3 unresolved attempts, the confirmation prompt extends to 3 options:
  - แก้ไขเรียบร้อยแล้ว
  - ยังพบปัญหาอยู่
  - ต้องการโอนไปให้เจ้าหน้าที่ช่วย ← shown only when retry_count ≥ MAX
- Resolver detects handoff-request phrases (`ต้องการโอน`, `ติดต่อเจ้าหน้าที่`,
  `คุยกับคน`, `talk to agent`) → `TRIGGER_HANDOFF` with reason
  `user_requested_handoff` → orchestrator escalates immediately.
- Bot never auto-escalates from troubleshooting; only the user can opt in.

### Problem 10 — Compound messages mis-classified by resolver

`_is_yes/no/end` did substring matching, so "เข้ามาได้แล้ว ถอนเงินยังไงหรอ"
matched `ได้แล้ว` and triggered END_FLOW, discarding the actual question.

User rejected adding question-marker word lists ("doesn't scale").

**Fix — length-based heuristic (`pipeline/context_resolver.py`):**
Pure resolution signals are short by nature ("ครับ", "ขอบคุณ", "ได้แล้ว").
`_is_pure_signal()` returns True only when message ≤ 20 chars. Above that,
hand off to the LLM router which sees full context.

### Problem 11 — Handoff summary returning garbage

Gemini Flash thinking with `max_tokens=300` was eating the budget, output
truncated to "• ปัญหา: ลูกค้า" (random word from somewhere).

**Fix (`pipeline/handoff.py`):**
- Added `_SUB_TYPE_TOPIC_TH/EN` map → human-readable topic per sub_type.
- `_topic_label()` looks up sub_type → label, falls back to `topic` / `remark`.
- `_fallback_summary()` is now deterministic: "• ปัญหา: <topic from map>"
  with optional `last_root_cause` and `retry_count` bullets.
- LLM still tries first (`max_tokens=1024`, output validated), but the
  deterministic builder is the safety net — guaranteed correct even on
  truncation.

### Problem 12 — Wrong image attached to LLM-generated answer

When retrieval returned a wrong-but-plausible article, the LLM would write a
correct novel answer (e.g. "Download from App Store") but the orchestrator
attached the **top doc's image** (e.g. "ประวัติเบิกเงิน" screenshot) — image
unrelated to the answer.

**Fix:** `_answer_uses_doc()` — character 5-gram overlap between answer and
top doc's answer. Only attach image when overlap ≥ 30%. Robust for Thai
since char n-grams don't need word boundaries.

### Problem 13 — Pin not firing on followups + duplicate confirmation prompts

The pinned-FAQ shortcut originally only fired in `_run_faq` (new-query path).
Followups (`is_new=False`) bypassed the pin and went through vector search,
returning whichever article the catalog happened to surface.

Separately: `append_confirmation()` was being called both inside
`_run_troubleshooting_staged` AND in the orchestrator post-processing block,
producing the prompt twice in the same answer.

**Fix:**
- Pin shortcut moved upstream of `is_new` branching — fires whenever a
  troubleshooting_* label has a registered article in
  `_TROUBLESHOOTING_FAQ_TITLES`.
- `append_confirmation()` is now idempotent: returns the text unchanged if
  the marker (`รบกวนแจ้งผลให้ทราบ`) is already present.

---

## v3 Architecture (current)

```
USER MESSAGE
   ↓
Resolver  ──► explicit handoff phrase?     → TRIGGER_HANDOFF (user_requested)
              awaiting_confirmation?       → END_FLOW / TRIGGER_HANDOFF / NEW
              short pure signal?           → END_FLOW / TRIGGER_HANDOFF
              else                         → NEW
   ↓
LLM Router  (Gemini Flash, max_tokens=1024 to survive thinking budget)
   ↓
is_new override: same troubleshooting sub_type → force is_new=False
   ↓
PIN SHORTCUT  ──► label in _TROUBLESHOOTING_FAQ_TITLES?
                  → exact-title lookup in cached catalog → return article + image
   ↓ (no pin)
Path execution
   • is_new=False + troubleshooting/faq active → _run_troubleshooting_recheck or
     _run_faq_followup (retry_count incremented for troubleshooting)
   • route=CHITCHAT/MISSING_INFO → template
   • route=TROUBLESHOOTING + is_new=True → _run_troubleshooting_new (live API)
   • else → _run_faq
        ├── vector + BGE rerank
        ├── LLM smart rerank (gray zone or close-call)
        ├── BGE full-scan over whole catalog (LLM picker on top-5)
        └── BGE-trust safety net when LLM rejects but BGE top ≥ 0.45
   ↓
Post-processing
   • TROUBLESHOOTING + not escalated → append_confirmation
       with_transfer = retry_count >= MAX_TROUBLESHOOTING_RETRIES
   • image attach gated on n-gram overlap with top doc
   • not fallback / not "ขออภัย" → save active context, persist turn
```

---

## v3 Files Changed

```
config/tenants.yaml                    company_id mapping fix + excluded_source_types
indexers/index_solutions.py            wipe-and-rebuild collections; respect excluded_source_types
rag/retriever.py                       read collection from tenants.yaml vector_collections
pipeline/router.py                     non-withdrawal troubleshooting → FAQ route; max_tokens 1024
pipeline/context_resolver.py           length-based pure-signal heuristic; _is_handoff_request
pipeline/orchestrator.py               pin shortcut, hybrid retrieval pipeline, retry loop, with_transfer
pipeline/handoff.py                    deterministic summary builder + _SUB_TYPE_TOPIC_*
memory/active_context.py               save_troubleshooting_context preserves accumulators
llm/templates.py                       formal confirmation prompt; idempotent append_confirmation;
                                       _CONFIRMATION_*_WITH_TRANSFER variant
agent/planner.py                       _TOOL_STRATEGY simplified (only withdrawal active)
data/faqs/solutions_faq.csv            withdrawal-how-to synonym rows; OTP/money image content
model/setfit_router/                   removed (470 MB); kept training script for future use
```

