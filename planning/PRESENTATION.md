# CS Chatbot Agent — Architecture

---

## Request Router (LLM-based)

```
User message
      │
 Fast LLM (configurable via LLM_PROVIDER, max_tokens=250, ~150ms)
 + active context from Redis (topic, remark, last_root_cause)
      │
 Returns JSON: { intent, conv_state, followup_type, confidence, reason }
      │
 PRIORITY RULES:
   1. greeting/thanks/goodbye/frustrated/confused → always CHITCHAT, ignore active context
   2. troubleshooting_recheck only for explicit recheck phrases
   3. troubleshooting_withdrawal for zero balance / can't withdraw
   4. faq for general questions
      │
  ┌───────────────┬────────────────┬────────────────────────────┐
  │   CHITCHAT    │  MISSING_INFO  │     TROUBLESHOOTING        │
  │               │                │                            │
  │  greeting     │  missing_info  │  troubleshooting_          │
  │  thanks       │                │  withdrawal                │
  │  goodbye      │                │  (add more subtypes here)  │
  │  frustrated   │                │                            │
  │  confused     │                │                            │
  └───────────────┴────────────────┴────────────────────────────┘
                                               │
                                       sub_type → tool strategy
                                       evidence.py → root_cause
                                       answer_templates.yaml
                             ┌─────────────────┴──────┐
                             │          FAQ            │
                             │   Vector DB search      │
                             │   → rerank → LLM answer │
                             └─────────────────────────┘
```

| Detail | |
|--------|---|
| **Primary** | LLM classifier — handles Thai, English, mixed language, typos, active context |
| **Fallback** | Keyword matching — used if LLM call fails |
| **Priority rule** | Greetings/chitchat always override active context (no false recheck) |
| **Chitchat labels** | `greeting / thanks / goodbye / frustrated / confused` → CHITCHAT |
| **Missing info label** | `missing_info` → MISSING_INFO |
| **Troubleshooting labels** | `troubleshooting_withdrawal` → TROUBLESHOOTING (add more subtypes in `_TS_TOPIC`) |
| **Conv state** | `new_query` / `followup` / `ambiguous` — drives multi-turn path |
| **Followup type** | `faq_followup` / `troubleshooting_recheck` / `null` |

---

## Chitchat & Missing Info

```
Router label (e.g. "greeting")
      │
 get_chitchat_template(label, language)
      │  reads config/chitchat_templates.yaml
      │
 Return template text directly — no LLM, no retrieval
```

**`config/chitchat_templates.yaml`** — edit this file to change any chitchat response:

| Key | Thai | English |
|-----|------|---------|
| `greeting` | สวัสดีค่ะ ยินดีให้บริการค่ะ... | Hello! How can I help... |
| `thanks` | ยินดีให้บริการค่ะ... | You're welcome!... |
| `goodbye` | ลาก่อนค่ะ... | Goodbye!... |
| `frustrated` | ขอโทษสำหรับความไม่สะดวกค่ะ... | I'm sorry to hear... |
| `confused` | ขอโทษที่ทำให้งงนะคะ... | Sorry for the confusion!... |
| `missing_info` | กรุณาบอกรายละเอียดเพิ่มเติม... | Could you share more detail?... |

> **Note — FAQ → missing_info fallback:** when FAQ retrieval finds no relevant results, it currently escalates to HR handoff. A "ask clarifying question first" flow will be added when chat history is implemented.

---

## Offline Data Pipeline

```
CSV Files (public FAQ + company-specific)
      │
 Merge by tenant + language
      │
 Clean & Normalize
 (lowercase, whitespace, Thai synonyms)
      │
 Embed (SentenceTransformer, 384-dim, cached)
      │
 Upsert to Qdrant
 collection: {company}_{lang}
```

| Step | Detail |
|------|--------|
| **Data sources** | `data/faqs/public_faq.csv` + `data/company/{tenant}/` |
| **Merge** | `indexers/merge_data.py` → `data/merged/{company}_{lang}.csv` |
| **Embedding model** | `distiluse-base-multilingual-cased-v2` — Thai + English, MPS-accelerated |
| **Vector store** | Qdrant (primary) / Pinecone (fallback), collection per tenant × language |
| **Reindex** | `/qdrant reindex hns th` — delete + rebuild from scratch |

