import boto3
import json
import logging
from botocore.exceptions import ClientError

# Tắt log nhiễu của boto3
logging.getLogger("botocore").setLevel(logging.CRITICAL)

INPUT_FILE = "data/pre_scan.json"
# Tên bucket dùng để test khi resource_id trong file scan bị sai (hoặc là Account ID)
TEST_BUCKET_NAME = "prowler-test-public-bucket"


def get_s3_client(region):
    return boto3.client("s3", region_name=region)


def get_s3_control_client(region):
    return boto3.client("s3control", region_name=region)


# ==========================================
# 1. PUBLIC ACCESS BLOCK (BPA) CHECKS
# ==========================================


def check_account_block(client, account_id, resource_id):
    """Kiểm tra Account Level Public Access Block"""
    try:
        resp = client.get_public_access_block(AccountId=account_id)
        conf = resp.get("PublicAccessBlockConfiguration", {})

        missing = []
        if not conf.get("BlockPublicAcls"):
            missing.append("BlockPublicAcls")
        if not conf.get("IgnorePublicAcls"):
            missing.append("IgnorePublicAcls")
        if not conf.get("BlockPublicPolicy"):
            missing.append("BlockPublicPolicy")
        if not conf.get("RestrictPublicBuckets"):
            missing.append("RestrictPublicBuckets")

        if not missing:
            return "PASS: All Account Blocks Enabled"
        return f"FAIL: Missing Account Blocks: {', '.join(missing)}"
    except ClientError:
        return "FAIL: No Account Block Configured"


def check_bucket_block(client, account_id, bucket):
    """Kiểm tra Bucket Level Public Access Block"""
    try:
        resp = client.get_public_access_block(Bucket=bucket)
        conf = resp.get("PublicAccessBlockConfiguration", {})

        missing = []
        if not conf.get("BlockPublicAcls"):
            missing.append("BlockPublicAcls")
        if not conf.get("IgnorePublicAcls"):
            missing.append("IgnorePublicAcls")
        if not conf.get("BlockPublicPolicy"):
            missing.append("BlockPublicPolicy")
        if not conf.get("RestrictPublicBuckets"):
            missing.append("RestrictPublicBuckets")

        if not missing:
            return "PASS: All Bucket Blocks Enabled"
        return f"FAIL: Missing Bucket Blocks: {', '.join(missing)}"
    except ClientError:
        return "FAIL: No Bucket Block Configured"


# ==========================================
# 2. ENCRYPTION & SECURITY CHECKS
# ==========================================


def check_encryption_status(client, account_id, bucket):
    """Kiểm tra Default Encryption (s3_bucket_default_encryption)"""
    try:
        resp = client.get_bucket_encryption(Bucket=bucket)
        rules = resp["ServerSideEncryptionConfiguration"]["Rules"]
        algo = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
        key_id = rules[0]["ApplyServerSideEncryptionByDefault"].get(
            "KMSMasterKeyID", "Managed-Key"
        )

        return f"PASS: Encrypted ({algo}) | Key: {key_id}"
    except ClientError:
        return "FAIL: Encryption Disabled"


def check_kms_specific(client, account_id, bucket):
    """Kiểm tra KMS Encryption (s3_bucket_kms_encryption)"""
    try:
        resp = client.get_bucket_encryption(Bucket=bucket)
        rules = resp["ServerSideEncryptionConfiguration"]["Rules"]
        algo = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]

        if algo == "aws:kms":
            return "PASS: Uses AWS KMS"
        return f"FAIL: Uses {algo} (Not KMS)"
    except ClientError:
        return "FAIL: Encryption Disabled"


def check_secure_transport(client, account_id, bucket):
    """Kiểm tra Policy HTTPS (s3_bucket_secure_transport_policy)"""
    try:
        resp = client.get_bucket_policy(Bucket=bucket)
        policy_str = resp["Policy"]
        # Check đơn giản condition aws:SecureTransport
        if '"aws:SecureTransport":"false"' in policy_str.replace(" ", ""):
            return "PASS: Enforces HTTPS (Deny HTTP)"
        return "FAIL: Does not enforce HTTPS explicitly"
    except ClientError:
        return "FAIL: No Bucket Policy / No HTTPS enforcement"


# ==========================================
# 3. CONFIGURATION & LOGGING CHECKS
# ==========================================


def check_ownership(client, account_id, bucket):
    """Kiểm tra Object Ownership (s3_bucket_acl_prohibited)"""
    try:
        resp = client.get_bucket_ownership_controls(Bucket=bucket)
        rules = resp.get("OwnershipControls", {}).get("Rules", [])
        for rule in rules:
            mode = rule.get("ObjectOwnership")
            if mode == "BucketOwnerEnforced":
                return "PASS: BucketOwnerEnforced (ACLs Disabled)"
            return f"FAIL: ObjectOwnership is {mode} (ACLs Enabled)"
        return "FAIL: No Ownership Rules (ACLs Enabled by default)"
    except ClientError:
        return "FAIL: Ownership Controls Not Set"


