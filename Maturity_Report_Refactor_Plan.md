# Plan: Refactor Report Agent — Adaptive Security Maturity Assessment

## 1. Context & Problem

### 1.1 Muc tieu de tai
"Nghien cuu va xay dung Tac tu AI Tu hanh de Danh gia Muc do Truong thanh Bao mat tren Nen tang AWS"

Report hien tai la **Remediation Report** (scan -> fix -> verify). De tai yeu cau **Maturity Assessment Report** danh gia theo domain/capability/stage cua AWS Security Maturity Model.

### 1.2 Van de hien tai
- Report chi xoay quanh PASS/FAIL findings va remediation status
- Khong co section danh gia maturity theo domain/capability
- Score tinh theo remediation effectiveness, khong phai maturity
- RAG da co du data maturity (78 capabilities, 502 mappings, 5 domains, 4 stages) nhung khong duoc khai thac

### 1.3 Thach thuc: Adaptive Scope
He thong ho tro nhieu kieu scan:
- **FAST_TRACK**: user chi dinh vai check cu the (vd: `s3_bucket_encryption`)
- **GROUP_SCAN**: scan toan bo 1 service (vd: "scan all s3")
- **RETRIEVAL_PATH**: RAG chon checks phu hop

-> Neu user chi scan 3 checks thi **khong the danh gia maturity toan dien**. Report can tu thich ung.

---

## 2. Thiet ke Adaptive Report

### 2.1 Ba che do report

```
                    ┌──────────────────────────────┐
                    │    MaturityEngine.assess()    │
                    │         tra ve dict           │
                    └──────────┬───────────────────┘
                               │
                    ┌──────────▼───────────────────┐
                    │    ReportAgent xac dinh mode  │
                    │    dua tren coverage metrics  │
                    └──────────┬───────────────────┘
                               │
              ┌────────────────┼────────────────────┐
              ▼                ▼                     ▼
    ┌─────────────────┐ ┌───────────────┐ ┌──────────────────┐
    │  FULL MATURITY   │ │   PARTIAL     │ │ FOCUSED FINDINGS │
    │  (primary mode)  │ │  MATURITY     │ │ (fallback mode)  │
    └─────────────────┘ └───────────────┘ └──────────────────┘
```

#### Mode 1: FULL MATURITY
**Dieu kien:** `domains_with_data >= 3 AND assessed_capabilities >= 15`

Report structure:
```
1. Cover — "Bao cao Danh gia Muc do Truong thanh Bao mat AWS"
   - Maturity Stage badge (vd: "Foundational")
   - Overall Score / 100
2. Muc luc
3. Tom tat Dieu hanh (maturity-focused, LLM viet)
4. Pham vi & Phuong phap
5. DANH GIA MUC DO TRUONG THANH BAO MAT ← PRIMARY SECTION
   5.1 Tong quan Truong thanh
       - Overall stage + score
       - Radar chart (5 domains)
       - Stage progress bar (4 stages)
       - Coverage disclaimer (X/78 capabilities assessed)
   5.2 Data Protection (domain card + LLM narrative + capability table)
   5.3 Identity & Access Management
   5.4 Logging & Monitoring
   5.5 Resilience
   5.6 Network Security
   5.7 Nang luc Chua Duoc Danh gia (unmapped capabilities + guidance)
   5.8 Lo trinh Cai thien (maturity roadmap, LLM viet)
6. Ket qua Kiem tra Chi tiet (pre-remediation findings — condensed)
7. Khac phuc (remediation — secondary, existing content)
8. Hau Khac phuc (post-remediation — existing)
9. Khuyen nghi Chien luoc (maturity-aware, LLM viet)
```

#### Mode 2: PARTIAL MATURITY
**Dieu kien:** `domains_with_data >= 1 AND assessed_capabilities >= 3 AND NOT full_mode`

