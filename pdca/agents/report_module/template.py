# template.py — Full HTML Template (Sprint 3 + Maturity Refactor)
# Jinja2 + HTML, adaptive layout based on report_mode (full/partial/focused)
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
"""


REPORT_TEMPLATE = (
    '<!DOCTYPE html>\n<html lang="vi">\n<head>\n'
    '    <meta charset="utf-8">\n'
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '    <title>Báo cáo Đánh giá Bảo mật AWS</title>\n'
    '    <style>' + REPORT_CSS + '</style>\n'
    '</head>\n<body>\n'
    r"""

<!-- ============================================================ -->
<!-- COVER PAGE (Adaptive)                                         -->
<!-- ============================================================ -->
{% if report_mode == "full" and maturity %}
{# Prefer POST-remediation maturity on cover: the report covers the whole
   pipeline so a PRE-only score misrepresents final state. #}
{% set cover_post = maturity_post if maturity_post else None %}
{% set cover_score = (cover_post.overall_score if cover_post else maturity.overall_score) | round(0, 'floor') | int %}
{% set cover_stage = (cover_post.overall_stage if cover_post else maturity.overall_stage) %}
{% set cover_stage_label = (cover_post.overall_stage_label if cover_post else maturity.overall_stage_label) %}
{% set cover_delta = maturity_delta.overall.score_delta if (maturity_delta and maturity_delta.overall) else None %}
<div class="cover-page">
    <h1>BÁO CÁO ĐÁNH GIÁ MỨC ĐỘ TRƯỞNG THÀNH BẢO MẬT AWS</h1>
    <p>
        <strong>Tài khoản:</strong> {{ env.account_id }} |
        <strong>Vùng:</strong> {{ env.region }}
    </p>
    <p><strong>Ngày:</strong> {{ scope.date }}</p>
    <p><strong>Mã báo cáo:</strong> {{ report_id }}</p>

    <div class="score-box">
        <span class="stage-badge stage-{{ cover_stage | replace(' ', '') }}">
            {{ cover_stage_label }}
        </span>
        <br>
        <span class="score-number">{{ cover_score }}</span><span>/ 100</span>
        <br><small>Điểm Trưởng thành Bảo mật{% if cover_post %} (sau khắc phục){% endif %}</small>
        {% if cover_delta is not none and cover_delta != 0 %}
        <br>
        <span class="{% if cover_delta > 0 %}delta-positive{% else %}delta-negative{% endif %}" style="font-size:0.9em;">
            {% if cover_delta > 0 %}&uarr; +{% else %}&darr; {% endif %}{{ cover_delta | round(1) }} so với trước khắc phục
        </span>
        {% endif %}
    </div>

    <p class="confidentiality">
        MẬT &mdash; Tài liệu này chứa thông tin đánh giá bảo mật nội bộ.
        Chỉ được phân phối cho nhân sự được ủy quyền.
    </p>
</div>

{% elif report_mode == "partial" and maturity %}
<div class="cover-page">
    <h1>BÁO CÁO ĐÁNH GIÁ BẢO MẬT AWS</h1>
    <div class="maturity-banner warning" style="text-align:left; display:inline-block;">
        Đánh giá một phần &mdash; {{ maturity.coverage.assessed }}/{{ maturity.coverage.scoped_capabilities }}
        năng lực được kiểm tra
        {% if maturity.coverage.scanned_services %}({{ maturity.coverage.scanned_services | join(', ') | upper }}){% endif %}
    </div>
    <p>
        <strong>Tài khoản:</strong> {{ env.account_id }} |
        <strong>Vùng:</strong> {{ env.region }}
    </p>
    <p><strong>Ngày:</strong> {{ scope.date }}</p>
    <p><strong>Mã báo cáo:</strong> {{ report_id }}</p>

    <div class="score-box">
        <span class="score-number">{{ score }}</span><span>/ 100</span>
        <br><small>Điểm Bảo mật</small>
    </div>

    <p class="confidentiality">
        MẬT &mdash; Tài liệu này chứa thông tin đánh giá bảo mật nội bộ.
        Chỉ được phân phối cho nhân sự được ủy quyền.
    </p>
</div>

{% else %}
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
{% endif %}

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
{% if report_mode == "full" %}
        <li>Đánh giá Mức độ Trưởng thành Bảo mật
            <ol>
                <li>Tổng quan</li>
                {% if maturity %}{% for domain_id, domain in maturity.domains.items() %}{% if domain.capabilities %}<li>{{ domain.display_name }}</li>{% endif %}{% endfor %}{% endif %}
                {% if maturity and maturity.unmapped_capabilities %}<li>Năng lực Chưa Được Đánh giá</li>{% endif %}
                <li>Lộ trình Cải thiện</li>
            </ol>
        </li>
        <li>Chi tiết thực thi khắc phục</li>
        <li>Hậu Khắc phục &amp; Tác động Trưởng thành
            <ol><li>Kết quả Xác minh</li><li>Hiệu quả Khắc phục</li><li>Tác động lên Mức độ Trưởng thành</li><li>Rủi ro Còn lại</li><li>Phân tích Chuyên gia</li></ol>
        </li>
        <li>Khuyến nghị Chiến lược &amp; Kế hoạch Tiếp theo</li>
{% elif report_mode == "partial" %}
        <li>Đánh giá Bảo mật theo Năng lực (Phạm vi Giới hạn)</li>
        <li>Chi tiết thực thi khắc phục</li>
        <li>Hậu Khắc phục
            <ol><li>Kết quả Xác minh</li><li>Hiệu quả Khắc phục</li><li>Tác động lên Năng lực</li><li>Rủi ro Còn lại</li><li>Phân tích Chuyên gia</li></ol>
        </li>
        <li>Khuyến nghị &amp; Kế hoạch Tiếp theo</li>
{% else %}
        <li>Chi tiết thực thi khắc phục</li>
        <li>Hậu Khắc phục
            <ol><li>Kết quả Xác minh</li><li>Hiệu quả Khắc phục</li><li>Rủi ro Còn lại</li><li>Phân tích Chuyên gia</li></ol>
        </li>
        <li>Khuyến nghị</li>
{% endif %}
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
{% if scope_info and scope_info.service_display %}
    <tr><td><strong>Dịch vụ chính</strong></td>
        <td>{{ scope_info.service_display }}{% if scope_info.is_multi_service %} (nhiều dịch vụ){% endif %}</td></tr>
{% endif %}
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

<!-- Focused mode: Security Capability Mapping (small table) -->
{% if report_mode == "focused" and maturity and maturity.coverage.assessed > 0 %}
<h2>3.4 Ánh xạ Năng lực Bảo mật</h2>
<p>Các kiểm tra đã thực hiện được ánh xạ tới các năng lực bảo mật
   trong Mô hình Trưởng thành AWS:</p>
<table class="styled-table">
<thead><tr><th>Năng lực</th><th>Lĩnh vực</th><th>Stage</th><th>Kết quả</th></tr></thead>
<tbody>
{% for domain_id, domain in maturity.domains.items() %}
{% for cap in domain.capabilities %}
{% if cap.status != "not_assessed" %}
<tr>
    <td>{{ cap.capability_name }}</td>
    <td>{{ domain.display_name }}</td>
    <td>{{ cap.stage }}</td>
    <td>{{ cap.pass_count }} PASS / {{ cap.fail_count }} FAIL</td>
</tr>
{% endif %}
{% endfor %}
{% endfor %}
</tbody>
</table>
<p><em>Để có đánh giá mức độ trưởng thành đầy đủ, cần mở rộng phạm vi
   quét sang nhiều dịch vụ và kiểm tra hơn.</em></p>
{% endif %}

<!-- ============================================================ -->
<!-- 4. FINDINGS DETAIL TABLE                                      -->
<!-- ============================================================ -->
<h1>4. Bảng chi tiết phát hiện</h1>
{% if unchanged_count is defined and unchanged_count > 0 %}
<p><em>Ghi chú: {{ unchanged_count }} findings không thay đổi trạng thái (PASS &rarr; PASS) đã được ẩn.
Bảng dưới đây chỉ hiển thị các findings có thay đổi.</em></p>
{% endif %}
<table class="styled-table">
<thead>
<tr>
    <th>STT</th><th>Phát hiện</th><th>Dịch vụ</th>
    <th>Tài nguyên</th><th>Mức độ</th>
    <th>Trước</th><th>Sau</th><th>Trạng thái</th>
</tr>
</thead>
<tbody>
{% for row in table if row.change != 'Unchanged' %}
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
<!-- 5. MATURITY ASSESSMENT (Adaptive — only full/partial)         -->
<!-- ============================================================ -->
{% if report_mode == "full" and maturity %}
<h1>5. Đánh giá Mức độ Trưởng thành Bảo mật</h1>

<h2>5.1 Tổng quan</h2>
<div class="maturity-banner">
    <strong>Mức độ Trưởng thành:</strong>
    <span class="stage-badge stage-{{ maturity.overall_stage | replace(' ', '') }}">
        {{ maturity.overall_stage_label }}
    </span>
    &mdash; Điểm tổng: <strong>{{ maturity.overall_score }}/100</strong>
    <br>
    <small>
        {{ maturity.coverage.assessed }} năng lực đã được đánh giá /
        {{ maturity.coverage.scoped_capabilities }} trong phạm vi
        ({{ maturity.coverage.mapping_coverage_pct }}% coverage)
        {% if maturity.coverage.scanned_services %} &mdash; Services: {{ maturity.coverage.scanned_services | join(', ') | upper }}{% endif %}
    </small>
</div>

{{ llm.maturity_overview }}

{% if maturity_charts.radar %}
<div style="text-align:center">
    <img src="{{ maturity_charts.radar }}" style="max-width:500px">
</div>
{% endif %}

{% if maturity_charts.stage_progress %}
<div style="text-align:center">
    <img src="{{ maturity_charts.stage_progress }}" style="max-width:700px">
</div>
{% endif %}

<!-- Per-domain sections (skip domains with zero assessed capabilities) -->
{% set ns_full = namespace(section_idx=1) %}
{% for domain_id, domain in maturity.domains.items() %}
{% if domain.capabilities %}
{% set ns_full.section_idx = ns_full.section_idx + 1 %}
<h2>5.{{ ns_full.section_idx }} {{ domain.display_name }}</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-{{ domain.stage | replace(' ', '') }}">
                {{ domain.stage_label }}
            </span>
        </div>
        <div class="domain-score score-{% if domain.score >= 70 %}high{% elif domain.score >= 40 %}medium{% else %}low{% endif %}">
            {{ domain.score | round(1) }}
        </div>
    </div>

    {% if llm.domain_assessments and llm.domain_assessments[domain_id] %}
    {{ llm.domain_assessments[domain_id] }}
    {% endif %}

    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    {% for cap in domain.capabilities %}
    <tr>
        <td>{{ cap.capability_name }}</td>
        <td><small>{{ cap.stage }}</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:{{ cap.score }}%; background:{% if cap.score >= 70 %}#4CAF50{% elif cap.score >= 40 %}#FFB300{% else %}#F44336{% endif %}"></div>
            </div>
            {{ cap.score | round(1) }}%
        </td>
        <td>{{ cap.pass_count }}</td>
        <td>{{ cap.fail_count }}</td>
        <td>{{ cap.status }}</td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
</div>
{% endif %}
{% endfor %}

<!-- Unmapped capabilities -->
{% if maturity.unmapped_capabilities %}
{% set ns_full.section_idx = ns_full.section_idx + 1 %}
<h2>5.{{ ns_full.section_idx }} Năng lực Chưa Được Đánh giá</h2>
<p>Các năng lực sau không có kiểm tra tự động tương ứng (Prowler checks).
   Cần đánh giá thủ công hoặc mở rộng phạm vi công cụ.</p>
<table class="styled-table">
<thead><tr><th>Năng lực</th><th>Stage</th><th>Hướng dẫn Đánh giá</th></tr></thead>
<tbody>
{% for cap in maturity.unmapped_capabilities[:15] %}
<tr>
    <td>{{ cap.capability_name }}</td>
    <td>{{ cap.stage }}</td>
    <td><small>{{ cap.guidance }}</small></td>
</tr>
{% endfor %}
</tbody>
</table>
{% if maturity.unmapped_capabilities | length > 15 %}
<p><em>... và {{ maturity.unmapped_capabilities | length - 15 }} năng lực khác.</em></p>
{% endif %}
{% endif %}

<!-- Maturity Roadmap -->
{% set ns_full.section_idx = ns_full.section_idx + 1 %}
<h2>5.{{ ns_full.section_idx }} Lộ trình Cải thiện</h2>
{{ llm.maturity_roadmap }}

{% elif report_mode == "partial" and maturity %}
<!-- ============================================================ -->
<!-- 5. PARTIAL MATURITY                                           -->
<!-- ============================================================ -->
<h1>5. Đánh giá Bảo mật theo Năng lực (Phạm vi Giới hạn)</h1>

<div class="maturity-banner warning">
    <strong>Lưu ý:</strong> Đánh giá này chỉ bao gồm
    {{ maturity.coverage.assessed }} / {{ maturity.coverage.scoped_capabilities }} năng lực bảo mật.
    Kết quả không đại diện cho mức độ trưởng thành toàn diện của hệ thống.
    Để có đánh giá đầy đủ, cần mở rộng phạm vi quét sang các dịch vụ khác.
</div>

<h2>5.1 Tổng quan</h2>

{% if maturity_charts.stage_progress %}
<div style="text-align:center">
    <img src="{{ maturity_charts.stage_progress }}" style="max-width:700px">
</div>
{% endif %}

{{ llm.maturity_overview }}

<!-- Summary table -->
<table class="styled-table">
<thead><tr><th>Lĩnh vực</th><th>Score</th><th>Capabilities</th><th>Trạng thái</th></tr></thead>
<tbody>
{% for domain_id, domain in maturity.domains.items() %}
{% if domain.capabilities %}
<tr>
    <td>{{ domain.display_name }}</td>
    <td>{{ domain.score | round(1) }}</td>
    <td>{{ domain.capabilities | length }}</td>
    <td><span class="stage-badge stage-{{ domain.stage | replace(' ', '') }}">{{ domain.stage_label }}</span></td>
</tr>
{% endif %}
{% endfor %}
</tbody>
</table>

<!-- Only domains with data -->
{% set ns = namespace(section_idx=1) %}
{% for domain_id, domain in maturity.domains.items() %}
{% if domain.capabilities %}
{% set ns.section_idx = ns.section_idx + 1 %}
<h2>5.{{ ns.section_idx }} {{ domain.display_name }}</h2>
<div class="domain-card">
    <div class="domain-card-header">
        <div>
            <span class="stage-badge stage-{{ domain.stage | replace(' ', '') }}">
                {{ domain.stage_label }}
            </span>
        </div>
        <div class="domain-score score-{% if domain.score >= 70 %}high{% elif domain.score >= 40 %}medium{% else %}low{% endif %}">
            {{ domain.score | round(1) }}
        </div>
    </div>

    {% if llm.domain_assessments and llm.domain_assessments[domain_id] %}
    {{ llm.domain_assessments[domain_id] }}
    {% endif %}

    {% if domain.capabilities %}
    <table class="capability-table">
    <thead><tr><th>Năng lực</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trạng thái</th></tr></thead>
    <tbody>
    {% for cap in domain.capabilities %}
    <tr>
        <td>{{ cap.capability_name }}</td>
        <td><small>{{ cap.stage }}</small></td>
        <td>
            <div class="cap-score-bar">
                <div class="cap-score-fill" style="width:{{ cap.score }}%; background:{% if cap.score >= 70 %}#4CAF50{% elif cap.score >= 40 %}#FFB300{% else %}#F44336{% endif %}"></div>
            </div>
            {{ cap.score | round(1) }}%
        </td>
        <td>{{ cap.pass_count }}</td>
        <td>{{ cap.fail_count }}</td>
        <td>{{ cap.status }}</td>
    </tr>
    {% endfor %}
    </tbody>
    </table>
    {% endif %}
</div>
{% endif %}
{% endfor %}

<!-- Scope not covered -->
<h2>Phạm vi Chưa Được Đánh giá</h2>
<p>Các lĩnh vực sau chưa nằm trong phạm vi quét:</p>
<ul>
{% for domain_id, domain in maturity.domains.items() %}
{% if not domain.capabilities %}
<li><strong>{{ domain.display_name }}</strong> &mdash; chưa có dữ liệu</li>
{% endif %}
{% endfor %}
</ul>

{{ llm.maturity_roadmap }}

{% endif %}

<!-- ============================================================ -->
<!-- REMEDIATION EXECUTION (Section 5/6/7 depending on mode)       -->
<!-- ============================================================ -->
{% if report_mode in ("full", "partial") %}
<h1>6. Chi tiết thực thi khắc phục</h1>
{% else %}
<h1>5. Chi tiết thực thi khắc phục</h1>
{% endif %}

{% if report_mode in ("full", "partial") %}
{% set rem_section = 6 %}
{% else %}
{% set rem_section = 5 %}
{% endif %}

<h2>{{ rem_section }}.1 Khắc phục thành công</h2>
{% for f in success %}
<h3>{{ loop.index }}. {{ f.display_title }}</h3>
<ul>
    <li><strong>Tài nguyên:</strong> <code>{{ f.resource | default('N/A', true) }}</code></li>
    <li><strong>Công cụ:</strong> <code>{{ f.tool_name | default('N/A', true) }}</code></li>
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

<h2>{{ rem_section }}.2 Khắc phục thất bại</h2>
{% for f in failed %}
<h3>{{ loop.index }}. {{ f.display_title }}</h3>
<p><strong>Tài nguyên:</strong> <code>{{ f.resource | default('N/A', true) }}</code></p>
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

<h2>{{ rem_section }}.3 Yêu cầu khắc phục thủ công</h2>
{% if not manual %}
<p><em>Không ghi nhận yêu cầu khắc phục thủ công trong phạm vi đánh giá này.</em></p>
{% endif %}

{% for f in manual %}
<blockquote>
    <strong>Yêu cầu thủ công #{{ loop.index }}</strong><br>
    <strong>Vấn đề:</strong> {{ f.description | default('Không có mô tả', true) }}<br>
    <strong>Tài nguyên:</strong> <code>{{ f.resource | default('N/A', true) }}</code> |
    <strong>Mức độ:</strong> {{ f.severity | default('N/A', true) }}<br>

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
<!-- POST-REMEDIATION (Enhanced — ALL MODES)                       -->
<!-- ============================================================ -->
{% if report_mode == "full" %}
{% set post_section = 7 %}
<h1>7. Hậu Khắc phục &amp; Tác động Trưởng thành</h1>
{% elif report_mode == "partial" %}
{% set post_section = 7 %}
<h1>7. Hậu Khắc phục</h1>
{% else %}
{% set post_section = 6 %}
<h1>6. Hậu Khắc phục</h1>
{% endif %}

<!-- 8.1 Verification Table -->
<h2>{{ post_section }}.1 Kết quả Xác minh</h2>
<p>Bảng dưới đây thể hiện kết quả xác minh cho từng finding sau khi
   thực hiện khắc phục. Mỗi finding được kiểm tra lại (re-scan) để
   xác nhận trạng thái thực tế.</p>
{% if unchanged_count is defined and unchanged_count > 0 %}
<p><em>{{ unchanged_count }} findings không thay đổi trạng thái đã được ẩn.</em></p>
{% endif %}

<table class="styled-table">
<thead>
<tr><th>STT</th><th>Finding</th><th>Service</th><th>Severity</th><th>Trước</th><th>Sau</th><th>Kết quả</th></tr>
</thead>
<tbody>
{% for row in table if row.change != 'Unchanged' %}
<tr class="{% if row.after == 'PASS' %}verification-pass{% elif row.after == 'FAIL' %}verification-fail{% endif %}">
    <td>{{ row.stt }}</td>
    <td>{{ row.finding }}</td>
    <td>{{ row.service }}</td>
    <td class="severity-{{ row.severity | lower }}">{{ row.severity }}</td>
    <td>{{ row.before }}</td>
    <td>{{ row.after }}</td>
    <td>
        {% if "Fixed" in row.change %}
            <span style="color:#2E7D32">&#10004; Đã khắc phục</span>
        {% elif "ManualRequired" in row.change %}
            <span style="color:#E65100">&#9888; Cần xử lý thủ công</span>
        {% elif "RemediationFailed" in row.change %}
            <span style="color:#C62828">&#10008; Khắc phục thất bại</span>
        {% elif row.change == "Unchanged" %}
            <span style="color:#757575">&mdash; Không đổi</span>
        {% elif row.change == "NewIssue" %}
            <span style="color:#C62828">&#9888; Vấn đề mới</span>
        {% else %}
            {{ row.change }}
        {% endif %}
    </td>
</tr>
{% endfor %}
</tbody>
</table>

<!-- 8.2 Fix Metrics -->
<h2>{{ post_section }}.2 Hiệu quả Khắc phục</h2>

{% if fix_metrics %}
<div style="text-align:center; margin: 20px 0;">
    <div class="metric-card">
        <div class="metric-value" style="color:#2E7D32">{{ fix_metrics.fix_rate_pct }}%</div>
        <div class="metric-label">Tỷ lệ Khắc phục</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{{ fix_metrics.fixed }}/{{ fix_metrics.total_fail_pre }}</div>
        <div class="metric-label">Findings Đã Fix</div>
    </div>
    <div class="metric-card">
        <div class="metric-value" style="color:#1565C0">{{ fix_metrics.auto_success_rate_pct }}%</div>
        <div class="metric-label">Auto-fix Thành công</div>
    </div>
    <div class="metric-card">
        <div class="metric-value {% if fix_metrics.residual_rate_pct > 30 %}score-low{% elif fix_metrics.residual_rate_pct > 10 %}score-medium{% else %}score-high{% endif %}">
            {{ fix_metrics.residual_fail }}
        </div>
        <div class="metric-label">Findings Còn lại</div>
    </div>
</div>

<table class="styled-table">
<thead><tr><th>Chỉ số</th><th>Trước Khắc phục</th><th>Sau Khắc phục</th><th>Thay đổi</th></tr></thead>
<tbody>
<tr>
    <td>Findings PASS</td>
    <td>{{ pre.pass }}</td>
    <td>{{ post.final_pass }}</td>
    <td class="delta-positive">+{{ post.final_pass - pre.pass }}</td>
</tr>
<tr>
    <td>Findings FAIL</td>
    <td>{{ pre.fail }}</td>
    <td>{{ post.final_fail }}</td>
    <td class="{% if post.final_fail < pre.fail %}delta-positive{% elif post.final_fail > pre.fail %}delta-negative{% else %}delta-zero{% endif %}">{{ post.final_fail - pre.fail }}</td>
</tr>
<tr>
    <td>Pass Rate</td>
    <td>{{ fix_metrics.pre_pass_rate_pct }}%</td>
    <td>{{ fix_metrics.post_pass_rate_pct }}%</td>
    <td class="{% if fix_metrics.pass_rate_delta > 0 %}delta-positive{% elif fix_metrics.pass_rate_delta < 0 %}delta-negative{% else %}delta-zero{% endif %}">
        {% if fix_metrics.pass_rate_delta > 0 %}+{% endif %}{{ fix_metrics.pass_rate_delta }}%
    </td>
</tr>
</tbody>
</table>
{% endif %}

<!-- 8.3 Maturity Delta (only for full/partial with delta) -->
{% if maturity_delta and report_mode in ("full", "partial") %}
<h2>{{ post_section }}.3 Tác động lên Mức độ Trưởng thành</h2>

<div class="maturity-banner">
    <strong>Điểm Trưởng thành:</strong>
    {{ maturity_delta.overall.pre_score | round(1) }}
    &rarr;
    <strong>{{ maturity_delta.overall.post_score | round(1) }}</strong>
    <span class="{% if maturity_delta.overall.score_delta > 0 %}delta-positive{% elif maturity_delta.overall.score_delta < 0 %}delta-negative{% else %}delta-zero{% endif %}">
        ({% if maturity_delta.overall.score_delta > 0 %}+{% endif %}{{ maturity_delta.overall.score_delta | round(1) }})
    </span>
    {% if maturity_delta.overall.stage_changed %}
    <br>
    <span class="stage-badge stage-{{ maturity_delta.overall.pre_stage | replace(' ', '') }}">
        {{ maturity_delta.overall.stage_label_pre }}
    </span>
    &rarr;
    <span class="stage-badge stage-{{ maturity_delta.overall.post_stage | replace(' ', '') }}">
        {{ maturity_delta.overall.stage_label_post }}
    </span>
    {% endif %}
</div>

{% if maturity_charts.maturity_delta %}
<div style="text-align:center">
    <img src="{{ maturity_charts.maturity_delta }}" style="max-width:700px">
</div>
{% endif %}

<!-- Domain delta table -->
<table class="styled-table">
<thead><tr><th>Lĩnh vực</th><th>Trước</th><th>Sau</th><th>Thay đổi</th><th>Stage</th></tr></thead>
<tbody>
{% for domain_id, dd in maturity_delta.domains.items() %}
<tr>
    <td>{{ dd.display_name }}</td>
    <td>{{ dd.pre_score | round(1) }}</td>
    <td>{{ dd.post_score | round(1) }}</td>
    <td class="{% if dd.score_delta > 0 %}delta-positive{% elif dd.score_delta < 0 %}delta-negative{% else %}delta-zero{% endif %}">
        {% if dd.score_delta > 0 %}+{% endif %}{{ dd.score_delta | round(1) }}
    </td>
    <td>
        {% if dd.stage_changed %}
            {{ dd.pre_stage }} &rarr; <strong>{{ dd.post_stage }}</strong>
        {% else %}
            {{ dd.pre_stage }}
        {% endif %}
    </td>
</tr>
{% endfor %}
</tbody>
</table>

{% if maturity_delta.capabilities_improved %}
<h3>Năng lực Được Cải thiện</h3>
<table class="styled-table">
<thead><tr><th>Năng lực</th><th>Lĩnh vực</th><th>Trước</th><th>Sau</th><th>Ghi chú</th></tr></thead>
<tbody>
{% for cap in maturity_delta.capabilities_improved[:20] %}
<tr>
    <td>{{ cap.capability_name }}</td>
    <td>{{ cap.domain }}</td>
    <td>{{ cap.pre_score | round(1) }}%</td>
    <td>{{ cap.post_score | round(1) }}%</td>
    <td>
        {% if cap.newly_passing %}
            <span class="delta-positive">Mới đạt chuẩn (&ge;50%)</span>
        {% else %}
            <span class="delta-positive">+{{ cap.score_delta | round(1) }}%</span>
        {% endif %}
    </td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}

