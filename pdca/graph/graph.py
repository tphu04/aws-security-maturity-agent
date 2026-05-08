"""Graph topology — Phase C6.

Pure topology: add_node / add_edge / add_conditional_edges / compile. No
business logic, no node implementations.
"""

from __future__ import annotations

from typing import Any, Optional

from langgraph.graph import END, START, StateGraph

from pdca.graph.checkpointer import get_checkpointer
from pdca.graph.nodes import (
    environment_node,
    execution_node,
    planning_node,
    rag_enrich_node,
    remediation_node,
    report_node,
    reset_index_node,
    review_task_node,
    risk_eval_node,
    scan_collect_node,
    scan_poll_node,
    scan_submit_node,
    verification_node,
)
from pdca.graph.routing import route_after_risk, route_review_task, route_scan_poll
from pdca.graph.state import PDCAState


def build_graph(checkpointer: Optional[Any] = None):
    """Compile and return the LangGraph application.

    Args:
        checkpointer: Optional checkpointer instance. Default = SqliteSaver via
                      `get_checkpointer()`. Tests should pass
                      `get_checkpointer("memory")`.
    """
    wf = StateGraph(PDCAState)

    # --- Nodes ---
    wf.add_node("environment", environment_node)
    wf.add_node("planning", planning_node)
    wf.add_node("scan_submit", scan_submit_node)
    wf.add_node("scan_poll", scan_poll_node)
    wf.add_node("scan_collect", scan_collect_node)
    wf.add_node("risk_evaluation", risk_eval_node)
    wf.add_node("rag_enrich", rag_enrich_node)
    wf.add_node("operational_planning", remediation_node)
    wf.add_node("review_task", review_task_node)
    wf.add_node("reset_index", reset_index_node)
    wf.add_node("execution", execution_node)
    wf.add_node("verification", verification_node)
    wf.add_node("report", report_node)

    # --- Linear edges ---
    wf.add_edge(START, "environment")
    wf.add_edge("environment", "planning")
    wf.add_edge("planning", "scan_submit")
    wf.add_edge("scan_submit", "scan_poll")
    wf.add_edge("scan_collect", "risk_evaluation")
    wf.add_edge("rag_enrich", "operational_planning")
    wf.add_edge("operational_planning", "review_task")
    wf.add_edge("reset_index", "execution")
    wf.add_edge("execution", "verification")
    wf.add_edge("verification", "report")
    wf.add_edge("report", END)

    # --- Conditional edges ---
    wf.add_conditional_edges(
        "scan_poll",
        route_scan_poll,
        {"scan_poll": "scan_poll", "scan_collect": "scan_collect"},
    )
    wf.add_conditional_edges(
        "risk_evaluation",
        route_after_risk,
        {"operational_planning": "rag_enrich", "report": "report"},
    )
    wf.add_conditional_edges(
        "review_task",
        route_review_task,
        {"review_task": "review_task", "reset_then_execute": "reset_index"},
    )

    cp = checkpointer if checkpointer is not None else get_checkpointer()
    return wf.compile(checkpointer=cp, interrupt_before=["review_task"])
