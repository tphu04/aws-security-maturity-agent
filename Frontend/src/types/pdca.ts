// ───────────── PDCA Prowler Agent — domain types ─────────────

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type GraphNodeName =
  | "environment"
  | "planning"
  | "scan_submit"
  | "scan_poll"
  | "scan_collect"
  | "risk_evaluation"
  | "operational_planning"
  | "review_task"
  | "reset_index"
  | "execution"
  | "verification"
  | "report";

export type NodeStatus =
  | "queued"
  | "running"
  | "completed"
  | "skipped"
  | "failed"
  | "waiting";

export type RunStatus =
  | "idle"
  | "validating_environment"
  | "planning"
  | "submitting_scan"
  | "polling"
  | "collecting_findings"
  | "evaluating_risk"
  | "waiting_for_approval"
  | "executing_remediation"
  | "verifying"
  | "generating_report"
  | "completed"
  | "failed";

export type ToolCategory = "scanner" | "knowledge" | "remediation";
export type ToolStatus = "queued" | "running" | "success" | "failed";

export type FindingStatus = "PASS" | "FAIL" | "MANUAL";
export type RemediationStatus = "open" | "remediated" | "manual" | "failed";

export type ApprovalDecision =
  | "pending"
  | "approved"
  | "rejected"
  | "skipped"
  | "manual_required";

export type VerificationStatus = "passed" | "failed" | "partial" | "manual_required";

export type AwsConnectionStatus =
  | "not_connected"
  | "validating"
  | "connected"
  | "error"
  | "expired_session"
  | "missing_permissions";

// ───────────── Graph nodes ─────────────

export interface PollIteration {
  index: number;
  startedAt: string;
  durationMs: number;
  pendingAfter: number;
  completedAfter: number;
  newFindings: number;
}

export interface GraphNode {
  name: GraphNodeName;
  status: NodeStatus;
  startedAt?: string;
  durationMs?: number;
  inputSummary?: string;
  outputSummary?: string;
  errorCount?: number;
  checkpointed?: boolean;
  pollIterations?: PollIteration[]; // only for scan_poll
}

// ───────────── Scanner jobs ─────────────

export interface ScanJob {
  id: string;
  apiEndpoint: string; // e.g. POST /v1/scan/group
  httpMethod: "GET" | "POST";
  taskType: "group" | "checks" | "custom";
  taskValue: string;
  status: "pending" | "running" | "completed" | "failed" | "timeout";
  submittedAt: string;
  finishedAt?: string;
  resultCount?: number;
  totalChecks?: number;
  completedChecks?: number;
}

// ───────────── Tool calls ─────────────

export interface ToolCall {
  id: string;
  name: string;            // e.g. s3_block_account_public_access
  category: ToolCategory;
  manualOnly: boolean;
  status: ToolStatus;
  inputPayload: Record<string, unknown>;
  outputSummary?: string;
  returnType: "dict";
  timestamp: string;
  durationMs?: number;
  relatedGraphNode?: GraphNodeName;
  relatedFindingId?: string;
}

// ───────────── Evidence ─────────────

export type EvidenceKind = "scanner_job" | "finding" | "remediation" | "verification";

export interface BaseEvidence {
  id: string;
  kind: EvidenceKind;
  timestamp: string;
  sourceNode?: GraphNodeName;
  sourceTool?: string;
  relatedFindingId?: string;
  relatedMessageId?: string;
}

export interface ScannerJobEvidence extends BaseEvidence {
  kind: "scanner_job";
  jobId: string;
  apiEndpoint: string;
  httpMethod: "GET" | "POST";
  taskType: ScanJob["taskType"];
  taskValue: string;
  status: ScanJob["status"];
  resultCount?: number;
}

export interface FindingEvidence extends BaseEvidence {
  kind: "finding";
  prowlerCheckId: string;
  service: string;
  resource: string;
  region: string;
  status: FindingStatus;
  severity: Severity;
  snippet: string;
}

export interface RemediationEvidence extends BaseEvidence {
  kind: "remediation";
  toolName: string;
  awsAction: string;
  resource: string;
  beforeState: string;
  afterState: string;
  verificationStatus: VerificationStatus;
  decision: ApprovalDecision;
}

