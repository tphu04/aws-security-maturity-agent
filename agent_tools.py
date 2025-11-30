import requests
import json
import os
import boto3  # <-- MỚI: Thư viện AWS SDK cho Python
import botocore  # <-- MỚI: Để bắt lỗi của Boto3

# -------------------------------------------------------------------
# ĐỊNH NGHĨA CÁC HÀM TOOL (GỌI API)
# -------------------------------------------------------------------

API_SERVER_URL = "http://127.0.0.1:8000"


def start_scan_by_group(group: str):
    """
    [TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN SERVICE (group).
    Ví dụ: 's3', 'iam', 'ec2'.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/check?group={group}")
    try:
        response = requests.get(f"{API_SERVER_URL}/scan/check", params={"group": group})
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError:
        return json.dumps(
            {
                "error": "Không thể kết nối đến API server. Bạn đã chạy 'uvicorn api_server:app' chưa?"
            }
        )
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {
                "error": f"Lỗi API: {str(e)}",
                "details": e.response.text if e.response else "N/A",
            }
        )


def start_scan_by_file(filename: str):
    """
    [TOOL] Bắt đầu một công việc quét tài khoản AWS theo TÊN FILE JSON tùy chỉnh.
    File JSON này phải tồn tại trong thư mục 'custom_checks' trên server.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /scan/custom?filename={filename}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/scan/custom", params={"filename": filename}
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "Không thể kết nối đến API server."})
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {
                "error": f"Lỗi API: {str(e)}",
                "details": e.response.text if e.response else "N/A",
            }
        )


def check_job_status(job_id: str):
    """
    [TOOL] Kiểm tra trạng thái của một công việc (job) quét AWS đã được bắt đầu.
    """
    print(f"[Tool Call] ⚡️ Đang gọi API: /job/status?job_id={job_id}")
    try:
        response = requests.get(
            f"{API_SERVER_URL}/job/status", params={"job_id": job_id}
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.ConnectionError:
        return json.dumps({"error": "Không thể kết nối đến API server."})
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {
                "error": f"Lỗi API: {str(e)}",
                "details": e.response.text if e.response else "N/A",
            }
        )


def remediate_s3_public_access(bucket_name: str, finding_id: str):
    """
    [TOOL] (BOTO3) Sửa lỗi S3 bucket đang public bằng cách bật 'Block all public access'.
    """
    print(f"[RemediateTool] ⚡️ ĐANG SỬA LỖI (Finding: {finding_id}):")
    print(f"   -> Tác vụ: Bật Block Public Access cho bucket '{bucket_name}'...")

    try:
        # Khởi tạo client S3
        s3_client = boto3.client("s3")

        # Gọi API của AWS
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

        print(f"   -> ✅ THÀNH CÔNG: Đã chặn public access cho {bucket_name}.")
        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": "Block Public Access",
            }
        )

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "AccessDenied":
            print(
                f"   -> ❌ LỖI: Access Denied. User của bạn thiếu quyền 's3:PutPublicAccessBlock'."
            )
            return json.dumps(
                {
                    "status": "failed",
                    "bucket": bucket_name,
                    "error": f"Access Denied (Thiếu quyền s3:PutPublicAccessBlock?): {e}",
                }
            )
        else:
            print(f"   -> ❌ LỖI: {e}")
            return json.dumps(
                {"status": "failed", "bucket": bucket_name, "error": str(e)}
            )
    except Exception as e:
        print(f"   -> ❌ LỖI CHUNG: {e}")
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_s3_bucket_versioning(bucket_name: str, finding_id: str):
    """
    [TOOL] (BOTO3) Bật tính năng Versioning cho S3 Bucket.
    Lệnh tương đương AWS CLI:
    aws s3api put-bucket-versioning --bucket <name> --versioning-configuration Status=Enabled
    """
    print(f"[RemediateTool] ⚡️ ĐANG SỬA LỖI (Finding: {finding_id}):")
    print(
        f"   -> Tác vụ: Bật Versioning (Status=Enabled) cho bucket '{bucket_name}'..."
    )

    try:
        s3_client = boto3.client("s3")

        # Gọi API put_bucket_versioning
        s3_client.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )

        print(f"   -> ✅ THÀNH CÔNG: Đã bật Versioning cho {bucket_name}.")
        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": "Enable Bucket Versioning",
            }
        )

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "AccessDenied":
            return json.dumps(
                {
                    "status": "failed",
                    "bucket": bucket_name,
                    "error": "Access Denied (Thiếu quyền s3:PutBucketVersioning)",
                }
            )
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})
    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_iam_user_mfa(user_name: str, finding_id: str):
    """
    [TOOL] (BOTO3) Sửa lỗi user IAM không có MFA bằng cách gắn một policy
    bắt buộc MFA (Deny-All-Unless-MFA).
    CẢNH BÁO: Điều này có thể khóa user ra ngoài nếu họ không có MFA!
    """
    print(f"[RemediateTool] ⚡️ ĐANG SỬA LỖI (Finding: {finding_id}):")
    print(f"   -> Tác vụ: Gắn policy bắt buộc MFA cho user '{user_name}'...")


