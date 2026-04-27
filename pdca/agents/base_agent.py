"""BaseAgent — chỉ giữ config metadata, lazy-init OpenAI client.

Phase B1:
- Bỏ eager init `openai.OpenAI` + `ChatOllama` trong `__init__` (mỗi agent
  thực ra chỉ dùng 1, init cả 2 = lãng phí + tăng surface lỗi import).
- `call_llm()` tạo `openai.OpenAI` lazily ở lần gọi đầu.
- Thêm `callbacks: list = None` để các subclass có LLM (risk/remediate/...)
  propagate xuống ChatOllama (Langfuse hook 3).
- Subclass có thể tự khởi tạo `ChatOllama` riêng (xem risk_evaluation_agent,
  remediate_planner_agent, scanner-NO).
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


class BaseAgent:
    """Lớp cơ sở cho các Agent — lưu config + cung cấp helper `call_llm`.

    Không init bất kỳ network client nào trong `__init__`. OpenAI client
    được tạo lazily lần đầu `call_llm()` được gọi.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str,
        callbacks: Optional[List[BaseCallbackHandler]] = None,
    ) -> None:
        self.model_name = model_name
        self.api_key = api_key or "ollama"
        self.base_url = base_url
        self.callbacks: List[BaseCallbackHandler] = list(callbacks or [])

        # Backward-compat aliases (tên cũ vẫn dùng ở vài chỗ)
        self.model = model_name

        self._openai_client = None  # lazy

    # ------------------------------------------------------------------
    @property
    def client(self):
        """Lazy OpenAI client — chỉ tạo khi cần (call_llm)."""
        if self._openai_client is None:
            import openai

            self._openai_client = openai.OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
            )
        return self._openai_client

    # ------------------------------------------------------------------
    def call_llm(
        self,
        messages,
        tools: Any = None,
        tool_choice: str = "auto",
        response_format: Any = None,
    ):
        """Helper gọi LLM qua OpenAI-compatible endpoint."""
        try:
            params = {
                "model": self.model_name,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
            if response_format:
                params["response_format"] = response_format

            response = self.client.chat.completions.create(**params)
            return response.choices[0].message
        except Exception as e:
            logger.error(
                "LLM call failed",
                extra={
                    "model": self.model_name,
                    "base_url": self.base_url,
                    "error": str(e),
                },
            )
            return None