export interface VerificationEvidence extends BaseEvidence {
  kind: "verification";
  prowlerCheckId: string;
  result: "PASS" | "FAIL" | "MANUAL";
  snippet: string;
}

export type Evidence =
  | ScannerJobEvidence
  | FindingEvidence
  | RemediationEvidence
  | VerificationEvidence;

// ───────────── Findings ─────────────

export interface Finding {
  id: string;
  prowlerCheckId: string;
  service: string;
  resource: string;
  region: string;
  title: string;
  description: string;
  severity: Severity;
  status: FindingStatus;
  remediationStatus: RemediationStatus;
  recommendation: string;
  evidenceIds: string[];
  ragKnowledgeContext?: string;
  remediationTaskId?: string;
  cve?: string;
}

// ───────────── Remediation tasks ─────────────

export interface RagRemediationStep {
  order: number;
  type: "cli" | "iac" | "console" | "other";
  snippet: string;
  prerequisite?: string;
}

export interface CapabilityTheme {
  domain: string;
  narrative: string;
  common_pitfalls?: string[];
  baselines?: string[];
  citations?: { source: string; url?: string; section?: string }[];
}

export interface RagRemediationGuide {
  check_id: string;
  steps?: RagRemediationStep[];
  rollback?: string;
  effort?: "low" | "medium" | "high";
  side_effects?: string[];
  citations?: { source: string; url?: string; section?: string }[];
}

export interface RagBundle {
  capabilityThemes: CapabilityTheme[];
  remediationGuides: RagRemediationGuide[];
  controlMappings: Record<string, unknown>;
  confidence: string;
  diagnostics?: Record<string, unknown>;
}

export interface RemediationTask {
  id: string;
  findingId: string;
  findingTitle: string;
  severity: Severity;
  resource: string;
  toolName: string;
  toolCategory: ToolCategory;
  manualOnly: boolean;
  proposedAction: string;
  expectedImpact: string;
  requiredAwsPermission: string;
  decision: ApprovalDecision;
  toolParams: Record<string, unknown>;
  guardChecks: {
    registeredTool: boolean;
    isRemediationCategory: boolean;
    notManualOnly: boolean;
  };
  // RAG-enriched (Phase 3 multi-query) — optional, populated when backend
  // calls /v1/retrieve/report_context successfully.
  ragSteps?: RagRemediationStep[];
  ragEffort?: "low" | "medium" | "high";
  ragSideEffects?: string[];
  ragRollback?: string;
  compliance?: string[];
}

export interface ExecutionLog {
  taskId: string;
  toolName: string;
  status: "skipped" | "running" | "success" | "failed" | "manual_required" | "error";
  message: string;
  durationMs: number;
  timestamp: string;
}

// ───────────── Verification ─────────────

export interface VerificationResult {
  id: string;
  findingId: string;
  resource: string;
  toolName: string;
  beforeState: string;
  afterState: string;
  result: VerificationStatus;
  rescanEvidenceId?: string;
  timestamp: string;
  executionLogTaskId?: string;
}

// ───────────── Report ─────────────

export type ReportSectionId =
  | "cover"
  | "executive_summary"
  | "aws_environment"
  | "scan_scope"
  | "methodology"
  | "graph_run_timeline"
  | "severity_summary"
  | "findings"
  | "evidence_appendix"
  | "remediation_decisions"
  | "verification_results"
  | "recommendations"
  | "conclusion";

export interface ReportSection {
  id: ReportSectionId;
  title: string;
  body: string; // pre-formatted markdown-lite
}

export interface Report {
  filename: string;
  status: "pending" | "ready" | "failed";
  generatedAt?: string;
  runId: string;
  version: string;
  sections: ReportSection[];
}

// ───────────── Chat / messages ─────────────

export type ChatRole = "user" | "assistant";

export type AssistantCardKind =
  | "environment_check"
  | "planning"
  | "scan_submitted"
  | "polling"
  | "findings_collected"
  | "risk_evaluation"
  | "remediation_offer"
  | "remediation_execution"
  | "verification"
  | "report_ready"
  | "text";

