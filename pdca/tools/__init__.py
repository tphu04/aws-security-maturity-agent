"""pdca.tools — package facade (B13, B14).

Public API (mới — dùng cho code mới):
- `REGISTRY`: ToolRegistry singleton (single source of truth)
- `get_tools_for(category)`: list[BaseTool] cho 1 category

Legacy exports (backward-compat):
- `REMEDIATION_TOOLS`, `SCANNER_AGENT_TOOLS`, `AVAILABLE_FUNCTIONS`,
  `ALL_TOOLS`, `TOOLS_MAP`

`AVAILABLE_FUNCTIONS` giờ chính là `TOOLS_MAP` (key = `tool.name` thật) —
loại bỏ alias key cũ kiểu `"remediate_s3_*"` (decision #34).
"""

from pdca.tools.registry import REGISTRY, get_tools_for

# Auto-register: side effects khi import từng module
from pdca.tools import scanner, knowledge   # noqa: F401, E402
from pdca.tools.remediation import s3       # noqa: F401, E402

# --- Backward-compat lists (DO NOT add new entries — dùng REGISTRY thay) ---
SCANNER_AGENT_TOOLS = (
    REGISTRY.for_category("scanner") + REGISTRY.for_category("knowledge")
)
REMEDIATION_TOOLS = REGISTRY.for_category("remediation")
ALL_TOOLS = SCANNER_AGENT_TOOLS + REMEDIATION_TOOLS
TOOLS_MAP = {t.name: t for t in ALL_TOOLS}
AVAILABLE_FUNCTIONS = TOOLS_MAP   # alias key đã chuẩn hóa về tool.name

__all__ = [
    "REGISTRY",
    "get_tools_for",
    # Legacy
    "SCANNER_AGENT_TOOLS",
    "REMEDIATION_TOOLS",
    "ALL_TOOLS",
    "TOOLS_MAP",
    "AVAILABLE_FUNCTIONS",
]
