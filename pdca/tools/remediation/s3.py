"""S3 remediation tools (B13, B15).

Invariants (decision #35, B15):
- Mọi tool LUÔN return `dict` — không bao giờ `json.dumps()`, không raise.
- Bucket name input được sanitize (B15 T10) — invalid → `ToolResult.failed`.
- Manual-only flag được khai báo qua `REGISTRY.register(..., manual_only=True)` (B14).

Bug fixes:
- T7: `s3_prepare_replication` không còn `json.dump(result)` thiếu file handle.
- T8: Mọi `print()` đã được thay bằng `logger.*`.
- T10: Bucket name được sanitize trước khi build IAM policy ARN string.

Bỏ `s3_force_private_acl` (B18 — overlap chức năng với `s3_disable_bucket_acls`,
approach lỗi thời).
"""

from __future__ import annotations

import json
import time
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from langchain_core.tools import tool

from pdca.observability.logger import get_logger
from pdca.tools._common import ToolResult, sanitize_s3_bucket_name
from pdca.tools.registry import REGISTRY

logger = get_logger(__name__)


# ============================================================
# AUTO-FIX TOOLS
# ============================================================

@tool
def s3_block_account_public_access(
    account_id: str, region: str = "us-east-1"
) -> dict:
    """[AUTO-FIX]
    Mục đích: Bật Block Public Access ở cấp tài khoản.
    Dùng khi: Finding yêu cầu chặn truy cập public cho toàn account.
    Tự động: Bật tất cả 4 chính sách public access.
    Giới hạn: Không sửa policy từng bucket; không liên quan tới ACL findings.
    """
    if not isinstance(account_id, str) or not account_id.strip():
        return ToolResult.failed(
            resource=str(account_id), error="account_id phải là string non-empty"
        )

    logger.info("S3 Block Account Public Access", extra={"account_id": account_id})
    try:
        client = boto3.client("s3control", region_name=region)
        resp = client.put_public_access_block(
            AccountId=account_id,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        return ToolResult.success(
            resource=account_id,
            action="enabled account-level Block Public Access",
            request_id=resp.get("ResponseMetadata", {}).get("RequestId"),
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=account_id, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=account_id, error=f"unexpected: {e}")


@tool
def s3_enable_versioning(resource_id: str, region: str = "us-east-1") -> dict:
    """[AUTO-FIX]
    Mục đích: Bật Versioning cho bucket.
    Dùng khi: Bucket thiếu versioning (CRR prerequisite, MFA Delete prerequisite).
    Tự động: Enable versioning.
    Giới hạn: Không bật MFA Delete.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    try:
        client = boto3.client("s3", region_name=region)
        client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )
        return ToolResult.success(resource=bucket, action="Enable Versioning")
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_enable_kms_encryption(
    resource_id: str,
    region: str = "us-east-1",
    kms_key_id: Optional[str] = None,
    algorithm: str = "aws:kms",
) -> dict:
    """[AUTO-FIX]
    Mục đích: Bật default encryption cho bucket (SSE-S3 hoặc SSE-KMS).
    Dùng khi:
      - Finding `s3_bucket_default_encryption` → algorithm="AES256" (rẻ hơn).
      - Finding `s3_bucket_kms_encryption` → algorithm="aws:kms" (mặc định).
    Tự động: Put encryption rule.
    Giới hạn: Ghi đè cấu hình encryption cũ; không tạo KMS Key mới.
    """
    if algorithm not in ("aws:kms", "AES256"):
        return ToolResult.failed(
            resource=resource_id,
            error=f"algorithm phải là 'aws:kms' hoặc 'AES256', got {algorithm!r}",
        )

    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    sse_default: dict = {"SSEAlgorithm": algorithm}
    if algorithm == "aws:kms" and kms_key_id:
        sse_default["KMSMasterKeyID"] = kms_key_id

    encryption_config = {
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": sse_default,
                "BucketKeyEnabled": algorithm == "aws:kms",
            }
        ]
    }

    try:
        client = boto3.client("s3", region_name=region)
        client.put_bucket_encryption(
            Bucket=bucket, ServerSideEncryptionConfiguration=encryption_config
        )
        return ToolResult.success(
            resource=bucket,
            action=f"Enable Default Encryption ({algorithm})",
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_secure_transport(resource_id: str, region: str = "us-east-1") -> dict:
    """[AUTO-FIX]
    Mục đích: Bắt buộc truy cập HTTPS bằng bucket policy.
    Dùng khi: Finding yêu cầu SecureTransport = true.
    Cơ chế: Safe Merge (không ghi đè policy khác) + Self-Verification.
    """
    # T10: sanitize bucket name trước khi nhúng vào IAM policy ARN
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    sid_name = "EnforceSSL"
    ssl_statement = {
        "Sid": sid_name,
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
            f"arn:aws:s3:::{bucket}",
            f"arn:aws:s3:::{bucket}/*",
        ],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
    }

    try:
        client = boto3.client("s3", region_name=region)

        # Safe load existing policy
        try:
            current = client.get_bucket_policy(Bucket=bucket)
            policy = json.loads(current["Policy"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "NoSuchBucketPolicy":
                policy = {"Version": "2012-10-17", "Statement": []}
            elif code == "NoSuchBucket":
                return ToolResult.failed(
                    resource=bucket, error=f"Bucket '{bucket}' not found."
                )
            else:
                raise

        statements = [
            s for s in policy.get("Statement", []) if s.get("Sid") != sid_name
        ]
        statements.append(ssl_statement)
        policy["Statement"] = statements

        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))

        # Verify
        time.sleep(2)
        verify_resp = client.get_bucket_policy(Bucket=bucket)
        verify_policy = json.loads(verify_resp["Policy"])
        is_fixed = any(
            s.get("Sid") == sid_name for s in verify_policy.get("Statement", [])
        )

        if is_fixed:
            return ToolResult.success(
                resource=bucket,
                action="enforced and verified SSL policy",
                note="Prowler/Security Hub may take time to update status to PASSED.",
            )
        return ToolResult.failed(
            resource=bucket,
            error="Policy update sent but verification failed (SCP/Permissions?).",
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_enable_lifecycle_configuration(
    resource_id: str, bucket_name: str = None, region: str = "us-east-1"
) -> dict:
    """[AUTO-FIX]
    Mục đích: Thêm lifecycle rule cơ bản để pass kiểm tra.
    Dùng khi: Bucket thiếu lifecycle configuration.
    Tự động: Tạo rule abort multipart upload sau 7 ngày.
    Giới hạn: Không thêm rule transition nếu không được yêu cầu.
    """
    raw = bucket_name if bucket_name else resource_id
    try:
        bucket = sanitize_s3_bucket_name(raw)
    except ValueError as e:
        return ToolResult.failed(resource=str(raw), error=str(e))

    lifecycle_config = {
        "Rules": [
            {
                "ID": "PruneIncompleteMultipartUploads",
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
            }
        ]
    }
    try:
        client = boto3.client("s3", region_name=region)
        client.put_bucket_lifecycle_configuration(
            Bucket=bucket, LifecycleConfiguration=lifecycle_config
        )
        return ToolResult.success(
            resource=bucket,
            action="Applied Lifecycle Configuration (Abort Incomplete 7 days)",
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_disable_bucket_acls(resource_id: str, region: str = "us-east-1") -> dict:
    """[AUTO-FIX] Khắc phục lỗi 's3_bucket_acl_prohibited'
    Mục đích: Vô hiệu hóa ACL và chuyển sang BucketOwnerEnforced.
    Dùng khi: Finding yêu cầu "ACLs should be disabled".
    Tự động: Put BucketOwnershipControls.
    Giới hạn: Không sửa bucket policy liên quan tới public access.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    try:
        client = boto3.client("s3", region_name=region)

        # Already compliant?
        try:
            resp = client.get_bucket_ownership_controls(Bucket=bucket)
            current = resp["OwnershipControls"]["Rules"][0].get("ObjectOwnership")
            if current == "BucketOwnerEnforced":
                return ToolResult.already_compliant(
                    resource=bucket, message="ACLs already disabled."
                )
        except ClientError:
            pass  # Chưa cấu hình → tiếp tục

        # Reset ACL về private (best-effort, có thể fail nếu Ownership đã Enforced)
        try:
            client.put_bucket_acl(Bucket=bucket, ACL="private")
        except ClientError:
            pass

        client.put_bucket_ownership_controls(
            Bucket=bucket,
            OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
        )
        return ToolResult.success(
            resource=bucket, action="Bucket ACLs disabled (BucketOwnerEnforced)"
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_enable_access_logging(
    resource_id: str,
    region: str = "us-east-1",
    target_bucket: Optional[str] = None,
    account_id: Optional[str] = None,
) -> dict:
    """[AUTO-FIX]
    Mục đích: Bật Access Logging cho bucket.
    Dùng khi: Bucket thiếu server access logging.
    Tự động: Tạo bucket log (nếu cần), cấu hình policy và logging.
    Giới hạn: Không xóa log bucket; tạo bucket mới có thể bị hạn chế trong safe-mode.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    try:
        s3 = boto3.client("s3", region_name=region)

        if not target_bucket:
            target_bucket = (
                f"logs-{account_id}-{region}" if account_id else f"{bucket}-logs"
            )

        try:
            target_bucket = sanitize_s3_bucket_name(target_bucket)
        except ValueError as e:
            return ToolResult.failed(resource=bucket, error=f"target_bucket: {e}")

        # Create log bucket nếu chưa có
        try:
            s3.head_bucket(Bucket=target_bucket)
        except ClientError:
            logger.info("Creating log bucket", extra={"target_bucket": target_bucket})
            if region == "us-east-1":
                s3.create_bucket(Bucket=target_bucket)
            else:
                s3.create_bucket(
                    Bucket=target_bucket,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )
            s3.put_public_access_block(
                Bucket=target_bucket,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )

        if not account_id:
            try:
                account_id = boto3.client("sts").get_caller_identity()["Account"]
            except (ClientError, BotoCoreError):
                account_id = None

        policy_statement = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "S3ServerAccessLogsPolicy",
                    "Effect": "Allow",
                    "Principal": {"Service": "logging.s3.amazonaws.com"},
                    "Action": "s3:PutObject",
                    "Resource": f"arn:aws:s3:::{target_bucket}/*",
                    "Condition": (
                        {"StringEquals": {"aws:SourceAccount": account_id}}
                        if account_id
                        else {}
                    ),
                }
            ],
        }

        logger.info("Applying log delivery bucket policy",
                    extra={"target_bucket": target_bucket})
        s3.put_bucket_policy(
            Bucket=target_bucket, Policy=json.dumps(policy_statement)
        )

        s3.put_bucket_logging(
            Bucket=bucket,
            BucketLoggingStatus={
                "LoggingEnabled": {
                    "TargetBucket": target_bucket,
                    "TargetPrefix": f"logs/{bucket}/",
                }
            },
        )
        return ToolResult.success(
            resource=bucket,
            action=f"Enabled logging to '{target_bucket}'",
            target_bucket=target_bucket,
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_enable_event_notifications(
    resource_id: str, region: str = "us-east-1"
) -> dict:
    """[AUTO-FIX]
    Mục đích: Bật sự kiện ObjectCreated/ObjectRemoved gửi SNS.
    Dùng khi: Finding yêu cầu bucket phải có event notifications.
    Tự động: Tạo SNS topic và cấu hình notification.
    Giới hạn: Có thể tạo resource mới (SNS), cần xác nhận trước khi chạy.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    topic_name = "S3-Security-Notifications"
    try:
        s3 = boto3.client("s3", region_name=region)
        sns = boto3.client("sns", region_name=region)

        topic_arn = sns.create_topic(Name=topic_name)["TopicArn"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "s3.amazonaws.com"},
                    "Action": "SNS:Publish",
                    "Resource": topic_arn,
                    "Condition": {
                        "ArnLike": {"aws:SourceArn": f"arn:aws:s3:::{bucket}"}
                    },
                }
            ],
        }
        sns.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(policy),
        )
        s3.put_bucket_notification_configuration(
            Bucket=bucket,
            NotificationConfiguration={
                "TopicConfigurations": [
                    {
                        "Id": "SecurityAlerts",
                        "TopicArn": topic_arn,
                        "Events": ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"],
                    }
                ]
            },
        )
        return ToolResult.success(
            resource=bucket,
            action=f"Enabled Notifications -> SNS: {topic_name}",
            topic_arn=topic_arn,
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_access_point_block_public_access(
    resource_id: str,
    account_id: str,
    region: str = "us-east-1",
) -> dict:
    """[AUTO-FIX] Khắc phục lỗi 's3_access_point_public_access_block'.
    Mục đích: Bật Block Public Access cho S3 Access Point.
    Dùng khi: Finding cảnh báo Access Point chưa có PAB.
    Tự động: put_access_point_public_access_block với 4 cờ True.
    Giới hạn: KHÔNG áp dụng cho Multi-Region Access Point (xem s3_mrap_*).
    """
    if not isinstance(account_id, str) or not account_id.strip():
        return ToolResult.failed(
            resource=str(resource_id),
            error="account_id phải là string non-empty",
        )
    if not isinstance(resource_id, str) or not resource_id.strip():
        return ToolResult.failed(
            resource=str(resource_id),
            error="resource_id (access point name) phải là string non-empty",
        )

    ap_name = resource_id.strip()
    try:
        client = boto3.client("s3control", region_name=region)
        client.put_access_point_public_access_block(
            AccountId=account_id,
            Name=ap_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        return ToolResult.success(
            resource=ap_name,
            action="Enabled Block Public Access on Access Point",
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=ap_name, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=ap_name, error=f"unexpected: {e}")


@tool
def s3_remove_public_write_policy(
    resource_id: str, region: str = "us-east-1"
) -> dict:
    """[AUTO-FIX] Khắc phục lỗi 's3_bucket_policy_public_write_access'.
    Mục đích: Xóa các statement Allow Principal=* với action ghi (Put/Delete/*).
    Dùng khi: Bucket policy có statement cho phép public write.
    Cơ chế: Load policy → filter statement public-write → put lại + verify.
    Giới hạn: Chỉ filter Principal="*" hoặc {"AWS":"*"}; KHÔNG động vào
              statement có Principal cụ thể (giữ nguyên cross-account hợp lệ).
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    write_actions = ("s3:put", "s3:delete", "s3:replicate", "s3:restore", "s3:*", "*")

    def _is_wildcard(principal) -> bool:
        if principal == "*":
            return True
        if isinstance(principal, dict):
            aws = principal.get("AWS")
            if aws == "*" or aws == ["*"]:
                return True
        return False

    def _has_write(action) -> bool:
        actions = action if isinstance(action, list) else [action]
        return any(
            isinstance(a, str) and a.lower().startswith(write_actions)
            for a in actions
        )

    try:
        client = boto3.client("s3", region_name=region)
        try:
            current = client.get_bucket_policy(Bucket=bucket)
            policy = json.loads(current["Policy"])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "NoSuchBucketPolicy":
                return ToolResult.already_compliant(
                    resource=bucket, message="Bucket has no policy."
                )
            if code == "NoSuchBucket":
                return ToolResult.failed(
                    resource=bucket, error=f"Bucket '{bucket}' not found."
                )
            raise

        original = policy.get("Statement", [])
        filtered = []
        removed = 0
        for stmt in original:
            if (
                stmt.get("Effect") == "Allow"
                and _is_wildcard(stmt.get("Principal"))
                and _has_write(stmt.get("Action", []))
            ):
                removed += 1
                continue
            filtered.append(stmt)

        if removed == 0:
            return ToolResult.already_compliant(
                resource=bucket,
                message="No public-write statements found.",
            )

        if not filtered:
            client.delete_bucket_policy(Bucket=bucket)
            verify_passed = True
        else:
            policy["Statement"] = filtered
            client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
            time.sleep(2)
            verify_resp = client.get_bucket_policy(Bucket=bucket)
            verify_policy = json.loads(verify_resp["Policy"])
            verify_passed = not any(
                stmt.get("Effect") == "Allow"
                and _is_wildcard(stmt.get("Principal"))
                and _has_write(stmt.get("Action", []))
                for stmt in verify_policy.get("Statement", [])
            )

        if verify_passed:
            return ToolResult.success(
                resource=bucket,
                action=f"Removed {removed} public-write statement(s)",
                statements_removed=removed,
            )
        return ToolResult.failed(
            resource=bucket,
            error="Policy update sent but verification still finds public-write.",
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


# ============================================================
# MANUAL-ONLY TOOLS
# ============================================================

@tool
def s3_prepare_replication(
    resource_id: str,
    bucket_name: Optional[str] = None,
    region: str = "us-east-1",
) -> dict:
    """[MANUAL-ONLY]
    Mục đích: Kiểm tra điều kiện để bật Cross-Region Replication (CRR).
    Dùng khi: Finding thiếu CRR hoặc chưa có replication rule.
    Tự động: Chỉ kiểm tra versioning và trạng thái replication.
    Giới hạn: Không tạo IAM Role, bucket đích hoặc replication rule.
    Lưu ý: Luôn yêu cầu thao tác thủ công để hoàn tất CRR.
    """
    raw = bucket_name if bucket_name else resource_id
    try:
        bucket = sanitize_s3_bucket_name(raw)
    except ValueError as e:
        return ToolResult.failed(resource=str(raw), error=str(e))

    # B15 invariant: tool LUÔN return dict — bao toàn bộ AWS path (gồm cả
    # `boto3.client(...)` vì invalid region_name raise InvalidRegionError
    # ngay từ constructor) trong try/except.
    before: dict = {}
    remaining: list[str] = []
    try:
        s3 = boto3.client("s3", region_name=region)

        # Versioning check (B15 T7 fix: bug `json.dump(result)` đã loại bỏ)
        try:
            ver = s3.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
        except ClientError as e:
            return ToolResult.failed(
                resource=bucket,
                error=f"Bucket not found during replication check: {e}",
            )

        before["versioning"] = ver
        if ver != "Enabled":
            remaining.append("Enable bucket versioning")

        # Replication rule check
        try:
            s3.get_bucket_replication(Bucket=bucket)
            before["replication"] = "Exists"
        except ClientError:
            before["replication"] = "NotConfigured"
            remaining.append("Create replication configuration")
    except (BotoCoreError, ClientError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")

    return ToolResult.manual_required(
        resource=bucket,
        remaining=remaining,
        reason="CRR setup cannot be performed automatically in safe mode.",
        verification={"before": before, "after": before, "passed": False},
    )


@tool
def s3_enable_mfa_delete(resource_id: str, region: str = "us-east-1") -> dict:
    """[MANUAL-ONLY]
    Mục đích: Bật versioning để chuẩn bị cho MFA Delete.
    Dùng khi: Finding thiếu MFA Delete.
    Tự động: Bật versioning.
    Giới hạn: Không thể bật MFA Delete (yêu cầu Root + MFA token).
    Lưu ý: Trả về manual-required cho bước bật MFA Delete.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    try:
        client = boto3.client("s3", region_name=region)
        before = client.get_bucket_versioning(Bucket=bucket)
        client.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"}
        )
        after = client.get_bucket_versioning(Bucket=bucket)
        return ToolResult.manual_required(
            resource=bucket,
            remaining=["Enable MFA Delete using AWS CLI with Root MFA token"],
            reason="AWS does not allow enabling MFA Delete programmatically.",
            verification={"before": before, "after": after, "passed": False},
            performed_actions=["Enabled Versioning"],
        )
    except (ClientError, BotoCoreError) as e:
        return ToolResult.failed(resource=bucket, error=str(e))
    except Exception as e:
        return ToolResult.failed(resource=bucket, error=f"unexpected: {e}")


@tool
def s3_enable_object_lock(resource_id: str, region: str = "us-east-1") -> dict:
    """[MANUAL-ONLY]
    Mục đích: Kiểm tra và hướng dẫn bật Object Lock.
    Dùng khi: Finding yêu cầu Object Lock.
    Tự động: Không thể bật Object Lock trên bucket đã tồn tại.
    Giới hạn: Chỉ có thể enable lúc tạo bucket mới.
    Lưu ý: Luôn trả về manual-required.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    return ToolResult.manual_required(
        resource=bucket,
        remaining=[
            "Recreate bucket with ObjectLockEnabled=True OR contact AWS Support"
        ],
        reason="Object Lock cannot be enabled on existing buckets.",
    )


@tool
def s3_remove_cross_account_principals(
    resource_id: str,
    region: str = "us-east-1",
    account_id: Optional[str] = None,
) -> dict:
    """[MANUAL-ONLY] Hỗ trợ phân tích IAM Policy cho lỗi
    's3_bucket_cross_account_access'.
    Mục đích: Gợi ý gỡ quyền truy cập cross-account.
    Dùng khi: Bucket policy cho phép tài khoản ngoài.
    Tự động: Không chỉnh sửa policy trong safe-mode.
    Giới hạn: Chỉ phân tích, không can thiệp.
    Lưu ý: Cần người dùng xem xét và sửa thủ công.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    return ToolResult.manual_required(
        resource=bucket,
        remaining=["Review and remove cross-account principals in bucket policy."],
        reason="Cross-account policy cleanup must be reviewed manually.",
    )


@tool
def s3_enable_intelligent_tiering(
    resource_id: str, region: str = "us-east-1"
) -> dict:
    """[MANUAL-ONLY]
    Mục đích: Gợi ý cấu hình Intelligent-Tiering.
    Dùng khi: Finding liên quan tối ưu chi phí lưu trữ.
    Tự động: Không áp dụng lifecycle rule.
    Giới hạn: Chỉ mô tả đề xuất, không thực thi.
    Lưu ý: Yêu cầu cấu hình thủ công nếu muốn bật.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    return ToolResult.manual_required(
        resource=bucket,
        remaining=[
            "Manually configure Intelligent-Tiering storage class transitions."
        ],
        reason="Tool does not auto-create intelligent-tiering rules.",
    )


@tool
def s3_mrap_block_public_access(
    resource_id: str,
    account_id: Optional[str] = None,
    region: str = "us-east-1",
) -> dict:
    """[MANUAL-ONLY] Khắc phục lỗi 's3_multi_region_access_point_public_access_block'.
    Mục đích: Bật Block Public Access cho Multi-Region Access Point (MRAP).
    Dùng khi: Finding cảnh báo MRAP chưa có PAB.
    Tự động: Không thể — MRAP PAB chỉ set được lúc tạo, không sửa được sau đó.
    Giới hạn: AWS không cung cấp UpdateMultiRegionAccessPoint cho PAB.
    Lưu ý: Phải tạo lại MRAP với PAB enabled rồi migrate alias.
    """
    name = (resource_id or "").strip() or "<unknown>"
    return ToolResult.manual_required(
        resource=name,
        remaining=[
            "Create a new Multi-Region Access Point with all 4 PublicAccessBlock "
            "flags = True, migrate alias usage, then delete the old MRAP.",
        ],
        reason="MRAP Public Access Block is immutable after creation.",
    )


@tool
def s3_bucket_shadow_resource_check(
    resource_id: str, region: str = "us-east-1"
) -> dict:
    """[MANUAL-ONLY] Khắc phục lỗi 's3_bucket_shadow_resource_vulnerability'.
    Mục đích: Cảnh báo bucket name có thể bị "squat" ở region khác (cross-region
              naming predictability — hay gặp với CloudTrail/ELB/Config log buckets).
    Dùng khi: Finding flag bucket có pattern dễ đoán.
    Tự động: Không thể — đổi tên bucket = recreate + migrate dữ liệu.
    Giới hạn: AWS không hỗ trợ rename bucket.
    Lưu ý: Phải tạo bucket mới với tên random/hash và migrate object.
    """
    try:
        bucket = sanitize_s3_bucket_name(resource_id)
    except ValueError as e:
        return ToolResult.failed(resource=resource_id, error=str(e))

    return ToolResult.manual_required(
        resource=bucket,
        remaining=[
            "Create a new bucket with a non-predictable name (include account-id "
            "or random suffix), migrate objects via S3 Batch Replication, update "
            "all references, then delete the old bucket.",
        ],
        reason="Bucket names are immutable; shadow-resource fix requires recreate.",
    )


# ============================================================
# REGISTRY — single source of truth (B14)
# ============================================================

# Auto-fix tools
REGISTRY.register(s3_block_account_public_access, category="remediation")
REGISTRY.register(s3_enable_versioning, category="remediation")
REGISTRY.register(s3_enable_kms_encryption, category="remediation")
REGISTRY.register(s3_secure_transport, category="remediation")
REGISTRY.register(s3_enable_lifecycle_configuration, category="remediation")
REGISTRY.register(s3_disable_bucket_acls, category="remediation")
REGISTRY.register(s3_enable_access_logging, category="remediation")
REGISTRY.register(s3_enable_event_notifications, category="remediation")
REGISTRY.register(s3_access_point_block_public_access, category="remediation")
REGISTRY.register(s3_remove_public_write_policy, category="remediation")

# Manual-only tools — flag được REGISTRY giữ (B14)
REGISTRY.register(s3_prepare_replication, category="remediation", manual_only=True)
REGISTRY.register(s3_enable_mfa_delete, category="remediation", manual_only=True)
REGISTRY.register(s3_enable_object_lock, category="remediation", manual_only=True)
REGISTRY.register(
    s3_remove_cross_account_principals, category="remediation", manual_only=True
)
REGISTRY.register(
    s3_enable_intelligent_tiering, category="remediation", manual_only=True
)
REGISTRY.register(s3_mrap_block_public_access, category="remediation", manual_only=True)
REGISTRY.register(
    s3_bucket_shadow_resource_check, category="remediation", manual_only=True
)