---

## FAQ Pipeline (online)

```
User Question
      │
 Clean Query
 (lowercase, whitespace, Thai synonyms)
      │
 Embed (cached LRU 500)
      │
 Qdrant Search (top 5)
      │
 BGE Reranker (top 5, threshold 0.3)
      │
 Build Context
      │
 LLM → generate answer (configurable via LLM_PROVIDER)
      │
 Grounding Check (word-overlap score)
      │
 score == 0.0 (LLM failed)?        → Human Handoff  ← always
 score < 0.25 AND retrieval < 0.4? → Human Handoff  ← weak match
      │
 Return Answer
```

| Step | Detail |
|------|--------|
| **Query cleaning** | `rag/query_cleaner.py` — removes punctuation, maps synonyms, preserves Thai combining chars |
| **Embedding cache** | LRU 500 entries — identical queries skip re-embedding |
| **Reranker** | `BAAI/bge-reranker-base` — sigmoid scoring, filters weak matches below 0.3 |
| **Grounding check** | Word-overlap heuristic between answer and retrieved context |
| **Escalation gate** | Escalates if: (grounding < 0.25 **and** retrieval < 0.4) **or** grounding == 0.0 (LLM error) |
| **Answer cleaning** | `_clean_answer()` strips LLM preamble boilerplate ("จากข้อมูล...", "ตามข้อมูล...") |

---

### Test results — FAQ questions (Thai)

Run: `PYTHONPATH=. python scripts/test_faq.py --tenant hns --lang th`

```
#    Question                                   Score   Answer preview
──────────────────────────────────────────────────────────────────────────────────────

  ── การเบิกเงิน (Withdrawal) ──

 1   เบิกเงินได้ตั้งแต่กี่โมงครับ              1.00    เบิกเงินได้ตลอด 24 ชั่วโมง ทุกวันไม่เว้นวันหยุด
 2   เบิกได้กี่ครั้งต่อเดือนคะ                1.00    เบิกได้สูงสุด 5 ครั้งต่อเดือน
 3   เบิกได้สูงสุดเท่าไหร่                    0.90    50% ของวันทำงานจริง แต่ไม่เกิน 25,000 บาทต่อรอบ
 4   เบิกขั้นต่ำต้องกี่บาทครับ               0.50    เบิกขั้นต่ำต้อง 500 บาทครับ
 5   วันหยุดเสาร์อาทิตย์เบิกเงินได้ไหมคะ     0.62    สามารถเบิกเงินในวันหยุดเสาร์อาทิตย์ได้ค่ะ
 6   เบิกได้ถึงวันที่เท่าไหร่ของเดือน         1.00    รอบ 16-15 เบิกได้วันที่ 23–15 / รอบ 21-20, 26-25 เบิกได้วันที่ 1–20
 7   เบิกแล้วเงินเข้าบัญชีไหนครับ             0.91    บัญชีเงินเดือนที่บริษัทจ่ายปกติ ภายใน 24 ชั่วโมง
 8   กดเบิกไปแล้วแต่เงินยังไม่เข้าเลย        0.55    รอไม่เกิน 24 ชั่วโมง หากเกินให้แจ้งแอดมินทันที
 9   เงินไม่เข้ามาเกิน 1 วันแล้ว ต้องทำอะไรคะ 0.42   ตรวจสอบกะ / check-in / ติดต่อแอดมิน
10   อยากเปลี่ยนบัญชีรับเงิน ทำได้ไหม         0.67    ติดต่อ HR พร้อมเตรียมเลขบัญชีใหม่และสำเนาสมุดบัญชี
```

**Observations from sample run:**

