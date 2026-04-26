# Lựa chọn mô hình LLM cho hệ thống

## 1. Yêu cầu

Hệ thống gồm 4 tác tử (Planning, Risk, Assessment, Report) chạy trên hạ tầng local với ràng buộc:

- **Phần cứng**: RTX 3060 Laptop (6 GB VRAM), 16 GB RAM
- **Ngôn ngữ**: Output tiếng Việt chuyên nghiệp (chủ yếu cho Report Agent)
- **Chất lượng**: Instruction following tốt, output có cấu trúc (JSON cho Planning/Risk/Assessment, văn xuôi cho Report)
- **Giấy phép**: Open-source, chạy offline

## 2. Hướng tiếp cận: SLM thay vì LLM

Hiện tại có 2 hướng triển khai LLM:

- **LLM lớn (>12B params)**: Chất lượng cao nhưng yêu cầu GPU server (≥16 GB VRAM) hoặc API trả phí (GPT-4, Claude). Không phù hợp với yêu cầu offline + open-source của dự án.
- **SLM (≤8B params, quantized Q4)**: Chạy được trên GPU consumer (6-8 GB VRAM), có thể offline hoàn toàn. Đánh đổi chất lượng nhưng phù hợp cho các tác tử có prompt được kiểm soát (structured JSON, template có RAG context).

Dự án chọn hướng **SLM** vì: (1) Dữ liệu bảo mật AWS nhạy cảm — không nên gửi qua API bên ngoài, (2) Prompt đã được thiết kế chặt với RAG + constraints — không cần khả năng reasoning tổng quát của LLM lớn, (3) Chi phí vận hành bằng 0.

## 3. Quy trình lựa chọn

Quá trình lựa chọn được chia thành 3 giai đoạn để thu hẹp dần từ landscape rộng về model cuối cùng:

```
Giai đoạn 1: Khảo sát  (20 model)
       ↓ Lọc phần cứng + hỗ trợ tiếng Việt
Giai đoạn 2: Shortlist  (4 model)
       ↓ Benchmark thực tế với prompt của Report Agent
Giai đoạn 3: Chốt  (1 model)
```

Dữ liệu đầy đủ được lưu ở `models_compare/Models_v2.xlsx` (7 sheet, đầy đủ tham chiếu HuggingFace và blog chính thức).

## 4. Khảo sát & lọc

Khảo sát 20 model từ 3 nhóm: LLM lớn (20-37B), LLM trung bình (7-12B), SLM (2-4B). Áp dụng 2 bộ lọc:

- **Phần cứng**: VRAM Q4 ≤ 5.5 GB (dư chỗ cho KV cache) → loại toàn bộ nhóm ≥ 12B
- **Tiếng Việt**: Có hỗ trợ ở mức trung bình trở lên → loại Phi-4-mini (không hỗ trợ), Mistral 7B (kém)

Kết quả shortlist 4 model vào giai đoạn benchmark:

| Model | Params | VRAM Q4 | Ghi chú |
|-------|--------|---------|---------|
| Gemma 3 4B IT | 4B | 2.8 GB | Hỗ trợ 140+ ngôn ngữ, IFEval 90.2 |
| Qwen2.5-7B-Instruct | 7B | 5.0 GB | Hỗ trợ VN chính thức, MMLU 75.4 |
| DeepSeek-R1-Distill-Qwen-7B | 7B | 4.7 GB | Reasoning mạnh, multilingual |
| Llama 3.2 3B Instruct | 3B | 2.0 GB | Baseline (model đang dùng) |

## 5. Benchmark thực tế

Chạy benchmark với 3 prompt thực từ `LLMWriter` của Report Agent (executive summary, remediation detail, recommendations). Đo 4 chỉ số: tốc độ sinh token, VRAM sử dụng, vi phạm ràng buộc output (word limit, ngôi thứ nhất, placeholder), chất lượng nội dung (chấm tay thang 1-5).

### Kết quả định lượng

| Model | Tốc độ (tok/s) | Tổng thời gian | VRAM (MB) | Violations |
|-------|:-:|:-:|:-:|:-:|
| **Gemma 3 4B** | **61.8** | **27.7 s** | 4849 | 3 |
| Qwen2.5-7B | 10.3 | 83.3 s | 5352 | **0** |
| DeepSeek-R1 7B | 11.2 | 258.5 s | 5342 | 2 |
| Llama 3.2 3B | 83.0 | 17.8 s | 3856 | 9 |

### Kết quả định tính (thang 1-5)

| Model | Tiếng Việt | Instruction | Nội dung | Văn phong | Tổng |
|-------|:-:|:-:|:-:|:-:|:-:|
| **Gemma 3 4B** | **5** | 3 | **5** | **5** | **21/25** |
| Qwen2.5-7B | 3 | **5** | **5** | 4 | 22/25 |
| DeepSeek-R1 7B | 2 | 3 | 4 | 4 | 16/25 |
| Llama 3.2 3B | 2 | 1 | 2 | 1 | 8/25 |

## 6. Quyết định

**Model được chọn: `gemma3:4b`** — sử dụng thống nhất cho cả 4 tác tử.

Áp dụng ma trận trọng số (Chất lượng tiếng Việt 25%, Tốc độ 20%, VRAM fit 15%, Instruction following 15%, Độ chính xác 15%, Văn phong 10%), Gemma 3 4B đạt điểm tổng cao nhất nhờ cân bằng tốt giữa 3 yếu tố quan trọng nhất:

- **Chất lượng tiếng Việt tự nhiên** (5/5) — tự nhiên nhất trong 4 candidate, không lẫn tiếng Anh
- **Tốc độ nhanh** (61.8 tok/s) — gấp 6× Qwen2.5-7B, gấp 9× DeepSeek-R1
- **VRAM thoải mái** (4.8/6 GB) — còn dư 1.2 GB cho KV cache ở context dài

**Trade-off đã chấp nhận**: Gemma 3 4B có xu hướng vượt word limit (2/3 test) do không tuân thủ ràng buộc số từ chặt bằng Qwen2.5. Được xử lý bằng cách tune `num_predict` và rõ ràng hoá constraint trong prompt.

**Các phương án đã loại**:
- **Qwen2.5-7B** (phương án B): Instruction following hoàn hảo (0 violations) nhưng output tiếng Anh dù prompt tiếng Việt, tốc độ chậm 6×.
- **DeepSeek-R1 7B**: Thinking block tốn nhiều token, tốc độ chậm 9×, output tiếng Anh — không phù hợp cho writing task.
- **Llama 3.2 3B** (baseline): Chất lượng tiếng Việt kém (không dấu), instruction following yếu, thường dump prompt thay vì sinh nội dung.