Report structure:
```
1. Cover — "Bao cao Danh gia Bao mat AWS (Pham vi Gioi han)"
   - Score / 100
   - Banner: "Danh gia mot phan — X/78 nang luc duoc kiem tra"
2. Muc luc
3. Tom tat Dieu hanh
4. Pham vi & Phuong phap
   - Ghi ro pham vi gioi han
5. DANH GIA BAO MAT THEO NANG LUC ← ADAPTED SECTION
   5.1 Tong quan (KHONG co radar chart — misleading voi data thieu)
       - Bang tom tat: domain | so capabilities assessed | score
       - Stage progress bar (chi cho domains co data)
   5.2 Chi tiet tung Domain DA DUOC SCAN (chi hien domain co data)
       - Domain card + capability table
       - LLM narrative cho tung domain
   5.3 Pham vi Chua Duoc Danh gia
       - Liet ke domains/capabilities chua scan
       - Khuyen nghi mo rong pham vi
6-9. Remediation sections (giu nguyen nhu cu)
```

#### Mode 3: FOCUSED FINDINGS
**Dieu kien:** `assessed_capabilities < 3 OR maturity_assessment is None`

Report structure:
```
GIU NGUYEN REPORT HIEN TAI (remediation-focused)
+ Them 1 section nho:
  "Anh xa Nang luc Bao mat"
  - Bang: check_id | capability | domain | stage
  - Giai thich cac check da scan thuoc nang luc/domain nao
  - Khuyen nghi: "De co danh gia maturity day du, can scan toan dien hon"
```

### 2.2 Mode Selection Logic

```python
# Trong report_agent.py
def _determine_report_mode(self, maturity: dict | None) -> str:
    if maturity is None:
        return "focused"
    
    coverage = maturity.get("coverage", {})
    assessed = coverage.get("assessed", 0)
    
    # Dem so domains co it nhat 1 capability assessed
    domains_with_data = sum(
        1 for d in maturity.get("domains", {}).values()
        if any(c["status"] in ("assessed", "partial") for c in d.get("capabilities", []))
    )
    
    if domains_with_data >= 3 and assessed >= 15:
        return "full"
    elif domains_with_data >= 1 and assessed >= 3:
        return "partial"
    else:
        return "focused"
```

### 2.3 Thresholds

| Threshold | Value | Ly do |
|-----------|-------|-------|
| `FULL_MIN_DOMAINS` | 3 | Can it nhat 3/5 domains de radar chart co y nghia |
| `FULL_MIN_CAPABILITIES` | 15 | ~20% cua 78 capabilities, du de danh gia tong the |
| `PARTIAL_MIN_CAPABILITIES` | 3 | It nhat 3 capabilities de co section maturity |
| `STAGE_COMPLETION_THRESHOLD` | 0.70 | 70% capabilities dat >= 50% de dat stage |
| `CAPABILITY_PASS_THRESHOLD` | 50.0 | Score >= 50% de coi la "dat" capability |

---

## 3. Maturity Engine — Chi tiet Ky thuat

### 3.1 File: `agents/report_module/maturity_engine.py` (NEW)

#### Data Sources (static, load 1 lan)
```
RAG/data/normalized/maturity_mappings.json     (502 entries)
RAG/data/normalized/maturity_capabilities.json (78 entries)
```

#### Internal Lookups
```python
# check_id -> list of mapping entries
_check_to_mappings: {
    "s3_account_level_public_access_blocks": [
        {
            "capability_id": "block_public_access",
            "domain": "data_protection",
            "mapping_type": "direct",      # direct | related | weak
            "mapping_confidence": "high",  # high | medium | low
        }
    ]
}

# capability_id -> capability info (from capabilities.json)
_cap_info: {
    "block_public_access": {
        "capability_name": "Block Public Access",
        "stage": "1 quickwins",
        "summary": "...",
        "risk_explanation": "...",
        "guidance": "...",
        "recommended_practices": [...]
    }
}

# capability_id -> set of domains (from mappings, NOT capabilities)
# NOTE: capabilities.json has domain="" for ALL 78 entries
_cap_domains: {
    "block_public_access": {"data_protection"},
    "audit_api_calls": {"identity_access", "logging_monitoring", "data_protection"},
}
```

#### Scoring Constants
```python
DOMAIN_DISPLAY = {
    "data_protection": "Data Protection",
    "identity_access": "Identity & Access Management",
    "logging_monitoring": "Logging & Monitoring",
    "resilience": "Resilience",
    "network_security": "Network Security",
}

STAGE_LABELS = {
    "1 quickwins": "Quick Wins",
    "2 foundational": "Foundational",
    "3 efficient": "Efficient",
    "4 optimized": "Optimized",
}

STAGE_ORDER = ["1 quickwins", "2 foundational", "3 efficient", "4 optimized"]

# Weight matrix: (mapping_type, mapping_confidence) -> weight
_MAPPING_WEIGHTS = {
    ("direct", "high"):   1.0,
    ("direct", "medium"): 0.8,
    ("direct", "low"):    0.6,
    ("related", "high"):  0.7,
    ("related", "medium"):0.5,
    ("related", "low"):   0.3,
    ("weak", "high"):     0.3,
    ("weak", "medium"):   0.2,
    ("weak", "low"):      0.2,
}
```

