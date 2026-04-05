# Test Retrieve Checks (`/v1/retrieve/checks`)

Test chất lượng truy vấn Prowler security checks qua RAG API.

## Yêu cầu

- RAG server đang chạy (mặc định `http://127.0.0.1:8000`)
- Python package: `requests`

## Chạy test

```bash
# Từ thư mục này
python run_test.py

# Hoặc chỉ định URL khác
python run_test.py --base-url http://localhost:8080
```

## Các loại test case

| Category | Mô tả | Ví dụ |
|---|---|---|
| `exact_id` | Lookup trực tiếp bằng `check_id` | `s3_bucket_level_public_access_block` |
| `keyword` | Truy vấn bằng keyword chính xác, kèm filter `service` | `"rds publicly accessible"` |
| `semantic` | Truy vấn paraphrase / ngữ nghĩa, không dùng keyword gốc | `"ensure we have an audit trail for all API calls"` |
| `cross_service` | Kiểm tra coverage đa dịch vụ (ec2, kms, lambda...) | `"security group allows unrestricted SSH"` |
| `retrieval_mode` | So sánh kết quả giữa lexical / vector / hybrid | Cùng query `"s3 versioning"` với 3 mode |

## Đọc kết quả

### Terminal output

```
[PASS] exact_id__s3_public_access_block  (exact_id)
  query/check_id : s3_bucket_level_public_access_block
  mode           : hybrid
  latency        : 45.23 ms
  confidence     : high
  top_ids        : ['s3_bucket_level_public_access_block', ...]
  expectation    : top1=s3_bucket_level_public_access_block: PASS
```

- **PASS/FAIL**: Kết quả so với expectation đã định nghĩa
- **top_ids**: Danh sách `doc_id` top-5 trả về
- **confidence**: Mức độ tin cậy RAG tự đánh giá (high/medium/low)
- **latency**: Thời gian xử lý (ms)

### JSON output

File kết quả lưu tại `output/retrieve_checks_<timestamp>.json` với cấu trúc:

```json
{
  "summary": { "total": 16, "passed": 14, "failed": 2, "skipped": 0 },
  "results": [
    {
      "case": "exact_id__s3_public_access_block",
      "category": "exact_id",
      "request": { ... },
      "top_doc_ids": ["s3_bucket_level_public_access_block", ...],
      "confidence": "high",
      "passed": true,
      "full_response": { ... }
    }
  ]
}
```

Mở file JSON để xem `full_response` chi tiết (diagnostics, scores, matched_by...).

## Thêm test case

Thêm entry mới vào list `CASES` trong `run_test.py`:

```python
{
    "name": "keyword__vpc_flow_logs",
    "category": "keyword",
    "body": {"query": "vpc flow logs enabled", "service": "vpc", "top_k": 5, "debug": True},
    "expect_any_in_top5": ["vpc_flow_logs_enabled"],
},
```
