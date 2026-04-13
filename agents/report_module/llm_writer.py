# llm_writer.py — Rebuilt (Sprint 3)
# - Inject BaseChatModel (done Sprint 2)
# - _ask() with fallback + _clean() post-processing
# - Output constraints appended to all prompts
import re
import json


# Constraint block appended to every LLM prompt
_OUTPUT_CONSTRAINTS = """

===== RÀNG BUỘC OUTPUT (BẮT BUỘC) =====
- KHÔNG vượt quá {word_limit} từ.
- KHÔNG tạo tiêu đề (đã có sẵn trong template).
- KHÔNG dùng ngôi thứ nhất (tôi, chúng tôi).
- KHÔNG dùng placeholder [text ở đây].
- KHÔNG lặp lại cùng 1 ý nhiều lần.
- Nếu data bằng 0 hoặc rỗng, nêu rõ sự thật và ngừng. KHÔNG suy đoán.
- KHÔNG sử dụng emoji hay icon (✅, ❌, 🚩...).
"""


class LLMWriter:

    # Regex patterns for cleaning LLM output
    _PLACEHOLDER = re.compile(r'\[.*?\]')
    # Vietnamese first-person: covers "Chúng tôi", "chúng tôi", "Tôi", "tôi"
    # (case-insensitive flag handles all variants)
    _FIRST_PERSON = re.compile(
        r'[Cc]húng\s+tôi|[Cc]hung\s+toi|[Tt]ôi|[Tt]oi',
        re.IGNORECASE,
    )

    def __init__(self, llm=None, model="llama3.1", api_key=None,
                 base_url=None, temperature=0.3):
        """
        Hỗ trợ 2 cách khởi tạo:
        - LLMWriter(llm=instance)              ← inject (từ ReportAgent mới)
        - LLMWriter(model=..., base_url=...)   ← auto-create (backward compat)

        temperature mặc định 0.3 (deterministic hơn cho report).
        """
        if llm is not None:
            self.llm = llm
        else:
            from langchain_ollama import ChatOllama
            self.llm = ChatOllama(
                model=model, base_url=base_url, temperature=temperature
            )

    # ----------------------------------------------------------
    # CORE: ASK + CLEAN
    # ----------------------------------------------------------
    def _ask(self, prompt: str,
             fallback: str = "*Nội dung không khả dụng.*") -> str:
        """Gọi LLM với error handling + clean output."""
        try:
            res = self.llm.invoke(prompt)
            if res is None or not hasattr(res, "content"):
                print("[LLMWriter] LLM returned None or invalid response")
                return fallback
            text = res.content or ""
            cleaned = self._clean(text)
            return cleaned if cleaned else fallback
        except Exception as e:
            print(f"[LLMWriter] LLM call failed ({type(e).__name__}): {e}")
            return fallback

    def _clean(self, text: str) -> str:
        """Post-processing: remove placeholders, first person, duplicate titles, None."""
        if not text:
            return ""
        # Remove placeholder brackets like [liệt kê các best practice...]
        text = self._PLACEHOLDER.sub('', text)
        # Remove first-person pronouns (Vietnamese variants)
        text = self._FIRST_PERSON.sub('', text)
        # Replace standalone "None" leaked from Python None values
        # Covers: trạng thái "None", công cụ None, giá trị None
        text = re.sub(r'(?<=["\s])None(?=["\s,.\)])', 'N/A', text)
        # Collapse multiple spaces left by removals
        text = re.sub(r' {2,}', ' ', text)
        # Remove LLM-generated duplicate title (dòng đầu là bold title)
        lines = text.strip().split('\n')
        if len(lines) > 1 and lines[0].strip().startswith('**') and lines[0].strip().endswith('**'):
            lines = lines[1:]
        return '\n'.join(lines).strip()

    def _with_constraints(self, prompt: str, word_limit: int = 300) -> str:
        """Append output constraints to prompt."""
        return prompt + _OUTPUT_CONSTRAINTS.format(word_limit=word_limit)

    # ======================================================
    # 1. Executive Summary
    # ======================================================
    def write_exec_summary(self, pre, sysdata, meta, rag_knowledge: str = ""):
        rag_block = f"\n===== KIẾN THỨC CHUYÊN MÔN TỪ CƠ SỞ DỮ LIỆU =====\n{rag_knowledge}\n\nHãy SỬ DỤNG kiến thức trên để viết chính xác hơn — KHÔNG bịa thêm.\n" if rag_knowledge else ""
        prompt = f"""
Bạn là Senior Cloud Security Consultant.
Nhiệm vụ của bạn là viết **Executive Summary** cho báo cáo đánh giá bảo mật Amazon S3 gửi lên C-Level (CTO/CISO).

===== DỮ LIỆU ĐẦU VÀO =====
- Bối cảnh hệ thống: {sysdata}
- Kết quả quét (Pre-remediation): {pre}
- Meta & User Notes: {meta}
{rag_block}

===== ĐỊNH NGHĨA THUẬT NGỮ (BẮT BUỘC TUÂN THỦ) =====
- "Finding": là kết quả kiểm tra cấu hình (bao gồm cả PASS và FAIL).
- "Lỗi" (Issue / Non-compliant): CHỈ các finding có trạng thái FAIL.
- TUYỆT ĐỐI KHÔNG gọi tổng số findings là tổng số lỗi.
- Khi trình bày số liệu:
  + Dùng "Tổng số findings" cho toàn bộ kết quả kiểm tra.
  + Dùng "Số lỗi" hoặc "Số finding FAIL" cho các cấu hình không đạt.

===== HARD CONSTRAINTS =====
- KHÔNG tạo tiêu đề báo cáo (ví dụ: "Báo Cáo Bảo Mật Amazon S3").
- KHÔNG lặp lại tên báo cáo hoặc tên dịch vụ ở dạng tiêu đề.
- Chỉ viết nội dung, bắt đầu trực tiếp từ phần "Bối cảnh & Mục tiêu".
- KHÔNG suy diễn số liệu ngoài dữ liệu được cung cấp.

===== YÊU CẦU CẤU TRÚC =====
Hãy trình bày ngắn gọn, súc tích, sử dụng kết hợp văn xuôi và gạch đầu dòng.

1. **Bối cảnh & Mục tiêu (1 đoạn văn ngắn):**
   - Xác nhận hoàn tất đánh giá bảo mật trên tài khoản/region nào.
   - Nêu đúng quy mô tài nguyên (ví dụ: số lượng bucket nếu có trong dữ liệu).

2. **Tóm tắt Hiện trạng An ninh (Bullet Points):**
   - Nêu số lượng findings và số lỗi (FAIL findings) một cách chính xác.
   - Nhấn mạnh các nhóm rủi ro chính (mất dữ liệu, truy cập công khai...).

3. **Kết luận & Định hướng (1 đoạn văn ngắn):**
   - Đánh giá mức độ trưởng thành bảo mật (ví dụ: giai đoạn đầu, cần cải thiện).
   - Đề xuất định hướng chiến lược (Encryption, Access Control, Governance).

===== GIỌNG VĂN =====
- Chuyên nghiệp, khách quan, mang tính tư vấn chiến lược.
- Không viết lan man, không dùng từ mơ hồ.

BẮT ĐẦU VIẾT EXECUTIVE SUMMARY:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=400),
            fallback="*Executive summary không khả dụng.*",
        )

    # ======================================================
    # 2. System Overview
    # ======================================================
    def write_system_overview(self, sysdata):
        sys_str = (
            json.dumps(sysdata, indent=2, ensure_ascii=False)
            if isinstance(sysdata, dict)
            else str(sysdata)
        )

        prompt = f"""