def remediate_s3_public_access(bucket_name: str, finding_id: str):
    """
    Bật tính năng 'Block Public Access' (chặn truy cập công khai) cho Bucket.
    """
    print(
        f"[RemediateTool] ⚡️ SỬA LỖI (Finding: {finding_id}) -> Block Public Access: {bucket_name}"
    )
    try:
        s3_client = boto3.client("s3")

        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": "Enabled Block Public Access",
            }
        )
    except botocore.exceptions.ClientError as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})
    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_s3_kms_encryption(bucket_name: str, finding_id: str):
    """
    [TOOL] Bật mã hóa Server-Side bằng KMS (SSE-KMS) cho Bucket.
    Sử dụng AWS Managed Key (aws/s3) nếu không chỉ định key riêng.
    Mapping: s3_bucket_kms_encryption (Severity: Low)
    Ref: aws put-bucket-encryption [cite: 22]
    """
    print(
        f"[RemediateTool] ⚡️ SỬA LỖI (Finding: {finding_id}) -> Enable SSE-KMS: {bucket_name}"
    )
    try:
        s3_client = boto3.client("s3")

        # Cấu hình mã hóa sử dụng thuật toán aws:kms
        # Mặc định sẽ dùng AWS Managed Key cho S3 nếu không cung cấp KMSMasterKeyID cụ thể
        encryption_config = {
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"},
                    "BucketKeyEnabled": True,
                }
            ]
        }

        s3_client.put_bucket_encryption(
            Bucket=bucket_name, ServerSideEncryptionConfiguration=encryption_config
        )

        print(f"   -> ✅ THÀNH CÔNG: Đã bật SSE-KMS cho {bucket_name}.")
        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": "Enabled SSE-KMS Encryption",
            }
        )

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "AccessDenied":
            return json.dumps(
                {
                    "status": "failed",
                    "bucket": bucket_name,
                    "error": "Access Denied (Thiếu quyền s3:PutEncryptionConfiguration)",
                }
            )
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})
    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})
    # Đây là policy JSON (dạng string)
    MFA_POLICY_DOCUMENT = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowAllActionsWithMFA",
                    "Effect": "Allow",
                    "Action": "*",
                    "Resource": "*",
                    "Condition": {"Bool": {"aws:MultiFactorAuthPresent": "true"}},
                },
                {
                    "Sid": "DenyAllActionsWithoutMFA",
                    "Effect": "Deny",
                    "Action": "*",
                    "Resource": "*",
                    "Condition": {
                        "BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}
                    },
                },
            ],
        }
    )

    # Tên policy sẽ gắn vào user
    policy_name = f"Auto-Remediate-Force-MFA-{user_name}"

    try:
        iam_client = boto3.client("iam")

        # Gắn policy INLINE vào user
        iam_client.put_user_policy(
            UserName=user_name,
            PolicyName=policy_name,
            PolicyDocument=MFA_POLICY_DOCUMENT,
        )

        print(
            f"   -> ✅ THÀNH CÔNG: Đã gắn policy '{policy_name}' cho user {user_name}."
        )
        return json.dumps(
            {
                "status": "success",
                "user": user_name,
                "action": f"Attached inline policy {policy_name}",
            }
        )

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code == "AccessDenied":
            print(
                f"   -> ❌ LỖI: Access Denied. User của bạn thiếu quyền 'iam:PutUserPolicy'."
            )
            return json.dumps(
                {
                    "status": "failed",
                    "user": user_name,
                    "error": f"Access Denied (Thiếu quyền iam:PutUserPolicy?): {e}",
                }
            )
        elif error_code == "EntityAlreadyExists":
            print(
                f"   -> ⚠️ BỎ QUA: Policy '{policy_name}' đã tồn tại cho user {user_name}."
            )
            return json.dumps(
                {
                    "status": "skipped",
                    "user": user_name,
                    "message": "Policy already exists.",
                }
            )
        else:
            print(f"   -> ❌ LỖI: {e}")
            return json.dumps({"status": "failed", "user": user_name, "error": str(e)})
    except Exception as e:
        print(f"   -> ❌ LỖI CHUNG: {e}")
        return json.dumps({"status": "failed", "user": user_name, "error": str(e)})


