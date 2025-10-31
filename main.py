import subprocess
import shlex
import json
import os
import uuid  # <-- MỚI: Để tạo job ID
import time  # <-- MỚI: Để theo dõi thời gian
import sys

from fastapi import FastAPI, BackgroundTasks, HTTPException  # <-- THAY ĐỔI
from pydantic import BaseModel
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()  # nạp AWS key từ file .env

app = FastAPI()

# --- Cấu hình (Giữ nguyên) ---
CHECKS_DIR = "custom_checks"
ALLOWED_GROUPS = {
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
}

# --- Job List (Database giả) ---
# <-- MỚI: "Job list" của chúng ta, dùng dictionary trong bộ nhớ
# Trong thực tế, bạn nên dùng Redis hoặc DB
MOCK_JOB_DATABASE: Dict[str, Dict[str, Any]] = {}


# --- Hàm Worker chạy nền ---
# <-- MỚI: Hàm này sẽ chạy trong nền, KHÔNG trả về HTTP response
def _run_prowler_command_worker(job_id: str, command: str):
    """
    Hàm này được gọi bởi BackgroundTasks.
    Nó thực hiện công việc nặng và cập nhật MOCK_JOB_DATABASE.
    """

    # 1. Cập nhật trạng thái job là "running"
    print(f"Job {job_id}: Bắt đầu chạy: {command}")
    job_info = MOCK_JOB_DATABASE.get(job_id)
    if not job_info:
        print(f"Job {job_id}: Lỗi nghiêm trọng, không tìm thấy job để bắt đầu.")
        return  # Thoát

    job_info["status"] = "running"
    job_info["start_time"] = time.time()

    try:
        env = os.environ.copy()
        env["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID", "")
        env["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        env["AWS_DEFAULT_REGION"] = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        env["PYTHONIOENCODING"] = "utf-8"
        env["LC_ALL"] = "C.UTF-8"
        env["LANG"] = "C.UTF-8"
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            check=True,
            timeout=1800,
            encoding="utf-8",
            errors="replace",
            env=env,  # ✅ truyền môi trường AWS vào subprocess
        )

        # (Logic parse kết quả của bạn, giữ nguyên)
        findings_list = []
        summary_lines = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    finding = json.loads(line)
                    findings_list.append(finding)
                except json.JSONDecodeError:
                    summary_lines.append(line)
        summary_text = "\n".join(summary_lines)

        # 2. Cập nhật job là "completed" với kết quả
        print(f"Job {job_id}: Hoàn thành.")
        job_info["status"] = "completed"
        job_info["end_time"] = time.time()
        job_info["duration_seconds"] = job_info["end_time"] - job_info["start_time"]
        job_info["result"] = {
            "status": "success",
            "count": len(findings_list),
            "summary": summary_text,
            "data": findings_list,
        }

    except subprocess.TimeoutExpired:
        print(f"Job {job_id}: Lỗi: Scan quá 30 phút")
        job_info["status"] = "failed"
        job_info["end_time"] = time.time()
        job_info["error"] = "Scan timed out (30 minutes)"

    except subprocess.CalledProcessError as e:
        print(f"Job {job_id}: Lỗi Prowler.")
        print("❌ Lỗi chi tiết:", e.stderr)

        job_info["status"] = "failed"
        job_info["end_time"] = time.time()
        job_info["error"] = {
            "error": "Prowler chạy bị lỗi (CalledProcessError)",
            "stdout_details": e.stdout,
            "stderr_details": e.stderr,
        }

    except Exception as e:
        print(f"Job {job_id}: Lỗi không xác định: {str(e)}")
        job_info["status"] = "failed"
        job_info["end_time"] = time.time()
        job_info["error"] = {"error": "Lỗi không xác định", "details": str(e)}


