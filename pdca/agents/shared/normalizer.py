import re
import datetime
from typing import Dict, Any, List

# ============================================================
# 1) HỖ TRỢ TÁCH RESOURCE TỪ MESSAGE (Fallback)
# ============================================================


def extract_resource_from_message(msg: str) -> str:
    if not msg:
        return "unknown"
    acc = re.search(r"\b\d{12}\b", msg)
    if acc:
        return acc.group(0)
    bucket = re.search(r"\b([a-z0-9\.\-]{3,63})\b", msg)
    if bucket:
        return bucket.group(1)
    return "unknown"


# ============================================================
# 2) CHUẨN HOÁ 1 FINDING
# ============================================================


def normalize_finding(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chuẩn hóa dữ liệu Prowler OCSF.
    """
    metadata = raw.get("metadata", {})
    finding_info = raw.get("finding_info", {})
    resources = raw.get("resources", [{}])
    resource_obj = resources[0] if resources else {}
    cloud = raw.get("cloud", {})

    # --- 1. CORE IDENTITY ---
    event_code = metadata.get("event_code", "")
    finding_id = finding_info.get("uid", event_code)

    # --- 2. AWS CONTEXT ---
    account_id = cloud.get("account", {}).get("uid", "")
    region = cloud.get("region") or raw.get("region") or "global"

    # --- 3. RESOURCE DETAILS ---
    service = "unknown"
    try:
        service = resource_obj.get("group", {}).get("name")
        if not service and event_code:
            service = event_code.split("_")[0]
    except:
        pass

    # [FIX] Ưu tiên lấy 'name' (ngắn gọn) trước, nếu không có mới lấy 'uid' (ARN)
    resource_id = resource_obj.get("name") or resource_obj.get("uid")
    if not resource_id:
        resource_id = extract_resource_from_message(raw.get("message", ""))

    # --- 4. STATUS & RISK ---
    status = raw.get("status_code", "FAIL")
    severity = raw.get("severity", "medium").lower()

    # --- 5. DESCRIPTION & REMEDIATION ---
    description = finding_info.get("desc") or raw.get("message", "")

    remediation_rec = raw.get("remediation", {})
    remediation_text = remediation_rec.get("desc", "")

    # [FIX] Logic tìm URL thông minh hơn cho Prowler v5+
    remediation_url = remediation_rec.get("url", "")

    # Nếu không có key 'url', quét trong mảng 'references'
    if not remediation_url:
        references = remediation_rec.get("references", [])
        for ref in references:
            if isinstance(ref, str) and ref.startswith("http"):
                remediation_url = ref
                break

    # Nếu vẫn không có, tìm trong unmapped (cho các version cũ hơn hoặc custom check)
    if not remediation_url:
        remediation_url = raw.get("unmapped", {}).get("related_url", "")

    # --- 6. UID ĐỘC NHẤT ---
    finding_uid = f"{account_id}|{region}|{finding_id}|{resource_id}"

    return {
        "finding_uid": finding_uid,
        "finding_id": finding_id,
        "event_code": event_code,
        "service": service,
        "resource_id": resource_id,
        "account_id": account_id,
        "region": region,
        "severity": severity,
        "status": status,
        "description": description,
        "remediation_text": remediation_text,
        "remediation_url": remediation_url,
    }


# ============================================================
# 3) CHUẨN HOÁ DANH SÁCH
# ============================================================


def normalize_results(flat_findings_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Input: Danh sách phẳng (List[Dict]) từ MonitoringAgent
    Output: Dictionary chứa metadata và danh sách findings đã chuẩn hóa.
    """
    normalized_findings = []

    # Bảo vệ: Đảm bảo input là list
    if not isinstance(flat_findings_list, list):
        flat_findings_list = []

    # Loop trực tiếp qua list phẳng
    for raw in flat_findings_list:
        # Giả sử hàm normalize_finding đã được define ở trên (như code cũ)
        # Tôi lược bỏ để ngắn gọn, hãy giữ lại hàm normalize_finding cũ
        try:
            # Gọi hàm normalize đơn lẻ
            normalized = normalize_finding(raw)
            normalized_findings.append(normalized)
        except Exception:
            continue

    # Trả về cấu trúc có Metadata (Dùng để lưu file JSON đẹp)
    return {
        "metadata": {
            "scan_time": datetime.datetime.utcnow().isoformat() + "Z",
            "total_findings": len(normalized_findings),
        },
        "findings": normalized_findings,  # Key này chứa List chuẩn
    }
