# llm_writer.py
import json
from openai import OpenAI
from langchain_ollama import ChatOllama


class LLMWriter:

    def __init__(self, model="llama3.1", api_key=None, base_url=None):
        # Dùng đúng client tương thích Ollama
        self.llm = ChatOllama(model=model, base_url=base_url, temperature=0)

    def _ask(self, prompt: str):
        res = self.llm.invoke(prompt)
        return res.content

    # ======================================================

    # 1. Executive Summary - REVISED FOR READABILITY
    def write_exec_summary(self, pre, sysdata, meta):
        prompt = f"""
Bạn là Senior Cloud Security Consultant. 
Nhiệm vụ của bạn là viết **Executive Summary** cho báo cáo đánh giá bảo mật Amazon S3 gửi lên C-Level (CTO/CISO).

===== DỮ LIỆU ĐẦU VÀO =====
- Bối cảnh hệ thống: {sysdata}
- Kết quả quét (Pre-remediation): {pre}
- Meta & User Notes: {meta}

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
        return self._ask(prompt)

    # ======================================================

    # 2. Assessment Goals
    # 2.1 System Overview - REVISED
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
        return self._ask(prompt)

    # 2.2 Assessment Goals
    # 2. Assessment Goals - REVISED
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
        return self._ask(prompt)

    # 3. Pre-Remediation Findings Overview

    # 3.1 PASS Findings Overview

    def write_pass_findings_overview(self, ctx):
        """
        ctx = {
            "total": int,
            "by_severity": {...},
            "by_event_code": {...},
            "items": [list of simplified findings]
        }
        """
        prompt = f"""
    Bạn là chuyên gia AWS Security. Viết phần **PASS FINDINGS OVERVIEW**,
    chỉ dựa trên dữ liệu PASS bên dưới.

    ===== TỔNG QUAN (SUMMARY) =====
    - Tổng PASS: {ctx["total"]}
    - PASS theo mức độ severity: {ctx["by_severity"]}
    - PASS theo event_code: {ctx["by_event_code"]}

    ===== DANH SÁCH PASS (ITEMS) =====
    {ctx["items"]}

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
        return self._ask(prompt)

    def write_fail_findings_overview(self, ctx):
        """
        ctx = {
            "total": int,
            "by_severity": {...},
            "by_event_code": {...},
            "items": [list of simplified findings]
        }
        """
        prompt = f"""
Bạn là chuyên gia AWS Security. Viết phần **FAIL FINDINGS OVERVIEW**, 
chỉ dựa trên dữ liệu FAIL bên dưới.

===== TỔNG QUAN (SUMMARY) =====
- Tổng FAIL: {ctx["total"]}
- FAIL theo mức độ severity: {ctx["by_severity"]}
- FAIL theo event_code: {ctx["by_event_code"]}

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
        return self._ask(prompt)

    def write_pass_remediation_detail(
        self, action, resource, before, after, tool_code, tool_description
    ):
        prompt = f"""
Bạn là Chuyên gia Kỹ thuật Bảo mật (Technical Security Writer).

Nhiệm vụ:
Viết báo cáo chi tiết cho một hành động khắc phục tự động (Auto-remediation)
đã được thực hiện thành công và được xác nhận bằng dữ liệu hậu kiểm.

===== DỮ LIỆU ĐẦU VÀO (CHỈ ĐƯỢC DÙNG PHẦN NÀY) =====
Hành động: {action}
Tài nguyên: {resource}

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
- Nội dung báo cáo phải được trình bày hoàn toàn bằng ngôn ngữ mô tả kỹ thuật,
  tập trung vào hành vi, tác động cấu hình và kết quả bảo mật.

YÊU CẦU NỘI DUNG:
Hãy viết một bản tường trình kỹ thuật rõ ràng, chia làm 3 phần (sử dụng gạch đầu dòng "-" để liệt kê):

1. **Phân tích Vấn đề & Rủi ro:**
   - Dựa vào trạng thái `Before`, giải thích ngắn gọn tại sao tài nguyên này không đạt chuẩn (Non-compliant).
   - Nêu rủi ro an ninh thực tế nếu không khắc phục (ví dụ: dữ liệu bị lộ, thiếu tính toàn vẹn...).

2. **Chi tiết Kỹ thuật Thực thi (DỰA TRÊN DỮ LIỆU THẬT):**
   - Phân tích và mô tả chi tiết hành vi kỹ thuật của remediation dựa trên tool_description và source code của công cụ (nếu được cung cấp).
   - Làm rõ:
   + Công cụ tác động vào thành phần kỹ thuật nào của tài nguyên.
   + Các thay đổi cấu hình hoặc hành động kỹ thuật đã được thực hiện.
   + Cơ chế bảo mật, dịch vụ hoặc API liên quan theo đúng logic triển khai.
   - Cho phép mô tả logic triển khai và luồng thực thi nội bộ,
   miễn là nội dung chỉ dựa trên dữ liệu thực tế đã cung cấp.


