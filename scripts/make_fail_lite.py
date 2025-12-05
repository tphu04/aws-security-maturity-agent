import boto3
import json
import logging
from botocore.exceptions import ClientError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger()

REGION = "us-east-1"
TARGET_BUCKETS = ["logs-065209282642-us-east-1", "prowler-test-public-bucket"]


def get_s3_client(region):
    return boto3.client("s3", region_name=region)


# =====================================================================
# FAIL 1: Disable bucket logging
# =====================================================================
def fail_logging(client, bucket):
    """FAIL: s3_bucket_server_access_logging_enabled"""
    logger.info(f"[1] Disabling bucket logging for {bucket} ...")
    try:
        client.put_bucket_logging(Bucket=bucket, BucketLoggingStatus={})
        logger.info("    -> Logging disabled.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


# =====================================================================
# FAIL 2: Disable bucket notifications
# =====================================================================
def fail_events(client, bucket):
    """FAIL: s3_bucket_event_notifications_enabled"""
    logger.info(f"[2] Removing event notifications for {bucket} ...")
    try:
        client.put_bucket_notification_configuration(
            Bucket=bucket, NotificationConfiguration={}
        )
        logger.info("    -> Events removed.")
    except ClientError as e:
        logger.error(f"    -> Error: {e}")


# =====================================================================
# FAIL 3: Remove lifecycle policy
# =====================================================================
def fail_lifecycle(client, bucket):
    """FAIL: s3_bucket_lifecycle_enabled"""
    logger.info(f"[3] Deleting lifecycle configuration for {bucket} ...")
    try:
        client.delete_bucket_lifecycle(Bucket=bucket)
        logger.info("    -> Lifecycle rules deleted.")
    except ClientError as e:
        logger.info(f"    -> Info: {e}")


# =====================================================================
# MAIN SCRIPT
# =====================================================================
def main():
    s3 = get_s3_client(REGION)

    print("====================================================")
    print("⚠️  APPLYING 3 FAILS TO BUCKETS (SAFE MODE)")
    print("====================================================")

    for bucket in TARGET_BUCKETS:
        print(f"\n--- Processing bucket: {bucket} ---")
        fail_logging(s3, bucket)
        fail_events(s3, bucket)
        fail_lifecycle(s3, bucket)

    print("\n====================================================")
    print("DONE. Run Prowler or verify_findings.py to confirm FAIL.")
    print("====================================================")


if __name__ == "__main__":
    main()
