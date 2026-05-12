import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Cloud, ListChecks, Send, RefreshCw, Filter, AlertTriangle, Wrench,
  PlayCircle, ShieldCheck, FileText, Download, Eye,
  BookOpen, Sparkles, Search, FileSearch, MessageCircleQuestion,
  ChevronDown, ExternalLink,
} from "lucide-react";
import {
  Code, Pill, NodeStatusPill, SeverityPill, VerificationPill, DecisionPill,
} from "@/components/ui/status-pill";
import type {
  EnvironmentCheckCard, PlanningCard, ScanSubmittedCard, PollingCard,
  FindingsCollectedCard, RiskEvaluationCard, RemediationOfferCard,
  RemediationExecutionCard, VerificationCard, ReportReadyCard, RemediationTask,
  VerificationSummaryCard, VerificationSummaryItem, Finding, QAAnswerCard, SuggestActionCard, SuggestionChip,
} from "@/types/pdca";
import { cn } from "@/lib/utils";

function CardShell({
  icon, title, accent = "primary", children, className,
}: {
  icon: React.ReactNode;
  title: string;
  accent?: "primary" | "info" | "violet" | "warning" | "success" | "danger";
  children: React.ReactNode;
  className?: string;
}) {
  const accentBg: Record<string, string> = {
    primary: "bg-primary/15 text-primary ring-primary/30",
    info:    "bg-severity-info/15 text-severity-info ring-severity-info/30",
    violet:  "bg-brand-violet/15 text-brand-violet ring-brand-violet/30",
    warning: "bg-status-warning/15 text-status-warning ring-status-warning/30",
    success: "bg-status-success/15 text-status-success ring-status-success/30",
    danger:  "bg-status-error/15 text-status-error ring-status-error/30",
  };
  return (
    <Card className={cn("overflow-hidden", className)}>
      <div className="flex items-center gap-2.5 border-b border-border/50 px-4 py-2.5">
        <div className={cn("grid h-6 w-6 shrink-0 place-items-center rounded-md ring-1 ring-inset", accentBg[accent])}>
          <span className="[&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
        </div>
        <div className="text-sm font-semibold text-text-primary leading-snug">{title}</div>
      </div>
      <div className="p-4">{children}</div>
    </Card>
  );
}

function Field({ label, children, multiline = false }: { label: string; children: React.ReactNode; multiline?: boolean }) {
  if (multiline) {
    return (
      <div className="py-1 text-xs">
        <div className="text-text-muted">{label}</div>
        <div className="mt-1 whitespace-pre-wrap break-words text-left leading-relaxed text-text-primary">{children}</div>
      </div>
    );
  }
  return (
    <div className="flex items-baseline justify-between gap-3 py-1 text-xs">
      <div className="shrink-0 text-text-muted">{label}</div>
      <div className="min-w-0 flex-1 truncate text-right text-text-primary">{children}</div>
    </div>
  );
}

// ───────────── Environment ─────────────
export function EnvironmentCheckCardView({ card }: { card: EnvironmentCheckCard }) {
  return (
    <CardShell icon={<Cloud className="h-4 w-4" />} title="Environment checked" accent="primary">
      <div className="divide-y divide-border/40">
        <Field label="AWS credentials">{card.awsCredentials}</Field>
        <Field label="Account"><Code>{card.account}</Code></Field>
        <Field label="Region"><Code>{card.region}</Code></Field>
        <Field label="S3 buckets discovered"><span className="font-mono">{card.bucketsDiscovered}</span></Field>
        <Field label="RAG knowledge service">
          <Pill tone={card.ragAvailable ? "success" : "danger"}>{card.ragAvailable ? "available" : "unavailable"}</Pill>
        </Field>
        <Field label="Run ID"><Code>{card.runId}</Code></Field>
      </div>
    </CardShell>
  );
}

// ───────────── Planning ─────────────
export function PlanningCardView({ card }: { card: PlanningCard }) {
  return (
    <CardShell icon={<ListChecks className="h-4 w-4" />} title="Scan plan created" accent="info">
      <div className="divide-y divide-border/40">
        <Field label="Scanner">{card.scanner}</Field>
        <Field label="Provider">{card.provider}</Field>
        <Field label="Service scope">{card.scope}</Field>
        <Field label="Groups to scan">
          <div className="inline-flex flex-wrap justify-end gap-1">
            {card.groups.map((g) => <Code key={g}>{g}</Code>)}
          </div>
        </Field>
        <Field label="Specific checks">{card.specificChecks}</Field>
        <Field label="Expected output">{card.expectedOutput}</Field>
        <Field label="Next node"><Code>{card.nextNode}</Code></Field>
      </div>
    </CardShell>
  );
}