#### Algorithm Flow
```
assess(findings) -> dict
│
├── Step 1: _map_findings_to_capabilities(findings)
│   - Match finding.event_code to mappings.check_id
│   - For each match: record (is_pass, weight, mapping_type)
│   - Output: {capability_id: [{is_pass, weight, mapping_type, ...}]}
│
├── Step 2: _score_capabilities(cap_findings)
│   - For each capability:
│     score = sum(weight * is_pass) / sum(weight) * 100
│     status = "assessed" if has direct/related, "partial" if only weak
│   - Output: {capability_id: {score, pass_count, fail_count, status, ...}}
│
├── Step 3: _rollup_to_domains(cap_results)
│   - Group capabilities by domain (from _cap_domains lookup)
│   - domain_score = avg(assessed_cap_scores)
│   - domain_stage = _determine_domain_stage(caps)
│   - Output: {domain: {score, stage, capabilities: [...]}}
│
├── Step 4: _compute_overall(domain_results)
│   - overall_score = weighted_avg(domain_scores, weight=n_caps)
│   - overall_stage = min(domain_stages)  # weakest link
│
├── Step 5: Identify unmapped capabilities
│   - all_caps - mapped_caps = unmapped
│
└── Step 6: Confidence summary
    - Count high/medium/low from all used mappings
```

#### Stage Determination Logic
```python
def _determine_domain_stage(caps):
    """
    Progressive: must complete lower stages first.
    "Complete" = >= 70% of stage's capabilities score >= 50%.
    """
    by_stage = group_caps_by_stage(caps)
    achieved = "1 quickwins"
    
    for stage in STAGE_ORDER:
        stage_caps = by_stage.get(stage, [])
        if not stage_caps:
            continue  # no caps for this stage in this domain
        
        passing = count(c for c in stage_caps if c.score >= 50.0)
        ratio = passing / len(stage_caps)
        
        if ratio >= 0.70:
            achieved = stage
        else:
            break  # progressive — can't skip
    
    return achieved
```

#### Output Schema
```python
{
    "overall_score": 62.5,            # float 0-100
    "overall_stage": "1 quickwins",   # lowest domain stage
    "overall_stage_label": "Quick Wins",
    
    "domains": {
        "data_protection": {
            "display_name": "Data Protection",
            "score": 75.0,
            "stage": "2 foundational",
            "stage_label": "Foundational",
            "capabilities": [
                {
                    "capability_id": "block_public_access",
                    "capability_name": "Block Public Access",
                    "stage": "1 quickwins",
                    "score": 100.0,
                    "pass_count": 5,
                    "fail_count": 0,
                    "total_checks": 5,
                    "status": "assessed",  # assessed | partial | not_assessed
                    "guidance": "Have you blocked public access...?"
                },
                ...
            ],
            "total_checks": 45,
            "passed_checks": 33,
        },
        "identity_access": { ... },
        "logging_monitoring": { ... },
        "resilience": { ... },
        "network_security": { ... },
    },
    
    "unmapped_capabilities": [
        {
            "capability_id": "evaluate_resilience_posture_aws_resilience_hub",
            "capability_name": "Evaluate Resilience Posture - AWS Resilience Hub",
            "stage": "1 quickwins",
            "guidance": "Have you analyzed critical workloads...?"
        },
        ...  # 38 capabilities without check mappings
    ],
    
    "confidence_summary": {"high": 29, "medium": 54, "low": 419},
    
    "coverage": {
        "total_capabilities": 78,
        "assessed": 25,
        "partial": 8,
        "not_assessed": 45,
        "mapping_coverage_pct": 42.3,
    }
}
```

#### Graceful Degradation
- JSON files not found -> return None (report falls back to focused mode)
- No findings match any mapping -> return empty assessment (all scores 0)
- Only weak mappings -> capabilities marked "partial", lower weight