# Ánh xạ tên (string) tới hàm (function)
def remediate_s3_secure_transport(bucket_name: str, finding_id: str):
    """
    Thêm Bucket Policy bắt buộc sử dụng HTTPS (TLS).
    Policy này sẽ DENY mọi request có 'aws:SecureTransport': 'false'.
    """
    print(
        f"[RemediateTool] ⚡️ SỬA LỖI (Finding: {finding_id}) -> Enforce SSL (Secure Transport): {bucket_name}"
    )
    try:
        s3_client = boto3.client("s3")

        # Policy bắt buộc HTTPS
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowSSLRequestsOnly",
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:*",
                    "Resource": [
                        f"arn:aws:s3:::{bucket_name}",
                        f"arn:aws:s3:::{bucket_name}/*",
                    ],
                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                }
            ],
        }

        # Lưu ý: Lệnh này sẽ GHI ĐÈ policy hiện tại.
        # Trong môi trường Prod thực tế, cần logic merge policy phức tạp hơn.
        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": "Applied SecureTransport Policy",
            }
        )
    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_s3_lifecycle(bucket_name: str, finding_id: str):
    """
    Thiết lập vòng đời cơ bản: Hủy upload chưa hoàn thành sau 7 ngày (giúp tiết kiệm chi phí và pass rule).
    """
    print(
        f"[RemediateTool] ⚡️ SỬA LỖI (Finding: {finding_id}) -> Enable Lifecycle: {bucket_name}"
    )
    try:
        s3_client = boto3.client("s3")

        lifecycle_config = {
            "Rules": [
                {
                    "ID": "AbortIncompleteMultipartUploads",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},  # Áp dụng cho toàn bộ bucket
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                }
            ]
        }

        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name, LifecycleConfiguration=lifecycle_config
        )
        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": "Enabled Lifecycle (Abort Incomplete Uploads)",
            }
        )
    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_s3_logging(bucket_name: str, finding_id: str):
    print(f"[Tool] ⚡️ Enable Logging (Self-logging): {bucket_name}")
    try:
        s3 = boto3.client("s3")
        # Grant permission to LogDelivery group (Required)
        uri = "http://acs.amazonaws.com/groups/s3/LogDelivery"
        acl = s3.get_bucket_acl(Bucket=bucket_name)
        grants = acl.get("Grants", [])
        grants.extend(
            [
                {"Grantee": {"Type": "Group", "URI": uri}, "Permission": "WRITE"},
                {"Grantee": {"Type": "Group", "URI": uri}, "Permission": "READ_ACP"},
            ]
        )
        s3.put_bucket_acl(
            Bucket=bucket_name,
            AccessControlPolicy={"Grants": grants, "Owner": acl["Owner"]},
        )
        # Enable logging
        s3.put_bucket_logging(
            Bucket=bucket_name,
            BucketLoggingStatus={
                "LoggingEnabled": {"TargetBucket": bucket_name, "TargetPrefix": "logs/"}
            },
        )
        return json.dumps(
            {"status": "success", "action": "Enabled Server Access Logging"}
        )
    except Exception as e:
        return json.dumps({"status": "failed", "error": str(e)})


