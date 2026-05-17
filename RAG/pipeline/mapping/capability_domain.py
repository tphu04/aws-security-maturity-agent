"""Derive security_domain for each capability in maturity_capabilities.json.

Capabilities expose `domain` as an AWS service name (s3, iam, ec2, ...). We
need a parallel `security_domain` label that aligns with the taxonomy emitted
by tier1_upstream_import for checks, so Tier 2 proposers can narrow the
capability search space.

This module never writes to the catalog; it returns an in-memory index
{capability_id: security_domain} that downstream tiers consume.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


# Mirrors _CHECKID_DOMAIN_HINTS / _CATEGORY_TO_DOMAIN from tier1 but tuned
# against capability text (capability_name + summary + keywords).
_CAPABILITY_PATTERNS = [
    (re.compile(r"encrypt|encryption|kms|tls|ssl|cmk|key\s*management",
                re.IGNORECASE), "data_protection"),
    (re.compile(r"public\s*access|public\s*ip|exposed|firewall|"
                r"network\s*segment|trust\s*boundary|vpc|security\s*group|"
                r"cross[\-\s]account", re.IGNORECASE), "network"),
    (re.compile(r"logging|audit\s*trail|cloudtrail|cloudwatch\s*log|"
                r"observability|monitoring", re.IGNORECASE),
     "logging_monitoring"),
    (re.compile(r"backup|disaster\s*recovery|resilien|multi[\-\s]az|"
                r"failover|fault\s*toleran|replica", re.IGNORECASE),
     "resilience"),
    (re.compile(r"identity|iam|access\s*management|mfa|password|"
                r"least\s*privilege|secrets?\s*manage|credentials?",
                re.IGNORECASE), "identity_access"),
    (re.compile(r"guardduty|inspector|securityhub|threat\s*detect|"
                r"intrusion|anomaly\s*detect", re.IGNORECASE),
     "threat_detection"),
    (re.compile(r"patch|vulnerability|cve|outdated\s*version",
                re.IGNORECASE), "vulnerability_management"),
    (re.compile(r"bedrock|sagemaker|generative\s*ai|gen[\-\s]*ai|llm",
                re.IGNORECASE), "gen_ai"),
    (re.compile(r"container|ecs|eks|ecr|kubernetes", re.IGNORECASE),
     "container_security"),
]


def infer_capability_security_domain(cap: Dict[str, Any]) -> Optional[str]:
    parts: List[str] = []
    for key in ("capability_name", "summary", "guidance",
                "risk_explanation", "how_to_check"):
        v = cap.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    for key in ("keywords", "recommended_practices", "tags"):
        v = cap.get(key)
        if isinstance(v, list):
            parts.extend(str(x) for x in v if x)
    blob = " ".join(parts)
    if not blob:
        return None
    for pattern, domain in _CAPABILITY_PATTERNS:
        if pattern.search(blob):
            return domain
    return None


def build_capability_domain_index(
    capabilities_path: Path,
) -> Dict[str, Optional[str]]:
    with capabilities_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    index: Dict[str, Optional[str]] = {}
    for cap in payload:
        cid = cap.get("capability_id")
        if not cid:
            continue
        index[cid] = infer_capability_security_domain(cap)
    return index


if __name__ == "__main__":
    import argparse
    from collections import Counter

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capabilities",
        default="RAG/data/normalized/maturity_capabilities.json",
        type=Path,
    )
    args = parser.parse_args()

    idx = build_capability_domain_index(args.capabilities)
    total = len(idx)
    with_domain = sum(1 for v in idx.values() if v)
    dist = Counter(v or "__none__" for v in idx.values())
    print(json.dumps({
        "total_capabilities": total,
        "with_security_domain": with_domain,
        "coverage_pct": round(100 * with_domain / total, 2) if total else 0.0,
        "distribution": dict(dist.most_common()),
    }, indent=2))
