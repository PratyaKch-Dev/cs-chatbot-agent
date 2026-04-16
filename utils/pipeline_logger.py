"""
FAQ pipeline logger.

Writes two files per session:
  logs/faq_trace.log   — human-readable blocks (easy to read in editor)
  logs/faq_trace.jsonl — one JSON line per request (for scripting)

Usage:
    trace = PipelineTrace(tenant_id="hns", query="...", language="th")
    trace.set_route(route="faq", reason="default")
    trace.set_retrieval(query_used="...", collection="hns_th", documents=[...])
    trace.set_answer(text="...", grounding_score=0.8, was_escalated=False)
    trace.flush()
"""

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "faq_trace.log"       # human-readable
JSONL_FILE = LOG_DIR / "faq_trace.jsonl"   # machine-readable

_logger = logging.getLogger("pipeline")

SEP = "─" * 72

# ── Active-trace registry ─────────────────────────────────────────────────────
# call_llm() pushes here so every LLM call is recorded without touching
# the router/answer_generator signatures.
_active_trace: Optional["PipelineTrace"] = None


def set_active_trace(trace: Optional["PipelineTrace"]) -> None:
    global _active_trace
    _active_trace = trace


def record_llm_call(
    step: str, model: str, in_tokens: int, out_tokens: int, latency_ms: float = 0.0
) -> None:
    """Called by llm/client.py after every successful LLM call."""
    if _active_trace is not None:
        _active_trace.llm_calls.append(
            {"step": step, "model": model, "in": in_tokens, "out": out_tokens, "ms": latency_ms}
        )


@dataclass
class RetrievalHit:
    rank: int
    score: float
    question: str
    answer_preview: str   # first 120 chars


@dataclass
class PipelineTrace:
    tenant_id: str
    query: str
    language: str
    timestamp: float = field(default_factory=time.time)

    route: str = ""
    route_reason: str = ""
    route_label: str = ""   # LLM-returned label e.g. "greeting", "troubleshooting_withdrawal"
    query_cleaned: str = ""
    collection: str = ""
    hits: list[RetrievalHit] = field(default_factory=list)
    answer: str = ""
    grounding_score: float = 0.0
    was_escalated: bool = False
    duration_ms: float = 0.0
    llm_calls: list[dict] = field(default_factory=list)   # [{step, model, in, out, ms}, ...]
    step_times: list[dict] = field(default_factory=list)  # [{step, ms}, ...] for non-LLM steps

    _start: float = field(default_factory=time.time, repr=False)

    def set_route(self, route: str, reason: str, label: str = "") -> None:
        self.route = route
        self.route_reason = reason
        self.route_label = label

    def set_retrieval(self, query_used: str, collection: str, documents: list) -> None:
        self.query_cleaned = query_used
        self.collection = collection
        self.hits = [
            RetrievalHit(
                rank=i + 1,
                score=round(doc.score, 4),
                question=doc.question,
                answer_preview=doc.answer[:120],
            )
            for i, doc in enumerate(documents)
        ]

    def set_troubleshooting(self, employee_id: str, root_cause: str, tools_used: list[str]) -> None:
        self.collection      = f"agent:{employee_id}"
        self.query_cleaned   = root_cause
        self._employee_id    = employee_id
        self._tools_used     = tools_used

    def mark_step(self, step: str, latency_ms: float) -> None:
        """Record timing for a named non-LLM step (e.g. 'retrieval', 'reranker')."""
        self.step_times.append({"step": step, "ms": round(latency_ms, 1)})

    def set_answer(self, text: str, grounding_score: float, was_escalated: bool) -> None:
        self.answer = text
        self.grounding_score = round(grounding_score, 4)
        self.was_escalated = was_escalated

    def __post_init__(self) -> None:
        set_active_trace(self)

    def flush(self) -> None:
        set_active_trace(None)
        self.duration_ms = round((time.time() - self._start) * 1000, 1)
        LOG_DIR.mkdir(exist_ok=True)

        _write_readable(self)
        _write_jsonl(self)
        _log_terminal(self)


