"""
Report Agent benchmark metrics — 4 core evaluation axes.

All core metrics are DETERMINISTIC (chi phi = 0, khong can LLM judge).
Extension metrics (narrative_faithfulness, correctness_judge) NOT included here.

4 axes:
- Structure: Gate check — HTML valid, sections present, no template leak, no None
- Correctness: Template-rendered data accuracy (stats, table, score, status colors)
- Faithfulness: Numerical claims in LLM narrative vs report_data
- Completeness: Findings coverage + conditional bypass logic

Khong import agent code. Chi nhan HTML output + report_data dict.
"""

import logging
import os
import re
import unicodedata
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_diacritics(text: str) -> str:
    """Xoa dau tieng Viet de matching."""
    text = text.replace("\u0111", "d").replace("\u0110", "D")
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


class _HTMLTextExtractor(HTMLParser):
    """Extract visible text from HTML, skip <style>/<script>/<pre>."""

    def __init__(self):
        super().__init__()
        self._result = []
        self._skip = False
        self._skip_tags = {"style", "script"}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._result.append(data)

    def get_text(self) -> str:
        return " ".join(self._result)


def _extract_text(html: str) -> str:
    """Extract visible text from HTML."""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _extract_numbers(text: str) -> List[int]:
    """Extract all integers from text."""
    return [int(m) for m in re.findall(r'\b(\d+)\b', text)]


# ---------------------------------------------------------------------------
# 1. Structure — Gate Check
# ---------------------------------------------------------------------------

# Section headings that MUST appear in the HTML output.
# These are matched case-insensitively against the rendered HTML.
# Anchored to actual Jinja template strings (template.py) — verified 2026-04-20.
REQUIRED_SECTIONS = [
    "Tóm tắt điều hành",             # 1. Executive Summary
    "Phạm vi và phương pháp",         # 2. Scope & Methodology
    "Đánh giá trước khắc phục",       # 3. Pre-remediation
    "Bảng chi tiết phát hiện",        # 4. Findings table
    "Chi tiết thực thi khắc phục",    # 5. Remediation execution
    "Hậu Khắc phục",                  # 6/7. Post-remediation (template: "Hậu Khắc phục")
    "Khuyến nghị",                    # 7/8. Recommendations (template: "Khuyến nghị")
]


