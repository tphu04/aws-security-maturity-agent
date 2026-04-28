from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from pdca.agents.execution_agent import ExecutionAgent
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph._tracing_helpers import flush_at_node, node_span
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def execution_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    metrics = state.get("performance_metrics", {})
    logger.info("execution start", extra={"run_id": run_id})

    with node_span("execution", run_id) as node_sp, measure_time() as timer:
        all_tasks = state.get("remediation_tasks", []) or []
        decisions = state.get("task_execution_plan", {}) or {}
        prioritized_findings = state.get("prioritized_findings", []) or []

        fid_to_uid_map = {
            f["finding_id"]: f["finding_uid"] for f in prioritized_findings
        }

        manual_tasks = [t for t in all_tasks if t.get("manual_required", False)]
        auto_tasks = [t for t in all_tasks if not t.get("manual_required", False)]
        task_to_finding = {t["task_id"]: t["finding_id"] for t in all_tasks}

        pipeline_context = []
        execution_logs = []

        # --- 1) MANUAL ---
        for t in manual_tasks:
            finding_uid = fid_to_uid_map.get(t["finding_id"])
            manual_log = {
                "task_id": t["task_id"],
                "tool_name": t["tool_name"],
                "status": "manual_required",
                "output": {
                    "status": "manual_required",
                    "message": "Requires manual steps.",
                },
                "error": None,
            }
            execution_logs.append(manual_log)
            pipeline_context.append(
                {
                    "task_id": t["task_id"],
                    "finding_uid": finding_uid,
                    "tool_name": t["tool_name"],
                    "tool_params": t["tool_params"],
                    "planner_reasoning": t.get("ai_reasoning"),
                    "manual_required": True,
                    "execution_status": "manual_required",
                    "execution_output": manual_log["output"],
                    "execution_error": None,
                }
            )

        # --- 2) AUTO ---
        if auto_tasks:
            aws_ctx = state.get("aws_context", {}) or {}
            executor = ExecutionAgent(aws_context=aws_ctx)
            auto_tasks_filtered = [
                t for t in auto_tasks if decisions.get(t["task_id"]) == "approve"
            ]
            auto_logs = executor.execute_all(auto_tasks_filtered, decisions)
            execution_logs.extend(auto_logs)

            task_obj_map = {t["task_id"]: t for t in auto_tasks}

            for log in auto_logs:
                task_id = log["task_id"]
                finding_id = task_to_finding.get(task_id)
                finding_uid = fid_to_uid_map.get(finding_id)
                task_info = task_obj_map.get(task_id)

                pipeline_context.append(
                    {
                        "task_id": task_id,
                        "finding_uid": finding_uid,
                        "tool_name": log["tool_name"],
                        "tool_params": task_info["tool_params"] if task_info else {},
                        "planner_reasoning": (
                            task_info.get("ai_reasoning") if task_info else None
                        ),
                        "manual_required": False,
                        "execution_status": (
                            "failed"
                            if log.get("status") == "error"
                            else log.get("status", "not_run")
                        ),
                        "execution_output": log.get("output", {}),
                        "execution_error": log.get("error", None),
                        "execution_timing": {
                            "started_at": log.get("started_at"),
                            "ended_at": log.get("ended_at"),
                            "duration": log.get("duration"),
                        },
                    }
                )

        metrics = update_metrics(metrics, "step_duration", "execution_node", timer())
        success_count = sum(1 for log in execution_logs if log.get("status") == "success")
        failed_count = sum(
            1 for log in execution_logs if log.get("status") in ("failed", "error")
        )
        skipped_count = sum(1 for log in execution_logs if log.get("status") == "skipped")
        node_sp.update(
            output={
                "log_count": len(execution_logs),
                "success": success_count,
                "failed": failed_count,
                "skipped": skipped_count,
            }
        )
        flush_at_node()

    logger.info(
        "execution done",
        extra={"run_id": run_id, "log_count": len(execution_logs)},
    )

    return {
        "execution_logs": execution_logs,
        "pipeline_context": pipeline_context,
        "performance_metrics": metrics,
    }
