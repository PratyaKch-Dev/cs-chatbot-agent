# User Profile API — Diagnosis Spec

**Status:** design — not yet implemented
**Endpoint:** `GET /api/v1/user/account/chatbot/profile`
**Auth:** `Authorization: Bearer {access_token}` — BE derives `user_id` from the token (FE must never send `user_id`).

---

## User story

> As a chatbot agent, I need to call the User Profile API using the `access_token` from mobile so that I can retrieve real user data and diagnose issues (e.g. cannot withdraw) without relying on mock data.

Replaces `MockEmployeeDataClient` with `EmployeeDataClient` for the troubleshooting agent's first tool call.

---

## When this is called

Troubleshooting agent fires this first whenever the router emits
`troubleshooting_withdrawal`. Common user inputs:

- "ยอดเป็น 0"
- "เบิกไม่ได้"
- "ทำไมเบิกไม่ได้"
- "เบิกแล้วเงินไม่เข้า"

It is **always** called before the attendance API.

---

## Request / response

### Request

```
GET /api/v1/user/account/chatbot/profile
Authorization: Bearer {access_token}
language: en | th
x-os-platform: ios | android | web
x-device-id: ...
x-app-version: 5.4.4
```

### Response (full contract)

```json
{
  "remaining_count": 0,
  "profile": {
    "user_id":    "1060062",
    "company_id": "563",
    "status":     "inactive",
    "metadata": {
      "remark": null
    }
  },
  "company": {
    "name":   "อรุณ บุญมา",
    "status": "active"
  },
  "bank_account": {
    "bank_code":       "011",
    "branch_name":     "",
    "account_name":    "Pratya three",
    "account_no":      "XXXXXX9058",
    "account_no_full": "1112479058",
    "bank_logo_url":   "https://d27npaycvagyws.cloudfront.net/banks/logo/TTB.png"
  },
  "paycycle": {
    "id":                   2171,
    "start":                "2026-03-25T17:00:00.000Z",
    "cutoff":               "2026-04-24T09:00:00.000Z",
    "end":                  "2026-04-25T16:59:59.999Z",
    "next_start":           "2026-04-26T16:59:59.999Z",
    "paycycle_status":      "active",
    "employee_data_status": "up_to_date"
  },
  "deductions": {
    "total_deducted":        1300.0,
    "deductions_updated_at": "2026-04-26T02:00:00.000Z"
  },
  "sync": {
    "sync_type": "manual",
    "schedules": []
  }
}
```

---

## Diagnosis fields

### Primary (drive root_cause logic)

| Field                                | Purpose                                    | Values                          |
|--------------------------------------|--------------------------------------------|---------------------------------|
| `remaining_count`                    | Withdraw eligibility                       | integer (≥ 0)                   |
| `paycycle.employee_data_status`      | Is the user's data fresh from the HRIS?    | `"up_to_date"` \| `"outdated"`  |
| `profile.status`                     | **Primary** account state                  | `"active"` \| `"inactive"`      |
| `deductions.total_deducted`    | Deduction issue                            | float (≥ 0)                     |
| `bank_account.bank_code`       | Bank existence (paired check)              | string or empty                 |
| `bank_account.account_no`      | Account existence (paired check)           | string or empty                 |
| `paycycle.paycycle_status`     | Paycycle validity                          | `"active"` \| `"inactive"`      |
| `paycycle.start`               | Window opens                               | ISO 8601 UTC                    |
| `paycycle.end`                 | Window closes                              | ISO 8601 UTC                    |
| `paycycle.cutoff`              | Withdrawal deadline within the window      | ISO 8601 UTC                    |

> **Note:** `bank_account.account_verify` is no longer used as a primary
> condition. A user passes the bank check as soon as `bank_code` AND
> `account_no` are both present — verification state isn't a withdrawal
> blocker per current BE rules.

### Supporting (free-text / display only)

| Field                                | Purpose                                                      |
|--------------------------------------|--------------------------------------------------------------|
| `profile.metadata.remark`            | Free-text reason / additional note from HR for the status    |
| `deductions.deductions_updated_at`   | When deductions were last refreshed — used in `has_deductions` template wording |
| `sync.sync_type`                     | Display only — `"manual"` \| `"auto"`                        |
| `sync.schedules`                     | Display only — list of sync timings (may be empty: `[]`)     |
| `balance.earned_avaliable_amount`    | **Informational** — how much the user can withdraw right now. Rendered as supporting copy ("ยอดเบิกได้ตอนนี้: 0 บาท"); never branched on. From the separate `/api/v1/user/ewa/balance/withdraw` endpoint that runs in parallel with the profile call. |
| `balance.status`                     | **Informational** — `"ready"` \| other. Shown as a label next to the amount; never branched on. |

---

## Decision tree (root_cause selection)

Evaluated in order; first match wins.