{% if maturity_delta.capabilities_regressed %}
<h3>Năng lực Bị Giảm</h3>
<p class="delta-negative">Các năng lực sau có điểm giảm sau khắc phục (có thể do phát hiện vấn đề mới trong quá trình re-scan):</p>
<table class="styled-table">
<thead><tr><th>Năng lực</th><th>Trước</th><th>Sau</th><th>Thay đổi</th></tr></thead>
<tbody>
{% for cap in maturity_delta.capabilities_regressed %}
<tr>
    <td>{{ cap.capability_name }}</td>
    <td>{{ cap.pre_score | round(1) }}%</td>
    <td>{{ cap.post_score | round(1) }}%</td>
    <td class="delta-negative">{{ cap.score_delta | round(1) }}%</td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}

{% endif %}
<!-- End maturity delta section -->

<!-- 8.4 Residual Risks -->
<h2>{{ post_section }}.{% if maturity_delta and report_mode in ("full", "partial") %}4{% else %}3{% endif %} Rủi ro Còn lại</h2>

{% if residual_risks and residual_risks.total == 0 %}
<div class="maturity-banner" style="background:#E8F5E9; border-color:#2E7D32">
    <strong>Tất cả findings đã được khắc phục thành công.</strong>
    Không có rủi ro còn lại cần xử lý.
