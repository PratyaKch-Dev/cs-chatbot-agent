"""
Evidence collector and diagnostic context builder.

Takes raw tool outputs from the agent and synthesizes them into
a structured diagnostic summary for the answer generator.
"""

from dataclasses import dataclass, field


@dataclass
class DiagnosticContext:
    employee_id: str
    issue: str
    tools_used: list[str]
    findings: dict               # tool_name → parsed result
    summary: str                 # human-readable diagnosis
    root_cause: str = ""
    suggested_actions: list[str] = field(default_factory=list)


def build_diagnostic_context(
    employee_id: str,
    issue: str,
    tool_outputs: dict[str, str],
) -> DiagnosticContext:
    """
    Parse tool outputs and synthesize a diagnostic summary.

    Args:
        employee_id: The employee being diagnosed
        issue: Original user complaint
        tool_outputs: Dict of {tool_name: raw_json_string}

    TODO Phase 5: implement — parse JSON from each tool, identify root cause.
    """
    raise NotImplementedError("Phase 5")


def format_for_llm(context: DiagnosticContext, language: str) -> str:
    """
    Format diagnostic context into a string for the LLM prompt.

    TODO Phase 5: implement Thai + English formatting.
    """
    raise NotImplementedError("Phase 5")
