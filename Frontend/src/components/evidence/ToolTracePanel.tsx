import { useState } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { RunSession } from "@/types/pdca";
import { Telescope, Activity, CircleDot, BookOpen, ExternalLink, ChevronDown, X, Route } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Code } from "@/components/ui/status-pill";
import { ToolCallCard } from "./ToolCallCard";
import { GraphTimeline } from "@/components/graph/GraphTimeline";
import { cn } from "@/lib/utils";

export function ToolTracePanel({ run, onClose }: { run: RunSession; onClose?: () => void }) {
  const calls = [...run.toolCalls].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const isLive = run.status !== "completed" && run.status !== "failed" && run.status !== "cancelled" && run.status !== "idle";
  const [statsOpen, setStatsOpen] = useState(false);
  const ragTrace = run.ragBundle?.trace ?? {};
  const ragRequest = ragTrace.report_context_request ?? {};
  const mappingRequests = ragTrace.resolve_mapping_requests ?? [];
  const responseCounts = ragTrace.response_counts ?? {};
  const ragTraceCount = (Object.keys(ragRequest).length ? 1 : 0) + mappingRequests.length;

  const pendingJobs   = run.scanJobs.filter(j => j.status === "pending" || j.status === "running").length;
  const completedJobs = run.scanJobs.filter(j => j.status === "completed").length;
  const failedFnd     = run.findings.filter(f => f.status === "FAIL").length;

  return (
    <div className="flex h-full flex-col">
      {/* Compact single-row header */}
      <div className="flex items-center gap-2 border-b border-border/60 px-4 py-2.5">
        <Telescope className="h-4 w-4 text-primary shrink-0" />
        <h2 className="text-sm font-semibold tracking-tight">Trace</h2>
        <Code className="ml-1 truncate">{run.id}</Code>
        <div className="ml-auto inline-flex items-center gap-1.5 text-[11px]">
          <CircleDot className={cn("h-3 w-3", isLive ? "text-primary animate-pulse" : "text-text-muted")} />
          <span className="text-text-muted uppercase tracking-wider">{isLive ? "live" : "idle"}</span>
          <Code className="ml-1">{run.currentNode}</Code>
        </div>
        {onClose && (
          <Button variant="ghost" size="icon" className="ml-1 h-7 w-7 shrink-0" onClick={onClose} aria-label="Close trace panel">
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {/* Inline stats — single line by default, expand for full grid */}
      <button
        type="button"
        onClick={() => setStatsOpen((v) => !v)}
        className="flex w-full items-center justify-between border-b border-border/60 bg-bg-elevated/20 px-4 py-1.5 text-left text-[11px] text-text-secondary hover:bg-bg-elevated/40"
      >
        <span className="font-mono">
          {completedJobs}/{completedJobs + pendingJobs} jobs · {run.findings.length} findings ({failedFnd} fail) · {run.remediationTasks.length} tasks · {run.evidence.length} evidence
        </span>
        <ChevronDown className={cn("h-3 w-3 transition-transform text-text-muted", statsOpen && "rotate-180")} />
      </button>
      {statsOpen && (
        <div className="border-b border-border/60 bg-bg-elevated/30 px-4 py-3">
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            <Stat k="pending_jobs"      v={pendingJobs} />
            <Stat k="completed_jobs"    v={completedJobs} />
            <Stat k="findings"          v={run.findings.length} />
            <Stat k="failed_findings"   v={failedFnd} />
            <Stat k="remediation_tasks" v={run.remediationTasks.length} />
            <Stat k="execution_logs"    v={run.executionLogs.length} />
            <Stat k="verifications"     v={run.verifications.length} />
            <Stat k="evidence"          v={run.evidence.length} />
            <Stat k="report"            v={<span className="capitalize">{run.report.status}</span>} />
          </div>
        </div>
      )}

      <Tabs defaultValue="graph" className="flex min-h-0 flex-1 flex-col">
        <div className="px-4 pt-3">
          <TabsList className="w-full">
            <TabsTrigger value="tools"     className="flex-1">Tools <Cnt n={calls.length} /></TabsTrigger>
            <TabsTrigger value="knowledge" className="flex-1">RAG <Cnt n={ragTraceCount || ((run.ragBundle?.capabilityThemes?.length ?? 0) + (run.ragBundle?.remediationGuides?.length ?? 0))} /></TabsTrigger>
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
                RAG queries and responses
                {run.ragBundle?.confidence && (
                  <Code>confidence={run.ragBundle.confidence}</Code>
                )}
              </div>

              {!run.ragBundle && (
                <div className="rounded-md border border-dashed border-border/60 p-4 text-center text-[11px] text-text-muted">
                  Knowledge will appear after the rag_enrich node runs.
                </div>
              )}

              {run.ragBundle && (
                <div className="rounded-md border border-border/60 bg-bg-elevated/30 p-3">
                  <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    <Route className="h-3.5 w-3.5 text-primary" />
                    Called RAG endpoint
                  </div>
                  <TraceRow k="endpoint" v={String(ragRequest.endpoint ?? "/v1/retrieve/report_context")} />
                  <TraceRow k="check_ids" v={<InlineList items={asStringList(ragRequest.check_ids)} />} />
                  <TraceRow k="domains" v={<InlineList items={asStringList(ragRequest.domains)} />} />
                  <TraceRow k="top_k" v={`${ragRequest.top_k_check ?? "?"}/${ragRequest.top_k_capability ?? "?"}/${ragRequest.top_k_remediation ?? "?"}`} />
                  <div className="mt-2 grid grid-cols-2 gap-1">
                    <MiniMetric k="checks" v={responseCounts.check_findings ?? run.findings.length} />
                    <MiniMetric k="themes" v={responseCounts.capability_themes ?? run.ragBundle.capabilityThemes.length} />
                    <MiniMetric k="guides" v={responseCounts.remediation_guides ?? run.ragBundle.remediationGuides.length} />
                    <MiniMetric k="mappings" v={responseCounts.control_mappings ?? Object.keys(run.ragBundle.controlMappings || {}).length} />
                  </div>
                  {Object.keys(run.ragBundle.diagnostics || {}).length > 0 && (
                    <pre className="mt-2 max-h-28 overflow-auto rounded border border-border/50 bg-bg-base/50 p-2 font-mono text-[10px] text-text-secondary scrollbar-thin">
                      {JSON.stringify(run.ragBundle.diagnostics, null, 2)}
                    </pre>
                  )}
                </div>
              )}

              {mappingRequests.length > 0 && (
                <div className="rounded-md border border-border/60 bg-bg-elevated/30 p-3">
                  <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    Mapping sub-queries
                  </div>
                  <div className="space-y-1.5">
                    {mappingRequests.slice(0, 12).map((m, i) => (
                      <div key={`${m.check_id ?? i}`} className="rounded border border-border/40 bg-bg-base/40 px-2 py-1.5 text-[11px]">
                        <div className="flex items-center justify-between gap-2">
                          <Code>{String(m.check_id ?? "unknown")}</Code>
                          <span className={cn("font-mono text-[10px]", m.status === "success" ? "text-status-success" : "text-status-error")}>
                            {String(m.status ?? "unknown")}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-1 text-text-muted">
                          <span>{String(m.endpoint ?? "/v1/resolve/mapping")}</span>
                          {m.selected_capability_id != null && <Code>{String(m.selected_capability_id)}</Code>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {run.ragBundle?.capabilityThemes?.map((t, i) => (
                <div key={`th-${i}`} className="rounded-md border border-border/60 bg-bg-elevated/30 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[10px] uppercase tracking-wider text-text-muted">Knowledge document</span>
                    <Code>{t.domain}</Code>
                    {t.citations?.[0]?.source && <Code>{t.citations[0].source}</Code>}
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed text-text-secondary">{t.narrative}</p>
                  {t.citations && t.citations.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-text-muted">
                      {t.citations.slice(0, 3).map((c, j) => (
                        <a key={j} href={c.url || undefined} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-primary">
                          <ExternalLink className="h-3 w-3" /> {c.source}
                        </a>
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

function TraceRow({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2 py-0.5 text-[11px]">
      <span className="shrink-0 font-mono text-text-muted">{k}</span>
      <span className="min-w-0 text-right font-mono text-text-primary">{v}</span>
    </div>
  );
}

function MiniMetric({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded border border-border/40 bg-bg-base/40 px-2 py-1">
      <div className="font-mono text-[10px] text-text-muted">{k}</div>
      <div className="font-mono text-sm text-text-primary">{v}</div>
    </div>
  );
}

function InlineList({ items }: { items: string[] }) {
  if (!items.length) return <span className="text-text-muted">none</span>;
  return (
    <span className="flex max-w-[220px] flex-wrap justify-end gap-1">
      {items.slice(0, 6).map((item) => <Code key={item}>{item}</Code>)}
      {items.length > 6 && <span className="text-text-muted">+{items.length - 6}</span>}
    </span>
  );
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((v) => String(v)).filter(Boolean) : [];
}
