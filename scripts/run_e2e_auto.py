"""
Run full PDCA pipeline end-to-end with auto-approve for all tasks.
No interactive input needed.

Usage:
    python scripts/run_e2e_auto.py "scan all s3 buckets"
    python scripts/run_e2e_auto.py                         # default: scan s3
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdca.orchestrator import build_graph


def run_auto(user_request="scan all s3 buckets"):
    """Run full pipeline with auto-approve for all remediation tasks."""
    app = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("\n" + "=" * 60)
    print(" PDCA SECURITY AGENT — AUTO-APPROVE MODE")
    print(f" Request: {user_request}")
    print("=" * 60)

    initial_input = {
        "user_request": user_request,
        "cycle_iteration": 0,
        "meta": {"user_input": user_request},
        "performance_metrics": {
            "step_duration": {},
            "llm_latency": {},
            "system_info": {"start_time": time.time()},
        },
    }
    current_input = initial_input
    iteration = 0

    while True:
        iteration += 1
        try:
            for event in app.stream(current_input, config=config):
                pass

            snapshot = app.get_state(config)

            if not snapshot.next:
                print(f"\n{'='*60}")
                print(" PIPELINE COMPLETE!")
                print(f"{'='*60}")
                break

            if snapshot.next[0] == "review_task":
                # Auto-approve: get current task, approve it
                state = snapshot.values
                tasks = state.get("remediation_tasks", [])
                idx = state.get("current_task_index", 0)

                if idx < len(tasks):
                    task = tasks[idx]
                    task_id = task["task_id"]
                    tool_name = task.get("tool_name", "unknown")
                    severity = "N/A"

                    # Try to get severity from finding
                    finding_uid = task.get("finding_uid")
                    for f in state.get("prioritized_findings", []):
                        if f.get("finding_uid") == finding_uid:
                            severity = f.get("severity", "N/A")
                            break

                    print(f"\n  [AUTO-APPROVE] Task {idx+1}/{len(tasks)}: "
                          f"{tool_name} (severity={severity})")

                    current_plan = state.get("task_execution_plan", {})
                    current_plan[task_id] = "approve"

                    app.update_state(
                        config,
                        {
                            "task_execution_plan": current_plan,
                            "current_task_index": idx + 1,
                        },
                    )
                else:
                    print(f"  [WARN] Task index {idx} out of range ({len(tasks)} tasks)")

                current_input = None
            else:
                current_input = None

        except Exception as e:
            import traceback
            print(f"\n ERROR: {e}")
            traceback.print_exc()
            break

    # Print results
    try:
        final_state = app.get_state(config).values
        report_path = final_state.get("final_report", {})
        if isinstance(report_path, dict):
            print(f"\n Report outputs:")
            for k, v in report_path.items():
                if v:
                    exists = os.path.exists(v) if v else False
                    size = os.path.getsize(v) if exists else 0
                    print(f"   {k}: {v} ({size:,} bytes)")
        elif report_path:
            print(f"\n Report: {report_path}")

        metrics = final_state.get("performance_metrics", {})
        if metrics.get("step_duration"):
            print(f"\n Step durations:")
            for step, dur in metrics["step_duration"].items():
                print(f"   {step}: {dur:.1f}s")
    except Exception:
        pass


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "scan all s3 buckets"
    run_auto(request)
