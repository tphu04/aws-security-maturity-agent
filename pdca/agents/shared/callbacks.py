"""Shared LangChain callback handlers.

Single source of truth cho `TimerCallback` (trước đây duplicate ở
`scanner_agent.py`, `risk_evaluation_agent.py`, `remediate_planner_agent.py`).

Là điểm swap khi tích hợp Langfuse: thay vì `[TimerCallback()]`, dùng
`get_callbacks(extra=[langfuse_handler])`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

try:
    from langchain_core.callbacks import BaseCallbackHandler
except Exception:  # pragma: no cover - dependency may be absent in minimal CI
    class BaseCallbackHandler:  # type: ignore[no-redef]
        pass

from pdca.observability.langfuse_client import get_langfuse_handler


class TimerCallback(BaseCallbackHandler):
    """Đo tổng thời gian + per-call latency cho mỗi LLM invocation."""

    def __init__(self) -> None:
        self.total_duration: float = 0.0
        self.call_history: List[float] = []
        self.start_time: float = 0.0

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> Any:
        self.start_time = time.perf_counter()

    def on_llm_end(self, response: Any, **kwargs: Any) -> Any:
        duration = time.perf_counter() - self.start_time
        self.total_duration += duration
        self.call_history.append(duration)


def get_callbacks(extra: Optional[List[BaseCallbackHandler]] = None) -> List[BaseCallbackHandler]:
    """Return TimerCallback plus Langfuse handler and optional callbacks.

    Mỗi caller nên TỰ tạo TimerCallback riêng để giữ state cô lập (latency
    metrics tính riêng cho từng agent). TimerCallback giữ song song Langfuse
    theo decision D12.
    """
    handler = get_langfuse_handler()
    return [TimerCallback()] + ([handler] if handler else []) + list(extra or [])


def extract_config_callbacks(config: Optional[Dict[str, Any]]) -> List[BaseCallbackHandler]:
    """Pull callback handlers out of a LangGraph RunnableConfig safely.

    LangGraph may inject `config['callbacks']` as a `CallbackManager` (not a
    plain list — `list(manager)` raises). We unwrap `.handlers` so downstream
    nodes can extend it freely.
    """
    if not config:
        return []
    raw = config.get("callbacks")
    if raw is None:
        raw = (config.get("configurable") or {}).get("callbacks")
    if raw is None:
        return []
    handlers = getattr(raw, "handlers", None)
    if handlers is not None:
        return list(handlers)
    try:
        return list(raw)
    except TypeError:
        return []


__all__ = ["TimerCallback", "get_callbacks", "extract_config_callbacks"]
