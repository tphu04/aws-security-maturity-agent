"""Apply statistics module to existing benchmark outputs and emit
LaTeX-ready tables + JSON summary for Chapter 6 revision.

Inputs (read-only):
  benchmarks/results/d1_20260506/summary.csv          # 5-session timing
  benchmarks/results/d1_20260506/node_latency.csv     # per-node mean/std
  benchmarks/llm_generation/results/ablation_mvp.json # Report Agent 4 conditions × 30 cases
  benchmarks/rag/benchmark_outputs/benchmark_checks_report.json   # 63 RAG cases (hybrid)
  benchmarks/rag/benchmark_outputs/benchmark_maturity_report.json # 9 RAG maturity cases

Outputs:
  benchmarks/results/d1_20260506/stats/timing_ci.json
  benchmarks/results/d1_20260506/stats/report_ablation_ci.json
  benchmarks/results/d1_20260506/stats/rag_hybrid_ci.json
  benchmarks/results/d1_20260506/stats/summary.md
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from stats import (
    bootstrap_ci,
    bootstrap_ci_proportion,
    cv_with_ci,
    mcnemar_test,
)

ROOT = Path(__file__).resolve().parents[2]
D1_DIR = ROOT / "benchmarks" / "results" / "d1_20260506"
OUT = D1_DIR / "stats"
OUT.mkdir(exist_ok=True)


def fmt_pct(x: float) -> str:
    return f"{100*x:.1f}\\%"


def fmt_ci(d: dict, scale: float = 1.0, suffix: str = "") -> str:
    return f"{d['mean']*scale:.2f}{suffix} [{d['ci_low']*scale:.2f}, {d['ci_high']*scale:.2f}]"


# ===========================================================================
# 1. Timing CI on 5 D1 sessions
# ===========================================================================
def analyze_timing():
    rows = []
    with open(D1_DIR / "summary.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["status"] == "completed":
                rows.append(float(r["duration_s"]))
    ci = bootstrap_ci(rows)
    cv = cv_with_ci(rows)
    out = {
        "metric": "duration_s",
        "n_sessions": len(rows),
        "values": rows,
        "mean_ci": ci,
        "cv_ci": cv,
    }
    (OUT / "timing_ci.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


# ===========================================================================
# 2. Per-node CI
# ===========================================================================
def analyze_per_node():
    """Compute CI for each node's mean latency across 5 sessions."""
    by_node: dict[str, list[float]] = {}
    with open(D1_DIR / "node_latency.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            node = r.get("node_name") or r.get("node")
            try:
                latency_s = float(r["duration_ms"]) / 1000.0
            except (KeyError, ValueError, TypeError):
                continue
            by_node.setdefault(node, []).append(latency_s)
    out = {}
    for n, vals in by_node.items():
        if len(vals) >= 3:
            out[n] = {"values": vals, **bootstrap_ci(vals)}
    (OUT / "node_latency_ci.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


# ===========================================================================
# 3. Report Agent ablation: 4 conditions × 30 cases
#    Compare full_mvp vs baseline on key binary-ish metrics.
# ===========================================================================
def analyze_report_ablation():
    src = ROOT / "benchmarks" / "llm_generation" / "results" / "ablation_mvp.json"
    if not src.exists():
        return None
    data = json.loads(src.read_text(encoding="utf-8"))
    by_cond = {r["condition"]: r for r in data["results"]}

    # Per-case metrics: extract structure_pass_rate, numerical_faithfulness, capability_grounding_rate
    metrics = ["structure_pass_rate", "numerical_faithfulness", "capability_grounding_rate", "off_scope_mention_rate"]
    out = {"per_condition": {}, "comparisons": {}}

    for cond, r in by_cond.items():
        per_metric = {}
        for m in metrics:
            vals = []
            for c in r["cases"]:
                v = c.get("metrics", {}).get(m, {}).get("score")
                if v is None:
                    continue
                vals.append(float(v))
            if vals:
                per_metric[m] = bootstrap_ci(vals)
                per_metric[m]["values_count"] = len(vals)
        out["per_condition"][cond] = per_metric

    # Pairwise McNemar on binary success per case (use numerical_faithfulness >= 0.95)
    THRESH = 0.95
    for m in metrics:
        if m == "off_scope_mention_rate":
            # Lower-is-better; compare baseline vs full_mvp using "==0" criterion
            criterion = lambda v: 1 if v == 0.0 else 0
        else:
            criterion = lambda v: 1 if v >= THRESH else 0
        baseline_bin, full_bin = [], []
        case_ids_b = {c["case_id"]: criterion(c["metrics"].get(m, {}).get("score", 0.0))
                      for c in by_cond.get("baseline", {}).get("cases", [])}
        case_ids_f = {c["case_id"]: criterion(c["metrics"].get(m, {}).get("score", 0.0))
                      for c in by_cond.get("full_mvp", {}).get("cases", [])}
        common = sorted(set(case_ids_b) & set(case_ids_f))
        if not common:
            continue
        for cid in common:
            baseline_bin.append(case_ids_b[cid])
            full_bin.append(case_ids_f[cid])
        out["comparisons"][f"baseline_vs_full_mvp__{m}"] = {
            "n": len(common),
            "criterion": ("==0" if m == "off_scope_mention_rate" else f">={THRESH}"),
            "mcnemar": mcnemar_test(baseline_bin, full_bin),
            "baseline_mean": sum(baseline_bin) / len(baseline_bin),
            "full_mvp_mean": sum(full_bin) / len(full_bin),
        }

    (OUT / "report_ablation_ci.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


# ===========================================================================
# 4. RAG retrieval (Hybrid) — per-query CI on Top-1, Top-5, MRR, NDCG
# ===========================================================================
def analyze_rag_hybrid():
    files = [
        ROOT / "benchmarks" / "rag" / "benchmark_outputs" / "benchmark_checks_report.json",
        ROOT / "benchmarks" / "rag" / "benchmark_outputs" / "benchmark_maturity_report.json",
    ]
    out = {"per_file": {}, "combined": {}}
    combined = {"hit_top1": [], "hit_top5": [], "reciprocal_rank": [], "ndcg@5": []}
    for f in files:
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        per_file = {"hit_top1": [], "hit_top5": [], "reciprocal_rank": [], "ndcg@5": []}
        for c in d["cases"]:
            # Skip negative cases (no expected doc)
            if c.get("expected_doc_id") in (None, ""):
                continue
            for k in per_file:
                v = c.get(k)
                if v is None:
                    continue
                # Bool → int
                if isinstance(v, bool):
                    v = int(v)
                per_file[k].append(float(v))
                combined[k].append(float(v))
        out["per_file"][f.name] = {
            k: {**bootstrap_ci(v), "n": len(v)} for k, v in per_file.items() if v
        }
    out["combined"] = {
        k: {**bootstrap_ci(v), "n": len(v)} for k, v in combined.items() if v
    }
    (OUT / "rag_hybrid_ci.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


# ===========================================================================
# Markdown summary
# ===========================================================================
def emit_markdown(timing, per_node, report_abl, rag):
    lines = ["# Stats summary — Chapter 6 evaluation\n"]
    lines.append("Generated by `benchmarks/holistic_eval/apply_stats.py`. ")
    lines.append("Bootstrap CI: 10000 iters, percentile, alpha=0.05, seed=42.\n")

    lines.append("## 1. End-to-end timing (5 D1 sessions, broad-scan group s3)\n")
    t = timing["mean_ci"]
    lines.append(f"- duration: **{t['mean']:.1f}s** [{t['ci_low']:.1f}, {t['ci_high']:.1f}], n={t['n']}, σ={t['std']:.1f}")
    lines.append(f"- CV: {timing['cv_ci']['cv']*100:.2f}% [{timing['cv_ci']['ci_low']*100:.2f}%, {timing['cv_ci']['ci_high']*100:.2f}%]\n")

    if rag and rag.get("combined"):
        lines.append("## 2. RAG hybrid retrieval (combined 72 valid cases)\n")
        for k, c in rag["combined"].items():
            lines.append(f"- {k}: **{c['mean']:.4f}** [{c['ci_low']:.4f}, {c['ci_high']:.4f}], n={c['n']}")
        lines.append("")

    if report_abl:
        lines.append("## 3. Report Agent ablation (n=30 per condition)\n")
        for cond, ms in report_abl["per_condition"].items():
            lines.append(f"### {cond}")
            for m, c in ms.items():
                lines.append(f"- {m}: {c['mean']:.4f} [{c['ci_low']:.4f}, {c['ci_high']:.4f}]")
            lines.append("")
        lines.append("### Pairwise: baseline vs full_mvp (McNemar exact, paired)")
        for k, comp in report_abl["comparisons"].items():
            lines.append(
                f"- {k}: n_disc={comp['mcnemar']['n_discordant']}, "
                f"p={comp['mcnemar']['p_value']:.4f} "
                f"(baseline={comp['baseline_mean']:.3f}, full_mvp={comp['full_mvp_mean']:.3f})"
            )

    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    print("[1/4] Timing CI...")
    t = analyze_timing()
    print("  mean=", t["mean_ci"]["mean"], "CI=", (t["mean_ci"]["ci_low"], t["mean_ci"]["ci_high"]))

    print("[2/4] Per-node CI...")
    pn = analyze_per_node()
    print("  nodes:", len(pn))

    print("[3/4] Report ablation CI + McNemar...")
    ra = analyze_report_ablation()
    if ra:
        print("  conditions:", list(ra["per_condition"].keys()))

    print("[4/4] RAG hybrid CI...")
    rg = analyze_rag_hybrid()
    if rg.get("combined"):
        print("  combined metrics:", list(rg["combined"].keys()))

    emit_markdown(t, pn, ra, rg)
    print("\nDone. Output dir:", OUT)


if __name__ == "__main__":
    main()
