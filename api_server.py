import subprocess
import shlex
import json
import os
import uuid
import time
import sys
import re
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# (Cấu hình CHECKS_DIR, ALLOWED_GROUPS... giữ nguyên)
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

# (PROJECT_ROOT, JOB_OUTPUT_DIR... giữ nguyên)
JOB_OUTPUT_DIR = "job_outputs"
os.makedirs(JOB_OUTPUT_DIR, exist_ok=True)
print(f"Thư mục output cho job: {JOB_OUTPUT_DIR}")


# (MOCK_JOB_DATABASE, strip_ansi_codes... giữ nguyên)
MOCK_JOB_DATABASE: Dict[str, Dict[str, Any]] = {}


def strip_ansi_codes(text: str) -> str:
    if not text:
        return ""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


# --- Hàm Worker chạy nền (ĐÃ SỬA) ---
def _run_prowler_command_worker(job_id: str):

    # (Bước 1: Lấy job_info... giữ nguyên)
    job_info = MOCK_JOB_DATABASE.get(job_id)
    if not job_info:
        print(f"Job {job_id}: Lỗi nghiêm trọng, không tìm thấy job.")
        return
    job_info["status"] = "running"
    job_info["start_time"] = time.time()

    # (Bước 2: Xây dựng Command... giữ nguyên)
    YOUR_PROFILE_NAME = "default"
    YOUR_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    task_type = job_info.get("task_type")
    task_value = job_info.get("task_value")
    output_filename = job_id
    prowler_executable = f'"{sys.executable}" -m prowler'
    command_base = f"{prowler_executable} aws --profile {YOUR_PROFILE_NAME} --region {YOUR_DEFAULT_REGION} --output-mode json-ocsf --ignore-exit-code-3 --no-color"
    command_task = ""
    if task_type == "group":
        command_task = f"--services {task_value}"
    elif task_type == "custom_file":
        command_task = f"--check {task_value}"
    command = f"{command_base} {command_task} --output-directory {JOB_OUTPUT_DIR} --output-filename {output_filename}"
    full_output_path = os.path.join(JOB_OUTPUT_DIR, f"{output_filename}.ocsf.json")

    # (Cài đặt env... giữ nguyên)
    env = os.environ.copy()
    env["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID", "")
    env["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    env["PYTHONIOENCODING"] = "utf-8"
    env["LC_ALL"] = "C.UTF-8"
    env["LANG"] = "C.UTF-8"

    try:
        # (Bước 3: Chạy Prowler... giữ nguyên)
        print(f"Job {job_id}: Bắt đầu chạy: {command}")
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            check=True,
            timeout=1800,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        # --- (BƯỚC 4: SỬA LỖI LOGIC ĐỌC FILE) ---
        print(f"Job {job_id}: Prowler chạy xong. Đang đọc file: {full_output_path}")
        text_summary = strip_ansi_codes(result.stdout)

        findings_data = []  # Biến sẽ chứa dữ liệu JSON

        if os.path.exists(full_output_path):
            entire_file_content = ""  # Biến để debug
            try:
                # SỬA: Đọc toàn bộ file (không đọc từng dòng)
                with open(full_output_path, "r", encoding="utf-8") as f:
                    entire_file_content = f.read()  # Đọc 1 lần

                    if entire_file_content:
                        # Prowler OCSF file là một list các JSON objects
                        findings_data = json.loads(entire_file_content)

                        # Đảm bảo nó là list
                        if not isinstance(findings_data, list):
                            findings_data = [findings_data]

                print(f"Job {job_id}: Đọc được {len(findings_data)} finding(s).")

            except json.JSONDecodeError as e:  # Bắt lỗi JSON cụ thể
                print(f"Job {job_id}: Lỗi khi đọc file OCSF (JSONDecodeError): {e}")
                print(
                    f"   -> Nội dung file (1000 ký tự đầu): {entire_file_content[:1000]}"
                )
            except Exception as e:
                print(f"Job {job_id}: Lỗi khi đọc file OCSF (Exception): {e}")
        else:
            print(
                f"Job {job_id}: Lỗi không tìm thấy file output tại: {full_output_path}"
            )
        # --- (HẾT SỬA LỖI) ---

        # (Bước 5: Cập nhật job... SỬA LẠI KEY ĐỂ AGENT HIỂU)
        job_info["status"] = "completed"
        job_info["end_time"] = time.time()
        job_info["duration_seconds"] = job_info["end_time"] - job_info["start_time"]

        # SỬA: Đặt findings_data vào key "result"
        # mà RiskEvaluationAgent đang tìm kiếm
        job_info["result"] = findings_data

        # (Lưu summary riêng nếu muốn)
        job_info["summary_text"] = text_summary

        # (Lưu ý: cấu trúc cũ của bạn là:)
        # job_info["result"] = {
        #     "status": "success",
        #     "count": len(findings_data),
        #     "summary": text_summary,
        #     "data": findings_data
        # }
        # Cấu trúc mới (job_info["result"] = findings_data) sẽ
        # dễ hơn cho RiskEvaluationAgent (với Kịch bản 1).

    # (Phần 'except' (xử lý lỗi) giữ nguyên)
    except subprocess.TimeoutExpired:
        print(f"Job {job_id}: Lỗi: Scan quá 30 phút")
        job_info["status"] = "failed"
        job_info["error"] = "Scan timed out (30 minutes)"
    except subprocess.CalledProcessError as e:
        print(f"Job {job_id}: Lỗi Prowler.")
        job_info["status"] = "failed"
        job_info["error"] = {
            "error": "Prowler chạy bị lỗi (CalledProcessError)",
            "stdout_details": strip_ansi_codes(e.stdout),
            "stderr_details": strip_ansi_codes(e.stderr),
        }
    except Exception as e:
        print(f"Job {job_id}: Lỗi không xác định: {str(e)}")
        job_info["status"] = "failed"
        job_info["error"] = {"error": "Lỗi không xác định", "details": str(e)}

    finally:
        # (Bước 6: Dọn dẹp file...)
        if os.path.exists(full_output_path):
            try:
                # os.remove(full_output_path) # Tạm thời tắt dọn dẹp để debug
                print(
                    f"Job {job_id}: (Debug) Tạm thời không dọn dẹp file {full_output_path}"
                )
            except Exception as e:
                print(f"Job {job_id}: Lỗi khi dọn dẹp file: {e}")


# (Toàn bộ các endpoint /scan/check, /scan/specific, /scan/custom, /job/status, /job/list giữ nguyên)
@app.get("/scan/check")
def run_simple_scan(group: str, tasks: BackgroundTasks):
    if group not in ALLOWED_GROUPS:
        raise HTTPException(status_code=400, detail=f"Nhóm '{group}' không được phép.")

    job_id = f"job_{str(uuid.uuid4())[:8]}"
    MOCK_JOB_DATABASE[job_id] = {
        "status": "pending",
        "job_id": job_id,
        "command_details": f"scan group: {group}",
        "submitted_time": time.time(),
        "task_type": "group",
        "task_value": group,
        "result": None,
        "error": None,
    }
    tasks.add_task(_run_prowler_command_worker, job_id)
    print(f"Job {job_id}: Đã thêm vào hàng đợi (scan group: {group})")
    return {
        "status": "pending",
        "job_id": job_id,
        "message": "Scan job đã được bắt đầu.",
    }

@app.get("/scan/specific")
def run_specific_checks(check_ids: str, tasks: BackgroundTasks):
    """
    Quét theo danh sách check_id (phân cách bằng dấu phẩy)
    """
    checks_string = check_ids.replace(",", " ").strip()

    job_id = f"job_{str(uuid.uuid4())[:8]}"
    MOCK_JOB_DATABASE[job_id] = {
        "status": "pending",
        "job_id": job_id,
        "command_details": f"scan checks: {checks_string}",
        "submitted_time": time.time(),
        "task_type": "custom_file",      # dùng logic custom_file
        "task_value": checks_string,     # prowler --check
        "result": None,
        "error": None,
    }

    tasks.add_task(_run_prowler_command_worker, job_id)

    print(f"Job {job_id}: Đã thêm vào hàng đợi (scan specific checks)")
    return {
        "status": "pending",
        "job_id": job_id,
        "message": "Specific checks scan started",
    }



@app.get("/scan/custom")
def run_custom_scan(filename: str, tasks: BackgroundTasks):
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

    job_id = f"job_{str(uuid.uuid4())[:8]}"
    MOCK_JOB_DATABASE[job_id] = {
        "status": "pending",
        "job_id": job_id,
        "command_details": f"scan custom file: {filename}",
        "submitted_time": time.time(),
        "task_type": "custom_file",
        "task_value": checks_string,
        "result": None,
        "error": None,
    }
    tasks.add_task(_run_prowler_command_worker, job_id)
    print(f"Job {job_id}: Đã thêm vào hàng đợi (scan file: {filename})")
    return {
        "status": "pending",
        "job_id": job_id,
        "message": "Scan job đã được bắt đầu.",
    }


@app.get("/job/status")
def get_job_status(job_id: str):
    job = MOCK_JOB_DATABASE.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID")
    return job


@app.get("/job/list")
def list_all_jobs():
    summary_list = {}
    for job_id, job in MOCK_JOB_DATABASE.items():
        summary_list[job_id] = {
            "status": job["status"],
            "details": job["command_details"],
            "submitted_time": job["submitted_time"],
        }
    return summary_list
