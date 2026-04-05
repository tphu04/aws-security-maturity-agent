# Test Retrieve Maturity (`/v1/retrieve/maturity`)

Test chất lượng truy vấn Maturity capabilities qua RAG API.

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
| `exact_id` | Lookup trực tiếp bằng `capability_id` | `block_public_access` |
| `keyword` | Truy vấn bằng keyword chính xác | `"encryption at rest"` |
| `semantic` | Truy vấn paraphrase / ngữ nghĩa | `"track and audit all API activity in the account"` |
| `stage_coverage` | Kiểm tra truy vấn tìm đúng capability ở các stage khác nhau | quickwins: `billing_alarms`, foundational: `imds_v2` |
| `retrieval_mode` | So sánh lexical / vector / hybrid cho cùng query | `"encryption at rest"` |

## Đọc kết quả

### Terminal output

```
[PASS] exact_id__block_public_access  (exact_id)
  query/cap_id   : block_public_access
  mode           : hybrid
  latency        : 32.15 ms
  confidence     : high
  top_ids        : ['block_public_access', ...]
  expectation    : top1 contains 'block_public_access': PASS
```

- **PASS/FAIL**: Kết quả so với expectation
- **top_ids**: Danh sách `capability_id` top-5 trả về
- **confidence**: Mức tin cậy (high/medium/low)

### JSON output

File kết quả lưu tại `output/retrieve_maturity_<timestamp>.json`:

```json
{
  "summary": { "total": 17, "passed": 15, "failed": 2, "skipped": 0 },
  "results": [
    {
      "case": "exact_id__block_public_access",
      "category": "exact_id",
      "top_doc_ids": ["block_public_access", ...],
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
    "name": "semantic__secure_root_account",
    "category": "semantic",
    "body": {"query": "secure the root account with hardware token", "top_k": 5, "debug": True},
    "expect_any_in_top5": ["enable_mfa"],
},
```