| # | Issue | Note |
|---|-------|------|
| Q5 | Score 0.62 — answer added citation "ตามที่ระบุไว้ในคำตอบข้อที่ 1 ว่า..." | `_clean_answer()` not catching this pattern yet |
| Q8 | Score 0.55 — answer added "[1]" / "[2]" reference markers | Same issue — LLM citing context index |
| Q9 | Score 0.42 — answer synthesised from 3 weak hits | Correct action but grounding score low; not escalated because retrieval score > 0.6 |

---

## Troubleshooting Agent

```
User: "ทำไมเบิกเงินไม่ได้ครับ"
        │
    Router → "troubleshooting_withdrawal"
        │
    sub_type → tool strategy (deterministic):
        │
  troubleshooting_withdrawal  →  get_employee_data + get_attendance
  (add more: register in _TS_TOPIC in orchestrator.py + _LABEL_TO_ROUTE in router.py)
        │
  ┌─ get_employee_data ──────────────────────────────────────┐
  │  • profile          → blacklisted? suspended? status?     │
  │  • sync schedule    → sync pending?                       │
  │  • deductions       → itemised deduction list             │
  │  • paycycle dates   → start_date used for attendance      │
  └──────────────────────────────────────────────────────────┘
        │
  ┌─ get_attendance (if strategy includes it) ───────────────┐
  │  Date range: paycycle.start_date → today                  │
  │  (fallback: last 7 days if paycycle unavailable)          │
  │  Returns attendance records → check remarks               │
  └──────────────────────────────────────────────────────────┘
        │  (more tools: add to _TOOL_STRATEGY in planner.py)
        │
  evidence.py → build_diagnostic_context()
        │
  Root cause identified
  (blacklisted → suspended → sync_pending → ok)
        │
  ┌─ Blocking issue? ────────────────────────────────────────┐
  │  blacklisted / suspended / sync_pending                   │
  │  → answer_templates.yaml fills template directly          │
  │  → Return answer  ← LLM NOT involved                     │
  └──────────────────────────────────────────────────────────┘
        │
  ┌─ No blocking issue (ok) ─────────────────────────────────┐
  │  → diagnostic_context passed to answer_generator          │
  │  → LLM synthesises answer from deductions, remarks, etc.  │
  │  → Return answer  ← LLM involved                         │
  └──────────────────────────────────────────────────────────┘
```

| Step | Detail |
|------|--------|
| **Router sub-type** | LLM classifies into `troubleshooting_withdrawal` (more added via `_TS_TOPIC`) |
| **Tool strategy** | Deterministic per sub-type — no ReAct agent, no Sonnet needed for diagnosis |
| **get_employee_data** | Always called — profile, sync, deductions, paycycle in one API call |
| **get_attendance** | Called only when sub-type needs it (withdrawal / attendance) |
| **Root cause priority** | blacklisted → suspended → sync_pending → ok |
| **Blocking issues** | Always use deterministic template — consistent, no hallucination risk |
| **Ok path** | LLM generates answer from full diagnostic context — handles nuanced cases (deductions, remarks) |
| **Add new tool** | Add entry to `_TOOL_STRATEGY` in `agent/planner.py` — no other changes needed |
| **Mock clients** | `USE_MOCK_APIS=true` loads from `users.json` — 6 employees, 6 scenarios |

### Root causes & templates

| Root cause | Trigger | Template tells user |
|------------|---------|---------------------|
| `blacklisted` | `blacklisted: true` | Contact HR to remove blacklist |
| `suspended` | `status: suspended` | Contact HR to reactivate account |
| `status_inactive` | `status: inactive` (or any non-active) | Contact HR to update status to active |
| `sync_pending` | `sync_status: pending` | Wait for nightly sync / ask HR for manual sync |
| `ok` + remarks | Attendance remarks present | Shows attendance table with missing punches / remarks |
| `ok` + deductions | Deduction items present | Shows itemised deductions |
| `ok` (clean) | No issues found | All normal — try closing and reopening the app |

---

### Test results — mock scenarios (`users.json`)

Tested against 6 mock employees covering all root cause paths.
Run: `USE_MOCK_APIS=true PYTHONPATH=. python scripts/test_troubleshooting.py`

