"""Phase I.2 — node-level tracing helpers.

Centralised so each node body stays focused on business logic. Wrappers are
no-ops when Langfuse is disabled; never raise.
"""

from __future__ import annotations

from typing import Any, Optional

from pdca.observability.context import set_run_id
from pdca.observability.langfuse_client import score_safe
from pdca.observability.tracing import (
    flush_at_node,
    span,
    update_trace_metadata,
)


def node_span(name: str, run_id: str, **metadata: Any):
    """Open a `node:<name>` span with run_id metadata.

    Pairs with ``flush_at_node()`` in the caller's ``finally``-style cleanup.
    """
    set_run_id(run_id or "")
    return span(f"node:{name}", metadata={"run_id": run_id, **metadata})


def emit_score(run_id: str, name: str, value: float, comment: Optional[str] = None) -> None:
    score_safe(trace_id=run_id, name=name, value=value, comment=comment)


__all__ = ["emit_score", "flush_at_node", "node_span", "update_trace_metadata"]
