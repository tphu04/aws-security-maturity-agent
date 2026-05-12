import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Code, SeverityPill, DecisionPill, ToolCategoryPill, Pill,
} from "@/components/ui/status-pill";
import { Eye, ShieldCheck, X, ClipboardCheck, Hand, AlertTriangle } from "lucide-react";
import type { RunSession, RemediationTask } from "@/types/pdca";

export function ApprovalsView({
  run, onApprove, onReject, onSkip,
}: {
  run: RunSession;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onSkip: (id: string) => void;
}) {
  const [active, setActive] = useState<RemediationTask | null>(null);

  const tasks = [...run.remediationTasks].sort((a, b) => {
    const order = { pending: 0, manual_required: 1, approved: 2, rejected: 3, skipped: 4 };
    return order[a.decision] - order[b.decision];
  });

  return (
    <PageShell
      run={run}
      title="Approval queue"
      subtitle="Human-in-the-loop: every remediation pauses here until you approve, reject, or mark as manual."
      actions={<Pill tone="warning"><ClipboardCheck className="h-3 w-3" /> {tasks.filter(t => t.decision === "pending" || t.decision === "manual_required").length} pending</Pill>}
    >
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {tasks.map((t) => (
          <Card key={t.id} className="overflow-hidden">
            <div className="flex items-start justify-between border-b border-border/60 px-4 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <SeverityPill severity={t.severity} />
                  <ToolCategoryPill category={t.toolCategory} />
                  {t.manualOnly && <Pill tone="violet"><Hand className="h-3 w-3" /> manual_only</Pill>}
                </div>
                <h3 className="mt-2 text-sm font-semibold text-text-primary">{t.findingTitle}</h3>
                <Code className="mt-1">{t.toolName}</Code>
              </div>
              <DecisionPill decision={t.decision} />
            </div>
            <div className="space-y-2 px-4 py-3 text-[11px]">
              <Row k="Resource"            v={<Code>{t.resource}</Code>} />
              <Row k="Proposed action"     v={<span className="text-text-primary">{t.proposedAction}</span>} />
              <Row k="Expected impact"     v={<span className="text-text-secondary">{t.expectedImpact}</span>} />
              <Row k="Required permission" v={<Code>{t.requiredAwsPermission}</Code>} />
            </div>
            <div className="flex flex-wrap gap-2 border-t border-border/60 bg-bg-elevated/30 px-4 py-3">
              {t.manualOnly || t.decision === "manual_required" ? (
                <Button variant="outline" size="sm" onClick={() => onSkip(t.id)} disabled={t.decision === "skipped"}>
                  <ShieldCheck className="h-3.5 w-3.5" /> Confirm manual
                </Button>
              ) : (
                <>
                  <Button size="sm" onClick={() => onApprove(t.id)} disabled={t.decision === "approved"}>
                    <ShieldCheck className="h-3.5 w-3.5" /> Approve
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => onReject(t.id)} disabled={t.decision === "rejected"}>
                    <X className="h-3.5 w-3.5" /> Reject
                  </Button>
                </>
              )}
              <Button variant="ghost" size="sm" onClick={() => setActive(t)}>
                <Eye className="h-3.5 w-3.5" /> Show Details
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {active && <DetailDrawer task={active} run={run} onClose={() => setActive(null)} />}
    </PageShell>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-text-muted">{k}</span>
      <span className="min-w-0 truncate text-right">{v}</span>
    </div>
  );
}

function DetailDrawer({ task, run, onClose }: { task: RemediationTask; run: RunSession; onClose: () => void }) {
  const finding = run.findings.find((f) => f.id === task.findingId);
  return (
    <div className="fixed inset-0 z-50 flex" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div onClick={(e) => e.stopPropagation()} className="relative ml-auto h-full w-full max-w-lg overflow-y-auto border-l border-border/60 bg-bg-surface/95 p-5 shadow-2xl backdrop-blur-md scrollbar-thin">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <SeverityPill severity={task.severity} />
              <DecisionPill decision={task.decision} />
              {task.manualOnly && <Pill tone="violet">manual_only</Pill>}
            </div>
            <h3 className="mt-2 font-display text-lg font-semibold leading-tight">{task.findingTitle}</h3>
            <Code className="mt-1">{task.toolName}</Code>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>✕</Button>
        </div>

        <Section title="Finding">
          <div className="rounded-md border border-border/60 bg-bg-elevated/40 p-3 text-[11px]">
            <Code>{finding?.prowlerCheckId}</Code>
            <p className="mt-1 text-text-secondary">{finding?.description}</p>
          </div>
        </Section>

        <Section title="Tool params">
          <pre className="overflow-x-auto rounded-md border border-border/60 bg-bg-elevated/40 p-3 font-mono text-[11px] text-text-primary">
            {JSON.stringify(task.toolParams, null, 2)}
          </pre>
        </Section>

        <Section title="Guard checks">
          <ul className="space-y-1 text-[11px] text-text-secondary">
            <li>{task.guardChecks.registeredTool ? "✅" : "❌"} Registered in tool registry</li>
            <li>{task.guardChecks.isRemediationCategory ? "✅" : "❌"} Category is <Code className="ml-1">remediation</Code></li>
            <li>{task.guardChecks.notManualOnly ? "✅" : "❌"} Not <Code className="ml-1">manual_only</Code></li>
          </ul>
        </Section>

        <Section title="Possible failure reasons">
          <ul className="grid grid-cols-2 gap-1.5 text-[11px] text-text-secondary">
            {["missing permission","resource not found","AWS API error","manual-only tool"].map((r) => (
              <li key={r} className="flex items-center gap-1.5 rounded border border-border/60 bg-bg-elevated/40 px-2 py-1">
                <AlertTriangle className="h-3 w-3 text-status-warning" /> {r}
              </li>
            ))}
          </ul>
        </Section>

        {task.manualOnly && (
          <Section title="Manual-only state">
            <div className="rounded-md border border-brand-violet/30 bg-brand-violet/5 p-3 text-[11px] text-text-secondary">
              <div className="flex items-center gap-1.5 text-brand-violet">
                <Hand className="h-3 w-3" /> Manual required
              </div>
              <p className="mt-1">This tool requires manual action. The agent will document the suggested steps in the final report.</p>
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">{title}</div>
      {children}
    </div>
  );
}
