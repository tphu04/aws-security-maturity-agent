"""Backfill the `domain` field in maturity_capabilities.json.

Logic (priority order):
1. Regex extract AWS service name from capability_id / capability_name.
2. Keyword match on keywords[] + capability_name.
3. Fallback: domain = "general".

Run:
    python RAG/scripts/backfill_capability_domain.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_FILE = PROJECT_ROOT / "RAG" / "data" / "normalized" / "maturity_capabilities.json"

# Ordered by specificity — checked against capability_id and capability_name
_SERVICE_PATTERNS: list[tuple[str, str]] = [
    # (regex_pattern, domain_label)
    (r"\bs3\b|s3_bucket|block.public.access|object.?stor|public.access.block", "s3"),
    (r"\biam\b|identity.feder|access.analyz|iam_role|iam_polic|least.priv|mfa|multi.factor|temporary.cred|use.temporary|secret.in.code|permission.guardrail", "iam"),
    (r"\bec2\b|security.group|open.admin.port|instance.meta|imdsv2", "ec2"),
    (r"\bcloudfront\b|cdn|viewer.cert|origin.access|distribution", "cloudfront"),
    (r"\brds\b|database.encr|db.encr|rds_", "rds"),
    (r"\bguardduty\b|guard.duty|threat.detect|malware.detect", "guardduty"),
    (r"\bkms\b|encr.at.rest|cmk|customer.manag.key|kms_key", "kms"),
    (r"\bvpc\b|network.segment|flow.log|vpc_flow|subnet|nacl|security.group", "vpc"),
    (r"\bcloudtrail\b|audit.api|api.call|cloud.trail|log.api", "cloudtrail"),
    (r"\bcloudwatch\b|billing.alarm|anomaly.detect|metric.alarm|cloudwatch", "cloudwatch"),
    (r"\bresilience.hub\b|resilience.posture|resilience_hub", "resilience_hub"),
    (r"\bwaf\b|managed.rule|web.acl", "waf"),
    (r"\bsecurity.hub\b|security_hub|securityhub", "securityhub"),
    (r"\bconfig\b|aws.config|compliance.rule|config_rule", "config"),
    (r"\biam.access.analyz\b|ciem|external.access", "iam"),
    (r"\broot.account\b|root.mfa|root.user", "iam"),
    (r"\bregion\b|block.region|scp", "organizations"),
    (r"\bbackup\b|data.backup|recovery|restore", "backup"),
    (r"\bencrypt\b|encryption.in.transit|tls|https|ssl", "kms"),
]

_KEYWORD_TO_DOMAIN: dict[str, str] = {
    "s3": "s3", "bucket": "s3", "object storage": "s3",
    "iam": "iam", "identity": "iam", "role": "iam", "policy": "iam",
    "ec2": "ec2", "instance": "ec2", "security group": "ec2",
    "vpc": "vpc", "network": "vpc", "subnet": "vpc",
    "cloudtrail": "cloudtrail", "audit": "cloudtrail",
    "cloudwatch": "cloudwatch", "alarm": "cloudwatch",
    "guardduty": "guardduty", "threat": "guardduty",
    "kms": "kms", "encryption": "kms", "key": "kms",
    "rds": "rds", "database": "rds",
    "cloudfront": "cloudfront",
    "waf": "waf",
    "backup": "backup",
    "config": "config",
}


def _derive_domain(capability_id: str, capability_name: str, keywords: list[str]) -> str:
    text_id = capability_id.lower().replace("_", " ")
    text_name = capability_name.lower()
    combined = f"{text_id} {text_name}"

    for pattern, domain in _SERVICE_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return domain

    kw_blob = " ".join(k.lower() for k in keywords)
    for kw, domain in _KEYWORD_TO_DOMAIN.items():
        if kw in kw_blob or kw in text_name:
            return domain

    return "general"


def backfill(data: list[dict], verbose: bool = False) -> tuple[list[dict], dict[str, int]]:
    stats: dict[str, int] = {}
    updated = 0
    for record in data:
        domain = _derive_domain(
            record.get("capability_id", ""),
            record.get("capability_name", ""),
            record.get("keywords", []),
        )
        if verbose:
            print(f"  {record.get('capability_id', '')[:50]:<50} -> {domain}")
        if not record.get("domain"):
            updated += 1
        record["domain"] = domain
        stats[domain] = stats.get(domain, 0) + 1
    print(f"Updated {updated} records (total {len(data)})")
    return data, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    data, stats = backfill(data, verbose=args.verbose)

    print("\nDomain distribution:")
    for domain, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count}")

    if args.dry_run:
        print("\n[DRY RUN] No file written.")
        return 0

    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {len(data)} records to {DATA_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