</div>
{% elif residual_risks and residual_risks.total > 0 %}

<p>Tổng cộng <strong>{{ residual_risks.total }}</strong> findings vẫn còn FAIL sau khắc phục:</p>
<table class="styled-table">
<thead><tr><th>Mức độ</th><th>Số lượng</th></tr></thead>
<tbody>
{% for sev in ["critical", "high", "medium", "low"] %}
{% if residual_risks.severity_breakdown[sev] > 0 %}
<tr>
    <td class="severity-{{ sev }}">{{ sev | upper }}</td>
    <td>{{ residual_risks.severity_breakdown[sev] }}</td>
</tr>
{% endif %}
{% endfor %}
</tbody>
</table>

{% if residual_risks.auto_fix_failed %}
<h3>Khắc phục Tự động Thất bại ({{ residual_risks.auto_fix_failed | length }})</h3>
<p>Hệ thống đã thử khắc phục tự động nhưng không thành công. Cần kiểm tra lại cấu hình hoặc xử lý thủ công.</p>
<table class="styled-table">
<thead><tr><th>Finding</th><th>Service</th><th>Severity</th><th>Resource</th></tr></thead>
<tbody>
{% for item in residual_risks.auto_fix_failed %}
<tr>
    <td>{{ item.finding }}</td>
    <td>{{ item.service }}</td>
    <td class="severity-{{ item.severity | lower }}">{{ item.severity }}</td>
    <td><small>{{ item.resource }}</small></td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}

