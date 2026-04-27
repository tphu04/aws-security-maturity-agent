"""Shared LangChain callback handlers.

Single source of truth cho `TimerCallback` (trước đây duplicate ở
`scanner_agent.py`, `risk_evaluation_agent.py`, `remediate_planner_agent.py`).

Là điểm swap khi tích hợp Langfuse: thay vì `[TimerCallback()]`, dùng
`get_callbacks(extra=[langfuse_handler])`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler


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
    """Return default callback list `[TimerCallback()] + extra`.

    Mỗi caller nên TỰ tạo TimerCallback riêng để giữ state cô lập (latency
    metrics tính riêng cho từng agent). Factory này tiện cho call site nào
    chỉ cần "callbacks chuẩn + (Langfuse handler nếu có)".
    """
    return [TimerCallback()] + list(extra or [])


__all__ = ["TimerCallback", "get_callbacks"]
