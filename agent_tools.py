import requests
import json
import os
import boto3  # <-- MỚI: Thư viện AWS SDK cho Python
import botocore # <-- MỚI: Để bắt lỗi của Boto3

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
            {"error": "Không thể kết nối đến API server. Bạn đã chạy 'uvicorn api_server:app' chưa?"}
        )
    except requests.exceptions.RequestException as e:
        return json.dumps(
            {"error": f"Lỗi API: {str(e)}", "details": e.response.text if e.response else "N/A"}
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
            {"error": f"Lỗi API: {str(e)}", "details": e.response.text if e.response else "N/A"}
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
            {"error": f"Lỗi API: {str(e)}", "details": e.response.text if e.response else "N/A"}
        )
def remediate_s3_public_access(bucket_name: str, finding_id: str):
    """
    [TOOL] (BOTO3) Sửa lỗi S3 bucket đang public bằng cách bật 'Block all public access'.
    """
    print(f"[RemediateTool] ⚡️ ĐANG SỬA LỖI (Finding: {finding_id}):")
    print(f"   -> Tác vụ: Bật Block Public Access cho bucket '{bucket_name}'...")
    
    try:
        # Khởi tạo client S3
        s3_client = boto3.client('s3')
        
        # Gọi API của AWS
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': True
            }
        )
        
        print(f"   -> ✅ THÀNH CÔNG: Đã chặn public access cho {bucket_name}.")
        return json.dumps({"status": "success", "bucket": bucket_name, "action": "Block Public Access"})

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'AccessDenied':
            print(f"   -> ❌ LỖI: Access Denied. User của bạn thiếu quyền 's3:PutPublicAccessBlock'.")
            return json.dumps({"status": "failed", "bucket": bucket_name, "error": f"Access Denied (Thiếu quyền s3:PutPublicAccessBlock?): {e}"})
        else:
            print(f"   -> ❌ LỖI: {e}")
            return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})
    except Exception as e:
        print(f"   -> ❌ LỖI CHUNG: {e}")
        return json.dumps({"status": "failed", "bucket": bucket_name, "error": str(e)})


def remediate_iam_user_mfa(user_name: str, finding_id: str):
    """
    [TOOL] (BOTO3) Sửa lỗi user IAM không có MFA bằng cách gắn một policy
    bắt buộc MFA (Deny-All-Unless-MFA).
    CẢNH BÁO: Điều này có thể khóa user ra ngoài nếu họ không có MFA!
    """
    print(f"[RemediateTool] ⚡️ ĐANG SỬA LỖI (Finding: {finding_id}):")
    print(f"   -> Tác vụ: Gắn policy bắt buộc MFA cho user '{user_name}'...")

    # Đây là policy JSON (dạng string)
    MFA_POLICY_DOCUMENT = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AllowAllActionsWithMFA",
                "Effect": "Allow",
                "Action": "*",
                "Resource": "*",
                "Condition": {
                    "Bool": {"aws:MultiFactorAuthPresent": "true"}
                }
            },
            {
                "Sid": "DenyAllActionsWithoutMFA",
                "Effect": "Deny",
                "Action": "*",
                "Resource": "*",
                "Condition": {
                    "BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}
                }
            }
        ]
    })
    
    # Tên policy sẽ gắn vào user
    policy_name = f"Auto-Remediate-Force-MFA-{user_name}"

    try:
        iam_client = boto3.client('iam')
        
        # Gắn policy INLINE vào user
        iam_client.put_user_policy(
            UserName=user_name,
            PolicyName=policy_name,
            PolicyDocument=MFA_POLICY_DOCUMENT
        )
        
        print(f"   -> ✅ THÀNH CÔNG: Đã gắn policy '{policy_name}' cho user {user_name}.")
        return json.dumps({"status": "success", "user": user_name, "action": f"Attached inline policy {policy_name}"})

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'AccessDenied':
            print(f"   -> ❌ LỖI: Access Denied. User của bạn thiếu quyền 'iam:PutUserPolicy'.")
            return json.dumps({"status": "failed", "user": user_name, "error": f"Access Denied (Thiếu quyền iam:PutUserPolicy?): {e}"})
        elif error_code == 'EntityAlreadyExists':
            print(f"   -> ⚠️ BỎ QUA: Policy '{policy_name}' đã tồn tại cho user {user_name}.")
            return json.dumps({"status": "skipped", "user": user_name, "message": "Policy already exists."})
        else:
            print(f"   -> ❌ LỖI: {e}")
            return json.dumps({"status": "failed", "user": user_name, "error": str(e)})
    except Exception as e:
        print(f"   -> ❌ LỖI CHUNG: {e}")
        return json.dumps({"status": "failed", "user": user_name, "error": str(e)})
# Ánh xạ tên (string) tới hàm (function)
AVAILABLE_FUNCTIONS = {
    "start_scan_by_group": start_scan_by_group,
    "start_scan_by_file": start_scan_by_file,
    "check_job_status": check_job_status,
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
            "name": "start_scan_by_group", # Quay lại tên cũ
            "description": "Bắt đầu quét AWS theo MỘT tên service (group).",
            "parameters": {
                "type": "object",
                "properties": {
                    "group": {
                        "type": "string", 
                        "description": "Một service, ví dụ: 's3'"
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
            #... (giữ nguyên)
        }
    }
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
                    "bucket_name": {"type": "string", "description": "Tên S3 bucket cần sửa."},
                    "finding_id": {"type": "string", "description": "Mã finding liên quan."},
                }, "required": ["bucket_name", "finding_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remediate_iam_user_mfa",
            "description": "Gắn một policy vào user IAM để bắt buộc họ dùng MFA.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {"type": "string", "description": "Tên user IAM cần sửa."},
                    "finding_id": {"type": "string", "description": "Mã finding liên quan."},
                }, "required": ["user_name", "finding_id"]
            }
        }
    }
]