import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Code, RunStatusPill, Pill } from "@/components/ui/status-pill";
import { GraphTimeline } from "@/components/graph/GraphTimeline";
import type { RunSession } from "@/types/pdca";
import { Database, Server, Clock, GitBranch, ShieldCheck } from "lucide-react";

function fmtDuration(ms: number) {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}m ${(s % 60).toString().padStart(2, "0")}s`;
}

export function RunDetailView({ run }: { run: RunSession }) {
  return (
    <PageShell run={run} title="Run · Session Detail" subtitle="Durable LangGraph run — survives refresh and worker restart via SQLite checkpoints.">
      {/* Header strip */}
      <Card className="mb-5 p-5">
        <div className="grid gap-3 md:grid-cols-4 lg:grid-cols-7">
          <Stat icon={GitBranch} k="run id"      v={<Code>{run.id}</Code>} />
          <Stat icon={GitBranch} k="thread id"   v={<Code>{run.threadId}</Code>} />
          <Stat icon={ShieldCheck} k="status"    v={<RunStatusPill status={run.status} />} />
          <Stat icon={Clock}     k="started"     v={<span className="font-mono">{new Date(run.startedAt).toLocaleString()}</span>} />
          <Stat icon={Clock}     k="duration"    v={<span className="font-mono">{fmtDuration(run.durationMs)}</span>} />
          <Stat icon={Server}    k="node"        v={<Code>{run.currentNode}</Code>} />
          <Stat icon={Database}  k="checkpointer" v={
            <span className="inline-flex items-center gap-1.5">
              <Pill tone="primary" className="font-mono">{run.checkpointer}</Pill>
              <span className="font-mono text-[10px] text-text-muted">{new Date(run.lastCheckpointAt).toLocaleTimeString()}</span>
            </span>
          } />
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <GraphTimeline nodes={run.graphNodes} currentNode={run.currentNode} />
        </Card>

        <div className="space-y-4">
          <Card className="p-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Scan jobs</div>
            <div className="space-y-2">
              {run.scanJobs.map((j) => (
                <div key={j.id} className="rounded-md border border-border/60 bg-bg-elevated/40 p-2.5 text-[11px]">
                  <div className="flex items-center justify-between">
                    <Code>{j.id}</Code>
                    <Pill tone={j.status === "completed" ? "success" : j.status === "failed" ? "danger" : "warning"}>{j.status}</Pill>
                  </div>
                  <div className="mt-1 text-text-secondary"><Code>{j.apiEndpoint}</Code></div>
                  <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 font-mono text-text-muted">
                    <div>task <span className="text-text-primary">{j.taskType}={j.taskValue}</span></div>
                    <div>checks <span className="text-text-primary">{j.completedChecks}/{j.totalChecks}</span></div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Findings summary</div>
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              {[
                { l: "high",   v: run.findings.filter(f => f.severity === "high").length,    c: "text-status-error" },
                { l: "medium", v: run.findings.filter(f => f.severity === "medium").length,  c: "text-status-warning" },
                { l: "low",    v: run.findings.filter(f => f.severity === "low").length,     c: "text-severity-info" },
                { l: "manual", v: run.findings.filter(f => f.status === "MANUAL").length,    c: "text-brand-violet" },
              ].map((s) => (
                <div key={s.l} className="rounded border border-border/60 bg-bg-elevated/40 px-2 py-1.5">
                  <div className="text-text-muted uppercase tracking-wider text-[9px]">{s.l}</div>
                  <div className={"font-mono text-base font-semibold " + s.c}>{s.v}</div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Pending approvals</div>
            <div className="space-y-1.5 text-[11px]">
              {run.remediationTasks.filter(t => t.decision === "pending" || t.decision === "manual_required").map((t) => (
                <div key={t.id} className="flex items-center justify-between rounded border border-border/60 bg-bg-elevated/40 px-2 py-1.5">
                  <Code>{t.id}</Code>
                  <Pill tone={t.decision === "manual_required" ? "violet" : "warning"}>{t.decision}</Pill>
                </div>
              ))}
              {run.remediationTasks.filter(t => t.decision === "pending" || t.decision === "manual_required").length === 0 && (
                <div className="text-text-muted">None pending.</div>
              )}
            </div>
          </Card>

          <Card className="p-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Report</div>
            <div className="text-[11px]">
              <div className="flex items-center justify-between">
                <Code>{run.report.filename}</Code>
                <Pill tone={run.report.status === "ready" ? "success" : "warning"}>{run.report.status}</Pill>
              </div>
              <div className="mt-1 font-mono text-text-muted">{run.report.version} · {run.report.generatedAt && new Date(run.report.generatedAt).toLocaleTimeString()}</div>
            </div>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}

function Stat({ icon: Icon, k, v }: { icon: React.ElementType; k: string; v: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        <Icon className="h-3 w-3 text-primary" /> {k}
      </div>
      <div className="mt-0.5 truncate text-xs text-text-primary">{v}</div>
    </div>
  );
}