3. **Xác nhận Kết quả:**
   - Tóm tắt trạng thái `After` dựa trên dữ liệu thật.
   - Mô tả lợi ích bảo mật khi trạng thái chuyển sang PASS.
   - Kết luận remediation dựa trên execution_output, AFTER, và logic tool.

YÊU CẦU VĂN PHONG:
- Chuyên nghiệp, khách quan, đậm chất kỹ thuật (Technical tone).
- Sử dụng thuật ngữ chính xác (Boto3 API, JSON Policy, Config Rule).
- **TUYỆT ĐỐI KHÔNG** sử dụng bất kỳ icon hay emoji nào (như ✅, ❌, 🚩). Chỉ dùng ký tự text thuần túy.
- Trình bày mạch lạc, không lặp từ.

BẮT ĐẦU VIẾT (CHỈ TRẢ VỀ NỘI DUNG VĂN BẢN):
"""
        return self._ask(prompt)

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
    ):
        prompt = f"""
Bạn là Kỹ sư Vận hành Hệ thống (System Operations Engineer) đang thực hiện phân tích nguyên nhân gốc rễ (Root Cause Analysis - RCA) cho một tác vụ tự động hóa bị lỗi.

DỮ LIỆU SỰ CỐ:
- Hành động: {action}
- Tài nguyên: {resource}
- Trạng thái trước (Before): {before}
- Trạng thái sau (After): {after}
- Lỗi ghi nhận (Error Log): {execution_error}
- Output thực thi: {execution_output}

LOGIC CÔNG CỤ (SOURCE CODE):
```python
{tool_code}
```

YÊU CẦU NỘI DUNG:
Hãy viết báo cáo điều tra sự cố kỹ thuật, chia thành 4 phần chính (sử dụng gạch đầu dòng "-" để trình bày):

1. **Ngữ cảnh & Vấn đề:**
   - Tóm tắt ngắn gọn cấu hình sai ban đầu (dựa trên `Before`).
   - Mục tiêu mà tool định thực hiện là gì?

2. **Quy trình Tool thực thi (Theo Code):**
   - Đọc `SOURCE CODE` và mô tả các bước tool đã cố gắng thực hiện.
   - Chỉ rõ tool đã dừng lại hoặc gặp lỗi ở đoạn nào (dựa trên logic code và error log).
   - Ví dụ: "Tool đã khởi tạo client thành công nhưng gặp lỗi khi gọi API `put_bucket_versioning`".

3. **Phân tích Nguyên nhân Thất bại (Root Cause):**
   - Đây là phần quan trọng nhất. Hãy phân tích nội dung `Error Log` để giải thích tại sao thất bại.
   - Phân loại lỗi: Do thiếu quyền (Access Denied)? Do tài nguyên không tồn tại (Not Found)? Hay do xung đột cấu hình (Conflict)?
   - Chỉ phân tích những đoạn logic trong source code có liên quan trực tiếp tới lỗi được ghi nhận trong Error Log.
   - Không mô tả toàn bộ luồng xử lý nếu không cần thiết cho việc xác định nguyên nhân.
   - Đừng chỉ copy log, hãy "dịch" log sang ngôn ngữ người đọc hiểu.

4. **Khuyến nghị Khắc phục (Next Steps):**
   - Dựa trên nguyên nhân lỗi, đề xuất hành động cụ thể cho người quản trị.
   - Ví dụ: "Cần cấp thêm quyền `s3:PutBucketVersioning` cho IAM Role thực thi" hoặc "Cần kiểm tra lại SCP policy đang chặn".

YÊU CẦU VĂN PHONG:
- Khách quan, tập trung vào kỹ thuật.
- Không đổ lỗi chung chung ("tool bị lỗi"), phải chỉ ra nguyên nhân cụ thể từ log.
- **TUYỆT ĐỐI KHÔNG** sử dụng icon hay emoji.
- Trình bày rõ ràng, dễ theo dõi.

BẮT ĐẦU VIẾT BÁO CÁO SỰ CỐ:
"""
        return self._ask(prompt)

    def write_manual_guide(self, manual):
        prompt = f"""
Bạn là chuyên gia AWS Security, đang viết **hướng dẫn xử lý thủ công (Manual Remediation Runbook)**
cho một finding không thể khắc phục tự động.

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

HARD CONSTRAINTS (CỰC KỲ QUAN TRỌNG):
1. KHÔNG nhắc đến:
   - Tên tool
   - Tool description
   - Source code
   - API, boto3, SDK, CLI
2. KHÔNG nói rằng finding đã được khắc phục.
3. KHÔNG đề cập trạng thái PASS / FAIL sau remediation.
4. KHÔNG suy đoán chi tiết kỹ thuật ngoài dữ liệu được cung cấp.
5. Nếu dữ liệu không đủ chi tiết, hãy nói rõ rằng cần quyết định từ người vận hành.