Bạn là Kiến trúc sư Bảo mật (Security Architect). Nhiệm vụ của bạn là viết phần "System Description" (Mô tả hệ thống).

DỮ LIỆU HỆ THỐNG:
{sys_str}

YÊU CẦU NỘI DUNG:
Viết một đoạn giới thiệu tổng quan (Narrative) kết hợp với các điểm nhấn chiến lược:

1. **Tổng quan (Văn xuôi):**
   - Mô tả vai trò của Amazon S3 trong hệ thống này (Data Lake, Backup, hay lưu trữ tĩnh...).
   - Không lặp lại Account ID/Region một cách máy móc (vì đã có bảng ở trên).

2. **Chiến lược đánh giá (Bullet Points):**
   - Sử dụng gạch đầu dòng để liệt kê các trọng tâm đánh giá (ví dụ: Access Control, Encryption, Resilience).
   - Khẳng định mục tiêu tuân thủ (AWS Well-Architected Framework).

LƯU Ý:
- Không dùng các từ như "Đoạn 1", "Mục 2".
- Giữ văn phong trang trọng.

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=250),
            fallback="*Mô tả hệ thống không khả dụng.*",
        )

    # ======================================================
    # 2.2 Assessment Goals
    # ======================================================
    def write_assessment_goals(self, user_input):
        prompt = f"""
Bạn là Chuyên gia Kiểm toán Bảo mật (Security Auditor). Nhiệm vụ của bạn là viết mục **Assessment Goals** cho báo cáo đánh giá cấu hình AWS (Configuration Review).

INPUT TỪ NGƯỜI DÙNG:
"{user_input}"

QUY TẮC AN TOÀN (BẮT BUỘC):
1. **Phạm vi:** Chỉ tập trung vào Bảo mật (Security), Tuân thủ (Compliance) và Cấu hình (Configuration).
2. **Cấm kỵ:**
   - TUYỆT ĐỐI KHÔNG nhắc đến "Hiệu suất" (Performance), "Độ trễ" (Latency), "Tốc độ tải" (Throughput) -> Tool này không đo hiệu năng.
   - TUYỆT ĐỐI KHÔNG nhắc đến "Khả năng ứng phó tấn công" hay "Penetration Testing" -> Tool này chỉ quét tĩnh (Static Scan), không tấn công thật.
3. **Trung thực:** Nếu user input yêu cầu kiểm tra hiệu năng, hãy tự động lái sang "Kiểm tra cấu hình ảnh hưởng đến tính sẵn sàng (Availability)" thay vì đo độ trễ.

CẤU TRÚC BÁO CÁO:
1. **Mục đích tổng quát (1-2 câu):** Nêu rõ mục tiêu là rà soát tư thế bảo mật (Security Posture) và giảm thiểu rủi ro sai cấu hình.
2. **Mục tiêu cụ thể (3-5 gạch đầu dòng):**
   - Tập trung vào: Kiểm soát truy cập (Access Control), Mã hóa dữ liệu (Encryption), Logging & Monitoring, và Tuân thủ Best Practices (CIS/Well-Architected).

VĂN PHONG:
- Chuyên nghiệp, khách quan.
- Dùng thuật ngữ chính xác (Misconfiguration, Compliance, Data Integrity).

BẮT ĐẦU VIẾT NỘI DUNG (KHÔNG THÊM LỜI DẪN):
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=200),
            fallback="*Mục tiêu đánh giá không khả dụng.*",
        )

    # ======================================================
    # 3. Pre-Remediation Findings
    # ======================================================
    def write_pass_findings_overview(self, ctx, rag_knowledge: str = ""):
        rag_block = f"\n===== KIẾN THỨC BẢO MẬT TỪ CƠ SỞ DỮ LIỆU =====\n{rag_knowledge}\n\nSử dụng kiến thức trên để giải thích ý nghĩa bảo mật chính xác hơn.\n" if rag_knowledge else ""
        prompt = f"""