// ───────────── Scan submitted ─────────────
export function ScanSubmittedCardView({ card }: { card: ScanSubmittedCard }) {
  return (
    <CardShell icon={<Send className="h-4 w-4" />} title="Prowler scan job submitted" accent="info">
      <div className="divide-y divide-border/40">
        <Field label="API"><Code>{card.api}</Code></Field>
        <Field label="Group"><Code>{card.group}</Code></Field>
        <Field label="Job ID"><Code>{card.jobId}</Code></Field>
        <Field label="Status"><Pill tone="warning">{card.status}</Pill></Field>
        <Field label="Next node"><Code>{card.nextNode}</Code></Field>
      </div>
    </CardShell>
  );
}

// ───────────── Polling ─────────────
export function PollingCardView({ card }: { card: PollingCard }) {
  const pct = Math.round((card.progressDone / card.progressTotal) * 100);
  return (
    <CardShell icon={<RefreshCw className="h-4 w-4 animate-spin" />} title="Polling scanner job" accent="info">
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="rounded-md border border-border/60 bg-bg-elevated/40 px-2 py-1.5">
            <div className="text-text-muted">Job</div>
            <Code className="mt-0.5">{card.jobId}</Code>
          </div>
          <div className="rounded-md border border-border/60 bg-bg-elevated/40 px-2 py-1.5">
            <div className="text-text-muted">Poll #{card.pollCount}</div>
            <div className="font-mono text-text-primary">{card.status}</div>
          </div>
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px]">
            <span className="text-text-muted">Progress</span>
            <span className="font-mono text-text-primary">{card.progressDone} / {card.progressTotal} checks · {pct}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-elevated/60">
            <div className="h-full rounded-full bg-gradient-to-r from-primary to-severity-info shadow-[0_0_8px_hsl(var(--primary)/0.5)]" style={{ width: `${pct}%` }} />
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px]">
          <Pill tone="warning">pending {card.pendingJobs}</Pill>
          <Pill tone="success">completed {card.completedJobs}</Pill>
        </div>
      </div>
    </CardShell>
  );
}