def evaluate_structure(html: str, output_dir: Optional[str] = None) -> Dict[str, Any]:
    """Gate check — 4 hard constraints + 2 soft constraints.

    Hard (fail 1 = output unusable):
      html_valid, section_presence_rate, no_template_leak, no_none_display

    Soft (warning only):
      cover_page_complete, chart_presence
    """

    # --- Hard: html_valid ---
    has_doctype = "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
    has_html_vi = '<html lang="vi">' in html
    has_charset = 'charset="utf-8"' in html or "charset=utf-8" in html.lower()
    html_valid = all([has_doctype, has_html_vi, has_charset])

    # --- Hard: section_presence_rate ---
    sections_found = []
    for section in REQUIRED_SECTIONS:
        found = section in html
        sections_found.append({"section": section, "found": found})
    present_count = sum(1 for s in sections_found if s["found"])
    section_presence_rate = present_count / len(REQUIRED_SECTIONS) if REQUIRED_SECTIONS else 1.0

    # --- Hard: no_template_leak ---
    # Check for Jinja2 syntax or placeholder leak OUTSIDE <pre>/<code> blocks
    # Strip code blocks first
    html_no_code = re.sub(r'<pre>.*?</pre>', '', html, flags=re.DOTALL)
    html_no_code = re.sub(r'<code>.*?</code>', '', html_no_code, flags=re.DOTALL)

    jinja_leaks = re.findall(r'\{\{.*?\}\}|\{%.*?%\}', html_no_code)
    placeholder_leaks = re.findall(r'\[(?!http)[^\]]{3,}\]', html_no_code)
    # Filter out legitimate brackets (like [PASS], [FAIL] which are valid)
    placeholder_leaks = [p for p in placeholder_leaks
                         if not re.match(r'\[(PASS|FAIL|OK|N/A)\]', p)]
    no_template_leak = len(jinja_leaks) == 0 and len(placeholder_leaks) == 0

    # --- Hard: no_none_display ---
    text = _extract_text(html)
    # Look for "None" as standalone word (not part of "Nonexistent", etc.)
    none_matches = re.findall(r'\bNone\b', text)
    # Filter out legitimate uses in code blocks
    text_no_code = re.sub(r'<pre>.*?</pre>', '', html, flags=re.DOTALL)
    text_no_code = re.sub(r'<code>.*?</code>', '', text_no_code, flags=re.DOTALL)
    none_in_text = re.findall(r'\bNone\b', _extract_text(text_no_code))
    no_none_display = len(none_in_text) == 0

    # --- Soft: cover_page_complete ---
    cover_match = re.search(r'<div class="cover-page">(.*?)</div>', html, re.DOTALL)
    cover_html = cover_match.group(1) if cover_match else ""
    has_account = bool(re.search(r'\d{12}', cover_html))  # 12-digit AWS account
    has_region = bool(re.search(r'[a-z]+-[a-z]+-\d', cover_html))  # e.g. ap-southeast-1
    has_date = bool(re.search(r'\d{4}-\d{2}-\d{2}', cover_html))
    has_report_id = bool(re.search(r'RPT-\d{8}-[A-F0-9]{4}', cover_html))
    has_score = bool(re.search(r'score-number', cover_html))
    cover_page_complete = all([has_account, has_region, has_date, has_report_id, has_score])

    # --- Soft: chart_presence ---
    chart_presence = False
    if output_dir:
        sev_path = os.path.join(output_dir, "charts", "severity_bar.png")
        pie_path = os.path.join(output_dir, "charts", "pass_fail_pie.png")
        chart_presence = os.path.exists(sev_path) and os.path.exists(pie_path)
    else:
        # Fallback: check if chart references exist in HTML
        chart_presence = ("severity_bar.png" in html and "pass_fail_pie.png" in html)

    # Gate logic
    hard_pass = all([html_valid, section_presence_rate == 1.0, no_template_leak, no_none_display])

    return {
        # Hard constraints
        "html_valid": html_valid,
        "section_presence_rate": round(section_presence_rate, 4),
        "sections_detail": sections_found,
        "no_template_leak": no_template_leak,
        "template_leaks": jinja_leaks + placeholder_leaks,
        "no_none_display": no_none_display,
        "none_occurrences": len(none_in_text),

        # Soft constraints
        "cover_page_complete": cover_page_complete,
        "cover_detail": {
            "account": has_account, "region": has_region,
            "date": has_date, "report_id": has_report_id, "score": has_score,
        },
        "chart_presence": chart_presence,

        # Aggregate
        "hard_pass": hard_pass,
    }


# ---------------------------------------------------------------------------
# 2. Correctness — Deterministic Data Accuracy
# ---------------------------------------------------------------------------