export interface AssistantCardBase {
  kind: AssistantCardKind;
}

export interface EnvironmentCheckCard extends AssistantCardBase {
  kind: "environment_check";
  awsCredentials: string;
  account: string;
  region: string;
  bucketsDiscovered: number;
  ragAvailable: boolean;
  runId: string;
}

export interface PlanningCard extends AssistantCardBase {
  kind: "planning";
  scanner: string;
  provider: string;
  scope: string;
  groups: string[];
  specificChecks: string;
  expectedOutput: string;
  nextNode: GraphNodeName;
}

export interface ScanSubmittedCard extends AssistantCardBase {
  kind: "scan_submitted";
  api: string;
  group: string;
  jobId: string;
  status: ScanJob["status"];
  nextNode: GraphNodeName;
}

export interface PollingCard extends AssistantCardBase {
  kind: "polling";
  jobId: string;
  pollCount: number;
  status: "running" | "completed" | "pending";
  progressDone: number;
  progressTotal: number;
  pendingJobs: number;
  completedJobs: number;
}

export interface FindingsCollectedCard extends AssistantCardBase {
  kind: "findings_collected";
  rawFindings: number;
  failed: number;
  passed: number;
  manual: number;
  node: GraphNodeName;
  snapshot: string;
}

export interface RiskEvaluationCard extends AssistantCardBase {
  kind: "risk_evaluation";
  high: number;
  medium: number;
  low: number;
  manualReview: number;
  prioritized: number;
}

export interface RemediationOfferCard extends AssistantCardBase {
  kind: "remediation_offer";
  taskId: string;
}

export interface RemediationExecutionCard extends AssistantCardBase {
  kind: "remediation_execution";
  taskId: string;
  toolName: string;
  decision: ApprovalDecision;
  status: "running" | "success" | "failed";
  guardChecks: RemediationTask["guardChecks"];
}

export interface VerificationCard extends AssistantCardBase {
  kind: "verification";
  findingId: string;
  beforeState: string;
  afterState: string;
  verificationStatus: VerificationStatus;
}

export interface ReportReadyCard extends AssistantCardBase {
  kind: "report_ready";
  filename: string;
  includes: string[];
}

export interface TextCard extends AssistantCardBase {
  kind: "text";
  text: string;
}

export type AssistantCard =
  | EnvironmentCheckCard
  | PlanningCard
  | ScanSubmittedCard
  | PollingCard
  | FindingsCollectedCard
  | RiskEvaluationCard
  | RemediationOfferCard
  | RemediationExecutionCard
  | VerificationCard
  | ReportReadyCard
  | TextCard;

export interface ChatMessage {
  id: string;
  role: ChatRole;
  timestamp: string;
  text?: string;
  cards?: AssistantCard[];
}

// ───────────── Run / session ─────────────

export interface AwsEnvironment {
  status: AwsConnectionStatus;
  accountMask: string;
  region: string;
  credentialType: string;
  lastValidatedAt: string;
  bucketsDiscovered: number;
  ragAvailable: boolean;
}

export interface RunSession {
  id: string;
  threadId: string;
  status: RunStatus;
  startedAt: string;
  durationMs: number;
  currentNode: GraphNodeName;
  checkpointer: "sqlite" | "memory";
  lastCheckpointAt: string;
  awsEnvironment: AwsEnvironment;
  graphNodes: GraphNode[];
  scanJobs: ScanJob[];
  toolCalls: ToolCall[];
  evidence: Evidence[];
  findings: Finding[];
  remediationTasks: RemediationTask[];
  executionLogs: ExecutionLog[];
  verifications: VerificationResult[];
  messages: ChatMessage[];
  report: Report;
  // RAG bundle from multi-query enrichment phase (optional).
  ragBundle?: RagBundle;
}

// History row (compact for table)
export interface RunHistoryRow {
  id: string;
  target: string;
  awsAccountMask: string;
  startedAt: string;
  durationMs: number;
  status: RunStatus;
  findingsTotal: number;
  remediated: number;
  reportStatus: Report["status"];
}
