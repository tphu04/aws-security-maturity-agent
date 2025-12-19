import requests
import json
import os
import boto3
import botocore
from typing import Optional, List, Dict, Any
import time
from botocore.exceptions import ClientError

# --- IMPORTS CHO LANGCHAIN & PYDANTIC V2 ---
from langchain_core.tools import tool
from pydantic import BaseModel, Field

API_SERVER_URL = "http://127.0.0.1:8000"

# ==========================================================
# 1. ĐỊNH NGHĨA INPUT SCHEMA (FIX LỖI SERIALIZATION)
# ==========================================================


class ScanGroupInput(BaseModel):
    group: str = Field(
        ..., description="Tên service AWS cần quét (ví dụ: 's3', 'iam', 'ec2')."
    )


class ScanFileInput(BaseModel):
    filename: str = Field(
        ..., description="Tên file JSON cấu hình nằm trong thư mục custom_checks."
    )


class JobStatusInput(BaseModel):
    job_id: str = Field(..., description="ID của job cần kiểm tra trạng thái.")


class ScanChecksInput(BaseModel):
    check_ids: str = Field(
        ...,
        description="Danh sách các Prowler Check IDs, cách nhau bởi dấu phẩy (vd: 's3_block_account_public_access,iam_root_mfa_enabled').",
    )