// ───────────── Findings collected ─────────────
export function FindingsCollectedCardView({ card }: { card: FindingsCollectedCard }) {
  return (
    <CardShell icon={<Filter className="h-4 w-4" />} title="Findings collected and normalized" accent="primary">
      <div className="grid grid-cols-3 gap-2 text-center">
        {[
          { label: "raw", v: card.rawFindings, tone: "neutral" as const },
          { label: "fail", v: card.failed, tone: "danger" as const },
          { label: "pass", v: card.passed, tone: "success" as const },
        ].map((c) => (
          <div key={c.label} className="rounded-md border border-border/60 bg-bg-elevated/40 p-2">
            <div className="font-mono text-lg font-semibold text-text-primary">{c.v}</div>
            <div className="text-[10px] uppercase tracking-wider text-text-muted">{c.label}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
        <Field label="Manual review">{card.manual}</Field>
        <Field label="Node"><Code>{card.node}</Code></Field>
        <Field label="Snapshot">{card.snapshot}</Field>
      </div>
    </CardShell>
  );
}

// ───────────── Risk evaluation ─────────────
export function RiskEvaluationCardView({ card }: { card: RiskEvaluationCard }) {
  return (
    <CardShell icon={<AlertTriangle className="h-4 w-4" />} title="Risk evaluation completed" accent="warning">
      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          { label: "high",    v: card.high,         tone: "danger"  as const },
          { label: "medium",  v: card.medium,       tone: "warning" as const },
          { label: "low",     v: card.low,          tone: "info"    as const },
          { label: "manual",  v: card.manualReview, tone: "violet"  as const },
        ].map((c) => (
          <div key={c.label} className="rounded-md border border-border/60 bg-bg-elevated/40 p-2">
            <div className="font-mono text-lg font-semibold text-text-primary">{c.v}</div>
            <div className="text-[10px] uppercase tracking-wider text-text-muted">{c.label}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 text-center text-[11px] text-text-secondary">
        <span className="font-mono text-text-primary">{card.prioritized}</span> prioritized findings ready for remediation planning
      </div>
    </CardShell>
  );
}

// ───────────── Remediation offer ─────────────
export function RemediationOfferCardView({
  card, task, onApprove, onReject, onSkip,
}: {
  card: RemediationOfferCard;
  task: RemediationTask;
  onApprove?: () => void;
  onReject?: () => void;
  onSkip?: () => void;
}) {
  const isManual = task.manualOnly || task.decision === "manual_required";
  const pending = task.decision === "pending" || task.decision === "manual_required";
  const title = isManual ? "Manual remediation required" : "Remediation tool found";
  return (
    <CardShell icon={<Wrench className="h-4 w-4" />} title={title} accent="warning">
      <p className="mb-3 text-xs leading-relaxed text-text-secondary">
        {isManual ? "This finding needs manual handling:" : "I found a remediation tool for the"}{" "}
        <SeverityPill severity={task.severity} className="mx-1" /> finding{" "}
        <span className="font-medium text-text-primary">"{task.findingTitle}"</span>
        {!isManual && ". Do you want me to remediate it?"}
      </p>
      <div className="divide-y divide-border/40">
        <Field label="Finding">{task.findingTitle}</Field>
        <Field label="Resource"><Code>{task.resource}</Code></Field>
        <Field label="Tool name"><Code>{task.toolName}</Code></Field>
        <Field label="Tool category"><Pill tone="primary">{task.toolCategory}</Pill></Field>
        <Field label="Manual only">{isManual ? <Pill tone="violet">true</Pill> : <Pill tone="success">false</Pill>}</Field>
        <Field label="Requires approval"><Pill tone="warning">true</Pill></Field>
        {task.ragEffort && (
          <Field label="Effort">
            <Pill tone={task.ragEffort === "low" ? "success" : task.ragEffort === "high" ? "danger" : "warning"}>
              {task.ragEffort}
            </Pill>
          </Field>
        )}
        {task.compliance && task.compliance.length > 0 && (
          <Field label="Compliance">
            <div className="flex flex-wrap gap-1">
              {task.compliance.slice(0, 6).map((c, i) => (
                <span key={i} className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{c}</span>
              ))}
            </div>
          </Field>
        )}
        <Field label="LLM rationale" multiline>{task.proposedAction}</Field>
      </div>

      {task.ragSteps && task.ragSteps.length > 0 && (
        <div className="mt-3 rounded-md border border-border/60 bg-bg-elevated/40 p-2.5">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
            RAG remediation steps
          </div>
          <div className="space-y-1.5">
            {task.ragSteps.map((s, i) => (
              <div key={i} className="rounded border border-border/40 bg-bg-base/40 p-2">
                <div className="flex items-center gap-1.5 text-[10px] text-text-muted">
                  <span>step {s.order ?? i + 1}</span>
                  <Code>{s.type}</Code>
                </div>
                <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[10.5px] text-text-secondary">
                  {s.snippet}
                </pre>
              </div>
            ))}
          </div>
          {task.ragSideEffects && task.ragSideEffects.length > 0 && (
            <div className="mt-1.5 text-[10px] text-text-muted">
              <span className="font-semibold uppercase tracking-wider">side effects:</span>{" "}
              {task.ragSideEffects.join(", ")}
            </div>
          )}
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {pending ? (
          isManual ? (
            <Button size="sm" onClick={onSkip}>
              <ShieldCheck className="h-4 w-4" /> Confirm manual handling
            </Button>
          ) : (
            <Button size="sm" onClick={onApprove}>
              <ShieldCheck className="h-4 w-4" /> Yes, remediate
            </Button>
          )
        ) : (
          <Pill tone={task.decision === "approved" ? "success" : task.decision === "rejected" ? "danger" : "violet"}>
            {task.decision === "approved" ? "remediation approved" : task.decision === "rejected" ? "kept as finding" : "manual confirmed"}
          </Pill>
        )}
        <Button variant="outline" size="sm" onClick={onReject} disabled={!pending}>No, keep as finding</Button>
      </div>
      {isManual && (
        <p className="mt-2 text-[11px] text-text-muted">
          This item requires manual handling. Complete the guided action, then confirm so the backend can continue the HITL flow.
        </p>
      )}
    </CardShell>
  );
}

// ───────────── Remediation execution ─────────────
export function RemediationExecutionCardView({ card }: { card: RemediationExecutionCard }) {
  return (
    <CardShell icon={<PlayCircle className="h-4 w-4" />} title="Remediation approved and running" accent="info">
      <div className="divide-y divide-border/40">
        <Field label="Node"><Code>execution</Code></Field>
        <Field label="Tool"><Code>{card.toolName}</Code></Field>
        <Field label="Decision"><DecisionPill decision={card.decision} /></Field>
        <Field label="Status"><NodeStatusPill status={card.status === "running" ? "running" : card.status === "success" ? "completed" : "failed"} /></Field>
      </div>
      <div className="mt-3 rounded-md border border-border/60 bg-bg-elevated/40 p-3">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Guard checks</div>
        <ul className="space-y-1 text-[11px] text-text-secondary">
          <li className="flex items-center gap-1.5">{card.guardChecks.registeredTool ? "✅" : "❌"} Tool exists in registry</li>
          <li className="flex items-center gap-1.5">{card.guardChecks.isRemediationCategory ? "✅" : "❌"} Tool category is <Code className="ml-1">remediation</Code></li>
          <li className="flex items-center gap-1.5">{card.guardChecks.notManualOnly ? "✅" : "❌"} Tool is not manual-only</li>
        </ul>
      </div>
    </CardShell>
  );
}

// ───────────── Verification ─────────────
export function VerificationCardView({ card, finding }: { card: VerificationCard; finding?: Finding }) {
  return (
    <CardShell icon={<ShieldCheck className="h-4 w-4" />} title="Remediation verified" accent="success">
      <div className="divide-y divide-border/40">
        <Field label="Node"><Code>verification</Code></Field>
        {finding && <Field label="Finding">{finding.title}</Field>}
        <Field label="Verification"><VerificationPill status={card.verificationStatus} /></Field>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <div className="rounded-md border border-status-error/20 bg-status-error/5 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-status-error">Before</div>
          <div className="mt-0.5 text-[11px] leading-relaxed text-text-secondary">{card.beforeState}</div>
        </div>
        <div className="rounded-md border border-status-success/20 bg-status-success/5 p-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-status-success">After</div>
          <div className="mt-0.5 text-[11px] leading-relaxed text-text-secondary">{card.afterState}</div>
        </div>
      </div>
    </CardShell>
  );
}

export function VerificationSummaryCardView({
  card, findingsById,
}: {
  card: VerificationSummaryCard;
  findingsById: Record<string, Finding>;
}) {
  const visibleItems = card.items.filter((v) => hasVerificationIdentity(v, findingsById));
  const passed = visibleItems.filter((v) => v.verificationStatus === "passed").length;
  const failed = visibleItems.filter((v) => v.verificationStatus === "failed").length;
  const partial = visibleItems.filter((v) => v.verificationStatus === "partial").length;
  const manual = visibleItems.filter((v) => v.verificationStatus === "manual_required").length;
  const hiddenCount = card.items.length - visibleItems.length;
  const resourceAlias = buildResourceAliases(visibleItems.map((v) => v.resource));

  return (
    <CardShell icon={<ShieldCheck className="h-4 w-4" />} title="Remediation verification" accent="success">
      <div className="grid grid-cols-4 gap-2 text-center">
        {[
          { label: "passed", v: passed, tone: "text-status-success" },
          { label: "failed", v: failed, tone: "text-status-error" },
          { label: "partial", v: partial, tone: "text-status-warning" },
          { label: "manual", v: manual, tone: "text-brand-violet" },
        ].map((s) => (
          <div key={s.label} className="rounded-md border border-border/60 bg-bg-elevated/40 p-2">
            <div className={cn("font-mono text-lg font-semibold", s.tone)}>{s.v}</div>
            <div className="text-[10px] uppercase tracking-wider text-text-muted">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-3 divide-y divide-border/40 rounded-md border border-border/60 bg-bg-elevated/30">
        {visibleItems.map((v) => {
          const finding = findingsById[v.findingId];
          const maskedResource = resourceAlias.get(v.resource) ?? redactResource(v.resource);
          const checkLabel = finding?.prowlerCheckId || v.toolName;
          const title = finding?.title || humanizeCheckId(checkLabel);
          const resultText = verificationResultText(v.verificationStatus, v.afterState);
          return (
            <div key={v.id} className="grid gap-3 px-3 py-3 text-[11px] md:grid-cols-[1fr_auto]">
              <div className="min-w-0">
                <div className="font-medium leading-snug text-text-primary">{title}</div>
                <div className="mt-1 flex flex-wrap items-center gap-1.5 text-text-muted">
                  {checkLabel && (
                    <>
                      <span>Check</span>
                      <Code>{checkLabel}</Code>
                    </>
                  )}
                  {v.toolName && v.toolName !== checkLabel && <Code>{v.toolName}</Code>}
                  <span>Resource</span>
                  <Code>{maskedResource}</Code>
                </div>
                <div className="mt-2 grid gap-1.5 sm:grid-cols-[1fr_1fr_auto]">
                  <span className="rounded border border-status-error/25 bg-status-error/5 px-2 py-1.5">
                    <span className="font-semibold uppercase text-status-error">Before scan</span>{" "}
                    <span className="font-mono text-text-primary">{v.beforeState || "unknown"}</span>
                  </span>
                  <span className="rounded border border-status-success/25 bg-status-success/5 px-2 py-1.5">
                    <span className="font-semibold uppercase text-status-success">After re-scan</span>{" "}
                    <span className="font-mono text-text-primary">{v.afterState || "unknown"}</span>
                  </span>
                  <span className="rounded border border-border/60 bg-bg-base/40 px-2 py-1.5 text-text-secondary">
                    {resultText}
                  </span>
                </div>
              </div>
              <div className="flex items-start justify-end">
                <VerificationPill status={v.verificationStatus} />
              </div>
            </div>
          );
        })}
      </div>
      {hiddenCount > 0 && (
        <div className="mt-2 text-[10px] text-text-muted">
          Hidden {hiddenCount} generic verification row{hiddenCount === 1 ? "" : "s"} without check/resource context.
        </div>
      )}
    </CardShell>
  );
}

function hasVerificationIdentity(item: VerificationSummaryItem, findingsById: Record<string, Finding>): boolean {
  if (findingsById[item.findingId]?.prowlerCheckId) return true;
  if ((item.toolName || "").trim()) return true;
  const resource = (item.resource || "").trim();
  return Boolean(resource && resource.toLowerCase() !== "unknown");
}

function buildResourceAliases(resources: string[]): Map<string, string> {
  const out = new Map<string, string>();
  let i = 1;
  for (const raw of resources) {
    const r = (raw || "").trim();
    if (!r || out.has(r)) continue;
    out.set(r, `resource-${String(i).padStart(2, "0")}`);
    i += 1;
  }
  return out;
}

function redactResource(resource: string): string {
  const raw = (resource || "").trim();
  if (!raw) return "resource-redacted";
  return raw
    .replace(/\b\d{12}\b/g, (m) => `${m.slice(0, 4)}••••••${m.slice(-2)}`)
    .replace(/[a-f0-9]{8,}/gi, (m) => `${m.slice(0, 4)}…${m.slice(-4)}`);
}

function humanizeCheckId(value: string): string {
  return (value || "Verification")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function verificationResultText(status: VerificationSummaryItem["verificationStatus"], afterState: string): string {
  if (status === "passed") return `Verified: after re-scan is ${afterState || "PASS"}.`;
  if (status === "failed") return `Still failing: after re-scan is ${afterState || "FAIL"}.`;
  if (status === "manual_required") return "Manual confirmation required.";
  return "Partial change: review before/after values.";
}

// ───────────── QA answer ─────────────
export function QAAnswerCardView({
  card, onSourceClick,
}: {
  card: QAAnswerCard;
  onSourceClick?: (checkId?: string) => void;
}) {
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const sources = card.sources ?? [];
  const conf = card.intentMeta?.confidence;
  return (
    <CardShell
      icon={<BookOpen className="h-4 w-4" />}
      title="Knowledge answer"
      accent="violet"
    >
      <div className="prose prose-sm max-w-none text-slate-950
                      prose-headings:text-slate-950 prose-headings:font-semibold
                      prose-p:text-slate-900 prose-p:leading-relaxed
                      prose-strong:text-slate-950
                      prose-code:text-primary prose-code:bg-bg-elevated/60 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:hidden prose-code:after:hidden
                      prose-pre:bg-bg-elevated/40 prose-pre:border prose-pre:border-border/60 prose-pre:rounded-lg
                      prose-a:text-primary hover:prose-a:text-primary/80
                      prose-table:text-xs prose-th:text-slate-950 prose-td:text-slate-900
                      prose-li:text-slate-900 prose-ul:text-slate-900 prose-ol:text-slate-900 prose-marker:text-slate-900
                      prose-hr:border-border/60">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeHighlight]}
        >
          {card.markdown}
        </ReactMarkdown>
      </div>

      {sources.length > 0 && (
        <div className="mt-3 rounded-md border border-border/60 bg-bg-elevated/40">
          <button
            type="button"
            onClick={() => setSourcesOpen((v) => !v)}
            className="flex w-full items-center justify-between px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-700 hover:text-slate-950"
          >
            <span className="flex items-center gap-1.5">
              <FileSearch className="h-3 w-3" /> Sources · {sources.length}
            </span>
            <ChevronDown className={cn("h-3 w-3 transition-transform", sourcesOpen && "rotate-180")} />
          </button>
          {sourcesOpen && (
            <ul className="divide-y divide-border/40 border-t border-border/40">
              {sources.map((s, i) => (
                <li key={i}>
                  <button
                    type="button"
                    onClick={() => onSourceClick?.(s.checkId)}
                    className="flex w-full items-start gap-2 px-3 py-2 text-left text-[11px] hover:bg-bg-elevated/60"
                  >
                    <span className="mt-0.5 text-slate-600">{i + 1}.</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        {s.checkId && <Code>{s.checkId}</Code>}
                        <span className="truncate text-slate-950">{s.title}</span>
                      </div>
                      {s.snippet && (
                        <div className="mt-0.5 truncate text-slate-700">{s.snippet}</div>
                      )}
                    </div>
                    {typeof s.score === "number" && (
                      <span className="shrink-0 font-mono text-slate-700">{s.score.toFixed(2)}</span>
                    )}
                    {s.url && <ExternalLink className="h-3 w-3 shrink-0 text-slate-700" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {typeof conf === "number" && (
        <div className="mt-2 flex items-center justify-end gap-1.5 text-[10px] text-text-muted">
          <Sparkles className="h-3 w-3" />
          <span>intent: <span className="font-mono">{card.intentMeta?.classified}</span> · confidence <span className="font-mono">{conf.toFixed(2)}</span></span>
        </div>
      )}
    </CardShell>
  );
}

// ───────────── Suggestion chips ─────────────
const CHIP_ICON: Record<NonNullable<SuggestionChip["icon"]>, React.ReactNode> = {
  scan: <Search className="h-3.5 w-3.5" />,
  qa: <MessageCircleQuestion className="h-3.5 w-3.5" />,
  report: <FileText className="h-3.5 w-3.5" />,
  evidence: <FileSearch className="h-3.5 w-3.5" />,
};

const CHIP_TONE: Record<SuggestionChip["intent"], string> = {
  qa: "border-brand-violet/40 hover:bg-brand-violet/10 hover:text-brand-violet",
  scan: "border-primary/40 hover:bg-primary/10 hover:text-primary",
  mixed: "border-border hover:bg-bg-elevated/60",
};

export function SuggestActionCardView({
  card, onChipClick,
}: {
  card: SuggestActionCard;
  onChipClick?: (chip: SuggestionChip) => void;
}) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card/40 px-4 py-3">
      {card.prompt && (
        <div className="mb-2 text-xs text-text-secondary">{card.prompt}</div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {card.chips.map((chip, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onChipClick?.(chip)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border bg-bg-elevated/40 px-3 py-1.5 text-[11.5px] text-text-secondary transition-colors",
              CHIP_TONE[chip.intent],
            )}
          >
            {chip.icon && CHIP_ICON[chip.icon]}
            <span>{chip.label}</span>
          </button>
        ))}
      </div>
      <div className="mt-2 text-[10px] text-text-muted">
        Câu hỏi của bạn hơi mơ hồ — chọn 1 hành động hoặc gõ rõ hơn.
      </div>
    </div>
  );
}

// ───────────── Report ready ─────────────
export function ReportReadyCardView({ card, onPreview, onDownload }: {
  card: ReportReadyCard; onPreview?: () => void; onDownload?: () => void;
}) {
  return (
    <CardShell icon={<FileText className="h-4 w-4" />} title="PDF report ready" accent="primary">
      <div className="divide-y divide-border/40">
        <Field label="Node"><Code>report</Code></Field>
        <Field label="Filename"><Code>{card.filename}</Code></Field>
      </div>
      <div className="mt-3">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Includes</div>
        <div className="flex flex-wrap gap-1.5">
          {card.includes.map((s) => (
            <span key={s} className="rounded-md border border-border/60 bg-bg-elevated/40 px-2 py-0.5 text-[11px] text-text-secondary">{s}</span>
          ))}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button size="sm" onClick={onPreview}><Eye className="h-4 w-4" /> Preview Report</Button>
        <Button variant="outline" size="sm" onClick={onDownload}><Download className="h-4 w-4" /> Download PDF</Button>
      </div>
    </CardShell>
  );
}
