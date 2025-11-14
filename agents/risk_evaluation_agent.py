import json
import re
import time  # Thêm time để xử lý rate limit (nếu cần)
from .base_agent import BaseAgent


class RiskEvaluationAgent(BaseAgent):
    """
    Agent này nhận một danh sách KẾT QUẢ JOB THÔ từ MonitoringAgent.
    Nó tự làm sạch dữ liệu để trích xuất các finding 'FAIL'.

    (LOGIC MỚI)
    Nó LẶP QUA TỪNG finding, gọi LLM (ở JSON MODE) cho TỪNG CÁI MỘT
    để gán mức độ ưu tiên (Severity) và điểm rủi ro (Risk Score).
    """

    # --- (PROMPT MỚI) ---
    # Prompt này CHỈ YÊU CẦU PHÂN TÍCH 1 FINDING
    SYSTEM_PROMPT_SINGLE = """
    Bạn là một API chỉ trả về MỘT đối tượng JSON duy nhất.
    Nhiệm vụ của bạn là nhận MỘT finding bảo mật.
    Phân tích nó và trả về MỘT JSON object với hai key: "severity" và "risk_score".

    QUY TẮC PHÂN HẠNG:
    - severity: Phải là một trong: "Critical", "High", "Medium", "Low".
    - risk_score: Phải là một số nguyên từ 0 (Info) đến 10 (Critical).

    VÍ DỤ INPUT (USER):
    {"finding_id": "...", "check_title": "S3 bucket server access logging enabled", ...}

    VÍ DỤ OUTPUT (BẠN):
    {"severity": "High", "risk_score": 7}

    KHÔNG GIẢI THÍCH. CHỈ TRẢ VỀ JSON OBJECT.
    """

    # (Prompt cũ không còn được sử dụng)
    # SYSTEM_PROMPT = """..."""

    def __init__(self, model_name: str, api_key: str, base_url: str):
        super().__init__(model_name, api_key, base_url)
        self.tools_menu = None
        self.available_tools = {}

    def _extract_json_from_text(self, text: str) -> str:
        # Ưu tiên tìm OBJECT { ... }
        match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
        if match:
            print("[RiskEvaluationAgent] ℹ️ (Đã trích xuất JSON từ khối ```json)")
            return match.group(1)
        match = re.search(r"(\{[\s\S]*\})", text)
        if match:
            print("[RiskEvaluationAgent] ℹ️ (Đã trích xuất JSON từ khối { ... })")
            return match.group(1)
        print(
            "[RiskEvaluationAgent] ⚠️ (Không tìm thấy khối JSON object, trả về text thô)"
        )
        return text

    # (Hàm _parse_and_clean_findings giữ nguyên, không cần sửa)
    # Nó đã hoạt động tốt (trích xuất 13 finding)
    def _parse_and_clean_findings(self, raw_job_results: list) -> list:
        print(
            f"[RiskEvaluationAgent] ℹ️ Đang trích xuất findings từ {len(raw_job_results)} kết quả job thô..."
        )
        all_cleaned_findings = []

        for job_result in raw_job_results:
            if job_result.get("status") != "completed" or "result" not in job_result:
                continue

            prowler_output_data = job_result.get("result", {})
            raw_findings = []

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
                if status == "FAIL":
                    finding_info = finding.get("finding_info", {})
                    resource = finding.get("resources", [{}])[0]

                    # 1. Lấy finding_id (chuỗi UID)
                    finding_uid = finding_info.get(
                        "uid",
                        finding.get("unmapped", {}).get("FindingUniqueId", "N/A"),
                    )

                    # 2. (LOGIC MỚI) Thử trích xuất Check ID từ finding_uid
                    prowler_check_id = "N/A"
                    try:
                        # Cấu trúc thường là: "prowler-aws-CHECK_ID-ACCOUNT-REGION-..."
                        parts = finding_uid.split("-")
                        if (
                            len(parts) > 2
                            and parts[0] == "prowler"
                            and parts[1] == "aws"
                        ):
                            # Lấy phần tử thứ 3 (index 2) làm ID
                            prowler_check_id = parts[2]
                    except Exception:
                        pass  # Bỏ qua nếu có lỗi

                    # ---- TẠO CLEAN FINDING (ĐÃ SỬA LỖI) ----
                    clean_finding = {
                        "finding_id": finding_uid,  # Sử dụng finding_uid đã lấy
                        "service": resource.get("group", {}).get("name", "N/A"),
                        "resource_id": resource.get("name", "N/A"),
                        "region": resource.get(
                            "region", finding.get("cloud", {}).get("region", "N/A")
                        ),
                        "check_title": finding_info.get("title", "N/A"),
                        # --- DÒNG SỬA QUAN TRỌNG ---
                        # Gán biến prowler_check_id (đã tính ở bước 2) vào đây
                        "prowler_check_id": prowler_check_id,
                        # -------------------------
                        "status": status,
                        "status_details": finding.get(
                            "message", finding.get("status_detail", "N/A")
                        ),
                        "remediation": finding.get("remediation", {}),
                    }
                    all_cleaned_findings.append(clean_finding)
                    cleaned_from_job += 1

            if cleaned_from_job > 0:
                print(
                    f"   -> ℹ️ Job {job_result.get('job_id')}: Trích xuất {cleaned_from_job} finding(s) 'FAIL'."
                )

        return all_cleaned_findings

    # --- (HÀM RUN ĐÃ VIẾT LẠI HOÀN TOÀN) ---
    def run(self, raw_job_results: list) -> list:
        """
        Chạy agent, LÀM SẠCH, sau đó LẶP QUA TỪNG finding
        để phân tích rủi ro.
        """
        print(f"--------------------------------------------------")

        # BƯỚC 1: LÀM SẠCH (Giữ nguyên)
        cleaned_findings = self._parse_and_clean_findings(raw_job_results)
        if not cleaned_findings:
            print("[RiskEvaluationAgent] ⚠️ Không có finding 'FAIL' nào để phân tích.")
            return []

        print(
            f"[RiskEvaluationAgent] 🤖 Đã làm sạch. Bắt đầu phân tích rủi ro cho {len(cleaned_findings)} finding(s) (từng cái một)..."
        )

        enriched_findings_list = []  # List kết quả mới

        # BƯỚC 2: LẶP QUA TỪNG FINDING
        for index, finding in enumerate(cleaned_findings):
            print(
                f"--- [Finding {index + 1}/{len(cleaned_findings)}] Đang xử lý: {finding.get('check_title')[:70]}..."
            )

            try:
                # 1. Chuẩn bị prompt cho MỘT finding
                finding_json_string = json.dumps(finding, indent=2, ensure_ascii=False)

                user_prompt = f"""
                Hãy phân tích finding (JSON) sau đây và trả về 
                MỘT JSON object chứa "severity" và "risk_score".

                {finding_json_string}
                """

                messages = [
                    {"role": "system", "content": self.SYSTEM_PROMPT_SINGLE},
                    {"role": "user", "content": user_prompt},
                ]

                # 2. Gọi LLM (với JSON Mode) cho CHỈ MỘT finding này
                response_message = self.call_llm(
                    messages, response_format={"type": "json_object"}
                )

                if not response_message or not response_message.content:
                    print(f"   -> ❌ Lỗi: AI không trả về phản hồi cho finding này.")
                    finding["severity"] = "N/A"
                    finding["risk_score"] = -1
                    enriched_findings_list.append(finding)
                    continue  # Đi tiếp đến finding tiếp theo

                # 3. Parse kết quả (Mong đợi: {"severity": "High", "risk_score": 8})
                cleaned_json_string = self._extract_json_from_text(
                    response_message.content
                )
                risk_data = json.loads(cleaned_json_string)

                if isinstance(risk_data, dict) and "severity" in risk_data:
                    # 4. GỘP kết quả vào finding gốc
                    finding.update(risk_data)
                    enriched_findings_list.append(finding)
                    print(f"   -> ✅ Thành công: {risk_data}")
                else:
                    print(f"   -> ❌ Lỗi: AI trả về JSON sai cấu trúc: {risk_data}")
                    finding["severity"] = "N/A"
                    finding["risk_score"] = -1
                    enriched_findings_list.append(finding)

            except json.JSONDecodeError:
                print(
                    f"   -> ❌ Lỗi: AI trả về text không phải JSON: {response_message.content[:200]}..."
                )
                finding["severity"] = "N/A"
                finding["risk_score"] = -1
                enriched_findings_list.append(finding)
            except Exception as e:
                print(f"   -> ❌ Lỗi hệ thống khi xử lý finding: {e}")
                finding["severity"] = "N/A"
                finding["risk_score"] = -1
                enriched_findings_list.append(finding)

            # time.sleep(0.5) # Thêm 1 chút delay nếu API bị quá tải

        # Hết vòng lặp

        # BƯỚC 3: SẮP XẾP KẾT QUẢ (THEO YÊU CẦU MỚI)
        print(
            f"[RiskEvaluationAgent] ℹ️ Đã phân tích xong. Đang sắp xếp {len(enriched_findings_list)} finding(s) theo mức độ ưu tiên..."
        )

        # Định nghĩa giá trị cho mỗi mức độ nghiêm trọng để sắp xếp
        # Vì "Critical" > "High", chúng ta cần map chúng thành số
        severity_map = {
            "Critical": 4,
            "High": 3,
            "Medium": 2,
            "Low": 1,
            "N/A": 0,  # Bất cứ thứ gì không map được sẽ coi là 0
        }

        # Sắp xếp danh sách:
        # 1. Ưu tiên theo 'severity' (đã chuyển thành số)
        # 2. Nếu severity bằng nhau, ưu tiên theo 'risk_score'
        # Cả hai đều sắp xếp từ lớn đến bé (reverse=True)
        sorted_enriched_list = sorted(
            enriched_findings_list,
            key=lambda f: (
                severity_map.get(f.get("severity"), 0),  # Lấy giá trị số của severity
                f.get("risk_score", -1),  # Lấy điểm rủi ro
            ),
            reverse=True,  # Sắp xếp từ lớn đến bé
        )

        print(
            f"[RiskEvaluationAgent] ✅ Đã sắp xếp xong. Tổng cộng {len(sorted_enriched_list)} finding(s) đã được làm giàu."
        )
        return sorted_enriched_list