Bạn là chuyên gia AWS Security. Viết phần **PASS FINDINGS OVERVIEW**,
chỉ dựa trên dữ liệu PASS bên dưới.

===== TỔNG QUAN (SUMMARY) =====
- Tổng PASS: {ctx["total"]}
- PASS theo mức độ severity: {ctx["by_severity"]}
- PASS theo event_code: {ctx["by_event_code"]}

===== DANH SÁCH PASS (ITEMS) =====
{ctx["items"]}
{rag_block}

YÊU CẦU:
1. Tóm tắt tổng quan các mục PASS:
   - Số lượng PASS (không cần ghi số tuyệt đối nếu bạn không chắc).
   - Xu hướng chung của các cấu hình đúng.
2. Giải thích ý nghĩa bảo mật:
   - Vì sao các mục này được xem là cấu hình tốt?
   - Các thực hành tốt (best practices) mà hệ thống đã tuân thủ.
3. Nêu tác động tích cực:
   - Điều này phản ánh điều gì về posture bảo mật?
   - Tác dụng đối với compliance / risk mitigation.
4. KHÔNG được mô tả từng finding riêng lẻ.
5. KHÔNG được bịa số liệu ngoài dữ liệu đầu vào.
6. Viết 1–2 đoạn văn ngắn gọn, rõ ràng.

