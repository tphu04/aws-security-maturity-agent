import { cn } from "@/lib/utils";
import type { ReactNode } from "react";
import type {
  Severity, NodeStatus, ToolStatus, ApprovalDecision,
  VerificationStatus, AwsConnectionStatus, RunStatus, FindingStatus,
  RemediationStatus, ToolCategory,
} from "@/types/pdca";
import {
  ShieldAlert, ShieldCheck, ShieldQuestion, AlertTriangle, Flame,
  CheckCircle2, Loader2, XCircle, Clock, PauseCircle, MinusCircle,
  Hand, Wifi, WifiOff, KeyRound, CircleDot, FileCheck2, Wrench, BookOpen, Search,
} from "lucide-react";

export function Pill({
  children, className, tone = "neutral", icon,
}: {
  children: ReactNode;
  className?: string;
  tone?: "neutral" | "primary" | "success" | "warning" | "danger" | "info" | "violet";
  icon?: ReactNode;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-bg-elevated/70 text-text-secondary ring-border-muted",
    primary: "bg-brand-cyan/10 text-brand-cyan ring-brand-cyan/30",
    success: "bg-status-success/10 text-status-success ring-status-success/30",
    warning: "bg-status-warning/10 text-status-warning ring-status-warning/30",
    danger:  "bg-status-error/10 text-status-error ring-status-error/30",
    info:    "bg-severity-info/10 text-severity-info ring-severity-info/30",
    violet:  "bg-brand-violet/10 text-brand-violet ring-brand-violet/30",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

// ───────── severity ─────────
const sevMap: Record<Severity, { tone: Parameters<typeof Pill>[0]["tone"]; icon: ReactNode; label: string }> = {
  info:     { tone: "info",    icon: <ShieldQuestion className="h-3 w-3" />, label: "info" },
  low:      { tone: "info",    icon: <ShieldCheck    className="h-3 w-3" />, label: "low" },
  medium:   { tone: "warning", icon: <AlertTriangle  className="h-3 w-3" />, label: "medium" },
  high:     { tone: "danger",  icon: <ShieldAlert    className="h-3 w-3" />, label: "high" },
  critical: { tone: "danger",  icon: <Flame          className="h-3 w-3" />, label: "critical" },
};
export function SeverityPill({ severity, className }: { severity: Severity; className?: string }) {
  const s = sevMap[severity];
  return <Pill tone={s.tone} icon={s.icon} className={className}>{s.label}</Pill>;
}

// ───────── node status ─────────
const nodeMap: Record<NodeStatus, { tone: Parameters<typeof Pill>[0]["tone"]; icon: ReactNode; label: string; spin?: boolean }> = {
  queued:    { tone: "neutral", icon: <Clock        className="h-3 w-3" />, label: "queued" },
  running:   { tone: "info",    icon: <Loader2      className="h-3 w-3 animate-spin" />, label: "running", spin: true },
  completed: { tone: "success", icon: <CheckCircle2 className="h-3 w-3" />, label: "completed" },
  skipped:   { tone: "neutral", icon: <MinusCircle  className="h-3 w-3" />, label: "skipped" },
  failed:    { tone: "danger",  icon: <XCircle      className="h-3 w-3" />, label: "failed" },
  waiting:   { tone: "warning", icon: <PauseCircle  className="h-3 w-3" />, label: "waiting" },
};
export function NodeStatusPill({ status, className }: { status: NodeStatus; className?: string }) {
  const s = nodeMap[status];
  return <Pill tone={s.tone} icon={s.icon} className={className}>{s.label}</Pill>;
}

// ───────── tool status ─────────
const toolMap: Record<ToolStatus, { tone: Parameters<typeof Pill>[0]["tone"]; icon: ReactNode; label: string }> = {
  queued:  { tone: "neutral", icon: <Clock        className="h-3 w-3" />, label: "queued" },
  running: { tone: "info",    icon: <Loader2      className="h-3 w-3 animate-spin" />, label: "running" },
  success: { tone: "success", icon: <CheckCircle2 className="h-3 w-3" />, label: "success" },
  failed:  { tone: "danger",  icon: <XCircle      className="h-3 w-3" />, label: "failed" },
};
export function ToolStatusPill({ status, className }: { status: ToolStatus; className?: string }) {
  const s = toolMap[status];
  return <Pill tone={s.tone} icon={s.icon} className={className}>{s.label}</Pill>;
}

// ───────── tool category ─────────
const catMap: Record<ToolCategory, { tone: Parameters<typeof Pill>[0]["tone"]; icon: ReactNode; label: string }> = {
  scanner:     { tone: "primary", icon: <Search    className="h-3 w-3" />, label: "scanner" },
  knowledge:   { tone: "violet",  icon: <BookOpen  className="h-3 w-3" />, label: "knowledge" },
  remediation: { tone: "warning", icon: <Wrench    className="h-3 w-3" />, label: "remediation" },
};
export function ToolCategoryPill({ category, className }: { category: ToolCategory; className?: string }) {
  const c = catMap[category];
  return <Pill tone={c.tone} icon={c.icon} className={className}>{c.label}</Pill>;
}

// ───────── decision ─────────
const decisionMap: Record<ApprovalDecision, { tone: Parameters<typeof Pill>[0]["tone"]; label: string; icon?: ReactNode }> = {
  pending:         { tone: "warning", label: "pending",        icon: <Clock        className="h-3 w-3" /> },
  approved:        { tone: "success", label: "approved",       icon: <CheckCircle2 className="h-3 w-3" /> },
  rejected:        { tone: "danger",  label: "rejected",       icon: <XCircle      className="h-3 w-3" /> },
  skipped:         { tone: "neutral", label: "skipped",        icon: <MinusCircle  className="h-3 w-3" /> },
  manual_required: { tone: "violet",  label: "manual",         icon: <Hand         className="h-3 w-3" /> },
};
export function DecisionPill({ decision, className }: { decision: ApprovalDecision; className?: string }) {
  const d = decisionMap[decision];
  return <Pill tone={d.tone} icon={d.icon} className={className}>{d.label}</Pill>;
}

// ───────── verification ─────────
const verifMap: Record<VerificationStatus, { tone: Parameters<typeof Pill>[0]["tone"]; label: string; icon: ReactNode }> = {
  passed:          { tone: "success", label: "passed",  icon: <CheckCircle2 className="h-3 w-3" /> },
  failed:          { tone: "danger",  label: "failed",  icon: <XCircle      className="h-3 w-3" /> },
  partial:         { tone: "warning", label: "partial", icon: <AlertTriangle className="h-3 w-3" /> },
  manual_required: { tone: "violet",  label: "manual",  icon: <Hand         className="h-3 w-3" /> },
};
export function VerificationPill({ status, className }: { status: VerificationStatus; className?: string }) {
  const v = verifMap[status];
  return <Pill tone={v.tone} icon={v.icon} className={className}>{v.label}</Pill>;
}

// ───────── AWS connection ─────────
const awsMap: Record<AwsConnectionStatus, { tone: Parameters<typeof Pill>[0]["tone"]; label: string; icon: ReactNode }> = {
  not_connected:       { tone: "neutral", label: "not connected",        icon: <WifiOff   className="h-3 w-3" /> },
  validating:          { tone: "info",    label: "validating",           icon: <Loader2   className="h-3 w-3 animate-spin" /> },
  connected:           { tone: "success", label: "connected",            icon: <Wifi      className="h-3 w-3" /> },
  error:               { tone: "danger",  label: "error",                icon: <XCircle   className="h-3 w-3" /> },
  expired_session:     { tone: "warning", label: "session expired",      icon: <KeyRound  className="h-3 w-3" /> },
  missing_permissions: { tone: "warning", label: "missing permissions",  icon: <KeyRound  className="h-3 w-3" /> },
};
export function AwsStatusPill({ status, className }: { status: AwsConnectionStatus; className?: string }) {
  const s = awsMap[status];
  return <Pill tone={s.tone} icon={s.icon} className={className}>{s.label}</Pill>;
}

// ───────── run status ─────────
const runMap: Record<RunStatus, { tone: Parameters<typeof Pill>[0]["tone"]; label: string }> = {
  idle:                   { tone: "neutral", label: "idle" },
  validating_environment: { tone: "info",    label: "validating env" },
  planning:               { tone: "info",    label: "planning" },
  submitting_scan:        { tone: "info",    label: "submitting scan" },
  polling:                { tone: "info",    label: "polling" },
  collecting_findings:    { tone: "info",    label: "collecting" },
  evaluating_risk:        { tone: "info",    label: "evaluating risk" },
  waiting_for_approval:   { tone: "warning", label: "awaiting approval" },
  executing_remediation:  { tone: "info",    label: "executing" },
  verifying:              { tone: "info",    label: "verifying" },
  generating_report:      { tone: "info",    label: "generating report" },
  completed:              { tone: "success", label: "completed" },
  failed:                 { tone: "danger",  label: "failed" },
};
export function RunStatusPill({ status, className }: { status: RunStatus; className?: string }) {
  const s = runMap[status];
  return <Pill tone={s.tone} icon={<CircleDot className="h-3 w-3" />} className={className}>{s.label}</Pill>;
}

// ───────── finding status / remediation ─────────
const findMap: Record<FindingStatus, { tone: Parameters<typeof Pill>[0]["tone"]; label: string }> = {
  PASS:   { tone: "success", label: "pass" },
  FAIL:   { tone: "danger",  label: "fail" },
  MANUAL: { tone: "violet",  label: "manual" },
};
export function FindingStatusPill({ status, className }: { status: FindingStatus; className?: string }) {
  const s = findMap[status];
  return <Pill tone={s.tone} icon={<FileCheck2 className="h-3 w-3" />} className={className}>{s.label}</Pill>;
}

const remMap: Record<RemediationStatus, { tone: Parameters<typeof Pill>[0]["tone"]; label: string }> = {
  open:        { tone: "warning", label: "open" },
  remediated:  { tone: "success", label: "remediated" },
  manual:      { tone: "violet",  label: "manual" },
  failed:      { tone: "danger",  label: "failed" },
};
export function RemediationStatusPill({ status, className }: { status: RemediationStatus; className?: string }) {
  const s = remMap[status];
  return <Pill tone={s.tone} className={className}>{s.label}</Pill>;
}

// ───────── code chip ─────────
export function Code({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <code className={cn(
      "inline-flex items-center rounded-md border border-border/60 bg-bg-elevated/60 px-1.5 py-0.5 font-mono text-[11px] text-text-primary/90",
      className,
    )}>
      {children}
    </code>
  );
}
