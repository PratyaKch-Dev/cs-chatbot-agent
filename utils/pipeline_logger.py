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
import threading
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
    step: str,
    model: str,
    in_tokens: int,
    out_tokens: int,
    latency_ms: float = 0.0,
    system: str = "",
    history_msgs: list = None,
    prompt: str = "",
    reply: str = "",
) -> None:
    """Called by llm/client.py after every successful LLM call."""
    if _active_trace is not None:
        _active_trace.llm_calls.append({
            "step":         step,
            "model":        model,
            "in":           in_tokens,
            "out":          out_tokens,
            "ms":           latency_ms,
            "system":       system,
            "history_msgs": history_msgs or [],
            "prompt":       prompt,
            "reply":        reply,
        })


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
    memory_info: dict = field(default_factory=dict)        # what was loaded from Redis

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

    def set_memory(
        self,
        history: list[dict],
        summary: str = "",
        context_type: str = "",
        context_detail: str = "",
    ) -> None:
        """Record what was loaded from Redis for this request."""
        self.memory_info = {
            "history": history,                     # full list [{role, content}]
            "summary": summary,                     # full summary text
            "context_type": context_type,           # "faq" | "troubleshooting" | ""
            "context_detail": context_detail,       # root_cause or question preview
        }

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
        _write_readable(self)  # sync — Gradio reads this immediately after flush()
        _log_terminal(self)
        threading.Thread(target=_write_jsonl, args=(self,), daemon=True).start()



def _write_readable(t: PipelineTrace) -> None:
    dt          = datetime.fromtimestamp(t.timestamp).strftime("%Y-%m-%d %H:%M:%S")
    route_label = t.route.replace("Route.", "").upper()
    is_ts       = "TROUBLESHOOTING" in t.route.upper()
    router_call = next((c for c in t.llm_calls if c["step"] == "router"), None)
    answer_call = next((c for c in t.llm_calls if c["step"] == "answer"), None)
    step_ms     = {s["step"]: s["ms"] for s in t.step_times}

    lines = ["", SEP, f"  {dt}  |  {t.tenant_id}/{t.language}  |  {t.duration_ms:.0f}ms", SEP]

    # ── USER ──────────────────────────────────────────────────────────────────
    lines += [f"  USER    {t.query}", ""]

    # ── MEMORY ────────────────────────────────────────────────────────────────
    m    = t.memory_info or {}
    hist = m.get("history", [])
    ctx  = m.get("context_type", "") or "none"
    detail = m.get("context_detail", "")
    smry = m.get("summary", "")
    ctx_str = f"{ctx} ({detail})" if detail else ctx

    lines.append(f"  MEMORY  history={len(hist)//2} turns  context={ctx_str}")
    for msg in hist:
        role = "U" if msg["role"] == "user" else "B"
        lines.append(f"          [{role}] {msg['content'].replace(chr(10), ' ')}")
    if smry:
        lines.append(f"          [summary] {smry.replace(chr(10), ' ')}")
    else:
        lines.append("          [summary] none")
    lines.append("")

    # ── ROUTER LLM ────────────────────────────────────────────────────────────
    r_tok = f"  in={router_call['in']} out={router_call['out']}" if router_call else ""
    r_ms  = f"  {router_call['ms']:.0f}ms" if router_call else ""
    lines.append(f"  ROUTE   {route_label}{r_ms}{r_tok}")
    if router_call:
        # system prompt
        sys_text = (router_call.get("system") or "").strip()
        for line in sys_text.splitlines():
            lines.append(f"  [SYS]   {line}")
        lines.append("")
        # → sent (the combined user content: summary + history + active_ctx + message)
        sent = (router_call.get("prompt") or "").strip()
        for line in sent.splitlines():
            lines.append(f"  →       {line}")
        # ← back
        reply = (router_call.get("reply") or "").replace("\n", " ")
        lines.append(f"  ←       {reply}")
    else:
        lines.append("          (fallback — no LLM)")
    if t.route_reason:
        lines.append(f"          reason: {t.route_reason}")
    lines.append("")

    # ── RETRIEVAL or AGENT ───────────────────────────────────────────────────
    if is_ts:
        emp_id     = getattr(t, "_employee_id", "?")
        tools_used = getattr(t, "_tools_used", [])
        lines.append(f"  AGENT   employee={emp_id}  root_cause={t.query_cleaned or '—'}")
        lines.append(f"          tools: {' -> '.join(tools_used) if tools_used else '(none)'}")
    else:
        ret_ms = f"  {step_ms['retrieval']:.0f}ms" if "retrieval" in step_ms else ""
        lines.append(f"  RAG{ret_ms}   collection={t.collection}")
        lines.append(f"  →       {t.query_cleaned or t.query}")
        for h in t.hits:
            lines.append(f"          #{h.rank} {h.score:.2f}  {h.question[:65]}")
        if not t.hits:
            lines.append("          (no results)")
    lines.append("")

    # ── ANSWER LLM ───────────────────────────────────────────────────────────
    a_tok = f"  in={answer_call['in']} out={answer_call['out']}" if answer_call else ""
    a_ms  = f"  {answer_call['ms']:.0f}ms" if answer_call else ""
    score_bar = _score_bar(t.grounding_score)
    escalated = "  *** ESCALATED ***" if t.was_escalated else ""
    lines.append(f"  ANSWER{a_ms}{a_tok}   grounding {score_bar} {t.grounding_score:.2f}{escalated}")
    if answer_call:
        # system prompt
        sys_text = (answer_call.get("system") or "").strip()
        for line in sys_text.splitlines():
            lines.append(f"  [SYS]   {line}")
        lines.append("")
        # → sent: history + context/question
        for msg in (answer_call.get("history_msgs") or []):
            role = "U" if msg["role"] == "user" else "B"
            lines.append(f"  →  [{role}] {msg['content'].replace(chr(10), ' ')}")
        sent = (answer_call.get("prompt") or "").strip()
        for line in sent.splitlines():
            lines.append(f"  →       {line}")
        # ← back
        reply = (answer_call.get("reply") or "").strip()
        for line in reply.splitlines():
            lines.append(f"  ←       {line}")
    else:
        for line in t.answer.splitlines():
            lines.append(f"          {line}")
    lines.append("")

    # ── TOKENS ────────────────────────────────────────────────────────────────
    total_in = total_out = 0
    for c in t.llm_calls:
        in_t, out_t = c.get("in", 0), c.get("out", 0)
        total_in  += in_t
        total_out += out_t
        lines.append(f"  TOKENS  {c['step']:12s}  in={in_t:5d}  out={out_t:4d}  total={in_t+out_t:5d}")
    if len(t.llm_calls) > 1:
        lines.append(f"  TOKENS  {'ALL':12s}  in={total_in:5d}  out={total_out:4d}  total={total_in+total_out:5d}")
    lines.append("")

    # ── TIMING ────────────────────────────────────────────────────────────────
    parts  = [f"{s['step']}={s['ms']:.0f}ms" for s in t.step_times]
    parts += [f"{c['step']}={c.get('ms',0):.0f}ms" for c in t.llm_calls]
    lines.append(f"  TOTAL   {t.duration_ms:.0f}ms   " + "  ".join(parts))
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
        "memory": t.memory_info,
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
