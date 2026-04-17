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
    <h1>BÁO CÁO ĐÁNH GIÁ BẢO MẬT AWS</h1>
    <div class="maturity-banner warning" style="text-align:left; display:inline-block;">
        Đánh giá một phần &mdash; 29/78
        năng lực được kiểm tra
        
    </div>
    <p>
        <strong>Tài khoản:</strong> 123456789012 |
        <strong>Vùng:</strong> ap-southeast-1
    </p>
    <p><strong>Ngày:</strong> 2026-04-15</p>
    <p><strong>Mã báo cáo:</strong> RPT-20260415-F50A</p>

    <div class="score-box">
        <span class="score-number">50</span><span>/ 100</span>
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

        <li>Đánh giá Bảo mật theo Năng lực (Phạm vi Giới hạn)</li>
        <li>Chi tiết thực thi khắc phục</li>
        <li>Hậu Khắc phục
            <ol><li>Kết quả Xác minh</li><li>Hiệu quả Khắc phục</li><li>Tác động lên Năng lực</li><li>Rủi ro Còn lại</li><li>Phân tích Chuyên gia</li></ol>
        </li>
        <li>Khuyến nghị &amp; Kế hoạch Tiếp theo</li>

    </ol>
</div>

<!-- ============================================================ -->
<!-- 1. EXECUTIVE SUMMARY                                          -->
<!-- ============================================================ -->
<h1>1. Tóm tắt điều hành</h1>
<p>Mock LLM response for visual testing.</p>

<!-- ============================================================ -->
<!-- 2. SCOPE & METHODOLOGY                                        -->
<!-- ============================================================ -->
<h1>2. Phạm vi và phương pháp</h1>

<h2>2.1 Bối cảnh hệ thống</h2>
<table class="styled-table">
<thead><tr><th>Thuộc tính</th><th>Chi tiết</th></tr></thead>
<tbody>
    <tr><td><strong>Tài khoản AWS</strong></td><td><code>123456789012</code></td></tr>
    <tr><td><strong>Vùng (Region)</strong></td><td>ap-southeast-1</td></tr>
    <tr><td><strong>Phạm vi quét</strong></td>
        <td>S3, IAM, CLOUDTRAIL</td></tr>
    <tr><td><strong>Công cụ</strong></td><td>Prowler, AWS SDK (boto3), PDCA Security Agent</td></tr>
</tbody>
</table>

<p>Mock LLM response for visual testing.</p>

<h2>2.2 Mục tiêu đánh giá</h2>
<p>Mock LLM response for visual testing.</p>

<!-- ============================================================ -->
<!-- 3. PRE-REMEDIATION ASSESSMENT                                 -->
<!-- ============================================================ -->
<h1>3. Đánh giá trước khắc phục</h1>

<h2>3.1 Trạng thái bảo mật ban đầu</h2>
<ul>
    <li><strong>Tổng số phát hiện:</strong> 502</li>
    <li><strong>ĐẠT (PASS):</strong> 250</li>
    <li><strong>KHÔNG ĐẠT (FAIL):</strong> 252</li>
</ul>
<p><strong>Phân bổ mức độ nghiêm trọng:</strong></p>
<ul>
    <li>Nghiêm trọng (Critical): <strong>126</strong></li>
    <li>Cao (High): <strong>126</strong></li>
    <li>Trung bình (Medium): <strong>125</strong></li>
    <li>Thấp (Low): <strong>125</strong></li>
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
<p>Mock LLM response for visual testing.</p>

<h3>Tổng quan các mục KHÔNG ĐẠT</h3>
<p>Mock LLM response for visual testing.</p>

<!-- Focused mode: Security Capability Mapping (small table) -->


<!-- ============================================================ -->
<!-- 4. FINDINGS DETAIL TABLE                                      -->
<!-- ============================================================ -->
<h1>4. Bảng chi tiết phát hiện</h1>

<p><em>Ghi chú: 250 findings không thay đổi trạng thái (PASS &rarr; PASS) đã được ẩn.
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
    <td>251</td>
    <td>Check: Ecr Repositories Tag Immutability</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-250</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>252</td>
    <td>Check: Ecs Cluster Container Insights Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-251</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>253</td>
    <td>Check: Ecs Service Fargate Latest Platform Version</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-252</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>254</td>
    <td>Check: Ecs Service No Assign Public Ip</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-253</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>255</td>
    <td>Check: Ecs Task Definitions Containers Readonly Access</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-254</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>256</td>
    <td>Check: Ecs Task Definitions Host Namespace Not Shared</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-255</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>PASS</td>
    <td class="status-fixed">
        Fixed
    </td>
</tr>

