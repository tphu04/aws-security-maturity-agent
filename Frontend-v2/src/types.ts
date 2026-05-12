// Trimmed types — only what the v2 UI consumes from the chatbot backend.
// Mirrors pdca/api/state_adapter.py output (RunSession projection).

export type Severity = "info" | "low" | "medium" | "high" | "critical";

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

export type GraphNodeName =
  | "environment" | "planning" | "scan_submit" | "scan_poll" | "scan_collect"
  | "risk_evaluation" | "operational_planning" | "review_task" | "reset_index"
  | "execution" | "verification" | "report";

export interface AwsEnvironment {
  status: string;
  accountMask: string;
  region: string;
  credentialType: string;
  lastValidatedAt: string;
  bucketsDiscovered: number;
  ragAvailable: boolean;
}

export interface GraphNode {
  name: GraphNodeName;
  status: string;
  startedAt?: string;
  durationMs?: number;
  inputSummary?: string;
  outputSummary?: string;
  pollIterations?: Array<{ index: number; pendingAfter: number; completedAfter: number; newFindings: number }>;
}

export interface ScanJob {
  id: string;
  taskType: string;
  taskValue: string;
  status: string;
  submittedAt: string;
  finishedAt?: string;
  resultCount?: number;
  totalChecks?: number;
  completedChecks?: number;
}

export interface Finding {
  id: string;
  prowlerCheckId: string;
  service: string;
  resource: string;
  region: string;
  title: string;
  description: string;
  severity: Severity;
  status: "PASS" | "FAIL" | "MANUAL";
  remediationStatus: string;
  recommendation: string;
}

export interface RagStep { order: number; type: string; snippet: string; prerequisite?: string }

export interface RemediationTask {
  id: string;
  findingId: string;
  findingTitle: string;
  severity: Severity;
  resource: string;
  toolName: string;
  toolCategory: string;
  manualOnly: boolean;
  proposedAction: string;
  expectedImpact: string;
  requiredAwsPermission: string;
  decision: "pending" | "approved" | "rejected" | "skipped" | "manual_required";
  toolParams: Record<string, unknown>;
  guardChecks?: { registeredTool: boolean; isRemediationCategory: boolean; notManualOnly: boolean };
  manualGuidance?: string;
  ragSteps?: RagStep[];
  ragEffort?: "low" | "medium" | "high";
  ragSideEffects?: string[];
  ragRollback?: string;
}

export interface ExecutionLog {
  taskId: string;
  toolName: string;
  status: string;
  message: string;
  durationMs: number;
  timestamp: string;
}

export interface VerificationResult {
  id: string;
  findingId: string;
  resource: string;
  toolName: string;
  beforeState: string;
  afterState: string;
  result: "passed" | "failed" | "partial" | "manual_required";
  timestamp: string;
}

export interface Report {
  filename: string;
  status: "pending" | "ready" | "failed";
  generatedAt?: string;
  runId: string;
  version?: string;
}

export interface RunSession {
  id: string;
  threadId: string;
  status: RunStatus;
  startedAt: string;
  durationMs: number;
  currentNode: GraphNodeName;
  awsEnvironment: AwsEnvironment;
  graphNodes: GraphNode[];
  scanJobs: ScanJob[];
  findings: Finding[];
  remediationTasks: RemediationTask[];
  executionLogs: ExecutionLog[];
  verifications: VerificationResult[];
  report: Report;
}

export interface QASource {
  checkId?: string;
  title: string;
  url?: string;
  snippet?: string;
  score?: number;
}

export interface IntentMeta {
  intent: "qa" | "scan" | "mixed";
  confidence: number;
  reason?: string;
  target_service?: string | null;
  finding_ref?: string | null;
}

// ───────────── UI line model ─────────────

export type LineKind =
  | "user"
  | "qa"
  | "event"
  | "approval"
  | "exec"
  | "error";

export type EventIcon = "▸" | "▶" | "✓" | "✗" | "⚠" | "⬢";

export interface BaseLine {
  id: string;
  ts: number;
  k: LineKind;
}

export interface UserLine extends BaseLine {
  k: "user";
  text: string;
}

export interface QaLine extends BaseLine {
  k: "qa";
  markdown: string;
  done: boolean;
  sources?: QASource[];
  intent?: IntentMeta;
}

export interface EventLine extends BaseLine {
  k: "event";
  icon: EventIcon;
  text: string;
  reasoning?: string;
  progress?: { done: number; total: number };
  tone?: "default" | "ok" | "warn" | "err" | "info";
}

export interface ApprovalLine extends BaseLine {
  k: "approval";
  task: RemediationTask;
  resolved?: "approved" | "rejected" | "skipped";
}

export interface ExecLine extends BaseLine {
  k: "exec";
  text: string;
  ok: boolean;
}

export interface ErrorLine extends BaseLine {
  k: "error";
  text: string;
}

export type LogLine = UserLine | QaLine | EventLine | ApprovalLine | ExecLine | ErrorLine;