===== YÊU CẦU VĂN PHONG =====
- Rõ ràng, ngắn gọn, định hướng vận hành.
- Tránh văn phong báo cáo học thuật dài dòng.
- Viết như **runbook cho người vận hành**, không phải bài phân tích.

===== CẤU TRÚC BẮT BUỘC =====
Chỉ viết theo đúng các mục sau (KHÔNG thêm mục mới):

1. **Vấn đề gốc**
   - Mô tả ngắn gọn bản chất của finding.
   - Giải thích vì sao finding này được đánh dấu cần xử lý thủ công.

2. **Vì sao cần xử lý thủ công**
   - Giải thích lý do hệ thống không thể tự động xử lý finding này,
     do giới hạn kỹ thuật, yêu cầu nghiệp vụ, quyền truy cập cao,
     hoặc rủi ro vận hành nếu tự động hóa.

3. **Hướng xử lý thủ công đề xuất**
   - Trình bày các hành động mà người vận hành cần thực hiện tiếp theo.
   - Chỉ ở mức định hướng / checklist.
   - KHÔNG mô tả chi tiết thao tác nếu dữ liệu không cung cấp.

4. **Lưu ý khi thực hiện**
   - Nêu các điểm người vận hành cần cân nhắc:
     + Ảnh hưởng tới dữ liệu
     + Ảnh hưởng tới vận hành
     + Yêu cầu phê duyệt (nếu có)

5. **Kết luận**
   - Tóm tắt vai trò của con người trong việc hoàn tất remediation cho finding này.
   - Nhấn mạnh đây là bước cần đánh giá cẩn trọng, không nên tự động hóa.

===== BẮT ĐẦU VIẾT MANUAL REMEDIATION RUNBOOK =====
"""
        return self._ask(prompt)

    def write_post_remediation_analysis(self, data):
        data_str = json.dumps(data, indent=2, ensure_ascii=False)

        prompt = f"""
Viết nội dung **Đánh giá của chuyên gia** cho Mục 7.3 của báo cáo bảo mật.
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
- Không gạch đầu dòng cụt, mỗi ý cần có giải thích ngắn.

===== NỘI DUNG CẦN VIẾT =====

Tổng quan thay đổi:
- Nhận định rõ ràng về sự thay đổi tư thế bảo mật sau remediation.
- Nêu mức giảm lỗi từ `initial_fail` xuống `final_fail` và ý nghĩa của sự thay đổi này.

Phân tích chi tiết:
- Đã khắc phục (Fixed): nêu số lượng lỗi đã xử lý và tác động trực tiếp tới an toàn hệ thống.
- Cần xử lý thủ công (Manual): mô tả bản chất các vấn đề còn tồn đọng và lý do cần can thiệp con người.
- Khắc phục thất bại (Failed):
  - Nếu bằng 0: ghi rõ không ghi nhận lỗi thực thi và hệ thống automation hoạt động ổn định.

Kết luận và hướng tiếp theo:
- Đánh giá mức độ rủi ro nghiêm trọng đã được kiểm soát đến đâu.
- Nêu rõ trọng tâm tiếp theo nên tập trung vào xử lý Manual hay duy trì trạng thái hiện tại.

===== VĂN PHONG =====
- Rõ ràng, trung lập, chắc chắn.
- Viết như kết luận của auditor, không viết kiểu tóm tắt gạch đầu dòng.

BẮT ĐẦU VIẾT:
"""
        return self._ask(prompt)

    def write_post_remediation_recommendations(self, data):
        data_str = json.dumps(data, indent=2, ensure_ascii=False)

        prompt = f"""
Viết nội dung **Khuyến nghị chiến lược** cho Mục 8 của báo cáo bảo mật.
Nội dung hướng tới cấp quản lý, dựa hoàn toàn trên dữ liệu sau remediation.

===== DỮ LIỆU SỬ DỤNG =====
{data_str}

===== QUY TẮC BẮT BUỘC =====
1. KHÔNG dùng ngôi thứ nhất.
2. KHÔNG đưa ra khuyến nghị cho vấn đề không tồn tại trong dữ liệu.
3. Không dùng ngôn ngữ sáo rỗng hoặc chung chung.

===== YÊU CẦU ĐỘ DÀI =====
- Mỗi khuyến nghị gồm:
  * Tiêu đề ngắn
  * **2–3 câu giải thích cụ thể**
- Không viết một câu duy nhất cho mỗi mục.

===== ĐỊNH HƯỚNG NỘI DUNG =====
- Ưu tiên xử lý các Manual Findings còn tồn đọng thông qua quy trình và phê duyệt rõ ràng.
- Nếu không có Failed, chỉ đề cập đến việc duy trì và củng cố automation hiện có.
- Đề xuất cơ chế giám sát và rà soát định kỳ để ngăn lỗi tái diễn.

===== VĂN PHONG =====
- Management-level
- Thực tế, gắn với dữ liệu
- Đủ chi tiết để hành động, không lan man

BẮT ĐẦU VIẾT:
"""
        return self._ask(prompt)
