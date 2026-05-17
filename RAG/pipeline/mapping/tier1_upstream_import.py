"""Tier 1 — Upstream framework import.

Goal: extract authoritative compliance signals embedded in Prowler raw data
(CheckType, Categories, AdditionalURLs) and emit two artifacts:

  1. evidence_refs per check_id — list of {source, ref, url} pointing to
     authoritative frameworks (NIST 800-53, CIS AWS Foundations, AWS FSBP,
     PCI-DSS, HIPAA, ISO 27001).
  2. derived security_domain per check_id — coarse domain label
     (data_protection, logging_monitoring, identity_access, network,
     resilience, threat_detection, vulnerability_management, gen_ai) used
     downstream by Tier 2/3 to narrow capability candidates.

This module is read-only over RAG/data/raw/prowler_checks.json and is the
input layer for the rebuild pipeline. It does NOT touch
RAG/data/normalized/maturity_mappings.json.

Run:
    python -m RAG.pipeline.mapping.tier1_upstream_import \\
        --prowler RAG/data/raw/prowler_checks.json \\
        --out RAG/data/normalized/tier1_upstream_signals.json \\
        --report RAG/data/normalized/tier1_coverage_report.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


# ---------------------------------------------------------------------------
# Framework reference extractors
# ---------------------------------------------------------------------------

# Prowler bundles framework hints inside the free-text CheckType taxonomy.
# We parse them out into structured refs. Patterns intentionally permissive
# because Prowler text is inconsistent (e.g. "NIST 800-53 Controls (USA)").

_FRAMEWORK_PATTERNS = [
    ("nist_800_53", re.compile(r"NIST\s*800[\-_ ]?53", re.IGNORECASE)),
    ("nist_csf", re.compile(r"NIST\s*CSF", re.IGNORECASE)),
    ("cis_aws", re.compile(r"CIS\s*AWS\s*Foundations", re.IGNORECASE)),
    ("aws_fsbp", re.compile(
        r"AWS\s*Foundational\s*Security\s*Best\s*Practices", re.IGNORECASE)),
    ("aws_security_best_practices", re.compile(
        r"AWS\s*Security\s*Best\s*Practices", re.IGNORECASE)),
    ("pci_dss", re.compile(r"PCI[\-\s]?DSS", re.IGNORECASE)),
    ("hipaa", re.compile(r"HIPAA", re.IGNORECASE)),
    ("iso_27001", re.compile(r"ISO\s*27001", re.IGNORECASE)),
    ("soc2", re.compile(r"SOC\s*2", re.IGNORECASE)),
    ("gdpr", re.compile(r"GDPR", re.IGNORECASE)),
]

# URL host signals — provide additional provenance even when CheckType is sparse.
_URL_PATTERNS = [
    ("aws_security_hub", re.compile(r"securityhub|security-hub", re.IGNORECASE)),
    ("trend_micro_cloud_conformity", re.compile(
        r"trendmicro\.com|cloudoneconformity", re.IGNORECASE)),
    ("nist_gov", re.compile(r"nist\.gov", re.IGNORECASE)),
    ("cis_security", re.compile(r"cisecurity\.org", re.IGNORECASE)),
    ("prowler_hub", re.compile(r"hub\.prowler\.com", re.IGNORECASE)),
]


# Map Prowler Categories tag → coarse security domain. These are the labels
# we will use to narrow capability candidates downstream. Capabilities in
# maturity_capabilities.json currently expose `domain` as AWS service name,
# so this is an additive taxonomy we control end-to-end.
_CATEGORY_TO_DOMAIN = {
    "encryption": "data_protection",
    "logging": "logging_monitoring",
    "forensics-ready": "logging_monitoring",
    "internet-exposed": "network",
    "trustboundaries": "network",
    "trust-boundaries": "network",
    "identity-access": "identity_access",
    "secrets": "identity_access",
    "threat-detection": "threat_detection",
    "vulnerabilities": "vulnerability_management",
    "redundancy": "resilience",
    "resilience": "resilience",
    "gen-ai": "gen_ai",
    "container-security": "container_security",
}

# Fallback domain inference when Categories field is empty.
# Walks CheckType taxonomy looking for known signals.
_CHECKTYPE_DOMAIN_HINTS = [
    (re.compile(r"data\s*protection", re.IGNORECASE), "data_protection"),
    (re.compile(r"data\s*exposure", re.IGNORECASE), "data_protection"),
    (re.compile(r"logging|monitoring", re.IGNORECASE), "logging_monitoring"),
    (re.compile(r"network\s*reachability|network", re.IGNORECASE), "network"),
    (re.compile(r"denial\s*of\s*service", re.IGNORECASE), "resilience"),
    (re.compile(r"credential|initial\s*access|defense\s*evasion",
                re.IGNORECASE), "identity_access"),
    (re.compile(r"vulnerability|patch", re.IGNORECASE),
     "vulnerability_management"),
]

# Last-resort: derive domain from check_id token patterns. Ordered: more
# specific patterns first so e.g. "public_access" wins over generic "access".
_CHECKID_DOMAIN_HINTS = [
    (re.compile(r"encryption|encrypt|kms|tls|ssl|cmk"), "data_protection"),
    (re.compile(r"public_access|public_ip|public_subnet|publicly|exposed|"
                r"open_ports|cross_account|allow_all"), "network"),
    (re.compile(r"logging|logs?_|cloudtrail|cloudwatch_log|audit"),
     "logging_monitoring"),
    (re.compile(r"backup|snapshot|multi_az|fault_tolerant|replica|"
                r"failover|deletion_protection"), "resilience"),
    (re.compile(r"password|mfa|root_|access_key|iam_|policy|"
                r"secrets?_|credentials?"), "identity_access"),
    (re.compile(r"guardduty|inspector|securityhub|detector"),
     "threat_detection"),
    (re.compile(r"patch|version|outdated|deprecated|unsupported"),
     "vulnerability_management"),
    (re.compile(r"bedrock|sagemaker|comprehend|textract"), "gen_ai"),
    (re.compile(r"ecs_|eks_|ecr_|container"), "container_security"),
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvidenceRef:
    source: str            # e.g. "nist_800_53", "cis_aws"
    ref_type: str          # "check_type" | "url" | "category"
    raw: str               # original text we extracted from
    url: Optional[str] = None


@dataclass
class CheckSignals:
    check_id: str
    service: str
    severity: str
    title: str
    categories: List[str]
    evidence_refs: List[EvidenceRef] = field(default_factory=list)
    security_domain: Optional[str] = None
    domain_source: Optional[str] = None  # "category" | "checktype" | "none"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------

def _extract_framework_refs(check: Dict[str, Any]) -> List[EvidenceRef]:
    refs: List[EvidenceRef] = []
    seen: set = set()

    for check_type in (check.get("CheckType") or []):
        for source, pattern in _FRAMEWORK_PATTERNS:
            if pattern.search(check_type):
                key = (source, "check_type", check_type)
                if key in seen:
                    continue
                seen.add(key)
                refs.append(EvidenceRef(
                    source=source,
                    ref_type="check_type",
                    raw=check_type.strip(),
                ))

    urls = list(check.get("AdditionalURLs") or [])
    if check.get("RelatedUrl"):
        urls.append(check["RelatedUrl"])
    rec = (check.get("Remediation") or {}).get("Recommendation") or {}
    if rec.get("Url"):
        urls.append(rec["Url"])

    for url in urls:
        if not url:
            continue
        for source, pattern in _URL_PATTERNS:
            if pattern.search(url):
                key = (source, "url", url)
                if key in seen:
                    continue
                seen.add(key)
                refs.append(EvidenceRef(
                    source=source,
                    ref_type="url",
                    raw=url,
                    url=url,
                ))

    return refs


def _infer_security_domain(check: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Return (domain, source) where source is 'category' | 'checktype' | 'checkid' | None."""
    categories = [c.strip().lower() for c in (check.get("Categories") or [])]
    for cat in categories:
        if cat in _CATEGORY_TO_DOMAIN:
            return _CATEGORY_TO_DOMAIN[cat], "category"

    for check_type in (check.get("CheckType") or []):
        for pattern, domain in _CHECKTYPE_DOMAIN_HINTS:
            if pattern.search(check_type):
                return domain, "checktype"

    check_id = str(check.get("CheckID", "")).lower()
    for pattern, domain in _CHECKID_DOMAIN_HINTS:
        if pattern.search(check_id):
            return domain, "checkid"

    return None, None


