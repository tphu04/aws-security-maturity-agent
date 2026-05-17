"""Tier 4 invariant tests — sanity rules that any mapping artifact must
satisfy regardless of how it was generated.

These are pure assertions; they do NOT replace human review but catch the
classes of bug that "self-review" pipelines historically miss (e.g. an S3
encryption check mapping to a Bedrock GenAI capability because both
mention "data protection").

Three families of invariants:
  1. Reference integrity — every check_id and capability_id exists in
     the corresponding catalog.
  2. Domain alignment — the chosen capability's security_domain must
     match the check's security_domain (with allowed exceptions list).
  3. Banned entity-gate pairs — specific check_id patterns must never
     map to specific capability_id patterns.

Run:
    python -m RAG.pipeline.mapping.tier4_validation.invariant_tests \\
        --mappings RAG/data/normalized/maturity_mappings.v2.json
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..capability_domain import build_capability_domain_index


# (check_id_pattern, capability_id_pattern, reason)
# These encode the "obvious wrong" mappings discovered during the v1 pipeline.
_BANNED_PAIRS = [
    (
        re.compile(r"^s3_.*(encryption|encrypt)"),
        re.compile(r"bedrock|generative|gen[\-_]?ai|sagemaker"),
        "S3 encryption checks must not map to GenAI/Bedrock capabilities.",
    ),
    (
        re.compile(r"^iam_.*(mfa|password)"),
        re.compile(r"backup|disaster|resilience|redundancy"),
        "Identity authentication checks must not map to resilience capabilities.",
    ),
    (
        # Only fire when check is logging-config WITHOUT encryption intent.
        # e.g. cloudtrail_multi_region_enabled -> encryption_at_rest is wrong,
        # but cloudtrail_kms_encryption_enabled -> encryption_at_rest is fine.
        re.compile(r"^(cloudtrail|cloudwatch_log)(?!.*encrypt)(?!.*kms).*"),
        re.compile(r"^(data_)?encryption_(at_rest|in_transit)$"),
        "Pure logging-config checks must not map to encryption capabilities.",
    ),
    (
        re.compile(r"^guardduty_|^inspector_"),
        re.compile(r"data_encryption|backup|multi_factor"),
        "Threat-detection service checks must not map to data/auth capabilities.",
    ),
]


@dataclass
class InvariantViolation:
    rule: str
    check_id: str
    capability_id: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule": self.rule,
            "check_id": self.check_id,
            "capability_id": self.capability_id,
            "detail": self.detail,
        }


def load_check_ids(prowler_path: Path) -> set[str]:
    with prowler_path.open("r", encoding="utf-8") as f:
        return {str(c.get("CheckID")) for c in json.load(f) if c.get("CheckID")}


def load_capability_ids(capabilities_path: Path) -> set[str]:
    with capabilities_path.open("r", encoding="utf-8") as f:
        return {
            str(c.get("capability_id"))
            for c in json.load(f) if c.get("capability_id")
        }


def load_check_domains(tier1_signals_path: Path) -> Dict[str, Optional[str]]:
    with tier1_signals_path.open("r", encoding="utf-8") as f:
        signals = json.load(f)
    return {s["check_id"]: s.get("security_domain") for s in signals}


def check_reference_integrity(
    mappings: List[Dict[str, Any]],
    check_ids: set[str],
    capability_ids: set[str],
) -> List[InvariantViolation]:
    violations: List[InvariantViolation] = []
    for m in mappings:
        cid = m.get("check_id")
        cap = m.get("capability_id")
        if cid not in check_ids:
            violations.append(InvariantViolation(
                rule="reference_integrity.unknown_check",
                check_id=str(cid), capability_id=str(cap),
                detail=f"check_id '{cid}' not found in Prowler catalog",
            ))
        if cap not in capability_ids:
            violations.append(InvariantViolation(
                rule="reference_integrity.unknown_capability",
                check_id=str(cid), capability_id=str(cap),
                detail=f"capability_id '{cap}' not found in capability catalog",
            ))
    return violations


def check_domain_alignment(
    mappings: List[Dict[str, Any]],
    check_domains: Dict[str, Optional[str]],
    capability_domain_index: Dict[str, Optional[str]],
) -> List[InvariantViolation]:
    """Flag mappings whose check and capability disagree on security_domain.

    None on either side is treated as "unknown, allow" — we'd rather miss a
    real mismatch than block legitimate mappings whose domain was simply
    not inferable from text.
    """
    violations: List[InvariantViolation] = []
    for m in mappings:
        cid = m.get("check_id")
        cap = m.get("capability_id")
        check_dom = check_domains.get(cid)
        cap_dom = capability_domain_index.get(cap)
        if check_dom and cap_dom and check_dom != cap_dom:
            violations.append(InvariantViolation(
                rule="domain_alignment.cross_domain",
                check_id=str(cid), capability_id=str(cap),
                detail=(
                    f"check security_domain='{check_dom}' but capability "
                    f"security_domain='{cap_dom}'"
                ),
            ))
    return violations


def check_banned_pairs(
    mappings: List[Dict[str, Any]],
) -> List[InvariantViolation]:
    violations: List[InvariantViolation] = []
    for m in mappings:
        cid = str(m.get("check_id", ""))
        cap = str(m.get("capability_id", ""))
        for check_pat, cap_pat, reason in _BANNED_PAIRS:
            if check_pat.search(cid) and cap_pat.search(cap):
                violations.append(InvariantViolation(
                    rule="banned_entity_gate",
                    check_id=cid, capability_id=cap,
                    detail=reason,
                ))
    return violations


def run_all(
    mappings_path: Path,
    prowler_path: Path,
    capabilities_path: Path,
    tier1_signals_path: Path,
) -> Dict[str, Any]:
    with mappings_path.open("r", encoding="utf-8") as f:
        mappings: List[Dict[str, Any]] = json.load(f)

    check_ids = load_check_ids(prowler_path)
    capability_ids = load_capability_ids(capabilities_path)
    check_domains = load_check_domains(tier1_signals_path)
    cap_domain_index = build_capability_domain_index(capabilities_path)

    ref_v = check_reference_integrity(mappings, check_ids, capability_ids)
    dom_v = check_domain_alignment(mappings, check_domains, cap_domain_index)
    ban_v = check_banned_pairs(mappings)

    all_violations = ref_v + dom_v + ban_v
    return {
        "total_mappings": len(mappings),
        "violations_by_family": {
            "reference_integrity": [v.to_dict() for v in ref_v],
            "domain_alignment": [v.to_dict() for v in dom_v],
            "banned_entity_gate": [v.to_dict() for v in ban_v],
        },
        "violation_counts": {
            "reference_integrity": len(ref_v),
            "domain_alignment": len(dom_v),
            "banned_entity_gate": len(ban_v),
            "total": len(all_violations),
        },
        "passed": len(all_violations) == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mappings",
        default="RAG/data/normalized/maturity_mappings.v2.json",
        type=Path,
    )
    parser.add_argument(
        "--prowler",
        default="RAG/data/raw/prowler_checks.json",
        type=Path,
    )
    parser.add_argument(
        "--capabilities",
        default="RAG/data/normalized/maturity_capabilities.json",
        type=Path,
    )
    parser.add_argument(
        "--tier1-signals",
        default="RAG/data/normalized/tier1_upstream_signals.json",
        type=Path,
    )
    args = parser.parse_args()

    report = run_all(
        mappings_path=args.mappings,
        prowler_path=args.prowler,
        capabilities_path=args.capabilities,
        tier1_signals_path=args.tier1_signals,
    )

    summary = {
        "total_mappings": report["total_mappings"],
        "violation_counts": report["violation_counts"],
        "passed": report["passed"],
    }
    print(json.dumps(summary, indent=2))
    if not report["passed"]:
        print("\nSample violations (first 5 per family):")
        for family, v_list in report["violations_by_family"].items():
            if v_list:
                print(f"\n[{family}]")
                for v in v_list[:5]:
                    print(f"  - {v['check_id']} -> {v['capability_id']}: {v['detail']}")


if __name__ == "__main__":
    main()
