from __future__ import annotations

import logging
from typing import Dict, List

from langchain_core.runnables import RunnableConfig

from pdca.agents.analysis_agent import AnalysisAgent
from pdca.agents.rescan_agent import RescanAgent
from pdca.graph._metrics import measure_time, update_metrics
from pdca.graph.state import PDCAState

logger = logging.getLogger(__name__)


def _aggregate_pipeline_data(
    state: PDCAState, pipeline_context: List[Dict]
) -> List[Dict]:
    remediation_tasks = state.get("remediation_tasks", []) or []
    execution_logs = state.get("execution_logs", []) or []
    prioritized = state.get("prioritized_findings", []) or []

    fid_to_uid = {f["finding_id"]: f["finding_uid"] for f in prioritized}
    tid_to_log = {l["task_id"]: l for l in execution_logs}
    tid_to_ctx = {c["task_id"]: c for c in pipeline_context if c.get("task_id")}

    out: List[Dict] = []
    for task in remediation_tasks:
        t_id = task["task_id"]
        f_id = task["finding_id"]
        f_uid = fid_to_uid.get(f_id)
        if not f_uid:
            continue

        ctx = tid_to_ctx.get(t_id)
        exec_log = tid_to_log.get(t_id)

        if ctx:
            final_status = ctx["execution_status"]
            final_output = ctx["execution_output"]
            final_error = ctx.get("execution_error")
            manual = ctx["manual_required"]
        else:
            final_status = exec_log.get("status", "not_run") if exec_log else "not_run"
            final_output = exec_log.get("output", {}) if exec_log else {}
            final_error = exec_log.get("error") if exec_log else None
            manual = task.get("manual_required", False)

        out.append(
            {
                "finding_uid": f_uid,
                "task_id": t_id,
                "tool_name": task["tool_name"],
                "tool_params": task["tool_params"],
                "planner_reasoning": task.get("ai_reasoning"),
                "manual_required": manual,
                "execution_status": final_status,
                "execution_output": final_output,
                "execution_error": final_error,
                "execution_timing": ctx.get("execution_timing") if ctx else None,
            }
        )
    return out


def verification_node(state: PDCAState, config: RunnableConfig) -> dict:
    run_id = state.get("run_id", "")
    metrics = state.get("performance_metrics", {})
    logger.info("verification start", extra={"run_id": run_id})

    with measure_time() as timer:
        # 1) Rescan — reuse plan via state instead of file coupling.
        plan = state.get("assessment_plan") or {}
        rescan_config = {
            "groups_to_scan": plan.get("groups_to_scan", []),
            "checks_to_scan": plan.get("checks_to_scan", []),
            "reasoning": plan.get("reasoning", ""),
        }
        rescan = RescanAgent(config=rescan_config)
        post_pkg = rescan.run()

        # 2) Pre-scan: read from state — `scan_collect` always sets it.
        pre_scan = state.get("pre_scan_snapshot") or {"findings": []}

        # 3) Aggregate execution data.
        pipeline_context = _aggregate_pipeline_data(
            state, state.get("pipeline_context", []) or []
        )

        # 4) Analyze diff.
        analyzer = AnalysisAgent()
        analysis_results = analyzer.run(
            pre_scan=pre_scan,
            post_scan=post_pkg,
            pipeline_context=pipeline_context,
        )

    metrics = update_metrics(metrics, "step_duration", "verification_node", timer())
    logger.info("verification done", extra={"run_id": run_id})

    return {
        "verification_results": analysis_results.get("diff_result", []),
        "analysis_results": analysis_results,
        "post_scan_snapshot": post_pkg,
        "performance_metrics": metrics,
    }