def remediate_s3_object_lock(bucket_name: str, finding_id: str):
    print(f"[Tool] ⚡️ Enable Object Lock: {bucket_name}")
    try:
        s3 = boto3.client("s3")
        # Bật versioning trước
        s3.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )
        s3.put_object_lock_configuration(
            Bucket=bucket_name,
            ObjectLockConfiguration={
                "ObjectLockEnabled": "Enabled",
                "Rule": {"DefaultRetention": {"Mode": "GOVERNANCE", "Days": 30}},
            },
        )
        return json.dumps({"status": "success", "action": "Enabled Object Lock"})
    except Exception as e:
        return json.dumps({"status": "failed", "error": str(e)})


def remediate_s3_event_notifications(bucket_name: str, finding_id: str):
    """
    [TOOL] Bật Event Notifications cho Bucket.
    Fix lỗi Region: Tự động tìm region của bucket để tạo SNS topic cùng vùng.
    """
    print(f"[RemediateTool] ⚡️ Enable Event Notifications: {bucket_name}...")

    try:
        # 1. Xác định Region của Bucket (Bước quan trọng nhất)
        # Dùng client mặc định để hỏi vị trí
        s3_control = boto3.client("s3")
        loc_resp = s3_control.get_bucket_location(Bucket=bucket_name)
        bucket_region = loc_resp["LocationConstraint"]

        # AWS quirks: Nếu là us-east-1, API trả về None -> Phải gán thủ công
        if bucket_region is None:
            bucket_region = "us-east-1"

        print(f"   -> Bucket nằm tại region: {bucket_region}")

        # 2. Khởi tạo Client S3 và SNS tại ĐÚNG REGION ĐÓ
        s3 = boto3.client("s3", region_name=bucket_region)
        sns = boto3.client("sns", region_name=bucket_region)

        topic_name = "S3-Security-Notifications-Sink"

        # 3. Tạo (hoặc lấy) SNS Topic
        print(f"   -> Đang tạo/kiểm tra SNS Topic: {topic_name}...")
        topic_response = sns.create_topic(Name=topic_name)
        topic_arn = topic_response["TopicArn"]

        # 4. Cấp quyền cho Bucket được phép gửi tin vào SNS Topic
        print(f"   -> Đang cấp quyền cho S3 publish vào SNS...")
        sns_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowS3ToPublish",
                    "Effect": "Allow",
                    "Principal": {"Service": "s3.amazonaws.com"},
                    "Action": "SNS:Publish",
                    "Resource": topic_arn,
                    "Condition": {
                        "ArnLike": {"aws:SourceArn": f"arn:aws:s3:::{bucket_name}"}
                    },
                }
            ],
        }

        sns.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName="Policy",
            AttributeValue=json.dumps(sns_policy),
        )

        # 5. Bật Notification trên Bucket
        print(f"   -> Đang cấu hình S3 Notification...")
        s3.put_bucket_notification_configuration(
            Bucket=bucket_name,
            NotificationConfiguration={
                "TopicConfigurations": [
                    {
                        "Id": "Auto-Remediate-Event-Notify",
                        "TopicArn": topic_arn,
                        "Events": ["s3:ObjectCreated:*"],
                    }
                ]
            },
        )

        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "region": bucket_region,
                "action": f"Enabled Event Notifications -> SNS: {topic_name}",
            }
        )

    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_s3_cross_account(bucket_name: str, finding_id: str):
    """
    Quét Bucket Policy, tìm các Statement cho phép Principal lạ (không thuộc account hiện tại)
    và xóa các Statement đó đi.
    """
    print(f"[RemediateTool] ⚡️ Remove Cross-Account Access: {bucket_name}")
    s3 = boto3.client("s3")
    sts = boto3.client("sts")

    try:
        current_account = sts.get_caller_identity()["Account"]

        # Lấy Policy hiện tại
        try:
            policy_resp = s3.get_bucket_policy(Bucket=bucket_name)
            policy_json = json.loads(policy_resp["Policy"])
        except botocore.exceptions.ClientError as e:
            if "NoSuchBucketPolicy" in str(e):
                return json.dumps(
                    {"status": "success", "action": "No Policy found (Secure)"}
                )
            raise e

        new_statements = []
        modified = False

        for stmt in policy_json.get("Statement", []):
            principal = stmt.get("Principal")
            # Logic đơn giản: Nếu Principal là AWS ARN và KHÔNG chứa account ID hiện tại -> Xóa
            # (Lưu ý: Logic này có thể xóa nhầm quyền CloudFront/Service, cần cẩn thận ở Prod)
            if isinstance(principal, dict) and "AWS" in principal:
                aws_princ = principal["AWS"]
                if isinstance(aws_princ, str):
                    aws_princ = [aws_princ]

                # Kiểm tra xem có ARN nào lạ không
                has_external = any(
                    current_account not in arn and "arn:aws:iam" in arn
                    for arn in aws_princ
                )

                if has_external:
                    print(f"   -> Removing Statement: {stmt.get('Sid', 'Unknown')}")
                    modified = True
                    continue  # Bỏ qua statement này (Xóa)

            new_statements.append(stmt)

        if modified:
            if not new_statements:
                # Nếu xóa hết thì delete luôn policy
                s3.delete_bucket_policy(Bucket=bucket_name)
                return json.dumps(
                    {
                        "status": "success",
                        "action": "Deleted Bucket Policy (All external)",
                    }
                )
            else:
                policy_json["Statement"] = new_statements
                s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy_json))
                return json.dumps(
                    {"status": "success", "action": "Removed External Principals"}
                )
        else:
            return json.dumps(
                {"status": "skipped", "reason": "No cross-account permissions found"}
            )

    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_s3_mfa_delete(bucket_name: str, finding_id: str):
    """
    Cố gắng bật MFA Delete.
    Lưu ý: Việc này yêu cầu Root Account MFA Device Serial + Code.
    Tool này sẽ thử bật nhưng 99% sẽ fail nếu chạy bằng IAM User thường.
    Tuy nhiên, nó giúp Agent không bị crash vì thiếu tool.
    """
    print(f"[RemediateTool] ⚡️ Enable MFA Delete: {bucket_name}")
    try:
        # Đây là lệnh chuẩn, nhưng sẽ thiếu MFA param
        boto3.client("s3").put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={"Status": "Enabled", "MFADelete": "Enabled"},
            # Cần tham số MFA='serial code' ở đây mới chạy được
        )
        return json.dumps({"status": "success", "action": "Enabled MFA Delete"})
    except Exception as e:
        # Trả về lỗi nhưng format đẹp để Agent hiểu là cần làm thủ công
        return json.dumps(
            {
                "status": "manual_required",
                "bucket": bucket_name,
                "message": "MFA Delete requires Root MFA Hardware. Please run CLI manually: aws s3api put-bucket-versioning ... --mfa 'serial code'",
            }
        )


