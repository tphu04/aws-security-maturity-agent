"""
Degrade S3 bucket configuration for E2E testing.

Chuyển 7 check S3 an toàn từ PASS sang FAIL để test end-to-end pipeline
(scan → remediate → rescan → report). Các thay đổi đều KHÔNG expose data,
KHÔNG mở public access, và có thể revert hoàn toàn.

Các check được target:
  1. s3_bucket_object_versioning              — Suspend versioning
  2. s3_bucket_kms_encryption                 — Đổi KMS sang SSE-S3
  3. s3_bucket_default_encryption             — Xóa encryption config
  4. s3_bucket_event_notifications_enabled    — Clear notifications
  5. s3_bucket_secure_transport_policy        — Xóa SSL-only policy
  6. s3_bucket_acl_prohibited                 — ObjectOwnership=ObjectWriter
  7. s3_bucket_shadow_resource_vulnerability  — Bỏ account-binding condition

KHÔNG động đến: public access blocks, cross-account access, public ACL/write.

Usage:
    # Xem actions sẽ chạy (không thực thi)
    python scripts/degrade_s3_for_e2e.py --bucket s3-test123-bucket --dry-run

    # Degrade PASS → FAIL (lưu snapshot config gốc)
    python scripts/degrade_s3_for_e2e.py --bucket s3-test123-bucket --degrade

    # Revert từ snapshot
    python scripts/degrade_s3_for_e2e.py --bucket s3-test123-bucket --revert
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

SNAPSHOT_DIR = Path(__file__).parent.parent / "data" / "artifacts" / "e2e_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "[+]", "WARN": "[!]", "ERROR": "[x]", "OK": "[v]"}
    print(f"{prefix.get(level, '[ ]')} {msg}")


def snapshot_path(bucket: str) -> Path:
    return SNAPSHOT_DIR / f"{bucket}_snapshot.json"


def capture_snapshot(s3, bucket: str) -> dict:
    """Capture current bucket config so we can revert."""
    snap = {"bucket": bucket, "timestamp": datetime.utcnow().isoformat()}

    def safe_call(label, fn):
        try:
            return fn()
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchBucketPolicy", "ServerSideEncryptionConfigurationNotFoundError",
                        "OwnershipControlsNotFoundError", "NoSuchConfiguration"):
                return None
            log(f"  snapshot '{label}' failed: {code}", "WARN")
            return None

    snap["versioning"] = safe_call("versioning", lambda: s3.get_bucket_versioning(Bucket=bucket))
    snap["encryption"] = safe_call("encryption", lambda: s3.get_bucket_encryption(Bucket=bucket))
    snap["notification"] = safe_call("notification", lambda: s3.get_bucket_notification_configuration(Bucket=bucket))
    snap["policy"] = safe_call("policy", lambda: s3.get_bucket_policy(Bucket=bucket))
    snap["ownership"] = safe_call("ownership", lambda: s3.get_bucket_ownership_controls(Bucket=bucket))

    # Strip ResponseMetadata from boto3 results for cleaner JSON
    for k, v in snap.items():
        if isinstance(v, dict) and "ResponseMetadata" in v:
            v.pop("ResponseMetadata", None)

    return snap


def save_snapshot(bucket: str, snap: dict):
    path = snapshot_path(bucket)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f, indent=2, default=str)
    log(f"Snapshot saved: {path}", "OK")


def load_snapshot(bucket: str) -> dict:
    path = snapshot_path(bucket)
    if not path.exists():
        raise FileNotFoundError(
            f"No snapshot at {path}. Run --degrade first to create one."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# DEGRADE ACTIONS (PASS → FAIL)
# ============================================================================

def degrade_versioning(s3, bucket: str, dry: bool):
    """Check: s3_bucket_object_versioning. Suspend versioning → FAIL."""
    log("Action 1/7: Suspend versioning")
    if dry:
        log("  [dry-run] would call put_bucket_versioning(Status=Suspended)")
        return
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Suspended"})
    log("  versioning suspended", "OK")


def degrade_encryption(s3, bucket: str, dry: bool):
    """Checks: s3_bucket_default_encryption + s3_bucket_kms_encryption.
    Delete encryption config entirely. If AWS auto-default applies, only
    kms_encryption will flip to FAIL.
    """
    log("Action 2/7: Delete bucket encryption config (may flip default + kms)")
    if dry:
        log("  [dry-run] would call delete_bucket_encryption()")
        return
    try:
        s3.delete_bucket_encryption(Bucket=bucket)
        log("  encryption config deleted", "OK")
    except ClientError as e:
        log(f"  delete_bucket_encryption failed: {e.response['Error']['Code']}", "WARN")


def degrade_notifications(s3, bucket: str, dry: bool):
    """Check: s3_bucket_event_notifications_enabled. Clear all notifications → FAIL."""
    log("Action 3/7: Clear event notifications")
    if dry:
        log("  [dry-run] would call put_bucket_notification_configuration(empty)")
        return
    s3.put_bucket_notification_configuration(
        Bucket=bucket, NotificationConfiguration={}
    )
    log("  notifications cleared", "OK")


def degrade_ownership(s3, bucket: str, dry: bool):
    """Check: s3_bucket_acl_prohibited. Enable ACLs via ObjectWriter → FAIL.

    Note: ACLs become writable but default bucket-level public access block
    still prevents public ACLs. Data remains private.
    """
    log("Action 4/7: Set ObjectOwnership=ObjectWriter (re-enables ACLs)")
    if dry:
        log("  [dry-run] would call put_bucket_ownership_controls(ObjectWriter)")
        return
    s3.put_bucket_ownership_controls(
        Bucket=bucket,
        OwnershipControls={"Rules": [{"ObjectOwnership": "ObjectWriter"}]},
    )
    log("  ObjectOwnership set to ObjectWriter", "OK")


def degrade_policy(s3, bucket: str, dry: bool):
    """Checks: s3_bucket_secure_transport_policy + s3_bucket_shadow_resource_vulnerability.
    Xóa bucket policy toàn bộ. Account-level public access block vẫn chặn
    public access nên KHÔNG expose data.
    """
    log("Action 5/7: Delete bucket policy (removes SSL-only + account-binding)")
    if dry:
        log("  [dry-run] would call delete_bucket_policy()")
        return
    try:
        s3.delete_bucket_policy(Bucket=bucket)
        log("  bucket policy deleted", "OK")
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "NoSuchBucketPolicy":
            log("  no existing policy (already in target state)", "WARN")
        else:
            log(f"  delete_bucket_policy failed: {code}", "WARN")


# ============================================================================
# REVERT ACTIONS (FAIL → PASS)
# ============================================================================

def revert_versioning(s3, bucket: str, snap: dict, dry: bool):
    v = (snap.get("versioning") or {}).get("Status", "Enabled")
    log(f"Revert versioning → {v}")
    if dry:
        return
    s3.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": v})
    log("  versioning restored", "OK")


def revert_encryption(s3, bucket: str, snap: dict, dry: bool):
    enc = snap.get("encryption")
    if not enc:
        log("Revert encryption: no snapshot data, restoring SSE-S3 default")
        config = {"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}
    else:
        log("Revert encryption from snapshot")
        config = enc.get("ServerSideEncryptionConfiguration", {})
    if dry:
        return
    s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration=config)
    log("  encryption restored", "OK")


def revert_notifications(s3, bucket: str, snap: dict, dry: bool):
    notif = snap.get("notification") or {}
    # Remove keys that aren't valid for PUT
    notif = {k: v for k, v in notif.items() if k != "ResponseMetadata"}
    log("Revert notifications from snapshot")
    if dry:
        return
    s3.put_bucket_notification_configuration(Bucket=bucket, NotificationConfiguration=notif)
    log("  notifications restored", "OK")


def revert_ownership(s3, bucket: str, snap: dict, dry: bool):
    own = snap.get("ownership")
    target = "BucketOwnerEnforced"  # safe default
    if own:
        rules = own.get("OwnershipControls", {}).get("Rules", [])
        if rules:
            target = rules[0].get("ObjectOwnership", target)
    log(f"Revert ObjectOwnership → {target}")
    if dry:
        return
    s3.put_bucket_ownership_controls(
        Bucket=bucket,
        OwnershipControls={"Rules": [{"ObjectOwnership": target}]},
    )
    log("  ownership restored", "OK")


def revert_policy(s3, bucket: str, snap: dict, dry: bool):
    pol = snap.get("policy")
    if not pol or not pol.get("Policy"):
        log("Revert policy: no snapshot policy, skipping", "WARN")
        return
    log("Revert bucket policy from snapshot")
    if dry:
        return
    s3.put_bucket_policy(Bucket=bucket, Policy=pol["Policy"])
    log("  policy restored", "OK")


# ============================================================================
# MAIN
# ============================================================================

def check_bucket_exists(s3, bucket: str) -> bool:
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as e:
        log(f"Bucket '{bucket}' not accessible: {e.response['Error']['Code']}", "ERROR")
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--region", default=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    mode.add_argument("--degrade", action="store_true", help="Flip PASS → FAIL")
    mode.add_argument("--revert", action="store_true", help="Restore from snapshot")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=args.region)

    print("=" * 60)
    print(f" S3 E2E degrade — bucket: {args.bucket} | region: {args.region}")
    mode_str = "DRY-RUN" if args.dry_run else ("DEGRADE" if args.degrade else "REVERT")
    print(f" Mode: {mode_str}")
    print("=" * 60)

    if not check_bucket_exists(s3, args.bucket):
        sys.exit(1)

    if args.degrade and not args.yes:
        resp = input("Proceed with degrade (y/N)? ")
        if resp.lower() != "y":
            log("Aborted", "WARN")
            sys.exit(0)

    dry = args.dry_run

    if args.degrade or args.dry_run:
        if not args.dry_run:
            log("Capturing snapshot of current config...")
            snap = capture_snapshot(s3, args.bucket)
            save_snapshot(args.bucket, snap)
        print()
        degrade_versioning(s3, args.bucket, dry)
        degrade_encryption(s3, args.bucket, dry)
        degrade_notifications(s3, args.bucket, dry)
        degrade_ownership(s3, args.bucket, dry)
        degrade_policy(s3, args.bucket, dry)
        print()
        log("Degrade complete. Expected 5-7 S3 checks to flip PASS → FAIL:", "OK")
        print("    - s3_bucket_object_versioning")
        print("    - s3_bucket_default_encryption (nếu AWS default không auto-apply)")
        print("    - s3_bucket_kms_encryption")
        print("    - s3_bucket_event_notifications_enabled")
        print("    - s3_bucket_acl_prohibited")
        print("    - s3_bucket_secure_transport_policy")
        print("    - s3_bucket_shadow_resource_vulnerability")
        if not args.dry_run:
            log("Run pipeline: python scripts/run_e2e_auto.py 'scan all s3 buckets'")

    elif args.revert:
        snap = load_snapshot(args.bucket)
        log(f"Loaded snapshot from {snap.get('timestamp')}")
        print()
        revert_versioning(s3, args.bucket, snap, dry)
        revert_encryption(s3, args.bucket, snap, dry)
        revert_notifications(s3, args.bucket, snap, dry)
        revert_ownership(s3, args.bucket, snap, dry)
        revert_policy(s3, args.bucket, snap, dry)
        print()
        log("Revert complete. Re-run Prowler scan to verify.", "OK")


if __name__ == "__main__":
    main()
