import json
import datetime
import re


# ============================================================
# 1) HỖ TRỢ TÁCH RESOURCE TỪ MESSAGE (fallback)
# ============================================================


def extract_resource_from_message(msg: str) -> str:
    if not msg:
        return "unknown"

    # 12-digit AWS Account
    acc = re.search(r"\b\d{12}\b", msg)
    if acc:
        return acc.group(0)

    # bucket name
    bucket = re.search(r"\b([a-z0-9\.\-]{3,63})\b", msg)
    if bucket:
        return bucket.group(1)

    return "unknown"


# ============================================================
# 2) CHUẨN HOÁ 1 FINDING DUY NHẤT
# ============================================================


def normalize_finding(raw: dict) -> dict:
    """
    Chuẩn hóa dữ liệu từ Prowler OCSF output thành format thống nhất.
    """

    # ---------- A. FINDING ID ----------
    # Example:
    #   prowler-aws-s3_account_level_public_access_blocks-065209282642-us-east-1-065209282642
    finding_id = raw.get("finding_info", {}).get("uid", "")
    if not finding_id:
        # fallback
        finding_id = raw.get("metadata", {}).get("event_code", "unknown_finding")

    # ---------- B. EVENT CODE ----------
    # Example: s3_account_level_public_access_blocks
    event_code = raw.get("metadata", {}).get("event_code", "")

    # ---------- C. SERVICE ----------
    # CHUẨN NHẤT: resources[0].group.name
    service = "unknown"
    try:
        service = raw["resources"][0]["group"]["name"]  # ex: "s3"
    except:
        if event_code:
            service = event_code.split("_")[0]  # fallback từ event_code

    # ---------- D. RESOURCE ----------
    # CHUẨN NHẤT: resources[0].name
    resource = "unknown"
    try:
        resource = raw["resources"][0]["name"]
    except:
        resource = extract_resource_from_message(raw.get("message", ""))

    # ---------- E. REGION ----------
    # Đúng nhất: raw["cloud"]["region"]
    region = raw.get("cloud", {}).get("region") or raw.get("region") or "unknown"

    # ---------- F. STATUS / SEVERITY ----------
    status = raw.get("status_code", "")  # PASS / FAIL
    severity = raw.get("severity", "Unknown")

    # ---------- G. UID ĐỘC NHẤT ----------
    finding_uid = f"{finding_id}|{resource}"

    # ---------- H. Kết quả cuối ----------
    return {
        "finding_uid": finding_uid,
        "finding_id": finding_id,
        "event_code": event_code,
        "service": service,
        "resource": resource,
        "region": region,
        "severity": severity,
        "status": status,
        "raw": raw,
    }


# ============================================================
# 3) CHUẨN HOÁ DANH SÁCH FINDINGS (DÙNG CHUNG CHO BEFORE/AFTER)
# ============================================================


def normalize_results(structured_report_data: list) -> dict:
    """
    Input: structured_report_data từ MonitoringAgent
    Output chuẩn: pre_scan.json hoặc post_scan.json
    """

    normalized_findings = []

    for job in structured_report_data:
        findings_list = job.get("result", [])
        for raw in findings_list:
            normalized_findings.append(normalize_finding(raw))

    # Metadata cho toàn bộ scan
    return {
        "metadata": {
            "scan_time": datetime.datetime.utcnow().isoformat() + "Z",
            "total_findings": len(normalized_findings),
        },
        "findings": normalized_findings,
    }
