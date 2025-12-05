import boto3
import json
import logging
from botocore.exceptions import ClientError

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()

# Cấu hình target dựa trên file post_scan.json của bạn
TARGET_ACCOUNT_ID = "065209282642"
REGION = "us-east-1"
TARGET_BUCKETS = ["logs-065209282642-us-east-1", "prowler-test-public-bucket"]


def get_s3_client(region):
    return boto3.client("s3", region_name=region)


def get_s3_control_client(region):
    return boto3.client("s3control", region_name=region)


# ==============================================================================
# 1. ACCOUNT LEVEL FAILURES
# ==============================================================================
def disable_account_public_block(client, account_id):
    """FAIL: s3_account_level_public_access_blocks"""
    logger.info(f"[-] Disabling Account Level Public Access Block for {account_id}...")
    try:
        client.delete_public_access_block(AccountId=account_id)
        logger.info("    -> Success: Account is now open to public config.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


# ==============================================================================
# 2. BUCKET LEVEL FAILURES (Make them vulnerable)
# ==============================================================================


def disable_bucket_block(client, bucket):
    """FAIL: s3_bucket_level_public_access_block, s3_bucket_public_access"""
    logger.info(f"[-] Deleting Public Access Block for {bucket}...")
    try:
        client.delete_public_access_block(Bucket=bucket)
        logger.info("    -> Success: Bucket block removed.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


def enable_acls_and_public_access(client, bucket):
    """
    FAIL: s3_bucket_acl_prohibited
    FAIL: s3_bucket_public_list_acl
    FAIL: s3_bucket_public_write_acl
    """
    logger.info(f"[-] Enabling ACLs and Setting Public Read/Write for {bucket}...")
    try:
        # 1. Bật ACLs (ObjectWriter hoặc BucketOwnerPreferred)
        client.put_bucket_ownership_controls(
            Bucket=bucket,
            OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerPreferred"}]},
        )
        # 2. Set ACL Public (Nguy hiểm nhất)
        client.put_bucket_acl(
            Bucket=bucket, ACL="public-read-write"  # Cho phép Everyone LIST và WRITE
        )
        logger.info("    -> Success: Bucket is now Public Read/Write via ACL.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


def set_insecure_policy(client, bucket):
    """
    FAIL: s3_bucket_policy_public_write_access
    FAIL: s3_bucket_secure_transport_policy (Overwrite secure policy)
    FAIL: s3_bucket_cross_account_access (Allow wildcard)
    """
    logger.info(f"[-] Setting Insecure Bucket Policy for {bucket}...")
    # Policy này cho phép tất cả mọi người (Principal *) làm mọi thứ (s3:*)
    # và KHÔNG bắt buộc HTTPS (thiếu condition aws:SecureTransport)
    insecure_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "PublicAccess",
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }
    try:
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(insecure_policy))
        logger.info("    -> Success: Insecure Wildcard Policy applied.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


def disable_encryption(client, bucket):
    """
    FAIL: s3_bucket_default_encryption
    FAIL: s3_bucket_kms_encryption
    """
    logger.info(f"[-] Deleting Encryption Config for {bucket}...")
    try:
        client.delete_bucket_encryption(Bucket=bucket)
        logger.info("    -> Success: Encryption disabled.")
    except ClientError as e:
        logger.info(f"    -> Info: {e} (Maybe already disabled)")


def suspend_versioning(client, bucket):
    """
    FAIL: s3_bucket_object_versioning
    FAIL: s3_bucket_no_mfa_delete (Cannot enable MFA via API easily, but suspending helps fail)
    """
    logger.info(f"[-] Suspending Versioning for {bucket}...")
    try:
        client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Suspended"}
        )
        logger.info("    -> Success: Versioning suspended.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


def disable_logging(client, bucket):
    """FAIL: s3_bucket_server_access_logging_enabled"""
    logger.info(f"[-] Disabling Server Access Logging for {bucket}...")
    try:
        # Gửi empty configuration để tắt logging
        client.put_bucket_logging(Bucket=bucket, BucketLoggingStatus={})
        logger.info("    -> Success: Logging disabled.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


def disable_events(client, bucket):
    """FAIL: s3_bucket_event_notifications_enabled"""
    logger.info(f"[-] Removing Event Notifications for {bucket}...")
    try:
        client.put_bucket_notification_configuration(
            Bucket=bucket, NotificationConfiguration={}
        )
        logger.info("    -> Success: Events removed.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


def disable_lifecycle(client, bucket):
    """FAIL: s3_bucket_lifecycle_enabled"""
    logger.info(f"[-] Deleting Lifecycle Rules for {bucket}...")
    try:
        client.delete_bucket_lifecycle(Bucket=bucket)
        logger.info("    -> Success: Lifecycle rules deleted.")
    except ClientError as e:
        logger.info(f"    -> Info: {e} (Maybe no rules exist)")


def disable_replication(client, bucket):
    """FAIL: s3_bucket_cross_region_replication"""
    logger.info(f"[-] Deleting Replication Config for {bucket}...")
    try:
        client.delete_bucket_replication(Bucket=bucket)
        logger.info("    -> Success: Replication deleted.")
    except ClientError as e:
        logger.info(f"    -> Info: {e} (Maybe no replication exists)")


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================


def main():
    s3 = get_s3_client(REGION)
    s3_control = get_s3_control_client(REGION)

    print("================================================================")
    print("WARNING: APPLYING INSECURE CONFIGURATIONS TO S3 RESOURCES")
    print("================================================================")

    # 1. Fail Account Level Checks
    disable_account_public_block(s3_control, TARGET_ACCOUNT_ID)

    # 2. Fail Bucket Level Checks
    for bucket in TARGET_BUCKETS:
        print(f"\n--- Processing Bucket: {bucket} ---")

        # BPA Checks
        disable_bucket_block(s3, bucket)

        # ACL & Public Access Checks
        enable_acls_and_public_access(s3, bucket)

        # Policy Checks (Secure Transport, Cross Account, Public Write)
        set_insecure_policy(s3, bucket)

        # Encryption Checks
        disable_encryption(s3, bucket)

        # Versioning & MFA Checks
        suspend_versioning(s3, bucket)

        # Logging Checks
        disable_logging(s3, bucket)

        # Event Notification Checks
        disable_events(s3, bucket)

        # Lifecycle Checks
        disable_lifecycle(s3, bucket)

        # Replication Checks
        disable_replication(s3, bucket)

    print("\n================================================================")
    print("DONE. Please run 'verify_findings.py' to confirm everything is FAIL.")


if __name__ == "__main__":
    main()