#### Edge Cases
| Case | Handling |
|------|----------|
| 1 capability maps to 2+ domains | Score counted in EACH domain (correct semantically) |
| 1 check maps to 2+ capabilities | Finding contributes to all mapped capabilities |
| No findings at all | _empty_assessment() -> all zeros |
| All PASS | Scores near 100, high stage |
| 83% low confidence mappings | Weighted at 0.2-0.3, flagged in confidence_summary |
| Capability has no domain (in mappings) | Excluded from domain rollup, listed in unmapped |

---

## 4. Data Flow Changes

### 4.1 Orchestrator: `graph_orchestator.py`

#### Changes to `report_node()` (line 693-706)

**BEFORE:**
```python
report_data = build_report_data(...)
rag_context = _fetch_rag_for_report(...)
report_data["rag_context"] = rag_context
agent = ReportAgent(...)
path = agent.run(report_context=report_data)
```

**AFTER:**
```python
report_data = build_report_data(...)
rag_context = _fetch_rag_for_report(...)
report_data["rag_context"] = rag_context

# --- Maturity Assessment (NEW) ---
try:
    from agents.report_module.maturity_engine import MaturityEngine
    engine = MaturityEngine(
        mappings_path="RAG/data/normalized/maturity_mappings.json",
        capabilities_path="RAG/data/normalized/maturity_capabilities.json",
    )
    report_data["maturity_assessment"] = engine.assess(
        report_data.get("raw_pre_findings", [])
    )
    print(f"[report_node] Maturity: score={report_data['maturity_assessment']['overall_score']}, "
          f"stage={report_data['maturity_assessment']['overall_stage_label']}")
except Exception as e:
    print(f"[report_node] Maturity assessment failed: {e}")
    report_data["maturity_assessment"] = None

agent = ReportAgent(...)
path = agent.run(report_context=report_data)
```

**No changes to:** `build_report_data()`, `_fetch_rag_for_report()`

---

## 5. Report Agent Changes

### 5.1 File: `agents/report_agent.py`

#### New imports
```python
from agents.report_module.chart_util import make_domain_radar, make_stage_progress
```

#### `_validate_input()` — No change
- `maturity_assessment` is NOT in required keys (optional, graceful degradation)

#### `run()` — Modified flow
```python
def run(self, data=None, report_context=None, **_kwargs):
    # ... existing validation ...
    
    pre = data["pre"]
    post = data["post"]
    env = data["environment"]
    scope = data["scope"]
    
    # NEW: Maturity data
    maturity = data.get("maturity_assessment")
    report_mode = self._determine_report_mode(maturity)
    
    # Derived data
    pass_findings, fail_findings = self._split_by_status(data["raw_pre_findings"])
    charts = self._make_charts(pre, self.output_dir)
    
    # NEW: Maturity charts (only for full/partial modes)
    maturity_charts = {}
    if maturity and report_mode in ("full", "partial"):
        maturity_charts = self._make_maturity_charts(maturity, report_mode, self.output_dir)
    
    # NEW: Maturity-based score (fallback to old score)
    if maturity and report_mode in ("full", "partial"):
        score = round(maturity["overall_score"])
    else:
        score = self._calc_score(pre, post)
    
    report_id = self._make_report_id(scope["date"])
    
    # LLM content
    llm = self._write_llm_sections(data, pre, post, env, scope, pass_findings, fail_findings)
    
    # NEW: Maturity LLM sections
    if maturity and report_mode in ("full", "partial"):
        llm.update(self._write_maturity_llm_sections(maturity, report_mode))
    
    # ... existing enrich findings ...
    
    # Render
    template_ctx = {
        "env": env, "scope": scope, "pre": pre, "post": post,
        "score": score, "report_id": report_id,
        "charts": charts, "table": data["findings_table"],
        "success": success, "failed": failed, "manual": manual,
        "llm": llm,
        # NEW
        "maturity": maturity,
        "maturity_charts": maturity_charts,
        "report_mode": report_mode,
    }
    return self._render(template_ctx)
```