def check_versioning_mfa(client, account_id, bucket):
    """Kiểm tra Versioning & MFA (s3_bucket_object_versioning, s3_bucket_no_mfa_delete)"""
    try:
        resp = client.get_bucket_versioning(Bucket=bucket)
        status = resp.get("Status", "Suspended")
        mfa = resp.get("MFADelete", "Disabled")

        result = f"Versioning: {status}"
        if status == "Enabled":
            result += f" | MFA Delete: {mfa}"
            return f"PASS: {result}"
        return f"FAIL: {result}"
    except ClientError:
        return "FAIL: Cannot check Versioning"


def check_logging(client, account_id, bucket):
    """Kiểm tra Server Access Logging (s3_bucket_server_access_logging_enabled)"""
    try:
        resp = client.get_bucket_logging(Bucket=bucket)
        if "LoggingEnabled" in resp:
            target = resp["LoggingEnabled"]["TargetBucket"]
            return f"PASS: Logging enabled -> {target}"
        return "FAIL: Logging Disabled"
    except ClientError:
        return "FAIL: Logging Check Error"


def check_events(client, account_id, bucket):
    """Kiểm tra Event Notifications (s3_bucket_event_notifications_enabled)"""
    try:
        resp = client.get_bucket_notification_configuration(Bucket=bucket)
        configs = []
        if "TopicConfigurations" in resp:
            configs.append("SNS")
        if "QueueConfigurations" in resp:
            configs.append("SQS")
        if "LambdaFunctionConfigurations" in resp:
            configs.append("Lambda")

        if configs:
            return f"PASS: Events configured for {', '.join(configs)}"
        return "PASS (Info): No Event Notifications"
    except ClientError:
        return "FAIL: Event Check Error"


def check_lifecycle(client, account_id, bucket):
    """Kiểm tra Lifecycle (s3_bucket_lifecycle_enabled)"""
    try:
        resp = client.get_bucket_lifecycle_configuration(Bucket=bucket)
        rules = resp.get("Rules", [])
        active_rules = [
            r.get("ID", "Rule") for r in rules if r.get("Status") == "Enabled"
        ]

        if active_rules:
            return f"PASS: {len(active_rules)} active rules"
        return "FAIL: Lifecycle configured but all rules Disabled"
    except ClientError:
        return "FAIL: Lifecycle Not Configured"


def check_replication(client, account_id, bucket):
    """Kiểm tra Replication (s3_bucket_cross_region_replication)"""
    try:
        resp = client.get_bucket_replication(Bucket=bucket)
        rules = resp.get("ReplicationConfiguration", {}).get("Rules", [])
        active = any(r.get("Status") == "Enabled" for r in rules)

        if active:
            return "PASS: Replication Enabled"
        return "FAIL: Replication Configured but Disabled"
    except ClientError:
        return "FAIL: Replication Not Configured"


def check_object_lock(client, account_id, bucket):
    """Kiểm tra Object Lock (s3_bucket_object_lock)"""
    try:
        resp = client.get_object_lock_configuration(Bucket=bucket)
        status = resp.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled")
        if status == "Enabled":
            return "PASS: Object Lock Enabled"
        return f"FAIL: Object Lock is {status}"
    except ClientError:
        return "FAIL: Object Lock Disabled"


def check_shadow(client, account_id, bucket):
    """Kiểm tra Shadow Resource (s3_bucket_shadow_resource_vulnerability)"""
    try:
        client.head_bucket(Bucket=bucket)
        return "PASS: Bucket exists & owned by you"
    except ClientError as e:
        return f"FAIL: Cannot access bucket ({e.response['Error']['Code']})"


# ==========================================
# 4. ACL & POLICY PUBLIC CHECKS
# ==========================================


def check_acl_public_list(client, account_id, bucket):
    """Kiểm tra Public List ACL (s3_bucket_public_list_acl)"""
    try:
        acls = client.get_bucket_acl(Bucket=bucket)
        for grant in acls["Grants"]:
            uri = grant.get("Grantee", {}).get("URI", "")
            perm = grant.get("Permission")
            if ("AllUsers" in uri or "AuthenticatedUsers" in uri) and perm in [
                "READ",
                "FULL_CONTROL",
            ]:
                return f"FAIL: Public LIST allowed via ACL ({perm})"
        return "PASS: No Public List ACL"
    except ClientError:
        return "FAIL: Cannot check ACL (Bucket might not exist or Access Denied)"


def check_acl_public_write(client, account_id, bucket):
    """Kiểm tra Public Write ACL (s3_bucket_public_write_acl)"""
    try:
        acls = client.get_bucket_acl(Bucket=bucket)
        for grant in acls["Grants"]:
            uri = grant.get("Grantee", {}).get("URI", "")
            perm = grant.get("Permission")
            if ("AllUsers" in uri or "AuthenticatedUsers" in uri) and perm in [
                "WRITE",
                "FULL_CONTROL",
            ]:
                return f"FAIL: Public WRITE allowed via ACL ({perm})"
        return "PASS: No Public Write ACL"
    except ClientError:
        return "FAIL: Cannot check ACL"


