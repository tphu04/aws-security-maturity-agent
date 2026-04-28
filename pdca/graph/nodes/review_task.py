from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from pdca.graph._tracing_helpers import node_span
from pdca.graph.state import PDCAState
from pdca.observability.tracing import _current_trace


def review_task_node(state: PDCAState, config: RunnableConfig) -> dict:
    """Persist Langfuse parent context so HITL `hitl:wait` can attach.

    The actual interrupt is driven by `interrupt_before=["review_task"]` in
    `build_graph`. We open a short span just to mark "the graph reached the
    HITL boundary" — the real human-wait span is created by
    `handle_task_review_interaction` (Phase I.5).
    """
    run_id = state.get("run_id", "")
    parent_span_id = None
    trace_id = None

    with node_span("review_task", run_id) as sp:
        parent_span_id = getattr(sp, "id", None)
        handle = _current_trace.get()
        trace_id = getattr(handle, "trace_id", None) if handle is not None else None

    delta: dict = {}
    if parent_span_id:
        delta["_langfuse_parent_span_id"] = parent_span_id
    if trace_id:
        delta["_langfuse_trace_id"] = trace_id
    return delta
