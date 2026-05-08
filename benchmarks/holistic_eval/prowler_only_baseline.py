"""D1 floor baseline: run Prowler-only against the same S3 sandbox after the
same `degrade` script, measure Coverage + latency, and emit a comparison row
to plug into the report.

Workflow:
  1. degrade s3-test123-bucket (7 PASS->FAIL)
  2. prowler aws --service s3 --output-formats json-asff csv  (timed)
  3. parse output → count FAIL findings whose check_id is in the 11 ground-truth set
  4. revert
  5. write `benchmarks/results/d1_20260506/stats/prowler_floor.json`

Ground-truth set (11 findings = 7 degraded + 4 pre-existing).
NOTE: The 4 pre-existing finding check_ids are derived from the agent's run.
We compute coverage on check_id basis (not finding_uid since uid changes per run).

Usage:
    python benchmarks/holistic_eval/prowler_only_baseline.py
        --bucket s3-test123-bucket
        --skip-degrade   # reuse current state (faster repeat run)
        --skip-revert    # leave state degraded after run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEGRADE = ROOT / "scripts" / "degrade_s3_for_e2e.py"
OUT_DIR = ROOT / "benchmarks" / "results" / "d1_20260506" / "stats"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PROWLER_OUT_DIR = OUT_DIR / "prowler_run"
PROWLER_OUT_DIR.mkdir(exist_ok=True)

# Ground-truth check IDs derived from §6.2.2 of report.
# 7 degraded checks (chủ động):
DEGRADED_CHECKS = {
    "s3_bucket_object_versioning",
    "s3_bucket_default_encryption",
    "s3_bucket_kms_encryption",
    "s3_bucket_event_notifications_enabled",
    "s3_bucket_acl_prohibited",
    "s3_bucket_secure_transport_policy",
    "s3_bucket_shadow_resource_vulnerability",
}
# 4 pre-existing on logs-085... + s3-test123 (read from prior agent run).
# We let the script discover these automatically from FAIL findings,
# but record the count for transparency.

PROWLER_TIMEOUT_S = 600


def run_degrade(bucket: str, mode: str):
    print(f"[degrade] {mode} on {bucket}")
    r = subprocess.run(
        [sys.executable, str(DEGRADE), "--bucket", bucket, f"--{mode}", "--yes"],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        print("STDERR:", r.stderr)
        raise SystemExit(f"degrade --{mode} failed")
    print(r.stdout[-300:])


def run_prowler(bucket: str) -> dict:
    """Run prowler aws --service s3 and return parsed result."""
    out_basename = f"prowler_floor_{int(time.time())}"
    cmd = [
        "prowler", "aws",
        "--service", "s3",
        "--output-formats", "json-ocsf",
        "--output-directory", str(PROWLER_OUT_DIR),
        "--output-filename", out_basename,
        "--ignore-exit-code-3",   # don't fail script on FAIL findings
        "--no-banner",
    ]
    print(f"[prowler] {' '.join(cmd)}")
    t0 = time.perf_counter()
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8",
           "AWS_DEFAULT_REGION": "us-east-1", "AWS_REGION": "us-east-1"}
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=PROWLER_TIMEOUT_S, env=env)
    dt = time.perf_counter() - t0
    print(f"[prowler] returncode={r.returncode}, time={dt:.1f}s")
    if r.returncode not in (0, 3):
        print("STDOUT (last 500):", r.stdout[-500:])
        print("STDERR (last 500):", r.stderr[-500:])

    # Parse OCSF JSON output (one or more files in PROWLER_OUT_DIR)
    findings = []
    for jf in PROWLER_OUT_DIR.glob(f"{out_basename}*.json"):
        text = jf.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
            if isinstance(data, list):
                findings.extend(data)
            else:
                findings.append(data)
        except json.JSONDecodeError:
            # JSON-Lines fallback
            for line in text.splitlines():
                line = line.strip()
                if line:
                    try:
                        findings.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    return {
        "duration_s": dt,
        "returncode": r.returncode,
        "raw_findings_count": len(findings),
        "findings": findings,
        "out_files": [str(p) for p in PROWLER_OUT_DIR.glob(f"{out_basename}*")],
    }


def analyze(prowler_run: dict) -> dict:
    """Extract FAIL findings, group by check_id, compute coverage on the
    7 degraded ground-truth checks."""
    fails = []
    for f in prowler_run["findings"]:
        # OCSF schema: status_code = "FAIL" | "PASS" (uppercase in 5.x)
        status = (f.get("status_code") or f.get("status") or "").upper()
        if status not in ("FAIL", "FAILED"):
            continue
        # In Prowler 5.x OCSF, check_id is in metadata.event_code
        check_id = (
            (f.get("metadata") or {}).get("event_code")
            or (f.get("unmapped") or {}).get("check_id")
        )
        resource_uid = None
        resources = f.get("resources") or []
        if resources:
            resource_uid = resources[0].get("uid") or resources[0].get("name")
        fails.append({"check_id": check_id, "resource": resource_uid})

    # Coverage: degraded check_ids found
    found_check_ids = {f["check_id"] for f in fails if f["check_id"]}
    degraded_found = found_check_ids & DEGRADED_CHECKS
    coverage_degraded = len(degraded_found) / len(DEGRADED_CHECKS)

    # Distinct (check_id, resource) failure pairs
    distinct_pairs = {(f["check_id"], f["resource"]) for f in fails if f["check_id"]}

    return {
        "n_fail_findings": len(fails),
        "n_distinct_check_resource": len(distinct_pairs),
        "found_degraded_check_ids": sorted(degraded_found),
        "missing_degraded_check_ids": sorted(DEGRADED_CHECKS - degraded_found),
        "coverage_degraded": coverage_degraded,
        "all_fail_check_ids": sorted(found_check_ids),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default="s3-test123-bucket")
    ap.add_argument("--skip-degrade", action="store_true")
    ap.add_argument("--skip-revert", action="store_true")
    args = ap.parse_args()

    if not args.skip_degrade:
        run_degrade(args.bucket, "degrade")
    else:
        print("[skip] degrade")

    try:
        run = run_prowler(args.bucket)
    finally:
        if not args.skip_revert:
            run_degrade(args.bucket, "revert")
        else:
            print("[skip] revert (bucket left in degraded state)")

    analysis = analyze(run)
    summary = {
        "schema_version": 1,
        "bucket": args.bucket,
        "prowler_version": "5.16.1",
        "duration_s": run["duration_s"],
        "raw_finding_count": run["raw_findings_count"],
        **analysis,
        "agent_baseline_for_compare": {
            "duration_s_mean_5sessions": 432.1,
            "coverage_full_11_findings": 1.00,
            "extras": [
                "Vietnamese narrative report (HTML/PDF/Markdown)",
                "Severity mapping + remediation steps per finding",
                "Auto-execute 5 of 11 fixes",
                "Maturity score (post = 78.10)",
                "Audit trail in Langfuse (trace + observation + score)",
            ],
        },
    }
    out = OUT_DIR / "prowler_floor.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\n=== PROWLER FLOOR SUMMARY ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "agent_baseline_for_compare"}, indent=2, default=str))
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
