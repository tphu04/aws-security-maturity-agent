from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.remediate_planner_agent import RemediationPlannerAgent
from pdca.config import settings
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def remediation_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    callbacks = (
        config.get("callbacks")
        or config.get("configurable", {}).get("callbacks", [])
        or []
    )
    metrics = state.get("performance_metrics", {})
    aws_ctx = state.get("aws_context", {}) or {}

    logger.info("remediation start", extra={"run_id": run_id})

    planner = RemediationPlannerAgent(
        settings.ollama_model,
        settings.ollama_api_key,
        settings.ollama_base_url,
        aws_context=aws_ctx,
        callbacks=callbacks,
    )

    with measure_time() as timer:
        findings = [
            f for f in state.get("prioritized_findings", []) if f.get("status") == "FAIL"
        ]
        generated_plans = planner.plan_remediation(findings)

        tasks = []
        for i, plan in enumerate(generated_plans, 1):
            tasks.append(
                {
                    "task_id": f"task_{i}",
                    "finding_id": plan["finding_id"],
                    "tool_name": plan["tool_name"],
                    "tool_params": plan["tool_params"],
                    "description": plan.get("description", ""),
                    "priority": 1,
                    "ai_reasoning": plan.get("reasoning", ""),
                    "manual_required": plan.get("manual_required", False),
                }
            )

    llm_metrics = planner.get_llm_metrics()
    metrics = update_metrics(metrics, "step_duration", "operational_planning_node", timer())
    metrics = update_metrics(
        metrics, "llm_latency", "remediation_planner_agent", llm_metrics
    )

    logger.info(
        "remediation done", extra={"run_id": run_id, "task_count": len(tasks)}
    )
    return {
        "remediation_tasks": tasks,
        "task_execution_plan": {},
        "current_task_index": 0,
        "performance_metrics": metrics,
    }
