import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Code, VerificationPill, SeverityPill } from "@/components/ui/status-pill";
import type { RunSession, VerificationResult } from "@/types/pdca";
import { ArrowRight, ShieldCheck, Wrench } from "lucide-react";

export function VerificationView({ run }: { run: RunSession }) {
  return (
    <PageShell run={run} title="Verification" subtitle="Re-scan results and before/after states for executed remediations.">
      <div className="space-y-5">
        {run.verifications.map((v) => {
          const finding = run.findings.find((f) => f.id === v.findingId);
          return (
            <Card key={v.id} className="overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 bg-bg-elevated/30 px-5 py-3">
                <div className="flex items-center gap-3">
                  <div className="grid h-9 w-9 place-items-center rounded-lg bg-status-success/10 text-status-success ring-1 ring-status-success/30">
                    <ShieldCheck className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-text-primary">{finding?.title ?? "Finding"}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                      <Code>{v.id}</Code>
                      {finding && <SeverityPill severity={finding.severity} />}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Wrench className="h-3.5 w-3.5 text-text-muted" />
                  <Code>{v.toolName}</Code>
                  <VerificationPill status={v.result} />
                </div>
              </div>

              <div className="grid gap-4 p-5 md:grid-cols-[1fr_auto_1fr]">
                <BeforeAfter title="Before" tone="error" body={v.beforeState} subtitle="finding status FAIL · severity high" />
                <div className="hidden self-center md:block"><ArrowRight className="h-5 w-5 text-text-muted" /></div>
                <BeforeAfter title="After"  tone="success" body={v.afterState} subtitle="finding status REMEDIATED · verification PASSED" />
              </div>

              <div className="grid grid-cols-2 gap-4 border-t border-border/60 bg-bg-elevated/20 px-5 py-3 text-[11px] md:grid-cols-4">
                <Meta k="resource"  v={<Code>{v.resource}</Code>} />
                <Meta k="timestamp" v={<span className="font-mono">{new Date(v.timestamp).toLocaleString()}</span>} />
                <Meta k="execution log task" v={v.executionLogTaskId ? <Code>{v.executionLogTaskId}</Code> : "—"} />
                <Meta k="rescan evidence" v={v.rescanEvidenceId ? <Code>{v.rescanEvidenceId}</Code> : "—"} />
              </div>
            </Card>
          );
        })}

        {run.verifications.length === 0 && (
          <Card className="p-6 text-center text-sm text-text-secondary">
            No verifications recorded for this run yet.
          </Card>
        )}
      </div>
    </PageShell>
  );
}

function BeforeAfter({ title, tone, body, subtitle }: { title: string; tone: "error" | "success"; body: string; subtitle: string }) {
  const cls = tone === "error" ? "border-status-error/30 bg-status-error/5 text-status-error" : "border-status-success/30 bg-status-success/5 text-status-success";
  return (
    <div className={"rounded-lg border p-4 " + cls.split(" text-")[0]}>
      <div className={"text-[10px] font-semibold uppercase tracking-wider " + (tone === "error" ? "text-status-error" : "text-status-success")}>{title}</div>
      <p className="mt-1 text-sm leading-relaxed text-text-primary">{body}</p>
      <p className="mt-2 text-[11px] text-text-muted">{subtitle}</p>
    </div>
  );
}
function Meta({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-text-muted">{k}</div>
      <div className="mt-0.5 text-text-primary">{v}</div>
    </div>
  );
}
