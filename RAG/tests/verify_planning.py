"""
Verification script: shows how planning bundle coverage changes for multi-intent queries.
"""
import requests
import json

URL = "http://localhost:8123/v1/context/build"

SCENARIOS = [
    {
        "name": "RDS multi-intent (public_access + encryption)",
        "payload": {
            "consumer": "planning",
            "query": "rds public access and encryption",
            "service": "rds",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
        },
    },
    {
        "name": "IAM multi-intent (iam + root + mfa)",
        "payload": {
            "consumer": "planning",
            "query": "secure IAM users and root account mfa",
            "service": "iam",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
        },
    },
    {
        "name": "Narrow query (single intent: logging)",
        "payload": {
            "consumer": "planning",
            "query": "cloudtrail logging enabled",
            "service": "cloudtrail",
            "include_mappings": True,
            "include_maturity": True,
            "top_k": 5,
        },
    },
]

for s in SCENARIOS:
    r = requests.post(URL, json=s["payload"], timeout=30)
    data = r.json()
    bundle = data.get("data", {}).get("payload", {}).get("planning_bundle", {})
    findings = bundle.get("related_findings", [])
    services = list({f.get("service") for f in findings if f.get("service")})

    print(f"\n=== {s['name']} ===")
    print(f"  Findings count : {len(findings)} (dynamic)")
    print(f"  Services covered: {sorted(services)}")
    for f in findings:
        svc = f.get("service", "?")
        cid = f.get("check_id", "")
        title = (f.get("title") or "")[:70]
        print(f"    [{svc:12}] {cid} -- {title}")