#### New method: `_determine_report_mode()`
```python
def _determine_report_mode(self, maturity: dict | None) -> str:
    """Determine report mode based on maturity coverage."""
    if maturity is None:
        return "focused"
    
    coverage = maturity.get("coverage", {})
    assessed = coverage.get("assessed", 0)
    
    domains_with_data = sum(
        1 for d in maturity.get("domains", {}).values()
        if any(c["status"] in ("assessed", "partial") for c in d.get("capabilities", []))
    )
    
    if domains_with_data >= 3 and assessed >= 15:
        return "full"
    elif domains_with_data >= 1 and assessed >= 3:
        return "partial"
    else:
        return "focused"
```

#### New method: `_make_maturity_charts()`
```python
def _make_maturity_charts(self, maturity, report_mode, output_dir):
    chart_dir = os.path.join(output_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    result = {}
    
    domain_scores = {
        d["display_name"]: d["score"]
        for d in maturity["domains"].values()
    }
    
    # Radar chart only for full mode (misleading with <3 domains)
    if report_mode == "full":
        radar_path = os.path.join(chart_dir, "maturity_radar.png")
        make_domain_radar(domain_scores, radar_path)
        result["radar"] = "charts/maturity_radar.png"
    
    # Stage progress for both full and partial
    stage_path = os.path.join(chart_dir, "stage_progress.png")
    make_stage_progress(maturity, stage_path)
    result["stage_progress"] = "charts/stage_progress.png"
    
    return result
```

#### New method: `_write_maturity_llm_sections()`
```python
def _write_maturity_llm_sections(self, maturity, report_mode):
    sections = {}
    rag = self._build_rag_knowledge(...)  # reuse existing
    
    sections["maturity_overview"] = self.llm.write_maturity_overview(maturity)
    
    sections["domain_assessments"] = {}
    for domain_id, ddata in maturity["domains"].items():
        # Skip domains with no data in partial mode
        if report_mode == "partial":
            has_data = any(c["status"] != "not_assessed" for c in ddata["capabilities"])
            if not has_data:
                continue
        sections["domain_assessments"][domain_id] = (
            self.llm.write_domain_assessment(ddata["display_name"], ddata)
        )
    
    sections["maturity_roadmap"] = self.llm.write_maturity_roadmap(maturity)
    
    return sections
```

---

## 6. LLM Prompts

### 6.1 File: `agents/report_module/llm_writer.py`

#### `write_maturity_overview(maturity_data: dict) -> str`
```
PROMPT STRUCTURE:
- Role: Senior Cloud Security Consultant
- Task: Viet tong quan danh gia muc do truong thanh bao mat
- Input data:
  - Overall score: {overall_score}/100
  - Overall stage: {overall_stage_label}
  - Domain summary: {domain: score, stage} for each domain
  - Coverage: {assessed}/{total} capabilities
- Output requirements:
  1. Nhan dinh tong the (1 doan): muc truong thanh hien tai, y nghia
  2. Diem manh (bullet points): domains/capabilities dat diem cao
  3. Diem yeu (bullet points): domains/capabilities can cai thien
  4. Coverage disclaimer: bao nhieu % duoc danh gia
- Word limit: 350
- Constraints: khong dung ngoi thu nhat, khong suy doan ngoai data
```

#### `write_domain_assessment(domain_name: str, domain_data: dict) -> str`
```
PROMPT STRUCTURE:
- Role: AWS Security Domain Expert
- Task: Viet danh gia cho linh vuc "{domain_name}"
- Input data:
  - Domain score: {score}/100
  - Domain stage: {stage_label}
  - Capabilities list with scores and status
  - Pass/fail counts
- Output requirements:
  1. Trang thai hien tai (2-3 cau): muc truong thanh cua domain
  2. Nang luc dat chuan (bullet points): capabilities co score >= 70
  3. Nang luc can cai thien (bullet points): capabilities co score < 50
  4. Huong hanh dong (2-3 cau): de nang len stage tiep theo
- Word limit: 250
- Constraints: chi dua tren data, cu the theo capability name
```

#### `write_maturity_roadmap(maturity_data: dict) -> str`
```
PROMPT STRUCTURE:
- Role: Security Strategy Advisor
- Task: Viet lo trinh nang cap maturity
- Input data:
  - Current stage per domain
  - Unmapped capabilities (chua duoc danh gia)
  - Low-scoring capabilities
  - Coverage gaps
- Output requirements:
  1. Uu tien truoc mat (Quick Wins chua dat): capabilities de dat nhat
  2. Muc tieu trung han (Foundational): capabilities can thiet
  3. Pham vi mo rong: domains/capabilities chua scan
  4. Khuyen nghi quy trinh: tan suat danh gia, nguoi chiu trach nhiem
- Word limit: 350
- Constraints: gan voi capability cu the, thuc te, khong chung chung
```

