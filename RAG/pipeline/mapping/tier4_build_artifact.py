"""Build the final mapping artifact from Tier 1-3 outputs.

The artifact is a drop-in for `RAG/data/normalized/maturity_mappings.json`
read by `MappingService`. Backward-compatible: legacy fields (`check_id`,
`capability_id`, `mapping_confidence`, `mapping_type`, `mapping_reason`,
`review_status`) are preserved so `MappingService` and downstream agents
work unchanged. New fields (`status`, `evidence_refs`, `consensus`,
`provenance`, `lifecycle`) are additive and only consumed by tooling that
opts in.

Promotion policy:
  - consensus_status == "consensus"           -> status="active", review_status="auto_high"
  - consensus_status == "majority"            -> status="active_majority", review_status="review_required"
  - consensus_status == "weak"                -> status="proposed", review_status="review_required"
  - consensus_status == "disputed"            -> NOT emitted into mappings artifact;
                                                 these check_ids are written to a
                                                 separate disputed file so they
                                                 cannot enter production silently.

The `MappingService.filter_for_agent_context` already restricts to
`approved/reviewed/auto_high` — combined with this policy, only consensus
mappings reach agents.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .capability_domain import build_capability_domain_index


PIPELINE_VERSION = "rebuild-pipeline@v2.0"
LIFECYCLE_REVIEW_WINDOW_DAYS = 180


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_review_due() -> str:
    return (datetime.now(timezone.utc)
            + timedelta(days=LIFECYCLE_REVIEW_WINDOW_DAYS)).isoformat()


def _load(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _index_prowler(prowler: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {c["CheckID"]: c for c in prowler if c.get("CheckID")}


def _index_capabilities(caps: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {c["capability_id"]: c for c in caps if c.get("capability_id")}


def _index_tier1(t1: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s["check_id"]: s for s in t1}


def _build_consensus_block(cons_rec: Dict[str, Any]) -> Dict[str, Any]:
    sig = cons_rec.get("signals", {}) or {}
    proposer_ids = sig.get("proposer_ids") or []
    rank1 = sig.get("rank1_per_proposer") or []
    agreement = sig.get("pairwise_top1_agreement_rate")
    return {
        "status_signal": cons_rec.get("consensus_status"),
        "voters": proposer_ids,
        "rank1_per_voter": rank1,
        "pairwise_top1_agreement_rate": agreement,
        "top_k_intersection": sig.get("top_k_intersection") or [],
        "borda_ranking_top3": sig.get("borda_ranking_top3") or [],
    }


def _build_provenance_block(check_id: str) -> Dict[str, Any]:
    return {
        "generated_by": PIPELINE_VERSION,
        "generated_at": _utc_now_iso(),
        "source_check_id": check_id,
    }


def _build_lifecycle_block() -> Dict[str, Any]:
    return {
        "status": "active",
        "supersedes": None,
        "next_review_due": _next_review_due(),
    }


def _confidence_from_status(consensus_status: str) -> str:
    return {
        "consensus": "high",
        "majority": "medium",
        "weak": "low",
        "disputed": "low",
    }.get(consensus_status, "low")


def _review_status_from_status(consensus_status: str) -> str:
    return {
        "consensus": "auto_high",
        "majority": "review_required",
        "weak": "review_required",
    }.get(consensus_status, "review_required")


def _mapping_type_from_status(consensus_status: str) -> str:
    return {
        "consensus": "direct",
        "majority": "related",
        "weak": "weak",
    }.get(consensus_status, "weak")


def _build_retrieval_text(check: Dict[str, Any], cap: Dict[str, Any]) -> str:
    parts = [
        check.get("CheckID") or "",
        check.get("ServiceName") or "",
        cap.get("capability_id") or "",
        cap.get("capability_name") or "",
        (cap.get("summary") or "")[:200],
    ]
    return "\n".join(p for p in parts if p)


def build_mapping_record(
    *,
    check_id: str,
    consensus_rec: Dict[str, Any],
    check: Dict[str, Any],
    capability: Dict[str, Any],
    tier1_signal: Dict[str, Any],
) -> Dict[str, Any]:
    status_signal = consensus_rec.get("consensus_status")
    capability_id = consensus_rec.get("consensus_capability_id")
    capability_name = capability.get("capability_name") or ""
    service = (check.get("ServiceName") or "").strip().lower()
    domain = tier1_signal.get("security_domain")
    evidence_refs = tier1_signal.get("evidence_refs") or []

    confidence = _confidence_from_status(status_signal)
    review_status = _review_status_from_status(status_signal)
    mapping_type = _mapping_type_from_status(status_signal)

    record: Dict[str, Any] = {
        # --- legacy fields consumed by MappingService ---
        "doc_id": f"mapping:{check_id}:{capability_id}",
        "doc_type": "maturity_mapping",
        "source_name": "tier1_4_consensus_pipeline",
        "source_type": "automated_consensus",
        "source_uri": "",
        "version": "2.0",
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "language": "en",
        "tags": [],
        "index_version": "rag-v6-2026-05-17",
        "retrieval_text": _build_retrieval_text(check, capability),
        "embedding_text": _build_retrieval_text(check, capability),
        "reranker_text": _build_retrieval_text(check, capability),
        "check_id": check_id,
        "provider": "aws",
        "service": service or None,
        "domain": domain,
        "capability_id": capability_id,
        "capability_name": capability_name,
        "mapping_confidence": confidence,
        "mapping_reason": _build_reason_text(consensus_rec, evidence_refs),
        "review_status": review_status,
        "reviewed_by": None,
        "mapping_type": mapping_type,
        "assessment_weight_hint": None,
        "report_note": None,
        # --- new schema additions ---
        "status": (
            "active" if status_signal == "consensus"
            else ("active_majority" if status_signal == "majority"
                  else "proposed")
        ),
        "evidence_refs": evidence_refs,
        "consensus": _build_consensus_block(consensus_rec),
        "provenance": _build_provenance_block(check_id),
        "lifecycle": _build_lifecycle_block(),
    }
    return record


def _build_reason_text(
    consensus_rec: Dict[str, Any],
    evidence_refs: List[Dict[str, Any]],
) -> str:
    sig = consensus_rec.get("signals", {}) or {}
    agreement = sig.get("pairwise_top1_agreement_rate")
    voters = sig.get("proposer_ids") or []
    parts: List[str] = []

    if agreement is not None:
        parts.append(
            f"Selected via {len(voters)}-proposer consensus "
            f"(pairwise top-1 agreement={agreement})."
        )
    if evidence_refs:
        sources = sorted({r.get("source") for r in evidence_refs if r.get("source")})
        if sources:
            parts.append(
                f"Supported by framework references: {', '.join(sources)}."
            )
    if not parts:
        parts.append("Auto-generated mapping from rebuild pipeline.")
    return " ".join(parts)


def run_build(
    *,
    prowler_path: Path,
    capabilities_path: Path,
    tier1_signals_path: Path,
    consensus_path: Path,
    out_path: Path,
    excluded_path: Path,
    report_path: Path,
) -> Dict[str, Any]:
    prowler_index = _index_prowler(_load(prowler_path))
    capability_index = _index_capabilities(_load(capabilities_path))
    tier1_index = _index_tier1(_load(tier1_signals_path))
    consensus_records: List[Dict[str, Any]] = _load(consensus_path)

    cap_domain_index = build_capability_domain_index(capabilities_path)

    mappings: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    counts = Counter()

    for cons in consensus_records:
        check_id = cons.get("check_id")
        cap_id = cons.get("consensus_capability_id")
        status = cons.get("consensus_status")
        counts[f"input.{status}"] += 1

        if status == "disputed" or not cap_id:
            excluded.append({
                "check_id": check_id,
                "reason": "disputed_or_no_capability",
                "consensus_status": status,
                "signals": cons.get("signals"),
            })
            counts["excluded.disputed"] += 1
            continue

        check = prowler_index.get(check_id)
        capability = capability_index.get(cap_id)
        if not check or not capability:
            excluded.append({
                "check_id": check_id,
                "reason": "missing_in_catalog",
                "consensus_status": status,
                "capability_id": cap_id,
            })
            counts["excluded.missing"] += 1
            continue

        tier1_signal = tier1_index.get(check_id) or {}
        record = build_mapping_record(
            check_id=check_id,
            consensus_rec=cons,
            check=check,
            capability=capability,
            tier1_signal=tier1_signal,
        )
        mappings.append(record)
        counts[f"emitted.{record['status']}"] += 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
    with excluded_path.open("w", encoding="utf-8") as f:
        json.dump(excluded, f, ensure_ascii=False, indent=2)

    report = {
        "summary": {
            "input_total": sum(counts[k] for k in counts if k.startswith("input.")),
            "emitted_total": len(mappings),
            "excluded_total": len(excluded),
            "by_bucket": dict(counts.most_common()),
        },
        "policy": {
            "pipeline_version": PIPELINE_VERSION,
            "lifecycle_review_window_days": LIFECYCLE_REVIEW_WINDOW_DAYS,
            "promotion_rules": {
                "consensus": "status=active, review_status=auto_high, confidence=high",
                "majority": "status=active_majority, review_status=review_required, confidence=medium",
                "weak": "status=proposed, review_status=review_required, confidence=low",
                "disputed": "EXCLUDED — disclosed in tier4_excluded_disputed.json",
            },
        },
        "artifact_paths": {
            "mappings": str(out_path),
            "excluded": str(excluded_path),
        },
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


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
    parser.add_argument("--consensus",
                        default="RAG/data/normalized/tier3_consensus.json",
                        type=Path)
    parser.add_argument("--out",
                        default="RAG/data/normalized/maturity_mappings.json",
                        type=Path)
    parser.add_argument("--excluded",
                        default="RAG/data/normalized/tier4_excluded_disputed.json",
                        type=Path)
    parser.add_argument("--report",
                        default="RAG/data/normalized/tier4_build_report.json",
                        type=Path)
    args = parser.parse_args()

    report = run_build(
        prowler_path=args.prowler,
        capabilities_path=args.capabilities,
        tier1_signals_path=args.tier1_signals,
        consensus_path=args.consensus,
        out_path=args.out,
        excluded_path=args.excluded,
        report_path=args.report,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