def remediate_s3_replication(bucket_name: str, finding_id: str):
    """
    [TOOL CAO CẤP] Tự động thiết lập Cross-Region Replication (CRR).
    1. Tạo bucket backup tại us-west-2 (nếu bucket chính ở us-east-1).
    2. Tạo IAM Role cho phép S3 replicate.
    3. Bật rule replication.
    """
    print(
        f"[RemediateTool] ⚡️ HIGH RISK FIX: Thiết lập Replication cho {bucket_name}..."
    )

    s3 = boto3.client("s3")
    iam = boto3.client("iam")
    sts = boto3.client("sts")

    try:
        # 1. Xác định Region nguồn và đích
        loc_resp = s3.get_bucket_location(Bucket=bucket_name)
        source_region = loc_resp["LocationConstraint"] or "us-east-1"

        # Chọn region đích khác nguồn (đơn giản hóa cho demo)
        dest_region = "us-west-2" if source_region == "us-east-1" else "us-east-1"
        dest_bucket_name = f"{bucket_name}-backup-{dest_region}"

        account_id = sts.get_caller_identity()["Account"]

        # 2. Tạo Bucket Đích (Destination Bucket)
        print(
            f"   -> Đang tạo/kiểm tra bucket backup: {dest_bucket_name} tại {dest_region}..."
        )
        try:
            if dest_region == "us-east-1":
                s3.create_bucket(Bucket=dest_bucket_name)
            else:
                s3.create_bucket(
                    Bucket=dest_bucket_name,
                    CreateBucketConfiguration={"LocationConstraint": dest_region},
                )
        except botocore.exceptions.ClientError as e:
            if "BucketAlreadyOwnedByYou" not in str(e):
                raise e  # Nếu lỗi không phải do đã tồn tại thì báo lỗi thật

        # 3. Bật Versioning cho cả 2 bucket (Yêu cầu bắt buộc của CRR)
        print("   -> Đang bật Versioning cho cả 2 bucket...")
        s3.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )
        s3.put_bucket_versioning(
            Bucket=dest_bucket_name, VersioningConfiguration={"Status": "Enabled"}
        )

        # 4. Tạo IAM Role cho Replication
        role_name = f"S3-Replication-Role-{bucket_name}"[:64]  # Giới hạn 64 ký tự
        print(f"   -> Đang cấu hình IAM Role: {role_name}...")

        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "s3.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        try:
            iam.create_role(
                RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
        except botocore.exceptions.ClientError as e:
            if "EntityAlreadyExists" not in str(e):
                raise e

        # Gắn quyền cho Role
        permission_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetReplicationConfiguration", "s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}"],
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:GetObjectVersionForReplication",
                        "s3:GetObjectVersionAcl",
                        "s3:GetObjectVersionTagging",
                    ],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                },
                {
                    "Effect": "Allow",
                    "Action": [
                        "s3:ReplicateObject",
                        "s3:ReplicateDelete",
                        "s3:ReplicateTags",
                    ],
                    "Resource": [f"arn:aws:s3:::{dest_bucket_name}/*"],
                },
            ],
        }
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="ReplicationPolicy",
            PolicyDocument=json.dumps(permission_policy),
        )

        # Đợi một chút để IAM Role lan truyền (propagation)
        import time

        time.sleep(5)

        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

        # 5. Kích hoạt Replication Config trên Bucket nguồn
        print("   -> Đang kích hoạt luật Replication...")
        replication_config = {
            "Role": role_arn,
            "Rules": [
                {
                    "ID": "Auto-Remediated-Rule",
                    "Status": "Enabled",
                    "Priority": 1,
                    "DeleteMarkerReplication": {"Status": "Disabled"},
                    "Filter": {"Prefix": ""},  # Replicate All
                    "Destination": {
                        "Bucket": f"arn:aws:s3:::{dest_bucket_name}",
                        "StorageClass": "STANDARD_IA",  # Tiết kiệm chi phí cho backup
                    },
                }
            ],
        }
        s3.put_bucket_replication(
            Bucket=bucket_name, ReplicationConfiguration=replication_config
        )

        return json.dumps(
            {
                "status": "success",
                "bucket": bucket_name,
                "action": f"Enabled Replication to {dest_bucket_name}",
                "details": "Created backup bucket and IAM role successfully.",
            }
        )

    except Exception as e:
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


