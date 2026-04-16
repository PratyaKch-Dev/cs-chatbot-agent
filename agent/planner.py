"""
Troubleshooting Agent planner — LangChain tool-calling agent.

The LLM agent decides which tools to call based on the employee's issue.
New tools can be added to _TOOLS in the future without changing this file.

Tool call strategy (agent decides, guided by system prompt):
  1. get_employee_data  — always first; returns profile, sync, deductions, paycycle
  2. get_attendance     — uses paycycle.start_date from step 1 as date_from

Evidence analysis is fully deterministic (evidence.py, no LLM).

Answer generation:
  - Blocking root cause (blacklisted / suspended / sync_pending) → template (no LLM)
  - No blocking issue (ok) → answer_generator calls LLM with diagnostic_context
"""

import logging
import os
import time

from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agent.tools.employee_data import get_employee_data
from agent.tools.attendance import get_attendance
from agent.evidence import (
    build_diagnostic_context, format_for_llm, get_filled_template,
)

_TOOLS = [
    get_employee_data,
    get_attendance,
]

_AGENT_SYSTEM_PROMPT = """\
You are a diagnostic assistant for the Salary Hero HR system.
Your ONLY job is to call tools to gather evidence about why an employee \
cannot withdraw their salary. Do NOT write the final answer.

Tool call strategy:
1. get_employee_data — always call this first.
   Returns profile, sync status, deductions, paycycle dates, and an
   attendance_snapshot covering the last 7 days (or since paycycle start,
   whichever is more recent).
   → If blacklisted or suspended: STOP, return findings.
   → If sync_status is "pending": STOP, return findings.

2. get_attendance — call ONLY if the attendance_snapshot is not enough:
   - User asks about a specific past period beyond the snapshot window
   - Anomalies in the snapshot suggest you need more historical context
   Use paycycle.start_date as date_from for the current pay cycle.
   The API caps results at MAX_ATTENDANCE_DAYS (default 30, configurable).

After calling the tools, respond with a single line: "Diagnosis complete."
"""

_executor: AgentExecutor | None = None


def _get_executor() -> AgentExecutor:
    global _executor
    if _executor is None:
        from llm.client import get_llm

        agent_model = os.environ.get("AGENT_LLM_MODEL", "claude-sonnet-4-6")
        llm = get_llm().__class__(
            model=agent_model,
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            temperature=0,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", _AGENT_SYSTEM_PROMPT),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(llm, _TOOLS, prompt)
        _executor = AgentExecutor(
            agent=agent,
            tools=_TOOLS,
            return_intermediate_steps=True,
            max_iterations=5,
            handle_parsing_errors=True,
            verbose=False,
        )
    return _executor


def run_troubleshooting_agent(
    employee_id: str,
    issue: str,
    language: str,
    tenant_id: str,
) -> dict:
    """
    Run the LangChain tool-calling agent to gather diagnostic evidence.

    Returns:
        {
          "diagnostic_context": str   — formatted text for answer_generator (LLM context)
          "template_answer":    str   — pre-filled template; empty = let LLM answer
          "tools_used":         list  — tool names called by the agent
          "root_cause":         str   — root cause key (e.g. "sync_pending")
          "iterations":         int   — number of tool calls made
        }
    """
    lang = language if language in ("th", "en") else "th"

    agent_input = (
        f"employee_id: {employee_id}\n"
        f"issue: {issue}"
    )

    tool_outputs: dict[str, str] = {}
    _MAX_RETRIES = 2
    for attempt in range(_MAX_RETRIES + 1):
        try:
            result = _get_executor().invoke({"input": agent_input})
            for action, output in result.get("intermediate_steps", []):
                tool_outputs[action.tool] = output
            break
        except Exception as e:
            err_str = str(e).lower()
            if attempt < _MAX_RETRIES and (
                "overloaded" in err_str or "529" in err_str or "rate" in err_str
            ):
                wait = 2 ** attempt
                logging.warning(
                    f"[agent] API overloaded for {employee_id}, retry {attempt + 1} in {wait}s"
                )
                time.sleep(wait)
            else:
                logging.warning(f"[agent] executor error for {employee_id}: {e}")
                break

    # Safety net: agent must always have get_employee_data. If the LLM skipped
    # the tool call (happens on short/generic issues), fetch it directly.
    if "get_employee_data" not in tool_outputs:
        logging.warning(
            f"[agent] {employee_id}: agent skipped get_employee_data — fetching directly"
        )
        tool_outputs["get_employee_data"] = get_employee_data.invoke({"employee_id": employee_id})

    context   = build_diagnostic_context(employee_id, issue, tool_outputs, lang)
    formatted = format_for_llm(context, lang)
    template  = get_filled_template(context, lang)

    logging.info(
        f"[agent] {employee_id} | root={context.root_cause} | tools={context.tools_used}"
    )

    return {
        "diagnostic_context": formatted,
        "template_answer":    template,     # "" for ok → answer_generator uses LLM
        "tools_used":         context.tools_used,
        "root_cause":         context.root_cause,
        "iterations":         len(tool_outputs),
    }