<tr>
    <td>257</td>
    <td>Check: Ecs Task Definitions Host Networking Mode Users</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-256</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>258</td>
    <td>Check: Ecs Task Definitions Logging Block Mode</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-257</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>259</td>
    <td>Check: Ecs Task Definitions Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-258</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>260</td>
    <td>Check: Ecs Task Definitions No Environment Secrets</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-259</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>261</td>
    <td>Check: Ecs Task Definitions No Privileged Containers</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-260</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>262</td>
    <td>Check: Ecs Task Set No Assign Public Ip</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-261</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>263</td>
    <td>Check: Efs Access Point Enforce Root Directory</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-262</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>264</td>
    <td>Check: Efs Access Point Enforce User Identity</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-263</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>265</td>
    <td>Check: Efs Encryption At Rest Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-264</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>266</td>
    <td>Check: Efs Have Backup Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-265</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>267</td>
    <td>Check: Efs Mount Target Not Publicly Accessible</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-266</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>268</td>
    <td>Check: Efs Multi Az Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-267</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>269</td>
    <td>Check: Efs Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-268</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>270</td>
    <td>Check: Eks Cluster Deletion Protection Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-269</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>271</td>
    <td>Check: Eks Cluster Kms Cmk Encryption In Secrets Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-270</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>272</td>
    <td>Check: Eks Cluster Network Policy Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-271</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>273</td>
    <td>Check: Eks Cluster Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-272</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>274</td>
    <td>Check: Eks Control Plane Logging All Types Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-273</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>275</td>
    <td>Check: Elasticache Redis Cluster Automatic Failover Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-274</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>276</td>
    <td>Check: Elasticache Redis Cluster Backup Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-275</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>277</td>
    <td>Check: Elasticache Redis Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-276</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>278</td>
    <td>Check: Elasticache Redis Cluster Rest Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-277</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>279</td>
    <td>Check: Elasticbeanstalk Environment Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-278</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>280</td>
    <td>Check: Elasticbeanstalk Environment Enhanced Health Reporting</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-279</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>281</td>
    <td>Check: Elb Cross Zone Load Balancing Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-280</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>282</td>
    <td>Check: Elb Desync Mitigation Mode</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-281</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>283</td>
    <td>Check: Elb Insecure Ssl Ciphers</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-282</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>284</td>
    <td>Check: Elb Internet Facing</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-283</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>285</td>
    <td>Check: Elb Is In Multiple Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-284</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>286</td>
    <td>Check: Elb Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-285</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>287</td>
    <td>Check: Elb Ssl Listeners</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-286</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>288</td>
    <td>Check: Elb Ssl Listeners Use Acm Certificate</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-287</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>289</td>
    <td>Check: Elbv2 Cross Zone Load Balancing Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-288</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>290</td>
    <td>Check: Elbv2 Insecure Ssl Ciphers</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-289</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>291</td>
    <td>Check: Elbv2 Internet Facing</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-290</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>292</td>
    <td>Check: Elbv2 Is In Multiple Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-291</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>293</td>
    <td>Check: Elbv2 Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-292</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>294</td>
    <td>Check: Elbv2 Nlb Tls Termination Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-293</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>295</td>
    <td>Check: Elbv2 Ssl Listeners</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-294</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>296</td>
    <td>Check: Elbv2 Waf Acl Attached</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-295</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>297</td>
    <td>Check: Emr Cluster Account Public Block Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-296</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>298</td>
    <td>Check: Emr Cluster Publicly Accesible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-297</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>299</td>
    <td>Check: Eventbridge Schema Registry Cross Account Access</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-298</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>300</td>
    <td>Check: Firehose Stream Encrypted At Rest</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-299</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>301</td>
    <td>Check: Fsx File System Copy Tags To Backups Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-300</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>302</td>
    <td>Check: Fsx File System Copy Tags To Volumes Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-301</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>303</td>
    <td>Check: Fsx Windows File System Multi Az Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-302</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>304</td>
    <td>Check: Glue Data Catalogs Connection Passwords Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-303</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>305</td>
    <td>Check: Glue Data Catalogs Metadata Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-304</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>306</td>
    <td>Check: Glue Data Catalogs Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-305</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>307</td>
    <td>Check: Glue Database Connections Ssl Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-306</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>308</td>
    <td>Check: Glue Development Endpoints Cloudwatch Logs Encryption Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-307</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>309</td>
    <td>Check: Glue Development Endpoints Job Bookmark Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-308</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>310</td>
    <td>Check: Glue Development Endpoints S3 Encryption Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-309</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>311</td>
    <td>Check: Glue Etl Jobs Amazon S3 Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-310</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>312</td>
    <td>Check: Glue Etl Jobs Cloudwatch Logs Encryption Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-311</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>313</td>
    <td>Check: Glue Etl Jobs Job Bookmark Encryption Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-312</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>314</td>
    <td>Check: Glue Etl Jobs Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-313</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>315</td>
    <td>Check: Glue Ml Transform Encrypted At Rest</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-314</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>316</td>
    <td>Check: Guardduty Centrally Managed</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-315</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>317</td>
    <td>Check: Guardduty Ec2 Malware Protection Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-316</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>318</td>
    <td>Check: Guardduty Eks Audit Log Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-317</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>319</td>
    <td>Check: Guardduty Eks Runtime Monitoring Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-318</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>320</td>
    <td>Check: Guardduty Is Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-319</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>321</td>
    <td>Check: Guardduty Lambda Protection Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-320</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>322</td>
    <td>Check: Guardduty No High Severity Findings</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-321</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>323</td>
    <td>Check: Guardduty Rds Protection Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-322</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>324</td>
    <td>Check: Guardduty S3 Protection Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-323</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>325</td>
    <td>Check: Iam Administrator Access With Mfa</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-324</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>326</td>
    <td>Check: Iam Avoid Root Usage</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-325</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>327</td>
    <td>Check: Iam Aws Attached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-326</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>328</td>
    <td>Check: Iam Check Saml Providers Sts</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-327</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>329</td>
    <td>Check: Iam Customer Attached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-328</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>330</td>
    <td>Check: Iam Customer Unattached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-329</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>331</td>
    <td>Check: Iam Group Administrator Access Policy</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-330</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>332</td>
    <td>Check: Iam Inline Policy Allows Privilege Escalation</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-331</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>333</td>
    <td>Check: Iam Inline Policy No Administrative Privileges</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-332</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>334</td>
    <td>Check: Iam Inline Policy No Full Access To Cloudtrail</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-333</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>335</td>
    <td>Check: Iam Inline Policy No Full Access To Kms</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-334</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>336</td>
    <td>Check: Iam No Custom Policy Permissive Role Assumption</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-335</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>337</td>
    <td>Check: Iam No Expired Server Certificates Stored</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-336</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>338</td>
    <td>Check: Iam No Root Access Key</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-337</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>339</td>
    <td>Check: Iam Password Policy Expires Passwords Within 90 Days Or Less</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-338</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>340</td>
    <td>Check: Iam Password Policy Lowercase</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-339</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>341</td>
    <td>Check: Iam Password Policy Minimum Length 14</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-340</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>342</td>
    <td>Check: Iam Password Policy Number</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-341</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>343</td>
    <td>Check: Iam Password Policy Reuse 24</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-342</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>344</td>
    <td>Check: Iam Password Policy Symbol</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-343</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>345</td>
    <td>Check: Iam Password Policy Uppercase</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-344</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>346</td>
    <td>Check: Iam Policy Allows Privilege Escalation</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-345</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>347</td>
    <td>Check: Iam Policy Attached Only To Group Or Roles</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-346</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>348</td>
    <td>Check: Iam Policy Cloudshell Admin Not Attached</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-347</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>349</td>
    <td>Check: Iam Policy No Full Access To Cloudtrail</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-348</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>350</td>
    <td>Check: Iam Policy No Full Access To Kms</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-349</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>351</td>
    <td>Check: Iam Role Administratoraccess Policy</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-350</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>352</td>
    <td>Check: Iam Role Cross Account Readonlyaccess Policy</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-351</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>353</td>
    <td>Check: Iam Role Cross Service Confused Deputy Prevention</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-352</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>354</td>
    <td>Check: Iam Root Credentials Management Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-353</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>355</td>
    <td>Check: Iam Root Hardware Mfa Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-354</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>356</td>
    <td>Check: Iam Root Mfa Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-355</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>357</td>
    <td>Check: Iam Rotate Access Key 90 Days</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-356</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>358</td>
    <td>Check: Iam Securityaudit Role Created</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-357</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>359</td>
    <td>Check: Iam Support Role Created</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-358</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>360</td>
    <td>Check: Iam User Accesskey Unused</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-359</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>361</td>
    <td>Check: Iam User Administrator Access Policy</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-360</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>362</td>
    <td>Check: Iam User Console Access Unused</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-361</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>363</td>
    <td>Check: Iam User Hardware Mfa Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-362</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>364</td>
    <td>Check: Iam User Mfa Enabled Console Access</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-363</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>365</td>
    <td>Check: Iam User No Setup Initial Access Key</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-364</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>366</td>
    <td>Check: Iam User Two Active Access Key</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-365</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>367</td>
    <td>Check: Iam User With Temporary Credentials</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-366</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>368</td>
    <td>Check: Inspector2 Active Findings Exist</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-367</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>369</td>
    <td>Check: Inspector2 Is Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-368</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>370</td>
    <td>Check: Kafka Cluster Encryption At Rest Uses Cmk</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-369</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>371</td>
    <td>Check: Kafka Cluster Enhanced Monitoring Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-370</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>372</td>
    <td>Check: Kafka Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-371</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>373</td>
    <td>Check: Kafka Cluster Is Public</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-372</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>374</td>
    <td>Check: Kafka Connector In Transit Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-373</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>375</td>
    <td>Check: Kinesis Stream Data Retention Period</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-374</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>376</td>
    <td>Check: Kinesis Stream Encrypted At Rest</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-375</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>377</td>
    <td>Check: Kms Cmk Are Used</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-376</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>378</td>
    <td>Check: Kms Cmk Not Deleted Unintentionally</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-377</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>379</td>
    <td>Check: Kms Cmk Not Multi Region</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-378</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>380</td>
    <td>Check: Kms Cmk Rotation Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-379</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>381</td>
    <td>Check: Kms Key Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-380</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>382</td>
    <td>Check: Lightsail Instance Automated Snapshots</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-381</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>383</td>
    <td>Check: Lightsail Instance Public</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-382</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>384</td>
    <td>Check: Macie Automated Sensitive Data Discovery Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-383</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>385</td>
    <td>Check: Macie Is Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-384</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>386</td>
    <td>Check: Mq Broker Active Deployment Mode</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-385</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>387</td>
    <td>Check: Mq Broker Cluster Deployment Mode</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-386</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>388</td>
    <td>Check: Mq Broker Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-387</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>389</td>
    <td>Check: Mq Broker Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-388</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>390</td>
    <td>Check: Neptune Cluster Backup Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-389</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>391</td>
    <td>Check: Neptune Cluster Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-390</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>392</td>
    <td>Check: Neptune Cluster Deletion Protection</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-391</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>393</td>
    <td>Check: Neptune Cluster Iam Authentication Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-392</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>394</td>
    <td>Check: Neptune Cluster Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-393</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>395</td>
    <td>Check: Neptune Cluster Multi Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-394</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>396</td>
    <td>Check: Neptune Cluster Public Snapshot</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-395</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>397</td>
    <td>Check: Neptune Cluster Snapshot Encrypted</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-396</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>398</td>
    <td>Check: Neptune Cluster Storage Encrypted</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-397</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>399</td>
    <td>Check: Neptune Cluster Uses Public Subnet</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-398</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>400</td>
    <td>Check: Networkfirewall Deletion Protection</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-399</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>401</td>
    <td>Check: Networkfirewall In All Vpc</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-400</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>402</td>
    <td>Check: Networkfirewall Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-401</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>403</td>
    <td>Check: Networkfirewall Multi Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-402</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>404</td>
    <td>Check: Networkfirewall Policy Rule Group Associated</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-403</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>405</td>
    <td>Check: Opensearch Service Domains Access Control Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-404</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>406</td>
    <td>Check: Opensearch Service Domains Audit Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-405</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>407</td>
    <td>Check: Opensearch Service Domains Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-406</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>408</td>
    <td>Check: Opensearch Service Domains Encryption At Rest Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-407</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>409</td>
    <td>Check: Opensearch Service Domains Fault Tolerant Data Nodes</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-408</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>410</td>
    <td>Check: Opensearch Service Domains Fault Tolerant Master Nodes</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-409</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>411</td>
    <td>Check: Opensearch Service Domains Https Communications Enforced</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-410</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>412</td>
    <td>Check: Opensearch Service Domains Node To Node Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-411</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>413</td>
    <td>Check: Opensearch Service Domains Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-412</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>414</td>
    <td>Check: Opensearch Service Domains Updated To The Latest Service Software Version</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-413</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>415</td>
    <td>Check: Opensearch Service Domains Use Cognito Authentication For Kibana</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-414</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>416</td>
    <td>Check: Organizations Account Part Of Organizations</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-415</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>417</td>
    <td>Check: Organizations Delegated Administrators</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-416</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>418</td>
    <td>Check: Organizations Opt Out Ai Services Policy</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-417</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>419</td>
    <td>Check: Organizations Scp Check Deny Regions</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-418</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>420</td>
    <td>Check: Organizations Tags Policies Enabled And Attached</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-419</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>421</td>
    <td>Check: Rds Cluster Backtrack Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-420</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>422</td>
    <td>Check: Rds Cluster Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-421</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>423</td>
    <td>Check: Rds Cluster Critical Event Subscription</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-422</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>424</td>
    <td>Check: Rds Cluster Iam Authentication Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-423</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>425</td>
    <td>Check: Rds Cluster Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-424</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>426</td>
    <td>Check: Rds Cluster Minor Version Upgrade Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-425</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>427</td>
    <td>Check: Rds Cluster Multi Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-426</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>428</td>
    <td>Check: Rds Cluster Non Default Port</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-427</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>429</td>
    <td>Check: Rds Cluster Storage Encrypted</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-428</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>430</td>
    <td>Check: Rds Instance Certificate Expiration</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-429</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>431</td>
    <td>Check: Rds Instance Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-430</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>432</td>
    <td>Check: Rds Instance Critical Event Subscription</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-431</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>433</td>
    <td>Check: Rds Instance Enhanced Monitoring Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-432</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>434</td>
    <td>Check: Rds Instance Event Subscription Parameter Groups</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-433</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>435</td>
    <td>Check: Rds Instance Event Subscription Security Groups</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-434</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>436</td>
    <td>Check: Rds Instance Iam Authentication Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-435</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>437</td>
    <td>Check: Rds Instance Inside Vpc</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-436</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>438</td>
    <td>Check: Rds Instance Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-437</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>439</td>
    <td>Check: Rds Instance Minor Version Upgrade Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-438</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>440</td>
    <td>Check: Rds Instance Multi Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-439</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>441</td>
    <td>Check: Rds Instance No Public Access</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-440</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>442</td>
    <td>Check: Rds Instance Non Default Port</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-441</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>443</td>
    <td>Check: Rds Instance Storage Encrypted</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-442</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>444</td>
    <td>Check: Rds Instance Transport Encrypted</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-443</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>445</td>
    <td>Check: Rds Snapshots Encrypted</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-444</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>446</td>
    <td>Check: Rds Snapshots Public Access</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-445</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>447</td>
    <td>Check: Redshift Cluster Audit Logging</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-446</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>448</td>
    <td>Check: Redshift Cluster Encrypted At Rest</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-447</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>449</td>
    <td>Check: Redshift Cluster Enhanced Vpc Routing</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-448</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>450</td>
    <td>Check: Redshift Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-449</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>451</td>
    <td>Check: Redshift Cluster Multi Az Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-450</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>452</td>
    <td>Check: Redshift Cluster Non Default Database Name</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-451</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>453</td>
    <td>Check: Redshift Cluster Non Default Username</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-452</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>454</td>
    <td>Check: Redshift Cluster Public Access</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-453</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>455</td>
    <td>Check: Route53 Dangling Ip Subdomain Takeover</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-454</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>456</td>
    <td>Check: Route53 Public Hosted Zones Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-455</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>457</td>
    <td>Check: Sagemaker Endpoint Config Prod Variant Instances</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-456</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>458</td>
    <td>Check: Sagemaker Notebook Instance Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-457</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>459</td>
    <td>Check: Sagemaker Notebook Instance Root Access Disabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-458</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>460</td>
    <td>Check: Sagemaker Training Jobs Intercontainer Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-459</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>461</td>
    <td>Check: Sagemaker Training Jobs Volume And Output Encryption Enabled</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-460</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>462</td>
    <td>Check: Secretsmanager Automatic Rotation Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-461</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>463</td>
    <td>Check: Secretsmanager Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-462</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>464</td>
    <td>Check: Secretsmanager Secret Rotated Periodically</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-463</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>465</td>
    <td>Check: Securityhub Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-464</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>466</td>
    <td>Check: Servicecatalog Portfolio Shared Within Organization Only</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-465</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>467</td>
    <td>Check: Ses Identity Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-466</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>468</td>
    <td>Check: Shield Advanced Protection In Associated Elastic Ips</td>
    <td>network</td>
    <td><small>arn:aws:s3:::bucket-467</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>469</td>
    <td>Check: Shield Advanced Protection In Classic Load Balancers</td>
    <td>network</td>
    <td><small>arn:aws:s3:::bucket-468</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>470</td>
    <td>Check: Shield Advanced Protection In Cloudfront Distributions</td>
    <td>network</td>
    <td><small>arn:aws:s3:::bucket-469</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>471</td>
    <td>Check: Shield Advanced Protection In Global Accelerators</td>
    <td>network</td>
    <td><small>arn:aws:s3:::bucket-470</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>472</td>
    <td>Check: Shield Advanced Protection In Internet Facing Load Balancers</td>
    <td>network</td>
    <td><small>arn:aws:s3:::bucket-471</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>473</td>
    <td>Check: Shield Advanced Protection In Route53 Hosted Zones</td>
    <td>network</td>
    <td><small>arn:aws:s3:::bucket-472</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>474</td>
    <td>Check: Sns Subscription Not Using Http Endpoints</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-473</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>475</td>
    <td>Check: Sns Topics Kms Encryption At Rest Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-474</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>476</td>
    <td>Check: Sns Topics Not Publicly Accessible</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-475</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>477</td>
    <td>Check: Sqs Queues Not Publicly Accessible</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-476</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>478</td>
    <td>Check: Sqs Queues Server Side Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-477</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>479</td>
    <td>Check: Ssm Document Secrets</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-478</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>480</td>
    <td>Check: Ssmincidents Enabled With Plans</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-479</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>481</td>
    <td>Check: Stepfunctions Statemachine Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-480</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>482</td>
    <td>Check: Storagegateway Fileshare Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-481</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>483</td>
    <td>Check: Storagegateway Gateway Fault Tolerant</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-482</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>484</td>
    <td>Check: Transfer Server In Transit Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-483</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>485</td>
    <td>Check: Trustedadvisor Errors And Warnings</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-484</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>486</td>
    <td>Check: Trustedadvisor Premium Support Plan Subscribed</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-485</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>487</td>
    <td>Check: Vpc Different Regions</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-486</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>488</td>
    <td>Check: Vpc Endpoint For Ec2 Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-487</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>489</td>
    <td>Check: Vpc Endpoint Multi Az Enabled</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-488</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>490</td>
    <td>Check: Vpc Flow Logs Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-489</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>491</td>
    <td>Check: Vpc Peering Routing Tables With Least Privilege</td>
    <td>identity</td>
    <td><small>arn:aws:s3:::bucket-490</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>492</td>
    <td>Check: Vpc Subnet Different Az</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-491</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>493</td>
    <td>Check: Vpc Vpn Connection Tunnels Up</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-492</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>494</td>
    <td>Check: Waf Global Rule With Conditions</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-493</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>495</td>
    <td>Check: Waf Global Webacl Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-494</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>496</td>
    <td>Check: Waf Regional Rule With Conditions</td>
    <td>resilience</td>
    <td><small>arn:aws:s3:::bucket-495</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>497</td>
    <td>Check: Wafv2 Webacl Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-496</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>498</td>
    <td>Check: Wafv2 Webacl Rule Logging Enabled</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-497</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>499</td>
    <td>Check: Wafv2 Webacl With Rules</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-498</small></td>
    <td><span class="sev-medium">MEDIUM</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

