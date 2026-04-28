from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from pdca.graph._tracing_helpers import flush_at_node, node_span
from pdca.graph.state import PDCAState


def reset_index_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Reset `current_task_index` → 0 before execution."""
    run_id = state.get("run_id", "")
    with node_span("reset_index", run_id) as sp:
        sp.update(output={"reset_to": 0})
        flush_at_node()
    return {"current_task_index": 0}