AVAILABLE_FUNCTIONS = {
    # --- Nhóm Scan & Check ---
    "start_scan_by_group": start_scan_by_group,
    "start_scan_by_file": start_scan_by_file,
    "check_job_status": check_job_status,
    # --- Nhóm Sửa Lỗi (Chính chủ) ---
    "remediate_s3_public_access": remediate_s3_public_access,
    "remediate_s3_bucket_versioning": remediate_s3_bucket_versioning,
    "remediate_s3_kms_encryption": remediate_s3_kms_encryption,
    "remediate_iam_user_mfa": remediate_iam_user_mfa,
    "remediate_s3_secure_transport": remediate_s3_secure_transport,  # <--- Mới
    "remediate_s3_lifecycle": remediate_s3_lifecycle,  # <--- Mới
    "remediate_s3_replication": remediate_s3_replication,
    "remediate_s3_bucket_event_notifications_enabled": remediate_s3_event_notifications,  # Log của bạn gọi tên này
    "remediate_s3_bucket_cross_region_replication": remediate_s3_replication,
    "remediate_s3_cross_account": remediate_s3_cross_account,
    "remediate_s3_mfa_delete": remediate_s3_mfa_delete,
    # --- [MỚI] Nhóm Bí danh (Alias) - Bắt các tên AI hay tự chế ---
    # Nếu AI chế ra tên dài ngoằng, ta trỏ nó về hàm đúng
    "remediate_s3_bucket_object_versioning": remediate_s3_bucket_versioning,
    "remediate_s3_bucket_level_public_access_block": remediate_s3_public_access,
    "remediate_s3_bucket_public_access": remediate_s3_public_access,
    "remediate_s3_bucket_secure_transport_policy": remediate_s3_secure_transport,  # AI hay thêm chữ _policy
    "remediate_s3_bucket_lifecycle_enabled": remediate_s3_lifecycle,
    "remediate_s3_bucket_kms_encryption": remediate_s3_kms_encryption,
    "remediate_s3_bucket_secure_transport_policy": remediate_s3_secure_transport,
    "remediate_s3_bucket_lifecycle_enabled": remediate_s3_lifecycle,
    "remediate_s3_bucket_server_access_logging_enabled": remediate_s3_logging,
    "remediate_s3_bucket_cross_account_access": remediate_s3_cross_account,  # Log của bạn gọi tên này
    "remediate_s3_bucket_object_lock": remediate_s3_object_lock,
    "remediate_s3_event_notifications": remediate_s3_event_notifications,
    "remediate_s3_bucket_no_mfa_delete": remediate_s3_mfa_delete,  # Log của bạn gọi tên này
    "remediate_s3_server_access_logging_enabled": remediate_s3_logging,  # Log của bạn gọi tên này (bỏ chữ bucket)
}
# -------------------------------------------------------------------
# "THỰC ĐƠN" TOOL CHO TỪNG AGENT
# -------------------------------------------------------------------