<tr>
    <td>500</td>
    <td>Check: Wellarchitected Workload No High Or Medium Risks</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-499</small></td>
    <td><span class="sev-low">LOW</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>501</td>
    <td>Check: Workspaces Volume Encryption Enabled</td>
    <td>data</td>
    <td><small>arn:aws:s3:::bucket-500</small></td>
    <td><span class="sev-critical">CRITICAL</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-error">
        Still Failing (RemediationFailed)
    </td>
</tr>

<tr>
    <td>502</td>
    <td>Check: Workspaces Vpc 2Private 1Public Subnets Nat</td>
    <td>logging</td>
    <td><small>arn:aws:s3:::bucket-501</small></td>
    <td><span class="sev-high">HIGH</span></td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td class="status-manual">
        Still Failing (ManualRequired)
    </td>
</tr>

</tbody>
</table>

<!-- ============================================================ -->
<!-- 5. MATURITY ASSESSMENT (Adaptive — only full/partial)         -->
<!-- ============================================================ -->

<!-- ============================================================ -->
<!-- 5. PARTIAL MATURITY                                           -->
<!-- ============================================================ -->
<h1>5. Đánh giá Bảo mật theo Năng lực (Phạm vi Giới hạn)</h1>

<div class="maturity-banner warning">
    <strong>Lưu ý:</strong> Đánh giá này chỉ bao gồm
    29 / 78 năng lực bảo mật.
    Kết quả không đại diện cho mức độ trưởng thành toàn diện của hệ thống.
    Để có đánh giá đầy đủ, cần mở rộng phạm vi quét sang các dịch vụ khác.
</div>

<h2>5.1 Tổng quan</h2>


<div style="text-align:center">
    <img src="charts/stage_progress.png" style="max-width:700px">
</div>


<p>Mock LLM response for visual testing.</p>

<!-- Summary table -->
<table class="styled-table">
<thead><tr><th>Lĩnh vực</th><th>Score</th><th>Capabilities</th><th>Trạng thái</th></tr></thead>
<tbody>


<tr>
    <td>Data Protection</td>
    <td>50.7</td>
    <td>10</td>
    <td><span class="stage-badge stage-1quickwins">Quick Wins</span></td>
</tr>



<tr>
    <td>Identity & Access Management</td>
    <td>46.2</td>
    <td>17</td>
    <td><span class="stage-badge stage-1quickwins">Quick Wins</span></td>
</tr>



<tr>
    <td>Logging & Monitoring</td>
    <td>56.1</td>
    <td>7</td>
    <td><span class="stage-badge stage-1quickwins">Quick Wins</span></td>
</tr>



<tr>
    <td>Resilience</td>
    <td>59.1</td>
    <td>8</td>
    <td><span class="stage-badge stage-1quickwins">Quick Wins</span></td>
</tr>



<tr>
    <td>Network Security</td>
    <td>0.0</td>
    <td>1</td>
    <td><span class="stage-badge stage-1quickwins">Quick Wins</span></td>
</tr>


</tbody>
</table>

<!-- Only domains with data -->




<h2>5.2 Data Protection</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-1quickwins">
                Quick Wins
            </span>
        </div>
        <div class="domain-score score-medium">
            50.7
        </div>
    </div>

    
    <p>Mock LLM response for visual testing.</p>
    

    
    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    
    <tr>
        <td>Block Public Access</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:63.7%; background:#FFB300"></div>
            </div>
            63.7%
        </td>
        <td>23</td>
        <td>21</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Data Encryption at rest</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:40.9%; background:#FFB300"></div>
            </div>
            40.9%
        </td>
        <td>13</td>
        <td>24</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Encryption in transit</td>
        <td><small>3 efficient</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:30.8%; background:#F44336"></div>
            </div>
            30.8%
        </td>
        <td>8</td>
        <td>18</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Data Backups</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:82.1%; background:#4CAF50"></div>
            </div>
            82.1%
        </td>
        <td>4</td>
        <td>3</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Audit API calls</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:64.6%; background:#FFB300"></div>
            </div>
            64.6%
        </td>
        <td>10</td>
        <td>6</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Generative AI data protection with Amazon Bedrock</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>3</td>
        <td>0</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Set up multi-account management with AWS Control Tower</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:25.0%; background:#F44336"></div>
            </div>
            25.0%
        </td>
        <td>1</td>
        <td>2</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Network segmentation (VPCs) - Public/private networks</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>1</td>
        <td>0</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Analyze data security posture</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>1</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Evaluate Resilience Posture - AWS Resilience Hub</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>1</td>
        <td>partial</td>
    </tr>
    
    </tbody>
    </table>
    
</div>




<h2>5.3 Identity & Access Management</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-1quickwins">
                Quick Wins
            </span>
        </div>
        <div class="domain-score score-medium">
            46.2
        </div>
    </div>

    
    <p>Mock LLM response for visual testing.</p>
    

    
    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    
    <tr>
        <td>Audit API calls</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:64.6%; background:#FFB300"></div>
            </div>
            64.6%
        </td>
        <td>10</td>
        <td>6</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Multi-Factor Authentication</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>1</td>
        <td>0</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>IAM Data Perimeters: Conditional Access</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:78.9%; background:#4CAF50"></div>
            </div>
            78.9%
        </td>
        <td>19</td>
        <td>5</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Cleanup unused and unintended external access using IAM Access Analyzer or CIEM solutions</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:17.9%; background:#F44336"></div>
            </div>
            17.9%
        </td>
        <td>4</td>
        <td>19</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Keep your security contact details up to date</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:57.1%; background:#FFB300"></div>
            </div>
            57.1%
        </td>
        <td>2</td>
        <td>2</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Evaluate Cloud Security Posture - AWS Security Hub</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:37.5%; background:#F44336"></div>
            </div>
            37.5%
        </td>
        <td>3</td>
        <td>5</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>WAF with managed rules</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>1</td>
        <td>0</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Automate deviation correction in configurations</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:16.7%; background:#F44336"></div>
            </div>
            16.7%
        </td>
        <td>3</td>
        <td>11</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Use Temporary Credentials</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:57.7%; background:#FFB300"></div>
            </div>
            57.7%
        </td>
        <td>6</td>
        <td>4</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Instance Metadata Service (IMDS) v2</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>2</td>
        <td>0</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Cleanup risky open admin ports in Security Groups</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:89.5%; background:#4CAF50"></div>
            </div>
            89.5%
        </td>
        <td>38</td>
        <td>4</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Zero Trust Access: Risk-Based Access Control</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:51.6%; background:#FFB300"></div>
            </div>
            51.6%
        </td>
        <td>6</td>
        <td>6</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Temporary Elevated Access Management</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:14.3%; background:#F44336"></div>
            </div>
            14.3%
        </td>
        <td>1</td>
        <td>4</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Limit Network Access using Security Groups</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>1</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Root Account Protection</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>3</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Discover sensitive data with Amazon Macie</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>4</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Advanced Threat Detection</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>1</td>
        <td>partial</td>
    </tr>
    
    </tbody>
    </table>
    
