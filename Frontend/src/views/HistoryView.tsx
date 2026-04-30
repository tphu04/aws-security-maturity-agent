import { useEffect, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Code, RunStatusPill, Pill } from "@/components/ui/status-pill";
import { Eye, Download, PlayCircle, FileText, RefreshCw } from "lucide-react";
import type { RunHistoryRow, RunSession } from "@/types/pdca";
import { mockHistory } from "@/data/mockRun";
import { useRouter } from "@/state/router";
import { useRun } from "@/state/run";

function fmtDuration(ms: number) {
  const s = Math.round(ms / 1000);
  const mm = Math.floor(s / 60).toString().padStart(2, "0");
  const ss = (s % 60).toString().padStart(2, "0");
  return `${mm}m ${ss}s`;
}

export function HistoryView({ run }: { run: RunSession }) {
  const { go } = useRouter();
  const { listHistory, chatbotOnline } = useRun();
  const [rows, setRows] = useState<RunHistoryRow[]>(mockHistory);
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<"mock" | "live">("mock");

  const refresh = async () => {
    setLoading(true);
    const live = await listHistory();
    if (live.length > 0) {
      setRows(live);
      setSource("live");
    } else if (chatbotOnline) {
      setRows([]);
      setSource("live");
    } else {
      setRows(mockHistory);
      setSource("mock");
    }
    setLoading(false);
  };

  useEffect(() => { void refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [chatbotOnline]);

  return (
    <PageShell
      run={run}
      title="Scan History"
      subtitle={
        source === "live"
          ? `Live from chatbot API · ${rows.length} run${rows.length === 1 ? "" : "s"}`
          : "Chatbot API offline — showing mock history. Start the chatbot service to see real runs."
      }
      actions={
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw className={"h-3.5 w-3.5 " + (loading ? "animate-spin" : "")} /> Refresh
        </Button>
      }
    >
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-border/60 bg-bg-elevated/30 text-[10px] uppercase tracking-wider text-text-muted">
              <tr>
                <th className="px-3 py-2.5">Run ID</th>
                <th className="px-3 py-2.5">Target</th>
                <th className="px-3 py-2.5">Account</th>
                <th className="px-3 py-2.5">Started</th>
                <th className="px-3 py-2.5">Duration</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Findings</th>
                <th className="px-3 py-2.5">Remediated</th>
                <th className="px-3 py-2.5">Report</th>
                <th className="px-3 py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-bg-elevated/30">
                  <td className="px-3 py-2.5"><Code>{r.id}</Code></td>
                  <td className="px-3 py-2.5 text-text-primary">{r.target}</td>
                  <td className="px-3 py-2.5"><Code>{r.awsAccountMask}</Code></td>
                  <td className="px-3 py-2.5 font-mono text-text-secondary">{new Date(r.startedAt).toLocaleString()}</td>
                  <td className="px-3 py-2.5 font-mono text-text-secondary">{fmtDuration(r.durationMs)}</td>
                  <td className="px-3 py-2.5"><RunStatusPill status={r.status} /></td>
                  <td className="px-3 py-2.5 font-mono text-text-primary">{r.findingsTotal}</td>
                  <td className="px-3 py-2.5 font-mono text-status-success">{r.remediated}</td>
                  <td className="px-3 py-2.5">
                    <Pill tone={r.reportStatus === "ready" ? "success" : r.reportStatus === "failed" ? "danger" : "warning"}>{r.reportStatus}</Pill>
                  </td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => go("workspace")}>
                        <PlayCircle className="h-3.5 w-3.5" /> Resume
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => go("results")}>
                        <Eye className="h-3.5 w-3.5" /> Results
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={() => go("report")}>
                        <FileText className="h-3.5 w-3.5" /> Report
                      </Button>
                      <Button variant="ghost" size="sm" className="h-7 px-2 text-xs" disabled={r.reportStatus !== "ready"}>
                        <Download className="h-3.5 w-3.5" /> DOCX
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </PageShell>
  );
}
