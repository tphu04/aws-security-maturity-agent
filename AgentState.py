# state.py (PDCAState V2)
import operator
from typing import TypedDict, List, Dict, Optional, Any, Annotated


class AWSEnvironment(TypedDict):
    account_id: str
    region: str
    identity_arn: str


class AssessmentPlan(TypedDict):
    groups_to_scan: List[str]
    target_services: List[str]    # alias of groups_to_scan for verification/report nodes
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


class PDCAState(TypedDict):
    # Input
    performance_metrics: Dict[str, Any]
    user_request: str
    aws_context: Optional[AWSEnvironment]
    cycle_iteration: int

    # RAG System availability (set by environment_node)
    rag_available: bool

    # Plan
    assessment_plan: Optional[AssessmentPlan]

    # Scan
    scan_job_ids: List[str]
    raw_findings: List[Dict]

    # Risk & Evaluation
    prioritized_findings: List[Dict]

    # Remediation Plan
    remediation_tasks: List[RemediationTask]

    # Human-in-the-loop per-task fields
    task_execution_plan: Dict[str, str]  # {task_id: "approve" | "skip" | "dry"}
    current_task_index: int  # index of task being reviewed

    # Execution logs
    execution_logs: Annotated[List[ExecutionLog], operator.add]

    pipeline_context: List[Dict]

    # Verification
    verification_results: Dict[str, Any]

    # Analysis results (output of AnalysisAgent — single source of truth)
    analysis_results: Dict[str, Any]

    # Report
    final_report: str
