"""Evaluate the pipeline against the curated golden set.

Two evaluation surfaces:

  1. Tier 2 — does any proposer (or the combined top-K) hit the expected
     capability? Reports Recall@1, Recall@3, MRR per proposer and combined.

  2. Tier 3 — does the consensus decision match the expected capability?
     Reports Top-1 accuracy on the golden subset, broken down by
     consensus_status (consensus / majority / weak / disputed).

Run:
    python -m RAG.pipeline.mapping.tier4_validation.precision_recall_eval
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _mrr(rank: int) -> float:
    return 1.0 / rank if rank > 0 else 0.0


def eval_tier2(
    golden_path: Path,
    proposals_path: Path,
) -> Dict[str, Any]:
    golden = json.load(golden_path.open("r", encoding="utf-8"))["mappings"]
    proposals: Dict[str, Dict[str, Any]] = json.load(
        proposals_path.open("r", encoding="utf-8"))

    per_proposer: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"hit@1": 0, "hit@3": 0, "hit@5": 0, "rr_sum": 0.0,
                 "evaluated": 0, "missing": 0})
    combined = {"hit@1": 0, "hit@3": 0, "hit@5": 0, "rr_sum": 0.0,
                "evaluated": 0, "missing": 0}

    missing_in_proposals: List[str] = []

    for g in golden:
        cid = g["check_id"]
        expected = g["expected_capability_id"]
        entry = proposals.get(cid)
        if not entry:
            missing_in_proposals.append(cid)
            continue

        combined_top: List[str] = []
        for p in entry.get("proposers", []):
            pid = p["proposer_id"]
            ranks = [pr["capability_id"] for pr in (p.get("proposals") or [])]
            per_proposer[pid]["evaluated"] += 1
            rank = ranks.index(expected) + 1 if expected in ranks else 0
            if rank == 1: per_proposer[pid]["hit@1"] += 1
            if 0 < rank <= 3: per_proposer[pid]["hit@3"] += 1
            if 0 < rank <= 5: per_proposer[pid]["hit@5"] += 1
            per_proposer[pid]["rr_sum"] += _mrr(rank)
            combined_top.extend(ranks)

        # Combined: union of top-K across proposers, preserving first-seen rank
        seen = []
        for c in combined_top:
            if c not in seen:
                seen.append(c)
        rank_c = seen.index(expected) + 1 if expected in seen else 0
        combined["evaluated"] += 1
        if rank_c == 1: combined["hit@1"] += 1
        if 0 < rank_c <= 3: combined["hit@3"] += 1
        if 0 < rank_c <= 5: combined["hit@5"] += 1
        combined["rr_sum"] += _mrr(rank_c)

    def _summarize(d: Dict[str, float]) -> Dict[str, Any]:
        n = d["evaluated"] or 1
        return {
            "evaluated": d["evaluated"],
            "recall@1": round(d["hit@1"] / n, 4),
            "recall@3": round(d["hit@3"] / n, 4),
            "recall@5": round(d["hit@5"] / n, 4),
            "mrr": round(d["rr_sum"] / n, 4),
        }

    return {
        "golden_size": len(golden),
        "missing_in_proposals": missing_in_proposals,
        "per_proposer": {pid: _summarize(d) for pid, d in per_proposer.items()},
        "combined_top_k_union": _summarize(combined),
    }


def eval_tier3(
    golden_path: Path,
    consensus_path: Path,
) -> Dict[str, Any]:
    golden = json.load(golden_path.open("r", encoding="utf-8"))["mappings"]
    consensus_records: List[Dict[str, Any]] = json.load(
        consensus_path.open("r", encoding="utf-8"))
    consensus_by_check = {r["check_id"]: r for r in consensus_records}

    per_status: Dict[str, Counter] = defaultdict(Counter)
    examples_wrong: List[Dict[str, Any]] = []
    total_evaluated = 0
    correct = 0
    missing = 0

    for g in golden:
        cid = g["check_id"]
        expected = g["expected_capability_id"]
        rec = consensus_by_check.get(cid)
        if not rec:
            missing += 1
            continue
        total_evaluated += 1
        status = rec["consensus_status"]
        chosen = rec.get("consensus_capability_id")
        per_status[status]["total"] += 1
        if chosen == expected:
            per_status[status]["correct"] += 1
            correct += 1
        else:
            examples_wrong.append({
                "check_id": cid,
                "expected": expected,
                "chosen": chosen,
                "status": status,
            })

    def _pct(c: Counter) -> Dict[str, Any]:
        total = c["total"] or 1
        return {
            "total": c["total"],
            "correct": c["correct"],
            "accuracy": round(c["correct"] / total, 4),
        }

    return {
        "golden_size": len(golden),
        "evaluated": total_evaluated,
        "missing": missing,
        "top1_accuracy": round(correct / max(total_evaluated, 1), 4),
        "accuracy_by_status": {s: _pct(c) for s, c in per_status.items()},
        "wrong_examples_sample": examples_wrong[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden",
        default="RAG/pipeline/mapping/tier4_validation/golden_set.json",
        type=Path,
    )
    parser.add_argument(
        "--proposals",
        default="RAG/data/normalized/tier2_proposals.json",
        type=Path,
    )
    parser.add_argument(
        "--consensus",
        default="RAG/data/normalized/tier3_consensus.json",
        type=Path,
    )
    parser.add_argument(
        "--out",
        default="RAG/data/normalized/tier4_eval_report.json",
        type=Path,
    )
    args = parser.parse_args()

    report = {
        "tier2": eval_tier2(args.golden, args.proposals),
        "tier3": eval_tier3(args.golden, args.consensus),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