KHÔNG được mô tả FAIL findings, không nhắc đến remediation.
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=200),
            fallback="*Phân tích PASS không khả dụng.*",
        )

    def write_fail_findings_overview(self, ctx, rag_knowledge: str = ""):
        rag_block = f"\n===== KIẾN THỨC BẢO MẬT TỪ CƠ SỞ DỮ LIỆU =====\n{rag_knowledge}\n\nSử dụng kiến thức trên để phân tích rủi ro chính xác hơn.\n" if rag_knowledge else ""
        prompt = f"""
Bạn là chuyên gia AWS Security. Viết phần **FAIL FINDINGS OVERVIEW**,
chỉ dựa trên dữ liệu FAIL bên dưới.

===== TỔNG QUAN (SUMMARY) =====
- Tổng FAIL: {ctx["total"]}
- FAIL theo mức độ severity: {ctx["by_severity"]}
- FAIL theo event_code: {ctx["by_event_code"]}
{rag_block}

===== DANH SÁCH FAIL (ITEMS) =====
{ctx["items"]}

YÊU CẦU:
1. Tóm tắt tổng quan các mục FAIL:
   - Những nhóm cấu hình nào đang thiếu sót?
   - Xu hướng sai cấu hình phổ biến.
2. Phân tích rủi ro cấp cao:
   - Các tác động tiềm tàng (mất dữ liệu, lộ dữ liệu, vi phạm truy cập…).
   - Vì sao các finding này quan trọng?
3. Đánh giá posture ban đầu:
   - Hệ thống đang ở mức độ trưởng thành bảo mật nào?
4. KHÔNG phân tích từng finding cụ thể.
5. KHÔNG mô tả bài học khắc phục hoặc remediation task.
6. Viết 1–2 đoạn văn rõ ràng, có trọng tâm.

Chỉ viết nội dung dựa trên FAIL findings phía trên.
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=200),
            fallback="*Phân tích FAIL không khả dụng.*",
        )

    # ======================================================
    # 5. Remediation Detail
    # ======================================================
    def write_pass_remediation_detail(
        self, action, resource, before, after, tool_code, tool_description,
        rag_risk: str = "",
    ):
        rag_block = f"\nMô tả rủi ro chính thức (từ cơ sở dữ liệu Prowler):\n{rag_risk}\n" if rag_risk else ""
        prompt = f"""
Bạn là Chuyên gia Kỹ thuật Bảo mật (Technical Security Writer).

Nhiệm vụ:
Viết báo cáo chi tiết cho một hành động khắc phục tự động (Auto-remediation)
đã được thực hiện thành công và được xác nhận bằng dữ liệu hậu kiểm.

