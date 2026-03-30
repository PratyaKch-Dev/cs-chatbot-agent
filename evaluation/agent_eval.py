"""
Troubleshooting agent evaluation.

Offline metrics to measure agent quality:
- Tool selection accuracy:  did the agent call the right tools?
- Loop efficiency:          how many iterations to reach an answer?
- Hallucination rate:       does the answer contradict tool output?
- Resolution rate:          was the issue correctly diagnosed?

Run manually before deploying agent changes.
"""

from dataclasses import dataclass, field
from pathlib import Path

DATASETS_DIR = Path(__file__).parent / "datasets"


@dataclass
class AgentEvalResult:
    scenario: str
    employee_id: str
    expected_tools: list[str]
    actual_tools: list[str]
    expected_diagnosis: str
    actual_diagnosis: str
    tool_accuracy: float
    iterations: int
    correctly_resolved: bool


def run_agent_eval(
    test_cases_path: str = str(DATASETS_DIR / "agent_test_cases.json"),
    tenant_id: str = "hns",
) -> list[AgentEvalResult]:
    """
    Run agent evaluation against the test dataset.

    TODO Phase 7: implement.
    """
    raise NotImplementedError("Phase 7")


def print_eval_report(results: list[AgentEvalResult]) -> None:
    """Print a summary report of evaluation results."""
    raise NotImplementedError("Phase 7")
