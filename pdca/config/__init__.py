"""pdca.config — package facade.

Exposes:
- `settings`: canonical Pydantic BaseSettings instance (USE THIS for new code)
- Legacy module-level constants: kept for backward compat. Will be removed
  after Phase B/C khi tất cả callers đã migrate sang `settings.xxx`.
"""

from pdca.config.settings import settings

# --- Backward-compat constants (DO NOT add new ones here) ---
RAG_API_URL = settings.rag_api_url
SCANNER_API_URL = settings.scanner_api_url
OLLAMA_BASE_URL = settings.ollama_base_url
OLLAMA_MODEL = settings.ollama_model
OLLAMA_API_KEY = settings.ollama_api_key
MULTI_QUERY_MODE = settings.multi_query_mode

__all__ = [
    "settings",
    # Legacy
    "RAG_API_URL",
    "SCANNER_API_URL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_API_KEY",
    "MULTI_QUERY_MODE",
]