===== DỮ LIỆU ĐẦU VÀO (CHỈ ĐƯỢC DÙNG PHẦN NÀY) =====
Hành động: {action}
Tài nguyên: {resource}
{rag_block}
Trạng thái trước (Before):
{before}

Trạng thái sau (After):
{after}

Mô tả kỹ thuật của công cụ (đã được chuẩn hóa):
{tool_description}

Source code của công cụ (tool_code):
{tool_code}

===== NGUYÊN TẮC BẮT BUỘC =====
- ĐƯỢC phép phân tích source code của công cụ nếu được cung cấp, nhằm mô tả chính xác hành vi kỹ thuật và logic thực thi.
- Chỉ sử dụng thông tin có thể suy ra trực tiếp từ:
  + Trạng thái before / after
  + execution_output (nếu có)
  + tool_description
  + tool_code (nếu có)

- Source code của công cụ (tool_code) chỉ được sử dụng cho mục đích PHÂN TÍCH và SUY LUẬN kỹ thuật.
- TUYỆT ĐỐI KHÔNG:
  + Trích dẫn lại source code
  + Viết lại logic dưới dạng code
  + Sao chép cấu trúc hàm, tên hàm, biến hoặc đoạn mã vào báo cáo
- Nội dung báo cáo phải được trình bày hoàn toàn bằng ngôn ngữ mô tả kỹ thuật.

YÊU CẦU NỘI DUNG:
Viết một bản tường trình kỹ thuật rõ ràng, chia làm 3 phần (sử dụng gạch đầu dòng "-"):

1. **Phân tích Vấn đề & Rủi ro:**
   - Dựa vào trạng thái `Before`, giải thích ngắn gọn tại sao tài nguyên không đạt chuẩn.
   - Nêu rủi ro an ninh thực tế nếu không khắc phục.

2. **Chi tiết Kỹ thuật Thực thi (DỰA TRÊN DỮ LIỆU THẬT):**
   - Phân tích hành vi kỹ thuật của remediation dựa trên tool_description và source code.
   - Công cụ tác động vào thành phần kỹ thuật nào. Các thay đổi cấu hình đã thực hiện.

3. **Xác nhận Kết quả:**
   - Tóm tắt trạng thái `After` dựa trên dữ liệu thật.
   - Mô tả lợi ích bảo mật khi trạng thái chuyển sang PASS.

YÊU CẦU VĂN PHONG:
- Chuyên nghiệp, khách quan, đậm chất kỹ thuật.
- Sử dụng thuật ngữ chính xác (Boto3 API, JSON Policy, Config Rule).

