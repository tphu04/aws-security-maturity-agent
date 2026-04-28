from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.planning_agent import PlanningAgent
from pdca.agents.shared.callbacks import get_callbacks
from pdca.agents.shared.rag_client import RAGClient
from pdca.config import settings
from pdca.graph._metrics import measure_time, save_scan_configuration, update_metrics
from pdca.graph._tracing_helpers import (
    emit_score,
    flush_at_node,
    node_span,
    update_trace_metadata,
)
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def planning_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    extra_callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    callbacks = get_callbacks(extra=list(extra_callbacks))
    metrics = state.get(
        "performance_metrics",
        {"step_duration": {}, "llm_latency": {}, "system_info": {}},
    )

    user_request = state["user_request"]
    logger.info("planning_node start", extra={"run_id": run_id})

    with node_span("planning", run_id) as sp:
        rag_client = None
        if state.get("rag_available", False):
            rag_client = RAGClient(base_url=settings.rag_api_url)

        agent = PlanningAgent(
            model_name=settings.ollama_model,
            api_key=settings.ollama_api_key,
            base_url=settings.ollama_base_url,
            rag_client=rag_client,
            callbacks=callbacks,
        )

        with measure_time() as timer:
            plan_result = agent.run(user_request)

        save_scan_configuration(plan_result)

        metrics = update_metrics(metrics, "step_duration", "planning_node", timer())
        checks = plan_result.get("checks_to_scan", []) or []
        groups = plan_result.get("groups_to_scan", []) or []
        top_score = plan_result.get("top_score")
        confidence = plan_result.get("confidence")
        update_trace_metadata(
            **{
                "pdca.plan.checks_count": len(checks),
                "pdca.plan.groups": groups,
                "pdca.plan.fast_track": bool(plan_result.get("fast_track")),
            }
        )
        sp.update(
            output={
                "checks_count": len(checks),
                "groups_count": len(groups),
                "confidence": confidence,
            }
        )
        if isinstance(top_score, (int, float)):
            emit_score(
                run_id,
                "planning_top_score",
                float(top_score),
                comment=f"confidence={confidence}",
            )
        flush_at_node()

    logger.info(
        "planning_node done",
        extra={
            "run_id": run_id,
            "checks": len(checks),
            "groups": len(groups),
        },
    )
    return {
        "assessment_plan": plan_result,
        "performance_metrics": metrics,
    }
