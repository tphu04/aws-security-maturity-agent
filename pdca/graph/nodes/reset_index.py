from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from pdca.graph.state import PDCAState


def reset_index_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Reset `current_task_index` → 0 before execution."""
    return {"current_task_index": 0}
