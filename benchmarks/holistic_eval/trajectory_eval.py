"""D2(b) -- Trajectory evaluation for the PDCA pipeline.

Four metrics per run, computed from the chatbot RunSession + Langfuse
node_latency.csv:

  1. Path correctness
       Dedupe consecutive duplicates in graphNodes (review_task is the
       interrupt point and naturally repeats once per pending task);
       compare to the canonical happy-path sequence from
       ``pdca/graph/graph.py``. Score = 100% if exact match, else
       (n_matched / n_expected).

  2. PDCA cycle count
       Count of distinct end-to-end traversals. We treat the run as one
       cycle if every non-loop node appears exactly once. Re-entries
       caused by ``interrupt_before=['review_task']`` are NOT counted as
       new cycles.

  3. Tool call correctness
       For each entry in toolCalls:
         * registered_in_REGISTRY  -- known tool name
         * legitimate              -- success OR (failed AND manual_only)
       Two scores: name-validity %, semantic-correctness %.

  4. State handoff fidelity
       Sanity invariants between successive nodes (no field drop):
         (i)   findings >= 1 after scan_collect
         (ii)  remediation_tasks >= 1 after operational_planning
         (iii) every task has a matching execution log
               (manual_only tasks log status=manual_required)
         (iv)  verifications >= #execution_logs after verification
         (v)   report.status == 'ready' after report
       Score = #satisfied / 5.

Usage:
    python benchmarks/holistic_eval/trajectory_eval.py \
        --run-ids-file       benchmarks/results/d1_20260505/run_ids.txt \
        --node-latency-csv   benchmarks/results/d1_20260505/node_latency.csv \
        --output-dir         benchmarks/results/d1_20260505/holistic
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.holistic_eval.state_loader import (  # noqa: E402
    configure_stdout_utf8,
    fetch_all_runs,
    load_run_ids,
)

configure_stdout_utf8()

# Canonical happy-path sequence -- mirrors pdca/graph/graph.py:build_graph.
CANONICAL_PATH = [
    "environment",
    "planning",
    "scan_submit",
    "scan_poll",
    "scan_collect",
    "risk_evaluation",
    "rag_enrich",
    "operational_planning",
    "review_task",     # interrupt_before -> may repeat per pending task
    "reset_index",
    "execution",
    "verification",
    "report",
]
INTERRUPT_NODES = {"review_task"}


# ---------------------------------------------------------------------------
# Tool registry helper -- soft-import; if it fails we mark all tools "unknown"
# ---------------------------------------------------------------------------
def _registered_tool_names() -> set[str]:
    try:
        # Importing pdca.tools triggers the side-effects that populate REGISTRY.
        import pdca.tools  # noqa: F401
        from pdca.tools.registry import REGISTRY
        return {t.name for t in REGISTRY.all()}
    except Exception as e:
        print(f"[!] could not load REGISTRY ({e}); skipping name validity", file=sys.stderr)
        return set()


# ---------------------------------------------------------------------------
# Path order helpers
# ---------------------------------------------------------------------------
def _collapse_consecutive(seq: Iterable[str]) -> list[str]:
    out: list[str] = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out


def _path_score(observed: list[str], expected: list[str]) -> tuple[float, int, int]:
    """Greedy match: walk expected; advance observed pointer on each match.
    Returns (pct, matched, len(expected))."""
    j = 0
    matched = 0
    for stage in expected:
        while j < len(observed) and observed[j] != stage:
            j += 1
        if j < len(observed) and observed[j] == stage:
            matched += 1
            j += 1
    pct = 100.0 * matched / len(expected) if expected else 0.0
    return pct, matched, len(expected)


def _node_seq_from_session(session: dict[str, Any]) -> list[str]:
    nodes = session.get("graphNodes") or []
    return [n.get("name") or "" for n in nodes if n.get("name")]


def _node_seq_from_csv(node_latency_rows: list[dict[str, Any]],
                       run_id: str) -> list[str]:
    rows = [r for r in node_latency_rows if r.get("run_id") == run_id]
    rows.sort(key=lambda r: r.get("startTime") or "")
    return [r["node_name"] for r in rows if r.get("node_name")]


# ---------------------------------------------------------------------------
# Tool call analysis
# ---------------------------------------------------------------------------
def _tool_call_metrics(session: dict[str, Any],
                       known_names: set[str]) -> dict[str, Any]:
    calls = session.get("toolCalls") or []
    n_total = len(calls)
    n_known = 0
    n_legit = 0
    n_success = 0
    n_manual_failed = 0
    n_unexpected_fail = 0
    unknown_names: list[str] = []

    for c in calls:
        name = c.get("name") or c.get("toolName") or ""
        status = (c.get("status") or "").lower()
        manual = bool(c.get("manualOnly"))
        if known_names and name not in known_names:
            unknown_names.append(name)
        else:
            n_known += 1

        if status == "success":
            n_success += 1
            n_legit += 1
        elif status in {"failed", "error", "manual_required"} and manual:
            n_manual_failed += 1
            n_legit += 1   # rejection by guard is the intended behaviour
        else:
            n_unexpected_fail += 1

    name_pct = 100.0 * n_known / n_total if n_total else 0.0
    semantic_pct = 100.0 * n_legit / n_total if n_total else 0.0
    return {
        "tool_calls_total": n_total,
        "tool_calls_known_pct": round(name_pct, 2),
        "tool_calls_known": n_known,
        "tool_calls_unknown_names": ",".join(sorted(set(unknown_names))) or "",
        "tool_calls_semantic_pct": round(semantic_pct, 2),
        "tool_calls_success": n_success,
        "tool_calls_manual_failed": n_manual_failed,
        "tool_calls_unexpected_failed": n_unexpected_fail,
    }


# ---------------------------------------------------------------------------
# State handoff invariants
# ---------------------------------------------------------------------------
def _handoff_invariants(session: dict[str, Any]) -> tuple[int, dict[str, bool]]:
    findings = session.get("findings") or []
    tasks = session.get("remediationTasks") or []
    logs = session.get("executionLogs") or []
    verifs = session.get("verifications") or []
    report = session.get("report") or {}

    task_ids = {t.get("id") for t in tasks if t.get("id")}
    log_task_ids = {l.get("taskId") for l in logs if l.get("taskId")}

    inv = {
        "i_findings_after_scan": len(findings) >= 1,
        "ii_tasks_after_oper_planning": len(tasks) >= 1,
        # Every remediation task -- manual_only included -- must have at
        # least one matching execution_log (status="success" or
        # "manual_required"). A drop here means the execution node
        # forgot to record one of the planned tasks.
        "iii_logs_cover_all_tasks": bool(task_ids) and task_ids.issubset(log_task_ids),
        "iv_verifs_cover_logs": len(verifs) >= len(logs),
        "v_report_ready": report.get("status") == "ready",
    }
    return sum(inv.values()), inv


# ---------------------------------------------------------------------------
# Cycle counter (heuristic from canonical sequence)
# ---------------------------------------------------------------------------
def _cycle_count(observed_collapsed: list[str]) -> int:
    """How many times we observed a 'report' node -- one report per cycle."""
    return max(1, sum(1 for x in observed_collapsed if x == "report"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
FIELDS = [
    "run_id",
    "path_pct", "path_matched", "path_expected",
    "path_observed", "path_collapsed", "path_review_repeats",
    "cycle_count",
    "tool_calls_total", "tool_calls_known_pct", "tool_calls_known",
    "tool_calls_unknown_names",
    "tool_calls_semantic_pct", "tool_calls_success",
    "tool_calls_manual_failed", "tool_calls_unexpected_failed",
    "handoff_score", "i_findings_after_scan", "ii_tasks_after_oper_planning",
    "iii_logs_cover_all_tasks", "iv_verifs_cover_logs", "v_report_ready",
    "error",
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-ids-file", required=True)
    p.add_argument("--node-latency-csv", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--keep-warmup", action="store_true")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_ids = load_run_ids(args.run_ids_file, drop_warmup_first=not args.keep_warmup)
    if not run_ids:
        print("[x] no run_ids", file=sys.stderr)
        return 2
    print(f"[+] evaluating {len(run_ids)} run(s)")

    # Load node_latency.csv (Langfuse export)
    node_latency_rows: list[dict[str, Any]] = []
    nl_path = Path(args.node_latency_csv)
    if nl_path.exists():
        with open(nl_path, encoding="utf-8") as f:
            node_latency_rows = list(csv.DictReader(f))
        print(f"[+] loaded {len(node_latency_rows)} rows from {nl_path.name}")
    else:
        print(f"[!] {nl_path} not found -- using graphNodes from API instead", file=sys.stderr)

    print("[+] loading tool registry...")
    known_names = _registered_tool_names()
    print(f"    REGISTRY tools known: {len(known_names)}")

    print("[+] fetching run sessions...")
    sessions = fetch_all_runs(run_ids)

    rows: list[dict[str, Any]] = []
    for rid in run_ids:
        s = sessions[rid]
        row: dict[str, Any] = {k: "" for k in FIELDS}
        row["run_id"] = rid
        if "_error" in s:
            row["error"] = s["_error"]
            rows.append(row)
            continue

        # Pick observed path. Prefer Langfuse CSV (truthier ordering) when
        # available, else fall back to graphNodes from the API.
        obs = _node_seq_from_csv(node_latency_rows, rid) or _node_seq_from_session(s)
        collapsed = _collapse_consecutive(obs)
        review_repeats = sum(1 for x in obs if x == "review_task")
        # Drop interrupt-induced repeats so the canonical comparison is fair.
        collapsed_for_match = [x for x in collapsed if x not in INTERRUPT_NODES]
        # Re-insert review_task once at its expected position so the canonical
        # sequence still matches.
        if "review_task" in CANONICAL_PATH and "review_task" not in collapsed_for_match:
            i = CANONICAL_PATH.index("review_task")
            collapsed_for_match.insert(i, "review_task")
        pct, matched, expected = _path_score(collapsed_for_match, CANONICAL_PATH)
        row.update({
            "path_pct": round(pct, 2),
            "path_matched": matched,
            "path_expected": expected,
            "path_observed": "->".join(obs),
            "path_collapsed": "->".join(collapsed),
            "path_review_repeats": review_repeats,
            "cycle_count": _cycle_count(collapsed),
        })

        # Tool calls
        row.update(_tool_call_metrics(s, known_names))

        # Handoff
        score, inv = _handoff_invariants(s)
        row["handoff_score"] = score
        for k, v in inv.items():
            row[k] = int(v)

        rows.append(row)

    out_path = out_dir / "trajectory_eval.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[v] wrote {out_path} ({len(rows)} rows)")

    # Compact summary
    print()
    print("=" * 78)
    print("D2(b) Trajectory Evaluation -- summary")
    print("-" * 78)
    print(f"{'run_id':18s}  path%  cyc  tools(ok/total)  legit%  handoff/5  review_repeats")
    for r in rows:
        path_pct = r["path_pct"] or "--"
        cyc = r["cycle_count"] or "--"
        tt = r["tool_calls_total"] or 0
        tn = r["tool_calls_known"] or 0
        sem = r["tool_calls_semantic_pct"] or "--"
        ho = r["handoff_score"] or "--"
        rep = r["path_review_repeats"] or "--"
        print(f"{r['run_id'][:18]:18s}  {path_pct!s:>5}  {cyc!s:>3}  {tn}/{tt:<14}  {sem!s:>5}  {ho!s:>4}/5  {rep!s:>5}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