# ==========================================================
# 2. CÁC SCANNER TOOLS (Sử dụng args_schema)
# ==========================================================
@tool(args_schema=ScanChecksInput)
def start_scan_by_check_ids(check_ids: str):
    """
    [TOOL] Quét hệ thống AWS theo các Check ID cụ thể (nhỏ hơn và nhanh hơn quét Group).
    Dùng tool này khi người dùng chỉ định rõ vấn đề (vd: logging, mfa, encryption).
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/specific?check_ids={check_ids}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/scan/specific", params={"check_ids": check_ids}
        )
        response.raise_for_status()
        return response.json()  # Trả về JSON luôn cho gọn
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(args_schema=ScanGroupInput)
def start_scan_by_group(group: str):
    """
    [TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN SERVICE.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/check?group={group}")
    try:
        response = requests.get(f"{API_SERVER_URL}/scan/check", params={"group": group})
        response.raise_for_status()

        data = response.json()

        # [QUAN TRỌNG] Đưa job_id ra ngoài để Agent dễ thấy
        # Giả sử API trả về { "job_id": "...", "status": "..." }
        job_id = data.get("job_id")

        return {
            "job_id": job_id,  # <-- FIX: Thêm dòng này để khớp với ScannerAgent
            "success": True,
            "data": data,
            "status_code": response.status_code,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(args_schema=ScanFileInput)
def start_scan_by_file(filename: str):
    """
    [TOOL] Bắt đầu quét tài khoản AWS theo TÊN FILE JSON tùy chỉnh.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/custom?filename={filename}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/scan/custom", params={"filename": filename}
        )
        response.raise_for_status()
        return {
            "success": True,
            "data": response.json(),
            "status_code": response.status_code,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool(args_schema=JobStatusInput)
def check_job_status(job_id: str):
    """
    [TOOL] Kiểm tra trạng thái của một công việc (job) đang chạy.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /job/status?job_id={job_id}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/job/status", params={"job_id": job_id}
        )
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==========================================================
# 3. CÁC REMEDIATION TOOLS (S3)
# ==========================================================


@tool
def s3_block_account_public_access(
    account_id: str, region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    Mục đích: Bật Block Public Access ở cấp tài khoản.
    Dùng khi: Finding yêu cầu chặn truy cập public cho toàn account.
    Tự động: Bật tất cả 4 chính sách public access.
    Giới hạn: Không sửa policy từng bucket; không liên quan tới ACL findings.
    """
    print(
        f"[Tool] 🛠️ Đang thực thi S3 Block Public Access cho Account ID: {account_id}..."
    )

    # Sử dụng s3control cho các thao tác cấp Account
    client = boto3.client("s3control", region_name=region)

    try:
        response = client.put_public_access_block(
            AccountId=account_id,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

        return {
            "success": True,
            "status": "enabled",
            "account_id": account_id,
            "details": "Account-level Block Public Access has been enabled.",
            "request_id": response.get("ResponseMetadata", {}).get("RequestId"),
        }

    except Exception as e:
        return {"success": False, "error": str(e), "account_id": account_id}


@tool
def s3_prepare_replication(
    resource_id: str, bucket_name: str = None, region: str = "us-east-1"
):
    """
    Mục đích: Kiểm tra điều kiện để bật Cross-Region Replication (CRR).
    Dùng khi: Finding thiếu CRR hoặc chưa có replication rule.
    Tự động: Chỉ kiểm tra versioning và trạng thái replication.
    Giới hạn: Không tạo IAM Role, bucket đích hoặc replication rule.
    Lưu ý: Luôn yêu cầu thao tác thủ công để hoàn tất CRR.
    """

    bucket = bucket_name or resource_id
    s3 = boto3.client("s3", region_name=region)

    result = {
        "success": False,
        "status": "manual_required",
        "manual_required": True,
        "resource": bucket,
        "performed_actions": [],
        "remaining_actions": [],
        "verification": {"before": {}, "after": {}, "passed": False},
    }

    try:
        # BEFORE snapshot
        before = {}

        # Check Versioning
        try:
            ver = s3.get_bucket_versioning(Bucket=bucket).get("Status", "Disabled")
        except ClientError:
            result["reason"] = "Bucket not found during replication check."
            json.dump(result)

        before["versioning"] = ver
        if ver != "Enabled":
            result["remaining_actions"].append("Enable bucket versioning")

        # Check Replication Rule
        try:
            s3.get_bucket_replication(Bucket=bucket)
            before["replication"] = "Exists"
        except:
            before["replication"] = "NotConfigured"
            result["remaining_actions"].append("Create replication configuration")

        # AFTER snapshot (unchanged)
        result["verification"]["before"] = before
        result["verification"]["after"] = before
        result["reason"] = "CRR setup cannot be performed automatically in safe mode."

        return json.dumps(result)

    except Exception as e:
        result["status"] = "failed"
        result["reason"] = str(e)
        return json.dumps(result)


@tool
def s3_enable_mfa_delete(resource_id: str, region: str = "us-east-1"):
    """
    Mục đích: Bật versioning để chuẩn bị cho MFA Delete.
    Dùng khi: Finding thiếu MFA Delete.
    Tự động: Bật versioning.
    Giới hạn: Không thể bật MFA Delete (yêu cầu Root + MFA token).
    Lưu ý: Trả về manual-required cho bước bật MFA Delete.
    """

    client = boto3.client("s3", region_name=region)

    result = {
        "success": False,
        "status": "manual_required",
        "manual_required": True,
        "resource": resource_id,
        "performed_actions": [],
        "remaining_actions": ["Enable MFA Delete using AWS CLI with Root MFA token"],
        "reason": "AWS does not allow enabling MFA Delete programmatically.",
        "verification": {"before": {}, "after": {}, "passed": False},
    }

    try:
        # BEFORE
        before = client.get_bucket_versioning(Bucket=resource_id)
        result["verification"]["before"] = before

        # PARTIAL ACTION
        client.put_bucket_versioning(
            Bucket=resource_id, VersioningConfiguration={"Status": "Enabled"}
        )
        result["performed_actions"].append("Enabled Versioning")

        # AFTER
        after = client.get_bucket_versioning(Bucket=resource_id)
        result["verification"]["after"] = after

        return json.dumps(result)

    except Exception as e:
        result["status"] = "failed"
        result["reason"] = str(e)
        return json.dumps(result)


@tool
def s3_enable_object_lock(resource_id: str, region: str = "us-east-1"):
    """
    Mục đích: Kiểm tra và hướng dẫn bật Object Lock.
    Dùng khi: Finding yêu cầu Object Lock.
    Tự động: Không thể bật Object Lock trên bucket đã tồn tại.
    Giới hạn: Chỉ có thể enable lúc tạo bucket mới.
    Lưu ý: Luôn trả về manual-required.
    """

    return {
        "success": False,
        "status": "manual_required",
        "manual_required": True,
        "resource": resource_id,
        "performed_actions": [],
        "remaining_actions": [
            "Recreate bucket with ObjectLockEnabled=True OR contact AWS Support"
        ],
        "reason": "Object Lock cannot be enabled on existing buckets.",
        "verification": {"before": {}, "after": {}, "passed": False},
    }


@tool
def s3_enable_access_logging(
    resource_id: str,
    region: str = "us-east-1",
    target_bucket: Optional[str] = None,
    account_id: str = None,
) -> Dict[str, Any]:
    """
    Mục đích: Bật Access Logging cho bucket.
    Dùng khi: Bucket thiếu server access logging.
    Tự động: Tạo bucket log (nếu cần), cấu hình policy và logging.
    Giới hạn: Không xóa log bucket; tạo bucket mới có thể bị hạn chế trong safe-mode.
    """
    s3 = boto3.client("s3", region_name=region)

    try:
        # 1. XÁC ĐỊNH BUCKET ĐÍCH
        if not target_bucket:
            if account_id:
                target_bucket = f"logs-{account_id}-{region}"
            else:
                target_bucket = f"{resource_id}-logs"

        # 2. TẠO BUCKET LOG (NẾU CHƯA CÓ)
        try:
            s3.head_bucket(Bucket=target_bucket)
        except Exception:
            print(f"[Tool] 🛠️ Creating log bucket: {target_bucket}...")
            if region == "us-east-1":
                s3.create_bucket(Bucket=target_bucket)
            else:
                s3.create_bucket(
                    Bucket=target_bucket,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )

            # Chặn Public Access (Luôn luôn cần thiết)
            s3.put_public_access_block(
                Bucket=target_bucket,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": True,
                    "IgnorePublicAcls": True,
                    "BlockPublicPolicy": True,
                    "RestrictPublicBuckets": True,
                },
            )

        # 3. CẤP QUYỀN GHI LOG BẰNG BUCKET POLICY (THAY VÌ ACL)
        # Đây là cách fix lỗi "The bucket does not allow ACLs"
        # Policy này cho phép dịch vụ logging của AWS ghi vào bucket này

        # Lấy Account ID hiện tại nếu chưa có (để lock policy chặt hơn)
        if not account_id:
            try:
                account_id = boto3.client("sts").get_caller_identity()["Account"]
            except:
                pass

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

        # Merge policy nếu bucket đã có policy cũ (Logic đơn giản hóa: Ghi đè hoặc thêm mới)
        # Ở đây ta dùng put_bucket_policy an toàn
        print(f"[Tool] 🛠️ Applying Bucket Policy for LogDelivery...")
        s3.put_bucket_policy(Bucket=target_bucket, Policy=json.dumps(policy_statement))

        # 4. BẬT LOGGING TRÊN BUCKET NGUỒN
        logging_config = {
            "LoggingEnabled": {
                "TargetBucket": target_bucket,
                "TargetPrefix": f"logs/{resource_id}/",
            }
        }
        s3.put_bucket_logging(Bucket=resource_id, BucketLoggingStatus=logging_config)

        return {
            "success": True,
            "status": "enabled",
            "message": f"Enabled logging to '{target_bucket}' using Bucket Policy.",
            "resource": resource_id,
            "target_bucket": target_bucket,
        }

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "error": str(e),
            "resource": resource_id,
        }


@tool
def s3_enable_event_notifications(resource_id: str, region: str = "us-east-1") -> str:
    """
    Mục đích: Bật sự kiện ObjectCreated/ObjectRemoved gửi SNS.
    Dùng khi: Finding yêu cầu bucket phải có event notifications.
    Tự động: Tạo SNS topic và cấu hình notification.
    Giới hạn: Có thể tạo resource mới (SNS), cần xác nhận trước khi chạy.
    """
    print(f"[Tool] 🛠️ Đang bật Event Notification cho: {resource_id}...")
    s3 = boto3.client("s3", region_name=region)
    sns = boto3.client("sns", region_name=region)

    topic_name = "S3-Security-Notifications"

    try:
        # 1. Tạo SNS Topic
        topic_resp = sns.create_topic(Name=topic_name)
        topic_arn = topic_resp["TopicArn"]

        # 2. Cấp quyền cho S3 bắn tin vào SNS (Access Policy)
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "s3.amazonaws.com"},
                    "Action": "SNS:Publish",
                    "Resource": topic_arn,
                    "Condition": {
                        "ArnLike": {"aws:SourceArn": f"arn:aws:s3:::{resource_id}"}
                    },
                }
            ],
        }
        sns.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(policy),
        )

        # 3. Config S3 Notification
        s3.put_bucket_notification_configuration(
            Bucket=resource_id,
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
        return {
            "success": True,
            "status": "enabled",
            "action": f"Enabled Notifications -> SNS: {topic_name}",
            "resource": resource_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def s3_force_private_acl(resource_id: str, region: str = "us-east-1") -> str:
    """
    Mục đích: Reset ACL bucket về private.
    Dùng khi: Finding phát hiện ACL public.
    Tự động: Set ACL = private.
    Giới hạn: Không chuyển sang BucketOwnerEnforced.

    """
    try:
        client = boto3.client("s3", region_name=region)
        client.put_bucket_acl(Bucket=resource_id, ACL="private")
        return {"success": True, "status": "enabled", "resource": resource_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def s3_enable_versioning(resource_id: str, region: str = "us-east-1") -> str:
    """
    Mục đích: Bật Versioning cho bucket.
    Dùng khi: Bucket thiếu versioning (CRR prerequisite, MFA Delete prerequisite).
    Tự động: Enable versioning.
    Giới hạn: Không bật MFA Delete.

    """
    try:
        client = boto3.client("s3", region_name=region)
        client.put_bucket_versioning(
            Bucket=resource_id, VersioningConfiguration={"Status": "Enabled"}
        )
        return {
            "success": True,
            "status": "enabled",
            "action": "Enable Versioning",
            "resource": resource_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "resource": resource_id}


@tool
def s3_enable_kms_encryption(
    resource_id: str, region: str = "us-east-1", kms_key_id: Optional[str] = None
) -> str:
    """
    Mục đích: Bật mã hóa SSE-KMS.
    Dùng khi: Bucket không có default encryption.
    Tự động: Thêm rule SSE-KMS.
    Giới hạn: Ghi đè cấu hình encryption cũ; không tạo KMS Key mới.

    """
    try:
        client = boto3.client("s3", region_name=region)
        encryption_config = {
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"},
                    "BucketKeyEnabled": True,
                }
            ]
        }
        if kms_key_id:
            encryption_config["Rules"][0]["ApplyServerSideEncryptionByDefault"][
                "KMSMasterKeyID"
            ] = kms_key_id

        client.put_bucket_encryption(
            Bucket=resource_id, ServerSideEncryptionConfiguration=encryption_config
        )
        return {
            "success": True,
            "status": "enabled",
            "action": "Enable KMS Encryption",
            "resource": resource_id,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "resource": resource_id}


@tool
def s3_secure_transport(resource_id: str, region: str = "us-east-1") -> str:
    """
    Mục đích: Bắt buộc truy cập HTTPS bằng bucket policy.
    Dùng khi: Finding yêu cầu SecureTransport = true.
    Cơ chế: Safe Merge (không ghi đè policy khác) + Self-Verification.
    """
    client = boto3.client("s3", region_name=region)
    sid_name = "EnforceSSL"

    # Statement chuẩn để Force SSL
    ssl_statement = {
        "Sid": sid_name,
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
            f"arn:aws:s3:::{resource_id}",
            f"arn:aws:s3:::{resource_id}/*",
        ],
        "Condition": {"Bool": {"aws:SecureTransport": "false"}},
    }

    try:
        # --- BƯỚC 1: LẤY POLICY HIỆN TẠI (SAFE LOAD) ---
        try:
            current_policy_raw = client.get_bucket_policy(Bucket=resource_id)
            policy = json.loads(current_policy_raw["Policy"])
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
                policy = {"Version": "2012-10-17", "Statement": []}
            elif e.response["Error"]["Code"] == "NoSuchBucket":
                return json.dumps(
                    {
                        "success": False,
                        "error": f"Bucket '{resource_id}' not found. Check name vs ARN.",
                    }
                )
            else:
                raise e

        # --- BƯỚC 2: MERGE POLICY (KHÔNG GHI ĐÈ) ---
        statements = policy.get("Statement", [])
        # Xóa rule cũ trùng tên (để cập nhật lại)
        clean_statements = [s for s in statements if s.get("Sid") != sid_name]
        # Thêm rule mới
        clean_statements.append(ssl_statement)
        policy["Statement"] = clean_statements

        # --- BƯỚC 3: CẬP NHẬT LÊN AWS ---
        client.put_bucket_policy(Bucket=resource_id, Policy=json.dumps(policy))

        # --- BƯỚC 4: VERIFY (KIỂM TRA LẠI NGAY LẬP TỨC) ---
        # Chờ 2 giây để AWS đồng bộ
        time.sleep(2)

        # Tải lại policy để xác thực
        verify_resp = client.get_bucket_policy(Bucket=resource_id)
        verify_policy = json.loads(verify_resp["Policy"])

        # Check sự tồn tại của rule EnforceSSL
        is_fixed = any(
            s.get("Sid") == sid_name for s in verify_policy.get("Statement", [])
        )

        if is_fixed:
            return json.dumps(
                {
                    "success": True,
                    "status": "remediated_and_verified",
                    "message": f"Successfully enforced and VERIFIED SSL policy for {resource_id}.",
                    "note": "Prowler/Security Hub may take time to update status to PASSED.",
                }
            )
        else:
            return json.dumps(
                {
                    "success": False,
                    "status": "verification_failed",
                    "error": "Policy update sent but verification failed. Check SCPs or Permissions.",
                }
            )

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def s3_enable_lifecycle_configuration(
    resource_id: str, bucket_name: str = None, region: str = "us-east-1"
) -> dict:
    """
    Mục đích: Thêm lifecycle rule cơ bản để pass kiểm tra.
    Dùng khi: Bucket thiếu lifecycle configuration.
    Tự động: Tạo rule abort multipart upload sau 7 ngày.
    Giới hạn: Không thêm rule transition nếu không được yêu cầu.

    """

    # 1. Logic lấy bucket name an toàn (Chuẩn Parameter Injection)
    # Ưu tiên bucket_name từ tham số truyền vào
    target_bucket = bucket_name if bucket_name else resource_id

    # Làm sạch nếu dính ARN
    if target_bucket and target_bucket.startswith("arn:aws:s3:::"):
        target_bucket = target_bucket.split(":::")[1]
    elif target_bucket:
        target_bucket = target_bucket.strip()

    if not target_bucket:
        return {"success": False, "error": "Could not determine bucket name"}

    # 2. Cấu hình Rule (Gộp logic tối ưu)
    # Rule này đủ để pass bài test của Prowler
    lifecycle_config = {
        "Rules": [
            {
                "ID": "PruneIncompleteMultipartUploads",
                "Status": "Enabled",
                "Filter": {"Prefix": ""},
                # Rule 1: Dọn rác upload lỗi sau 7 ngày
                "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
            }
            # Bạn có thể thêm Rule 2 transition ở đây nếu muốn gộp
        ]
    }

    try:
        client = boto3.client("s3", region_name=region)
        client.put_bucket_lifecycle_configuration(
            Bucket=target_bucket, LifecycleConfiguration=lifecycle_config
        )
        return {
            "success": True,
            "action": "Applied Lifecycle Configuration (Abort Incomplete 7 days)",
            "resource": target_bucket,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "resource": target_bucket}


@tool
def s3_remove_cross_account_principals(
    resource_id: str, region: str = "us-east-1", account_id: Optional[str] = None
) -> str:
    """
    [MANUAL-ONLY] Hỗ trợ phân tích IAM Policy cho lỗi 's3_bucket_cross_account_access'.
    Mục đích: Gợi ý gỡ quyền truy cập cross-account.
    Dùng khi: Bucket policy cho phép tài khoản ngoài.
    Tự động: Không chỉnh sửa policy trong safe-mode.
    Giới hạn: Chỉ phân tích, không can thiệp.
    Lưu ý: Cần người dùng xem xét và sửa thủ công.
    """
    return {
        "success": False,
        "status": "manual_required",
        "manual_required": True,
        "resource": resource_id,
        "performed_actions": [],
        "remaining_actions": [
            "Review and remove cross-account principals in bucket policy."
        ],
        "reason": "Cross-account policy cleanup must be reviewed manually.",
        "verification": {"before": {}, "after": {}, "passed": False},
    }


@tool
def s3_disable_bucket_acls(
    resource_id: str, region: str = "us-east-1"
) -> Dict[str, Any]:
    """
    [AUTO-FIX] Khắc phục lỗi 's3_bucket_acl_prohibited'
    Mục đích: Vô hiệu hóa ACL và chuyển sang BucketOwnerEnforced.
    Dùng khi: Finding yêu cầu "ACLs should be disabled".
    Tự động: Put BucketOwnershipControls.
    Giới hạn: Không sửa bucket policy liên quan tới public access.
    """
    client = boto3.client("s3", region_name=region)
    try:
        # Check current state
        try:
            resp = client.get_bucket_ownership_controls(Bucket=resource_id)
            current = resp["OwnershipControls"]["Rules"][0].get("ObjectOwnership")
            if current == "BucketOwnerEnforced":
                return {
                    "success": True,
                    "status": "skipped",
                    "message": "ACLs already disabled.",
                    "bucket": resource_id,
                }
        except Exception:
            pass  # Chưa cấu hình thì cứ chạy tiếp

        # STEP 1: Cố gắng reset ACL về private trước (Fix lỗi InvalidBucketAcl)
        # Lưu ý: Lệnh này có thể fail nếu Ownership đã là Enforced, nên ta bọc try/except
        try:
            client.put_bucket_acl(Bucket=resource_id, ACL="private")
        except Exception:
            pass

        # STEP 2: Apply BucketOwnerEnforced
        client.put_bucket_ownership_controls(
            Bucket=resource_id,
            OwnershipControls={"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]},
        )

        return {
            "success": True,
            "status": "remediated",
            "message": "Bucket ACLs disabled (BucketOwnerEnforced).",
            "bucket": resource_id,
        }

    except Exception as e:
        return {"success": False, "error": str(e), "bucket": resource_id}


@tool
def s3_enable_intelligent_tiering(resource_id: str, region: str = "us-east-1") -> str:
    """
    Mục đích: Gợi ý cấu hình Intelligent-Tiering.
    Dùng khi: Finding liên quan tối ưu chi phí lưu trữ.
    Tự động: Không áp dụng lifecycle rule.
    Giới hạn: Chỉ mô tả đề xuất, không thực thi.
    Lưu ý: Yêu cầu cấu hình thủ công nếu muốn bật.
    """
    return {
        "success": False,
        "status": "manual_required",
        "manual_required": True,
        "resource": resource_id,
        "performed_actions": [],
        "remaining_actions": [
            "Manually configure Intelligent-Tiering storage class transitions."
        ],
        "reason": "Tool does not auto-create intelligent-tiering rules.",
        "verification": {"before": {}, "after": {}, "passed": False},
    }


# ==========================================================
# 4. EXPORT CẤU HÌNH TOOL (PHẦN QUAN TRỌNG BẠN ĐANG THIẾU)
# ==========================================================

# ⚠️ ĐÂY LÀ BIẾN MÀ SCANNER AGENT ĐANG TÌM KIẾM
AVAILABLE_FUNCTIONS = {
    "start_scan_by_group": start_scan_by_group,
    "start_scan_by_file": start_scan_by_file,
    "start_scan_by_check_ids": start_scan_by_check_ids,
    "check_job_status": check_job_status,
    "remediate_s3_public_access": s3_block_account_public_access,
    "remediate_s3_bucket_versioning": s3_enable_versioning,
    "remediate_s3_kms_encryption": s3_enable_kms_encryption,
    "remediate_s3_secure_transport": s3_secure_transport,
    "remediate_s3_bucket_lifecycle_enabled": s3_enable_lifecycle_configuration,
    "remediate_s3_bucket_cross_account_access": s3_remove_cross_account_principals,
    "remediate_s3_bucket_acl_prohibited": s3_disable_bucket_acls,
    "prepare_s3_bucket_replication": s3_prepare_replication,
    "remediate_s3_bucket_mfa_delete": s3_enable_mfa_delete,
    "remediate_s3_bucket_object_lock": s3_enable_object_lock,
    "remediate_s3_bucket_logging": s3_enable_access_logging,
    "remediate_s3_bucket_event_notifications": s3_enable_event_notifications,
}

# Danh sách tất cả tool cho RemediateAgent

ALLOWED_GROUPS_LIST = [
    "accessanalyzer",
    "account",
    "acm",
    "apigateway",
    "apigatewayv2",
    "appstream",
    "appsync",
    "athena",
    "autoscaling",
    "awslambda",
    "backup",
    "bedrock",
    "cloudformation",
    "cloudfront",
    "cloudtrail",
    "cloudwatch",
    "codeartifact",
    "codebuild",
    "cognito",
    "config",
    "datasync",
    "directconnect",
    "directoryservice",
    "dlm",
    "dms",
    "documentdb",
    "drs",
    "dynamodb",
    "ec2",
    "ecr",
    "ecs",
    "efs",
    "eks",
    "elasticache",
    "elasticbeanstalk",
    "elb",
    "elbv2",
    "emr",
    "eventbridge",
    "firehose",
    "fms",
    "fsx",
    "glacier",
    "glue",
    "guardduty",
    "iam",
    "inspector2",
    "kafka",
    "kinesis",
    "kms",
    "lightsail",
    "macie",
    "memorydb",
    "mq",
    "neptune",
    "networkfirewall",
    "opensearch",
    "organizations",
    "rds",
    "redshift",
    "resourceexplorer2",
    "route53",
    "s3",
    "sagemaker",
    "secretsmanager",
    "securityhub",
    "servicecatalog",
    "ses",
    "shield",
    "sns",
    "sqs",
    "ssm",
    "ssmincidents",
    "stepfunctions",
    "storagegateway",
    "transfer",
    "trustedadvisor",
    "vpc",
    "waf",
    "wafv2",
    "wellarchitected",
    "workspaces",
]

# Danh sách tool cho ScannerAgent
SCANNER_AGENT_TOOLS = [
    start_scan_by_group,
    start_scan_by_file,
    start_scan_by_check_ids,
    check_job_status,
]

# Danh sách tất cả tool cho RemediateAgent
REMEDIATION_TOOLS = [
    # --- S3 Remediation Tools ---
    s3_block_account_public_access,
    s3_enable_versioning,
    s3_enable_kms_encryption,
    s3_secure_transport,
    s3_enable_lifecycle_configuration,
    s3_remove_cross_account_principals,
    s3_disable_bucket_acls,
    s3_prepare_replication,
    s3_enable_mfa_delete,
    s3_enable_object_lock,
    s3_enable_access_logging,
    s3_enable_event_notifications,
    s3_force_private_acl,
    s3_enable_intelligent_tiering,
]

ALL_TOOLS = SCANNER_AGENT_TOOLS + REMEDIATION_TOOLS
