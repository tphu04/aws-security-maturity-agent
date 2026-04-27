"""Thin CLI wrapper around `pdca.graph.graph.build_graph` (Phase C7).

All node implementations, routing functions and helpers were moved to
`pdca.graph.*`. This module keeps only:
- `build_graph()` — re-export for backward-compat callers (tests, scripts).
- `run_interactive_session()` + `handle_task_review_interaction()` — CLI loop.
- `build_report_data()` / `_extract_post_findings()` — thin wrappers around
  `ReportDataBuilder` for legacy tests; will be deleted after Phase D.
"""

from __future__ import annotations

import time
import uuid

from dotenv import load_dotenv

from pdca.graph.graph import build_graph
from pdca.tools import REGISTRY

load_dotenv()


# ---------------------------------------------------------------------------
# Legacy thin wrappers (kept for tests — `tests/test_report_rebuild.py`
# and `tests/test_orchestrator_maturity.py` import these directly).
# ---------------------------------------------------------------------------


def build_report_data(
    analysis: dict, aws_context: dict, plan: dict, user_request: str
) -> dict:
    from pdca.agents.report_module.data_builder import ReportDataBuilder

    return ReportDataBuilder.build_context(analysis, aws_context, plan, user_request)


def _extract_post_findings(analysis: dict) -> list:
    from pdca.agents.report_module.data_builder import ReportDataBuilder

    return ReportDataBuilder._extract_post_findings(analysis)


# ---------------------------------------------------------------------------
# CLI: per-task HITL review loop
# ---------------------------------------------------------------------------


def handle_task_review_interaction(app, config) -> None:
    """Pause-time interaction handler: prints the pending task and asks for
    approval/skip via stdin. Updates state via `app.update_state(...)`.
    """
    snapshot = app.get_state(config)
    state = snapshot.values

    idx = state["current_task_index"]
    tasks = [
        t for t in state["remediation_tasks"] if not t.get("manual_required", False)
    ]
    prioritized_findings = state.get("prioritized_findings", [])

    if idx >= len(tasks):
        return

    task = tasks[idx]
    tool_name = task["tool_name"]

    tool_obj = REGISTRY.get(tool_name)
    description = tool_obj.description if tool_obj else "Tool description not found."

    finding_id = task["finding_id"]
    finding = next(
        (f for f in prioritized_findings if f["finding_id"] == finding_id), None
    )

    print("\n" + "=" * 60)
    print(f"  REVIEWING TASK [{idx + 1}/{len(tasks)}]")
    print(f"  Task ID    : {task['task_id']}")
    if finding:
        print(f"  Finding ID : {finding['finding_id']}")
        print(f"  Service    : {finding.get('service', 'N/A')}")
        print(f"  Resource   : {finding.get('resource_id', 'N/A')}")
        print(f"  Region     : {finding.get('region', 'N/A')}")
        print(f"  Severity   : {finding.get('severity', 'N/A')}")
        compliance = finding.get("compliance", [])
        print(f"  Compliance : {', '.join(compliance) if compliance else 'N/A'}")
        print(f"  Risk Score : {finding.get('risk_score', 'N/A')}")
        print(f"  Description: {finding.get('description', '')[:200]}...")
    print(f"  Tool       : {tool_name}")
    print(f"  Description: {description}")
    print(f"  Params     : {task['tool_params']}")
    print(f"  AI Reasoning: {task.get('ai_reasoning', 'N/A')}")
    print("=" * 60)

    choice = input("   [Y]es (run) / [N]o (skip): ").strip().lower()
    decision = "approve" if choice in ("y", "yes") else "skip"
    print(f"   -> Saved: {decision.upper()}")

    current_plan = state.get("task_execution_plan", {})
    current_plan[task["task_id"]] = decision

    app.update_state(
        config,
        {
            "task_execution_plan": current_plan,
            "current_task_index": idx + 1,
        },
    )


def run_interactive_session() -> None:
    app = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("\n" + "=" * 50)
    print("  PDCA SECURITY AGENT — INTERACTIVE SESSION")
    print("=" * 50)

    user_request_text = input(
        " Enter your request (e.g. Scan S3, Check IAM users...): "
    ).strip()
    if not user_request_text:
        user_request_text = "Scan my AWS environment"
        print(f"   (default: '{user_request_text}')")

    initial_input = {
        "run_id": thread_id,
        "user_request": user_request_text,
        "cycle_iteration": 0,
        "performance_metrics": {
            "step_duration": {},
            "llm_latency": {},
            "system_info": {"start_time": time.time()},
        },
    }
    current_input = initial_input

    while True:
        try:
            for _event in app.stream(current_input, config=config):
                pass

            snapshot = app.get_state(config)
            if not snapshot.next:
                print("\n  Pipeline completed.")
                break

            if snapshot.next[0] == "review_task":
                handle_task_review_interaction(app, config)
                current_input = None
            else:
                current_input = None
        except Exception as e:
            import traceback

            print(f" Error in main loop: {e}")
            traceback.print_exc()
            break


if __name__ == "__main__":
    run_interactive_session()
