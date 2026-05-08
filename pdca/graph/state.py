"""PDCAState V3 — Phase C: scan flow split, error accumulation, snapshot fields.

Canonical location: `pdca.graph.state`. `pdca.state` re-exports for backward compat.

Key invariants (decision #25, #27, #28):
- `raw_findings` no reducer — `scan_submit` resets `[]`, `scan_poll` does explicit
  `state.get("raw_findings", []) + new_raw` append.
- `normalized_findings` no reducer — set ONCE by `scan_collect`.
- `pending_jobs`/`completed_jobs` no reducer — each scan node returns full new dict.
- `scan_started_at` is wall-clock (`time.time()`) — survives SqliteSaver restart.
- `errors` accumulates via `operator.add`.
"""

import operator
from typing import TypedDict, List, Dict, Optional, Any, Annotated, NotRequired


class AWSEnvironment(TypedDict):
    account_id: str
    region: str
    identity_arn: str
    buckets: List[str]
    _degraded: NotRequired[bool]


class AssessmentPlan(TypedDict):
    groups_to_scan: List[str]
    target_services: List[str]
    checks_to_scan: List[str]
    reasoning: str


class RemediationTask(TypedDict):
    task_id: str
    finding_id: str
    tool_name: str
    tool_params: Dict[str, Any]
    priority: int
    ai_reasoning: str


class ExecutionLog(TypedDict):
    task_id: str
    status: str
    output: str
    timestamp: str


class ScanJobMeta(TypedDict, total=False):
    """Metadata cho 1 scan job — giữ context để debug + retry."""
    task_type: str       # "group" | "checks" | "custom"
    task_value: str      # group name / check_ids joined / filename
    status: str          # "pending" | "completed" | "failed" | "timeout"


class PDCAState(TypedDict):
    # --- Identity ---
    run_id: str

    # --- Input ---
    performance_metrics: Dict[str, Any]
    user_request: str
    aws_context: Optional[AWSEnvironment]
    cycle_iteration: int

    # --- RAG availability ---
    rag_available: bool

    # --- RAG enrichment bundle (multi-query Q1+Q2+Q3 + control mappings) ---
    # Set ONCE bởi rag_enrich_node sau risk_evaluation. Dùng cho:
    # 1. operational_planning gắn ragSteps/ragEffort vào tasks
    # 2. report_node truyền vào ReportDataBuilder
    # 3. FE ToolTracePanel "Knowledge" tab
    rag_bundle: NotRequired[Dict[str, Any]]

    # --- Plan ---
    assessment_plan: Optional[AssessmentPlan]

    # --- DEPRECATED v1.4 — vestigial, sẽ xóa cuối Phase C ---
    scan_job_ids: List[str]

    # --- Scan flow (Phase C — no reducers, explicit replace semantic) ---
    raw_findings: List[Dict]
    normalized_findings: List[Dict]
    pending_jobs: Dict[str, ScanJobMeta]
    completed_jobs: Dict[str, ScanJobMeta]
    scan_started_at: float        # time.time() Unix epoch — survives restart
    scan_poll_count: int

    # --- Risk & Evaluation ---
    prioritized_findings: List[Dict]

    # --- Remediation ---
    remediation_tasks: List[RemediationTask]
    task_execution_plan: Dict[str, str]
    current_task_index: int

    # --- Execution ---
    execution_logs: Annotated[List[ExecutionLog], operator.add]
    pipeline_context: List[Dict]

    # --- Verification ---
    verification_results: Dict[str, Any]
    analysis_results: Dict[str, Any]

    # --- Snapshots (Phase C — decouple from filesystem) ---
    pre_scan_snapshot: Optional[Dict]
    post_scan_snapshot: Optional[Dict]

    # --- Report ---
    final_report: str

    # --- Error accumulation ---
    errors: Annotated[List[Dict], operator.add]

    # --- Observability resume context (Langfuse Phase F/I) ---
    _langfuse_parent_span_id: NotRequired[Optional[str]]
    _langfuse_trace_id: NotRequired[Optional[str]]
