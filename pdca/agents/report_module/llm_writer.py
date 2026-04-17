# llm_writer.py — Rebuilt (Sprint 3)
# - Inject BaseChatModel (done Sprint 2)
# - _ask() with fallback + _clean() post-processing
# - Output constraints appended to all prompts
import re
import json
import logging
import markdown

from pdca.agents.report_module.llm_validator import FactValidator

logger = logging.getLogger(__name__)
_VALIDATOR = FactValidator()


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

    def __init__(self, llm=None, model="gemma3:4b", api_key=None,
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
        """Post-processing: sanitize, then convert markdown → HTML.

        Small LLMs (gemma3:4b, llama3.2) output markdown by default.
        Since the report template is HTML, we convert here.
        """
        if not text:
            return ""
        # Remove placeholder brackets like [liệt kê các best practice...]
        text = self._PLACEHOLDER.sub('', text)
        # Remove first-person pronouns (Vietnamese variants)
        text = self._FIRST_PERSON.sub('', text)
        # Replace standalone "None" leaked from Python None values
        text = re.sub(r'(?<=["\s])None(?=["\s,.\)])', 'N/A', text)
        # Collapse multiple spaces left by removals
        text = re.sub(r' {2,}', ' ', text)
        # Remove LLM-generated duplicate title (dòng đầu là bold title)
        lines = text.strip().split('\n')
        if len(lines) > 1 and lines[0].strip().startswith('**') and lines[0].strip().endswith('**'):
            lines = lines[1:]
        text = '\n'.join(lines).strip()

        # Force a blank line before bullet/numbered list items when the LLM
        # emits "<paragraph text>\n* item\n* item" without a separator, which
        # causes `markdown` to keep the `*` literal inside the <p> tag.
        text = re.sub(
            r"(?<!\n)\n(?=\s*(?:\*|-)\s+\S)",  # bullet-style lists
            "\n\n",
            text,
        )
        text = re.sub(
            r"(?<!\n)\n(?=\s*\d+\.\s+\S)",  # numbered lists
            "\n\n",
            text,
        )

        # Break enumerated section headings like "1. **Title:** …" into
        # proper <h4>Title</h4> followed by its body. Small LLMs love to mix
        # numbered section lists with bullet sub-lists, which produces broken
        # ol/ul nesting once markdown.markdown() runs. Promoting the title
        # out of the list entirely sidesteps the issue.
        def _promote_numbered_heading(m):
            title = m.group("title").strip().rstrip(":").strip()
            body = m.group("body").strip()
            return f"\n\n#### {title}\n\n{body}"

        text = re.sub(
            r"(?m)^\s*\d+\.\s+\*\*(?P<title>[^\n*]+?)\*\*\s*[:\s]*\n(?P<body>(?:(?!^\s*\d+\.\s+\*\*).)+)",
            _promote_numbered_heading,
            text,
            flags=re.DOTALL,
        )

        # Convert markdown → HTML. `sane_lists` avoids merging consecutive
        # unrelated lists (e.g. "* foo" followed by "1. bar").
        text = markdown.markdown(text, extensions=["tables", "sane_lists"])

        return text

    def _with_constraints(self, prompt: str, word_limit: int = 300) -> str:
        """Append output constraints to prompt."""
        return prompt + _OUTPUT_CONSTRAINTS.format(word_limit=word_limit)

    def _ask_validated(self, prompt: str, allowed_numbers: set,
                       fallback: str,
                       section: str = "unknown") -> str:
        """Call LLM then validate numbers. Fallback if hallucinated numbers."""
        text = self._ask(prompt, fallback=fallback)
        if not text or text == fallback:
            return text
        result = _VALIDATOR.validate(text, allowed_numbers)
        if not result.ok:
            logger.warning(
                "[LLMWriter:%s] Fact validation failed. Offending numbers: %s. "
                "Allowed: %s. Using template fallback.",
                section, result.offending, sorted(allowed_numbers),
            )
            return fallback
        return text

    # ======================================================
    # 1. Executive Summary
    # ======================================================
    def write_exec_summary(self, pre, sysdata, meta, rag_knowledge: str = "",
                           fail_findings: list = None):
        rag_block = f"\n===== KIẾN THỨC CHUYÊN MÔN TỪ CƠ SỞ DỮ LIỆU =====\n{rag_knowledge}\n\nHãy SỬ DỤNG kiến thức trên để viết chính xác hơn — KHÔNG bịa thêm.\n" if rag_knowledge else ""

        account_id = ""
        if isinstance(sysdata, dict):
            account_id = str(sysdata.get("account_id", "")).strip()

        fail_block = ""
        if fail_findings:
            lines = []
            for i, f in enumerate(fail_findings, 1):
                desc = (f.get("description") or "").strip().replace("\n", " ")
                if len(desc) > 140:
                    desc = desc[:137] + "..."
                sev = (f.get("severity") or "N/A").upper()
                res = (f.get("resource") or f.get("resource_id") or "N/A").strip()
                # Account-level checks use account_id in `resource`. Label
                # clearly so the LLM doesn't call the account ID a bucket.
                if res == account_id or res.isdigit():
                    scope_label = "scope: account-level"
                else:
                    scope_label = f"bucket: {res}"
                # Avoid [SEV] brackets — they are stripped by _PLACEHOLDER
                # regex in _clean. Use parens instead.
                lines.append(f"  {i}. ({sev}) {desc} ({scope_label})")
            fail_block = (
                "\n===== DANH SÁCH LỖI CỤ THỂ — BẮT BUỘC TRÍCH DẪN CHÍNH XÁC =====\n"
                + "\n".join(lines)
                + "\n\nKhi nêu 'các nhóm rủi ro chính', CHỈ được nhắc tới các lỗi "
                  "trong danh sách trên. TUYỆT ĐỐI KHÔNG liệt kê các loại lỗi "
                  "không có trong danh sách (ví dụ: KHÔNG nhắc 'Public Access', "
                  "'Encryption', 'Access Control' nếu chúng không xuất hiện).\n"
            )

        prompt = f"""
Bạn là Senior Cloud Security Consultant.
Nhiệm vụ của bạn là viết **Executive Summary** cho báo cáo đánh giá bảo mật Amazon S3 gửi lên C-Level (CTO/CISO).

===== DỮ LIỆU ĐẦU VÀO =====
- Bối cảnh hệ thống: {sysdata}
- Kết quả quét (Pre-remediation): {pre}
- Meta & User Notes: {meta}
{rag_block}
{fail_block}

===== ĐỊNH NGHĨA THUẬT NGỮ (BẮT BUỘC TUÂN THỦ) =====
- "Finding": là kết quả kiểm tra cấu hình (bao gồm cả PASS và FAIL).
- "Lỗi" (Issue / Non-compliant): CHỈ các finding có trạng thái FAIL.
- TUYỆT ĐỐI KHÔNG gọi tổng số findings là tổng số lỗi.
- TUYỆT ĐỐI KHÔNG gọi số findings là số buckets — một bucket có thể có nhiều
  findings. Chỉ dùng `total_buckets` (trong sysdata) làm số buckets.
- Khi trình bày số liệu:
  + Dùng "Tổng số findings" cho toàn bộ kết quả kiểm tra.
  + Dùng "Số lỗi" hoặc "Số finding FAIL" cho các cấu hình không đạt.
  + Dùng "Số buckets" = sysdata.total_buckets.
- Phân bổ severity (critical/high/medium/low) trong `pre` là của TOÀN BỘ findings (PASS+FAIL), KHÔNG phải chỉ của nhóm FAIL.

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
   - Liệt kê các lỗi cụ thể dựa trên DANH SÁCH LỖI CỤ THỂ ở trên.

3. **Kết luận & Định hướng (1 đoạn văn ngắn):**
   - Đánh giá mức độ trưởng thành bảo mật (ví dụ: giai đoạn đầu, cần cải thiện).
   - Đề xuất định hướng chiến lược sát với các lỗi đã liệt kê.

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

        # Deterministic facts the LLM must respect. `total_buckets` already
        # reflects findings-derived count when env.buckets is empty, so this
        # line is always safe to quote.
        tb = sysdata.get("total_buckets", 0) if isinstance(sysdata, dict) else 0
        bucket_facts = (
            f"Số buckets trong phạm vi quét: {tb}."
            if tb > 0 else
            "Không có bucket nào được liệt kê trong phạm vi."
        )

        prompt = f"""
Bạn là Kiến trúc sư Bảo mật (Security Architect). Nhiệm vụ của bạn là viết phần "System Description" (Mô tả hệ thống).

DỮ LIỆU HỆ THỐNG:
{sys_str}

SỰ THẬT BẮT BUỘC (không được phủ nhận hoặc nói ngược lại):
- {bucket_facts}

YÊU CẦU NỘI DUNG:
Viết một đoạn giới thiệu tổng quan (Narrative) kết hợp với các điểm nhấn chiến lược:

1. **Tổng quan (Văn xuôi):**
   - Mô tả vai trò của Amazon S3 trong hệ thống này (Data Lake, Backup, hay lưu trữ tĩnh...).
   - Không lặp lại Account ID/Region một cách máy móc (vì đã có bảng ở trên).
   - KHÔNG được viết câu kiểu "không có bucket được tìm thấy" nếu Số buckets > 0.

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
    def write_post_remediation_recommendations(self, data, rag_knowledge: str = "",
                                                 failing_capabilities: list = None):
        outcome = data.get("remediation_outcome") or {}
        fixed = int(outcome.get("auto_fix_success", 0))
        failed = int(outcome.get("auto_fix_failed", 0))
        manual = int(outcome.get("manual_required", 0))
        post = data.get("post_summary") or {}
        pre_fail = int(post.get("initial_fail", fixed + failed + manual))
        final_fail = int(post.get("final_fail", failed + manual))

        fc_block = ""
        if failing_capabilities:
            fc_lines = "\n".join(f"- {c}" for c in failing_capabilities)
            fc_block = (
                "\n===== DANH SÁCH CAPABILITY / FINDING CÒN YẾU — AUTHORITATIVE =====\n"
                "Đây là nguồn duy nhất để đưa ra khuyến nghị. Không dùng "
                "kiến thức RAG nếu không khớp với danh sách dưới:\n"
                f"{fc_lines}\n\n"
                "RÀNG BUỘC TUYỆT ĐỐI:\n"
                "- CHỈ viết khuyến nghị cho các mục CÓ trong danh sách trên.\n"
                "- TUYỆT ĐỐI KHÔNG nhắc tới 'Block Public Access', 'Data "
                "  Backups', 'Encryption in transit', hay bất kỳ capability "
                "  nào KHÔNG có trong danh sách — kể cả khi RAG đề cập.\n"
                "- Nếu RAG theme không khớp với danh sách, hãy BỎ QUA.\n"
            )

        numeric_block = f"""
===== CÁC SỐ LIỆU CỦA DỮ LIỆU GỐC (chỉ để tham chiếu, KHÔNG trích lại) =====
Số findings FAIL ban đầu: {pre_fail}. Fix tự động thành công: {fixed}.
Fix tự động thất bại: {failed}. Cần thủ công: {manual}. Còn FAIL: {final_fail}.

Một khối bảng số liệu đã được RENDER SẴN ở trên phần prose của bạn — TUYỆT
ĐỐI KHÔNG lặp lại các con số này dưới dạng liệt kê "Số findings X: N".
Chỉ viết prose diễn giải và khuyến nghị chiến lược.

TUYỆT ĐỐI KHÔNG nêu bất kỳ con số nào khác ngoài danh sách trên (ngoại trừ
các con số thứ tự bullet point 1/2/3/4). KHÔNG nói "N vượt qua sau điều chỉnh"
nếu con số đó không có trong danh sách.
"""

        # Expose only the aggregated numbers to the LLM — NOT the whole JSON
        # (the full JSON tempts the LLM to re-dump the literal block).
        rag_block = f"\n===== THỰC HÀNH KHUYẾN NGHỊ TỪ CƠ SỞ DỮ LIỆU =====\n{rag_knowledge}\n\nƯu tiên các khuyến nghị trên khi đưa ra đề xuất chiến lược.\n" if rag_knowledge else ""

        prompt = f"""
Viết nội dung **Khuyến nghị chiến lược** cho báo cáo bảo mật.
Nội dung hướng tới cấp quản lý, dựa hoàn toàn trên dữ liệu sau remediation.

{fc_block}
{numeric_block}
{rag_block}

===== CẤU TRÚC ĐẦU RA (BẮT BUỘC) =====
Viết 3-4 khuyến nghị, mỗi khuyến nghị là một khối độc lập theo cấu trúc:

**<Tiêu đề khuyến nghị ngắn gọn>**
<2-3 câu giải thích cụ thể, nhắc đúng tên finding/capability đang FAIL.>

KHÔNG dùng danh sách đánh số (1. 2. 3.) cho các khuyến nghị.
KHÔNG mở đầu bằng "Số findings FAIL ban đầu: ..." hoặc bất kỳ block liệt kê
số liệu nào — phần đó template đã render riêng.

===== QUY TẮC BẮT BUỘC =====
- KHÔNG dùng ngôi thứ nhất.
- KHÔNG đưa ra khuyến nghị cho vấn đề không tồn tại trong dữ liệu (ví dụ:
  không khuyến nghị "Block Public Access" nếu capability đó đang PASS).
- KHÔNG bịa ra con số ngoài danh sách.
- Management-level, thực tế, gắn với dữ liệu.

===== ĐỊNH HƯỚNG NỘI DUNG =====
- Ưu tiên xử lý {manual} Manual Findings còn tồn đọng (nếu > 0).
- Nếu có {failed} auto-fix thất bại, nêu cần điều tra nguyên nhân.
- Nếu không có Failed, chỉ đề cập duy trì automation hiện có.
- Đề xuất cơ chế giám sát và rà soát định kỳ.

BẮT ĐẦU VIẾT:
"""
        allowed = {float(pre_fail), float(fixed), float(failed), float(manual),
                   float(final_fail)}
        # Tránh regex 0% vô tình reject khi LLM nhắc đến "0"
        allowed.update({0.0})
        return self._ask_validated(
            self._with_constraints(prompt, word_limit=300),
            allowed_numbers=allowed,
            fallback=self._recommendations_fallback(
                fixed=fixed, failed=failed, manual=manual,
                pre_fail=pre_fail, final_fail=final_fail,
            ),
            section="recommendations",
        )

    @staticmethod
    def _recommendations_fallback(*, fixed: int, failed: int, manual: int,
                                   pre_fail: int, final_fail: int) -> str:
        """Template-based recommendations used when LLM output fails validation."""
        parts = [f"<p>Tổng kết khắc phục: {pre_fail} findings FAIL ban đầu, "
                 f"trong đó {fixed} được khắc phục tự động thành công, "
                 f"{failed} auto-fix thất bại, {manual} cần xử lý thủ công. "
                 f"Còn lại {final_fail} findings FAIL sau remediation.</p>"]
        bullets = []
        if manual > 0:
            bullets.append(
                f"<li><strong>Xử lý {manual} Manual Findings:</strong> "
                "gán trách nhiệm cụ thể, đặt deadline và xử lý theo hướng dẫn "
                "trong Section 6.3 của báo cáo.</li>"
            )
        if failed > 0:
            bullets.append(
                f"<li><strong>Điều tra {failed} Auto-fix Thất bại:</strong> "
                "kiểm tra quyền IAM của agent, log lỗi và trạng thái thực tế "
                "của tài nguyên để xác định nguyên nhân gốc.</li>"
            )
        if fixed > 0:
            bullets.append(
                f"<li><strong>Duy trì Automation:</strong> {fixed} khắc phục "
                "tự động đã thành công — tiếp tục theo dõi để tránh drift "
                "cấu hình và mở rộng coverage.</li>"
            )
        bullets.append(
            "<li><strong>Giám sát và Rà soát Định kỳ:</strong> re-scan "
            "hàng tuần/tháng, tích hợp cảnh báo cho các finding mới phát sinh.</li>"
        )
        parts.append("<ul>" + "".join(bullets) + "</ul>")
        return "\n".join(parts)

    # ======================================================
    # 8. Maturity Overview (Phase 4 — NEW)
    # ======================================================
    def write_maturity_overview(self, maturity_data: dict) -> str:
        """Write overall maturity assessment narrative."""
        if not maturity_data:
            return "*Tổng quan mức độ trưởng thành bảo mật không khả dụng.*"

        # Separate strong vs weak domains up front so the LLM cannot call a
        # 34/100 domain a "strength".
        STRONG_THRESHOLD = 70.0
        WEAK_THRESHOLD = 50.0
        strong_domains = []
        weak_domains = []
        for d_id, d_info in maturity_data.get("domains", {}).items():
            caps = d_info.get("capabilities", [])
            if not caps:
                continue
            score = d_info.get("score", 0)
            line = (
                f"- {d_info['display_name']}: {score:.1f}/100, "
                f"stage={d_info.get('stage_label', '')}, "
                f"{len(caps)} capabilities assessed"
            )
            if score >= STRONG_THRESHOLD:
                strong_domains.append(line)
            elif score < WEAK_THRESHOLD:
                weak_domains.append(line)
            else:
                # Mid-range (50 <= score < 70): keep visible as context but
                # do not call it a strength or weakness.
                weak_domains.append(line + "  (trung bình)")

        strong_block = "\n".join(strong_domains) or (
            "(Chưa có domain nào đạt ngưỡng \"Điểm mạnh\" ≥ 70.)"
        )
        weak_block = "\n".join(weak_domains) or (
            "(Không có domain rơi dưới ngưỡng 50.)"
        )

        coverage = maturity_data.get("coverage", {})
        scoped_total = coverage.get("scoped_capabilities") \
            or (coverage.get("assessed", 0) + coverage.get("partial", 0)
                + coverage.get("not_assessed", 0))
        scoped_assessed = coverage.get("assessed", 0) + coverage.get("partial", 0)
        scoped_pct = coverage.get("mapping_coverage_pct", 0.0)
        global_total = coverage.get("total_capabilities", 78)

        prompt = f"""
Bạn là Senior Cloud Security Consultant.
Nhiệm vụ: Viết tổng quan đánh giá mức độ trưởng thành bảo mật.

===== DỮ LIỆU ĐẦU VÀO =====
Overall Score: {maturity_data.get('overall_score', 0)}/100
Overall Stage: {maturity_data.get('overall_stage_label', 'N/A')}

Domains đạt "Điểm mạnh" (score ≥ {STRONG_THRESHOLD:.0f}):
{strong_block}

Domains cần cải thiện (score < {WEAK_THRESHOLD:.0f}) hoặc trung bình:
{weak_block}

Coverage trong phạm vi quét: {scoped_assessed}/{scoped_total} capabilities ({scoped_pct:.1f}%).
Tổng capabilities toàn model (tham khảo): {global_total}.

===== YÊU CẦU CẤU TRÚC =====
Dùng các tiêu đề in đậm riêng biệt (KHÔNG dùng danh sách đánh số 1./2./3.):

**Nhận định tổng thể**
<1 đoạn: Mức trưởng thành hiện tại và ý nghĩa.>

**Điểm mạnh**
<Bullet points — CHỈ liệt kê domains/capabilities có score ≥ {STRONG_THRESHOLD:.0f}.
Nếu danh sách "Domains đạt Điểm mạnh" ở trên là rỗng, ghi đúng nguyên văn:
"Chưa có domain nào đạt ngưỡng Điểm mạnh (≥ {STRONG_THRESHOLD:.0f})." — và dừng mục này.>

**Điểm yếu**
<Bullet points: các domain/capability cần cải thiện.>

**Ghi chú Coverage**
<1-2 câu: dùng đúng tỉ số {scoped_assessed}/{scoped_total} trong phạm vi quét,
KHÔNG viết "{scoped_assessed}/{global_total}" vì sẽ sai ngữ nghĩa.>

===== RÀNG BUỘC =====
- Chỉ dựa trên dữ liệu cung cấp, không suy đoán.
- Không dùng ngôi thứ nhất.
- KHÔNG gọi 1 domain có score < {STRONG_THRESHOLD:.0f} là "Điểm mạnh".

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=350),
            fallback="*Tổng quan mức độ trưởng thành bảo mật không khả dụng.*",
        )

    # ======================================================
    # 9. Domain Assessment (Phase 4 — NEW)
    # ======================================================
    def write_domain_assessment(self, domain_name: str, domain_data: dict) -> str:
        """Write assessment narrative for a single security domain."""
        if not domain_data:
            return f"*Đánh giá lĩnh vực {domain_name} không khả dụng.*"

        caps = domain_data.get("capabilities", [])
        strong = [c for c in caps if c.get("score", 0) >= 70]
        weak = [c for c in caps if c.get("score", 0) < 50]

        strong_lines = "\n".join(
            f"- {c['capability_name']}: {c['score']:.0f}/100" for c in strong
        ) or "(Không có)"
        weak_lines = "\n".join(
            f"- {c['capability_name']}: {c['score']:.0f}/100" for c in weak
        ) or "(Không có)"

        prompt = f"""
Bạn là AWS Security Domain Expert.
Nhiệm vụ: Viết đánh giá cho lĩnh vực "{domain_name}".

===== DỮ LIỆU ĐẦU VÀO =====
Domain Score: {domain_data.get('score', 0):.1f}/100
Domain Stage: {domain_data.get('stage_label', 'N/A')}
Total checks: {domain_data.get('total_checks', 0)}
Passed checks: {domain_data.get('passed_checks', 0)}

Năng lực ĐẠT CHUẨN (score >= 70):
{strong_lines}

Năng lực CẦN CẢI THIỆN (score < 50):
{weak_lines}

===== YÊU CẦU CẤU TRÚC (BẮT BUỘC ĐỊNH DẠNG) =====
Trình bày mỗi mục dưới dạng tiêu đề **in đậm** riêng biệt, KHÔNG dùng danh
sách đánh số (1. 2. 3.). Mỗi tiêu đề trên một dòng, body ở các dòng sau,
và có dòng trống giữa các mục:

**Trạng thái hiện tại**
<2-3 câu>

**Năng lực đạt chuẩn**
- <capability A>: <1 câu>
- <capability B>: <1 câu>

**Năng lực cần cải thiện**
- <capability X>: <hướng khắc phục ngắn>

**Hướng hành động**
<2-3 câu>

===== RÀNG BUỘC =====
- Nhắc tên capability cụ thể, không viết chung chung.
- Không dùng ngôi thứ nhất.
- KHÔNG bắt đầu dòng nào bằng "1." / "2." / "3." / "4." — gây lỗi render HTML.
- Nếu "Năng lực đạt chuẩn" rỗng, ghi "(Không có capability đạt chuẩn trong lĩnh vực này.)".

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=250),
            fallback=f"*Đánh giá lĩnh vực {domain_name} không khả dụng.*",
        )

    # ======================================================
    # 10. Maturity Roadmap (Phase 4 — NEW)
    # ======================================================
    def write_maturity_roadmap(self, maturity_data: dict) -> str:
        """Write improvement roadmap based on maturity gaps."""
        if not maturity_data:
            return "*Lộ trình cải thiện không khả dụng.*"

        # Extract low-scoring capabilities
        low_caps = []
        for d_info in maturity_data.get("domains", {}).values():
            for c in d_info.get("capabilities", []):
                if c.get("score", 0) < 50:
                    low_caps.append(f"- {c['capability_name']} ({d_info['display_name']}): {c['score']:.0f}/100")

        # Domain stages
        stage_lines = []
        for d_info in maturity_data.get("domains", {}).values():
            if d_info.get("capabilities"):
                stage_lines.append(
                    f"- {d_info['display_name']}: {d_info.get('stage_label', 'N/A')}"
                )

        # Unmapped capabilities
        unmapped = maturity_data.get("unmapped_capabilities", [])
        unmapped_count = len(unmapped)
        unmapped_sample = "\n".join(
            f"- {u['capability_name']}" for u in unmapped[:5]
        )

        coverage = maturity_data.get("coverage", {})

        prompt = f"""
Bạn là Security Strategy Advisor.
Nhiệm vụ: Viết lộ trình nâng cấp mức độ trưởng thành bảo mật.

===== DỮ LIỆU ĐẦU VÀO =====
Current stage per domain:
{chr(10).join(stage_lines) if stage_lines else '(Chưa có dữ liệu)'}

Coverage: {coverage.get('assessed', 0) + coverage.get('partial', 0)}/{coverage.get('total_capabilities', 78)} capabilities ({coverage.get('mapping_coverage_pct', 0):.1f}%)

Capabilities điểm thấp (< 50):
{chr(10).join(low_caps[:10]) if low_caps else '(Không có)'}

Capabilities chưa đánh giá: {unmapped_count}
{unmapped_sample if unmapped_sample else ''}

===== YÊU CẦU CẤU TRÚC =====
1. **Ưu tiên trước mắt** (Quick Wins chưa đạt): Capabilities dễ đạt nhất.
2. **Mục tiêu trung hạn** (Foundational): Capabilities cần thiết để nâng stage.
3. **Phạm vi mở rộng**: Domains/capabilities chưa scan cần bổ sung.
4. **Khuyến nghị quy trình**: Tần suất đánh giá, người chịu trách nhiệm.

===== RÀNG BUỘC =====
- Gắn với capability cụ thể, thực tế, không chung chung.
- Không dùng ngôi thứ nhất.

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=350),
            fallback="*Lộ trình cải thiện không khả dụng.*",
        )

    # ======================================================
    # 11. Post-Remediation Analysis V2 (Phase 4 — ENHANCED)
    # ======================================================
    def write_post_remediation_analysis_v2(self, fix_metrics: dict,
                                            residual_risks: dict,
                                            maturity_delta: dict | None,
                                            report_mode: str) -> str:
        """Enhanced post-remediation analysis including maturity delta."""
        if not fix_metrics:
            return "*Phân tích hậu khắc phục không khả dụng.*"

        # Build fix metrics block
        metrics_block = (
            f"Fix rate: {fix_metrics.get('fix_rate_pct', 0):.1f}%\n"
            f"Auto-fix success rate: {fix_metrics.get('auto_success_rate_pct', 0):.1f}%\n"
            f"Pass rate: {fix_metrics.get('pre_pass_rate_pct', 0):.1f}% → "
            f"{fix_metrics.get('post_pass_rate_pct', 0):.1f}% "
            f"(delta: {fix_metrics.get('pass_rate_delta', 0):+.1f}%)\n"
            f"Residual FAIL: {fix_metrics.get('residual_fail', 0)} "
            f"({fix_metrics.get('residual_rate_pct', 0):.1f}%)"
        )

        # Build residual risks block
        residual_block = ""
        if residual_risks:
            sev = residual_risks.get("severity_breakdown", {})
            residual_block = (
                f"Residual risks total: {residual_risks.get('total', 0)}\n"
                f"- Auto-fix failed: {len(residual_risks.get('auto_fix_failed', []))}\n"
                f"- Manual required: {len(residual_risks.get('manual_required', []))}\n"
                f"- Unchanged: {len(residual_risks.get('unchanged', []))}\n"
                f"Severity: Critical={sev.get('critical', 0)}, High={sev.get('high', 0)}, "
                f"Medium={sev.get('medium', 0)}, Low={sev.get('low', 0)}"
            )

        # Build maturity delta block (conditional)
        maturity_block = ""
        if maturity_delta:
            overall = maturity_delta.get("overall", {})
            summary = maturity_delta.get("summary", {})
            stages_unlocked = maturity_delta.get("stages_unlocked", [])
            maturity_block = f"""
