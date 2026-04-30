import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { RunSession } from "@/types/pdca";
import { Telescope, FlaskConical, Activity } from "lucide-react";
import { Code } from "@/components/ui/status-pill";
import { ToolCallCard } from "./ToolCallCard";
import { EvidenceCard } from "./EvidenceCard";
import { GraphTimeline } from "@/components/graph/GraphTimeline";

export function ToolTracePanel({ run }: { run: RunSession }) {
  const calls = [...run.toolCalls].sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border/60 px-4 pb-3 pt-4">
        <div className="flex items-center gap-2">
          <Telescope className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold tracking-tight">Tool & Evidence Trace</h2>
        </div>
        <p className="mt-0.5 text-[11px] text-text-muted">
          Live transparency: nodes, tools, and evidence the agent collected.
        </p>
      </div>

      {/* Run state strip */}
      <div className="border-b border-border/60 bg-bg-elevated/30 px-4 py-3">
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <Stat k="run_id"               v={<Code>{run.id}</Code>} />
          <Stat k="current_node"         v={<Code>{run.currentNode}</Code>} />
          <Stat k="pending_jobs"         v={run.scanJobs.filter(j => j.status === "pending" || j.status === "running").length} />
          <Stat k="completed_jobs"       v={run.scanJobs.filter(j => j.status === "completed").length} />
          <Stat k="raw_findings"         v={run.scanJobs.reduce((s, j) => s + (j.totalChecks ?? 0), 0)} />
          <Stat k="normalized_findings"  v={run.findings.length} />
          <Stat k="prioritized_findings" v={run.findings.filter(f => f.status === "FAIL").length} />
          <Stat k="remediation_tasks"    v={run.remediationTasks.length} />
          <Stat k="execution_logs"       v={run.executionLogs.length} />
          <Stat k="report"               v={<span className="capitalize">{run.report.status}</span>} />
        </div>
      </div>

      <Tabs defaultValue="tools" className="flex min-h-0 flex-1 flex-col">
        <div className="px-4 pt-3">
          <TabsList className="w-full">
            <TabsTrigger value="tools"    className="flex-1">Tools <Cnt n={calls.length} /></TabsTrigger>
            <TabsTrigger value="evidence" className="flex-1">Evidence <Cnt n={run.evidence.length} /></TabsTrigger>
            <TabsTrigger value="graph"    className="flex-1">Graph</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="tools" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full scrollbar-thin">
            <div className="space-y-2 p-4">
              <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                <Activity className="h-3.5 w-3.5 text-primary" />
                Tool calls
              </div>
              {calls.map((c) => <ToolCallCard key={c.id} call={c} />)}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="evidence" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full scrollbar-thin">
            <div className="space-y-2 p-4">
              <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                <FlaskConical className="h-3.5 w-3.5 text-primary" />
                Evidence collected
              </div>
              {run.evidence.map((e) => <EvidenceCard key={e.id} evidence={e} />)}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="graph" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full scrollbar-thin">
            <div className="p-4">
              <GraphTimeline nodes={run.graphNodes} currentNode={run.currentNode} dense />
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-text-muted">{k}</span>
      <span className="font-mono text-text-primary">{v}</span>
    </div>
  );
}
function Cnt({ n }: { n: number }) {
  return <span className="ml-1.5 rounded bg-bg-elevated/80 px-1 font-mono text-[10px] text-text-muted">{n}</span>;
}
