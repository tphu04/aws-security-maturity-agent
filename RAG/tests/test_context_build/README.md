# Test Context Build (`/v1/context/build`)

Test chất lượng xây dựng context cho 3 loại agent consumer: **planning**, **risk**, **report**.

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
| `planning` | Build PlanningBundle (related_findings, control_mapping_ids, maturity_capability_ids) | query `"s3 public access block"`, check_ids `["iam_root_hardware_mfa_enabled"]` |
| `risk` | Build RiskBundle (primary_finding, related_findings, control_mapping, maturity_context) | findings-based với status FAIL, check_ids-based |
| `report` | Build ReportBundle (primary_topics, key_findings, control_themes, recommended_practices) | query `"s3 encryption and access controls"`, multi check_ids |
| `edge` | Trường hợp biên: tắt mappings/maturity, top_k=1 | `include_mappings=False`, `top_k=1` |

## Đọc kết quả

### Terminal output

```
[PASS] risk__s3_public_access_check_ids  (risk)
  consumer       : risk
  query/ids      : ['s3_bucket_level_public_access_block']
  service        : s3
  latency        : 120.45 ms
  confidence     : high
  bundle_type    : risk_bundle
  checks/maps/caps: 3/2/2
  expectation    : has risk_bundle: PASS
  expectation    : has primary_finding: PASS
```

- **bundle_type**: Loại bundle trả về (planning_bundle / risk_bundle / report_bundle)
- **checks/maps/caps**: Số lượng selected checks / mappings / capabilities trong diagnostics
- **confidence**: Mức tin cậy tổng hợp

### JSON output

File kết quả lưu tại `output/context_build_<timestamp>.json`:

```json
{
  "summary": { "total": 14, "passed": 12, "failed": 2, "skipped": 0 },
  "results": [
    {
      "case": "risk__s3_public_access_check_ids",
      "category": "risk",
      "bundle_summary": {
        "consumer": "risk",
        "bundle_type": "risk_bundle",
        "selected_check_count": 3,
        "selected_mapping_count": 2,
        "selected_capability_count": 2
      },
      "confidence": "high",
      "passed": true,
      "full_response": { ... }
    }
  ]
}
```

Mở file JSON để xem chi tiết:
- `full_response.data.payload.risk_bundle` — nội dung bundle thực tế
- `full_response.data.diagnostics` — quá trình chọn checks, mappings, capabilities
- `full_response.meta` — confidence, review_recommended

### Summary theo consumer

Cuối output terminal có summary nhóm theo consumer:

```
SUMMARY: 12/14 passed, 2 failed, 0 skipped
  planning  : 4/4 passed
  risk      : 3/4 passed
  report    : 3/3 passed
  edge      : 2/3 passed
```

## Thêm test case

Thêm entry mới vào list `CASES` trong `run_test.py`:

```python
{
    "name": "risk__ec2_open_ports",
    "category": "risk",
    "body": {
        "consumer": "risk",
        "findings": [
            {"check_id": "ec2_securitygroup_allow_ingress_from_internet_to_tcp_port_22", "service": "ec2", "status": "FAIL", "severity": "high"},
        ],
        "include_mappings": True,
        "include_maturity": True,
        "top_k": 5,
        "debug": True,
    },
    "expect": {
        "has_bundle": "risk_bundle",
        "has_primary_finding": True,
    },
},
```