Maturity Delta:
- Score: {overall.get('pre_score', 0):.1f} → {overall.get('post_score', 0):.1f} (delta: {overall.get('score_delta', 0):+.1f})
- Stage: {overall.get('stage_label_pre', '')} → {overall.get('stage_label_post', '')}
- Capabilities improved: {summary.get('improved', 0)}, newly passing: {summary.get('newly_passing', 0)}
- Domains nâng stage: {len(stages_unlocked)}
"""

        # Adapt word limit by mode
        word_limit = 200 if report_mode == "focused" else 400

        mode_note = ""
        if report_mode == "focused":
            mode_note = "\nLưu ý: Viết ngắn gọn (~200 từ), chỉ phân tích fix metrics. Không nhắc maturity."
        elif not maturity_delta:
            mode_note = "\nLưu ý: Không có dữ liệu maturity delta — bỏ qua phần tác động maturity."

        prompt = f"""
Bạn là Security Remediation Analyst.
Nhiệm vụ: Viết phân tích hiệu quả khắc phục và tác động lên mức độ trưởng thành.

===== DỮ LIỆU ĐẦU VÀO =====
Fix Metrics:
{metrics_block}

Residual Risks:
{residual_block if residual_block else '(Không có dữ liệu)'}
{maturity_block}
{mode_note}

