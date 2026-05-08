"""D2(a) -- Deliverable quality rubric for the PDCA report.

Four metrics per run, computed from the chatbot RunSession + maturity KB:

  1. Coverage
       % of seeded check_ids that appear in state.findings.
       Seeded set is the union of all check_ids observed across the runs
       (acts as proxy ground truth -- the bucket is identically degraded
        before each session, so a high-coverage union is the expected set).

  2. Completeness
       Boolean checks that the report exposes the five PDCA artefacts:
         - findings list                  (Detect)
         - prioritised findings + risks   (Analyse)
         - remediation tasks              (Plan)
         - execution logs                 (Apply)
         - verifications                  (Verify)
       And the report itself has status=ready with >= MIN_SECTIONS rendered
       sections. Score = number of artefacts satisfied / 5.

  3. Mapping consistency
       For each finding with controlMappings.mapping populated, compare to
       the canonical KB entry (state_loader.load_maturity_kb). A finding is
       "consistent" when:
         * mapped capability_id matches KB
         * mapped domain matches KB
         * KB review_status is approved
       Score = #consistent / #findings.

  4. Maturity score correctness
       Heuristic: derive expected maturity from finding pass/fail ratio
       using the same domain weighting as MaturityEngine, then compare to
       the score embedded in data/artifacts/final_report.md (only the
       latest run's markdown is on disk -- earlier runs' files were
       overwritten). Output ``maturity_diff = system_score - rubric_score``
       only for runs whose markdown is still accessible; others record
       ``markdown_available=False``.

Usage:
    python benchmarks/holistic_eval/deliverable_quality.py \
        --run-ids-file benchmarks/results/d1_20260505/run_ids.txt \
        --output-dir   benchmarks/results/d1_20260505/holistic
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure relative imports work when invoked as `python benchmarks/holistic_eval/deliverable_quality.py`
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.holistic_eval.state_loader import (  # noqa: E402
    configure_stdout_utf8,
    fetch_all_runs,
    load_maturity_kb,
    load_run_ids,
)

configure_stdout_utf8()

MIN_SECTIONS = 10  # report must have at least this many rendered sections
ARTIFACTS_DIR = ROOT / "data" / "artifacts"


def _final_report_path(run_id: str) -> Path:
    """Per-run markdown path. Falls back to legacy shared path so older
    runs without per-run folders still resolve."""
    per_run = ARTIFACTS_DIR / run_id / "final_report.md"
    if per_run.exists():
        return per_run
    return ARTIFACTS_DIR / "final_report.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _check_ids(findings: list[dict[str, Any]]) -> set[str]:
    return {f.get("prowlerCheckId") for f in findings if f.get("prowlerCheckId")}


def _seeded_union(runs: dict[str, dict[str, Any]]) -> set[str]:
    """Union of all check_ids observed across all runs."""
    seeded: set[str] = set()
    for s in runs.values():
        if "_error" in s:
            continue
        seeded |= _check_ids(s.get("findings") or [])
    return seeded


def _completeness(session: dict[str, Any]) -> tuple[int, dict[str, bool]]:
    """Return (score 0..5, breakdown dict)."""
    findings = session.get("findings") or []
    tasks = session.get("remediationTasks") or []
    logs = session.get("executionLogs") or []
    verifs = session.get("verifications") or []
    report = session.get("report") or {}
    sections = report.get("sections") or []

    breakdown = {
        "detect_findings": len(findings) > 0,
        "analyse_risks": any(
            (f.get("riskFromRag") or f.get("severity") in {"critical", "high", "medium", "low"})
            for f in findings
        ),
        "plan_tasks": len(tasks) > 0,
        "apply_logs": len(logs) > 0,
        "verify_results": len(verifs) > 0,
        "report_ready": (report.get("status") == "ready") and len(sections) >= MIN_SECTIONS,
    }
    # `report_ready` is treated as an additional pass-condition shown alongside
    # the 5 PDCA artefacts. Final score caps at 5; report_ready is reported
    # separately so reviewers can see it if rendering failed.
    score = sum(1 for k in (
        "detect_findings", "analyse_risks", "plan_tasks", "apply_logs", "verify_results"
    ) if breakdown[k])
    return score, breakdown


def _mapping_consistency(findings: list[dict[str, Any]],
                         kb: dict[str, dict[str, Any]]) -> tuple[float, int, int]:
    """Returns (consistent_pct, n_consistent, n_total_with_mapping)."""
    consistent = 0
    total = 0
    for f in findings:
        cid = f.get("prowlerCheckId")
        cm = (f.get("controlMappings") or {}).get("mapping") or {}
        if not cid or not cm:
            continue
        total += 1
        kb_entry = kb.get(cid)
        if not kb_entry:
            continue
        ok_cap = kb_entry.get("capability_id") == cm.get("capability_id")
        ok_dom = kb_entry.get("domain") == cm.get("domain")
        ok_review = kb_entry.get("review_status") == "approved"
        if ok_cap and ok_dom and ok_review:
            consistent += 1
    pct = (100.0 * consistent / total) if total else 0.0
    return pct, consistent, total


# ---------- Maturity score helpers (markdown only available for last run) ----------
# Patterns derived from data/artifacts/final_report.md structure:
#   §7.3 has a "X → Y (+Z)" block — most reliable.
#   prose summary contains "từ A lên B, ... cộng C điểm" — fallback.
_PRE_POST_BLOCK = re.compile(
    r"(\d+\.?\d*)\s*\n\s*(?:→|->)\s*\n\s*(\d+\.?\d*)\s*\n\s*\(\+(\d+\.?\d*)\)",
    re.MULTILINE,
)
_PRE_POST_PROSE = re.compile(
    r"từ\s*(\d+\.?\d*)\s*lên\s*(\d+\.?\d*)[^,]*?cộng\s*(\d+\.?\d*)",
    re.IGNORECASE,
)


def _read_maturity_from_markdown(path: Path) -> dict[str, float | None]:
    """Extract pre/post/delta scores from a generated markdown report.

    Strategy: try §7.3 "pre → post (+delta)" block first (rendered by
    pdca/agents/report_module/exporters); fall back to prose pattern in
    the summary. Returns ``{pre,post,delta}`` with None when absent.
    """
    if not path.exists():
        return {"pre": None, "post": None, "delta": None}
    text = path.read_text(encoding="utf-8", errors="replace")

    m = _PRE_POST_BLOCK.search(text)
    if m:
        pre, post, delta = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return {"pre": pre, "post": post, "delta": delta}

    m = _PRE_POST_PROSE.search(text)
    if m:
        pre, post, delta = float(m.group(1)), float(m.group(2)), float(m.group(3))
        return {"pre": pre, "post": post, "delta": delta}

    return {"pre": None, "post": None, "delta": None}


def _rubric_maturity(findings: list[dict[str, Any]],
                     verifs: list[dict[str, Any]]) -> dict[str, float]:
    """Independent rubric: severity-weighted pass ratio.

    Weight per severity: critical=4, high=3, medium=2, low=1.
    Pre-score  = 100 * (1 - sum(weight_fail)/sum(weight_total)).
    Post-score = 100 * (1 - sum(weight_remaining_fail)/sum(weight_total)),
    where ``weight_remaining_fail`` removes severities of findings that
    have at least one matching verification with result == 'passed'.
    """
    sev_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 1}
    total = sum(sev_weight.get((f.get("severity") or "").lower(), 1) for f in findings) or 1
    fails = total  # before remediation everything is FAIL by construction (group scan on degraded bucket)
    fixed_findings = {
        v.get("findingId") for v in verifs
        if v.get("result") == "passed" and v.get("findingId")
    }
    fail_after = sum(
        sev_weight.get((f.get("severity") or "").lower(), 1)
        for f in findings if f.get("id") not in fixed_findings
    )
    pre = round(100.0 * (1 - fails / total), 2)
    post = round(100.0 * (1 - fail_after / total), 2)
    return {"pre": pre, "post": post, "delta": round(post - pre, 2)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
FIELDS = [
    "run_id", "n_findings",
    "coverage_pct", "covered", "expected",
    "completeness_score", "detect_findings", "analyse_risks", "plan_tasks",
    "apply_logs", "verify_results", "report_ready",
    "mapping_consistency_pct", "mapping_consistent", "mapping_total",
    "maturity_md_available", "maturity_pre_md", "maturity_post_md", "maturity_delta_md",
    "maturity_pre_rubric", "maturity_post_rubric", "maturity_delta_rubric",
    "maturity_diff_post",
    "error",
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-ids-file", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--keep-warmup", action="store_true",
                   help="Don't drop the first run_id from the file")
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_ids = load_run_ids(args.run_ids_file, drop_warmup_first=not args.keep_warmup)
    if not run_ids:
        print("[x] no run_ids loaded", file=sys.stderr)
        return 2
    print(f"[+] evaluating {len(run_ids)} run(s)")

    print("[+] loading maturity KB...")
    kb = load_maturity_kb()
    print(f"    KB indexed by {len(kb)} check_ids")

    print("[+] fetching run sessions from chatbot API...")
    sessions = fetch_all_runs(run_ids)
    seeded = _seeded_union({rid: s for rid, s in sessions.items() if "_error" not in s})
    print(f"    seeded check_ids (union): {len(seeded)}")

    rows: list[dict[str, Any]] = []
    for i, rid in enumerate(run_ids):
        s = sessions[rid]
        row: dict[str, Any] = {k: "" for k in FIELDS}
        row["run_id"] = rid
        if "_error" in s:
            row["error"] = s["_error"]
            rows.append(row)
            continue

        findings = s.get("findings") or []
        verifs = s.get("verifications") or []

        # Coverage
        detected = _check_ids(findings)
        covered = detected & seeded
        cov_pct = (100.0 * len(covered) / len(seeded)) if seeded else 0.0
        row.update({
            "n_findings": len(findings),
            "coverage_pct": round(cov_pct, 2),
            "covered": len(covered),
            "expected": len(seeded),
        })

        # Completeness
        comp_score, breakdown = _completeness(s)
        row["completeness_score"] = comp_score
        row.update({k: int(v) for k, v in breakdown.items()})

        # Mapping consistency
        pct, n_ok, n_tot = _mapping_consistency(findings, kb)
        row["mapping_consistency_pct"] = round(pct, 2)
        row["mapping_consistent"] = n_ok
        row["mapping_total"] = n_tot

        # Maturity rubric (independent) + markdown comparison (last-run only)
        rubric = _rubric_maturity(findings, verifs)
        row["maturity_pre_rubric"] = rubric["pre"]
        row["maturity_post_rubric"] = rubric["post"]
        row["maturity_delta_rubric"] = rubric["delta"]

        # Per-run markdown (after P6: each run has its own folder).
        md_scores = _read_maturity_from_markdown(_final_report_path(rid))
        md_available = md_scores["post"] is not None
        row["maturity_md_available"] = int(md_available)
        if md_available:
            row["maturity_pre_md"] = md_scores["pre"]
            row["maturity_post_md"] = md_scores["post"]
            row["maturity_delta_md"] = md_scores["delta"]
            row["maturity_diff_post"] = round(md_scores["post"] - rubric["post"], 2)

        rows.append(row)

    out_path = out_dir / "deliverable_quality.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[v] wrote {out_path} ({len(rows)} rows)")

    # Compact summary
    print()
    print("=" * 60)
    print("D2(a) Deliverable Quality -- summary")
    print("-" * 60)
    print(f"{'run_id':18s}  cov%  comp/5  map%   mat_post(rubric)  mat_post(md)")
    for r in rows:
        cov = r["coverage_pct"] or "--"
        comp = r["completeness_score"] or "--"
        mp = r["mapping_consistency_pct"] or "--"
        mr = r["maturity_post_rubric"] or "--"
        md = r["maturity_post_md"] or "--"
        print(f"{r['run_id'][:18]:18s}  {cov!s:>5}  {comp!s:>4}/5  {mp!s:>5}  {mr!s:>15}  {md!s:>10}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