def check_policy_public_write(client, account_id, bucket):
    """Kiểm tra Policy Public Write (s3_bucket_policy_public_write_access)"""
    try:
        resp = client.get_bucket_policy(Bucket=bucket)
        policy_str = resp["Policy"]
        if (
            '"Principal":{"AWS":"*"}' in policy_str.replace(" ", "")
            or '"Principal":"*"' in policy_str
        ):
            return "FAIL: Policy has Wildcard Principal (*)"
        return "PASS: Policy looks safe (No obvious wildcard)"
    except ClientError:
        return "PASS: No Bucket Policy"


def check_cross_account(client, account_id, bucket):
    """Kiểm tra Cross Account (s3_bucket_cross_account_access)"""
    try:
        resp = client.get_bucket_policy(Bucket=bucket)
        policy_str = resp["Policy"]
        if account_id in policy_str:
            return "PASS: Policy restricts to current Account ID"
        return "WARNING: Account ID not found in policy (Possible Cross-Account)"
    except ClientError:
        return "PASS: No Policy (Safe)"


# ==========================================
# DISPATCHER MAPPING (ĐỦ 19 Event Codes)
# ==========================================
DISPATCHER = {
    # 1. Account Level
    "s3_account_level_public_access_blocks": check_account_block,
    # 2. Bucket Public Access & ACLs
    "s3_bucket_level_public_access_block": check_bucket_block,
    "s3_bucket_public_access": check_bucket_block,  # Kiểm tra chung về public access
    "s3_bucket_acl_prohibited": check_ownership,
    "s3_bucket_public_list_acl": check_acl_public_list,
    "s3_bucket_public_write_acl": check_acl_public_write,
    # 3. Encryption
    "s3_bucket_default_encryption": check_encryption_status,
    "s3_bucket_kms_encryption": check_kms_specific,
    # 4. Security & Data Protection
    "s3_bucket_secure_transport_policy": check_secure_transport,
    "s3_bucket_cross_region_replication": check_replication,
    "s3_bucket_lifecycle_enabled": check_lifecycle,
    "s3_bucket_object_lock": check_object_lock,
    "s3_bucket_object_versioning": check_versioning_mfa,
    "s3_bucket_no_mfa_delete": check_versioning_mfa,
    # 5. Monitoring & Policy
    "s3_bucket_server_access_logging_enabled": check_logging,
    "s3_bucket_event_notifications_enabled": check_events,
    "s3_bucket_policy_public_write_access": check_policy_public_write,
    "s3_bucket_cross_account_access": check_cross_account,
    "s3_bucket_shadow_resource_vulnerability": check_shadow,
}


def main():
    try:
        with open(INPUT_FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"File {INPUT_FILE} not found. Make sure you have data/pre_scan.json")
        return

    print(f"{'RESOURCE ID':<40} | {'EVENT CODE':<45} | {'STATUS'}")
    print("=" * 140)

    s3_clients = {}
    s3control_clients = {}

    count = 0

    for finding in data.get("findings", []):
        event_code = finding.get("event_code")
        resource_id = finding.get("resource_id")
        account_id = finding.get("account_id")
        region = finding.get("region", "us-east-1")

        # === FIX LOGIC RESOURCE ID CHO 34 FINDINGS ===
        target_resource = resource_id

        # Logic 1: Nếu resource_id là Account ID (Finding 26, 27, 28...), dùng bucket test
        if resource_id == account_id and "bucket" in event_code:
            target_resource = TEST_BUCKET_NAME

        # Logic 2: Nếu event code là bucket check nhưng resource_id trống
        if not target_resource and "bucket" in event_code:
            target_resource = TEST_BUCKET_NAME

        # Logic 3: Nếu là ARN, cắt lấy tên bucket
        if target_resource and target_resource.startswith("arn:aws"):
            target_resource = target_resource.split(":")[-1]

        handler = DISPATCHER.get(event_code)
        if not handler:
            print(f"{target_resource:<40} | {event_code:<45} | SKIPPED (No Handler)")
            continue

        # Chọn Client (Cache client để chạy nhanh hơn)
        try:
            if "account_level" in event_code:
                if region not in s3control_clients:
                    s3control_clients[region] = get_s3_control_client(region)
                client = s3control_clients[region]
            else:
                if region not in s3_clients:
                    s3_clients[region] = get_s3_client(region)
                client = s3_clients[region]

            # RUN CHECK
            result = handler(client, account_id, target_resource)
            count += 1
        except Exception as e:
            result = f"ERROR: {str(e)}"

        print(f"{target_resource:<40} | {event_code:<45} | {result}")

    print("=" * 140)
    print(f"Total findings verified: {count} / {len(data.get('findings', []))}")


if __name__ == "__main__":
    main()
