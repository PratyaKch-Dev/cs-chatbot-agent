"""
Troubleshooting Agent planner.

Sets up a LangChain ReAct AgentExecutor with all HR tools.
The agent iteratively decides which tools to call to diagnose an issue.
"""

from typing import Optional

# TODO Phase 5: implement
# from langchain.agents import create_react_agent, AgentExecutor
# from langchain.prompts import PromptTemplate
# from llm.client import get_llm
# from agent.tools.attendance import get_attendance_records
# from agent.tools.shift import get_shift_schedule
# from agent.tools.deduction import get_salary_deductions
# from agent.tools.employee_status import get_employee_status
# from agent.tools.sync_schedule import get_sync_schedule

MAX_ITERATIONS = 10     # prevent runaway loops
MAX_EXECUTION_TIME = 30 # seconds

AGENT_SYSTEM_PROMPT = """You are a Salary Hero HR support agent helping diagnose employee issues.
You have access to tools that fetch real employee data. Use them to investigate the issue thoroughly.

Guidelines:
- Always check employee status first before other tools
- Use structured JSON data from tools — do not guess or assume values
- After gathering evidence, summarize findings clearly in {language}
- If data is insufficient to diagnose, say so clearly

Available tools: {tools}
Tool names: {tool_names}

{agent_scratchpad}
"""


def create_troubleshooting_agent():
    """
    Create and return a LangChain AgentExecutor for troubleshooting.

    TODO Phase 5: implement using create_react_agent.
    """
    raise NotImplementedError("Phase 5")


def run_troubleshooting_agent(
    employee_id: str,
    issue: str,
    language: str,
    tenant_id: str,
) -> dict:
    """
    Run the troubleshooting agent for a specific employee issue.

    Returns a dict with:
        - diagnostic_context: str  (evidence summary for answer generator)
        - tools_used: list[str]
        - iterations: int

    TODO Phase 5: implement.
    """
    raise NotImplementedError("Phase 5")
