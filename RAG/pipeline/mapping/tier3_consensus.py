"""Tier 3 — consensus across Tier 2 proposers.

Reads `tier2_proposals.json` and produces, per check_id, a consensus
decision. No human reviewer is invoked; the only source of trust is
inter-proposer agreement. Outputs:

  - `tier3_consensus.json`: per check, the consensus capability (if any),
    agreement signals (top-1 agreement, top-K overlap, Borda-aggregated
    rank), and a status:
        * "consensus"  — all proposers' rank-1 agree
        * "majority"   — strict majority but not unanimous
        * "weak"       — same capability appears in top-K of every proposer
                         but at different ranks
        * "disputed"   — no capability shared across all proposers' top-K
  - `tier3_disputed.json`: subset where status == "disputed", flagged for
    explicit handling (escalation or known-limitation disclosure).
  - `tier3_report.json`: system-level stats including pairwise Cohen's
    kappa over rank-1 picks.

Consensus is intentionally conservative. The point of Tier 3 is to be
defensible without a reviewer, so we only promote when proposers — built
from independent feature spaces — agree.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Cohen's kappa for two raters over a categorical label set
# ---------------------------------------------------------------------------

def cohen_kappa(labels_a: List[str], labels_b: List[str]) -> float:
    """Cohen's kappa for paired categorical ratings.

    Returns 0.0 when undefined (zero variance) instead of raising — the
    coverage report calls this in bulk and we want a numeric value to log.
    """
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0

    n = len(labels_a)
    agree = sum(1 for x, y in zip(labels_a, labels_b) if x == y)
    p_o = agree / n

    counts_a: Counter = Counter(labels_a)
    counts_b: Counter = Counter(labels_b)
    p_e = sum(
        (counts_a[k] / n) * (counts_b[k] / n)
        for k in set(counts_a) | set(counts_b)
    )
    if p_e >= 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


# ---------------------------------------------------------------------------
# Per-check consensus
# ---------------------------------------------------------------------------

def _top_k_ids(proposals: List[Dict[str, Any]], k: int) -> List[str]:
    return [p["capability_id"] for p in proposals[:k] if p.get("capability_id")]


def _borda_aggregate(
    per_proposer_top_k: List[List[str]],
    k: int,
) -> List[Tuple[str, float]]:
    """Aggregate ranks across proposers using Borda count.

    For each proposer, rank-1 gets k points, rank-2 gets k-1, ..., rank-k
    gets 1. Capabilities not in a proposer's top-k get 0 from that voter.
    Returns capabilities sorted by total points descending.
    """
    scores: Dict[str, float] = defaultdict(float)
    for top_k in per_proposer_top_k:
        for rank, cid in enumerate(top_k, start=1):
            scores[cid] += (k - rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def compute_consensus_for_check(
    check_entry: Dict[str, Any],
    top_k: int = 3,
) -> Dict[str, Any]:
    """Compute consensus signals for a single check.

    `check_entry` is the Tier 2 output for a single check (see tier2_run.py).
    """
    proposers = check_entry.get("proposers", [])
    if not proposers:
        return _empty_consensus(check_entry, reason="no_proposers")

    per_proposer_top_k: List[List[str]] = []
    rank1_per_proposer: List[Optional[str]] = []
    proposer_ids: List[str] = []

    for p in proposers:
        proposer_ids.append(p["proposer_id"])
        proposals = p.get("proposals") or []
        top = _top_k_ids(proposals, top_k)
        per_proposer_top_k.append(top)
        rank1_per_proposer.append(top[0] if top else None)

    if any(t is None for t in rank1_per_proposer):
        return _empty_consensus(check_entry, reason="missing_proposer_output")

    # Top-1 unanimous
    unanimous_top1 = len(set(rank1_per_proposer)) == 1

    # Top-1 majority (strict majority but not unanimous)
    top1_counts = Counter(rank1_per_proposer)
    most_common_top1, most_common_top1_n = top1_counts.most_common(1)[0]
    n_proposers = len(rank1_per_proposer)
    majority_top1 = (
        most_common_top1_n > n_proposers / 2 and not unanimous_top1
    )

    # Top-K intersection across all proposers
    sets = [set(top) for top in per_proposer_top_k]
    intersect = set.intersection(*sets) if sets else set()

    # Borda-aggregated ranking (used as the final "preferred capability")
    borda = _borda_aggregate(per_proposer_top_k, top_k)
    borda_winner = borda[0][0] if borda else None

    # Agreement rate = average pairwise top-1 agreement
    pairs = list(combinations(rank1_per_proposer, 2))
    pairwise_agree = (
        sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else 0.0
    )

    # Classify status
    if unanimous_top1:
        status = "consensus"
        chosen = most_common_top1
    elif majority_top1:
        status = "majority"
        chosen = most_common_top1
    elif intersect:
        status = "weak"
        # Pick the intersection capability with best Borda score
        chosen_candidates = [c for c, _ in borda if c in intersect]
        chosen = chosen_candidates[0] if chosen_candidates else next(iter(intersect))
    else:
        status = "disputed"
        chosen = None

    return {
        "check_id": check_entry.get("check_id"),
        "security_domain": check_entry.get("security_domain"),
        "consensus_status": status,
        "consensus_capability_id": chosen,
        "signals": {
            "proposer_ids": proposer_ids,
            "rank1_per_proposer": rank1_per_proposer,
            "top_k_per_proposer": per_proposer_top_k,
            "top_k_intersection": sorted(intersect),
            "pairwise_top1_agreement_rate": round(pairwise_agree, 4),
            "borda_ranking_top3": [
                {"capability_id": c, "points": round(pts, 2)}
                for c, pts in borda[:3]
            ],
        },
    }


def _empty_consensus(check_entry: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "check_id": check_entry.get("check_id"),
        "security_domain": check_entry.get("security_domain"),
        "consensus_status": "disputed",
        "consensus_capability_id": None,
        "signals": {"reason": reason},
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_tier3(
    proposals_path: Path,
    out_path: Path,
    disputed_path: Path,
    report_path: Path,
    top_k: int = 3,
) -> Dict[str, Any]:
    with proposals_path.open("r", encoding="utf-8") as f:
        proposals: Dict[str, Dict[str, Any]] = json.load(f)

    consensus_records: List[Dict[str, Any]] = []
    disputed_records: List[Dict[str, Any]] = []

    # For system-level kappa we collect each proposer's rank-1 labels in
    # parallel arrays indexed by check.
    proposer_rank1_columns: Dict[str, List[str]] = defaultdict(list)

    for check_id, entry in proposals.items():
        rec = compute_consensus_for_check(entry, top_k=top_k)
        consensus_records.append(rec)
        if rec["consensus_status"] == "disputed":
            disputed_records.append(rec)

        # Collect rank-1 per proposer for kappa
        for p in entry.get("proposers", []):
            pid = p["proposer_id"]
            top1 = (
                p["proposals"][0]["capability_id"]
                if p.get("proposals") else "__none__"
            )
            proposer_rank1_columns[pid].append(top1)

    # System-level pairwise kappa
    proposer_ids = sorted(proposer_rank1_columns.keys())
    pairwise_kappa: Dict[str, float] = {}
    for a, b in combinations(proposer_ids, 2):
        kappa = cohen_kappa(
            proposer_rank1_columns[a], proposer_rank1_columns[b],
        )
        pairwise_kappa[f"{a}__vs__{b}"] = round(kappa, 4)

    status_counts = Counter(r["consensus_status"] for r in consensus_records)
    total = len(consensus_records)

    def pct(n: int) -> float:
        return round(100 * n / total, 2) if total else 0.0

    report = {
        "summary": {
            "total_checks": total,
            "top_k": top_k,
            "proposer_ids": proposer_ids,
            "status_distribution": {
                k: {"count": v, "pct": pct(v)}
                for k, v in status_counts.most_common()
            },
            "promotable_to_active_pct": pct(
                status_counts.get("consensus", 0)
                + status_counts.get("majority", 0)
            ),
        },
        "system_pairwise_cohen_kappa": pairwise_kappa,
        "disputed_sample": [
            r["check_id"] for r in disputed_records[:20]
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(consensus_records, f, ensure_ascii=False, indent=2)
    with disputed_path.open("w", encoding="utf-8") as f:
        json.dump(disputed_records, f, ensure_ascii=False, indent=2)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--proposals",
        default="RAG/data/normalized/tier2_proposals.json",
        type=Path,
    )
    parser.add_argument(
        "--out",
        default="RAG/data/normalized/tier3_consensus.json",
        type=Path,
    )
    parser.add_argument(
        "--disputed",
        default="RAG/data/normalized/tier3_disputed.json",
        type=Path,
    )
    parser.add_argument(
        "--report",
        default="RAG/data/normalized/tier3_report.json",
        type=Path,
    )
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    report = run_tier3(
        proposals_path=args.proposals,
        out_path=args.out,
        disputed_path=args.disputed,
        report_path=args.report,
        top_k=args.top_k,
    )
    print(json.dumps(report, indent=2))
    print(f"\nConsensus written to: {args.out}")
    print(f"Disputed written to:  {args.disputed}")
    print(f"Report written to:    {args.report}")


if __name__ == "__main__":
    main()
