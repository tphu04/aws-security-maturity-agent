r"""D1 — Aggregate per-session CSVs into a LaTeX table for §6.4.

Reads from --input-dir (the d1_<date>/ folder produced by run_d1_sessions.py
and langfuse_export.py):
  - summary.csv         (mandatory, from run_d1_sessions.py)
  - node_latency.csv    (optional, from langfuse_export.py)
  - llm_calls.csv       (optional, used for token / LLM stats)
  - run_ids.txt         (used to filter warmup sessions when warmup index given)

Outputs (in --input-dir):
  - d1_table.tex        (\begin{table}...\end{table}, ready to \input)
  - d1_report.md        (human-readable, before reviewing the .tex)

Stats reported per node: n, mean_s, std_s, min_s, max_s, p95_s.

Uses only stdlib (no pandas) so it runs on the same venv.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def log(msg: str) -> None:
    print(msg, flush=True)


# Canonical 13 nodes (preserve graph order from pdca/graph/graph.py)
NODE_ORDER = [
    "environment", "planning", "scan_submit", "scan_poll", "scan_collect",
    "risk_evaluation", "rag_enrich", "operational_planning",
    "review_task", "reset_index", "execution", "verification", "report",
]


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p
    lo = int(math.floor(k)); hi = int(math.ceil(k))
    if lo == hi:
        return xs[lo]
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _stats(xs: list[float]) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None, "p95": None}
    return {
        "n": len(xs),
        "mean": statistics.fmean(xs),
        "std": statistics.pstdev(xs) if len(xs) > 1 else 0.0,
        "min": min(xs),
        "max": max(xs),
        "p95": _percentile(xs, 0.95),
    }


# ---------------------------------------------------------------------------
# Load CSVs
# ---------------------------------------------------------------------------
def load_summary(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_node_latency(path: Path) -> dict[str, dict[str, list[float]]]:
    """Return {run_id: {node_name: [duration_s, ...]}} (a node may appear >1x)."""
    out: dict[str, dict[str, list[float]]] = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rid = r.get("run_id") or ""
            node = r.get("node_name") or ""
            ms = _f(r.get("duration_ms"))
            if not (rid and node and ms is not None):
                continue
            out.setdefault(rid, {}).setdefault(node, []).append(ms / 1000.0)
    return out


def load_llm_calls(path: Path) -> dict[str, dict]:
    """Return per-run aggregate: {run_id: {n_calls, total_tokens_in, total_tokens_out, total_cost}}."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rid = r.get("run_id") or ""
            if not rid:
                continue
            agg = out.setdefault(rid, {"n_calls": 0, "in_tok": 0.0, "out_tok": 0.0, "cost": 0.0})
            agg["n_calls"] += 1
            agg["in_tok"] += _f(r.get("input_tokens")) or 0
            agg["out_tok"] += _f(r.get("output_tokens")) or 0
            agg["cost"] += _f(r.get("total_cost")) or 0
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def select_runs(summary: list[dict], drop_warmup: bool, drop_failed: bool) -> list[dict]:
    out = []
    for r in summary:
        if drop_warmup and (r.get("warmup") or "").lower() in ("true", "1", "yes"):
            continue
        if drop_failed and r.get("status") not in ("completed",):
            continue
        out.append(r)
    return out


def aggregate(summary: list[dict],
              node_lat: dict[str, dict[str, list[float]]],
              llm: dict[str, dict]) -> dict:
    run_ids = [r.get("run_id") for r in summary if r.get("run_id")]
    total_durations = [_f(r.get("duration_s")) for r in summary if _f(r.get("duration_s")) is not None]
    findings_counts = [int(r.get("num_findings") or 0) for r in summary]
    tasks_counts = [int(r.get("num_remediation_tasks") or 0) for r in summary]
    approvals_counts = [int(r.get("num_approvals_sent") or 0) for r in summary]

    per_node: dict[str, dict] = {}
    for node in NODE_ORDER:
        # Aggregate per-run sums (a node may execute multiple times per run; we
        # sum within run, then take stats across runs — matches "time spent in
        # node X per session").
        per_run_sums: list[float] = []
        for rid in run_ids:
            durs = (node_lat.get(rid) or {}).get(node) or []
            if durs:
                per_run_sums.append(sum(durs))
        per_node[node] = _stats(per_run_sums)

    selected_run_ids = set(run_ids)
    llm_selected = {rid: v for rid, v in llm.items() if rid in selected_run_ids}

    return {
        "n_runs": len(summary),
        "run_ids": run_ids,
        "total_duration_s": _stats(total_durations),
        "findings": _stats([float(x) for x in findings_counts]),
        "remediation_tasks": _stats([float(x) for x in tasks_counts]),
        "approvals_sent": _stats([float(x) for x in approvals_counts]),
        "per_node_s": per_node,
        "llm_per_run": _stats([v["n_calls"] for v in llm_selected.values()]) if llm_selected else None,
        "tokens_in_per_run": _stats([v["in_tok"] for v in llm_selected.values()]) if llm_selected else None,
        "tokens_out_per_run": _stats([v["out_tok"] for v in llm_selected.values()]) if llm_selected else None,
    }


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def _fmt(v, fmt: str = "{:.2f}") -> str:
    if v is None:
        return "--"
    try:
        return fmt.format(float(v))
    except Exception:
        return str(v)


