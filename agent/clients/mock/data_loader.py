"""
Mock data loader.

Loads all mock user data from users.json once and caches it.
All mock clients use this to look up data by employee_id.
"""

import json
from pathlib import Path

_USERS_JSON = Path(__file__).parent / "users.json"
_cache: dict | None = None


def load_mock_users() -> dict:
    """Load and cache mock user data from users.json."""
    global _cache
    if _cache is None:
        with open(_USERS_JSON, encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def get_user(employee_id: str) -> dict:
    """
    Return mock data for a specific employee.
    Raises ValueError if employee_id is not in the mock data.
    """
    users = load_mock_users()
    if employee_id not in users:
        raise ValueError(
            f"Mock user '{employee_id}' not found. "
            f"Available: {list(users.keys())}"
        )
    return users[employee_id]
