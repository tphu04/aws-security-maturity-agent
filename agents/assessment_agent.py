import json
import re
from typing import Dict, Any, Optional, List
from .base_agent import BaseAgent

# Import LangChain
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

class AssessmentAgent(BaseAgent):
    """
    AssessmentAgent v3 (LangChain Integrated)
    ----------------------------------------
    - Nhận input từ RiskEvaluationAgent.
    - Sử dụng LangChain ChatOllama để tránh lỗi kết nối 404.
    - Mapping issue_type cứng (Hard-coded) nếu có.
    - LLM chỉ bổ sung maturity_level, impact, remediation_intent.
    """

    # =========================================================================
    # 1. HARD-CODED MAPPINGS
    # =========================================================================
    KNOWN_MAPPINGS: Dict[str, str] = {
        # --- S3 ---
        "s3_bucket_public_access_block": "MissingPublicAccessBlockConfiguration",
        "s3_account_level_public_access_blocks": "MissingPublicAccessBlockConfiguration",
        "s3_bucket_acl_prohibited": "PublicACL",
        "s3_bucket_public_access": "PublicAccess",
        "s3_bucket_policy_ssl_requests_only": "MissingSecureTransport",
        "s3_bucket_secure_transport_policy": "MissingSecureTransport",
        "s3_bucket_server_side_encryption": "MissingEncryption",
        "s3_bucket_default_encryption": "MissingEncryption",
        "s3_bucket_kms_encryption": "MissingKMSEncryption",
        "s3_bucket_server_access_logging_enabled": "MissingLogging",
        "s3_bucket_logging_enabled": "MissingLogging",
        "s3_bucket_event_notifications_enabled": "MissingEventNotifications",
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
    # 2. SYSTEM PROMPT
    # =========================================================================
    SYSTEM_PROMPT_SINGLE_FINDING = """
### Role
Bạn là **AWS Security Assessment Engine**.

Nhiệm vụ:
- Nhận MỘT finding đã được chuẩn hóa.
- Phân tích và trả về JSON đánh giá Maturity Model.

### Input Fields
Bạn sẽ nhận JSON gồm: issue_hint, check_title, short_description, severity, risk_score.

### Output Format (JSON Only)
{
  "issue_type": "PascalCaseString",
  "service_group": "S3 | IAM | EC2 | ...",
  "maturity_level": 1,        // 1: Basic, 2: Standard, 3: Advanced, 4: Optimized
  "impact": "Mô tả rủi ro ngắn gọn (dưới 20 từ)",
  "remediation_intent": "Mục tiêu tổng quát khi fix lỗi này"
}

### Logic:
- Nếu severity="Critical" -> maturity_level <= 2.
- Nếu risk_score thấp -> maturity_level >= 3.
- impact phải ngắn gọn, súc tích.
"""

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        print(f"[AssessmentAgent] Init LangChain với model {model_name}...")
        
        # Cấu hình ChatOllama (Fix lỗi 404)
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=0,
            format="json"
        )

    # ==========================================================
    # Helper: Parse JSON từ LLM output
    # ==========================================================
    def _get_json_from_llm(self, text: str) -> Optional[dict]:
        # Regex tìm khối JSON
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            try: return json.loads(match.group(1))
            except: pass

        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            try: return json.loads(match.group(1))
            except: pass
        
        # Nếu LLM trả về JSON thuần
        try: return json.loads(text)
        except: return None

    # ==========================================================
    # Helper: Tìm issue_type từ mapping cứng
    # ==========================================================
    def _identify_issue_type(self, issue_hint: Optional[str], finding_id: Optional[str], check_title: Optional[str]) -> Optional[str]:
        if not issue_hint and not finding_id:
            return None

        issue_hint = (issue_hint or "").lower()
        finding_id = (finding_id or "").lower()
        title = (check_title or "").lower()

        # 1. Exact match
        if issue_hint in self.KNOWN_MAPPINGS:
            return self.KNOWN_MAPPINGS[issue_hint]

        # 2. Substring match
        sorted_keys = sorted(self.KNOWN_MAPPINGS.keys(), key=len, reverse=True)
        for key in sorted_keys:
            key_l = key.lower()
            if key_l in issue_hint or key_l in finding_id or key_l in title:
                return self.KNOWN_MAPPINGS[key]
        return None

    # ==========================================================
    # MAIN RUN
    # ==========================================================
    def run(self, cleaned_findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        print("--------------------------------------------------")
        print(f"[AssessmentAgent] 🤖 Đánh giá {len(cleaned_findings)} finding(s) (Clean Input Mode)...")

        assessed_findings_list: List[Dict[str, Any]] = []

        for index, finding in enumerate(cleaned_findings):
            title = finding.get("check_title", "N/A")
            finding_id = finding.get("finding_id", "")
            issue_hint = finding.get("issue_hint", "")
            service_group = finding.get("service_group", "AWS")
            severity = finding.get("severity", "N/A")
            risk_score = finding.get("risk_score", -1)
            short_description = finding.get("short_description", "")

            print(f"--- [{index + 1}/{len(cleaned_findings)}] {title[:60]}...")

            # 1. Map issue_type cứng
            predefined_issue = self._identify_issue_type(issue_hint, finding_id, title)
            
            constraint_text = ""
            if predefined_issue:
                print(f"   🔹 Mapping Found: '{issue_hint}' → '{predefined_issue}'")
                constraint_text = f'CONSTRAINT: issue_type MUST be "{predefined_issue}". service_group MUST be "{service_group}".'
            else:
                print(f"   🔸 No hard mapping found → AI suggestion enabled.")
                constraint_text = "CONSTRAINT: Propose a short PascalCase issue_type."

            # 2. Gọi LLM qua LangChain
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
                FINDING INFO:
                {json.dumps(llm_view, indent=2, ensure_ascii=False)}

                {constraint_text}
                """

                messages = [
                    SystemMessage(content=self.SYSTEM_PROMPT_SINGLE_FINDING),
                    HumanMessage(content=user_prompt)
                ]

                # --- SỬ DỤNG LANGCHAIN INVOKE ---
                response = self.llm.invoke(messages)
                content = response.content
                
                # Parse kết quả
                data = self._get_json_from_llm(content)

                if data:
                    # Enforce Logic
                    if predefined_issue:
                        data["issue_type"] = predefined_issue
                    
                    if not data.get("service_group"):
                        data["service_group"] = service_group
                    else:
                        data["service_group"] = service_group # Ưu tiên giữ nguyên group gốc

                    # Clamp Maturity
                    ml = data.get("maturity_level", 1)
                    try: ml = int(ml)
                    except: ml = 1
                    
                    if severity == "Critical" and ml > 2: ml = 2
                    if severity == "High" and ml > 3: ml = 3
                    if severity == "Low" and ml < 2: ml = 2
                    
                    data["maturity_level"] = ml
                    finding["smm_assessment"] = data

                    print(f"   -> ✅ Result: [{data.get('service_group')}] {data.get('issue_type')} (Maturity: {ml})")
                else:
                    print("   -> ❌ LLM Error: Invalid JSON output.")
                    finding["smm_assessment"] = self._create_fallback(predefined_issue, service_group)

            except Exception as e:
                print(f"   -> ❌ Exception: {e}")
                finding["smm_assessment"] = self._create_fallback(predefined_issue, service_group, str(e))

            assessed_findings_list.append(finding)

        print(f"[AssessmentAgent] ✅ Hoàn tất đánh giá.")
        return assessed_findings_list

    def _create_fallback(self, issue_type, service_group, error_msg=""):
        return {
            "issue_type": issue_type or "UnknownIssue",
            "service_group": service_group or "AWS",
            "maturity_level": 1,
            "impact": "Unknown risk",
            "remediation_intent": "Manual review required",
            "error": error_msg
        }