BẮT ĐẦU VIẾT (CHỈ TRẢ VỀ NỘI DUNG VĂN BẢN):
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=350),
            fallback="*Phân tích kỹ thuật không khả dụng.*",
        )

    def write_fail_remediation_detail(
        self,
        action,
        resource,
        before,
        after,
        execution_status,
        execution_output,
        execution_error,
        execution_timing,
        tool_code,
        tool_description,
        rag_risk: str = "",
    ):
        rag_block = f"\nMô tả rủi ro chính thức (từ cơ sở dữ liệu Prowler):\n{rag_risk}\n" if rag_risk else ""
        prompt = f"""
Bạn là Kỹ sư Vận hành Hệ thống (System Operations Engineer) đang thực hiện phân tích nguyên nhân gốc rễ (Root Cause Analysis - RCA) cho một tác vụ tự động hóa bị lỗi.

DỮ LIỆU SỰ CỐ:
- Hành động: {action}
- Tài nguyên: {resource}
{rag_block}
- Trạng thái trước (Before): {before}
- Trạng thái sau (After): {after}
- Lỗi ghi nhận (Error Log): {execution_error}
- Output thực thi: {execution_output}

LOGIC CÔNG CỤ (SOURCE CODE):
```python
{tool_code}
```

YÊU CẦU NỘI DUNG:
Viết báo cáo điều tra sự cố kỹ thuật, chia thành 4 phần chính (sử dụng gạch đầu dòng "-"):

1. **Ngữ cảnh & Vấn đề:**
   - Tóm tắt ngắn gọn cấu hình sai ban đầu (dựa trên `Before`).
   - Mục tiêu mà tool định thực hiện là gì?

2. **Quy trình Tool thực thi (Theo Code):**
   - Đọc `SOURCE CODE` và mô tả các bước tool đã cố gắng thực hiện.
   - Chỉ rõ tool đã dừng lại hoặc gặp lỗi ở đoạn nào.

3. **Phân tích Nguyên nhân Thất bại (Root Cause):**
   - Phân tích nội dung `Error Log` để giải thích tại sao thất bại.
   - Phân loại lỗi: Access Denied? Not Found? Conflict?
   - Đừng chỉ copy log, hãy "dịch" log sang ngôn ngữ người đọc hiểu.

4. **Khuyến nghị Khắc phục (Next Steps):**
   - Đề xuất hành động cụ thể cho người quản trị.

YÊU CẦU VĂN PHONG:
- Khách quan, tập trung vào kỹ thuật.
- Không đổ lỗi chung chung, phải chỉ ra nguyên nhân cụ thể từ log.

BẮT ĐẦU VIẾT BÁO CÁO SỰ CỐ:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=350),
            fallback="*Phân tích lỗi không khả dụng.*",
        )

    # ======================================================
    # 5.3 Manual Guide
    # ======================================================
    def write_manual_guide(self, manual, rag_context: dict = None):
        rag_block = ""
        if rag_context:
            risk = rag_context.get("risk_summary", "")
            title = rag_context.get("title", "")
            if risk or title:
                rag_block = f"""
===== KIẾN THỨC TỪ CƠ SỞ DỮ LIỆU PROWLER =====
Tiêu đề check: {title}
Mô tả rủi ro: {risk}

Sử dụng thông tin trên để viết hướng dẫn chính xác hơn.
"""

        prompt = f"""
Bạn là chuyên gia AWS Security, đang viết **hướng dẫn xử lý thủ công (Manual Remediation Runbook)**
cho một finding không thể khắc phục tự động.
{rag_block}
===== DỮ LIỆU ĐẦU VÀO (CHỈ ĐƯỢC DÙNG PHẦN NÀY) =====
FINDING DESCRIPTION:
{manual.get("description")}

RESOURCE:
{manual.get("resource")}

SEVERITY:
{manual.get("severity")}

MANUAL REASON:
{manual.get("manual_reason")}

REMAINING MANUAL ACTIONS:
{manual.get("remaining_actions")}

===== ĐỊNH NGHĨA & NGUYÊN TẮC (BẮT BUỘC TUÂN THỦ) =====
- Manual remediation = **Con người ra quyết định và thực hiện**.
- KHÔNG có khái niệm tool execution trong manual remediation.

HARD CONSTRAINTS:
1. KHÔNG nhắc đến: Tên tool, Tool description, Source code, API, boto3, SDK, CLI
2. KHÔNG nói rằng finding đã được khắc phục.
3. KHÔNG đề cập trạng thái PASS / FAIL sau remediation.
4. KHÔNG suy đoán chi tiết kỹ thuật ngoài dữ liệu được cung cấp.
5. Nếu dữ liệu không đủ chi tiết, hãy nói rõ rằng cần quyết định từ người vận hành.

===== CẤU TRÚC BẮT BUỘC =====
1. **Vấn đề gốc** — bản chất finding và lý do cần xử lý thủ công.
2. **Vì sao cần xử lý thủ công** — giới hạn kỹ thuật, yêu cầu nghiệp vụ, quyền cao.
3. **Hướng xử lý thủ công đề xuất** — checklist hành động.
4. **Lưu ý khi thực hiện** — ảnh hưởng, yêu cầu phê duyệt.
5. **Kết luận** — vai trò con người, không nên tự động hóa.