```
remaining_count > 0
    └── normal_active                          → "You can withdraw"

remaining_count == 0
    ├── profile.status == "inactive"
    │     → status_inactive
    │       (render profile.metadata.remark as supporting text when present;
    │        the template must read cleanly when remark is null)
    │
    ├── profile.metadata.remark is truthy      → has_remark
    │     (status is "active" but HR left a note explaining why this user
    │      can't withdraw — surface the remark to the user verbatim)
    │     Template: "ข้อมูลของคุณมีหมายเหตุจาก HR: {remark}
    │                ซึ่งอาจเป็นสาเหตุที่จำนวนเงินของคุณไม่อัปเดต ..."
    │
    ├── paycycle.paycycle_status == "inactive" → paycycle_inactive
    │     (the company's pay cycle is closed — withdrawal is structurally
    │      impossible regardless of data freshness or deductions, so check this
    │      before data_outdated)
    │
    ├── today not in [paycycle.start, paycycle.end]
    │                                          → outside_paycycle_window
    │     (paycycle is configured but the current date is before the window
    │      opens or after it closes — fail fast with a clear "wait until next
    │      cycle" message)
    │
    ├── today >= paycycle.cutoff
    │                                          → past_cutoff
    │     (within the paycycle window but past the daily/period cutoff time —
    │      withdrawals for this cycle are no longer accepted)
    │
    ├── paycycle.employee_data_status == "outdated"
    │                                          → data_outdated
    │     (BE hasn't synced the latest HRIS data yet — balance may be stale.
    │      Render sync.sync_type + sync.schedules as supporting info so the
    │      user knows when fresh data will arrive)
    │
    ├── deductions.total_deducted > 0          → has_deductions
    │     (render deductions_updated_at as "ข้อมูลล่าสุดเมื่อ ...")
    │
    ├── not bank_account.bank_code
    │     OR not bank_account.account_no       → no_bank
    │
    └── otherwise                              → ok
         (no profile-side blockers → call Attendance API next)
```

**Why this order:**
`status == "inactive"` is checked **first** because it represents an
unconditional account-level lock — even if the user has deductions or a
verified bank, none of that matters until the account is reactivated.
We collapse the previous `suspended` / `blacklisted` / `status_inactive`
template scenarios into one (`status_inactive`) because the BE now exposes
only a binary `active | inactive`. The specific reason is carried by the
free-text `profile.metadata.remark` field and rendered as supporting copy.

---

## Answer-template impact (`config/answer_templates.yaml`)

The decision-tree maps to the existing template scenarios. Updates needed:

| root_cause          | Existing template?      | Action                                                                          |
|---------------------|-------------------------|---------------------------------------------------------------------------------|
| `normal_active`     | ✓ keep                  | No change.                                                                      |
| `status_inactive`   | ✓ keep                  | **Add `{remark}` placeholder** (sourced from `profile.metadata.remark`) so the HR-provided reason renders when present, and the template still reads cleanly when it's null/empty. The previous separate `suspended` and `blacklisted` templates are now folded into this one. |
| `has_remark`        | ✗ **new**               | Add scenario — fires when `status == "active"` but `metadata.remark` is non-null and `remaining_count == 0`. Template surfaces the remark verbatim as the primary explanation, e.g. *"ข้อมูลของคุณมีหมายเหตุจาก HR: {remark} ซึ่งอาจเป็นสาเหตุที่จำนวนเงินของคุณไม่อัปเดต..."* |
| `data_outdated`     | ✗ **new**               | Add scenario — fires when `employee_data_status == "outdated"`. Template tells the user the HR data hasn't synced yet; render `sync.sync_type` + `sync.schedules` as supporting info so they know when fresh data will arrive. |
| `suspended`         | ⚠️ deprecate            | Keep the entry for backwards-compat but mark unused — BE no longer returns this status. Map to `status_inactive` if any legacy code hits it. |
| `blacklisted`       | ⚠️ deprecate            | Same as `suspended` — fold into `status_inactive`.                              |
| `has_deductions`    | ✓ keep                  | Already renders `total_deducted` — verify it formats the number with commas (e.g. `1,300 บาท`). Add `{deductions_updated_at}` as supporting text. |
| `no_bank`           | ✓ keep                  | Covers missing `bank_code` and/or `account_no`. **Verification state is no longer a trigger** — only existence matters. |
| `bank_unverified`   | ⚠️ deprecate            | Removed from decision tree — `account_verify` is no longer used as a blocker. Keep the YAML entry for backwards-compat but no code path reaches it. |
| `paycycle_inactive` | ✗ **new**               | Add scenario — short Thai/English template (`รอบจ่ายของบริษัทยังไม่เปิด...`). |
| `ok`                | ✓ keep                  | The agent then calls Attendance API for remarks/missing-punch detection.        |