</div>




<h2>5.4 Logging & Monitoring</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-1quickwins">
                Quick Wins
            </span>
        </div>
        <div class="domain-score score-medium">
            56.1
        </div>
    </div>

    
    <p>Mock LLM response for visual testing.</p>
    

    
    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    
    <tr>
        <td>Audit API calls</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:64.6%; background:#FFB300"></div>
            </div>
            64.6%
        </td>
        <td>10</td>
        <td>6</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Inventory & Configurations Monitoring</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:58.2%; background:#FFB300"></div>
            </div>
            58.2%
        </td>
        <td>39</td>
        <td>36</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Advanced security automations</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>2</td>
        <td>0</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Billing alarms for anomaly detection</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:86.1%; background:#4CAF50"></div>
            </div>
            86.1%
        </td>
        <td>12</td>
        <td>2</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Security investigations - Root cause analysis with Amazon Detective</td>
        <td><small>3 efficient</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:37.5%; background:#F44336"></div>
            </div>
            37.5%
        </td>
        <td>1</td>
        <td>2</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>VPC Flow Logs Analysis</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:27.9%; background:#F44336"></div>
            </div>
            27.9%
        </td>
        <td>7</td>
        <td>19</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Select the region(s) where you want to operate and block the rest</td>
        <td><small>1 quickwins</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:18.5%; background:#F44336"></div>
            </div>
            18.5%
        </td>
        <td>2</td>
        <td>9</td>
        <td>assessed</td>
    </tr>
    
    </tbody>
    </table>
    
</div>




<h2>5.5 Resilience</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-1quickwins">
                Quick Wins
            </span>
        </div>
        <div class="domain-score score-medium">
            59.1
        </div>
    </div>

    
    <p>Mock LLM response for visual testing.</p>
    

    
    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    
    <tr>
        <td>IAM Data Perimeters: Conditional Access</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:78.9%; background:#4CAF50"></div>
            </div>
            78.9%
        </td>
        <td>19</td>
        <td>5</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Least Privilege Review: Set up right-size permissions in roles</td>
        <td><small>3 efficient</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:87.8%; background:#4CAF50"></div>
            </div>
            87.8%
        </td>
        <td>14</td>
        <td>2</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Achieve redundancy using multiple Availability Zones</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:33.0%; background:#F44336"></div>
            </div>
            33.0%
        </td>
        <td>11</td>
        <td>21</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Don't store secrets in code - Remove secrets from code</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:60.0%; background:#FFB300"></div>
            </div>
            60.0%
        </td>
        <td>7</td>
        <td>5</td>
        <td>assessed</td>
    </tr>
    
    <tr>
        <td>Manage vulnerabilities in your infrastructure and perform pentesting</td>
        <td><small>2 foundational</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:80.0%; background:#4CAF50"></div>
            </div>
            80.0%
        </td>
        <td>4</td>
        <td>1</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Automate evidence gathering for compliance audit reports</td>
        <td><small>4 optimized</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:100.0%; background:#4CAF50"></div>
            </div>
            100.0%
        </td>
        <td>1</td>
        <td>0</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Advanced WAF protection with Custom Rules</td>
        <td><small>3 efficient</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:33.3%; background:#F44336"></div>
            </div>
            33.3%
        </td>
        <td>1</td>
        <td>2</td>
        <td>partial</td>
    </tr>
    
    <tr>
        <td>Tagging Strategy</td>
        <td><small>3 efficient</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>2</td>
        <td>partial</td>
    </tr>
    
    </tbody>
    </table>
    
</div>




<h2>5.6 Network Security</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-1quickwins">
                Quick Wins
            </span>
        </div>
        <div class="domain-score score-low">
            0.0
        </div>
    </div>

    
    <p>Mock LLM response for visual testing.</p>
    

    
    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    
    <tr>
        <td>Advanced DDoS Mitigation (Layer 7) - AWS Shield</td>
        <td><small>3 efficient</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:0.0%; background:#F44336"></div>
            </div>
            0.0%
        </td>
        <td>0</td>
        <td>6</td>
        <td>partial</td>
    </tr>
    
    </tbody>
    </table>
    
</div>



<!-- Scope not covered -->
<h2>Phạm vi Chưa Được Đánh giá</h2>
<p>Các lĩnh vực sau chưa nằm trong phạm vi quét:</p>
<ul>











</ul>

<p>Mock LLM response for visual testing.</p>



<!-- ============================================================ -->
<!-- REMEDIATION EXECUTION (Section 5/6/7 depending on mode)       -->
<!-- ============================================================ -->

<h1>6. Chi tiết thực thi khắc phục</h1>






<h2>6.1 Khắc phục thành công</h2>



<p><em>Không có khắc phục tự động thành công.</em></p>


<h2>6.2 Khắc phục thất bại</h2>



<p><em>Không ghi nhận lỗi trong quá trình khắc phục tự động.</em></p>


<h2>6.3 Yêu cầu khắc phục thủ công</h2>

<p><em>Không ghi nhận yêu cầu khắc phục thủ công trong phạm vi đánh giá này.</em></p>




<!-- ============================================================ -->
<!-- POST-REMEDIATION (Enhanced — ALL MODES)                       -->
<!-- ============================================================ -->


<h1>7. Hậu Khắc phục</h1>


<!-- 8.1 Verification Table -->
<h2>7.1 Kết quả Xác minh</h2>
<p>Bảng dưới đây thể hiện kết quả xác minh cho từng finding sau khi
   thực hiện khắc phục. Mỗi finding được kiểm tra lại (re-scan) để
   xác nhận trạng thái thực tế.</p>

<p><em>250 findings không thay đổi trạng thái đã được ẩn.</em></p>


<table class="styled-table">
<thead>
<tr><th>STT</th><th>Finding</th><th>Service</th><th>Severity</th><th>Trước</th><th>Sau</th><th>Kết quả</th></tr>
</thead>
<tbody>

