import { useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Code, SeverityPill, FindingStatusPill, RemediationStatusPill,
} from "@/components/ui/status-pill";
import type { Finding, RunSession, Severity } from "@/types/pdca";
import { Eye, BookOpen, Filter, ExternalLink } from "lucide-react";
import { useRouter } from "@/state/router";
import { cn } from "@/lib/utils";

const SEV_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function ResultsView({ run }: { run: RunSession }) {
  const [active, setActive] = useState<Finding | null>(null);
  const { go } = useRouter();
  const findings = [...run.findings].sort((a, b) => SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity));

  const totals = {
    total: findings.length,
    passed: findings.filter(f => f.status === "PASS").length,
    failed: findings.filter(f => f.status === "FAIL").length,
    manual: findings.filter(f => f.status === "MANUAL").length,
    high: findings.filter(f => f.severity === "high" || f.severity === "critical").length,
    medium: findings.filter(f => f.severity === "medium").length,
    low: findings.filter(f => f.severity === "low").length,
    remediated: findings.filter(f => f.remediationStatus === "remediated").length,
    open: findings.filter(f => f.remediationStatus === "open").length,
  };

  return (
    <PageShell
      run={run}
      title="Results dashboard"
      subtitle="Normalized and prioritized findings after scan_collect and risk_evaluation."
      actions={
        <Button size="sm" onClick={() => go("report")}>
          <ExternalLink className="h-4 w-4" /> Open Report
        </Button>
      }
    >
      {/* Summary cards */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-10">
        {[
          { l: "checks",      v: totals.total,      tone: "neutral" as const },
          { l: "passed",      v: totals.passed,     tone: "success" as const },
          { l: "failed",      v: totals.failed,     tone: "danger"  as const },
          { l: "manual",      v: totals.manual,     tone: "violet"  as const },
          { l: "high",        v: totals.high,       tone: "danger"  as const },
          { l: "medium",      v: totals.medium,     tone: "warning" as const },
          { l: "low",         v: totals.low,        tone: "info"    as const },
          { l: "remediated",  v: totals.remediated, tone: "success" as const },
          { l: "open",        v: totals.open,       tone: "warning" as const },
          { l: "report",      v: run.report.status, tone: "primary" as const },
        ].map((s) => (
          <Card key={s.l} className="p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">{s.l}</div>
            <div className={cn(
              "mt-0.5 font-mono text-xl font-semibold",
              s.tone === "success" && "text-status-success",
              s.tone === "warning" && "text-status-warning",
              s.tone === "danger"  && "text-status-error",
              s.tone === "violet"  && "text-brand-violet",
              s.tone === "info"    && "text-severity-info",
              s.tone === "primary" && "text-primary capitalize",
              s.tone === "neutral" && "text-text-primary",
            )}>{s.v}</div>
          </Card>
        ))}
      </div>

      {/* Findings table */}
      <Card className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Filter className="h-4 w-4 text-primary" /> Findings
            <span className="font-mono text-[11px] text-text-muted">({findings.length})</span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border/60 bg-bg-elevated/30 text-[10px] uppercase tracking-wider text-text-muted">
              <tr>
                <th className="px-3 py-2.5">Sev</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Remediation</th>
                <th className="px-3 py-2.5">Check ID</th>
                <th className="px-3 py-2.5">Service</th>
                <th className="px-3 py-2.5">Resource</th>
                <th className="px-3 py-2.5">Finding</th>
                <th className="px-3 py-2.5">Evidence</th>
                <th className="px-3 py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {findings.map((f) => (
                <tr key={f.id} className="hover:bg-bg-elevated/30">
                  <td className="px-3 py-2.5"><SeverityPill severity={f.severity} /></td>
                  <td className="px-3 py-2.5"><FindingStatusPill status={f.status} /></td>
                  <td className="px-3 py-2.5"><RemediationStatusPill status={f.remediationStatus} /></td>
                  <td className="px-3 py-2.5"><Code>{f.prowlerCheckId}</Code></td>
                  <td className="px-3 py-2.5 text-text-secondary">{f.service}</td>
                  <td className="px-3 py-2.5"><Code>{f.resource}</Code></td>
                  <td className="px-3 py-2.5 text-text-primary">{f.title}</td>
                  <td className="px-3 py-2.5 font-mono text-text-muted">{f.evidenceIds.length}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => setActive(f)}>
                        <Eye className="h-3.5 w-3.5" /> View
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Detail drawer */}
      {active && <FindingDetail finding={active} run={run} onClose={() => setActive(null)} />}
    </PageShell>
  );
}

function FindingDetail({ finding, run, onClose }: { finding: Finding; run: RunSession; onClose: () => void }) {
  const evidence = run.evidence.filter((e) => finding.evidenceIds.includes(e.id));
  return (
    <div className="fixed inset-0 z-50 flex" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative ml-auto h-full w-full max-w-lg overflow-y-auto border-l border-border/60 bg-bg-surface/95 p-5 shadow-2xl backdrop-blur-md scrollbar-thin"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <SeverityPill severity={finding.severity} />
              <FindingStatusPill status={finding.status} />
              <RemediationStatusPill status={finding.remediationStatus} />
            </div>
            <h3 className="mt-2 font-display text-lg font-semibold leading-tight">{finding.title}</h3>
            <Code className="mt-1">{finding.prowlerCheckId}</Code>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>✕</Button>
        </div>

        <Section title="Resource"><Code>{finding.resource}</Code> · {finding.region}</Section>
        <Section title="Description"><p className="text-text-secondary">{finding.description}</p></Section>
        <Section title="Recommendation"><p className="text-text-primary">{finding.recommendation}</p></Section>

        <Section title="Evidence">
          <div className="space-y-2">
            {evidence.map((e) => (
              <div key={e.id} className="rounded-md border border-border/60 bg-bg-elevated/40 p-2.5 text-[11px]">
                <div className="flex items-center justify-between">
                  <Code>{e.id}</Code>
                  <span className="text-text-muted">{e.kind}</span>
                </div>
                {e.kind === "finding" && <p className="mt-1 text-text-secondary">{e.snippet}</p>}
                {e.kind === "verification" && <p className="mt-1 text-text-secondary">{e.snippet}</p>}
                {e.kind === "remediation" && (
                  <div className="mt-1 space-y-0.5 text-text-secondary">
                    <div><span className="text-status-error">before</span>: {e.beforeState}</div>
                    <div><span className="text-status-success">after</span>: {e.afterState}</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>

        <Section title="RAG knowledge context">
          <div className="rounded-md border border-border/60 bg-bg-elevated/40 p-2.5 text-xs text-text-secondary">
            <BookOpen className="mr-1 inline h-3 w-3 text-brand-violet" />
            Mapped to NIST SP 800-53 AC-3, CIS AWS 2.1.5 — supports the recommendation above.
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">{title}</div>
      <div className="text-xs">{children}</div>
    </div>
  );
}