{% if residual_risks.manual_required %}
<h3>Cần Xử lý Thủ công ({{ residual_risks.manual_required | length }})</h3>
<p>Các findings này cần sự can thiệp thủ công từ đội ngũ quản trị.</p>
<table class="styled-table">
<thead><tr><th>Finding</th><th>Service</th><th>Severity</th><th>Resource</th></tr></thead>
<tbody>
{% for item in residual_risks.manual_required %}
<tr>
    <td>{{ item.finding }}</td>
    <td>{{ item.service }}</td>
    <td class="severity-{{ item.severity | lower }}">{{ item.severity }}</td>
    <td><small>{{ item.resource }}</small></td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}

{% if residual_risks.unchanged %}
<h3>Chưa Có Hành động ({{ residual_risks.unchanged | length }})</h3>
<p>Các findings này chưa được xử lý trong đợt khắc phục này.</p>
<table class="styled-table">
<thead><tr><th>Finding</th><th>Service</th><th>Severity</th></tr></thead>
<tbody>
{% for item in residual_risks.unchanged %}
<tr>
    <td>{{ item.finding }}</td>
    <td>{{ item.service }}</td>
    <td class="severity-{{ item.severity | lower }}">{{ item.severity }}</td>
</tr>
{% endfor %}
</tbody>
</table>
{% endif %}

