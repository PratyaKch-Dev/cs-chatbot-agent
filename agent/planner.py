"""
Troubleshooting planner — deterministic tool execution.

The router's Haiku classifier already decided the sub-type:
    troubleshooting_withdrawal  → employee_data + attendance
    troubleshooting_attendance  → employee_data (paycycle) + attendance
    troubleshooting_account     → employee_data only
    troubleshooting_deduction   → employee_data only (deduction focus)

Tools are called in a fixed order based on sub-type — no ReAct agent needed.
evidence.py then determines root_cause and picks the answer template.
"""

import logging

from agent.tools.employee_data import get_employee_data
from agent.tools.attendance import get_attendance
from agent.evidence import (
    build_diagnostic_context, format_for_llm, get_filled_template,
)

_logger = logging.getLogger("agent.planner")

# Sub-type → which tools to call (in order)
_TOOL_STRATEGY: dict[str, list[str]] = {
    "troubleshooting_withdrawal": ["get_employee_data", "get_attendance"],
    "troubleshooting_attendance": ["get_employee_data", "get_attendance"],
    "troubleshooting_account":    ["get_employee_data"],
    "troubleshooting_deduction":  ["get_employee_data"],
}
_DEFAULT_STRATEGY = ["get_employee_data", "get_attendance"]


def run_troubleshooting_agent(
    employee_id: str,
    issue: str,
    language: str,
    tenant_id: str,
    sub_type: str = "",
) -> dict:
    """
    Run deterministic tool calls based on the sub-type from the router.

    Returns:
        {
          "diagnostic_context": str   — formatted text for answer_generator
          "template_answer":    str   — pre-filled template; empty = let LLM answer
          "tools_used":         list  — tool names called
          "root_cause":         str   — root cause key (e.g. "sync_pending")
          "iterations":         int   — number of tool calls made
        }
    """
    lang = language if language in ("th", "en") else "th"
    strategy = _TOOL_STRATEGY.get(sub_type, _DEFAULT_STRATEGY)
    _logger.info(f"[planner] {employee_id} | sub_type={sub_type!r} | tools={strategy}")

    tool_outputs: dict[str, str] = {}

    for tool_name in strategy:
        try:
            if tool_name == "get_employee_data":
                tool_outputs["get_employee_data"] = get_employee_data.invoke(
                    {"employee_id": employee_id}
                )
            elif tool_name == "get_attendance":
                # Extract paycycle start_date from employee_data if available
                from datetime import date
                date_from = _extract_paycycle_start(tool_outputs.get("get_employee_data", ""))
                date_to   = date.today().isoformat()
                tool_outputs["get_attendance"] = get_attendance.invoke(
                    {"employee_id": employee_id, "date_from": date_from, "date_to": date_to}
                )
        except Exception as exc:
            _logger.warning(f"[planner] tool {tool_name} failed for {employee_id}: {exc}")

    # Safety net — always need employee_data
    if "get_employee_data" not in tool_outputs:
        _logger.warning(f"[planner] {employee_id}: get_employee_data missing — fetching directly")
        try:
            tool_outputs["get_employee_data"] = get_employee_data.invoke(
                {"employee_id": employee_id}
            )
        except Exception as exc:
            _logger.error(f"[planner] fallback get_employee_data failed: {exc}")

    context   = build_diagnostic_context(employee_id, issue, tool_outputs, lang)
    formatted = format_for_llm(context, lang)
    template  = get_filled_template(context, lang)

    _logger.info(
        f"[planner] {employee_id} | root={context.root_cause} | tools={context.tools_used}"
    )

    return {
        "diagnostic_context": formatted,
        "template_answer":    template,
        "tools_used":         context.tools_used,
        "root_cause":         context.root_cause,
        "iterations":         len(tool_outputs),
    }


def _extract_paycycle_start(employee_data_output: str) -> str:
    """
    Pull paycycle start_date from the employee_data tool output string.
    Returns empty string if not found — get_attendance will use its own default.
    """
    import re
    match = re.search(r"start_date[\"']?\s*:\s*[\"']?([\d\-]+)", employee_data_output)
    return match.group(1) if match else ""