<tr class="verification-pass">
    <td>251</td>
    <td>Check: Ecr Repositories Tag Immutability</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-pass">
    <td>252</td>
    <td>Check: Ecs Cluster Container Insights Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-pass">
    <td>253</td>
    <td>Check: Ecs Service Fargate Latest Platform Version</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-pass">
    <td>254</td>
    <td>Check: Ecs Service No Assign Public Ip</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-pass">
    <td>255</td>
    <td>Check: Ecs Task Definitions Containers Readonly Access</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-pass">
    <td>256</td>
    <td>Check: Ecs Task Definitions Host Namespace Not Shared</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>PASS</td>
    <td>
        
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>257</td>
    <td>Check: Ecs Task Definitions Host Networking Mode Users</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>258</td>
    <td>Check: Ecs Task Definitions Logging Block Mode</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>259</td>
    <td>Check: Ecs Task Definitions Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>260</td>
    <td>Check: Ecs Task Definitions No Environment Secrets</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>261</td>
    <td>Check: Ecs Task Definitions No Privileged Containers</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>262</td>
    <td>Check: Ecs Task Set No Assign Public Ip</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>263</td>
    <td>Check: Efs Access Point Enforce Root Directory</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>264</td>
    <td>Check: Efs Access Point Enforce User Identity</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>265</td>
    <td>Check: Efs Encryption At Rest Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>266</td>
    <td>Check: Efs Have Backup Enabled</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>267</td>
    <td>Check: Efs Mount Target Not Publicly Accessible</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>268</td>
    <td>Check: Efs Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>269</td>
    <td>Check: Efs Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>270</td>
    <td>Check: Eks Cluster Deletion Protection Enabled</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>271</td>
    <td>Check: Eks Cluster Kms Cmk Encryption In Secrets Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>272</td>
    <td>Check: Eks Cluster Network Policy Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>273</td>
    <td>Check: Eks Cluster Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>274</td>
    <td>Check: Eks Control Plane Logging All Types Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>275</td>
    <td>Check: Elasticache Redis Cluster Automatic Failover Enabled</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>276</td>
    <td>Check: Elasticache Redis Cluster Backup Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>277</td>
    <td>Check: Elasticache Redis Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>278</td>
    <td>Check: Elasticache Redis Cluster Rest Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>279</td>
    <td>Check: Elasticbeanstalk Environment Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>280</td>
    <td>Check: Elasticbeanstalk Environment Enhanced Health Reporting</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>281</td>
    <td>Check: Elb Cross Zone Load Balancing Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>282</td>
    <td>Check: Elb Desync Mitigation Mode</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>283</td>
    <td>Check: Elb Insecure Ssl Ciphers</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>284</td>
    <td>Check: Elb Internet Facing</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>285</td>
    <td>Check: Elb Is In Multiple Az</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>286</td>
    <td>Check: Elb Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>287</td>
    <td>Check: Elb Ssl Listeners</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>288</td>
    <td>Check: Elb Ssl Listeners Use Acm Certificate</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>289</td>
    <td>Check: Elbv2 Cross Zone Load Balancing Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>290</td>
    <td>Check: Elbv2 Insecure Ssl Ciphers</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>291</td>
    <td>Check: Elbv2 Internet Facing</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>292</td>
    <td>Check: Elbv2 Is In Multiple Az</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>293</td>
    <td>Check: Elbv2 Logging Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>294</td>
    <td>Check: Elbv2 Nlb Tls Termination Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>295</td>
    <td>Check: Elbv2 Ssl Listeners</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>296</td>
    <td>Check: Elbv2 Waf Acl Attached</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>297</td>
    <td>Check: Emr Cluster Account Public Block Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>298</td>
    <td>Check: Emr Cluster Publicly Accesible</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>299</td>
    <td>Check: Eventbridge Schema Registry Cross Account Access</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>300</td>
    <td>Check: Firehose Stream Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>301</td>
    <td>Check: Fsx File System Copy Tags To Backups Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>302</td>
    <td>Check: Fsx File System Copy Tags To Volumes Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>303</td>
    <td>Check: Fsx Windows File System Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>304</td>
    <td>Check: Glue Data Catalogs Connection Passwords Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>305</td>
    <td>Check: Glue Data Catalogs Metadata Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>306</td>
    <td>Check: Glue Data Catalogs Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>307</td>
    <td>Check: Glue Database Connections Ssl Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>308</td>
    <td>Check: Glue Development Endpoints Cloudwatch Logs Encryption Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>309</td>
    <td>Check: Glue Development Endpoints Job Bookmark Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>310</td>
    <td>Check: Glue Development Endpoints S3 Encryption Enabled</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>311</td>
    <td>Check: Glue Etl Jobs Amazon S3 Encryption Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>312</td>
    <td>Check: Glue Etl Jobs Cloudwatch Logs Encryption Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>313</td>
    <td>Check: Glue Etl Jobs Job Bookmark Encryption Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>314</td>
    <td>Check: Glue Etl Jobs Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>315</td>
    <td>Check: Glue Ml Transform Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>316</td>
    <td>Check: Guardduty Centrally Managed</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>317</td>
    <td>Check: Guardduty Ec2 Malware Protection Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>318</td>
    <td>Check: Guardduty Eks Audit Log Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>319</td>
    <td>Check: Guardduty Eks Runtime Monitoring Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>320</td>
    <td>Check: Guardduty Is Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>321</td>
    <td>Check: Guardduty Lambda Protection Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>322</td>
    <td>Check: Guardduty No High Severity Findings</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>323</td>
    <td>Check: Guardduty Rds Protection Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>324</td>
    <td>Check: Guardduty S3 Protection Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>325</td>
    <td>Check: Iam Administrator Access With Mfa</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>326</td>
    <td>Check: Iam Avoid Root Usage</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>327</td>
    <td>Check: Iam Aws Attached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>328</td>
    <td>Check: Iam Check Saml Providers Sts</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>329</td>
    <td>Check: Iam Customer Attached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>330</td>
    <td>Check: Iam Customer Unattached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>331</td>
    <td>Check: Iam Group Administrator Access Policy</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>332</td>
    <td>Check: Iam Inline Policy Allows Privilege Escalation</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>333</td>
    <td>Check: Iam Inline Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>334</td>
    <td>Check: Iam Inline Policy No Full Access To Cloudtrail</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>335</td>
    <td>Check: Iam Inline Policy No Full Access To Kms</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>336</td>
    <td>Check: Iam No Custom Policy Permissive Role Assumption</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>337</td>
    <td>Check: Iam No Expired Server Certificates Stored</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>338</td>
    <td>Check: Iam No Root Access Key</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>339</td>
    <td>Check: Iam Password Policy Expires Passwords Within 90 Days Or Less</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>340</td>
    <td>Check: Iam Password Policy Lowercase</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>341</td>
    <td>Check: Iam Password Policy Minimum Length 14</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>342</td>
    <td>Check: Iam Password Policy Number</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>343</td>
    <td>Check: Iam Password Policy Reuse 24</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>344</td>
    <td>Check: Iam Password Policy Symbol</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>345</td>
    <td>Check: Iam Password Policy Uppercase</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>346</td>
    <td>Check: Iam Policy Allows Privilege Escalation</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>347</td>
    <td>Check: Iam Policy Attached Only To Group Or Roles</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>348</td>
    <td>Check: Iam Policy Cloudshell Admin Not Attached</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>349</td>
    <td>Check: Iam Policy No Full Access To Cloudtrail</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>350</td>
    <td>Check: Iam Policy No Full Access To Kms</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>351</td>
    <td>Check: Iam Role Administratoraccess Policy</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>352</td>
    <td>Check: Iam Role Cross Account Readonlyaccess Policy</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>353</td>
    <td>Check: Iam Role Cross Service Confused Deputy Prevention</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>354</td>
    <td>Check: Iam Root Credentials Management Enabled</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>355</td>
    <td>Check: Iam Root Hardware Mfa Enabled</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>356</td>
    <td>Check: Iam Root Mfa Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>357</td>
    <td>Check: Iam Rotate Access Key 90 Days</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>358</td>
    <td>Check: Iam Securityaudit Role Created</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>359</td>
    <td>Check: Iam Support Role Created</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>360</td>
    <td>Check: Iam User Accesskey Unused</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>361</td>
    <td>Check: Iam User Administrator Access Policy</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>362</td>
    <td>Check: Iam User Console Access Unused</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>363</td>
    <td>Check: Iam User Hardware Mfa Enabled</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>364</td>
    <td>Check: Iam User Mfa Enabled Console Access</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>365</td>
    <td>Check: Iam User No Setup Initial Access Key</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>366</td>
    <td>Check: Iam User Two Active Access Key</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>367</td>
    <td>Check: Iam User With Temporary Credentials</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>368</td>
    <td>Check: Inspector2 Active Findings Exist</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>369</td>
    <td>Check: Inspector2 Is Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>370</td>
    <td>Check: Kafka Cluster Encryption At Rest Uses Cmk</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>371</td>
    <td>Check: Kafka Cluster Enhanced Monitoring Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>372</td>
    <td>Check: Kafka Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>373</td>
    <td>Check: Kafka Cluster Is Public</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>374</td>
    <td>Check: Kafka Connector In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>375</td>
    <td>Check: Kinesis Stream Data Retention Period</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>376</td>
    <td>Check: Kinesis Stream Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>377</td>
    <td>Check: Kms Cmk Are Used</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>378</td>
    <td>Check: Kms Cmk Not Deleted Unintentionally</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>379</td>
    <td>Check: Kms Cmk Not Multi Region</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>380</td>
    <td>Check: Kms Cmk Rotation Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>381</td>
    <td>Check: Kms Key Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>382</td>
    <td>Check: Lightsail Instance Automated Snapshots</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>383</td>
    <td>Check: Lightsail Instance Public</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>384</td>
    <td>Check: Macie Automated Sensitive Data Discovery Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>385</td>
    <td>Check: Macie Is Enabled</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>386</td>
    <td>Check: Mq Broker Active Deployment Mode</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>387</td>
    <td>Check: Mq Broker Cluster Deployment Mode</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>388</td>
    <td>Check: Mq Broker Logging Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>389</td>
    <td>Check: Mq Broker Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>390</td>
    <td>Check: Neptune Cluster Backup Enabled</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>391</td>
    <td>Check: Neptune Cluster Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>392</td>
    <td>Check: Neptune Cluster Deletion Protection</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>393</td>
    <td>Check: Neptune Cluster Iam Authentication Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>394</td>
    <td>Check: Neptune Cluster Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>395</td>
    <td>Check: Neptune Cluster Multi Az</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>396</td>
    <td>Check: Neptune Cluster Public Snapshot</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>397</td>
    <td>Check: Neptune Cluster Snapshot Encrypted</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>398</td>
    <td>Check: Neptune Cluster Storage Encrypted</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>399</td>
    <td>Check: Neptune Cluster Uses Public Subnet</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>400</td>
    <td>Check: Networkfirewall Deletion Protection</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>401</td>
    <td>Check: Networkfirewall In All Vpc</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>402</td>
    <td>Check: Networkfirewall Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>403</td>
    <td>Check: Networkfirewall Multi Az</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>404</td>
    <td>Check: Networkfirewall Policy Rule Group Associated</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>405</td>
    <td>Check: Opensearch Service Domains Access Control Enabled</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>406</td>
    <td>Check: Opensearch Service Domains Audit Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>407</td>
    <td>Check: Opensearch Service Domains Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>408</td>
    <td>Check: Opensearch Service Domains Encryption At Rest Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>409</td>
    <td>Check: Opensearch Service Domains Fault Tolerant Data Nodes</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>410</td>
    <td>Check: Opensearch Service Domains Fault Tolerant Master Nodes</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>411</td>
    <td>Check: Opensearch Service Domains Https Communications Enforced</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>412</td>
    <td>Check: Opensearch Service Domains Node To Node Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>413</td>
    <td>Check: Opensearch Service Domains Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>414</td>
    <td>Check: Opensearch Service Domains Updated To The Latest Service Software Version</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>415</td>
    <td>Check: Opensearch Service Domains Use Cognito Authentication For Kibana</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>416</td>
    <td>Check: Organizations Account Part Of Organizations</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>417</td>
    <td>Check: Organizations Delegated Administrators</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>418</td>
    <td>Check: Organizations Opt Out Ai Services Policy</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>419</td>
    <td>Check: Organizations Scp Check Deny Regions</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>420</td>
    <td>Check: Organizations Tags Policies Enabled And Attached</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>421</td>
    <td>Check: Rds Cluster Backtrack Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>422</td>
    <td>Check: Rds Cluster Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>423</td>
    <td>Check: Rds Cluster Critical Event Subscription</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>424</td>
    <td>Check: Rds Cluster Iam Authentication Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>425</td>
    <td>Check: Rds Cluster Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>426</td>
    <td>Check: Rds Cluster Minor Version Upgrade Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>427</td>
    <td>Check: Rds Cluster Multi Az</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>428</td>
    <td>Check: Rds Cluster Non Default Port</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>429</td>
    <td>Check: Rds Cluster Storage Encrypted</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>430</td>
    <td>Check: Rds Instance Certificate Expiration</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>431</td>
    <td>Check: Rds Instance Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>432</td>
    <td>Check: Rds Instance Critical Event Subscription</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>433</td>
    <td>Check: Rds Instance Enhanced Monitoring Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>434</td>
    <td>Check: Rds Instance Event Subscription Parameter Groups</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>435</td>
    <td>Check: Rds Instance Event Subscription Security Groups</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>436</td>
    <td>Check: Rds Instance Iam Authentication Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>437</td>
    <td>Check: Rds Instance Inside Vpc</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>438</td>
    <td>Check: Rds Instance Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>439</td>
    <td>Check: Rds Instance Minor Version Upgrade Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>440</td>
    <td>Check: Rds Instance Multi Az</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>441</td>
    <td>Check: Rds Instance No Public Access</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>442</td>
    <td>Check: Rds Instance Non Default Port</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>443</td>
    <td>Check: Rds Instance Storage Encrypted</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>444</td>
    <td>Check: Rds Instance Transport Encrypted</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>445</td>
    <td>Check: Rds Snapshots Encrypted</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>446</td>
    <td>Check: Rds Snapshots Public Access</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>447</td>
    <td>Check: Redshift Cluster Audit Logging</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>448</td>
    <td>Check: Redshift Cluster Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>449</td>
    <td>Check: Redshift Cluster Enhanced Vpc Routing</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>450</td>
    <td>Check: Redshift Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>451</td>
    <td>Check: Redshift Cluster Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>452</td>
    <td>Check: Redshift Cluster Non Default Database Name</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>453</td>
    <td>Check: Redshift Cluster Non Default Username</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>454</td>
    <td>Check: Redshift Cluster Public Access</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>455</td>
    <td>Check: Route53 Dangling Ip Subdomain Takeover</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>456</td>
    <td>Check: Route53 Public Hosted Zones Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>457</td>
    <td>Check: Sagemaker Endpoint Config Prod Variant Instances</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>458</td>
    <td>Check: Sagemaker Notebook Instance Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>459</td>
    <td>Check: Sagemaker Notebook Instance Root Access Disabled</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>460</td>
    <td>Check: Sagemaker Training Jobs Intercontainer Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>461</td>
    <td>Check: Sagemaker Training Jobs Volume And Output Encryption Enabled</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>462</td>
    <td>Check: Secretsmanager Automatic Rotation Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>463</td>
    <td>Check: Secretsmanager Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>464</td>
    <td>Check: Secretsmanager Secret Rotated Periodically</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>465</td>
    <td>Check: Securityhub Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>466</td>
    <td>Check: Servicecatalog Portfolio Shared Within Organization Only</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>467</td>
    <td>Check: Ses Identity Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>468</td>
    <td>Check: Shield Advanced Protection In Associated Elastic Ips</td>
    <td>network</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>469</td>
    <td>Check: Shield Advanced Protection In Classic Load Balancers</td>
    <td>network</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>470</td>
    <td>Check: Shield Advanced Protection In Cloudfront Distributions</td>
    <td>network</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>471</td>
    <td>Check: Shield Advanced Protection In Global Accelerators</td>
    <td>network</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>472</td>
    <td>Check: Shield Advanced Protection In Internet Facing Load Balancers</td>
    <td>network</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>473</td>
    <td>Check: Shield Advanced Protection In Route53 Hosted Zones</td>
    <td>network</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>474</td>
    <td>Check: Sns Subscription Not Using Http Endpoints</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>475</td>
    <td>Check: Sns Topics Kms Encryption At Rest Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>476</td>
    <td>Check: Sns Topics Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>477</td>
    <td>Check: Sqs Queues Not Publicly Accessible</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>478</td>
    <td>Check: Sqs Queues Server Side Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>479</td>
    <td>Check: Ssm Document Secrets</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>480</td>
    <td>Check: Ssmincidents Enabled With Plans</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>481</td>
    <td>Check: Stepfunctions Statemachine Logging Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>482</td>
    <td>Check: Storagegateway Fileshare Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>483</td>
    <td>Check: Storagegateway Gateway Fault Tolerant</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>484</td>
    <td>Check: Transfer Server In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>485</td>
    <td>Check: Trustedadvisor Errors And Warnings</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>486</td>
    <td>Check: Trustedadvisor Premium Support Plan Subscribed</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>487</td>
    <td>Check: Vpc Different Regions</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>488</td>
    <td>Check: Vpc Endpoint For Ec2 Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>489</td>
    <td>Check: Vpc Endpoint Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>490</td>
    <td>Check: Vpc Flow Logs Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>491</td>
    <td>Check: Vpc Peering Routing Tables With Least Privilege</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>492</td>
    <td>Check: Vpc Subnet Different Az</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>493</td>
    <td>Check: Vpc Vpn Connection Tunnels Up</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>494</td>
    <td>Check: Waf Global Rule With Conditions</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>495</td>
    <td>Check: Waf Global Webacl Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>496</td>
    <td>Check: Waf Regional Rule With Conditions</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>497</td>
    <td>Check: Wafv2 Webacl Logging Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>498</td>
    <td>Check: Wafv2 Webacl Rule Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>499</td>
    <td>Check: Wafv2 Webacl With Rules</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>500</td>
    <td>Check: Wellarchitected Workload No High Or Medium Risks</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>501</td>
    <td>Check: Workspaces Volume Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        
    </td>
