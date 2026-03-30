"""
Application metrics.

Tracks per-tenant operational metrics:
- Token cost per request
- Request latency (p50, p95, p99)
- Route distribution (faq / troubleshooting / template / handoff)
- Escalation rate
- Error rate
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestMetric:
    tenant_id: str
    user_id: str
    route_taken: str
    latency_ms: float
    grounding_score: float
    was_escalated: bool
    error: Optional[str] = None
    token_count: Optional[int] = None
    tools_used: list[str] = field(default_factory=list)


def record_metric(metric: RequestMetric) -> None:
    """
    Record a request metric.

    TODO Phase 7: implement — push to monitoring backend (Prometheus / Datadog / CloudWatch).
    Currently logs to stdout as a placeholder.
    """
    pass  # no-op until Phase 7


def get_escalation_rate(tenant_id: str, window_hours: int = 24) -> float:
    """
    Return escalation rate for a tenant over the last N hours.

    TODO Phase 7: implement.
    """
    raise NotImplementedError("Phase 7")