def evaluate_correctness(
    html: str,
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministic correctness: template-rendered data matches report_data.

    Sub-metrics:
    - stats_accuracy: pre/post numbers in HTML match input
    - findings_table_accuracy: table row count + severity badges
    - score_accuracy: security score matches _calc_score()
    - status_color_accuracy: Fixed/Manual/Failed → correct CSS class
    """

    pre = report_data.get("pre", {})
    post = report_data.get("post", {})
    findings_table = report_data.get("findings_table", [])

    text = _extract_text(html)

    # --- stats_accuracy ---
    # Check key stats appear in HTML
    stats_checks = []

    # Pre stats
    for key, label in [("total", "pre.total"), ("pass", "pre.pass"), ("fail", "pre.fail")]:
        val = pre.get(key)
        if val is not None:
            found = str(val) in html
            stats_checks.append({"field": label, "expected": val, "found": found})

    # Severity stats
    sev = pre.get("severity", {})
    for level in ["critical", "high", "medium", "low"]:
        val = sev.get(level)
        if val is not None:
            # Check in the severity section area
            found = str(val) in html
            stats_checks.append({"field": f"pre.severity.{level}", "expected": val, "found": found})

    # Post stats
    for key, label in [("fixed", "post.fixed"), ("manual", "post.manual"), ("failed", "post.failed"),
                        ("final_pass", "post.final_pass"), ("final_fail", "post.final_fail")]:
        val = post.get(key)
        if val is not None:
            found = str(val) in html
            stats_checks.append({"field": label, "expected": val, "found": found})

    stats_correct = sum(1 for s in stats_checks if s["found"])
    stats_total = len(stats_checks)
    stats_accuracy = stats_correct / stats_total if stats_total > 0 else 1.0

    # --- findings_table_accuracy ---
    # Count <tr> rows in the findings table (section 4)
    # The findings table is the styled-table right after "Bảng chi tiết phát hiện"
    # and before the next <h1> section. Use a more specific pattern to avoid
    # matching other tables (e.g. section 6.1 post-remediation summary table).
    # The template may insert a note paragraph (e.g. "Ghi chú: N findings
    # không thay đổi ... đã được ẩn") between the heading and the table
    # when PASS→PASS rows are filtered out. Allow arbitrary intermediate
    # content so the regex keeps matching after that template change.
    table_section = re.search(
        r'Bảng chi tiết phát hiện</h1>.*?<table class="styled-table">.*?<tbody>(.*?)</tbody>',
        html, re.DOTALL
    )
    table_rows = 0
    if table_section:
        table_rows = len(re.findall(r'<tr>', table_section.group(1)))

    # The template hides PASS→PASS "Unchanged" rows (see the "Ghi chú: N
    # findings không thay đổi đã được ẩn" note). Expected visible count
    # is only the rows whose status actually changed — including the
    # edge case where *every* row is Unchanged, which renders an empty
    # tbody correctly.
    expected_rows = sum(
        1 for r in findings_table
        if (r.get("change") or "").strip().lower() != "unchanged"
    )
    table_row_match = table_rows == expected_rows

    # Check severity badges use correct CSS classes
    severity_badge_correct = True
    for row in findings_table:
        sev_val = (row.get("severity") or "").lower()
        expected_class = f"sev-{sev_val}"
        if sev_val and expected_class not in html:
            severity_badge_correct = False
            break

    findings_table_accuracy = 1.0 if (table_row_match and severity_badge_correct) else 0.0

    # --- score_accuracy ---
    # Extract score from cover page
    score_match = re.search(r'<span class="score-number">(\d+)</span>', html)
    displayed_score = int(score_match.group(1)) if score_match else None
    expected_score = _calc_score(pre, post)
    score_accuracy = 1.0 if displayed_score == expected_score else 0.0

    # --- status_color_accuracy ---
    status_checks = []
    for row in findings_table:
        change = (row.get("change") or "").lower()
        if "fixed" in change:
            expected_class = "status-fixed"
        elif "manual" in change:
            expected_class = "status-manual"
        else:
            expected_class = "status-error"
        # Check the row's change text appears near the expected class
        # Simplified: just check that the CSS class exists in HTML
        found = expected_class in html
        status_checks.append({"change": row.get("change"), "expected_class": expected_class, "found": found})

    status_correct = sum(1 for s in status_checks if s["found"])
    status_total = len(status_checks)
    status_color_accuracy = status_correct / status_total if status_total > 0 else 1.0

    return {
        "stats_accuracy": round(stats_accuracy, 4),
        "stats_detail": stats_checks,
        "findings_table_accuracy": round(findings_table_accuracy, 4),
        "table_rows_expected": expected_rows,
        "table_rows_found": table_rows,
        "severity_badges_correct": severity_badge_correct,
        "score_accuracy": round(score_accuracy, 4),
        "displayed_score": displayed_score,
        "expected_score": expected_score,
        "status_color_accuracy": round(status_color_accuracy, 4),
        "status_detail": status_checks,
    }


def _calc_score(pre: Dict, post: Dict) -> int:
    """Mirror of ReportAgent._calc_score() for verification."""
    total = post.get("final_pass", 0) + post.get("final_fail", 0)
    if total == 0:
        return 100

    pass_ratio = post.get("final_pass", 0) / total

    sev = pre.get("severity", {})
    max_penalty = total * 10
    actual = (
        sev.get("critical", 0) * 10
        + sev.get("high", 0) * 5
        + sev.get("medium", 0) * 2
        + sev.get("low", 0) * 0.5
    )
    sev_score = 1 - (actual / max(max_penalty, 1))

    rem_rate = post.get("fixed", 0) / max(pre.get("fail", 0), 1)

    score = pass_ratio * 60 + sev_score * 30 + rem_rate * 10
    return round(min(max(score, 0), 100))


# ---------------------------------------------------------------------------
# 3. Faithfulness — Numerical Claims in Narrative vs Data
# ---------------------------------------------------------------------------

# LLM-generated sections in the template (these contain narrative text)
_LLM_SECTION_PATTERNS = [
    # (section_name, regex to extract LLM content from HTML)
    ("executive_summary", r'<h1>1\. Tóm tắt điều hành</h1>\s*(.*?)\s*<h1>'),
    ("system_overview", r'<h2>2\.1 Bối cảnh hệ thống</h2>.*?</table>\s*(.*?)\s*<h2>'),
    ("assessment_goals", r'<h2>2\.2 Mục tiêu đánh giá</h2>\s*(.*?)\s*<h1>'),
    ("pass_overview", r'<h3>Tổng quan các mục ĐẠT</h3>\s*(.*?)\s*<h3>'),
    ("fail_overview", r'<h3>Tổng quan các mục KHÔNG ĐẠT</h3>\s*(.*?)\s*<h1>'),
    ("post_analysis", r'<h2>6\.3 Đánh giá của chuyên gia</h2>\s*(.*?)\s*<h1>'),
    ("recommendations", r'<h1>7\. Khuyến nghị chiến lược</h1>\s*(.*?)\s*<hr>'),
]


def _extract_llm_sections(html: str) -> Dict[str, str]:
    """Extract LLM-generated narrative sections from HTML."""
    sections = {}
    for name, pattern in _LLM_SECTION_PATTERNS:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            raw = match.group(1)
            sections[name] = _extract_text(f"<div>{raw}</div>")
    return sections


def evaluate_faithfulness(
    html: str,
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Numerical faithfulness: numbers in LLM narrative match report_data.

    Core metric (deterministic, cost = 0).
    Extracts numbers from LLM sections, checks if they appear in report_data.
    """

    pre = report_data.get("pre", {})
    post = report_data.get("post", {})
    sev = pre.get("severity", {})

    # Build set of "known numbers" from report_data
    known_numbers = set()
    for val in [pre.get("total"), pre.get("pass"), pre.get("fail")]:
        if val is not None:
            known_numbers.add(val)
    for val in sev.values():
        if val is not None:
            known_numbers.add(val)
    for key in ["fixed", "failed", "manual", "initial_pass", "initial_fail",
                "final_pass", "final_fail"]:
        val = post.get(key)
        if val is not None:
            known_numbers.add(val)

    # Add derived numbers
    expected_score = _calc_score(pre, post)
    known_numbers.add(expected_score)

    # Count findings
    for key in ["success_findings", "failed_findings", "manual_findings"]:
        known_numbers.add(len(report_data.get(key, [])))
    known_numbers.add(len(report_data.get("findings_table", [])))
    known_numbers.add(len(report_data.get("raw_pre_findings", [])))

    # Add account_id from environment (LLM writes it in the cover / narrative)
    env = report_data.get("environment", {})
    acct = env.get("account_id")
    if acct is not None:
        try:
            known_numbers.add(int(str(acct).replace("-", "")))
        except ValueError:
            pass

    # Remove trivial numbers (0, 1) — too common to be meaningful
    known_numbers.discard(0)
    known_numbers.discard(1)

    # Add common "infrastructure" numbers that appear in reports
    # but are not from report_data (avoid false negatives)
    _INFRASTRUCTURE_NUMBERS = {100, 256, 2024, 2025, 2026, 2027}
    known_numbers.update(_INFRASTRUCTURE_NUMBERS)

    # Extract LLM sections
    llm_sections = _extract_llm_sections(html)
    if not llm_sections:
        return {
            "score": 0.0,
            "verified": 0,
            "total_claims": 0,
            "details": [],
            "error": "no LLM sections extracted",
        }

    # Concatenate all LLM text
    all_llm_text = " ".join(llm_sections.values())

    # Extract numbers from LLM text
    llm_numbers = _extract_numbers(all_llm_text)
    if not llm_numbers:
        # No numerical claims → vacuously faithful
        return {
            "score": 1.0,
            "verified": 0,
            "total_claims": 0,
            "details": [],
            "note": "no numerical claims in narrative",
        }

    # Filter to "meaningful" numbers (> 1, likely to be data references)
    meaningful = [n for n in llm_numbers if n > 1]
    if not meaningful:
        return {
            "score": 1.0,
            "verified": 0,
            "total_claims": 0,
            "details": [],
            "note": "no meaningful numerical claims",
        }

    # Verify each number
    details = []
    for num in meaningful:
        is_known = num in known_numbers
        details.append({"number": num, "known_in_data": is_known})

    verified = sum(1 for d in details if d["known_in_data"])
    total = len(details)
    score = verified / total if total > 0 else 1.0

    return {
        "score": round(score, 4),
        "verified": verified,
        "total_claims": total,
        "known_numbers": sorted(known_numbers),
        "details": details,
    }


# ---------------------------------------------------------------------------
# 4. Completeness — Findings Coverage + Bypass Logic
# ---------------------------------------------------------------------------

def evaluate_completeness(
    html: str,
    report_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Completeness: findings coverage + conditional bypass correctness.

    Core:
    - findings_coverage: finding_ids/event_codes present in HTML
    - conditional_bypass_correctness: bypass logic when PASS=0 or FAIL=0
    """

    pre = report_data.get("pre", {})

    # --- findings_coverage ---
    findings_table = report_data.get("findings_table", [])
    raw_pre = report_data.get("raw_pre_findings", [])

    # Collect identifiers that APPEAR in the rendered HTML.
    # finding_id (f001, f002) is internal — NOT rendered in the report template.
    # Only event_code and findings_table.finding are rendered.
    #
    # IMPORTANT: Only collect identifiers from findings_table (FAIL findings
    # that went through remediation). raw_pre_findings PASS items are rendered
    # via _build_findings_ctx() as aggregated counts, not individual event_codes.
    # For all_pass cases (findings_table=[]), coverage is vacuously 1.0.
    identifiers = set()
    for f in findings_table:
        if f.get("finding"):
            identifiers.add(f["finding"])

    found_ids = set()
    html_lower = html.lower()
    for ident in identifiers:
        if ident.lower() in html_lower:
            found_ids.add(ident)

    total_ids = len(identifiers)
    # Vacuously complete: no findings to cover → 100% coverage
    findings_coverage = len(found_ids) / total_ids if total_ids > 0 else 1.0

    coverage_detail = []
    for ident in sorted(identifiers):
        coverage_detail.append({
            "identifier": ident,
            "found": ident in found_ids,
        })

    # --- conditional_bypass_correctness ---
    # When pre.pass == 0, pass_overview should be hardcoded text (no LLM call)
    # When pre.fail == 0, fail_overview should be hardcoded text (no LLM call)
    bypass_checks = []

    # Known bypass texts from report_agent.py
    PASS_BYPASS_TEXT = "Không ghi nhận cấu hình nào đạt chuẩn"
    FAIL_BYPASS_TEXT = "Toàn bộ các kiểm tra cấu hình đều đạt chuẩn"

    pass_count = pre.get("pass", -1)
    fail_count = pre.get("fail", -1)

    if pass_count == 0:
        # Should use bypass text for pass_overview
        has_bypass = PASS_BYPASS_TEXT in html
        bypass_checks.append({
            "condition": "pre.pass == 0",
            "expected": "hardcoded pass_overview",
            "correct": has_bypass,
        })

    if fail_count == 0:
        # Should use bypass text for fail_overview
        has_bypass = FAIL_BYPASS_TEXT in html
        bypass_checks.append({
            "condition": "pre.fail == 0",
            "expected": "hardcoded fail_overview",
            "correct": has_bypass,
        })

    if pass_count > 0 and fail_count > 0:
        # Normal case — bypass should NOT appear
        has_pass_bypass = PASS_BYPASS_TEXT in html
        has_fail_bypass = FAIL_BYPASS_TEXT in html
        bypass_checks.append({
            "condition": "pre.pass > 0 AND pre.fail > 0",
            "expected": "no bypass text",
            "correct": not has_pass_bypass and not has_fail_bypass,
        })

    bypass_correct = all(b["correct"] for b in bypass_checks) if bypass_checks else True

    return {
        "findings_coverage": round(findings_coverage, 4),
        "findings_found": len(found_ids),
        "findings_total": total_ids,
        "coverage_detail": coverage_detail,
        "conditional_bypass_correctness": bypass_correct,
        "bypass_detail": bypass_checks,
    }


# ---------------------------------------------------------------------------
# Aggregate helpers (reusable pattern from gen_metrics.py)
# ---------------------------------------------------------------------------

def mean_of(cases: List[Dict], section: str, field: str) -> float:
    """Compute average of a field across evaluated cases. bool -> int."""
    values = []
    for c in cases:
        v = c.get(section, {}).get(field)
        if isinstance(v, bool):
            v = int(v)
        if v is not None:
            values.append(v)
    return round(sum(values) / len(values), 4) if values else 0.0


def check_release_criteria(summary: Dict, criteria: Dict) -> Dict[str, Any]:
    """Check summary against release criteria thresholds.

    criteria format: {"metric_path_min": 0.7}
    Suffix _min -> actual >= threshold.
    """

    METRIC_MAP = {
        # Structure (gate)
        "html_valid_min": ("structure", "html_valid_rate"),
        "section_presence_rate_min": ("structure", "section_presence_rate"),
        "no_template_leak_min": ("structure", "no_template_leak_rate"),
        "no_none_display_min": ("structure", "no_none_display_rate"),
        # Correctness
        "stats_accuracy_min": ("correctness", "stats_accuracy"),
        "findings_table_accuracy_min": ("correctness", "findings_table_accuracy"),
        "score_accuracy_min": ("correctness", "score_accuracy"),
        # Faithfulness
        "numerical_faithfulness_min": ("faithfulness", "numerical_faithfulness"),
        # Completeness
        "findings_coverage_min": ("completeness", "findings_coverage"),
        "conditional_bypass_correctness_min": ("completeness", "conditional_bypass_correctness"),
    }

    checks = []
    all_passed = True

    for criterion, threshold in criteria.items():
        if criterion.startswith("_"):
            continue

        path = METRIC_MAP.get(criterion)
        if not path:
            continue

        section, field = path
        actual = summary.get(section, {}).get(field, 0.0)

        if criterion.endswith("_min"):
            passed = actual >= threshold
        elif criterion.endswith("_max"):
            passed = actual <= threshold
        else:
            passed = actual >= threshold

        if not passed:
            all_passed = False

        checks.append({
            "criterion": criterion,
            "threshold": threshold,
            "actual": actual,
            "passed": passed,
        })

    return {
        "verdict": "PASS" if all_passed else "FAIL",
        "checks": checks,
    }