</tr>

<tr class="verification-fail">
    <td>502</td>
    <td>Check: Workspaces Vpc 2Private 1Public Subnets Nat</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td>FAIL</td>
    <td>FAIL</td>
    <td>
        
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        
    </td>
</tr>

</tbody>
</table>

<!-- 8.2 Fix Metrics -->
<h2>7.2 Hiệu quả Khắc phục</h2>


<div style="text-align:center; margin: 20px 0;">
    <div class="metric-card">
        <div class="metric-value" style="color:#2E7D32">2.4%</div>
        <div class="metric-label">Tỷ lệ Khắc phục</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">6/252</div>
        <div class="metric-label">Findings Đã Fix</div>
    </div>
    <div class="metric-card">
        <div class="metric-value" style="color:#1565C0">3.5%</div>
        <div class="metric-label">Auto-fix Thành công</div>
    </div>
    <div class="metric-card">
        <div class="metric-value score-low">
            246
        </div>
        <div class="metric-label">Findings Còn lại</div>
    </div>
</div>

<table class="styled-table">
<thead><tr><th>Chỉ số</th><th>Trước Khắc phục</th><th>Sau Khắc phục</th><th>Thay đổi</th></tr></thead>
<tbody>
<tr>
    <td>Findings PASS</td>
    <td>250</td>
    <td>256</td>
    <td class="delta-positive">+6</td>
</tr>
<tr>
    <td>Findings FAIL</td>
    <td>252</td>
    <td>246</td>
    <td class="delta-positive">-6</td>
</tr>
<tr>
    <td>Pass Rate</td>
    <td>49.8%</td>
    <td>51.0%</td>
    <td class="delta-positive">
        +1.2%
    </td>
</tr>
</tbody>
</table>


<!-- 8.3 Maturity Delta (only for full/partial with delta) -->

<h2>7.3 Tác động lên Mức độ Trưởng thành</h2>

<div class="maturity-banner">
    <strong>Điểm Trưởng thành:</strong>
    50.2
    &rarr;
    <strong>50.7</strong>
    <span class="delta-positive">
        (+0.5)
    </span>
    
</div>


<div style="text-align:center">
    <img src="charts/maturity_delta.png" style="max-width:700px">
</div>


<!-- Domain delta table -->
<table class="styled-table">
<thead><tr><th>Lĩnh vực</th><th>Trước</th><th>Sau</th><th>Thay đổi</th><th>Stage</th></tr></thead>
<tbody>

<tr>
    <td>Data Protection</td>
    <td>50.7</td>
    <td>50.9</td>
    <td class="delta-positive">
        +0.2
    </td>
    <td>
        
            1 quickwins
        
    </td>
</tr>

<tr>
    <td>Identity & Access Management</td>
    <td>46.2</td>
    <td>47.1</td>
    <td class="delta-positive">
        +0.9
    </td>
    <td>
        
            1 quickwins
        
    </td>
</tr>

<tr>
    <td>Logging & Monitoring</td>
    <td>56.1</td>
    <td>56.6</td>
    <td class="delta-positive">
        +0.5
    </td>
    <td>
        
            1 quickwins
        
    </td>
</tr>

<tr>
    <td>Resilience</td>
    <td>59.1</td>
    <td>59.1</td>
    <td class="delta-zero">
        0.0
    </td>
    <td>
        
            1 quickwins
        
    </td>
</tr>

<tr>
    <td>Network Security</td>
    <td>0.0</td>
    <td>0.0</td>
    <td class="delta-zero">
        0.0
    </td>
    <td>
        
            1 quickwins
        
    </td>
</tr>

</tbody>
</table>


<h3>Năng lực Được Cải thiện</h3>
<table class="styled-table">
<thead><tr><th>Năng lực</th><th>Lĩnh vực</th><th>Trước</th><th>Sau</th><th>Ghi chú</th></tr></thead>
<tbody>

<tr>
    <td>Block Public Access</td>
    <td>data_protection</td>
    <td>63.7%</td>
    <td>65.3%</td>
    <td>
        
            <span class="delta-positive">+1.6%</span>
        
    </td>
</tr>

<tr>
    <td>Zero Trust Access: Risk-Based Access Control</td>
    <td>identity_access</td>
    <td>51.6%</td>
    <td>61.3%</td>
    <td>
        
            <span class="delta-positive">+9.7%</span>
        
    </td>
</tr>

<tr>
    <td>Automate deviation correction in configurations</td>
    <td>identity_access</td>
    <td>16.7%</td>
    <td>22.2%</td>
    <td>
        
            <span class="delta-positive">+5.5%</span>
        
    </td>
</tr>

<tr>
    <td>Inventory & Configurations Monitoring</td>
    <td>logging_monitoring</td>
    <td>58.2%</td>
    <td>61.4%</td>
    <td>
        
            <span class="delta-positive">+3.2%</span>
        
    </td>
</tr>

</tbody>
</table>





<!-- End maturity delta section -->

<!-- 8.4 Residual Risks -->
<h2>7.4 Rủi ro Còn lại</h2>



<p>Tổng cộng <strong>246</strong> findings vẫn còn FAIL sau khắc phục:</p>
<table class="styled-table">
<thead><tr><th>Mức độ</th><th>Số lượng</th></tr></thead>
<tbody>


<tr>
    <td class="severity-critical">CRITICAL</td>
    <td>62</td>
</tr>



<tr>
    <td class="severity-high">HIGH</td>
    <td>62</td>
</tr>



<tr>
    <td class="severity-medium">MEDIUM</td>
    <td>61</td>
</tr>



<tr>
    <td class="severity-low">LOW</td>
    <td>61</td>
</tr>


</tbody>
</table>


<h3>Khắc phục Tự động Thất bại (164)</h3>
<p>Hệ thống đã thử khắc phục tự động nhưng không thành công. Cần kiểm tra lại cấu hình hoặc xử lý thủ công.</p>
<table class="styled-table">
<thead><tr><th>Finding</th><th>Service</th><th>Severity</th><th>Resource</th></tr></thead>
<tbody>

<tr>
    <td>Check: Ecs Task Definitions Host Networking Mode Users</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-256</small></td>
</tr>

<tr>
    <td>Check: Ecs Task Definitions Logging Block Mode</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-257</small></td>
</tr>

<tr>
    <td>Check: Ecs Task Definitions No Environment Secrets</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-259</small></td>
</tr>

<tr>
    <td>Check: Ecs Task Definitions No Privileged Containers</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-260</small></td>
</tr>

<tr>
    <td>Check: Efs Access Point Enforce Root Directory</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-262</small></td>
</tr>

<tr>
    <td>Check: Efs Access Point Enforce User Identity</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-263</small></td>
</tr>

<tr>
    <td>Check: Efs Have Backup Enabled</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-265</small></td>
</tr>

<tr>
    <td>Check: Efs Mount Target Not Publicly Accessible</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-266</small></td>
</tr>

<tr>
    <td>Check: Efs Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-268</small></td>
</tr>

<tr>
    <td>Check: Eks Cluster Deletion Protection Enabled</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-269</small></td>
</tr>

<tr>
    <td>Check: Eks Cluster Network Policy Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-271</small></td>
</tr>

<tr>
    <td>Check: Eks Cluster Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-272</small></td>
</tr>

<tr>
    <td>Check: Elasticache Redis Cluster Automatic Failover Enabled</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-274</small></td>
</tr>

<tr>
    <td>Check: Elasticache Redis Cluster Backup Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-275</small></td>
</tr>

<tr>
    <td>Check: Elasticache Redis Cluster Rest Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-277</small></td>
</tr>

<tr>
    <td>Check: Elasticbeanstalk Environment Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-278</small></td>
</tr>

<tr>
    <td>Check: Elb Cross Zone Load Balancing Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-280</small></td>
</tr>

<tr>
    <td>Check: Elb Desync Mitigation Mode</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-281</small></td>
</tr>

<tr>
    <td>Check: Elb Internet Facing</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-283</small></td>
