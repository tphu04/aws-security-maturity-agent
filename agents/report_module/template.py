# template.py — Full HTML Template (Sprint 3 + Hotfix)
# Jinja2 + HTML thuần túy, không qua markdown2
# CSS gom vào cùng file, kiểm soát 100% layout

REPORT_CSS = """
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

@media print {
    .cover-page { page-break-after: always; }
    h1 { page-break-before: always; }
    h1:first-of-type { page-break-before: avoid; }
}
"""


REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo cáo Đánh giá Bảo mật AWS</title>
    <style>""" + REPORT_CSS + """</style>
</head>
<body>

<!-- ============================================================ -->
<!-- COVER PAGE                                                    -->
<!-- ============================================================ -->
<div class="cover-page">
    <h1>BÁO CÁO ĐÁNH GIÁ VÀ KHẮC PHỤC BẢO MẬT AWS</h1>
    <p>
        <strong>Tài khoản:</strong> {{ env.account_id }} |
        <strong>Vùng:</strong> {{ env.region }}
    </p>
    <p><strong>Ngày:</strong> {{ scope.date }}</p>
    <p><strong>Mã báo cáo:</strong> {{ report_id }}</p>

    <div class="score-box">
        <span class="score-number">{{ score }}</span>
        <span>/ 100</span>
        <br><small>Điểm Bảo mật</small>
    </div>

    <p class="confidentiality">
        MẬT &mdash; Tài liệu này chứa thông tin đánh giá bảo mật nội bộ.
        Chỉ được phân phối cho nhân sự được ủy quyền.
    </p>
</div>

<!-- ============================================================ -->
<!-- TABLE OF CONTENTS                                             -->
<!-- ============================================================ -->
<div class="toc">
    <h2>Mục lục</h2>
    <ol>
        <li>Tóm tắt điều hành</li>
        <li>Phạm vi và phương pháp</li>
        <li>Đánh giá trước khắc phục</li>
        <li>Bảng chi tiết phát hiện</li>
        <li>Chi tiết thực thi khắc phục</li>
        <li>Đánh giá sau khắc phục</li>
        <li>Khuyến nghị chiến lược</li>
    </ol>
</div>

<!-- ============================================================ -->
<!-- 1. EXECUTIVE SUMMARY                                          -->
<!-- ============================================================ -->
<h1>1. Tóm tắt điều hành</h1>
{{ llm.executive_summary }}

<!-- ============================================================ -->
<!-- 2. SCOPE & METHODOLOGY                                        -->
<!-- ============================================================ -->
<h1>2. Phạm vi và phương pháp</h1>

<h2>2.1 Bối cảnh hệ thống</h2>
<table class="styled-table">
<thead><tr><th>Thuộc tính</th><th>Chi tiết</th></tr></thead>
<tbody>
    <tr><td><strong>Tài khoản AWS</strong></td><td><code>{{ env.account_id }}</code></td></tr>
    <tr><td><strong>Vùng (Region)</strong></td><td>{{ env.region }}</td></tr>
    <tr><td><strong>Phạm vi quét</strong></td>
        <td>{{ scope.services | join(', ') | upper }}</td></tr>
    <tr><td><strong>Công cụ</strong></td><td>Prowler, AWS SDK (boto3), PDCA Security Agent</td></tr>
</tbody>
</table>

{{ llm.system_overview }}

<h2>2.2 Mục tiêu đánh giá</h2>
{{ llm.assessment_goals }}

<!-- ============================================================ -->
<!-- 3. PRE-REMEDIATION ASSESSMENT                                 -->
<!-- ============================================================ -->
<h1>3. Đánh giá trước khắc phục</h1>

<h2>3.1 Trạng thái bảo mật ban đầu</h2>
<ul>
    <li><strong>Tổng số phát hiện:</strong> {{ pre.total }}</li>
    <li><strong>ĐẠT (PASS):</strong> {{ pre.pass }}</li>
    <li><strong>KHÔNG ĐẠT (FAIL):</strong> {{ pre.fail }}</li>