---

## 7. Charts

### 7.1 File: `agents/report_module/chart_util.py`

#### `make_domain_radar(domain_scores: dict, output_path: str)`
```python
"""
5-axis radar/spider chart.

Input:  {"Data Protection": 75.0, "Identity & Access": 60.0, ...}
Output: PNG file

Design:
- matplotlib polar projection
- 5 axes, equally spaced
- Score range 0-100
- Fill area with semi-transparent color
- Reference circles at 25, 50, 75 (stage thresholds)
- Labels at each axis with domain name + score
- Title: "Maturity Profile"
- figsize: (6, 6), dpi: 150
- Color scheme: blue fill (#1E88E5, alpha=0.25), dark blue line
"""
```

#### `make_stage_progress(maturity_data: dict, output_path: str)`
```python
"""
4 horizontal bars showing stage completion.

Input: maturity_data dict (full output from MaturityEngine)
Logic:
  For each stage in STAGE_ORDER:
    - Count capabilities in that stage across all domains
    - Count how many score >= 50%
    - completion_pct = passing / total

Output: PNG with 4 horizontal bars

Design:
- 4 rows: Quick Wins / Foundational / Efficient / Optimized
- Each bar shows completion % (0-100%)
- Color: green (>= 70%, stage achieved), yellow (30-70%), red (<30%)
- Current overall stage highlighted
- figsize: (8, 3), dpi: 150
"""
```

---

## 8. Template Changes

### 8.1 File: `agents/report_module/template.py`

#### Strategy: Conditional Sections
Template uses `report_mode` variable to switch between sections:

```html
{% if report_mode == "full" %}
    <!-- FULL MATURITY TEMPLATE -->
{% elif report_mode == "partial" %}
    <!-- PARTIAL MATURITY TEMPLATE -->
{% else %}
    <!-- FOCUSED FINDINGS TEMPLATE (existing + small addition) -->
{% endif %}
```

#### New CSS Classes
```css
/* Maturity-specific styles */
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
.stage-quickwins   { background: #E8F5E9; color: #2E7D32; }
.stage-foundational { background: #E3F2FD; color: #1565C0; }
.stage-efficient    { background: #F3E5F5; color: #7B1FA2; }
.stage-optimized    { background: #FFF8E1; color: #F57F17; }

.domain-card {
    border: 1px solid #ddd; border-radius: 8px;
    padding: 20px; margin: 15px 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
.domain-card-header {
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 15px;
}
.domain-score {
    font-size: 2em; font-weight: bold;
}
.score-high   { color: #2E7D32; }  /* >= 70 */
.score-medium { color: #E65100; }  /* 40-69 */
.score-low    { color: #C62828; }  /* < 40 */

.capability-table { width: 100%; border-collapse: collapse; }
.capability-table td { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }
.cap-score-bar {
    height: 8px; border-radius: 4px; background: #e0e0e0;
}
.cap-score-fill {
    height: 100%; border-radius: 4px;
}
```

#### Cover Page Changes (all modes)
```html
<!-- FULL mode -->
<div class="cover-page">
    <h1>BAO CAO DANH GIA MUC DO TRUONG THANH BAO MAT AWS</h1>
    ...
    <div class="score-box">
        <span class="stage-badge stage-{{ maturity.overall_stage | replace(' ', '') }}">
            {{ maturity.overall_stage_label }}
        </span>
        <br>
        <span class="score-number">{{ score }}</span><span>/ 100</span>
        <br><small>Diem Truong thanh Bao mat</small>
    </div>
</div>

<!-- PARTIAL mode -->
<div class="cover-page">
    <h1>BAO CAO DANH GIA BAO MAT AWS</h1>
    <div class="maturity-banner warning">
        Danh gia mot phan — {{ maturity.coverage.assessed }}/{{ maturity.coverage.total_capabilities }}
        nang luc duoc kiem tra
    </div>
    ...
</div>

<!-- FOCUSED mode -->
<!-- Giu nguyen cover hien tai -->
```