</tr>

<tr>
    <td>Check: Elb Is In Multiple Az</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-284</small></td>
</tr>

<tr>
    <td>Check: Elb Ssl Listeners</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-286</small></td>
</tr>

<tr>
    <td>Check: Elb Ssl Listeners Use Acm Certificate</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-287</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Insecure Ssl Ciphers</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-289</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Internet Facing</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-290</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Logging Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-292</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Nlb Tls Termination Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-293</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Waf Acl Attached</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-295</small></td>
</tr>

<tr>
    <td>Check: Emr Cluster Account Public Block Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-296</small></td>
</tr>

<tr>
    <td>Check: Eventbridge Schema Registry Cross Account Access</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-298</small></td>
</tr>

<tr>
    <td>Check: Firehose Stream Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-299</small></td>
</tr>

<tr>
    <td>Check: Fsx File System Copy Tags To Volumes Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-301</small></td>
</tr>

<tr>
    <td>Check: Fsx Windows File System Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-302</small></td>
</tr>

<tr>
    <td>Check: Glue Data Catalogs Metadata Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-304</small></td>
</tr>

<tr>
    <td>Check: Glue Data Catalogs Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-305</small></td>
</tr>

<tr>
    <td>Check: Glue Development Endpoints Cloudwatch Logs Encryption Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-307</small></td>
</tr>

<tr>
    <td>Check: Glue Development Endpoints Job Bookmark Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-308</small></td>
</tr>

<tr>
    <td>Check: Glue Etl Jobs Amazon S3 Encryption Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-310</small></td>
</tr>

<tr>
    <td>Check: Glue Etl Jobs Cloudwatch Logs Encryption Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-311</small></td>
</tr>

<tr>
    <td>Check: Glue Etl Jobs Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-313</small></td>
</tr>

<tr>
    <td>Check: Glue Ml Transform Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-314</small></td>
</tr>

<tr>
    <td>Check: Guardduty Ec2 Malware Protection Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-316</small></td>
</tr>

<tr>
    <td>Check: Guardduty Eks Audit Log Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-317</small></td>
</tr>

<tr>
    <td>Check: Guardduty Is Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-319</small></td>
</tr>

<tr>
    <td>Check: Guardduty Lambda Protection Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-320</small></td>
</tr>

<tr>
    <td>Check: Guardduty Rds Protection Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-322</small></td>
</tr>

<tr>
    <td>Check: Guardduty S3 Protection Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-323</small></td>
</tr>

<tr>
    <td>Check: Iam Avoid Root Usage</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-325</small></td>
</tr>

<tr>
    <td>Check: Iam Aws Attached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-326</small></td>
</tr>

<tr>
    <td>Check: Iam Customer Attached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-328</small></td>
</tr>

<tr>
    <td>Check: Iam Customer Unattached Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-329</small></td>
</tr>

<tr>
    <td>Check: Iam Inline Policy Allows Privilege Escalation</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-331</small></td>
</tr>

<tr>
    <td>Check: Iam Inline Policy No Administrative Privileges</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-332</small></td>
</tr>

<tr>
    <td>Check: Iam Inline Policy No Full Access To Kms</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-334</small></td>
</tr>

<tr>
    <td>Check: Iam No Custom Policy Permissive Role Assumption</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-335</small></td>
</tr>

<tr>
    <td>Check: Iam No Root Access Key</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-337</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Expires Passwords Within 90 Days Or Less</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-338</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Minimum Length 14</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-340</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Number</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-341</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Symbol</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-343</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Uppercase</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-344</small></td>
</tr>

<tr>
    <td>Check: Iam Policy Attached Only To Group Or Roles</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-346</small></td>
</tr>

<tr>
    <td>Check: Iam Policy Cloudshell Admin Not Attached</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-347</small></td>
</tr>

<tr>
    <td>Check: Iam Policy No Full Access To Kms</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-349</small></td>
</tr>

<tr>
    <td>Check: Iam Role Administratoraccess Policy</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-350</small></td>
</tr>

<tr>
    <td>Check: Iam Role Cross Service Confused Deputy Prevention</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-352</small></td>
</tr>

<tr>
    <td>Check: Iam Root Credentials Management Enabled</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-353</small></td>
</tr>

<tr>
    <td>Check: Iam Root Mfa Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-355</small></td>
</tr>

<tr>
    <td>Check: Iam Rotate Access Key 90 Days</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-356</small></td>
</tr>

<tr>
    <td>Check: Iam Support Role Created</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-358</small></td>
</tr>

<tr>
    <td>Check: Iam User Accesskey Unused</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-359</small></td>
</tr>

<tr>
    <td>Check: Iam User Console Access Unused</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-361</small></td>
</tr>

<tr>
    <td>Check: Iam User Hardware Mfa Enabled</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-362</small></td>
</tr>

<tr>
    <td>Check: Iam User No Setup Initial Access Key</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-364</small></td>
</tr>

<tr>
    <td>Check: Iam User Two Active Access Key</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-365</small></td>
</tr>

<tr>
    <td>Check: Inspector2 Active Findings Exist</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-367</small></td>
</tr>

<tr>
    <td>Check: Inspector2 Is Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-368</small></td>
</tr>

<tr>
    <td>Check: Kafka Cluster Enhanced Monitoring Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-370</small></td>
</tr>

<tr>
    <td>Check: Kafka Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-371</small></td>
</tr>

<tr>
    <td>Check: Kafka Connector In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-373</small></td>
</tr>

<tr>
    <td>Check: Kinesis Stream Data Retention Period</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-374</small></td>
</tr>

<tr>
    <td>Check: Kms Cmk Are Used</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-376</small></td>
</tr>

<tr>
    <td>Check: Kms Cmk Not Deleted Unintentionally</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-377</small></td>
</tr>

<tr>
    <td>Check: Kms Cmk Rotation Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-379</small></td>
</tr>

<tr>
    <td>Check: Kms Key Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-380</small></td>
</tr>

<tr>
    <td>Check: Lightsail Instance Public</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-382</small></td>
</tr>

<tr>
    <td>Check: Macie Automated Sensitive Data Discovery Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-383</small></td>
</tr>

<tr>
    <td>Check: Mq Broker Active Deployment Mode</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-385</small></td>
</tr>

<tr>
    <td>Check: Mq Broker Cluster Deployment Mode</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-386</small></td>
</tr>

<tr>
    <td>Check: Mq Broker Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-388</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Backup Enabled</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-389</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Deletion Protection</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-391</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Iam Authentication Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-392</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Multi Az</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-394</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Public Snapshot</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-395</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Storage Encrypted</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-397</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Uses Public Subnet</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-398</small></td>
</tr>

<tr>
    <td>Check: Networkfirewall In All Vpc</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-400</small></td>
</tr>

<tr>
    <td>Check: Networkfirewall Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-401</small></td>
</tr>

<tr>
    <td>Check: Networkfirewall Policy Rule Group Associated</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-403</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Access Control Enabled</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-404</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-406</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Encryption At Rest Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-407</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Fault Tolerant Master Nodes</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-409</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Https Communications Enforced</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-410</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-412</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Updated To The Latest Service Software Version</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-413</small></td>
</tr>

<tr>
    <td>Check: Organizations Account Part Of Organizations</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-415</small></td>
</tr>

<tr>
    <td>Check: Organizations Delegated Administrators</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-416</small></td>
</tr>

<tr>
    <td>Check: Organizations Scp Check Deny Regions</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-418</small></td>
</tr>

<tr>
    <td>Check: Organizations Tags Policies Enabled And Attached</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-419</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-421</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Critical Event Subscription</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-422</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-424</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Minor Version Upgrade Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-425</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Non Default Port</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-427</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Storage Encrypted</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-428</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-430</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Critical Event Subscription</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-431</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Event Subscription Parameter Groups</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-433</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Event Subscription Security Groups</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-434</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Inside Vpc</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-436</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-437</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Multi Az</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-439</small></td>
</tr>

<tr>
    <td>Check: Rds Instance No Public Access</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-440</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Storage Encrypted</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-442</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Transport Encrypted</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-443</small></td>
</tr>

<tr>
    <td>Check: Rds Snapshots Public Access</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-445</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Audit Logging</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-446</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Enhanced Vpc Routing</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-448</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-449</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Non Default Database Name</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-451</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Non Default Username</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-452</small></td>
</tr>

<tr>
    <td>Check: Route53 Dangling Ip Subdomain Takeover</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-454</small></td>
</tr>

<tr>
    <td>Check: Route53 Public Hosted Zones Cloudwatch Logging Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-455</small></td>
</tr>

<tr>
    <td>Check: Sagemaker Notebook Instance Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-457</small></td>
</tr>

<tr>
    <td>Check: Sagemaker Notebook Instance Root Access Disabled</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-458</small></td>
</tr>

<tr>
    <td>Check: Sagemaker Training Jobs Volume And Output Encryption Enabled</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-460</small></td>
</tr>

<tr>
    <td>Check: Secretsmanager Automatic Rotation Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-461</small></td>
</tr>

<tr>
    <td>Check: Secretsmanager Secret Rotated Periodically</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-463</small></td>
</tr>

<tr>
    <td>Check: Securityhub Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-464</small></td>
</tr>

<tr>
    <td>Check: Ses Identity Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-466</small></td>
</tr>

<tr>
    <td>Check: Shield Advanced Protection In Associated Elastic Ips</td>
    <td>network</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-467</small></td>
</tr>

<tr>
    <td>Check: Shield Advanced Protection In Cloudfront Distributions</td>
    <td>network</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-469</small></td>
</tr>

<tr>
    <td>Check: Shield Advanced Protection In Global Accelerators</td>
    <td>network</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-470</small></td>
</tr>

<tr>
    <td>Check: Shield Advanced Protection In Route53 Hosted Zones</td>
    <td>network</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-472</small></td>
</tr>

<tr>
    <td>Check: Sns Subscription Not Using Http Endpoints</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-473</small></td>
</tr>

<tr>
    <td>Check: Sns Topics Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-475</small></td>
</tr>

<tr>
    <td>Check: Sqs Queues Not Publicly Accessible</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-476</small></td>
</tr>

<tr>
    <td>Check: Ssm Document Secrets</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-478</small></td>
</tr>

<tr>
    <td>Check: Ssmincidents Enabled With Plans</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-479</small></td>
</tr>

<tr>
    <td>Check: Storagegateway Fileshare Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-481</small></td>
</tr>

<tr>
    <td>Check: Storagegateway Gateway Fault Tolerant</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-482</small></td>
</tr>

<tr>
    <td>Check: Trustedadvisor Errors And Warnings</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-484</small></td>
</tr>

<tr>
    <td>Check: Trustedadvisor Premium Support Plan Subscribed</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-485</small></td>
</tr>

