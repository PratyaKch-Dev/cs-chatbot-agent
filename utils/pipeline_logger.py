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

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "faq_trace.log"       # human-readable
JSONL_FILE = LOG_DIR / "faq_trace.jsonl"   # machine-readable

_logger = logging.getLogger("pipeline")

SEP = "─" * 72


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
    query_cleaned: str = ""
    collection: str = ""
    hits: list[RetrievalHit] = field(default_factory=list)
    answer: str = ""
    grounding_score: float = 0.0
    was_escalated: bool = False
    duration_ms: float = 0.0

    _start: float = field(default_factory=time.time, repr=False)

    def set_route(self, route: str, reason: str) -> None:
        self.route = route
        self.route_reason = reason

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

    def set_answer(self, text: str, grounding_score: float, was_escalated: bool) -> None:
        self.answer = text
        self.grounding_score = round(grounding_score, 4)
        self.was_escalated = was_escalated

    def flush(self) -> None:
        self.duration_ms = round((time.time() - self._start) * 1000, 1)
        LOG_DIR.mkdir(exist_ok=True)

        _write_readable(self)
        _write_jsonl(self)
        _log_terminal(self)


def _write_readable(t: PipelineTrace) -> None:
    dt = datetime.fromtimestamp(t.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    escalated = "  *** ESCALATED ***" if t.was_escalated else ""
    score_bar = _score_bar(t.grounding_score)

    lines = [
        "",
        SEP,
        f"  {dt}  |  {t.tenant_id}/{t.language}  |  {t.duration_ms}ms",
        SEP,
        f"  QUERY    : {t.query}",
    ]

    if t.query_cleaned != t.query:
        lines.append(f"  CLEANED  : {t.query_cleaned}")

    route_label = t.route.replace("Route.", "")
    lines.append(f"  ROUTE    : {route_label}  ({t.route_reason})")
    lines.append(f"  COLLECT  : {t.collection}")
    lines.append("")

    if t.hits:
        lines.append("  RETRIEVED:")
        for h in t.hits:
            lines.append(f"    #{h.rank}  score={h.score:.3f}  Q: {h.question}")
            lines.append(f"             A: {h.answer_preview}")
    else:
        lines.append("  RETRIEVED: (none)")

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
