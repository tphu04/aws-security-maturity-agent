import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Code, Pill } from "@/components/ui/status-pill";
import { ArrowLeft, Download, ExternalLink, FileText } from "lucide-react";
import type { RunSession } from "@/types/pdca";
import { useRouter } from "@/state/router";
import { useRun } from "@/state/run";
import { chatbotApi } from "@/lib/api";

export function ReportView({ run }: { run: RunSession }) {
  const sections = run.report.sections;
  const isEmpty = !sections || sections.length === 0;
  const { go } = useRouter();
  const { activeRunId } = useRun();
  const runId = activeRunId || run.id;
  const previewUrl = runId ? chatbotApi.reportUrl(runId, "pdf") : "#";

  const downloadReport = () => {
    if (!runId) return;
    window.open(chatbotApi.reportUrl(runId, "pdf", true), "_blank");
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
      title="Report Preview"
      subtitle={
        <span className="font-mono">
          {run.report.filename.replace(/\.md$/i, ".pdf")} · <span className="capitalize">{run.report.status}</span> · {run.report.version}
        </span>
      }
      actions={
        <>
          <Button variant="outline" size="sm" onClick={() => go("results")}>
            <ArrowLeft className="h-4 w-4" /> Back to Results
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.open(previewUrl, "_blank")}>
            <ExternalLink className="h-4 w-4" /> Open PDF
          </Button>
          <Button size="sm" onClick={downloadReport}><Download className="h-4 w-4" /> Download PDF</Button>
        </>
      }
    >
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-4 py-3">
          <Pill tone="primary" className="self-start">
            <FileText className="h-3 w-3" /> {run.report.filename.replace(/\.md$/i, ".pdf")}
          </Pill>
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
            <Meta k="AWS account" v={<Code>{run.awsEnvironment.accountMask}</Code>} />
            <Meta k="Generated" v={<span className="font-mono">{run.report.generatedAt && new Date(run.report.generatedAt).toLocaleString()}</span>} />
          </div>
        </div>
        <iframe
          title="PDF report preview"
          src={previewUrl}
          className="h-[calc(100vh-220px)] min-h-[620px] w-full bg-white"
        />
      </Card>
    </PageShell>
  );
}

function Meta({ k, v }: { k: string; v: React.ReactNode }) {
  return <div><span className="text-text-muted">{k}: </span><span className="text-text-primary">{v}</span></div>;
}