def render_markdown(agg: dict, run_ids: list[str], cfg: dict) -> str:
    lines = []
    lines.append(f"# D1 -- End-to-end PDCA timing\n")
    lines.append(f"- Runs aggregated: **{agg['n_runs']}**")
    lines.append(f"- Bucket: `{cfg.get('bucket', '?')}`")
    lines.append(f"- Decision at HITL: `{cfg.get('decision', '?')}`")
    lines.append(f"- Prompt: `{cfg.get('prompt', '?')}`")
    lines.append(f"- Generated: {datetime.utcnow().isoformat()}Z\n")

    td = agg["total_duration_s"]
    lines.append("## Total duration")
    lines.append(f"| metric | n | mean (s) | std (s) | min | max | p95 |")
    lines.append(f"|---|---|---|---|---|---|---|")
    lines.append(f"| total | {td['n']} | {_fmt(td['mean'])} | {_fmt(td['std'])} "
                 f"| {_fmt(td['min'])} | {_fmt(td['max'])} | {_fmt(td['p95'])} |")
    lines.append("")

    lines.append("## Per-node duration (seconds)")
    lines.append("| node | n | mean | std | min | max | p95 |")
    lines.append("|---|---|---|---|---|---|---|")
    for node in NODE_ORDER:
        s = agg["per_node_s"][node]
        lines.append(
            f"| `{node}` | {s['n']} | {_fmt(s['mean'])} | {_fmt(s['std'])} "
            f"| {_fmt(s['min'])} | {_fmt(s['max'])} | {_fmt(s['p95'])} |"
        )
    lines.append("")

    lines.append("## Workload summary (per run)")
    fs = agg["findings"]; ts = agg["remediation_tasks"]; aps = agg["approvals_sent"]
    lines.append("| metric | n | mean | std | min | max |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(f"| findings | {fs['n']} | {_fmt(fs['mean'], '{:.1f}')} | {_fmt(fs['std'], '{:.1f}')} | {_fmt(fs['min'], '{:.0f}')} | {_fmt(fs['max'], '{:.0f}')} |")
    lines.append(f"| remediation tasks | {ts['n']} | {_fmt(ts['mean'], '{:.1f}')} | {_fmt(ts['std'], '{:.1f}')} | {_fmt(ts['min'], '{:.0f}')} | {_fmt(ts['max'], '{:.0f}')} |")
    lines.append(f"| approvals sent | {aps['n']} | {_fmt(aps['mean'], '{:.1f}')} | {_fmt(aps['std'], '{:.1f}')} | {_fmt(aps['min'], '{:.0f}')} | {_fmt(aps['max'], '{:.0f}')} |")
    lines.append("")

    if agg.get("llm_per_run"):
        l = agg["llm_per_run"]; ti = agg["tokens_in_per_run"]; to = agg["tokens_out_per_run"]
        lines.append("## LLM activity (per run)")
        lines.append("| metric | n | mean | std | min | max |")
        lines.append("|---|---|---|---|---|---|")
        lines.append(f"| LLM calls | {l['n']} | {_fmt(l['mean'], '{:.1f}')} | {_fmt(l['std'], '{:.1f}')} | {_fmt(l['min'], '{:.0f}')} | {_fmt(l['max'], '{:.0f}')} |")
        lines.append(f"| input tokens | {ti['n']} | {_fmt(ti['mean'], '{:.0f}')} | {_fmt(ti['std'], '{:.0f}')} | {_fmt(ti['min'], '{:.0f}')} | {_fmt(ti['max'], '{:.0f}')} |")
        lines.append(f"| output tokens | {to['n']} | {_fmt(to['mean'], '{:.0f}')} | {_fmt(to['std'], '{:.0f}')} | {_fmt(to['min'], '{:.0f}')} | {_fmt(to['max'], '{:.0f}')} |")
        lines.append("")

    lines.append("## Run IDs")
    for rid in run_ids:
        lines.append(f"- `{rid}`")
    return "\n".join(lines)


def render_latex(agg: dict, cfg: dict) -> str:
    """Render booktabs table for §6.4 (versioning convention §1.6 -> _v2)."""
    n = agg["n_runs"]
    td = agg["total_duration_s"]
    bucket = cfg.get("bucket", "?")
    date = datetime.utcnow().strftime("%Y-%m-%d")

    lines: list[str] = []
    lines.append(r"% Auto-generated by scripts/aggregate_d1.py -- do not edit by hand.")
    lines.append(r"% Source: benchmarks/results/d1_<date>/summary.csv + node_latency.csv (Langfuse).")
    lines.append(r"\begin{table}[H]")
    lines.append(r"  \centering")
    # Vietnamese caption uses utf-8 directly (report is compiled with babel/vntex).
    lines.append(
        r"  \caption{Thống kê thời gian thực thi pipeline PDCA trên "
        f"$N={n}$ phiên (loại trừ phiên warm-up). "
        f"Nguồn: trace Langfuse export ngày {date}, bucket \\texttt{{{bucket.replace('_', r'\_')}}}.}}"
    )
    lines.append(r"  \label{tab:pdca_timing_v2}")
    lines.append(r"  \small")
    lines.append(r"  \begin{tabular}{lrrrrrr}")
    lines.append(r"    \toprule")
    lines.append(
        r"    \textbf{Node} & \textbf{n} & \textbf{Mean (s)} & \textbf{Std (s)} & "
        r"\textbf{Min (s)} & \textbf{Max (s)} & \textbf{p95 (s)} \\"
    )
    lines.append(r"    \midrule")
    for node in NODE_ORDER:
        s = agg["per_node_s"][node]
        node_tex = node.replace("_", r"\_")
        lines.append(
            f"    \\texttt{{{node_tex}}} & {s['n']} & "
            f"{_fmt(s['mean'])} & {_fmt(s['std'])} & {_fmt(s['min'])} & "
            f"{_fmt(s['max'])} & {_fmt(s['p95'])} \\\\"
        )
    lines.append(r"    \midrule")
    lines.append(
        f"    \\textbf{{Tổng cộng}} & {td['n']} & {_fmt(td['mean'])} & "
        f"{_fmt(td['std'])} & {_fmt(td['min'])} & {_fmt(td['max'])} & {_fmt(td['p95'])} \\\\"
    )
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input-dir", required=True, help="d1_<date>/ folder")
    p.add_argument("--keep-warmup", action="store_true", help="Include warmup session in aggregates")
    p.add_argument("--keep-failed", action="store_true", help="Include status != completed")
    args = p.parse_args()

    in_dir = Path(args.input_dir)
    if not in_dir.exists():
        log(f"--input-dir not found: {in_dir}")
        return 2

    summary = load_summary(in_dir / "summary.csv")
    if not summary:
        log("summary.csv is missing or empty")
        return 2

    selected = select_runs(summary, drop_warmup=not args.keep_warmup,
                                     drop_failed=not args.keep_failed)
    if not selected:
        log("No sessions selected after filtering (all warmup or non-completed?)")
        return 2

    log(f"Loaded {len(summary)} sessions; aggregating {len(selected)} after filters.")

    node_lat = load_node_latency(in_dir / "node_latency.csv")
    llm = load_llm_calls(in_dir / "llm_calls.csv")

    agg = aggregate(selected, node_lat, llm)

    # Load run_config.json (best-effort) for context on prompt/bucket/decision.
    cfg_path = in_dir / "run_config.json"
    cfg = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    md = render_markdown(agg, [r.get("run_id") for r in selected if r.get("run_id")], cfg)
    tex = render_latex(agg, cfg)

    (in_dir / "d1_report.md").write_text(md, encoding="utf-8")
    (in_dir / "d1_table.tex").write_text(tex, encoding="utf-8")
    (in_dir / "d1_aggregate.json").write_text(
        json.dumps(agg, indent=2, default=str), encoding="utf-8")

    log(f"  wrote: {in_dir / 'd1_report.md'}")
    log(f"  wrote: {in_dir / 'd1_table.tex'}")
    log(f"  wrote: {in_dir / 'd1_aggregate.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
