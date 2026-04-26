<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo cáo Đánh giá Bảo mật AWS</title>
    <style>
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.7; color: #2c3e50;
    max-width: 1000px; margin: 0 auto; padding: 30px;
}
h1, h2, h3 { color: #2c3e50; }
h1 { border-bottom: 2px solid #2c3e50; padding-bottom: 10px; }
h2 { border-bottom: 1px solid #eee; padding-bottom: 8px; margin-top: 40px; }

/* Cover page */
.cover-page { text-align: center; padding: 60px 0; page-break-after: always; }
.cover-page h1 { border: none; font-size: 2em; }
.score-box { display: inline-block; padding: 20px; margin: 20px;
             border: 3px solid #2c3e50; border-radius: 10px; }
.score-number { font-size: 3em; font-weight: bold; }
.confidentiality { font-size: 0.8em; color: #999; margin-top: 40px;
                   font-style: italic; }

/* Table */
.styled-table { border-collapse: collapse; width: 100%; margin: 20px 0;
                font-size: 0.9em; box-shadow: 0 0 20px rgba(0,0,0,0.1); }
.styled-table thead tr { background: #009879; color: white; }
.styled-table th, .styled-table td { padding: 12px 15px; border: 1px solid #ddd; }
.styled-table tbody tr:nth-child(even) { background: #f3f3f3; }

/* Status colors */
.status-fixed  { color: #2E7D32; font-weight: bold; }
.status-manual { color: #E65100; font-weight: bold; }
.status-error  { color: #C62828; font-weight: bold; }

/* Severity badges */
.sev-critical { background: #B71C1C; color: white; padding: 2px 8px;
                border-radius: 3px; font-size: 0.85em; }
.sev-high     { background: #E65100; color: white; padding: 2px 8px;
                border-radius: 3px; font-size: 0.85em; }
.sev-medium   { background: #FFB300; color: #333; padding: 2px 8px;
                border-radius: 3px; font-size: 0.85em; }
.sev-low      { background: #1E88E5; color: white; padding: 2px 8px;
                border-radius: 3px; font-size: 0.85em; }

blockquote { background: #f9f9f9; border-left: 5px solid #ccc;
             margin: 1.5em 10px; padding: 0.5em 10px; }
pre { background: #f4f4f4; border: 1px solid #ddd; border-left: 3px solid #f36d33;
      padding: 1em; overflow: auto; font-size: 14px; }
.toc { background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }
.toc ol { line-height: 2; }

/* ---- Maturity-specific styles (Phase 6) ---- */
.maturity-banner {
    background: #E3F2FD; border-left: 5px solid #1E88E5;
    padding: 15px; margin: 20px 0;
}
.maturity-banner.warning {
    background: #FFF3E0; border-left-color: #E65100;
}
.stage-badge {
    display: inline-block; padding: 4px 12px;
    border-radius: 15px; font-weight: bold; font-size: 0.9em;
}
.stage-1quickwins     { background: #E8F5E9; color: #2E7D32; }
.stage-2foundational  { background: #E3F2FD; color: #1565C0; }
.stage-3efficient     { background: #F3E5F5; color: #7B1FA2; }
.stage-4optimized     { background: #FFF8E1; color: #F57F17; }

.domain-card {
    border: 1px solid #ddd; border-radius: 8px;
    padding: 20px; margin: 15px 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.domain-card-header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 15px;
}
.domain-score { font-size: 2em; font-weight: bold; }
.score-high   { color: #2E7D32; }
.score-medium { color: #E65100; }
.score-low    { color: #C62828; }

.capability-table { width: 100%; border-collapse: collapse; margin: 10px 0; }
.capability-table th { background: #f5f5f5; text-align: left; padding: 8px 12px; border-bottom: 2px solid #ddd; }
.capability-table td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }
.cap-score-bar { height: 8px; border-radius: 4px; background: #e0e0e0; display: inline-block; width: 60px; vertical-align: middle; margin-right: 5px; }
.cap-score-fill { height: 100%; border-radius: 4px; display: block; }

.delta-positive { color: #2E7D32; font-weight: bold; }
.delta-negative { color: #C62828; font-weight: bold; }
.delta-zero     { color: #757575; }
.metric-card {
    display: inline-block; text-align: center; padding: 15px 25px;
    border: 1px solid #e0e0e0; border-radius: 8px; margin: 5px;
    min-width: 120px;
}
.metric-value { font-size: 2em; font-weight: bold; }
.metric-label { font-size: 0.85em; color: #666; margin-top: 4px; }
.verification-pass { background: #E8F5E9; }
.verification-fail { background: #FFEBEE; }
.severity-critical { color: #C62828; font-weight: bold; }
.severity-high     { color: #E65100; font-weight: bold; }

@media print {
    .cover-page { page-break-after: always; }
    h1 { page-break-before: always; }
    h1:first-of-type { page-break-before: avoid; }
}
</style>
</head>
<body>


<!-- ============================================================ -->
<!-- COVER PAGE (Adaptive)                                         -->
<!-- ============================================================ -->

<div class="cover-page">
    <h1>BÁO CÁO ĐÁNH GIÁ VÀ KHẮC PHỤC BẢO MẬT AWS</h1>
    <p>
        <strong>Tài khoản:</strong> 123456789012 |
        <strong>Vùng:</strong> us-east-1
    </p>
    <p><strong>Ngày:</strong> 2026-04-20</p>
    <p><strong>Mã báo cáo:</strong> RPT-20260420-384D</p>

    <div class="score-box">
        <span class="score-number">79</span>
        <span>/ 100</span>
        <br><small>Điểm Bảo mật</small>
    </div>

    <p class="confidentiality">
        MẬT &mdash; Tài liệu này chứa thông tin đánh giá bảo mật nội bộ.
        Chỉ được phân phối cho nhân sự được ủy quyền.
    </p>
</div>


<!-- ============================================================ -->
<!-- TABLE OF CONTENTS (Adaptive)                                  -->
<!-- ============================================================ -->
<div class="toc">
    <h2>Mục lục</h2>
    <ol>
        <li>Tóm tắt điều hành</li>
        <li>Phạm vi và phương pháp</li>
        <li>Đánh giá trước khắc phục</li>
        <li>Bảng chi tiết phát hiện</li>

        <li>Chi tiết thực thi khắc phục</li>
        <li>Hậu Khắc phục
            <ol><li>Kết quả Xác minh</li><li>Hiệu quả Khắc phục</li><li>Rủi ro Còn lại</li><li>Phân tích Chuyên gia</li></ol>
        </li>
        <li>Khuyến nghị</li>

    </ol>
</div>

<!-- ============================================================ -->
<!-- 1. EXECUTIVE SUMMARY                                          -->
<!-- ============================================================ -->
<h1>1. Tóm tắt điều hành</h1>
<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>

<!-- ============================================================ -->
<!-- 2. SCOPE & METHODOLOGY                                        -->
<!-- ============================================================ -->
<h1>2. Phạm vi và phương pháp</h1>

<h2>2.1 Bối cảnh hệ thống</h2>
<table class="styled-table">
<thead><tr><th>Thuộc tính</th><th>Chi tiết</th></tr></thead>
<tbody>
    <tr><td><strong>Tài khoản AWS</strong></td><td><code>123456789012</code></td></tr>
    <tr><td><strong>Vùng (Region)</strong></td><td>us-east-1</td></tr>
    <tr><td><strong>Phạm vi quét</strong></td>
        <td>S3</td></tr>

    <tr><td><strong>Dịch vụ chính</strong></td>
        <td>Amazon S3</td></tr>

    <tr><td><strong>Công cụ</strong></td><td>Prowler, AWS SDK (boto3), PDCA Security Agent</td></tr>
</tbody>
</table>

<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>

<h2>2.2 Mục tiêu đánh giá</h2>
<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>

<!-- ============================================================ -->
<!-- 3. PRE-REMEDIATION ASSESSMENT                                 -->
<!-- ============================================================ -->
<h1>3. Đánh giá trước khắc phục</h1>

<h2>3.1 Trạng thái bảo mật ban đầu</h2>
<ul>
    <li><strong>Tổng số phát hiện:</strong> 6</li>
    <li><strong>ĐẠT (PASS):</strong> 3</li>
    <li><strong>KHÔNG ĐẠT (FAIL):</strong> 3</li>
</ul>
<p><strong>Phân bổ mức độ nghiêm trọng:</strong></p>
<ul>
    <li>Nghiêm trọng (Critical): <strong>1</strong></li>
    <li>Cao (High): <strong>1</strong></li>
    <li>Trung bình (Medium): <strong>0</strong></li>
    <li>Thấp (Low): <strong>1</strong></li>
</ul>

<h2>3.2 Phân tích trực quan</h2>
<table style="width:100%">
<tr>
    <td style="text-align:center; width:50%">
        <img src="charts/severity_bar.png" style="max-width:100%; height:auto;">
    </td>
    <td style="text-align:center; width:50%">
        <img src="charts/pass_fail_pie.png" style="max-width:100%; height:auto;">
    </td>
</tr>
</table>

<h2>3.3 Phân tích phát hiện</h2>
<h3>Tổng quan các mục ĐẠT</h3>
<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>

<h3>Tổng quan các mục KHÔNG ĐẠT</h3>
<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>

<!-- Focused mode: Security Capability Mapping (small table) -->


<!-- ============================================================ -->
<!-- 4. FINDINGS DETAIL TABLE                                      -->
<!-- ============================================================ -->
<h1>4. Bảng chi tiết phát hiện</h1>

<p><em>Ghi chú: 3 findings không thay đổi trạng thái (PASS &rarr; PASS) đã được ẩn.
Bảng dưới đây chỉ hiển thị các findings có thay đổi.</em></p>

<table class="styled-table">
<thead>
<tr>
    <th>STT</th><th>Phát hiện</th><th>Dịch vụ</th>
    <th>Tài nguyên</th><th>Mức độ</th>
    <th>Trước</th><th>Sau</th><th>Trạng thái</th>
</tr>
</thead>
<tbody>

<tr>
    <td>1</td>
    <td>Bucket prod-data-lake missing default encryption</td>
    <td>s3</td>
    <td><small>prod-data-lake</small></td>
    <td><span class="sev-high">High</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>3</td>
    <td>Bucket logs-archive allows public read</td>
    <td>s3</td>
    <td><small>logs-archive</small></td>
    <td><span class="sev-critical">Critical</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>5</td>
    <td>Bucket public-assets has access logging off</td>
    <td>s3</td>
    <td><small>public-assets</small></td>
    <td><span class="sev-low">Low</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

</tbody>
</table>

<!-- ============================================================ -->
<!-- 5. MATURITY ASSESSMENT (Adaptive — only full/partial)         -->
<!-- ============================================================ -->


<!-- ============================================================ -->
<!-- REMEDIATION EXECUTION (Section 5/6/7 depending on mode)       -->
<!-- ============================================================ -->

<h1>5. Chi tiết thực thi khắc phục</h1>






<h2>5.1 Khắc phục thành công</h2>



<p><em>Không có khắc phục tự động thành công.</em></p>


<h2>5.2 Khắc phục thất bại</h2>



<p><em>Không ghi nhận lỗi trong quá trình khắc phục tự động.</em></p>


<h2>5.3 Yêu cầu khắc phục thủ công</h2>

<p><em>Không ghi nhận yêu cầu khắc phục thủ công trong phạm vi đánh giá này.</em></p>




<!-- ============================================================ -->
<!-- POST-REMEDIATION (Enhanced — ALL MODES)                       -->
<!-- ============================================================ -->


<h1>6. Hậu Khắc phục</h1>


<!-- 8.1 Verification Table -->
<h2>6.1 Kết quả Xác minh</h2>
<p>Bảng dưới đây thể hiện kết quả xác minh cho từng finding sau khi
   thực hiện khắc phục. Mỗi finding được kiểm tra lại (re-scan) để
   xác nhận trạng thái thực tế.</p>

<p><em>3 findings không thay đổi trạng thái đã được ẩn.</em></p>


<table class="styled-table">
<thead>
<tr><th>STT</th><th>Finding</th><th>Service</th><th>Severity</th><th>Trước</th><th>Sau</th><th>Kết quả</th></tr>
</thead>
<tbody>

<tr class="verification-pass">
    <td>1</td>
    <td>Bucket prod-data-lake missing default encryption</td>
    <td>s3</td>
    <td class="severity-high">High</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>3</td>
    <td>Bucket logs-archive allows public read</td>
    <td>s3</td>
    <td class="severity-critical">Critical</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-pass">
    <td>5</td>
    <td>Bucket public-assets has access logging off</td>
    <td>s3</td>
    <td class="severity-low">Low</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

</tbody>
</table>

<!-- 8.2 Fix Metrics -->
<h2>6.2 Hiệu quả Khắc phục</h2>


<div style="text-align:center; margin: 20px 0;">
    <div class="metric-card">
        <div class="metric-value" style="color:#2E7D32">66.7%</div>
        <div class="metric-label">Tỷ lệ Khắc phục</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">2/3</div>
        <div class="metric-label">Findings Đã Fix</div>
    </div>
    <div class="metric-card">
        <div class="metric-value" style="color:#1565C0">100.0%</div>
        <div class="metric-label">Auto-fix Thành công</div>
    </div>
    <div class="metric-card">
        <div class="metric-value score-medium">
            1
        </div>
        <div class="metric-label">Findings Còn lại</div>
    </div>
</div>

<table class="styled-table">
<thead><tr><th>Chỉ số</th><th>Trước Khắc phục</th><th>Sau Khắc phục</th><th>Thay đổi</th></tr></thead>
<tbody>
<tr>
    <td>Findings PASS</td>
    <td>3</td>
    <td>5</td>
    <td class="delta-positive">+2</td>
</tr>
<tr>
    <td>Findings FAIL</td>
    <td>3</td>
    <td>1</td>
    <td class="delta-positive">-2</td>
</tr>
<tr>
    <td>Pass Rate</td>
    <td>50.0%</td>
    <td>83.3%</td>
    <td class="delta-positive">
        +33.3%
    </td>
</tr>
</tbody>
</table>


<!-- 8.3 Maturity Delta (only for full/partial with delta) -->

<!-- End maturity delta section -->

<!-- 8.4 Residual Risks -->
<h2>6.3 Rủi ro Còn lại</h2>



<p>Tổng cộng <strong>1</strong> findings vẫn còn FAIL sau khắc phục:</p>
<table class="styled-table">
<thead><tr><th>Mức độ</th><th>Số lượng</th></tr></thead>
<tbody>


<tr>
    <td class="severity-critical">CRITICAL</td>
    <td>1</td>
</tr>








</tbody>
</table>




<h3>Cần Xử lý Thủ công (1)</h3>
<p>Các findings này cần sự can thiệp thủ công từ đội ngũ quản trị.</p>
<table class="styled-table">
<thead><tr><th>Finding</th><th>Service</th><th>Severity</th><th>Resource</th></tr></thead>
<tbody>

<tr>
    <td>Bucket logs-archive allows public read</td>
    <td>s3</td>
    <td class="severity-critical">Critical</td>
    <td><small>logs-archive</small></td>
</tr>

</tbody>
</table>






<!-- 8.5 Expert Analysis -->
<h2>6.4 Phân tích Chuyên gia</h2>

<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>


<!-- ============================================================ -->
<!-- RECOMMENDATIONS & ACTION PLAN                                 -->
<!-- ============================================================ -->

<h1>7. Khuyến nghị</h1>
<h2>7.1 Khuyến nghị</h2>




<div class="metric-card" style="display:block; text-align:left; padding:15px 20px; margin:15px 0; background:#f8f9fa; border-left:4px solid #1565C0;">
    <strong>Tổng kết khắc phục</strong>
    <table style="width:100%; margin-top:8px; font-size:0.95em;">
        <tr>
            <td style="padding:4px 12px;">Findings FAIL ban đầu</td>
            <td style="padding:4px 12px; font-weight:bold;">3</td>
            <td style="padding:4px 12px;">Fix tự động thành công</td>
            <td style="padding:4px 12px; color:#2E7D32; font-weight:bold;">2</td>
        </tr>
        <tr>
            <td style="padding:4px 12px;">Fix tự động thất bại</td>
            <td style="padding:4px 12px; color:#2E7D32; font-weight:bold;">0</td>
            <td style="padding:4px 12px;">Cần xử lý thủ công</td>
            <td style="padding:4px 12px; color:#E65100; font-weight:bold;">1</td>
        </tr>
        <tr>
            <td style="padding:4px 12px;">FAIL còn lại sau khắc phục</td>
            <td style="padding:4px 12px; font-weight:bold;" colspan="3">1</td>
        </tr>
    </table>
</div>


<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>



<h2>7.2 Kế hoạch Hành động Tiếp theo</h2>

<p>Báo cáo được xây dựng dựa trên kết quả quét cấu hình hiện tại. Đội kỹ thuật đã rà soát toàn bộ các phát hiện và đề xuất phương án khắc phục phù hợp với mức độ ưu tiên.</p>


<!-- ============================================================ -->
<!-- FOOTER                                                        -->
<!-- ============================================================ -->
<hr>
<p style="text-align:center; font-size:0.8em; color:#999;">
    Mã báo cáo: RPT-20260420-384D | Ngày tạo: 2026-04-20 |
    PDCA Security Agent
</p>

</body>
</html>