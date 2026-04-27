"""ToolRegistry — single source of truth cho tool catalog (B14).

Mỗi tool tự register vào REGISTRY khi module được import (xem
`pdca/tools/__init__.py`). Metadata-rich: category + manual_only.

Thay 4 export list cũ (`AVAILABLE_FUNCTIONS`, `SCANNER_AGENT_TOOLS`,
`REMEDIATION_TOOLS`, `ALL_TOOLS`) bằng 1 source of truth — backward-compat
shim trong `__init__.py` build các list cũ từ REGISTRY.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from langchain_core.tools import BaseTool


@dataclass
class ToolMeta:
    tool: BaseTool
    category: str           # "scanner" | "knowledge" | "remediation"
    manual_only: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, ToolMeta] = {}

    def register(
        self,
        tool: BaseTool,
        *,
        category: str,
        manual_only: bool = False,
    ) -> BaseTool:
        if tool.name in self._by_name:
            raise ValueError(f"Tool '{tool.name}' đã được register")
        self._by_name[tool.name] = ToolMeta(
            tool=tool, category=category, manual_only=manual_only,
        )
        return tool

    def get(self, name: str) -> Optional[BaseTool]:
        meta = self._by_name.get(name)
        return meta.tool if meta else None

    def meta(self, name: str) -> Optional[ToolMeta]:
        return self._by_name.get(name)

    def is_manual_only(self, name: str) -> bool:
        meta = self._by_name.get(name)
        return meta.manual_only if meta else False

    def for_category(self, category: str) -> list[BaseTool]:
        return [m.tool for m in self._by_name.values() if m.category == category]

    def all(self) -> list[BaseTool]:
        return [m.tool for m in self._by_name.values()]


REGISTRY = ToolRegistry()


def get_tools_for(category: str) -> list[BaseTool]:
    return REGISTRY.for_category(category)