#### Section 5: Full Maturity Template
```html
{% if report_mode == "full" %}
<h1>5. Danh gia Muc do Truong thanh Bao mat</h1>

<h2>5.1 Tong quan</h2>
<div class="maturity-banner">
    <strong>Muc do Truong thanh:</strong>
    <span class="stage-badge stage-{{ maturity.overall_stage | replace(' ', '') }}">
        {{ maturity.overall_stage_label }}
    </span>
    — Diem tong: <strong>{{ maturity.overall_score }}/100</strong>
    <br>
    <small>
        {{ maturity.coverage.assessed }} nang luc da duoc danh gia /
        {{ maturity.coverage.total_capabilities }} tong cong
        ({{ maturity.coverage.mapping_coverage_pct }}% coverage)
    </small>
</div>

{{ llm.maturity_overview }}

<!-- Radar chart -->
<div style="text-align:center">
    <img src="{{ maturity_charts.radar }}" style="max-width:500px">
</div>

<!-- Stage progress -->
<div style="text-align:center">
    <img src="{{ maturity_charts.stage_progress }}" style="max-width:700px">
</div>

<!-- Per-domain sections -->
{% for domain_id, domain in maturity.domains.items() %}
<h2>5.{{ loop.index + 1 }} {{ domain.display_name }}</h2>
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
    
    <!-- LLM narrative -->
    {{ llm.domain_assessments[domain_id] }}
    
    <!-- Capability table -->
    {% if domain.capabilities %}
    <table class="capability-table">
    <thead><tr><th>Nang luc</th><th>Stage</th><th>Score</th><th>PASS</th><th>FAIL</th><th>Trang thai</th></tr></thead>
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
    {% else %}
    <p><em>Khong co du lieu danh gia cho linh vuc nay.</em></p>
    {% endif %}
</div>
{% endfor %}

<!-- Unmapped capabilities -->
{% if maturity.unmapped_capabilities %}
<h2>5.{{ maturity.domains | length + 2 }} Nang luc Chua Duoc Danh gia</h2>
<p>Cac nang luc sau khong co kiem tra tu dong tuong ung (Prowler checks).
   Can danh gia thu cong hoac mo rong pham vi cong cu.</p>
<table class="styled-table">
<thead><tr><th>Nang luc</th><th>Stage</th><th>Huong dan Danh gia</th></tr></thead>
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
{% endif %}

<!-- Maturity Roadmap -->
<h2>5.{{ maturity.domains | length + 3 }} Lo trinh Cai thien</h2>
{{ llm.maturity_roadmap }}

{% endif %}
```

#### Section 5: Partial Maturity Template
```html
{% if report_mode == "partial" %}
<h1>5. Danh gia Bao mat theo Nang luc (Pham vi Gioi han)</h1>

<div class="maturity-banner warning">
    <strong>Luu y:</strong> Danh gia nay chi bao gom
    {{ maturity.coverage.assessed }} / {{ maturity.coverage.total_capabilities }} nang luc bao mat.
    Ket qua khong dai dien cho muc do truong thanh toan dien cua he thong.
    De co danh gia day du, can mo rong pham vi quet sang cac dich vu khac.
</div>

<h2>5.1 Tong quan</h2>
<!-- Stage progress (no radar) -->
<div style="text-align:center">
    <img src="{{ maturity_charts.stage_progress }}" style="max-width:700px">
</div>

{{ llm.maturity_overview }}

<!-- Summary table -->
<table class="styled-table">
<thead><tr><th>Linh vuc</th><th>Score</th><th>Capabilities</th><th>Trang thai</th></tr></thead>
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
{% for domain_id, domain in maturity.domains.items() %}
{% set has_data = domain.capabilities | selectattr("status", "ne", "not_assessed") | list | length > 0 %}
{% if has_data %}
<h2>5.{{ loop.index + 1 }} {{ domain.display_name }}</h2>
<div class="domain-card">
    <!-- Same as full mode but without radar reference -->
    ...domain card content...
</div>
{% endif %}
{% endfor %}

<!-- Scope not covered -->
<h2>Pham vi Chua Duoc Danh gia</h2>
<p>Cac linh vuc sau chua nam trong pham vi quet:</p>
<ul>
{% for domain_id, domain in maturity.domains.items() %}
{% if not domain.capabilities %}
<li><strong>{{ domain.display_name }}</strong> — chua co du lieu</li>
{% endif %}
{% endfor %}
</ul>

{{ llm.maturity_roadmap }}
{% endif %}
```