def extract_check_signals(check: Dict[str, Any]) -> CheckSignals:
    domain, domain_src = _infer_security_domain(check)
    return CheckSignals(
        check_id=str(check.get("CheckID", "")).strip(),
        service=str(check.get("ServiceName", "")).strip().lower(),
        severity=str(check.get("Severity", "")).strip().lower(),
        title=str(check.get("CheckTitle", "")).strip(),
        categories=[c.strip() for c in (check.get("Categories") or [])],
        evidence_refs=_extract_framework_refs(check),
        security_domain=domain,
        domain_source=domain_src,
    )


# ---------------------------------------------------------------------------
# Coverage reporting
# ---------------------------------------------------------------------------

def build_coverage_report(signals: List[CheckSignals]) -> Dict[str, Any]:
    total = len(signals)
    with_any_ref = sum(1 for s in signals if s.evidence_refs)
    with_domain = sum(1 for s in signals if s.security_domain)
    with_both = sum(
        1 for s in signals if s.evidence_refs and s.security_domain)

    refs_by_source: Counter = Counter()
    for s in signals:
        for r in s.evidence_refs:
            refs_by_source[r.source] += 1

    domains: Counter = Counter(
        s.security_domain or "__none__" for s in signals)
    domain_sources: Counter = Counter(
        s.domain_source or "__none__" for s in signals)

    by_service: Counter = Counter(s.service for s in signals)

    missing_both = [
        s.check_id for s in signals
        if not s.evidence_refs and not s.security_domain
    ]

    def pct(n: int) -> float:
        return round(100 * n / total, 2) if total else 0.0

    return {
        "summary": {
            "total_checks": total,
            "with_evidence_ref": with_any_ref,
            "with_evidence_ref_pct": pct(with_any_ref),
            "with_security_domain": with_domain,
            "with_security_domain_pct": pct(with_domain),
            "with_both": with_both,
            "with_both_pct": pct(with_both),
            "no_upstream_signal": total - max(with_any_ref, with_domain),
        },
        "evidence_refs_by_source": dict(refs_by_source.most_common()),
        "security_domain_distribution": dict(domains.most_common()),
        "domain_inference_source": dict(domain_sources.most_common()),
        "checks_by_service_top10": dict(by_service.most_common(10)),
        "checks_missing_all_signals_sample": missing_both[:20],
        "checks_missing_all_signals_count": len(missing_both),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prowler",
        default="RAG/data/raw/prowler_checks.json",
        type=Path,
    )
    parser.add_argument(
        "--out",
        default="RAG/data/normalized/tier1_upstream_signals.json",
        type=Path,
    )
    parser.add_argument(
        "--report",
        default="RAG/data/normalized/tier1_coverage_report.json",
        type=Path,
    )
    args = parser.parse_args()

    with args.prowler.open("r", encoding="utf-8") as f:
        prowler_checks = json.load(f)

    signals = [extract_check_signals(c) for c in prowler_checks]
    signals_payload = [s.to_dict() for s in signals]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(signals_payload, f, ensure_ascii=False, indent=2)

    report = build_coverage_report(signals)
    with args.report.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report["summary"], indent=2))
    print(f"\nFull signals written to: {args.out}")
    print(f"Coverage report written to: {args.report}")


if __name__ == "__main__":
    main()
