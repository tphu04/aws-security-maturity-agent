import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { RunSession } from "@/types/pdca";
import { Telescope, FlaskConical, Activity, CircleDot, BookOpen, ExternalLink } from "lucide-react";
import { Code } from "@/components/ui/status-pill";
import { ToolCallCard } from "./ToolCallCard";
import { EvidenceCard } from "./EvidenceCard";
import { GraphTimeline } from "@/components/graph/GraphTimeline";

export function ToolTracePanel({ run }: { run: RunSession }) {
  const calls = [...run.toolCalls].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const isLive = run.status !== "completed" && run.status !== "failed" && run.status !== "idle";

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

      {/* Live banner: current node */}
      <div className={"border-b border-border/60 px-4 py-2.5 " + (isLive ? "bg-primary/10" : "bg-bg-elevated/30")}>
        <div className="flex items-center gap-2 text-[11px]">
          <CircleDot className={"h-3.5 w-3.5 " + (isLive ? "text-primary animate-pulse" : "text-text-muted")} />
          <span className="text-text-muted uppercase tracking-wider">{isLive ? "running" : "idle"}</span>
          <Code>{run.currentNode}</Code>
          <span className="ml-auto text-text-muted">{run.status}</span>
        </div>
      </div>

      {/* Run state strip */}
      <div className="border-b border-border/60 bg-bg-elevated/30 px-4 py-3">
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          <Stat k="run_id"               v={<Code>{run.id}</Code>} />
          <Stat k="pending_jobs"         v={run.scanJobs.filter(j => j.status === "pending" || j.status === "running").length} />
          <Stat k="completed_jobs"       v={run.scanJobs.filter(j => j.status === "completed").length} />
          <Stat k="findings"             v={run.findings.length} />
          <Stat k="failed_findings"      v={run.findings.filter(f => f.status === "FAIL").length} />
          <Stat k="remediation_tasks"    v={run.remediationTasks.length} />
          <Stat k="execution_logs"       v={run.executionLogs.length} />
          <Stat k="verifications"        v={run.verifications.length} />
          <Stat k="evidence"             v={run.evidence.length} />
          <Stat k="report"               v={<span className="capitalize">{run.report.status}</span>} />
        </div>
      </div>

      <Tabs defaultValue="graph" className="flex min-h-0 flex-1 flex-col">
        <div className="px-4 pt-3">
          <TabsList className="w-full">
            <TabsTrigger value="tools"     className="flex-1">Tools <Cnt n={calls.length} /></TabsTrigger>
            <TabsTrigger value="knowledge" className="flex-1">RAG <Cnt n={(run.ragBundle?.capabilityThemes?.length ?? 0) + (run.ragBundle?.remediationGuides?.length ?? 0)} /></TabsTrigger>
            <TabsTrigger value="evidence"  className="flex-1">Evidence <Cnt n={run.evidence.length} /></TabsTrigger>
            <TabsTrigger value="graph"     className="flex-1">Graph</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="tools" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full scrollbar-thin">
            <div className="space-y-3 p-4">
              <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                <Activity className="h-3.5 w-3.5 text-primary" />
                Tool calls grouped by node
              </div>
              {calls.length === 0 && (
                <div className="rounded-md border border-dashed border-border/60 p-4 text-center text-[11px] text-text-muted">
                  No tools called yet — they appear once the agent invokes scanner / remediation tools.
                </div>
              )}
              {Object.entries(
                calls.reduce<Record<string, typeof calls>>((acc, c) => {
                  const k = c.relatedGraphNode ?? "(misc)";
                  (acc[k] ??= []).push(c);
                  return acc;
                }, {})
              ).map(([node, items]) => (
                <div key={node}>
                  <div className="mb-1 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    <Code>{node}</Code>
                    <span>{items.length} call{items.length === 1 ? "" : "s"}</span>
                  </div>
                  <div className="space-y-2">
                    {items.map((c) => <ToolCallCard key={c.id} call={c} />)}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="knowledge" className="m-0 min-h-0 flex-1">
          <ScrollArea className="h-full scrollbar-thin">
            <div className="space-y-4 p-4">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                <BookOpen className="h-3.5 w-3.5 text-primary" />
                RAG knowledge bundle
                {run.ragBundle?.confidence && (
                  <Code>confidence={run.ragBundle.confidence}</Code>
                )}
              </div>

              {!run.ragBundle && (
                <div className="rounded-md border border-dashed border-border/60 p-4 text-center text-[11px] text-text-muted">
                  Knowledge will appear after the rag_enrich node runs.
                </div>
              )}

              {run.ragBundle?.capabilityThemes?.map((t, i) => (
                <div key={`th-${i}`} className="rounded-md border border-border/60 bg-bg-elevated/30 p-3">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wider text-text-muted">Capability theme</span>
                    <Code>{t.domain}</Code>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{t.narrative}</p>
                  {t.common_pitfalls && t.common_pitfalls.length > 0 && (
                    <div className="mt-2">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Common pitfalls</div>
                      <ul className="ml-4 list-disc text-[11px] text-text-secondary">
                        {t.common_pitfalls.slice(0, 4).map((p, j) => <li key={j}>{p}</li>)}
                      </ul>
                    </div>
                  )}
                  {t.baselines && t.baselines.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {t.baselines.slice(0, 6).map((b, j) => (
                        <span key={j} className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{b}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {run.ragBundle?.remediationGuides?.map((g, i) => (
                <div key={`rg-${i}`} className="rounded-md border border-border/60 bg-bg-elevated/30 p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] uppercase tracking-wider text-text-muted">Remediation guide</span>
                      <Code>{g.check_id}</Code>
                    </div>
                    <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">effort: {g.effort ?? "?"}</span>
                  </div>
                  {(g.steps ?? []).map((s, j) => (
                    <div key={j} className="mt-2 rounded border border-border/40 bg-bg-base/40 p-2 text-[11px]">
                      <div className="flex items-center gap-1.5 text-text-muted">
                        <span>step {s.order ?? j + 1}</span>
                        <Code>{s.type}</Code>
                      </div>
                      <pre className="mt-1 whitespace-pre-wrap break-words font-mono text-[10.5px] text-text-secondary">{s.snippet}</pre>
                    </div>
                  ))}
                  {g.side_effects && g.side_effects.length > 0 && (
                    <div className="mt-2 text-[10px] text-text-muted">
                      <span className="font-semibold uppercase tracking-wider">side effects:</span>{" "}
                      {g.side_effects.join(", ")}
                    </div>
                  )}
                  {g.citations && g.citations.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-text-muted">
                      {g.citations.slice(0, 3).map((c, j) => (
                        <a key={j} href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-primary">
                          <ExternalLink className="h-3 w-3" /> {c.source}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {run.ragBundle && Object.keys(run.ragBundle.controlMappings || {}).length > 0 && (
                <div className="rounded-md border border-border/60 bg-bg-elevated/30 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">Control mappings</div>
                  <div className="mt-1 grid grid-cols-1 gap-1 text-[11px] text-text-secondary">
                    {Object.entries(run.ragBundle.controlMappings).slice(0, 8).map(([cid]) => (
                      <Code key={cid}>{cid}</Code>
                    ))}
                  </div>
                </div>
              )}
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