# --- Endpoint để scan theo nhóm (ĐÃ CẬP NHẬT) ---
@app.get("/scan/check")
def run_simple_scan(group: str, tasks: BackgroundTasks):  # <-- THAY ĐỔI
    if group not in ALLOWED_GROUPS:
        raise HTTPException(status_code=400, detail=f"Nhóm '{group}' không được phép.")

    YOUR_PROFILE_NAME = "default"
    YOUR_DEFAULT_REGION = "us-east-1"
    command = f'"{sys.executable}" -m prowler aws --profile {YOUR_PROFILE_NAME} --region {YOUR_DEFAULT_REGION} --services {group} --output-mode json-ocsf --ignore-exit-code-3 --no-color'

    # --- Logic tạo Job ---
    job_id = f"job_{str(uuid.uuid4())[:8]}"  # Tạo ID
    MOCK_JOB_DATABASE[job_id] = {
        "status": "pending",
        "job_id": job_id,
        "command_details": f"scan group: {group}",
        "submitted_time": time.time(),
        "result": None,
        "error": None,
    }

    # Thêm task vào hàng đợi chạy nền
    tasks.add_task(_run_prowler_command_worker, job_id, command)

    # Trả về ngay lập tức
    print(f"Job {job_id}: Đã thêm vào hàng đợi (scan group: {group})")
    return {
        "status": "pending",
        "job_id": job_id,
        "message": "Scan job đã được bắt đầu.",
    }


# --- Endpoint để scan theo file JSON tùy chỉnh (ĐÃ CẬP NHẬT) ---
@app.get("/scan/custom")
def run_custom_scan(filename: str, tasks: BackgroundTasks):  # <-- THAY ĐỔI
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ.")

    full_path = os.path.join(CHECKS_DIR, filename)
    if not os.path.isfile(full_path):
        raise HTTPException(
            status_code=404, detail=f"Không tìm thấy file check: {full_path}"
        )

    try:
        with open(full_path, "r") as f:
            checks_list = json.load(f)
        if not isinstance(checks_list, list) or not checks_list:
            raise HTTPException(
                status_code=400, detail="File JSON phải là một list và không rỗng."
            )
        checks_string = " ".join(checks_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file JSON: {str(e)}")

    YOUR_PROFILE_NAME = "default"
    YOUR_DEFAULT_REGION = "us-east-1"
    command = f"prowler aws --profile {YOUR_PROFILE_NAME} --region {YOUR_DEFAULT_REGION} --check {checks_string} --output-mode json-ocsf --ignore-exit-code-3"

    # --- Logic tạo Job ---
    job_id = f"job_{str(uuid.uuid4())[:8]}"
    MOCK_JOB_DATABASE[job_id] = {
        "status": "pending",
        "job_id": job_id,
        "command_details": f"scan custom file: {filename}",
        "submitted_time": time.time(),
        "result": None,
        "error": None,
    }

    # Thêm task vào hàng đợi chạy nền
    tasks.add_task(_run_prowler_command_worker, job_id, command)

    # Trả về ngay lập tức
    print(f"Job {job_id}: Đã thêm vào hàng đợi (scan file: {filename})")
    return {
        "status": "pending",
        "job_id": job_id,
        "message": "Scan job đã được bắt đầu.",
    }


# --- API MỚI ĐỂ CHECK JOB STATUS ---
@app.get("/job/status")
def get_job_status(job_id: str):
    """
    Kiểm tra trạng thái của một job đã được bắt đầu.
    """
    job = MOCK_JOB_DATABASE.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID")

    # Nếu job hoàn thành, trả về kết quả
    if job["status"] == "completed":
        return {
            "status": "completed",
            "job_id": job["job_id"],
            "command_details": job["command_details"],
            "duration_seconds": job.get("duration_seconds"),
            "result": job.get("result"),  # Trả về data, summary...
        }

    # Nếu job thất bại, trả về lỗi
    elif job["status"] == "failed":
        return {
            "status": "failed",
            "job_id": job["job_id"],
            "command_details": job["command_details"],
            "error": job.get("error"),
        }

    else:
        return {
            "status": job["status"],  # Sẽ là "pending" hoặc "running"
            "job_id": job["job_id"],
            "message": "Job đang được xử lý...",
        }


# --- API MỚI (Tùy chọn) để xem tất cả job ---
@app.get("/job/list")
def list_all_jobs():
    """
    (Helper) Lấy danh sách tóm tắt của tất cả các job.
    """
    summary_list = {}
    for job_id, job in MOCK_JOB_DATABASE.items():
        summary_list[job_id] = {
            "status": job["status"],
            "details": job["command_details"],
            "submitted_time": job["submitted_time"],
        }
    return summary_list
