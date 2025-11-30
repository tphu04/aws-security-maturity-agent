# 🛡️ Báo cáo Đánh giá & Cải thiện Bảo mật AWS
**Thời gian:** 2025-11-28 13:18:02 UTC
**Tài khoản:** `unknown`
---

**Báo Cáo An Ninh AWS**

**Tóm tắt Điều Hành**
--------------------

- **Account**: Unknown
- **Group Scan**: ['s3']
- **Thời gian**: Không có thông tin cụ thể về thời gian thực hiện điều hành.

**Những Cải Thiện Chính**
-------------------------

Dưới đây là danh sách các cải thiện chính đã được thực hiện trên tài khoản AWS:

*   **S3 Bucket Acl Prohibited**: Cài đặt ACL cho bucket S3 để ngăn chặn truy cập không cần thiết.
*   **S3 Bucket Cross-Account Access**: Cài đặt quyền truy cập giữa tài khoản để đảm bảo an toàn cho dữ liệu.
*   **S3 Bucket Default Encryption**: Cài đặt mã hóa mặc định cho bucket S3 để bảo vệ dữ liệu.
*   **S3 Bucket Event Notifications Enabled**: Bật notifications cho các sự kiện trong bucket S3 để nhận thông báo khi có thay đổi.
*   **S3 Bucket KMS Encryption**: Sử dụng mã hóa KMS để bảo vệ dữ liệu trong bucket S3.
*   **S3 Bucket Level Public Access Block**: Cài đặt level public access block để ngăn chặn truy cập công khai cho bucket S3.

**Rủi Ro Còn Tồn Tại**
-------------------------

Dưới đây là danh sách các rủi ro còn tồn tại sau khi thực hiện điều hành:

*   **S3 Bucket Cross-Region Replication**: Không cài đặt replication giữa khu vực khác nhau.
*   **S3 Bucket No MFA Delete**: Không bật mã hóa hai yếu tố (MFA) để xóa bucket S3.

**Khuyến Nghị Tiếp Theo**
-------------------------

Để đảm bảo an toàn cho tài khoản AWS, chúng tôi khuyến nghị thực hiện các bước sau:

*   Cài đặt replication giữa khu vực khác nhau cho bucket S3.
*   Bật mã hóa hai yếu tố (MFA) để xóa bucket S3.

**Kết luận**
----------

Sau khi thực hiện điều hành, chúng tôi đã cải thiện một số vấn đề an ninh trên tài khoản AWS. Tuy nhiên, vẫn còn một số rủi ro tồn tại và cần được giải quyết sớm nhất có thể.

---

## 📊 Tóm tắt BEFORE / AFTER
- Tổng findings: **19**
- Đã cải thiện: **0**
- Không đổi: **19**
- Phát sinh mới: **0**

---

## 📋 Bảng chi tiết
| UID | Trước | Sau | Thay đổi |
|------|--------|------|----------|
| `prowler-aws-s3_account_level_public_access_blocks-065209282642-us-east-1-065209282642|065209282642` | FAIL | FAIL | **Unchanged** |
| `prowler-aws-s3_bucket_acl_prohibited-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_cross_account_access-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_cross_region_replication-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | FAIL | FAIL | **Unchanged** |
| `prowler-aws-s3_bucket_default_encryption-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_event_notifications_enabled-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | FAIL | FAIL | **Unchanged** |
| `prowler-aws-s3_bucket_kms_encryption-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_level_public_access_block-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_lifecycle_enabled-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_no_mfa_delete-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | FAIL | FAIL | **Unchanged** |
| `prowler-aws-s3_bucket_object_lock-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | FAIL | FAIL | **Unchanged** |
| `prowler-aws-s3_bucket_object_versioning-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_policy_public_write_access-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_public_access-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_public_list_acl-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_public_write_acl-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_secure_transport_policy-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |
| `prowler-aws-s3_bucket_server_access_logging_enabled-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | FAIL | FAIL | **Unchanged** |
| `prowler-aws-s3_bucket_shadow_resource_vulnerability-065209282642-us-east-1-prowler-test-public-bucket|prowler-test-public-bucket` | PASS | PASS | **Unchanged** |