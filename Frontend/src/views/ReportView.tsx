import { useEffect, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Code, Pill } from "@/components/ui/status-pill";
import { ArrowLeft, Eye, Download, FileText, Copy, RefreshCw, Printer } from "lucide-react";
import type { RunSession } from "@/types/pdca";
import { useRouter } from "@/state/router";
import { useRun } from "@/state/run";
import { cn } from "@/lib/utils";
import { loadEndpoints } from "@/lib/api";

export function ReportView({ run }: { run: RunSession }) {
  const sections = run.report.sections;
  const isEmpty = !sections || sections.length === 0;
  const [active, setActive] = useState<string>(sections[0]?.id ?? "");
  const { go } = useRouter();
  const { activeRunId } = useRun();
  const activeSection = sections.find((s) => s.id === active) ?? sections[0];

  // Sync the selected section id when sections list changes (live updates).
  useEffect(() => {
    if (sections[0] && !sections.find((s) => s.id === active)) {
      setActive(sections[0].id);
    }
  }, [sections, active]);

  const downloadReport = () => {
    const runId = activeRunId || run.id;
    const base = loadEndpoints().chatbot;
    if (!base) return;
    window.open(`${base.replace(/\/+$/, "")}/v1/runs/${encodeURIComponent(runId)}/report?format=markdown`, "_blank");
  };

  if (isEmpty) {
    return (
      <PageShell run={run} title="Report" subtitle="Run is still in progress.">
        <Card className="p-8 text-center">
          <FileText className="mx-auto h-8 w-8 text-text-muted" />
          <h3 className="mt-3 font-display text-lg font-semibold">Report not ready yet</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-text-secondary">
            The agent is still scanning, planning, or executing remediation. The report will be assembled once
            verification finishes.
          </p>
          <div className="mt-4 flex justify-center gap-2">
            <Button variant="outline" size="sm" onClick={() => go("workspace")}>
              <ArrowLeft className="h-4 w-4" /> Back to Workspace
            </Button>
          </div>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell
      run={run}
      title="DOCX Report Preview"
      subtitle={
        <span className="font-mono">
          {run.report.filename} · <span className="capitalize">{run.report.status}</span> · {run.report.version}
        </span>
      }
      actions={
        <>
          <Button variant="outline" size="sm" onClick={() => go("results")}>
            <ArrowLeft className="h-4 w-4" /> Back to Results
          </Button>
          <Button size="sm" onClick={downloadReport}><Download className="h-4 w-4" /> Download Markdown</Button>
          <Button variant="outline" size="sm" disabled><Printer className="h-4 w-4" /> Export PDF</Button>
        </>
      }
    >
      <div className="grid gap-5 lg:grid-cols-[260px_1fr]">
        {/* Outline */}
        <Card className="h-fit p-3">
          <div className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Outline</div>
          <ul className="space-y-0.5">
            {sections.map((s, i) => (
              <li key={s.id}>
                <button
                  onClick={() => setActive(s.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                    active === s.id
                      ? "bg-primary/10 text-primary ring-1 ring-inset ring-primary/30"
                      : "text-text-secondary hover:bg-bg-elevated/60 hover:text-text-primary",
                  )}
                >
                  <span className="grid h-5 w-5 shrink-0 place-items-center rounded font-mono text-[10px] text-text-muted">{i + 1}</span>
                  <span className="truncate">{s.title}</span>
                </button>
              </li>
            ))}
          </ul>

          <div className="mt-4 space-y-2 border-t border-border/60 px-2 pt-3">
            <Button variant="ghost" size="sm" className="w-full justify-start"><Copy className="h-3.5 w-3.5" /> Copy executive summary</Button>
            <Button variant="ghost" size="sm" className="w-full justify-start"><RefreshCw className="h-3.5 w-3.5" /> Regenerate report</Button>
          </div>
        </Card>

        {/* Document */}
        <div className="space-y-4">
          {/* Cover */}
          <Card className="overflow-hidden">
            <div className="border-b border-border/60 bg-gradient-to-br from-primary/10 via-transparent to-brand-violet/10 p-8">
              <Pill tone="primary" className="self-start">
                <FileText className="h-3 w-3" /> {run.report.filename}
              </Pill>
              <h2 className="mt-3 font-display text-3xl font-bold tracking-tight md:text-4xl">{sections[0].title}</h2>
              <p className="mt-1 text-sm text-text-secondary">Generated by PDCA Prowler Agent</p>
              <div className="mt-5 grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
                <Meta k="AWS account" v={<Code>{run.awsEnvironment.accountMask}</Code>} />
                <Meta k="Region"      v={<Code>{run.awsEnvironment.region}</Code>} />
                <Meta k="Service"     v="S3" />
                <Meta k="Run ID"      v={<Code>{run.id}</Code>} />
                <Meta k="Scanner job" v={<Code>{run.scanJobs[0]?.id}</Code>} />
                <Meta k="Generated"   v={<span className="font-mono">{run.report.generatedAt && new Date(run.report.generatedAt).toLocaleString()}</span>} />
              </div>
            </div>
          </Card>

          {/* Active section preview */}
          <Card className="p-6 md:p-8">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Section</div>
            <h3 className="mt-1 font-display text-2xl font-semibold tracking-tight">{activeSection.title}</h3>
            <div className="prose prose-invert mt-4 max-w-none text-sm leading-relaxed text-text-secondary">
              {activeSection.body.split("\n").map((line, i) => (
                <p key={i} className="mb-2 last:mb-0">{line || <br />}</p>
              ))}
            </div>
          </Card>

          {/* Quick preview of other sections */}
          <Card className="p-5">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">All sections</div>
              <Button variant="ghost" size="sm"><Eye className="h-3.5 w-3.5" /> Full preview</Button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {sections.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setActive(s.id)}
                  className="rounded-md border border-border/60 bg-bg-elevated/30 p-3 text-left transition-colors hover:border-primary/40 hover:bg-primary/5"
                >
                  <div className="text-xs font-semibold text-text-primary">{s.title}</div>
                  <div className="mt-1 line-clamp-2 text-[11px] text-text-secondary">{s.body}</div>
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </PageShell>
  );
}

function Meta({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><span className="text-text-muted">{k}: </span><span className="text-text-primary">{v}</span></div>;
}