</ul>
<p><strong>Phân bổ mức độ nghiêm trọng:</strong></p>
<ul>
    <li>Nghiêm trọng (Critical): <strong>{{ pre.severity.critical }}</strong></li>
    <li>Cao (High): <strong>{{ pre.severity.high }}</strong></li>
    <li>Trung bình (Medium): <strong>{{ pre.severity.medium }}</strong></li>
    <li>Thấp (Low): <strong>{{ pre.severity.low }}</strong></li>
</ul>

<h2>3.2 Phân tích trực quan</h2>
<table style="width:100%">
<tr>
    <td style="text-align:center; width:50%">
        <img src="{{ charts.severity }}" style="max-width:100%; height:auto;">
    </td>
    <td style="text-align:center; width:50%">
        <img src="{{ charts.pass_fail }}" style="max-width:100%; height:auto;">
    </td>
</tr>
</table>

<h2>3.3 Phân tích phát hiện</h2>
<h3>Tổng quan các mục ĐẠT</h3>
{{ llm.pass_overview }}

<h3>Tổng quan các mục KHÔNG ĐẠT</h3>
{{ llm.fail_overview }}

<!-- ============================================================ -->
<!-- 4. FINDINGS DETAIL TABLE                                      -->
<!-- ============================================================ -->
<h1>4. Bảng chi tiết phát hiện</h1>
<table class="styled-table">
<thead>
<tr>
    <th>STT</th><th>Phát hiện</th><th>Dịch vụ</th>
    <th>Tài nguyên</th><th>Mức độ</th>
    <th>Trước</th><th>Sau</th><th>Trạng thái</th>
</tr>
</thead>
<tbody>
{% for row in table %}
<tr>
    <td>{{ row.stt }}</td>
    <td>{{ row.finding }}</td>
    <td>{{ row.service }}</td>
    <td><small>{{ row.resource }}</small></td>
    <td><span class="sev-{{ row.severity|lower }}">{{ row.severity }}</span></td>
    <td>{{ row.before }}</td>
    <td>{{ row.after }}</td>
    <td class="{% if row.change|lower == 'fixed' %}status-fixed{% elif 'manual' in row.change|lower %}status-manual{% else %}status-error{% endif %}">
        {{ row.change }}
    </td>
</tr>
{% endfor %}
</tbody>
</table>

<!-- ============================================================ -->
<!-- 5. REMEDIATION EXECUTION                                      -->
<!-- ============================================================ -->
<h1>5. Chi tiết thực thi khắc phục</h1>

<h2>5.1 Khắc phục thành công</h2>
{% for f in success %}
<h3>{{ loop.index }}. {{ f.display_title }}</h3>
<ul>
    <li><strong>Tài nguyên:</strong> <code>{{ f.resource | default('N/A') }}</code></li>
    <li><strong>Công cụ:</strong> <code>{{ f.tool_name | default('N/A') }}</code></li>
</ul>
<blockquote>
    <strong>Phân tích kỹ thuật:</strong><br>
    {{ f.llm_detail }}
</blockquote>
<hr>
{% endfor %}

{% if not success %}
<p><em>Không có khắc phục tự động thành công.</em></p>
{% endif %}

<h2>5.2 Khắc phục thất bại</h2>
{% for f in failed %}
<h3>{{ loop.index }}. {{ f.display_title }}</h3>
<p><strong>Tài nguyên:</strong> <code>{{ f.resource | default('N/A') }}</code></p>
<blockquote>
    <strong>Phân tích lỗi:</strong><br>
    {{ f.llm_detail }}
</blockquote>
<pre>{{ f.execution_log }}</pre>
<hr>
{% endfor %}

{% if not failed %}
<p><em>Không ghi nhận lỗi trong quá trình khắc phục tự động.</em></p>
{% endif %}

<h2>5.3 Yêu cầu khắc phục thủ công</h2>
{% if not manual %}
<p><em>Không ghi nhận yêu cầu khắc phục thủ công trong phạm vi đánh giá này.</em></p>
{% endif %}

