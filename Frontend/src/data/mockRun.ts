import type { RunSession, RunHistoryRow } from "@/types/pdca";

const base = Date.parse("2026-04-27T10:42:00Z");
const t = (offsetSec: number) => new Date(base + offsetSec * 1000).toISOString();

export const mockRun: RunSession = {
  id: "run_2026_0427_s3_001",
  threadId: "thread_s3_scan_001",
  status: "completed",
  startedAt: t(0),
  durationMs: 134_000,
  currentNode: "report",
  checkpointer: "sqlite",
  lastCheckpointAt: t(132),

  awsEnvironment: {
    status: "connected",
    accountMask: "1234••••••90",
    region: "ap-southeast-1",
    credentialType: "Access key",
    lastValidatedAt: t(0),
    bucketsDiscovered: 4,
    ragAvailable: true,
  },

  graphNodes: [
    { name: "environment", status: "completed", startedAt: t(0), durationMs: 1_200, inputSummary: "AWS profile · ap-southeast-1", outputSummary: "Account 1234••••••90 · 4 S3 buckets · RAG up", checkpointed: true },
    { name: "planning", status: "completed", startedAt: t(2), durationMs: 1_800, inputSummary: "Scan my S3 service for security issues.", outputSummary: "Provider AWS · Service S3 · Groups: s3 · Auto checks", checkpointed: true },
    { name: "scan_submit", status: "completed", startedAt: t(4), durationMs: 600, inputSummary: "POST /v1/scan/group { group: s3 }", outputSummary: "Job scan_job_aws_s3_001 queued", checkpointed: true },
    {
      name: "scan_poll",
      status: "completed",
      startedAt: t(5),
      durationMs: 96_000,
      inputSummary: "1 pending job",
      outputSummary: "0 pending · 28 checks complete",
      checkpointed: true,
      pollIterations: [
        { index: 1, startedAt: t(5),  durationMs: 24_000, pendingAfter: 1, completedAfter: 0, newFindings: 0 },
        { index: 2, startedAt: t(29), durationMs: 24_000, pendingAfter: 1, completedAfter: 0, newFindings: 9 },
        { index: 3, startedAt: t(53), durationMs: 24_000, pendingAfter: 1, completedAfter: 0, newFindings: 12 },
        { index: 4, startedAt: t(77), durationMs: 24_000, pendingAfter: 0, completedAfter: 1, newFindings: 7 },
      ],
    },
    { name: "scan_collect", status: "completed", startedAt: t(101), durationMs: 1_400, inputSummary: "28 raw findings", outputSummary: "5 FAIL · 21 PASS · 2 MANUAL", checkpointed: true },
    { name: "risk_evaluation", status: "completed", startedAt: t(103), durationMs: 5_800, inputSummary: "5 failed findings", outputSummary: "1 high · 2 medium · 2 low", checkpointed: true },
    { name: "operational_planning", status: "completed", startedAt: t(109), durationMs: 4_200, inputSummary: "5 prioritized findings", outputSummary: "1 remediation task ready · 4 manual review", checkpointed: true },
    { name: "review_task", status: "completed", startedAt: t(114), durationMs: 8_500, inputSummary: "Awaiting human approval", outputSummary: "Decision: approve", checkpointed: true },
    { name: "reset_index", status: "completed", startedAt: t(122), durationMs: 80, outputSummary: "current_task_index = 0", checkpointed: true },
    { name: "execution", status: "completed", startedAt: t(123), durationMs: 4_800, inputSummary: "s3_block_account_public_access", outputSummary: "Block Public Access enabled", checkpointed: true },
    { name: "verification", status: "completed", startedAt: t(128), durationMs: 3_400, inputSummary: "Re-run s3_bucket_public_access", outputSummary: "PASS — remediation verified", checkpointed: true },
    { name: "report", status: "completed", startedAt: t(132), durationMs: 1_900, inputSummary: "Compose DOCX", outputSummary: "pdca-prowler-s3-report.docx", checkpointed: true },
  ],

  scanJobs: [
    {
      id: "scan_job_aws_s3_001",
      apiEndpoint: "POST /v1/scan/group",
      httpMethod: "POST",
      taskType: "group",
      taskValue: "s3",
      status: "completed",
      submittedAt: t(4),
      finishedAt: t(101),
      resultCount: 28,
      totalChecks: 28,
      completedChecks: 28,
    },
  ],

  toolCalls: [
    { id: "tc1", name: "start_scan_by_group", category: "scanner", manualOnly: false, status: "success", inputPayload: { group: "s3" }, outputSummary: "job_id=scan_job_aws_s3_001", returnType: "dict", timestamp: t(4), durationMs: 480, relatedGraphNode: "scan_submit" },
    { id: "tc2", name: "check_job_status",    category: "scanner", manualOnly: false, status: "success", inputPayload: { job_id: "scan_job_aws_s3_001" }, outputSummary: "status=running · 9/28 checks", returnType: "dict", timestamp: t(29), durationMs: 220, relatedGraphNode: "scan_poll" },
    { id: "tc3", name: "check_job_status",    category: "scanner", manualOnly: false, status: "success", inputPayload: { job_id: "scan_job_aws_s3_001" }, outputSummary: "status=running · 21/28 checks", returnType: "dict", timestamp: t(53), durationMs: 230, relatedGraphNode: "scan_poll" },
    { id: "tc4", name: "check_job_status",    category: "scanner", manualOnly: false, status: "success", inputPayload: { job_id: "scan_job_aws_s3_001" }, outputSummary: "status=completed · 28/28 checks", returnType: "dict", timestamp: t(77), durationMs: 210, relatedGraphNode: "scan_poll" },
    { id: "tc5", name: "lookup_security_knowledge", category: "knowledge", manualOnly: false, status: "success", inputPayload: { check_ids: ["s3_bucket_public_access","s3_bucket_server_side_encryption_enabled"] }, outputSummary: "Returned 4 NIST/CIS context items", returnType: "dict", timestamp: t(108), durationMs: 1_120, relatedGraphNode: "operational_planning" },
    { id: "tc6", name: "s3_block_account_public_access", category: "remediation", manualOnly: false, status: "success", inputPayload: { resource_id: "s3://project-demo-public-assets", region: "ap-southeast-1" }, outputSummary: "BlockPublicAcls=true · IgnorePublicAcls=true · BlockPublicPolicy=true · RestrictPublicBuckets=true", returnType: "dict", timestamp: t(124), durationMs: 4_300, relatedGraphNode: "execution", relatedFindingId: "f1" },
  ],

  evidence: [
    { id: "ev1", kind: "scanner_job", timestamp: t(4),   sourceNode: "scan_submit",  jobId: "scan_job_aws_s3_001", apiEndpoint: "/v1/scan/group", httpMethod: "POST", taskType: "group", taskValue: "s3", status: "completed", resultCount: 28 },
    { id: "ev2", kind: "finding",     timestamp: t(101), sourceNode: "scan_collect", sourceTool: "check_job_status", relatedFindingId: "f1", prowlerCheckId: "s3_bucket_public_access",                  service: "S3", resource: "s3://project-demo-public-assets", region: "ap-southeast-1", status: "FAIL", severity: "high",    snippet: "Bucket public access setting indicates a potential public exposure risk." },
    { id: "ev3", kind: "finding",     timestamp: t(101), sourceNode: "scan_collect", sourceTool: "check_job_status", relatedFindingId: "f2", prowlerCheckId: "s3_bucket_server_side_encryption_enabled", service: "S3", resource: "s3://project-demo-logs",          region: "ap-southeast-1", status: "FAIL", severity: "medium",  snippet: "Bucket has no default server-side encryption configured." },
    { id: "ev4", kind: "finding",     timestamp: t(101), sourceNode: "scan_collect", sourceTool: "check_job_status", relatedFindingId: "f3", prowlerCheckId: "s3_bucket_logging_enabled",                service: "S3", resource: "s3://project-demo-assets",        region: "ap-southeast-1", status: "FAIL", severity: "medium",  snippet: "Server access logging is disabled — no audit trail." },
    { id: "ev5", kind: "finding",     timestamp: t(101), sourceNode: "scan_collect", sourceTool: "check_job_status", relatedFindingId: "f4", prowlerCheckId: "s3_bucket_versioning_enabled",             service: "S3", resource: "s3://project-demo-temp",          region: "ap-southeast-1", status: "FAIL", severity: "low",     snippet: "Versioning disabled — accidental deletes are unrecoverable." },
    { id: "ev6", kind: "finding",     timestamp: t(101), sourceNode: "scan_collect", sourceTool: "check_job_status", relatedFindingId: "f5", prowlerCheckId: "s3_bucket_lifecycle_policy",               service: "S3", resource: "s3://project-demo-archive",       region: "ap-southeast-1", status: "MANUAL", severity: "low", snippet: "Lifecycle policy present but retention should be reviewed by data owner." },
    { id: "ev7", kind: "remediation", timestamp: t(125), sourceNode: "execution",    relatedFindingId: "f1", toolName: "s3_block_account_public_access", awsAction: "PutPublicAccessBlock", resource: "s3://project-demo-public-assets", beforeState: "Public access block incomplete", afterState: "Block Public Access enabled (all 4 flags)", verificationStatus: "passed", decision: "approved" },
    { id: "ev8", kind: "verification",timestamp: t(130), sourceNode: "verification", relatedFindingId: "f1", prowlerCheckId: "s3_bucket_public_access", result: "PASS", snippet: "Re-scan confirms BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets are all true." },
  ],

  findings: [
    { id: "f1", prowlerCheckId: "s3_bucket_public_access",                  service: "S3", resource: "s3://project-demo-public-assets", region: "ap-southeast-1", title: "Public S3 bucket exposure risk",          description: "Bucket-level public access block is incomplete; objects may be exposed if a permissive bucket policy or ACL is added.", severity: "high",   status: "FAIL",   remediationStatus: "remediated", recommendation: "Enable S3 Block Public Access at the account and bucket level.",                                evidenceIds: ["ev2","ev7","ev8"], remediationTaskId: "task1" },
    { id: "f2", prowlerCheckId: "s3_bucket_server_side_encryption_enabled", service: "S3", resource: "s3://project-demo-logs",          region: "ap-southeast-1", title: "Server-side encryption not enabled",       description: "Bucket has no default SSE configured. New objects may be stored unencrypted.", severity: "medium", status: "FAIL", remediationStatus: "open",       recommendation: "Enable SSE-S3 (AES256) or SSE-KMS for the bucket.",                                            evidenceIds: ["ev3"], remediationTaskId: "task2" },
    { id: "f3", prowlerCheckId: "s3_bucket_logging_enabled",                service: "S3", resource: "s3://project-demo-assets",        region: "ap-southeast-1", title: "Access logging disabled",                  description: "Server access logging is disabled; no audit trail of object-level access.", severity: "medium", status: "FAIL", remediationStatus: "open",       recommendation: "Enable access logging into a dedicated log bucket.",                                          evidenceIds: ["ev4"], remediationTaskId: "task3" },
    { id: "f4", prowlerCheckId: "s3_bucket_versioning_enabled",             service: "S3", resource: "s3://project-demo-temp",          region: "ap-southeast-1", title: "Versioning disabled",                      description: "Versioning disabled — accidental deletes are unrecoverable.", severity: "low",    status: "FAIL", remediationStatus: "open",       recommendation: "Enable versioning to allow object recovery.",                                                  evidenceIds: ["ev5"], remediationTaskId: "task4" },
    { id: "f5", prowlerCheckId: "s3_bucket_lifecycle_policy",               service: "S3", resource: "s3://project-demo-archive",       region: "ap-southeast-1", title: "Lifecycle policy requires review",         description: "A lifecycle policy exists but retention windows must be reviewed by the data owner before automation.", severity: "low",    status: "MANUAL", remediationStatus: "manual", recommendation: "Review retention windows with the data owner.", evidenceIds: ["ev6"] },
  ],

  remediationTasks: [
    { id: "task1", findingId: "f1", findingTitle: "Public S3 bucket exposure risk",     severity: "high",   resource: "s3://project-demo-public-assets", toolName: "s3_block_account_public_access",        toolCategory: "remediation", manualOnly: false, proposedAction: "Enable S3 Block Public Access (account & bucket)", expectedImpact: "Prevents new and existing objects from being publicly accessible.",       requiredAwsPermission: "s3:PutBucketPublicAccessBlock", decision: "approved", toolParams: { resource_id: "s3://project-demo-public-assets", region: "ap-southeast-1" }, guardChecks: { registeredTool: true, isRemediationCategory: true, notManualOnly: true } },
    { id: "task2", findingId: "f2", findingTitle: "Server-side encryption not enabled", severity: "medium", resource: "s3://project-demo-logs",          toolName: "s3_enable_bucket_encryption",            toolCategory: "remediation", manualOnly: false, proposedAction: "Apply default SSE-S3 (AES256) encryption",         expectedImpact: "All new objects encrypted at rest with AWS-managed keys.",                requiredAwsPermission: "s3:PutEncryptionConfiguration", decision: "pending",  toolParams: { resource_id: "s3://project-demo-logs",          algorithm: "AES256" },              guardChecks: { registeredTool: true, isRemediationCategory: true, notManualOnly: true } },
    { id: "task3", findingId: "f3", findingTitle: "Access logging disabled",            severity: "medium", resource: "s3://project-demo-assets",        toolName: "s3_enable_access_logging",               toolCategory: "remediation", manualOnly: false, proposedAction: "Enable access logging to project-demo-logs",       expectedImpact: "All object-level access events captured for audit.",                      requiredAwsPermission: "s3:PutBucketLogging",            decision: "pending",  toolParams: { resource_id: "s3://project-demo-assets",        target_bucket: "project-demo-logs" }, guardChecks: { registeredTool: true, isRemediationCategory: true, notManualOnly: true } },
    { id: "task4", findingId: "f4", findingTitle: "Versioning disabled",                severity: "low",    resource: "s3://project-demo-temp",          toolName: "s3_enable_versioning",                   toolCategory: "remediation", manualOnly: false, proposedAction: "Enable bucket versioning",                         expectedImpact: "Recoverable object history; storage cost increases.",                     requiredAwsPermission: "s3:PutBucketVersioning",         decision: "pending",  toolParams: { resource_id: "s3://project-demo-temp" },                                          guardChecks: { registeredTool: true, isRemediationCategory: true, notManualOnly: true } },
    { id: "task5", findingId: "f5", findingTitle: "Lifecycle policy requires review",   severity: "low",    resource: "s3://project-demo-archive",       toolName: "s3_enable_object_lock",                  toolCategory: "remediation", manualOnly: true,  proposedAction: "Enable Object Lock (manual review required)",      expectedImpact: "Cannot be reversed once enabled — must be authorized by data owner.",      requiredAwsPermission: "s3:PutObjectLockConfiguration",  decision: "manual_required", toolParams: { resource_id: "s3://project-demo-archive" },                                       guardChecks: { registeredTool: true, isRemediationCategory: true, notManualOnly: false } },
  ],

  executionLogs: [
    { taskId: "task1", toolName: "s3_block_account_public_access", status: "success", message: "Public Access Block applied — all 4 flags = true.", durationMs: 4_200, timestamp: t(124) },
  ],

  verifications: [
    { id: "ver1", findingId: "f1", resource: "s3://project-demo-public-assets", toolName: "s3_block_account_public_access", beforeState: "Public access block incomplete · BlockPublicPolicy=false", afterState: "Block Public Access enabled · all 4 flags = true", result: "passed", rescanEvidenceId: "ev8", timestamp: t(130), executionLogTaskId: "task1" },
  ],

  messages: [
    { id: "m1", role: "user", timestamp: t(-2), text: "Scan my S3 service for security issues." },
    { id: "m2", role: "assistant", timestamp: t(1),   cards: [{ kind: "environment_check", awsCredentials: "found in Settings", account: "1234••••••90", region: "ap-southeast-1", bucketsDiscovered: 4, ragAvailable: true, runId: "run_2026_0427_s3_001" }] },
    { id: "m3", role: "assistant", timestamp: t(3),   cards: [{ kind: "planning", scanner: "Prowler", provider: "AWS", scope: "S3", groups: ["s3"], specificChecks: "Auto", expectedOutput: "normalized findings + DOCX report", nextNode: "scan_submit" }] },
    { id: "m4", role: "assistant", timestamp: t(5),   cards: [{ kind: "scan_submitted", api: "POST /v1/scan/group", group: "s3", jobId: "scan_job_aws_s3_001", status: "pending", nextNode: "scan_poll" }] },
    { id: "m5", role: "assistant", timestamp: t(53),  cards: [{ kind: "polling", jobId: "scan_job_aws_s3_001", pollCount: 3, status: "running", progressDone: 21, progressTotal: 28, pendingJobs: 1, completedJobs: 0 }] },
    { id: "m6", role: "assistant", timestamp: t(101), cards: [{ kind: "findings_collected", rawFindings: 28, failed: 5, passed: 21, manual: 2, node: "scan_collect", snapshot: "pre_scan_snapshot created" }] },
    { id: "m7", role: "assistant", timestamp: t(108), cards: [{ kind: "risk_evaluation", high: 1, medium: 2, low: 2, manualReview: 2, prioritized: 5 }] },
    { id: "m8", role: "assistant", timestamp: t(112), cards: [{ kind: "remediation_offer", taskId: "task1" }] },
    { id: "m9", role: "user",      timestamp: t(118), text: "Yes, remediate it." },
    { id: "m10", role: "assistant", timestamp: t(123), cards: [{ kind: "remediation_execution", taskId: "task1", toolName: "s3_block_account_public_access", decision: "approved", status: "running", guardChecks: { registeredTool: true, isRemediationCategory: true, notManualOnly: true } }] },
    { id: "m11", role: "assistant", timestamp: t(130), cards: [{ kind: "verification", findingId: "f1", beforeState: "Public access block incomplete", afterState: "Block Public Access enabled", verificationStatus: "passed" }] },
    { id: "m12", role: "assistant", timestamp: t(133), cards: [{ kind: "report_ready", filename: "pdca-prowler-s3-report.docx", includes: ["Executive summary","Scan scope","Findings","Evidence appendix","Remediation approval","Verification results","Recommendations"] }] },
  ],

  report: {
    filename: "pdca-prowler-s3-report.docx",
    status: "ready",
    generatedAt: t(133),
    runId: "run_2026_0427_s3_001",
    version: "v1.0",
    sections: [
      { id: "cover", title: "AWS S3 Security Scan Report", body: "Generated by PDCA Prowler Agent\n\nAWS account: 1234••••••90\nRegion: ap-southeast-1\nService: S3\nRun ID: run_2026_0427_s3_001\nScanner job: scan_job_aws_s3_001" },
      { id: "executive_summary", title: "Executive Summary", body: "Total checks: 28 — Failed: 5 — Manual: 2.\nHighest severity before remediation: HIGH (Public S3 bucket exposure risk).\nOpen severity after remediation: MEDIUM.\nRemediated findings: 1 — Manual review items: 2.\n\nOverall recommendation: address remaining medium-severity logging and encryption gaps within the next sprint, and review the lifecycle policy with the data owner before enabling Object Lock." },
      { id: "aws_environment", title: "AWS Environment", body: "Account: 1234••••••90\nRegion: ap-southeast-1\nProvider credential: Access key (least-privilege scanning role)\nDiscovered S3 buckets: 4" },
      { id: "scan_scope", title: "Scan Scope", body: "Scanner: Prowler · Provider: AWS · Service: S3\nGroups: s3 · Specific checks: Auto" },
      { id: "methodology", title: "Methodology", body: "1. Environment validation\n2. Plan generation\n3. Prowler scan submission via POST /v1/scan/group\n4. Polling /v1/job/{job_id} until terminal state\n5. Finding normalization (raw → normalized)\n6. Risk evaluation\n7. Human-approved remediation (HITL)\n8. Verification re-scan\n9. DOCX report generation" },
      { id: "graph_run_timeline", title: "Graph Run Timeline", body: "12 LangGraph nodes executed across 4 scan_poll iterations. Last checkpoint persisted to SQLite at 10:44:12 UTC." },
      { id: "severity_summary", title: "Severity Summary", body: "Critical: 0 · High: 1 (remediated) · Medium: 2 (open) · Low: 2 (1 open, 1 manual)" },
      { id: "findings", title: "Findings", body: "5 failed Prowler checks across 5 distinct S3 buckets — see appendix." },
      { id: "evidence_appendix", title: "Evidence Appendix", body: "8 evidence items captured (1 scanner job, 5 finding evidence, 1 remediation evidence, 1 verification evidence)." },
      { id: "remediation_decisions", title: "Remediation Decisions", body: "1 of 5 remediation tasks approved and executed. 1 manual-only task surfaced for review. 3 tasks remain pending user approval." },
      { id: "verification_results", title: "Verification Results", body: "Public S3 bucket exposure risk → PASS after remediation. All 4 BPA flags confirmed true via re-scan." },
      { id: "recommendations", title: "Recommendations", body: "• Approve and execute the encryption/logging tasks for project-demo-logs and project-demo-assets.\n• Review lifecycle policy with the data owner for project-demo-archive.\n• Schedule a recurring weekly Prowler scan with this agent.\n• Move the scanning credential to a least-privilege IAM role with read-only S3 access." },
      { id: "conclusion", title: "Conclusion", body: "PDCA Prowler Agent reduced the highest-severity exposure risk in this run, surfaced clear next actions, and produced an auditable trail of evidence and decisions." },
    ],
  },
};