{% endif %}

<!-- 8.5 Expert Analysis -->
<h2>{{ post_section }}.{% if maturity_delta and report_mode in ("full", "partial") %}5{% else %}4{% endif %} Phân tích Chuyên gia</h2>
{% if llm.post_remediation_analysis %}
{{ llm.post_remediation_analysis }}
{% else %}
{{ llm.post_analysis }}
{% endif %}

<!-- ============================================================ -->
<!-- RECOMMENDATIONS & ACTION PLAN                                 -->
<!-- ============================================================ -->
{% if report_mode in ("full", "partial") %}
<h1>8. Khuyến nghị Chiến lược &amp; Kế hoạch Tiếp theo</h1>
<h2>8.1 Khuyến nghị</h2>
{% else %}
<h1>7. Khuyến nghị</h1>
<h2>7.1 Khuyến nghị</h2>
{% endif %}

{# Deterministic numeric summary — rendered by template, not LLM. This
   eliminates the "SỐ findings FAIL ban đầu: 10\n..." flat-paragraph bug
   and guarantees consistency with Section 7 metrics. #}
{% if fix_metrics %}
<div class="metric-card" style="display:block; text-align:left; padding:15px 20px; margin:15px 0; background:#f8f9fa; border-left:4px solid #1565C0;">
    <strong>Tổng kết khắc phục</strong>
    <table style="width:100%; margin-top:8px; font-size:0.95em;">
        <tr>
            <td style="padding:4px 12px;">Findings FAIL ban đầu</td>
            <td style="padding:4px 12px; font-weight:bold;">{{ fix_metrics.total_fail_pre }}</td>
            <td style="padding:4px 12px;">Fix tự động thành công</td>
            <td style="padding:4px 12px; color:#2E7D32; font-weight:bold;">{{ fix_metrics.fixed }}</td>
        </tr>
        <tr>
            <td style="padding:4px 12px;">Fix tự động thất bại</td>
            <td style="padding:4px 12px; color:{% if fix_metrics.failed_fix > 0 %}#C62828{% else %}#2E7D32{% endif %}; font-weight:bold;">{{ fix_metrics.failed_fix }}</td>
            <td style="padding:4px 12px;">Cần xử lý thủ công</td>
            <td style="padding:4px 12px; color:#E65100; font-weight:bold;">{{ fix_metrics.manual }}</td>
        </tr>
        <tr>
            <td style="padding:4px 12px;">FAIL còn lại sau khắc phục</td>
            <td style="padding:4px 12px; font-weight:bold;" colspan="3">{{ fix_metrics.residual_fail }}</td>
        </tr>
    </table>
</div>
{% endif %}

{{ llm.recommendations }}

{% if llm.action_plan %}
{% if report_mode in ("full", "partial") %}
<h2>8.2 Kế hoạch Hành động Tiếp theo</h2>
{% else %}
<h2>7.2 Kế hoạch Hành động Tiếp theo</h2>
{% endif %}
{{ llm.action_plan }}
{% endif %}

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
)