{% for f in manual %}
<blockquote>
    <strong>Yêu cầu thủ công #{{ loop.index }}</strong><br>
    <strong>Vấn đề:</strong> {{ f.description | default('Không có mô tả') }}<br>
    <strong>Tài nguyên:</strong> <code>{{ f.resource | default('N/A') }}</code> |
    <strong>Mức độ:</strong> {{ f.severity | default('N/A') }}<br>

    {% if f.remaining_actions %}
    <strong>Kế hoạch hành động:</strong>
    <ul>
    {% for a in f.remaining_actions %}
        <li>{{ a }}</li>
    {% endfor %}
    </ul>
    {% endif %}

    <strong>Hướng dẫn chi tiết:</strong><br>
    {{ f.llm_manual_guide }}
</blockquote>
{% endfor %}

<!-- ============================================================ -->
<!-- 6. POST-REMEDIATION ASSESSMENT                                -->
<!-- ============================================================ -->
<h1>6. Đánh giá sau khắc phục</h1>

<h2>6.1 Tóm tắt hiệu quả</h2>
<table class="styled-table">
<thead><tr><th>Chỉ số</th><th>Trước</th><th>Sau</th><th>Thay đổi</th></tr></thead>
<tbody>
<tr>
    <td><strong>ĐẠT (PASS)</strong></td>
    <td>{{ post.initial_pass }}</td>
    <td><strong>{{ post.final_pass }}</strong></td>
    <td>{% set d = post.final_pass - post.initial_pass %}
        {% if d > 0 %}Tăng {{ d }}{% elif d < 0 %}Giảm {{ d|abs }}{% else %}Giữ nguyên{% endif %}
    </td>
</tr>
<tr>
    <td><strong>KHÔNG ĐẠT (FAIL)</strong></td>
    <td>{{ post.initial_fail }}</td>
    <td><strong>{{ post.final_fail }}</strong></td>
    <td>{% set d = post.final_fail - post.initial_fail %}
        {% if d < 0 %}Giảm {{ d|abs }}{% elif d > 0 %}Tăng {{ d }}{% else %}Giữ nguyên{% endif %}
    </td>
</tr>
</tbody>
</table>

<p><strong>Trạng thái khắc phục:</strong></p>
<ul>
    <li><strong>Tự động sửa:</strong> {{ post.fixed }}</li>
    <li><strong>Cần thủ công:</strong> {{ post.manual }}</li>
    <li><strong>Lỗi (Error):</strong> {{ post.failed }}</li>
</ul>

<h2>6.2 Chi tiết thay đổi</h2>
<h3>Đã sửa tự động</h3>
{% if success %}
<ul>
{% for f in success %}
    <li>{{ f.description | default('Remediation Action') }} (<code>{{ f.resource | default('N/A') }}</code>)</li>
{% endfor %}
</ul>
{% else %}
<p><em>Không có.</em></p>
{% endif %}

<h3>Cần xử lý thủ công</h3>
{% if manual %}
<ul>
{% for f in manual %}
    <li>{{ f.description | default('Manual Action') }} (<code>{{ f.resource | default('N/A') }}</code>)</li>
{% endfor %}
</ul>
{% else %}
<p><em>Không có.</em></p>
{% endif %}

<h3>Lỗi tồn đọng</h3>
{% if failed %}
<ul>
{% for f in failed %}
    <li>{{ f.description | default('Failed Action') }} (<code>{{ f.resource | default('N/A') }}</code>)</li>
{% endfor %}
</ul>
{% else %}
<p><em>Không có lỗi trong quá trình sửa.</em></p>
{% endif %}

<h2>6.3 Đánh giá của chuyên gia</h2>
{{ llm.post_analysis }}

<!-- ============================================================ -->
<!-- 7. RECOMMENDATIONS                                            -->
<!-- ============================================================ -->
<h1>7. Khuyến nghị chiến lược</h1>
{{ llm.recommendations }}

<!-- ============================================================ -->
<!-- FOOTER                                                        -->
<!-- ============================================================ -->
<hr>
<p style="text-align:center; font-size:0.8em; color:#999;">
    Mã báo cáo: {{ report_id }} | Ngày tạo: {{ scope.date }} |
    PDCA Security Agent
</p>

</body>
</html>
"""