// Empty run used as initial state when the backend is online.
// All arrays are empty so the UI starts clean; awsEnvironment gets
// overwritten by refreshEnvironment() once the chatbot probe succeeds.
export const emptyRun: RunSession = {
  id: "",
  threadId: "",
  status: "idle",
  startedAt: new Date().toISOString(),
  durationMs: 0,
  currentNode: "environment",
  checkpointer: "sqlite",
  lastCheckpointAt: new Date().toISOString(),
  awsEnvironment: {
    status: "not_connected",
    accountMask: "————",
    region: "—",
    credentialType: "—",
    lastValidatedAt: new Date().toISOString(),
    bucketsDiscovered: 0,
    ragAvailable: false,
  },
  graphNodes: [],
  scanJobs: [],
  toolCalls: [],
  evidence: [],
  findings: [],
  remediationTasks: [],
  executionLogs: [],
  verifications: [],
  messages: [],
  report: {
    filename: "",
    status: "pending",
    runId: "",
    version: "—",
    sections: [],
  },
};

export const mockHistory: RunHistoryRow[] = [
  { id: "run_2026_0427_s3_001", target: "AWS S3",     awsAccountMask: "1234••••••90", startedAt: t(0),         durationMs: 134_000, status: "completed",            findingsTotal: 5,  remediated: 1, reportStatus: "ready" },
  { id: "run_2026_0426_iam_002", target: "AWS IAM",    awsAccountMask: "1234••••••90", startedAt: "2026-04-26T03:14:00Z", durationMs: 218_000, status: "completed",            findingsTotal: 11, remediated: 4, reportStatus: "ready" },
  { id: "run_2026_0426_ec2_001", target: "AWS EC2",    awsAccountMask: "5921••••••40", startedAt: "2026-04-26T01:02:00Z", durationMs: 312_000, status: "waiting_for_approval", findingsTotal: 7,  remediated: 0, reportStatus: "pending" },
  { id: "run_2026_0425_full_001",target: "Full account",awsAccountMask:"1234••••••90", startedAt: "2026-04-25T18:55:00Z", durationMs: 905_000, status: "failed",               findingsTotal: 2,  remediated: 0, reportStatus: "failed" },
];