```
#    Employee  Issue                         Root cause      Pass?
─────────────────────────────────────────────────────────────────
 1   EMP004    ยอด 0 บาท เบิกเงินไม่ได้      sync_pending    ✅
 2   EMP004    แสดงผล 0 ทำไม                 sync_pending    ✅
 3   EMP004    ยอดไม่ขึ้นเลยครับ             sync_pending    ✅
 4   EMP005    เบิกไม่ได้ครับ                blacklisted     ✅
 5   EMP005    เงินไม่ขึ้น บัญชีมีปัญหา      blacklisted     ✅
 6   EMP002    ทำไมเบิกเงินไม่ได้            status_inactive ✅
 7   EMP003    เบิกเงินไม่ได้เลย             ok (remarks)    ✅
 8   EMP003    ทำไมเช็คอินไม่ขึ้น            ok (remarks)    ✅
 9   EMP006    ทำไมเบิกเงินไม่ได้            ok (clean)      ✅
10   EMP006    ยอดเงินเป็น 0 ครับ            ok (clean)      ✅
11   EMP001    ทำไมยอดไม่อัปเดต              ok (clean)      ✅
12   EMP001    หักเงินเท่าไหร่               ok (clean)      ✅

Total: 12  |  Passed: 12  |  Failed: 0  |  Accuracy: 100%
```

**Full 1-1 chat results — all 6 employees:**

---

**EMP001** — สมชาย ใจดี | `root_cause: ok` | template: `normal_active`
```
User: ทำไมยอดไม่อัปเดต

Bot:  ตรวจสอบข้อมูลของ สมชาย ใจดี แล้ว ทุกอย่างปกติค่ะ ไม่พบปัญหาที่ขัดขวางการเบิกเงิน

      หากยังเบิกไม่ได้ ลองทำตามนี้:
      - ปิดแอปแล้วเปิดใหม่เพื่อรีเฟรชยอดเงิน
      - ตรวจสอบว่ามีสัญญาณอินเทอร์เน็ต
      - หากยังมีปัญหา ติดต่อแอดมิน Salary Hero ได้เลยค่ะ
```

---

**EMP002** — วิไล รักงาน | `root_cause: status_inactive` | template: `status_inactive`
```
User: ทำไมเบิกเงินไม่ได้

Bot:  บัญชีของ วิไล รักงาน มีสถานะ "inactive" อยู่ในขณะนี้ จึงไม่สามารถเบิกเงินได้ค่ะ

      กรุณาติดต่อฝ่าย HR เพื่อตรวจสอบและอัปเดตสถานะบัญชีให้เป็น active
      เมื่อ HR อัปเดตสถานะแล้ว รอระบบซิงค์ข้อมูล (ปกติภายในคืนนั้น) ก็จะเบิกเงินได้ค่ะ
```

---

**EMP003** — ประยุทธ์ มีสุข | `root_cause: ok` | template: `attendance_remark`
```
User: เบิกเงินไม่ได้เลย

Bot:  พบรายการเข้า-ออกงานที่ไม่สมบูรณ์ของ ประยุทธ์ มีสุข ซึ่งอาจเป็นสาเหตุให้ยอดเงินไม่ถูกต้องค่ะ

        24 มี.ค. 2026  เข้า 08:50 น. / ออก 18:00 น.
        25 มี.ค. 2026  เข้า — / ออก 18:05 น.  ⚠️ ลืม check in
        26 มี.ค. 2026  เข้า 09:00 น. / ออก —  ⚠️ ลืม check out
        27 มี.ค. 2026  เข้า — / ออก —  ⚠️ บัตรพนักงานเสีย — HR บันทึกให้
        28 มี.ค. 2026  เข้า 08:55 น. / ออก 18:00 น.

      ระบบคำนวณยอดเงินจากข้อมูล check-in / check-out หากมีรายการที่ขาดหายหรือมีหมายเหตุค้างอยู่
      ยอดที่แสดงอาจไม่ถูกต้อง

      วิธีแก้ไข:
      - แจ้ง HR ให้ตรวจสอบและแก้ไขรายการที่มี — หรือ ⚠️
      - เมื่อ HR บันทึกข้อมูลแล้ว รอระบบซิงค์คืนนั้น ยอดเงินจะอัปเดตค่ะ
```

