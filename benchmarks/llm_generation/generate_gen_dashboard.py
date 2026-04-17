"""
Generate comparison dashboard for Generation Benchmark runs.

Usage:
    python benchmarks/llm_generation/generate_gen_dashboard.py

Reads benchmark run JSON files and produces a Markdown dashboard
comparing 4 configurations: llama3.2 vs qwen3:8b, w/RAG vs no-RAG.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BENCHMARK_DIR / "benchmark_outputs"
CRITERIA_FILE = BENCHMARK_DIR / "release_criteria_gen.json"

# -------------------------------------------------------------------
# Run mapping: label -> benchmark report filename
# Identified by correlating inference_outputs/run_*/run_metadata.json
# with evaluation fingerprints (severity prediction sequences).
#
# llama3.2 w/RAG  = inference run_20260403_101355 -> eval 103853
# llama3.2 no-RAG = inference run_20260403_101900 -> eval 103854
# qwen3:8b no-RAG = inference run_20260403_112326 -> eval 115443
# qwen3:8b w/RAG  = inference run_20260403_120252 -> eval 122819
# -------------------------------------------------------------------
RUN_MAP = {
    "llama3.2 w/RAG":  "gen_benchmark_run_20260403_103853.json",
    "llama3.2 no-RAG": "gen_benchmark_run_20260403_103854.json",
    "qwen3:8b no-RAG": "gen_benchmark_run_20260403_115443.json",
    "qwen3:8b w/RAG":  "gen_benchmark_run_20260403_122819.json",
}

LABELS = ["llama3.2 w/RAG", "llama3.2 no-RAG", "qwen3:8b w/RAG", "qwen3:8b no-RAG"]
MODELS = ["llama3.2", "qwen3:8b"]
CATEGORIES = ["exact", "paraphrase", "semantic_hard", "risk"]
SERVICES = ["s3", "iam", "ec2", "rds", "cloudtrail", "kms"]
SEV_ORDER = ["Critical", "High", "Medium", "Low"]


def load_runs():
    data = {}
    for label, fname in RUN_MAP.items():
        path = OUTPUT_DIR / fname
        with open(path, encoding="utf-8") as f:
            data[label] = json.load(f)
    return data


def load_criteria():
    with open(CRITERIA_FILE, encoding="utf-8") as f:
        return json.load(f)


def fmt(val, mode="pct"):
    if val is None:
        return "—"
    if mode == "pct":
        return f"{val:.1%}"
    if mode == "f4":
        return f"{val:.4f}"
    if mode == "f2":
        return f"{val:.2f}"
    return str(val)


def delta(rag_val, norag_val):
    if rag_val is None or norag_val is None:
        return "—"
    d = rag_val - norag_val
    sign = "+" if d >= 0 else ""
    arrow = "↑" if d > 0.005 else ("↓" if d < -0.005 else "→")
    return f"{sign}{d:.1%} {arrow}"


def build_confusion(cases):
    matrix = {}
    for s in SEV_ORDER:
        matrix[s] = Counter()
    for c in cases:
        pred = c["debug"]["agent_severity"] or "None"
        exp = c["debug"]["expected_severity"]
        if exp in matrix:
            matrix[exp][pred] += 1
    return matrix


def generate_dashboard(data, criteria):
    lines = []
    w = lines.append

    ts = datetime.now(timezone.utc).isoformat()
    w("# Generation Benchmark Dashboard — Model × RAG Comparison")
    w("")
    w(f"**Generated**: {ts}  ")
    w(f"**Cases**: 30 per run | **Categories**: 4 (exact, paraphrase, semantic_hard, risk) | **Services**: 6  ")
    w(f"**Models**: llama3.2:latest, qwen3:8b | **Ablation**: w/RAG vs no-RAG")
    w("")

    # ── 1. Overall Summary ──
    w("## 1. Overall Metrics")
    w("")
    w("| Metric | llama3.2 w/RAG | llama3.2 no-RAG | qwen3:8b w/RAG | qwen3:8b no-RAG |")
    w("|--------|:-:|:-:|:-:|:-:|")

    metrics = [
        ("JSON Parse Rate",        "structure",    "json_parse_rate",            "pct"),
        ("Schema Compliance",      "structure",    "schema_compliance_rate",     "pct"),
        ("Internal Consistency",   "structure",    "internal_consistency_rate",  "pct"),
        ("Faithfulness Mean",      "faithfulness", "mean",                       "f4"),
        ("Severity Accuracy",      "correctness",  "severity_accuracy",         "pct"),
        ("Severity QWK",           "correctness",  "severity_qwk",             "f4"),
        ("Evidence Completeness",  "completeness", "evidence_coverage_mean",    "pct"),
    ]

    for display, section, key, mode in metrics:
        vals = [data[label][section][key] for label in LABELS]
        row = " | ".join(fmt(v, mode) for v in vals)
        w(f"| {display} | {row} |")

    w("")

    # ── 2. RAG Lift Analysis ──
    w("## 2. RAG Lift Analysis")
    w("")
    w("RAG Lift = metric(w/RAG) − metric(no-RAG). Positive = RAG helps.")
    w("")
    w("| Metric | llama3.2 RAG Lift | qwen3:8b RAG Lift |")
    w("|--------|:-:|:-:|")

    lift_metrics = [
        ("Severity Accuracy",     "correctness",  "severity_accuracy"),
        ("Severity QWK",          "correctness",  "severity_qwk"),
        ("Faithfulness",          "faithfulness", "mean"),
        ("Evidence Completeness", "completeness", "evidence_coverage_mean"),
        ("Internal Consistency",  "structure",    "internal_consistency_rate"),
    ]

    for display, section, key in lift_metrics:
        ll_lift = delta(
            data["llama3.2 w/RAG"][section][key],
            data["llama3.2 no-RAG"][section][key],
        )
        qw_lift = delta(
            data["qwen3:8b w/RAG"][section][key],
            data["qwen3:8b no-RAG"][section][key],
        )
        w(f"| {display} | {ll_lift} | {qw_lift} |")

    w("")
    w("> **Key finding**: llama3.2 shows **negative RAG lift** on accuracy (−10.0pp) — RAG context")
    w("> causes severity overestimation. qwen3:8b shows **positive RAG lift** (+6.7pp),")
    w("> demonstrating better utilization of RAG-provided severity guidance.")
    w("")

    # ── 3. Release Criteria ──
    w("## 3. Release Criteria")
    w("")
    criteria_clean = {k: v for k, v in criteria.items() if not k.startswith("_")}
    header = "| Criterion | Threshold | " + " | ".join(LABELS) + " |"
    sep = "|-----------|:-:|" + ":-:|" * len(LABELS)
    w(header)
    w(sep)

    criterion_map = {
        "json_parse_rate_min":             ("structure",    "json_parse_rate"),
        "schema_compliance_rate_min":      ("structure",    "schema_compliance_rate"),
        "faithfulness_mean_min":           ("faithfulness", "mean"),
        "severity_accuracy_min":           ("correctness",  "severity_accuracy"),
        "severity_qwk_min":               ("correctness",  "severity_qwk"),
        "evidence_completeness_mean_min":  ("completeness", "evidence_coverage_mean"),
    }

    for crit_name, threshold in criteria_clean.items():
        if crit_name not in criterion_map:
            continue
        section, key = criterion_map[crit_name]
        cells = []
        for label in LABELS:
            val = data[label][section][key]
            passed = val >= threshold
            status = "PASS" if passed else "**FAIL**"
            cells.append(f"{val:.4f} {status}")
        w(f"| {crit_name} | {threshold:.2f} | " + " | ".join(cells) + " |")

    # Overall verdict per run
    verdicts = []
    for label in LABELS:
        rc = data[label].get("release_criteria", {})
        v = rc.get("verdict", "N/A")
        verdicts.append(f"**{v}**")
    w(f"| **Verdict** | — | " + " | ".join(verdicts) + " |")
    w("")

    # ── 4. By Category ──
    w("## 4. Accuracy by Category")
    w("")
    w("| Category | n | " + " | ".join(LABELS) + " |")
    w("|----------|:-:|" + ":-:|" * len(LABELS))

    for cat in CATEGORIES:
        cells = []
        n = None
        for label in LABELS:
            cat_data = data[label]["by_category"].get(cat, {})
            if n is None:
                n = cat_data.get("total", "?")
            cells.append(fmt(cat_data.get("severity_accuracy"), "pct"))
        w(f"| {cat} | {n} | " + " | ".join(cells) + " |")
    w("")

    w("### Faithfulness by Category")
    w("")
    w("| Category | " + " | ".join(LABELS) + " |")
    w("|----------|" + ":-:|" * len(LABELS))
    for cat in CATEGORIES:
        cells = []
        for label in LABELS:
            cat_data = data[label]["by_category"].get(cat, {})
            cells.append(fmt(cat_data.get("faithfulness_mean"), "f2"))
        w(f"| {cat} | " + " | ".join(cells) + " |")
    w("")

    w("### Completeness by Category")
    w("")
    w("| Category | " + " | ".join(LABELS) + " |")
    w("|----------|" + ":-:|" * len(LABELS))
    for cat in CATEGORIES:
        cells = []
        for label in LABELS:
            cat_data = data[label]["by_category"].get(cat, {})
            cells.append(fmt(cat_data.get("completeness_mean"), "pct"))
        w(f"| {cat} | " + " | ".join(cells) + " |")
    w("")

    # ── 5. By Service ──
    w("## 5. Accuracy by Service")
    w("")
    w("| Service | n | " + " | ".join(LABELS) + " |")
    w("|---------|:-:|" + ":-:|" * len(LABELS))
    for svc in SERVICES:
        cells = []
        n = None
        for label in LABELS:
            svc_data = data[label]["by_service"].get(svc, {})
            if n is None:
                n = svc_data.get("total", "?")
            cells.append(fmt(svc_data.get("severity_accuracy"), "pct"))
        w(f"| {svc} | {n} | " + " | ".join(cells) + " |")
    w("")

    # ── 6. Severity Distribution ──
    w("## 6. Severity Prediction Distribution")
    w("")
    w("Expected distribution: Critical=14, High=4, Medium=6, Low=6")
    w("")
    w("| Severity | Expected | " + " | ".join(LABELS) + " |")
    w("|----------|:-:|" + ":-:|" * len(LABELS))
    for sev in SEV_ORDER:
        cells = []
        exp_count = sum(1 for c in data[LABELS[0]]["cases"]
                        if c["debug"]["expected_severity"] == sev)
        for label in LABELS:
            pred_count = sum(1 for c in data[label]["cases"]
                            if c["debug"]["agent_severity"] == sev)
            cells.append(str(pred_count))
        w(f"| {sev} | {exp_count} | " + " | ".join(cells) + " |")
    w("")

    # ── 7. Per-Case Comparison ──
    w("## 7. Per-Case Severity Predictions")
    w("")
    w("Cases marked with `*` indicate incorrect prediction vs expected.")
    w("")
    w(f"| {'Case ID':30s} | Expected | " + " | ".join(f"{l:15s}" for l in LABELS) + " |")
    w(f"|{'-'*32}|:--------:|" + ":-:|" * len(LABELS))

    ref_cases = data[LABELS[0]]["cases"]
    for i, c in enumerate(ref_cases):
        cid = c["case_id"]
        exp = c["debug"]["expected_severity"]
        cells = []
        for label in LABELS:
            pred = data[label]["cases"][i]["debug"]["agent_severity"]
            if pred == exp:
                cells.append(pred)
            else:
                cells.append(f"**{pred}** ✗")
        w(f"| {cid:30s} | {exp:8s} | " + " | ".join(cells) + " |")
    w("")

    # ── 8. Root Cause Summary ──
    w("## 8. Root Cause Analysis: RAG Lift")
    w("")
    w("### llama3.2 — Negative RAG Lift (−10.0pp accuracy)")
    w("")
    w("| Symptom | Detail |")
    w("|---------|--------|")

    # Count over-predictions for llama w/RAG vs no-RAG
    ll_rag_cases = data["llama3.2 w/RAG"]["cases"]
    ll_norag_cases = data["llama3.2 no-RAG"]["cases"]
    rag_overpredict = sum(
        1 for c in ll_rag_cases
        if SEV_ORDER.index(c["debug"]["agent_severity"] or "Low")
        < SEV_ORDER.index(c["debug"]["expected_severity"])
    )
    norag_overpredict = sum(
        1 for c in ll_norag_cases
        if SEV_ORDER.index(c["debug"]["agent_severity"] or "Low")
        < SEV_ORDER.index(c["debug"]["expected_severity"])
    )
    w(f"| Over-prediction (sev > expected) | w/RAG: {rag_overpredict}/30, no-RAG: {norag_overpredict}/30 |")
    w(f"| Critical over-use | w/RAG: {sum(1 for c in ll_rag_cases if c['debug']['agent_severity']=='Critical')}/30, "
      f"no-RAG: {sum(1 for c in ll_norag_cases if c['debug']['agent_severity']=='Critical')}/30 |")
    w(f"| Internal consistency | w/RAG: {data['llama3.2 w/RAG']['structure']['internal_consistency_rate']:.1%}, "
      f"no-RAG: {data['llama3.2 no-RAG']['structure']['internal_consistency_rate']:.1%} |")
    w("")
    w("**Root cause**: llama3.2 (3B params) struggles to integrate RAG severity guidance.")
    w("When RAG context supplies `official_severity`, the model over-anchors on worst-case")
    w("interpretations, inflating Critical predictions. Without RAG, it relies on its own")
    w("calibration which is paradoxically more accurate for this benchmark.")
    w("")

    w("### qwen3:8b — Positive RAG Lift (+6.7pp accuracy)")
    w("")
    qw_rag_cases = data["qwen3:8b w/RAG"]["cases"]
    qw_norag_cases = data["qwen3:8b no-RAG"]["cases"]

    # Find cases where RAG flipped result
    rag_fixed = []
    rag_broke = []
    for i in range(len(ref_cases)):
        cid = ref_cases[i]["case_id"]
        exp = ref_cases[i]["debug"]["expected_severity"]
        rag_pred = qw_rag_cases[i]["debug"]["agent_severity"]
        norag_pred = qw_norag_cases[i]["debug"]["agent_severity"]
        if rag_pred == exp and norag_pred != exp:
            rag_fixed.append(cid)
        elif rag_pred != exp and norag_pred == exp:
            rag_broke.append(cid)

    w(f"RAG **fixed** {len(rag_fixed)} cases: {', '.join(rag_fixed)}")
    w("")
    if rag_broke:
        w(f"RAG **broke** {len(rag_broke)} cases: {', '.join(rag_broke)}")
        w("")
    w("qwen3:8b (8B params) has sufficient capacity to correctly interpret RAG severity")
    w("hints and adjust predictions accordingly, yielding net positive lift.")
    w("")

    # ── Footer ──
    w("---")
    w(f"*Dashboard generated from benchmark run files on {ts}*  ")
    w(f"*Source files: {', '.join(RUN_MAP.values())}*")

    return "\n".join(lines)


def main():
    data = load_runs()
    criteria = load_criteria()
    md = generate_dashboard(data, criteria)

    out_path = OUTPUT_DIR / "gen_benchmark_dashboard.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Dashboard written to {out_path}")

    # Also print to stdout (handle Windows encoding)
    print()
    try:
        print(md)
    except UnicodeEncodeError:
        print(md.encode("utf-8", errors="replace").decode("utf-8"))


if __name__ == "__main__":
    main()
