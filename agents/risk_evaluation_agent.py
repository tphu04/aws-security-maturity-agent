import json
import re
import time  # Nếu cần throttle
from .base_agent import BaseAgent


class RiskEvaluationAgent(BaseAgent):
    """
    RiskEvaluationAgent v2 (Clean + Meta)
    -------------------------------------
    - Nhận danh sách job kết quả Prowler/OCSF từ MonitoringAgent.
    - Trích xuất các finding có status_code = FAIL.
    - Gọi LLM (JSON mode) cho TỪNG finding để gán:
        + severity: Critical | High | Medium | Low
        + risk_score: 0..10
    - Chuẩn hóa output thành format SẠCH cho AssessmentAgent & RemediateAgent,
      đồng thời giữ lại remediation gốc trong meta.original_remediation.
    """

    SYSTEM_PROMPT_SINGLE = """
    Bạn là một Chuyên gia An ninh mạng AWS (Senior AWS Security Analyst) kiêm API Processor.
    Nhiệm vụ: Phân tích finding bảo mật từ Prowler/SecurityHub và đánh giá rủi ro.

    INPUT: Một JSON object chứa thông tin lỗ hổng (Title, Description, Status Details).
    OUTPUT: Một JSON object duy nhất chứa "severity" và "risk_score".

    --------------------------------------------------------
    HƯỚNG DẪN CHẤM ĐIỂM (SCORING RUBRIC):
    
    1. CRITICAL (Score 9-10):
       - Lỗ hổng cho phép Public Access vào dữ liệu nhạy cảm (S3 Public, Open SG 0.0.0.0/0 port database).
       - Chiếm quyền Admin/Root hoặc leo thang đặc quyền (Privilege Escalation).
       - Mất dữ liệu hoặc mã hóa không thể phục hồi.

    2. HIGH (Score 7-8):
       - Cấu hình sai nghiêm trọng nhưng cần điều kiện để khai thác (VD: IAM Policy quá rộng nhưng nội bộ).
       - Thiếu mã hóa (Encryption) trên dữ liệu quan trọng.
       - Các dịch vụ tính toán (EC2/Lambda) bị phơi bày ra Internet không cần thiết.

    3. MEDIUM (Score 4-6):
       - Vi phạm Best Practice về Logging/Monitoring (Thiếu CloudTrail, VPC Flow Logs).
       - Thiếu MFA trên tài khoản thường.
       - Vi phạm tuân thủ (Compliance) nhưng không gây nguy hiểm tức thì.

    4. LOW (Score 1-3):
       - Các lỗi cấu hình nhỏ, thông tin (Informational).
       - Tagging resources không chuẩn.
       - Các vấn đề ít ảnh hưởng hoặc rủi ro chấp nhận được.

    --------------------------------------------------------
    YÊU CẦU OUTPUT JSON:
    {
        "severity": "Critical" | "High" | "Medium" | "Low",
        "risk_score": <int 0-10>
    }

    QUY TẮC:
    - Chỉ trả về JSON. Không Markdown. Không giải thích.
    - Đọc kỹ 'status_details' hoặc 'description' để quyết định điểm số chính xác.
    """

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.tools_menu = None
        self.available_tools = {}

    # ===============================================================
    # 1. UTIL: Trích JSON từ response LLM
    # ===============================================================
    def _extract_json_from_text(self, text: str) -> str:
        # Ưu tiên khối ```json ... ```
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            print("[RiskEvaluationAgent] ℹ️ (Đã trích xuất JSON từ khối ```json```)")
            return match.group(1)

        # Sau đó tới { ... }
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            print("[RiskEvaluationAgent] ℹ️ (Đã trích xuất JSON từ khối { ... })")
            return match.group(1)

        print(
            "[RiskEvaluationAgent] ⚠️ (Không tìm thấy khối JSON object, trả về text thô)"
        )
        return text

    # ===============================================================
    # 2. PARSER: Làm sạch Prowler job output → list finding thô (chưa enrich)
    # ===============================================================
    def _parse_and_clean_findings(self, raw_job_results: list) -> list:
        """
        Lấy output từ MonitoringAgent (danh sách job_result),
        trích ra các finding có status_code == 'FAIL'.

        Trả về danh sách finding ở dạng "thô đã lọc":
        {
            "finding_id": ...,
            "service": ...,
            "resource_id": ...,
            "region": ...,
            "check_title": ...,
            "prowler_check_id": ...,
            "status": ...,
            "status_details": ...,
            "remediation": {...}  # sẽ được chuyển sang meta ở giai đoạn sau
        }
        """
        print(
            f"[RiskEvaluationAgent] ℹ️ Đang trích xuất findings từ {len(raw_job_results)} kết quả job thô..."
        )
        all_cleaned_findings = []

        for job_result in raw_job_results:
            if job_result.get("status") != "completed" or "result" not in job_result:
                continue

            prowler_output_data = job_result.get("result", {})
            raw_findings = []

            # Prowler có thể trả list hoặc dict dạng {"findings": [...]}
            if isinstance(prowler_output_data, list):
                raw_findings = prowler_output_data
            elif isinstance(prowler_output_data, dict):
                raw_findings = prowler_output_data.get("findings", [])
            elif (
                isinstance(prowler_output_data, str) and ".json" in prowler_output_data
            ):
                print(
                    f"   -> ⚠️ Job {job_result.get('job_id')}: Cần đọc file OCSF (chưa hỗ trợ)."
                )
                continue

            if not raw_findings:
                print(
                    f"   -> ⚠️ Job {job_result.get('job_id')}: 'result' không chứa list findings nào."
                )
                continue

            cleaned_from_job = 0
            for finding in raw_findings:
                if not isinstance(finding, dict):
                    continue

                status = finding.get("status_code", "N/A")
                if status != "FAIL":
                    continue

                finding_info = finding.get("finding_info", {})
                resources = finding.get("resources", [])
                resource = (
                    resources[0] if resources and isinstance(resources, list) else {}
                )

                # 1. Lấy finding_id (UID)
                finding_uid = finding_info.get(
                    "uid",
                    finding.get("unmapped", {}).get("FindingUniqueId", "N/A"),
                )

                # 2. Thử trích Check ID từ finding_uid (định dạng prowler-aws-CHECKID-ACCOUNT-REGION-...)
                prowler_check_id = "N/A"
                try:
                    parts = str(finding_uid).split("-")
                    if len(parts) > 2 and parts[0] == "prowler" and parts[1] == "aws":
                        prowler_check_id = parts[2]
                except Exception:
                    pass  # Không có gì nghiêm trọng, fallback giữ "N/A"

                # 3. Service (group name nếu có)
                service_raw = resource.get("group", {}).get("name") or resource.get(
                    "type", "N/A"
                )

                # 4. Region
                region = resource.get("region") or finding.get("cloud", {}).get(
                    "region", "N/A"
                )

                # 5. Status detail / message
                status_details = finding.get("message") or finding.get(
                    "status_detail", ""
                )

                # 6. Remediation (giữ tạm để chuyển sang meta)
                remediation = finding.get("remediation", {})

                # ---- TẠO CLEAN FINDING THÔ ----
                clean_finding = {
                    "finding_id": finding_uid,
                    "service": service_raw,
                    "resource_id": resource.get("name", "N/A"),
                    "region": region,
                    "check_title": finding_info.get("title", "N/A"),
                    "prowler_check_id": prowler_check_id,
                    "status": status,
                    "status_details": status_details,
                    "remediation": remediation,
                }

                all_cleaned_findings.append(clean_finding)
                cleaned_from_job += 1

            if cleaned_from_job > 0:
                print(
                    f"   -> ℹ️ Job {job_result.get('job_id')}: Trích xuất {cleaned_from_job} finding(s) 'FAIL'."
                )

        return all_cleaned_findings

    # ===============================================================
    # 3. NORMALIZER: Chuẩn hoá output cho AssessmentAgent (CLEAN + META)
    # ===============================================================
    def _clean_output_for_assessment(self, finding: dict, risk_data: dict) -> dict:
        """
        Chuẩn hóa output cho AssessmentAgent & RemediateAgent:
        - Loại bỏ rác và nested phức tạp.
        - Ánh xạ service → service_group chuẩn.
        - Rút gọn mô tả (short_description).
        - Đưa remediation gốc vào meta.original_remediation.
        """

        # --- 1. Normalize service_group ---
        raw_service = str(finding.get("service", "") or "").lower()

        service_alias = {
            "aws s3": "S3",
            "amazon s3": "S3",
            "aws_s3": "S3",
            "s3": "S3",
            "aws iam": "IAM",
            "aws_iam": "IAM",
            "iam": "IAM",
            "ec2": "EC2",
            "aws ec2": "EC2",
            "rds": "RDS",
            "aws rds": "RDS",
        }

        service_group = service_alias.get(raw_service, raw_service.upper() or "AWS")

        # --- 2. issue_hint từ prowler_check_id ---
        issue_hint = finding.get("prowler_check_id") or ""
        if issue_hint == "N/A":
            issue_hint = ""

        issue_hint = str(issue_hint).strip()

        # --- 3. Short description: ưu tiên message/status_details, fallback check_title ---
        raw_desc = finding.get("status_details") or finding.get("check_title") or ""
        short_desc = str(raw_desc).strip()
        if len(short_desc) > 150:
            short_desc = short_desc[:147] + "..."

        # --- 4. Severity & risk_score từ LLM (kèm fallback) ---
        severity = risk_data.get("severity") or "N/A"
        risk_score = risk_data.get("risk_score")

        # Ép kiểu risk_score về int (nếu không phải int thì cho -1)
        try:
            risk_score = int(risk_score)
        except Exception:
            risk_score = -1

        # --- 5. original_remediation đưa vào meta (KHÔNG DÙNG CHO LLM) ---
        original_remediation = finding.get("remediation") or {}

        clean_finding = {
            # Core identity
            "finding_id": finding.get("finding_id"),
            "service_group": service_group,
            "issue_hint": issue_hint,
            "check_title": finding.get("check_title"),
            "short_description": short_desc,
            "resource_id": finding.get("resource_id"),
            "region": finding.get("region"),
            # Risk evaluation
            "severity": severity,
            "risk_score": risk_score,
            # Meta: giữ thêm dữ liệu gốc phục vụ reporting/UI (không đưa vào LLM sau)
            "meta": {
                "original_service_raw": finding.get("service"),
                "original_status": finding.get("status"),
                "original_status_details": finding.get("status_details"),
                "original_remediation": original_remediation,
                "prowler_check_id": finding.get("prowler_check_id"),
            },
        }

        return clean_finding

    # ===============================================================
    # 4. MAIN RUN
    # ===============================================================
    def run(self, raw_job_results: list) -> list:
        """
        Pipeline chính:
        1. Parse + lọc findings FAIL từ kết quả job thô.
        2. Với mỗi finding:
           - Gọi LLM (JSON Mode) để gán severity + risk_score.
           - Chuẩn hóa về clean format (CLEAN + META).
        3. Sort theo severity + risk_score (ưu tiên cao trước).
        """
        print("--------------------------------------------------")

        # BƯỚC 1: LÀM SẠCH FROM JOB
        cleaned_findings = self._parse_and_clean_findings(raw_job_results)
        if not cleaned_findings:
            print("[RiskEvaluationAgent] ⚠️ Không có finding 'FAIL' nào để phân tích.")
            return []

        print(
            f"[RiskEvaluationAgent] 🤖 Đã làm sạch. Bắt đầu phân tích rủi ro cho {len(cleaned_findings)} finding(s) (từng cái một)..."
        )

        enriched_findings_list = []

        # BƯỚC 2: LẶP QUA TỪNG FINDING
        for index, finding in enumerate(cleaned_findings):
            print(
                f"--- [Finding {index + 1}/{len(cleaned_findings)}] Đang xử lý: {finding.get('check_title', 'N/A')[:70]}..."
            )

            try:
                # 1. Tạo "view" cho LLM: KHÔNG gửi remediation gốc
                llm_view = {
                    "finding_id": finding.get("finding_id"),
                    "service": finding.get("service"),
                    "resource_id": finding.get("resource_id"),
                    "region": finding.get("region"),
                    "check_title": finding.get("check_title"),
                    "prowler_check_id": finding.get("prowler_check_id"),
                    "status": finding.get("status"),
                    "status_details": finding.get("status_details"),
                }

                finding_json_string = json.dumps(llm_view, indent=2, ensure_ascii=False)

                user_prompt = f"""
                Hãy phân tích finding (JSON) sau đây và trả về 
                MỘT JSON object chứa "severity" và "risk_score".

                {finding_json_string}
                """

                messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT_SINGLE},
                    {"role": "user", "content": user_prompt},
                ]

                # 2. Gọi LLM (JSON Mode)
                response_message = self.call_llm(
                    messages, response_format={"type": "json_object"}
                )

                if not response_message or not response_message.content:
                    print(f"   -> ❌ Lỗi: AI không trả về phản hồi cho finding này.")
                    risk_data = {"severity": "N/A", "risk_score": -1}
                else:
                    # 3. Parse JSON trả về
                    raw_content = (
                        response_message.content
                        if isinstance(response_message.content, str)
                        else json.dumps(response_message.content)
                    )
                    cleaned_json_string = self._extract_json_from_text(raw_content)
                    try:
                        tmp = json.loads(cleaned_json_string)
                        if isinstance(tmp, dict) and "severity" in tmp:
                            risk_data = tmp
                            print(f"   -> ✅ Thành công: {risk_data}")
                        else:
                            print(f"   -> ❌ Lỗi: JSON sai cấu trúc: {tmp}")
                            risk_data = {"severity": "N/A", "risk_score": -1}
                    except json.JSONDecodeError:
                        print(
                            f"   -> ❌ Lỗi: AI trả về text không phải JSON: {raw_content[:200]}..."
                        )
                        risk_data = {"severity": "N/A", "risk_score": -1}

                # 4. Chuẩn hoá output CLEAN + META
                clean_final = self._clean_output_for_assessment(finding, risk_data)
                enriched_findings_list.append(clean_final)

            except Exception as e:
                print(f"   -> ❌ Lỗi hệ thống khi xử lý finding: {e}")
                fallback = self._clean_output_for_assessment(
                    finding, {"severity": "N/A", "risk_score": -1}
                )
                enriched_findings_list.append(fallback)

            # Nếu cần tránh rate limit:
            # time.sleep(0.5)

        # BƯỚC 3: SẮP XẾP THEO PRIORITY
        print(
            f"[RiskEvaluationAgent] ℹ️ Đã phân tích xong. Đang sắp xếp {len(enriched_findings_list)} finding(s) theo mức độ ưu tiên..."
        )

        severity_map = {
            "Critical": 4,
            "High": 3,
            "Medium": 2,
            "Low": 1,
            "N/A": 0,
        }

        sorted_enriched_list = sorted(
            enriched_findings_list,
            key=lambda f: (
                severity_map.get(f.get("severity"), 0),
                (f.get("risk_score") if isinstance(f.get("risk_score"), int) else -1),
            ),
            reverse=True,
        )

        print(
            f"[RiskEvaluationAgent] ✅ Đã sắp xếp xong. Tổng cộng {len(sorted_enriched_list)} finding(s) đã được làm giàu."
        )
        return sorted_enriched_list
