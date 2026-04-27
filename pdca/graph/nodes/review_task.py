from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from pdca.graph.state import PDCAState


def review_task_node(state: PDCAState, config: RunnableConfig) -> dict:
    """No-op — `interrupt_before=["review_task"]` pauses graph here for HITL."""
    return {}
