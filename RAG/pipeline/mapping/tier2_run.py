"""Tier 2 driver — run all configured proposers over every Prowler check.

Joins Tier 1 signals into each check (so proposers can narrow by
security_domain), runs each proposer independently, and writes proposals
keyed by check_id for Tier 3 consensus.

Output schema (RAG/data/normalized/tier2_proposals.json):
    {
      "<check_id>": {
        "check_id": "...",
        "security_domain": "...",
        "proposers": [
          {"proposer_id": "lexical@v1", "proposals": [Proposal, ...]},
          {"proposer_id": "tfidf_embedding@v1", "proposals": [...]},
        ]
      },
      ...
    }
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import os

from .capability_domain import build_capability_domain_index
from .tier2_proposers.base import Proposer
from .tier2_proposers.lexical_proposer import LexicalProposer
from .tier2_proposers.llm_proposer import (
    EmbeddingProposer,
    LLMProposer,
    LLMInvokeAdapter,
)
from .tier2_proposers.llm_adapters import (
    PromptCache,
    make_invoke_from_env,
)


def _join_tier1_into_check(
    check: Dict[str, Any],
    tier1_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    check_id = check.get("CheckID")
    enriched = dict(check)
    t1 = tier1_index.get(check_id) or {}
    enriched["security_domain"] = t1.get("security_domain")
    enriched["evidence_refs"] = t1.get("evidence_refs", [])
    return enriched


def run_tier2(
    prowler_path: Path,
    capabilities_path: Path,
    tier1_signals_path: Path,
    out_path: Path,
    report_path: Path,
    top_k: int = 5,
) -> Dict[str, Any]:
    with prowler_path.open("r", encoding="utf-8") as f:
        prowler_checks: List[Dict[str, Any]] = json.load(f)
    with capabilities_path.open("r", encoding="utf-8") as f:
        capabilities: List[Dict[str, Any]] = json.load(f)
    with tier1_signals_path.open("r", encoding="utf-8") as f:
        tier1_list: List[Dict[str, Any]] = json.load(f)
    tier1_index = {item["check_id"]: item for item in tier1_list}

    cap_domain_index = build_capability_domain_index(capabilities_path)

    proposers: List[Proposer] = [
        LexicalProposer(capability_domain_index=cap_domain_index),
        EmbeddingProposer(capability_domain_index=cap_domain_index),
    ]

    # LLMProposer is opt-in: only wired when ENABLE_LLM_PROPOSER=1 and an
    # API key is configured. Keeps offline/CI runs deterministic.
    if os.environ.get("ENABLE_LLM_PROPOSER") == "1":
        cache = PromptCache(Path(".cache/llm_proposer_cache.json"))
        invoke_fn, model_id = make_invoke_from_env(cache=cache)
        proposers.append(LLMProposer(
            adapter=LLMInvokeAdapter(invoke_fn=invoke_fn),
            model_id=model_id,
            capability_domain_index=cap_domain_index,
            shortlist_size=15,
        ))

    all_proposals: Dict[str, Dict[str, Any]] = {}
    coverage_per_proposer: Dict[str, int] = Counter()
    no_proposal_checks: List[str] = []
    score_buckets_per_proposer: Dict[str, Counter] = {
        p.proposer_id: Counter() for p in proposers
    }

    for raw_check in prowler_checks:
        check = _join_tier1_into_check(raw_check, tier1_index)
        check_id = check.get("CheckID")
        if not check_id:
            continue

        proposer_outputs = []
        has_any = False
        for proposer in proposers:
            props = proposer.propose(check, capabilities, top_k=top_k)
            if props:
                has_any = True
                coverage_per_proposer[proposer.proposer_id] += 1
                top_score = props[0].score
                bucket = _bucket(top_score)
                score_buckets_per_proposer[proposer.proposer_id][bucket] += 1
            proposer_outputs.append({
                "proposer_id": proposer.proposer_id,
                "proposals": [p.to_dict() for p in props],
            })

        if not has_any:
            no_proposal_checks.append(check_id)

        all_proposals[check_id] = {
            "check_id": check_id,
            "security_domain": check.get("security_domain"),
            "proposers": proposer_outputs,
        }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(all_proposals, f, ensure_ascii=False, indent=2)

    total = len(prowler_checks)
    report = {
        "summary": {
            "total_checks": total,
            "proposers": [p.proposer_id for p in proposers],
            "top_k_per_proposer": top_k,
            "checks_with_zero_proposals": len(no_proposal_checks),
        },
        "coverage_per_proposer": {
            pid: {
                "checks_with_at_least_one": coverage_per_proposer[pid],
                "coverage_pct": round(
                    100 * coverage_per_proposer[pid] / total, 2)
                if total else 0.0,
                "top_score_buckets":
                    dict(score_buckets_per_proposer[pid].most_common()),
            }
            for pid in (p.proposer_id for p in proposers)
        },
        "zero_proposal_sample": no_proposal_checks[:20],
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report


def _bucket(score: float) -> str:
    if score >= 0.70:
        return ">=0.70"
    if score >= 0.50:
        return "0.50-0.70"
    if score >= 0.33:
        return "0.33-0.50"
    if score >= 0.15:
        return "0.15-0.33"
    return "<0.15"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prowler",
                        default="RAG/data/raw/prowler_checks.json", type=Path)
    parser.add_argument("--capabilities",
                        default="RAG/data/normalized/maturity_capabilities.json",
                        type=Path)
    parser.add_argument("--tier1-signals",
                        default="RAG/data/normalized/tier1_upstream_signals.json",
                        type=Path)
    parser.add_argument("--out",
                        default="RAG/data/normalized/tier2_proposals.json",
                        type=Path)
    parser.add_argument("--report",
                        default="RAG/data/normalized/tier2_coverage_report.json",
                        type=Path)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    report = run_tier2(
        prowler_path=args.prowler,
        capabilities_path=args.capabilities,
        tier1_signals_path=args.tier1_signals,
        out_path=args.out,
        report_path=args.report,
        top_k=args.top_k,
    )
    print(json.dumps(report, indent=2))
    print(f"\nProposals written to: {args.out}")
    print(f"Report written to:    {args.report}")


if __name__ == "__main__":
    main()
