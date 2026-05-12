// Adapters: backend payloads → FE domain types.
// Keep this layer pure so we can swap in /v1/runs (Sprint 2+) without
// touching any view component.

import type {
  AwsEnvironment,
  Finding,
  RunHistoryRow,
  RunStatus,
  ScanJob,
  Severity,
  FindingStatus,
  Report,
} from "@/types/pdca";
import type { BackendEnvironment, BackendJob, BackendRunListItem } from "./api";

// ─── ScanJob ─────────────────────────────────────────────────────────

const STATUS_MAP: Record<string, ScanJob["status"]> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  timeout: "timeout",
  cancelled: "cancelled",
};

const TASK_TYPE_MAP: Record<string, ScanJob["taskType"]> = {
  group: "group",
  custom_file: "custom",
  checks: "checks",
};

function epochToIso(sec?: number | null): string | undefined {
  if (sec == null) return undefined;
  return new Date(sec * 1000).toISOString();
}

export function jobToScanJob(job: BackendJob): ScanJob {
  const taskType = TASK_TYPE_MAP[job.task_type] ?? "group";
  return {
    id: job.job_id,
    apiEndpoint:
      taskType === "group"   ? "POST /v1/scan/group" :
      taskType === "checks"  ? "POST /v1/scan/checks" :
                               "POST /v1/scan/custom",
    httpMethod: "POST",
    taskType,
    taskValue: job.task_value,
    status: STATUS_MAP[job.status] ?? "pending",
    submittedAt: epochToIso(job.submitted_time) ?? new Date().toISOString(),
    finishedAt: epochToIso(job.end_time),
    resultCount: Array.isArray(job.result) ? job.result.length : undefined,
  };
}

// ─── Findings ─────────────────────────────────────────────────────────

// Prowler OCSF severity_id → FE Severity.
const OCSF_SEVERITY: Record<number, Severity> = {
  1: "info",
  2: "low",
  3: "medium",
  4: "high",
  5: "critical",
  6: "critical",
};

const FE_SEVERITY: Record<string, Severity> = {
  INFORMATIONAL: "info",
  LOW: "low",
  MEDIUM: "medium",
  HIGH: "high",
  CRITICAL: "critical",
};

function pickSeverity(raw: any): Severity {
  if (typeof raw?.severity_id === "number") {
    return OCSF_SEVERITY[raw.severity_id] ?? "info";
  }
  const s = String(raw?.severity ?? "").toUpperCase();
  return FE_SEVERITY[s] ?? "info";
}

function pickStatus(raw: any): FindingStatus {
  // OCSF: status_code / status_id; Prowler also writes "status_code": "PASS"|"FAIL"|"MANUAL"
  const code = String(raw?.status_code ?? raw?.status ?? "").toUpperCase();
  if (code === "PASS" || code === "FAIL" || code === "MANUAL") return code;
  // status_id 1=PASS 2=FAIL fallback.
  if (raw?.status_id === 1) return "PASS";
  if (raw?.status_id === 2) return "FAIL";
  return "MANUAL";
}

function pickResource(raw: any): { resource: string; region: string; service: string } {
  const r = raw?.resources?.[0] ?? raw?.resource ?? {};
  return {
    resource: String(r?.uid ?? r?.name ?? r?.resource_arn ?? raw?.resource_id ?? "unknown"),
    region:   String(r?.region ?? raw?.region ?? raw?.cloud?.region ?? ""),
    service:  String(r?.cloud_partition ?? r?.type ?? raw?.service_name ?? raw?.service ?? "aws"),
  };
}

function pickCheckId(raw: any): string {
  return String(
    raw?.metadata?.event_code ??
    raw?.finding_info?.uid ??
    raw?.check_id ??
    raw?.unmapped?.check_id ??
    "unknown_check",
  );
}

function pickTitle(raw: any): string {
  return String(
    raw?.finding_info?.title ??
    raw?.metadata?.product?.name ??
    raw?.check_title ??
    pickCheckId(raw),
  );
}

function pickDescription(raw: any): string {
  return String(
    raw?.finding_info?.desc ??
    raw?.message ??
    raw?.description ??
    "",
  );
}

function pickRecommendation(raw: any): string {
  return String(
    raw?.remediation?.desc ??
    raw?.unmapped?.remediation_recommendation ??
    raw?.recommendation ??
    "",
  );
}

// ─── Environment ──────────────────────────────────────────────────────

export function environmentFromBackend(env: BackendEnvironment): AwsEnvironment {
  return {
    status: env.status,
    accountMask: env.accountMask,
    region: env.region,
    credentialType: env.credentialType,
    lastValidatedAt: env.lastValidatedAt,
    bucketsDiscovered: env.bucketsDiscovered,
    ragAvailable: env.ragAvailable,
  };
}

// ─── Run history rows ─────────────────────────────────────────────────

const RUN_STATUS_FALLBACK: Record<string, RunStatus> = {
  idle: "idle",
  pending: "submitting_scan",
  running: "polling",
  completed: "completed",
  cancelled: "cancelled",
  failed: "failed",
};

export function runHistoryFromBackend(item: BackendRunListItem): RunHistoryRow {
  return {
    id: item.id,
    target: item.target,
    awsAccountMask: item.awsAccountMask,
    startedAt: item.startedAt,
    durationMs: item.durationMs,
    status: RUN_STATUS_FALLBACK[item.status] ?? "idle",
    findingsTotal: item.findingsTotal,
    remediated: item.remediated,
    reportStatus: (item.reportStatus ?? "pending") as Report["status"],
  };
}

export function findingsFromJob(job: BackendJob): Finding[] {
  if (!Array.isArray(job.result)) return [];
  return job.result.map((raw: any, i): Finding => {
    const r = pickResource(raw);
    return {
      id: `${job.job_id}-${i}`,
      prowlerCheckId: pickCheckId(raw),
      service: r.service,
      resource: r.resource,
      region: r.region,
      title: pickTitle(raw),
      description: pickDescription(raw),
      severity: pickSeverity(raw),
      status: pickStatus(raw),
      remediationStatus: "open",
      recommendation: pickRecommendation(raw),
      evidenceIds: [],
    };
  });
}
