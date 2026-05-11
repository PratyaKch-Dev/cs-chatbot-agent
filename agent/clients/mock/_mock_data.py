"""
One-stop mock fixture for the three BE endpoints.

Edit the dicts below to test any scenario without hitting the real API.
Shape matches exactly what the BE returns from:
    GET /api/v1/user/account/chatbot/profile
    GET /api/v1/user/ewa/balance/withdraw
    GET /api/v1/user/account/chatbot/attendance

How to use:
  1. Make sure you're on the mock path (no Bearer token in Gradio,
     or USE_MOCK_APIS=true in .env).
  2. Edit a field below.
  3. Send a message in Gradio. The mock clients will read these dicts.

Common test scenarios — flip these to reproduce each root_cause:
  - status_inactive:        PROFILE["profile"]["status"] = "inactive"
  - has_remark:             PROFILE["profile"]["metadata"]["remark"] = "ลืม check out"
  - paycycle_inactive:      PROFILE["paycycle"]["paycycle_status"] = "inactive"
  - outside_paycycle:       PROFILE["paycycle"]["end"] = "2020-01-01T00:00:00Z"
  - past_cutoff:            PROFILE["paycycle"]["cutoff"] = "2020-01-01T00:00:00Z"
  - data_outdated:          PROFILE["paycycle"]["employee_data_status"] = "outdated"
  - has_deductions:         PROFILE["deductions"]["total_deducted"] = 1300; PROFILE["remaining_count"] = 0
  - no_bank:                PROFILE["bank_account"]["bank_code"] = ""; PROFILE["bank_account"]["account_no"] = ""
  - attendance_remark:      ATTENDANCE["records"][0]["metadata"]["remark"] = "ลืม check in"
  - balance not_ready:      BALANCE["status"] = "not_ready"

Hot reload note: changes are picked up on the NEXT mock client call —
no app restart required (re-imports the module).
"""

# ── 1. Profile API response (GET /api/v1/user/account/chatbot/profile) ──────
PROFILE: dict = {
    "remaining_count": 30,
    "profile": {
        "user_id":    "1060059",
        "company_id": "563",
        "status":     "active",           # "active" | "inactive"
        "metadata": {
            "remark": None,               # set to a string to trigger has_remark
        },
    },
    "company": {
        "name":   "Pratya",
        "status": "active",
    },
    "bank_account": {
        "bank_code":       "014",         # empty → no_bank
        "branch_name":     "",
        "account_verify":  "pending",     # informational only — not a blocker
        "account_name":    "Pratya Emp",
        "account_no":      "XXXXXX0001",  # empty → no_bank
        "account_no_full": "3821350001",
        "bank_logo_url":   "https://d27npaycvagyws.cloudfront.net/banks/logo/SCB.png",
    },
    "paycycle": {
        "id":                   3761,
        "start":                "2026-04-30T17:00:00.209Z",
        "cutoff":               "2026-05-30T09:00:00.209Z",
        "end":                  "2026-05-31T16:59:59.999Z",
        "next_start":           "2026-06-01T16:59:59.999Z",
        "paycycle_status":      "active",         # "active" | "inactive"
        "employee_data_status": "up_to_date",     # "up_to_date" | "outdated"
    },
    "deductions": {
        "total_deducted":        0,
        "deductions_updated_at": "2026-05-11T06:48:48.056Z",
    },
    "sync": {
        "sync_type": "manual",                    # "manual" | "auto"
        "schedules": [],                          # display only
    },
}

# ── 2. Balance API response (GET /api/v1/user/ewa/balance/withdraw) ─────────
BALANCE: dict = {
    "earned_avaliable_amount": 0,                 # information only — never a blocker
    "status":                  "ready",           # "ready" | other
}

# ── 3. Attendance API response (GET /api/v1/user/account/chatbot/attendance)
# `records` is a flat list ordered newest-first by `date`.
# Set `remarks` to a string on any row to trigger attendance_remark scenario.
ATTENDANCE: dict = {
    "records": [
        {"date": "2026-05-11", "check_in": "09:33:00", "check_out": "19:33:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-10", "check_in": "08:45:00", "check_out": "18:45:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-09", "check_in": "10:32:00", "check_out": "20:32:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-08", "check_in": "07:35:00", "check_out": "17:35:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-07", "check_in": "09:12:00", "check_out": "19:12:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-06", "check_in": "08:15:00", "check_out": "08:15:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-05", "check_in": "08:20:00", "check_out": "18:20:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-04", "check_in": "08:05:00", "check_out": "18:05:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-03", "check_in": "11:05:00", "check_out": "21:05:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-02", "check_in": "07:30:00", "check_out": "17:30:00",
         "metadata": {"remark": None}},
        {"date": "2026-05-01", "check_in": "08:39:00", "check_out": "18:39:00",
         "metadata": {"remark": None}},
    ],
}


# ── Hot-reload accessors ─────────────────────────────────────────────────────
# Mock clients call these (not the module-level constants) so edits made
# during a running Gradio session take effect on the NEXT message.

def get_profile() -> dict:
    """Re-read the PROFILE dict at call time so edits don't need a restart."""
    import importlib
    from agent.clients.mock import _mock_data as m
    importlib.reload(m)
    return m.PROFILE


def get_balance() -> dict:
    import importlib
    from agent.clients.mock import _mock_data as m
    importlib.reload(m)
    return m.BALANCE


def get_attendance() -> dict:
    import importlib
    from agent.clients.mock import _mock_data as m
    importlib.reload(m)
    return m.ATTENDANCE
