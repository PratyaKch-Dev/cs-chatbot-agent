"""Shared access-token context var for all agent tools.

Planner calls set_token() once before invoking any tool.
Both get_employee_data and get_attendance read from the same ContextVar,
so only one set_token() call is needed per request.
"""

from contextvars import ContextVar

_token_ctx: ContextVar[str] = ContextVar("agent_access_token", default="")


def set_token(token: str) -> None:
    """Inject the access token for the current call chain."""
    _token_ctx.set(token)


def get_token() -> str:
    """Return the current access token (empty string if not set)."""
    return _token_ctx.get()