#### Focused Mode: Small Addition
```html
{% if report_mode == "focused" and maturity and maturity.coverage.assessed > 0 %}
<!-- Insert after Section 3 (Pre-remediation) -->
<h2>3.4 Anh xa Nang luc Bao mat</h2>
<p>Cac kiem tra da thuc hien duoc anh xa toi cac nang luc bao mat
   trong Mo hinh Truong thanh AWS:</p>
<table class="styled-table">
<thead><tr><th>Nang luc</th><th>Linh vuc</th><th>Stage</th><th>Ket qua</th></tr></thead>
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
<p><em>De co danh gia muc do truong thanh day du, can mo rong pham vi
   quet sang nhieu dich vu va kiem tra hon.</em></p>
{% endif %}
```

---

## 9. TOC per Mode

### Full Mode TOC
```
1. Tom tat Dieu hanh
2. Pham vi va Phuong phap
3. Ket qua Kiem tra (Pre-remediation — condensed)
4. Bang Chi tiet Phat hien
5. Danh gia Muc do Truong thanh Bao mat   ← PRIMARY
   5.1 Tong quan
   5.2 Data Protection
   5.3 Identity & Access Management
   5.4 Logging & Monitoring
   5.5 Resilience
   5.6 Network Security
   5.7 Nang luc Chua Duoc Danh gia
   5.8 Lo trinh Cai thien
6. Khac phuc (Remediation)                ← SECONDARY
7. Hau Khac phuc
8. Khuyen nghi Chien luoc
```

### Partial Mode TOC
```
1. Tom tat Dieu hanh
2. Pham vi va Phuong phap
3. Ket qua Kiem tra
4. Bang Chi tiet Phat hien
5. Danh gia Bao mat theo Nang luc (Pham vi Gioi han)
   5.1 Tong quan
   5.2-5.N [Chi domains co data]
   5.N+1 Pham vi Chua Danh gia
   5.N+2 Lo trinh
6. Khac phuc
7. Hau Khac phuc
8. Khuyen nghi
```

### Focused Mode TOC
```
1-7. GIU NGUYEN nhu hien tai
+ 3.4 Anh xa Nang luc Bao mat (bang nho)
```

---

## 10. Implementation Order

```
Phase 1: maturity_engine.py           CREATE   ~250 lines   standalone, testable
Phase 2: graph_orchestator.py         MODIFY   ~15 lines    inject maturity data
Phase 3: chart_util.py                MODIFY   ~100 lines   2 new chart functions
Phase 4: llm_writer.py                MODIFY   ~150 lines   3 new LLM prompts
Phase 5: report_agent.py              MODIFY   ~80 lines    mode logic + integration
Phase 6: template.py                  MODIFY   ~300 lines   adaptive template sections
```

### Dependency Graph
```
Phase 1 (engine) ← standalone
Phase 2 (orchestrator) ← depends on Phase 1
Phase 3 (charts) ← standalone
Phase 4 (LLM prompts) ← standalone
Phase 5 (report_agent) ← depends on Phase 1, 3, 4
Phase 6 (template) ← depends on Phase 5
```

### Parallel Work Possible
```
[Phase 1] ──┐
[Phase 3] ──┼──→ [Phase 5] ──→ [Phase 6]
[Phase 4] ──┘
[Phase 2] ← can be done anytime after Phase 1
```

---

## 11. Verification Plan

### Unit Tests
1. **MaturityEngine**: mock findings → verify output structure, scores, stage determination
2. **Charts**: generate PNGs → verify file exists and size > 0
3. **Mode selection**: test threshold logic with different coverage levels

### Integration Tests
4. **Full pipeline**: run with existing scan data → verify maturity_assessment in report_data
5. **Template rendering**: verify HTML output contains maturity sections
6. **PDF export**: verify maturity charts render in PDF

### Edge Case Tests
7. **Empty findings**: verify focused mode, no crash
8. **All PASS**: verify high scores, correct stage
9. **Single check**: verify focused mode with capability mapping table
10. **RAG unavailable + maturity available**: verify maturity works independently

### Manual Verification
11. Open generated HTML in browser → visual check radar chart, domain cards
12. Compare report with AWS Security Maturity Model website
13. Verify Vietnamese text quality in LLM outputs