BẮT ĐẦU VIẾT MANUAL REMEDIATION RUNBOOK:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=300),
            fallback="*Hướng dẫn thủ công không khả dụng.*",
        )

    # ======================================================
    # 6.3 Post-Remediation Analysis
    # ======================================================
    def write_post_remediation_analysis(self, data):
        data_str = json.dumps(data, indent=2, ensure_ascii=False)

        prompt = f"""
Viết nội dung **Đánh giá của chuyên gia** cho báo cáo bảo mật.
Nội dung là một phần chính thức của báo cáo, không phải lời thoại.

===== DỮ LIỆU SỬ DỤNG =====
{data_str}

===== QUY TẮC BẮT BUỘC =====
1. KHÔNG dùng ngôi thứ nhất (tôi, chúng tôi).
2. KHÔNG có câu meta như "tôi có thể giúp".
3. KHÔNG tạo tiêu đề mới hoặc markdown heading.
4. Viết theo văn phong báo cáo kỹ thuật.

===== YÊU CẦU ĐỘ DÀI =====
- Mỗi mục viết **2–3 câu ngắn**.
- Không viết một câu quá dài.

===== NỘI DUNG CẦN VIẾT =====

Tổng quan thay đổi:
- Nhận định rõ ràng về sự thay đổi tư thế bảo mật sau remediation.
- Nêu mức giảm lỗi từ `initial_fail` xuống `final_fail` và ý nghĩa.

Phân tích chi tiết:
- Đã khắc phục (Fixed): số lượng lỗi đã xử lý và tác động.
- Cần xử lý thủ công (Manual): bản chất các vấn đề tồn đọng.
- Khắc phục thất bại (Failed): nếu 0, ghi rõ automation ổn định.

Kết luận và hướng tiếp theo:
- Mức độ rủi ro đã kiểm soát đến đâu.
- Trọng tâm tiếp theo: xử lý Manual hay duy trì.

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=300),
            fallback="*Đánh giá hậu kiểm không khả dụng.*",
        )

    # ======================================================
    # 7. Recommendations
    # ======================================================
    def write_post_remediation_recommendations(self, data, rag_knowledge: str = ""):
        data_str = json.dumps(data, indent=2, ensure_ascii=False)
        rag_block = f"\n===== THỰC HÀNH KHUYẾN NGHỊ TỪ CƠ SỞ DỮ LIỆU =====\n{rag_knowledge}\n\nƯu tiên các khuyến nghị trên khi đưa ra đề xuất chiến lược.\n" if rag_knowledge else ""

        prompt = f"""
Viết nội dung **Khuyến nghị chiến lược** cho báo cáo bảo mật.
Nội dung hướng tới cấp quản lý, dựa hoàn toàn trên dữ liệu sau remediation.

===== DỮ LIỆU SỬ DỤNG =====
{data_str}
{rag_block}

===== QUY TẮC BẮT BUỘC =====
1. KHÔNG dùng ngôi thứ nhất.
2. KHÔNG đưa ra khuyến nghị cho vấn đề không tồn tại trong dữ liệu.
3. Không dùng ngôn ngữ sáo rỗng hoặc chung chung.

===== YÊU CẦU ĐỘ DÀI =====
- Mỗi khuyến nghị gồm:
  * Tiêu đề ngắn
  * **2–3 câu giải thích cụ thể**

===== ĐỊNH HƯỚNG NỘI DUNG =====
- Ưu tiên xử lý các Manual Findings còn tồn đọng.
- Nếu không có Failed, chỉ đề cập duy trì automation hiện có.
- Đề xuất cơ chế giám sát và rà soát định kỳ.

===== VĂN PHONG =====
- Management-level, thực tế, gắn với dữ liệu.

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=300),
            fallback="*Khuyến nghị không khả dụng.*",
        )
