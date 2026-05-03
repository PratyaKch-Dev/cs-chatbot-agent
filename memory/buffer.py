"""
Async debounce buffer for webhook message combining.

When a user sends multiple messages quickly, they are held for DEBOUNCE_SECONDS
then flushed as a single combined call to the pipeline.

Each new message resets the timer — the flush fires only after the user
has stopped typing for the debounce window.

Designed for single-process async (FastAPI/uvicorn --workers 1).
For multi-process: replace in-memory state with Redis pub/sub + distributed lock.
"""

import asyncio
import logging
from typing import Awaitable, Callable

_logger = logging.getLogger("memory.buffer")

DEBOUNCE_SECONDS = 1.5

_buffers: dict[str, list[str]] = {}
_tasks: dict[str, asyncio.Task] = {}
_lock = asyncio.Lock()


async def append(
    key: str,
    message: str,
    on_flush: Callable[[list[str]], Awaitable[None]],
    debounce: float = DEBOUNCE_SECONDS,
) -> None:
    """Push a message and (re)start the debounce timer for this key."""
    async with _lock:
        _buffers.setdefault(key, []).append(message)
        existing = _tasks.get(key)
        if existing and not existing.done():
            existing.cancel()
        _tasks[key] = asyncio.create_task(_fire(key, on_flush, debounce))
        _logger.debug(f"[buffer] {key} buffered ({len(_buffers[key])} msg(s))")


async def _fire(
    key: str,
    on_flush: Callable[[list[str]], Awaitable[None]],
    delay: float,
) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return  # timer was reset by a newer message
    async with _lock:
        messages = _buffers.pop(key, [])
        _tasks.pop(key, None)
    if messages:
        _logger.info(f"[buffer] {key} flushing {len(messages)} message(s): {messages}")
        try:
            await on_flush(messages)
        except Exception as e:
            _logger.error(f"[buffer] {key} flush error: {e}")
