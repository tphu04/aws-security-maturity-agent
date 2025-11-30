import json
import re
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent


class AssessmentAgent(BaseAgent):
    """
    AssessmentAgent v3
    ------------------
    - Nhận input đã được chuẩn hóa từ RiskEvaluationAgent v2 (clean + meta).
    - Không còn đọc nguyên ASFF/Prowler thô.
    - Ưu tiên:
        + Dùng service_group từ RiskAgent (không tự đoán lại).
        + Dùng issue_hint (prowler_check_id) để map issue_type (hard-coded).
    - LLM chỉ dùng để:
        + Bổ sung maturity_level (1-4),
        + impact (mô tả ngắn),
        + remediation_intent.
    - Nếu có mapping cứng → LLM KHÔNG được tự ý đổi issue_type.
    """

    # =========================================================================
    # 1. HARD-CODED MAPPINGS (issue_hint / prowler_check_id → issue_type)
    #    Dùng cho output của RiskAgent v2: finding["issue_hint"]
    # =========================================================================
    KNOWN_MAPPINGS: Dict[str, str] = {
        # --- S3: ACCESS & POLICY ---
        "s3_bucket_public_access_block": "MissingPublicAccessBlockConfiguration",
        "s3_account_level_public_access_blocks": "MissingPublicAccessBlockConfiguration",
        "s3_bucket_acl_prohibited": "PublicACL",
        "s3_bucket_public_access": "PublicAccess",
        "s3_bucket_policy_ssl_requests_only": "MissingSecureTransport",
        "s3_bucket_secure_transport_policy": "MissingSecureTransport",
        # --- S3: ENCRYPTION ---
        "s3_bucket_server_side_encryption": "MissingEncryption",
        "s3_bucket_default_encryption": "MissingEncryption",
        "s3_bucket_kms_encryption": "MissingKMSEncryption",
        # --- S3: LOGGING & MONITORING ---
        "s3_bucket_server_access_logging_enabled": "MissingLogging",
        "s3_bucket_logging_enabled": "MissingLogging",
        "s3_bucket_event_notifications_enabled": "MissingEventNotifications",
        # --- S3: DATA PROTECTION & RECOVERY ---
        "s3_bucket_versioning_enabled": "MissingVersioning",
        "s3_bucket_object_lock": "MissingObjectLock",
        "s3_bucket_cross_region_replication": "MissingCrossRegionReplication",
        "s3_bucket_no_mfa_delete": "MissingMFADelete",
        "s3_bucket_lifecycle_expiration": "MissingLifecyclePolicy",
        # --- IAM ---
        "iam_rotate_access_key_90_days": "AccessKeyRotation",
        "iam_root_mfa_enabled": "RootUserMFA",
        "iam_user_mfa_enabled_console_access": "UserMFA",
        "iam_password_policy_strong": "WeakPasswordPolicy",
        "iam_policy_no_administrative_privileges": "ExcessivePrivileges",
        # --- EC2 ---
        "ec2_security_group_allow_ingress_from_internet_to_any_port": "OpenSecurityGroup",
        "ec2_instance_imdsv2_enabled": "MissingIMDSv2",
        "ec2_ebs_snapshot_encryption": "UnencryptedEBS",
        "ec2_ebs_volume_encryption": "UnencryptedEBS",
    }

    # =========================================================================
    # 2. SYSTEM PROMPT (LLM chỉ làm maturity/impact/remediation_intent)
    # =========================================================================
    SYSTEM_PROMPT_SINGLE_FINDING = """
### Role
Bạn là **AWS Security Assessment Engine**.

Nhiệm vụ:
- Nhận MỘT finding đã được chuẩn hóa (RiskAgent v2).
- Dùng `issue_type` và `service_group` (nếu đã có mapping cứng).
- Nếu không có mapping cứng, bạn được phép gợi ý `issue_type` (dạng PascalCase).

### Input Fields
Bạn sẽ nhận một JSON với các field:
- finding_id: Chuỗi UID duy nhất của finding.
- service_group: Ví dụ "S3", "IAM", "EC2"...
- issue_hint: Mã check Prowler đã rút gọn (vd: "s3_bucket_logging_enabled").
- check_title: Tiêu đề ngắn của finding.
- short_description: Mô tả ngắn gọn (đã truncate).
- severity: Critical | High | Medium | Low | N/A
- risk_score: Số nguyên từ -1 đến 10.

### Output Format (JSON Only)
Bạn BẮT BUỘC chỉ trả về MỘT object JSON duy nhất:

{
  "issue_type": "PascalCaseString",
  "service_group": "S3 | IAM | EC2 | ...",
  "maturity_level": 1,        // 1: Basic, 2: Standard, 3: Advanced, 4: Optimized
  "impact": "Mô tả rủi ro ngắn gọn (dưới 20 từ)",
  "remediation_intent": "Mục tiêu tổng quát khi fix lỗi này"
}

### Gợi ý logics:
- Nếu severity = "Critical" => thường maturity_level <= 2 (chưa trưởng thành).
- Nếu severity = "Low" và risk_score thấp => maturity_level có thể 3 hoặc 4.
- "impact" và "remediation_intent" viết ngắn, rõ, không lan man.
"""

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)

    # ==========================================================
    # Helper: Parse JSON từ LLM output (phòng trường hợp không tuân JSON mode)
    # ==========================================================
    def _get_json_from_llm(self, text: str) -> Optional[dict]:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        return None

    # ==========================================================
    # Helper: Tìm issue_type từ mapping cứng dựa trên issue_hint / finding_id
    # ==========================================================
    def _identify_issue_type(
        self,
        issue_hint: Optional[str],
        finding_id: Optional[str],
        check_title: Optional[str],
    ) -> Optional[str]:
        """
        Ưu tiên:
        1. Exact match trên issue_hint.
        2. Substring match (issue_hint hoặc finding_id) trong KNOWN_MAPPINGS key.
        3. Nếu không tìm được, trả về None (cho LLM tự suy luận).
        """
        if not issue_hint and not finding_id:
            return None

        issue_hint = (issue_hint or "").lower()
        finding_id = (finding_id or "").lower()
        title = (check_title or "").lower()

        # 1. Exact match trên issue_hint
        if issue_hint in self.KNOWN_MAPPINGS:
            return self.KNOWN_MAPPINGS[issue_hint]

        # 2. Substring match: key nằm trong issue_hint / finding_id / title
        sorted_keys = sorted(self.KNOWN_MAPPINGS.keys(), key=len, reverse=True)
        
        for key in sorted_keys:
            issue_type = self.KNOWN_MAPPINGS[key] # Lấy value ra
            key_l = key.lower()
            
            # Kiểm tra key có nằm trong bất kỳ chuỗi input nào không
            if key_l in issue_hint or key_l in finding_id or key_l in title:
                return issue_type

        # ==================================================================

        # 3. Không match được (Giữ nguyên)
        return None

    # ==========================================================
    # MAIN: Đánh giá danh sách findings đã được RiskAgent làm sạch
    # ==========================================================
    def run(self, cleaned_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Input: danh sách findings từ RiskEvaluationAgent v2 (clean + meta).
        Output: mỗi finding bổ sung field "smm_assessment".
        """
        print("--------------------------------------------------")
        print(
            f"[AssessmentAgent] 🤖 Đánh giá {len(cleaned_findings)} finding(s) (Clean Input Mode)..."
        )

        assessed_findings_list: List[Dict[str, Any]] = []

        for index, finding in enumerate(cleaned_findings):
            title = finding.get("check_title", "N/A")
            finding_id = finding.get("finding_id", "")
            issue_hint = finding.get("issue_hint", "")
            service_group = finding.get("service_group", "AWS")
            severity = finding.get("severity", "N/A")
            risk_score = finding.get("risk_score", -1)
            short_description = finding.get("short_description", "")

            print(f"--- [{index + 1}/{len(cleaned_findings)}] {title[:70]}...")

            # 1. Map issue_type từ mapping cứng (nếu có)
            predefined_issue = self._identify_issue_type(
                issue_hint=issue_hint,
                finding_id=finding_id,
                check_title=title,
            )

            if predefined_issue:
                print(
                    f"   🔹 Mapping Found: issue_hint='{issue_hint}' → issue_type='{predefined_issue}' (service_group={service_group})"
                )
                constraint_text = (
                    f"CONSTRAINT (BẮT BUỘC):\n"
                    f'- issue_type: "{predefined_issue}"\n'
                    f'- service_group: "{service_group}"\n'
                    "Bạn KHÔNG được thay đổi issue_type, chỉ được đánh giá maturity_level, impact và remediation_intent."
                )
            else:
                print(f"   🔸 No hard mapping found → cho phép LLM gợi ý issue_type.")
                constraint_text = (
                    "CONSTRAINT: Nếu không có mapping cứng, bạn được phép tự đề xuất issue_type "
                    "(dạng PascalCase, ngắn gọn, mô tả loại vấn đề bảo mật)."
                )

            # Chuẩn bị field smm_assessment mặc định
            finding["smm_assessment"] = {}

            # 2. Gọi LLM để lấy context (maturity, impact, remediation_intent)
            try:
                llm_view = {
                    "finding_id": finding_id,
                    "service_group": service_group,
                    "issue_hint": issue_hint,
                    "check_title": title,
                    "short_description": short_description,
                    "severity": severity,
                    "risk_score": risk_score,
                }

                user_prompt = f"""
FINDING (NORMALIZED JSON):
{json.dumps(llm_view, indent=2, ensure_ascii=False)}

{constraint_text}
"""

                messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT_SINGLE_FINDING},
                    {"role": "user", "content": user_prompt},
                ]

                resp = self.call_llm(messages, response_format={"type": "json_object"})

                data = None
                if resp and resp.content:
                    content_str = (
                        resp.content
                        if isinstance(resp.content, str)
                        else json.dumps(resp.content)
                    )
                    data = self._get_json_from_llm(content_str)

                if data:
                    # 3. Enforce mapping cứng (nếu có)
                    if predefined_issue:
                        data["issue_type"] = predefined_issue

                    # Đảm bảo service_group không bị LLM đổi lung tung
                    if not data.get("service_group"):
                        data["service_group"] = service_group
                    else:
                        # Nếu LLM trả về khác → ưu tiên service_group gốc
                        data["service_group"] = service_group

                    # 4. Clamp maturity_level theo severity (heuristic nhẹ)
                    ml = data.get("maturity_level", 1)
                    try:
                        ml = int(ml)
                    except Exception:
                        ml = 1

                    if severity == "Critical" and ml > 2:
                        ml = 2
                    if severity == "High" and ml > 3:
                        ml = 3
                    if severity == "Low" and ml < 2:
                        # Low severity mà maturity=1 hơi vô lý, đẩy lên ít nhất 2
                        ml = max(2, ml)

                    data["maturity_level"] = ml

                    finding["smm_assessment"] = data  # (Sửa key nếu bạn muốn khác)
                    finding["smm_assessment"] = data  # dùng key này cho thống nhất
                    print(
                        f"   -> ✅ Result: [{data.get('service_group')}] {data.get('issue_type')} (maturity={data.get('maturity_level')})"
                    )

                else:
                    print("   -> ❌ LLM Error: Invalid JSON output.")
                    finding["smm_assessment"] = {
                        "issue_type": predefined_issue or "UnknownIssue",
                        "service_group": service_group or "AWS",
                        "maturity_level": 1,
                        "impact": "Unknown risk",
                        "remediation_intent": "Manual review required",
                    }

            except Exception as e:
                print(f"   -> ❌ Exception in AssessmentAgent: {e}")
                finding["smm_assessment"] = {
                    "issue_type": predefined_issue or "UnknownIssue",
                    "service_group": service_group or "AWS",
                    "maturity_level": 1,
                    "impact": "Unknown risk",
                    "remediation_intent": "Manual review required",
                    "error": str(e),
                }

            assessed_findings_list.append(finding)

        print(f"[AssessmentAgent] ✅ Hoàn tất đánh giá.")
        return assessed_findings_list