---

**EMP004** — นภาพร ทองดี | `root_cause: sync_pending` | template: `sync_pending`
```
User: ยอด 0 บาท เบิกเงินไม่ได้

Bot:  ยอดเงินของ นภาพร ทองดี ยังไม่อัปเดตเพราะข้อมูลเงินเดือนอยู่ระหว่างการซิงค์ค่ะ

      - ซิงค์ล่าสุด: 20 มี.ค. 2026 เวลา 02:00 น.
      - ซิงค์ถัดไป: ยังไม่มีกำหนด

      รอระบบซิงค์ข้อมูลอัตโนมัติ หลังจากนั้นยอดเงินจะขึ้นและเบิกได้ทันที
      หากรอไม่ได้ แจ้ง HR หรือแอดมินเพื่อทำ sync ด่วนได้เลยค่ะ
```

---

**EMP005** — กิตติ แสนดี | `root_cause: blacklisted` | template: `blacklisted`
```
User: เบิกไม่ได้ครับ

Bot:  บัญชีของ กิตติ แสนดี ถูกระงับการใช้งานชั่วคราว (blacklist) จึงไม่สามารถเบิกเงินได้ในขณะนี้ค่ะ

      กรุณาติดต่อฝ่าย HR โดยตรงเพื่อตรวจสอบสาเหตุและขอให้ปลด blacklist
      เมื่อ HR ปลดแล้ว จะสามารถเบิกเงินได้ทันทีในรอบถัดไปค่ะ
```

---

**EMP006** — มานะ ตั้งใจ | `root_cause: ok` | template: `normal_active`
```
User: ทำไมเบิกเงินไม่ได้

Bot:  ตรวจสอบข้อมูลของ มานะ ตั้งใจ แล้ว ทุกอย่างปกติค่ะ ไม่พบปัญหาที่ขัดขวางการเบิกเงิน

      หากยังเบิกไม่ได้ ลองทำตามนี้:
      - ปิดแอปแล้วเปิดใหม่เพื่อรีเฟรชยอดเงิน
      - ตรวจสอบว่ามีสัญญาณอินเทอร์เน็ต
      - หากยังมีปัญหา ติดต่อแอดมิน Salary Hero ได้เลยค่ะ
```

---

## Multi-turn Conversation Architecture

> All interfaces (Gradio, LINE webhook) call `pipeline/orchestrator.py → handle_message()` as the single entry point.

### Full Request Flow