# Tool cho Agent Điều phối (chỉ được phép "bắt đầu" job)
DISPATCH_AGENT_TOOLS = None
SCANNER_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_scan_by_group",  # Quay lại tên cũ
            "description": "Bắt đầu quét AWS theo MỘT tên service (group).",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": "string",
                        "description": "Một service, ví dụ: 's3'",
                    }
                },
                "required": ["group"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_scan_by_file",
            # ... (giữ nguyên)
        },
    },
]
# Tool cho Agent Giám sát (chỉ được phép "kiểm tra" job)
# (Mặc dù agent này sẽ gọi thẳng, chúng ta vẫn định nghĩa nó)
MONITORING_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_job_status",
            "description": "Kiểm tra trạng thái của một job đang chạy bằng 'job_id' của nó.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Mã ID của job được trả về từ các hàm 'start_scan'.",
                    }
                },
                "required": ["job_id"],
            },
        },
    },
]
REMEDIATE_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "remediate_s3_public_access",
            "description": "Sửa lỗi S3 bucket đang public bằng cách bật 'Block all public access'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bucket_name": {
                        "type": "string",
                        "description": "Tên S3 bucket cần sửa.",
                    },
                    "finding_id": {
                        "type": "string",
                        "description": "Mã finding liên quan.",
                    },
                },
                "required": ["bucket_name", "finding_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remediate_iam_user_mfa",
            "description": "Gắn một policy vào user IAM để bắt buộc họ dùng MFA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {
                        "type": "string",
                        "description": "Tên user IAM cần sửa.",
                    },
                    "finding_id": {
                        "type": "string",
                        "description": "Mã finding liên quan.",
                    },
                },
                "required": ["user_name", "finding_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remediate_s3_kms_encryption",
            "description": "Bật mã hóa KMS cho S3 Bucket.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bucket_name": {"type": "string"},
                    "finding_id": {"type": "string"},
                },
                "required": ["bucket_name", "finding_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {  # <--- TOOL MỚI ĐƯỢC THÊM VÀO ĐÂY
            "name": "remediate_s3_bucket_versioning",
            "description": "Bật tính năng Versioning cho S3 Bucket (dành cho các finding Low/Info về backup/recovery).",
            "parameters": {
                "type": "object",
                "properties": {
                    "bucket_name": {
                        "type": "string",
                        "description": "Tên S3 bucket cần bật versioning.",
                    },
                    "finding_id": {
                        "type": "string",
                        "description": "Mã finding liên quan.",
                    },
                },
                "required": ["bucket_name", "finding_id"],
            },
        },
    },
]