**General notes for templates:**
- Mask `account_no` — render `XXXXXX9058`, never `account_no_full`.
- When `status_reason` is `null` or empty, the template must still read cleanly (no "(reason: null)" leaks).
- `sync.schedules` is shown as a *supporting* line only — never used as the headline cause.

---

## Chatbot flow

```
1. Receive access_token from mobile
2. set_token(access_token)
3. Call get_employee_data  (profile API)
4. Evaluate decision tree (above):
     - If root_cause is blocking (suspended / blacklisted / status_inactive /
       has_deductions / no_bank / bank_unverified / paycycle_inactive) →
       render the matching template; do NOT call Attendance API.
     - If root_cause is `ok` → call Attendance API with date range
       (date_from=paycycle.start, date_to=today) and continue diagnosis there.
5. Return the chosen template (TH / EN per user language).
```

---

## Acceptance criteria

- [ ] `EmployeeDataClient` replaces `MockEmployeeDataClient` whenever a Bearer token is provided.
- [ ] Token passed via `Authorization: Bearer {token}`.
- [ ] BE derives user from token — no `user_id` in the request payload or query.
- [ ] Response includes `profile.metadata.remark`; chatbot uses it as **supporting** info, never as primary logic.
- [ ] `status` is the **primary** logic field.
- [ ] Chatbot validates bank existence only — `bank_code` AND `account_no` both non-empty. **`account_verify` is no longer checked** (verification state is not a withdrawal blocker per current BE rules).
- [ ] New field `employee_data_status` is read and drives the `data_outdated` root_cause when its value is `"outdated"`.
- [ ] `deductions.deductions_updated_at` is rendered as supporting "data last refreshed at …" copy in the `has_deductions` template.
- [ ] `sync.schedules` is rendered as display-only supporting info (never as a root cause) and the template reads cleanly when it's an empty list `[]`.
- [ ] No silent fallback to mock data when token is present and BE returns an error — surface the error in the trace.
- [ ] `account_no` is masked in any UI output.
- [ ] Template for `status_inactive` includes a `{remark}` placeholder (from `profile.metadata.remark`) that degrades gracefully when the field is null/empty.
- [ ] New `has_remark` root_cause + template: fires when `status == "active"` AND `metadata.remark` is non-null AND `remaining_count == 0`. The remark is rendered verbatim and framed as the reason the balance isn't updating.
- [ ] `evidence.py` treats `status` as **binary** — only branch on `"active"` vs `"inactive"`; only branch on `metadata.remark` as a truthy/null **existence check**, never on its text content.
- [ ] Legacy `suspended` / `blacklisted` template scenarios are kept in `answer_templates.yaml` for backwards-compat but no code path reaches them (marked deprecated in comments).
- [ ] New template scenario `paycycle_inactive` is added to `config/answer_templates.yaml` (TH + EN).
- [ ] Numeric formatting in `has_deductions` template: `1,300 บาท` (comma-grouped).

---

## Tech notes

- **Schema is uniform across all tenants/companies** — the BE returns the same response shape for every company. Diagnosis logic, templates, and `EmployeeData` dataclass can be written once and used by all tenants without per-company branching.
- `status` is the primary logic — `profile.metadata.remark` is free-text and must not be used in `if` branches. Branch only on its existence (`truthy` vs `null/empty`), never on its content.
- `sync` is config-only; no runtime "last successful sync" field exists, so the template must phrase it as "your sync schedule" not "last sync".
- `schedules` is a **list** to support future multi-config (e.g. two sync windows per week).
- Mask sensitive data (`account_no`) before rendering. Use `account_no` (already masked) not `account_no_full`.
- Keep the response schema consistent across environments (dev / staging / prod). If a field is absent, evidence.py must default to a safe empty value (already handled by `EmployeeData` dataclass defaults).

---

## Out of scope (this spec)

- Attendance API integration — separate spec.
- Retry / circuit breaker policy for the BE call — current behaviour is a single 10s-timeout request; revisit if production traffic warrants.
- Multi-tenant token validation — BE is single source of truth.

---

## Implementation checklist (when ready)

1. `agent/evidence.py` — update `_identify_root_cause()` to read the new fields exactly as per the decision tree above; add `paycycle_inactive` to `RC_*` constants.
2. `config/answer_templates.yaml` — add `paycycle_inactive`; add `{status_reason}` placeholder to `status_inactive`; ensure number formatting in `has_deductions`.
3. `agent/clients/employee_data_client.py` — already calling the correct endpoint with the required headers; verify the response parses cleanly with the new field names.
4. `agent/clients/base.py` — confirm `EmployeeData` dataclass covers every field; add defaults if any are missing.
5. Update mock fixtures `agent/clients/mock/users.json` to mirror the real schema so dev/test stays consistent.
6. Add scenario rows in `scripts/test_troubleshooting.py` for each root_cause path.