```
User sends message
        │
        ▼
1. Session check (Redis)
   key: chat:session:{tenant}:{user}
   - same session? continue
   - expired? start new session
             session continuity resets
             active context, summary, and cache follow their own TTL rules
        │
        ▼
2. Load memory from Redis
   - History:        chat:history:{tenant}:{user}:{lang}   → last 3–5 turns
   - Summary:        chat:summary:{tenant}:{user}:{lang}   → recap of older turns
   - Active context: chat:context:{tenant}:{user}          → current topic / open case / remark
   - Context cache:  chat:cache:{tenant}:{user}            → last FAQ docs / last diagnosis
        │
        ▼
3. Router  (fast LLM — Haiku / Gemini Flash)
   Input:
   - current user message
   - short history (last 3 turns)
   - summary
   - active context  ← includes topic, remark, last_user_need, last_root_cause

   Router outputs:
   ┌─────────────────────────────────────────────────────────┐
   │  intent:      faq / troubleshooting / chitchat /        │
   │               missing_info                              │
   │                                                         │
   │  conv_state:  new_query                                 │
   │               followup  →  faq_followup                 │
   │                         →  troubleshooting_recheck      │
   │               ambiguous  →  resolve to followup         │
   │                          →  or escalate to missing_info │
   │                                                         │
   │  confidence:  0.0 – 1.0                                 │
   │  reason:      short explanation string                  │
   └─────────────────────────────────────────────────────────┘
        │
        ├──────────────────────────────────────────────┐
        │                                              │
        ▼                                              ▼
4A. conv_state = followup / ambiguous             4B. conv_state = new_query
        │                                              │
        ├── faq_followup                               ├── chitchat / greeting
        │   e.g. "ผมใช้ iOS"                           │   → YAML template, no LLM
        │   - load active context (topic + remark)     │
        │   - update remark with new detail            ├── FAQ
        │   - rerun retrieval if follow-up changes:    │   → vector search
        │       platform / company / product /         │   → rerank
        │       policy target / date scope /           │   → LLM answer
        │       issue subtype                          │   → grounding check
        │   - reuse cache otherwise                    │
        │     ("ครับ" / "ขอลิงก์อีกที" → no rerun)    ├── Troubleshooting
        │                                              │   → fetch live API data
        ├── troubleshooting_recheck                    │   → deterministic diagnosis
        │   e.g. "แจ้ง HR แล้ว ฝากเช็คอีกที"           │   → template or LLM answer
        │   - load active case + employee_id + remark  │
        │   - call live API again (always)             └── Missing info
        │   - compare new vs old root_cause                → ask only for the one
        │     fixed     → "ตอนนี้ปกติแล้วค่ะ"               missing piece needed
        │     not fixed → "ยังพบปัญหาอยู่..."
        │
        └── ambiguous
            e.g. "ตอนนี้ล่ะ" / "แล้วไงต่อ"
            - active context exists + confidence >= 0.7
              → resolve to faq_followup or troubleshooting_recheck
            - active context exists + confidence < 0.7
              → ask one targeted clarification
                "ต้องการให้เช็กเรื่องการถอนเงินต่อ หรือถามเรื่องอื่นครับ?"
            - no active context
              → escalate to missing_info
        │
        ▼
5. Pipeline execution

   FAQ:
   - build query from topic + remark in active context
   - retrieve docs (skip if cache valid and remark unchanged)
   - rerank
   - LLM answer with grounded context
   - grounding < 0.25 AND retrieval < 0.4 → HR handoff

   Troubleshooting:
   - load active case + employee_id from active context
   - fetch latest data from live API  ← always, Redis is context not business truth
   - diagnose root cause
   - blocking issue → deterministic template
   - ok path → LLM synthesis from diagnostic context
   - unclear → ask precise follow-up or HR handoff

   Chitchat:
   - YAML template lookup, return immediately

   Missing info:
   - identify exactly what is missing
   - ask one targeted clarification question
        │
        ▼
6. Final answer → user
        │
        ▼
7. Update Redis  (non-blocking where possible)

   save_turn()            → append user + bot messages to history
   update_summary()       → background thread, refresh rolling recap
   save_active_context()  → overwrite with latest topic / remark / root_cause
   save_context_cache()   → save last FAQ docs or last diagnosis result
   refresh session TTL    → reset 30 min idle timer
```

---

### Redis Key Structure

| Key | Purpose | TTL |
|-----|---------|-----|
| `chat:session:{tenant}:{user}` | Session continuity window | 30 min idle |
| `chat:history:{tenant}:{user}:{lang}` | Last 3–5 raw turns | 7 days |
| `chat:summary:{tenant}:{user}:{lang}` | Rolling 2–3 sentence recap | 7 days |
| `chat:context:{tenant}:{user}` | Active topic / case / remark / status | 30 min (troubleshooting) · 1 day (FAQ) |
| `chat:cache:{tenant}:{user}` | Last FAQ doc IDs or last diagnosis | 2 hours |

---

### Router Output Schema

```json
{
  "intent": "faq",
  "conv_state": "followup",
  "followup_type": "faq_followup",
  "confidence": 0.91,
  "reason": "message refers to previous active topic and changes platform detail"
}
```

**All valid combinations:**

