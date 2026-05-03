"""
Message combiner.

When a new message arrives while a previous one is still being processed,
both are combined into one query so the user gets a single answer.

How it works (two-phase):
  - push()       — instantly add a message to the pending queue (no generation bump)
  - claim()      — claim pending + inflight as the new batch to process;
                   increments generation; returns (generation, messages)
  - is_current() — after pipeline returns, check if a newer claim arrived;
                   if so, discard the result
  - complete()   — clear inflight state after showing the result
  - reset()      — wipe state on clear / session end

Thread-safe. Designed for sync interfaces (Gradio).
Async/webhook interfaces use memory/buffer.py (Redis + asyncio) instead.
"""

import threading

_states: dict[str, dict] = {}
_global_lock = threading.Lock()


def _state(tenant_id: str, user_id: str) -> dict:
    key = f"{tenant_id}:{user_id}"
    with _global_lock:
        if key not in _states:
            _states[key] = {
                "inflight":   [],   # messages currently being processed
                "pending":    [],   # messages that arrived mid-processing
                "generation": 0,
                "lock":       threading.Lock(),
            }
        return _states[key]


def push(tenant_id: str, user_id: str, message: str) -> None:
    """Add a message to the pending queue without starting processing."""
    s = _state(tenant_id, user_id)
    with s["lock"]:
        s["pending"].append(message)


def claim(tenant_id: str, user_id: str) -> tuple[int | None, list[str]]:
    """
    Claim all pending messages (+ any inflight) as the next batch to process.

    Returns (generation, messages) where:
      generation — None if nothing to process; pass to is_current() after pipeline
      messages   — list of strings to join and pass to handle_message
    """
    s = _state(tenant_id, user_id)
    with s["lock"]:
        if not s["pending"] and not s["inflight"]:
            return None, []
        s["generation"] += 1
        gen = s["generation"]
        batch = s["inflight"] + s["pending"]
        s["inflight"] = batch[:]
        s["pending"]  = []
    return gen, batch


def is_current(tenant_id: str, user_id: str, generation: int) -> bool:
    """
    True if this generation should show its result.

    Returns False if a newer claim exists OR if pending messages are queued —
    the latter forces rapid messages to be combined: the next claim() will
    pick up inflight + pending as one batch.
    """
    s = _state(tenant_id, user_id)
    with s["lock"]:
        if s["pending"]:
            return False
        return s["generation"] == generation


def complete(tenant_id: str, user_id: str) -> None:
    """Clear inflight state after the result has been shown."""
    s = _state(tenant_id, user_id)
    with s["lock"]:
        s["inflight"] = []


def reset(tenant_id: str, user_id: str) -> None:
    """Wipe all state (call on session clear)."""
    key = f"{tenant_id}:{user_id}"
    with _global_lock:
        _states.pop(key, None)