<tr>
    <td>Check: Vpc Endpoint For Ec2 Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-487</small></td>
</tr>

<tr>
    <td>Check: Vpc Endpoint Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-488</small></td>
</tr>

<tr>
    <td>Check: Vpc Peering Routing Tables With Least Privilege</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-490</small></td>
</tr>

<tr>
    <td>Check: Vpc Subnet Different Az</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-491</small></td>
</tr>

<tr>
    <td>Check: Waf Global Rule With Conditions</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-493</small></td>
</tr>

<tr>
    <td>Check: Waf Global Webacl Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-494</small></td>
</tr>

<tr>
    <td>Check: Wafv2 Webacl Logging Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-496</small></td>
</tr>

<tr>
    <td>Check: Wafv2 Webacl Rule Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-497</small></td>
</tr>

<tr>
    <td>Check: Wellarchitected Workload No High Or Medium Risks</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-499</small></td>
</tr>

<tr>
    <td>Check: Workspaces Volume Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-500</small></td>
</tr>

</tbody>
</table>



<h3>Cần Xử lý Thủ công (82)</h3>
<p>Các findings này cần sự can thiệp thủ công từ đội ngũ quản trị.</p>
<table class="styled-table">
<thead><tr><th>Finding</th><th>Service</th><th>Severity</th><th>Resource</th></tr></thead>
<tbody>

<tr>
    <td>Check: Ecs Task Definitions Logging Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-258</small></td>
</tr>

<tr>
    <td>Check: Ecs Task Set No Assign Public Ip</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-261</small></td>
</tr>

<tr>
    <td>Check: Efs Encryption At Rest Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-264</small></td>
</tr>

<tr>
    <td>Check: Efs Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-267</small></td>
</tr>

<tr>
    <td>Check: Eks Cluster Kms Cmk Encryption In Secrets Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-270</small></td>
</tr>

<tr>
    <td>Check: Eks Control Plane Logging All Types Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-273</small></td>
</tr>

<tr>
    <td>Check: Elasticache Redis Cluster In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-276</small></td>
</tr>

<tr>
    <td>Check: Elasticbeanstalk Environment Enhanced Health Reporting</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-279</small></td>
</tr>

<tr>
    <td>Check: Elb Insecure Ssl Ciphers</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-282</small></td>
</tr>

<tr>
    <td>Check: Elb Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-285</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Cross Zone Load Balancing Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-288</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Is In Multiple Az</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-291</small></td>
</tr>

<tr>
    <td>Check: Elbv2 Ssl Listeners</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-294</small></td>
</tr>

<tr>
    <td>Check: Emr Cluster Publicly Accesible</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-297</small></td>
</tr>

<tr>
    <td>Check: Fsx File System Copy Tags To Backups Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-300</small></td>
</tr>

<tr>
    <td>Check: Glue Data Catalogs Connection Passwords Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-303</small></td>
</tr>

<tr>
    <td>Check: Glue Database Connections Ssl Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-306</small></td>
</tr>

<tr>
    <td>Check: Glue Development Endpoints S3 Encryption Enabled</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-309</small></td>
</tr>

<tr>
    <td>Check: Glue Etl Jobs Job Bookmark Encryption Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-312</small></td>
</tr>

<tr>
    <td>Check: Guardduty Centrally Managed</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-315</small></td>
</tr>

<tr>
    <td>Check: Guardduty Eks Runtime Monitoring Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-318</small></td>
</tr>

<tr>
    <td>Check: Guardduty No High Severity Findings</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-321</small></td>
</tr>

<tr>
    <td>Check: Iam Administrator Access With Mfa</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-324</small></td>
</tr>

<tr>
    <td>Check: Iam Check Saml Providers Sts</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-327</small></td>
</tr>

<tr>
    <td>Check: Iam Group Administrator Access Policy</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-330</small></td>
</tr>

<tr>
    <td>Check: Iam Inline Policy No Full Access To Cloudtrail</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-333</small></td>
</tr>

<tr>
    <td>Check: Iam No Expired Server Certificates Stored</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-336</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Lowercase</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-339</small></td>
</tr>

<tr>
    <td>Check: Iam Password Policy Reuse 24</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-342</small></td>
</tr>

<tr>
    <td>Check: Iam Policy Allows Privilege Escalation</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-345</small></td>
</tr>

<tr>
    <td>Check: Iam Policy No Full Access To Cloudtrail</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-348</small></td>
</tr>

<tr>
    <td>Check: Iam Role Cross Account Readonlyaccess Policy</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-351</small></td>
</tr>

<tr>
    <td>Check: Iam Root Hardware Mfa Enabled</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-354</small></td>
</tr>

<tr>
    <td>Check: Iam Securityaudit Role Created</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-357</small></td>
</tr>

<tr>
    <td>Check: Iam User Administrator Access Policy</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-360</small></td>
</tr>

<tr>
    <td>Check: Iam User Mfa Enabled Console Access</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-363</small></td>
</tr>

<tr>
    <td>Check: Iam User With Temporary Credentials</td>
    <td>identity</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-366</small></td>
</tr>

<tr>
    <td>Check: Kafka Cluster Encryption At Rest Uses Cmk</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-369</small></td>
</tr>

<tr>
    <td>Check: Kafka Cluster Is Public</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-372</small></td>
</tr>

<tr>
    <td>Check: Kinesis Stream Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-375</small></td>
</tr>

<tr>
    <td>Check: Kms Cmk Not Multi Region</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-378</small></td>
</tr>

<tr>
    <td>Check: Lightsail Instance Automated Snapshots</td>
    <td>resilience</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-381</small></td>
</tr>

<tr>
    <td>Check: Macie Is Enabled</td>
    <td>identity</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-384</small></td>
</tr>

<tr>
    <td>Check: Mq Broker Logging Enabled</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-387</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Copy Tags To Snapshots</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-390</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Integration Cloudwatch Logs</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-393</small></td>
</tr>

<tr>
    <td>Check: Neptune Cluster Snapshot Encrypted</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-396</small></td>
</tr>

<tr>
    <td>Check: Networkfirewall Deletion Protection</td>
    <td>logging</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-399</small></td>
</tr>

<tr>
    <td>Check: Networkfirewall Multi Az</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-402</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Audit Logging Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-405</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Fault Tolerant Data Nodes</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-408</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Node To Node Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-411</small></td>
</tr>

<tr>
    <td>Check: Opensearch Service Domains Use Cognito Authentication For Kibana</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-414</small></td>
</tr>

<tr>
    <td>Check: Organizations Opt Out Ai Services Policy</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-417</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Backtrack Enabled</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-420</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Iam Authentication Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-423</small></td>
</tr>

<tr>
    <td>Check: Rds Cluster Multi Az</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-426</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Certificate Expiration</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-429</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Enhanced Monitoring Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-432</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Iam Authentication Enabled</td>
    <td>identity</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-435</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Minor Version Upgrade Enabled</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-438</small></td>
</tr>

<tr>
    <td>Check: Rds Instance Non Default Port</td>
    <td>identity</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-441</small></td>
</tr>

<tr>
    <td>Check: Rds Snapshots Encrypted</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-444</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Encrypted At Rest</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-447</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Multi Az Enabled</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-450</small></td>
</tr>

<tr>
    <td>Check: Redshift Cluster Public Access</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-453</small></td>
</tr>

<tr>
    <td>Check: Sagemaker Endpoint Config Prod Variant Instances</td>
    <td>resilience</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-456</small></td>
</tr>

<tr>
    <td>Check: Sagemaker Training Jobs Intercontainer Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-459</small></td>
</tr>

<tr>
    <td>Check: Secretsmanager Not Publicly Accessible</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-462</small></td>
</tr>

<tr>
    <td>Check: Servicecatalog Portfolio Shared Within Organization Only</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-465</small></td>
</tr>

<tr>
    <td>Check: Shield Advanced Protection In Classic Load Balancers</td>
    <td>network</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-468</small></td>
</tr>

<tr>
    <td>Check: Shield Advanced Protection In Internet Facing Load Balancers</td>
    <td>network</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-471</small></td>
</tr>

<tr>
    <td>Check: Sns Topics Kms Encryption At Rest Enabled</td>
    <td>data</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-474</small></td>
</tr>

<tr>
    <td>Check: Sqs Queues Server Side Encryption Enabled</td>
    <td>data</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-477</small></td>
</tr>

<tr>
    <td>Check: Stepfunctions Statemachine Logging Enabled</td>
    <td>logging</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-480</small></td>
</tr>

<tr>
    <td>Check: Transfer Server In Transit Encryption Enabled</td>
    <td>data</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-483</small></td>
</tr>

<tr>
    <td>Check: Vpc Different Regions</td>
    <td>resilience</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-486</small></td>
</tr>

<tr>
    <td>Check: Vpc Flow Logs Enabled</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-489</small></td>
</tr>

<tr>
    <td>Check: Vpc Vpn Connection Tunnels Up</td>
    <td>data</td>
    <td class="severity-critical">CRITICAL</td>
    <td><small>arn:aws:s3:::bucket-492</small></td>
</tr>

<tr>
    <td>Check: Waf Regional Rule With Conditions</td>
    <td>resilience</td>
    <td class="severity-low">LOW</td>
    <td><small>arn:aws:s3:::bucket-495</small></td>
</tr>

<tr>
    <td>Check: Wafv2 Webacl With Rules</td>
    <td>logging</td>
    <td class="severity-medium">MEDIUM</td>
    <td><small>arn:aws:s3:::bucket-498</small></td>
</tr>

<tr>
    <td>Check: Workspaces Vpc 2Private 1Public Subnets Nat</td>
    <td>logging</td>
    <td class="severity-high">HIGH</td>
    <td><small>arn:aws:s3:::bucket-501</small></td>
</tr>

</tbody>
</table>






<!-- 8.5 Expert Analysis -->
<h2>7.5 Phân tích Chuyên gia</h2>

<p>Mock LLM response for visual testing.</p>


<!-- ============================================================ -->
<!-- RECOMMENDATIONS & ACTION PLAN                                 -->
<!-- ============================================================ -->

<h1>8. Khuyến nghị Chiến lược &amp; Kế hoạch Tiếp theo</h1>
<h2>8.1 Khuyến nghị</h2>

<p>Mock LLM response for visual testing.</p>



<h2>8.2 Kế hoạch Hành động Tiếp theo</h2>

<p>Mock LLM response for visual testing.</p>


<!-- ============================================================ -->
<!-- FOOTER                                                        -->
<!-- ============================================================ -->
<hr>
<p style="text-align:center; font-size:0.8em; color:#999;">
    Mã báo cáo: RPT-20260415-F50A | Ngày tạo: 2026-04-15 |
    PDCA Security Agent
</p>

</body>
</html>