def _write_readable(t: PipelineTrace) -> None:
    dt          = datetime.fromtimestamp(t.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    escalated   = "  *** ESCALATED ***" if t.was_escalated else ""
    route_label = t.route.replace("Route.", "")
    is_ts       = "TROUBLESHOOTING" in t.route.upper()

    lines = [
        "",
        SEP,
        f"  {dt}  |  {t.tenant_id}/{t.language}  |  {t.duration_ms}ms",
        SEP,
        f"  QUERY    : {t.query}",
        f"  ROUTE    : {route_label}  ({t.route_reason})"
        + (f"  →  {t.route_label}" if getattr(t, "route_label", "") else ""),
    ]

    if is_ts:
        emp_id     = getattr(t, "_employee_id", "?")
        tools_used = getattr(t, "_tools_used", [])
        root_cause = t.query_cleaned   # stored in set_troubleshooting
        lines += [
            f"  EMPLOYEE : {emp_id}",
            f"  ROOT     : {root_cause}",
            "",
            "  TOOLS CALLED:",
        ]
        for i, tool in enumerate(tools_used, 1):
            lines.append(f"    #{i}  {tool}")
        if not tools_used:
            lines.append("    (none)")
    else:
        if t.query_cleaned != t.query:
            lines.append(f"  CLEANED  : {t.query_cleaned}")
        lines += ["", f"  COLLECT  : {t.collection}", "", "  RETRIEVED:"]
        if t.hits:
            for h in t.hits:
                lines.append(f"    #{h.rank}  score={h.score:.3f}  Q: {h.question}")
                lines.append(f"             A: {h.answer_preview}")
        else:
            lines.append("    (none)")

    has_timings = t.step_times or t.llm_calls
    if has_timings:
        lines += ["", "  TIMINGS:"]
        for s in t.step_times:
            lines.append(f"    [{s['step']:12s}]  {s['ms']:>7.1f}ms")
        for c in t.llm_calls:
            lines.append(
                f"    [{c['step']:12s}]  {c.get('ms', 0):>7.1f}ms  "
                f"(LLM: model={c['model']}  in={c['in']} out={c['out']})"
            )
        accounted_ms = sum(s["ms"] for s in t.step_times) + sum(c.get("ms", 0) for c in t.llm_calls)
        other_ms = max(t.duration_ms - accounted_ms, 0.0)
        lines.append(f"    [{'other':12s}]  {other_ms:>7.1f}ms  (lang/intent/overhead)")
        lines.append(f"    {'─' * 36}")
        lines.append(f"    [{'TOTAL':12s}]  {t.duration_ms:>7.1f}ms")

    score_bar = _score_bar(t.grounding_score)
    lines += [
        "",
        f"  GROUNDING: {score_bar}  {t.grounding_score:.2f}{escalated}",
        "",
        "  ANSWER:",
    ]
    for line in t.answer.splitlines():
        lines.append(f"    {line}")
    lines.append(SEP)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_jsonl(t: PipelineTrace) -> None:
    record = {
        "ts": t.timestamp,
        "tenant": t.tenant_id,
        "lang": t.language,
        "query": t.query,
        "query_cleaned": t.query_cleaned,
        "route": t.route,
        "route_reason": t.route_reason,
        "collection": t.collection,
        "hits": [asdict(h) for h in t.hits],
        "answer": t.answer,
        "grounding_score": t.grounding_score,
        "was_escalated": t.was_escalated,
        "duration_ms": t.duration_ms,
        "step_times": t.step_times,
        "llm_calls": t.llm_calls,
    }
    with open(JSONL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _log_terminal(t: PipelineTrace) -> None:
    escalated_tag = " [ESCALATED]" if t.was_escalated else ""
    hit_summary = "  ".join(
        f"#{h.rank}({h.score:.2f}) {h.question[:25]!r}"
        for h in t.hits[:3]
    )
    _logger.info(
        f"[FAQ] {t.tenant_id}/{t.language} | route={t.route.replace('Route.', '')} | "
        f"score={t.grounding_score:.2f}{escalated_tag} | {t.duration_ms}ms\n"
        f"  Q: {t.query[:80]}\n"
        f"  hits: {hit_summary}"
    )


def _score_bar(score: float) -> str:
    filled = round(score * 10)
    return "[" + "█" * filled + "░" * (10 - filled) + "]"
