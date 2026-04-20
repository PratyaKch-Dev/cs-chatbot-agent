"""
Central memory configuration.
All TTLs and Redis key prefixes are loaded from config/memory.yaml.
Import from here — never hardcode TTLs in individual memory modules.
"""

from pathlib import Path
import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "memory.yaml"

def _load() -> dict:
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)

_cfg = _load()

# ── TTLs ──────────────────────────────────────────────────────────────────────
SESSION_TTL_SECONDS                  = _cfg["session"]["ttl_seconds"]
HISTORY_TTL_SECONDS                  = _cfg["history"]["ttl_seconds"]
MAX_EXCHANGES                        = _cfg["history"]["max_exchanges"]
SUMMARY_TTL_SECONDS                  = _cfg["summary"]["ttl_seconds"]
FAQ_CONTEXT_TTL_SECONDS              = _cfg["context"]["faq_ttl_seconds"]
TROUBLESHOOTING_CONTEXT_TTL_SECONDS  = _cfg["context"]["troubleshooting_ttl_seconds"]
CACHE_TTL_SECONDS                    = _cfg["cache"]["ttl_seconds"]

# ── Key builders ──────────────────────────────────────────────────────────────
_k = _cfg["keys"]

def session_key(tenant_id: str, user_id: str) -> str:
    return f"{_k['session']}:{tenant_id}:{user_id}"

def history_key(tenant_id: str, user_id: str, language: str) -> str:
    return f"{_k['history']}:{tenant_id}:{user_id}:{language}"

def summary_key(tenant_id: str, user_id: str, language: str) -> str:
    return f"{_k['summary']}:{tenant_id}:{user_id}:{language}"

def context_key(tenant_id: str, user_id: str) -> str:
    return f"{_k['context']}:{tenant_id}:{user_id}"

def cache_key(tenant_id: str, user_id: str) -> str:
    return f"{_k['cache']}:{tenant_id}:{user_id}"