| intent | conv_state | followup_type |
|--------|-----------|---------------|
| `faq` | `new_query` | `null` |
| `faq` | `followup` | `faq_followup` |
| `troubleshooting` | `new_query` | `null` |
| `troubleshooting` | `followup` | `troubleshooting_recheck` |
| `chitchat` | `new_query` | `null` |
| `missing_info` | `new_query` | `null` |
| `missing_info` | `ambiguous` | `null` |

---

### Active Context Shape

**FAQ**
```json
{
  "intent": "faq",
  "topic": "download_app",
  "remark": "user clarified they use iOS",
  "last_user_need": "iOS app download link",
  "status": "active",
  "updated_at": "2026-04-20T10:30:00+07:00"
}
```

**Troubleshooting**
```json
{
  "intent": "troubleshooting",
  "topic": "withdrawal_issue",
  "sub_type": "troubleshooting_withdrawal",
  "employee_id": "12345",
  "remark": "user asked to recheck after contacting HR",
  "last_root_cause": "incomplete_attendance",
  "status": "active",
  "updated_at": "2026-04-20T10:35:00+07:00"
}
```
`sub_type` = the agent API key to call on recheck — stored directly so no reverse-mapping needed.

`status` values: `active` · `resolved` · `stale`

---

### Active Context Overwrite Rules

**FAQ**

| Field | Rule |
|-------|------|
| `topic` | Keep if same FAQ thread. Overwrite if new topic detected |
| `remark` | Always overwrite with latest user detail |
| `last_user_need` | Overwrite only if user clarified further |
| `status` | Set `active` on new query. Set `resolved` when goodbye/thanks detected |

**Troubleshooting**

| Field | Rule |
|-------|------|
| `employee_id` | Never overwrite — set once, kept for session lifetime |
| `topic` | Keep if same case. Overwrite if new issue raised |
| `remark` | Always overwrite with latest user message context |
| `last_root_cause` | Overwrite only after fresh API diagnosis completes |
| `status` | `active` → `resolved` when API confirms fixed · `stale` if session expires |

---

### FAQ Cache Validity Rules

**Reuse cache if ALL true:**
- same topic as active context
- same tenant / company scope
- remark change does NOT affect: platform, product, company, policy target, date scope, issue subtype
- cache age < 2 hours
- doc IDs present in cache

**Force rerun retrieval if ANY true:**
- topic changed
- company or tenant changed
- remark changes: platform, product, date range, issue subtype
- cache missing or expired

**Troubleshooting — always call live API:**
- never reuse diagnosis cache as business truth
- cache only used to show previous result for delta comparison

---

### Example Flows

#### Flow 1 — FAQ multi-turn

```
Turn 1
  User:   ฉันสามารถดาวน์โหลดแอปได้ที่ไหน
  Router: new_query · intent=faq · topic=download_app
  Bot:    returns generic app download answer
  Redis:  save active context { topic: download_app, remark: "user asked where to download" }

Turn 2
  User:   ผมใช้ iOS
  Router: followup · faq_followup · confidence=0.88
          remark changed → platform change → rerun retrieval
  Bot:    returns iOS-specific download link
  Redis:  update remark to "user clarified they use iOS"
```

#### Flow 2 — Troubleshooting recheck

```
Turn 1
  User:   ทำไมถอนเงินไม่ได้
  Router: new_query · intent=troubleshooting
  Bot:    fetch API → incomplete_attendance → show attendance table
  Redis:  save { topic: withdrawal_issue, last_root_cause: incomplete_attendance }

Turn 2
  User:   แจ้ง HR แล้ว ฝากเช็คให้อีกทีครับ
  Router: followup · troubleshooting_recheck · confidence=0.93
  Bot:    call API again → compare with previous root_cause
          fixed     → "ตอนนี้ทุกอย่างปกติแล้วค่ะ"
          not fixed → "ยังพบปัญหาในวันที่..."

Turn 3
  User:   ตอนนี้เป็นปกติหรือยัง
  Router: ambiguous · confidence=0.71 → active context exists → troubleshooting_recheck
  Bot:    call API again → answer with latest status
```