===== YÊU CẦU CẤU TRÚC =====
1. **Tổng quan hiệu quả** (1 đoạn): Fix rate, auto-fix rate, pass rate delta.
2. **Tác động lên Mức độ Trưởng thành** (chỉ khi có maturity delta):
   - Score thay đổi bao nhiêu điểm
   - Domain nào được nâng stage
   - Bao nhiêu capabilities mới vượt ngưỡng
3. **Rủi ro còn lại** (bullet points): Severity breakdown, manual items.
4. **Nhận định tổng kết** (2-3 câu): Hệ thống đã cải thiện thế nào, còn gì cần xử lý.

===== RÀNG BUỘC =====
- Dựa trên số liệu cụ thể.
- Không dùng ngôi thứ nhất.

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=word_limit),
            fallback="*Phân tích hậu khắc phục không khả dụng.*",
        )

    # ======================================================
    # 12. Action Plan (Phase 4 — NEW)
    # ======================================================
    def write_action_plan(self, residual_risks: dict,
                          maturity_delta: dict | None) -> str:
        """Write concrete action plan with timeline."""
        # Build residual summary
        residual_block = ""
        if residual_risks:
            sev = residual_risks.get("severity_breakdown", {})
            critical_high = sev.get("critical", 0) + sev.get("high", 0)
            medium_low = sev.get("medium", 0) + sev.get("low", 0)
            residual_block = (
                f"Findings chưa fix: {residual_risks.get('total', 0)}\n"
                f"- CRITICAL+HIGH: {critical_high}\n"
                f"- MEDIUM+LOW: {medium_low}\n"
                f"- Manual required: {len(residual_risks.get('manual_required', []))}\n"
                f"- Auto-fix failed: {len(residual_risks.get('auto_fix_failed', []))}"
            )

        # Build maturity context
        maturity_block = ""
        if maturity_delta:
            overall = maturity_delta.get("overall", {})
            coverage_note = ""
            summary = maturity_delta.get("summary", {})
            maturity_block = (
                f"Current score: {overall.get('post_score', 0):.1f}/100\n"
                f"Current stage: {overall.get('stage_label_post', 'N/A')}\n"
                f"Capabilities improved: {summary.get('improved', 0)}\n"
                f"Domains stage up: {summary.get('domains_stage_up', 0)}"
            )

        prompt = f"""
Bạn là Security Program Manager.
Nhiệm vụ: Viết kế hoạch hành động cụ thể sau báo cáo đánh giá bảo mật.

===== DỮ LIỆU ĐẦU VÀO =====
Residual Risks:
{residual_block if residual_block else '(Không còn rủi ro tồn đọng)'}

{'Maturity State:' + chr(10) + maturity_block if maturity_block else ''}

===== YÊU CẦU CẤU TRÚC =====
1. **Hành động NGAY (trong 1 tuần):**
   - Xử lý findings CRITICAL/HIGH chưa fix.
   - Gán người chịu trách nhiệm cho manual findings.
2. **Hành động NGẮN HẠN (trong 1 tháng):**
   - Fix remaining findings MEDIUM/LOW.
   - Mở rộng phạm vi scan nếu coverage thấp.
3. **Hành động DÀI HẠN (quý tiếp theo):**
   - Mục tiêu maturity stage cho từng domain.
   - Tần suất re-scan khuyến nghị.
   - Tích hợp vào quy trình bảo mật (CI/CD, periodic review).
4. **Metrics theo dõi:** KPIs cụ thể để đo lường tiến trình.

===== RÀNG BUỘC =====
- Hành động phải CỤ THỂ và CÓ THỂ THỰC HIỆN ĐƯỢC.
- Không khuyến nghị mua tool/service ngoài scope.
- Gắn timeline tương đối (1 tuần, 1 tháng, 1 quý).
- Không dùng ngôi thứ nhất.

BẮT ĐẦU VIẾT:
"""
        return self._ask(
            self._with_constraints(prompt, word_limit=300),
            fallback="*Kế hoạch hành động không khả dụng.*",
        )
