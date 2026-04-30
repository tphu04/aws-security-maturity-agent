import type { GraphNode, GraphNodeName } from "@/types/pdca";
import { cn, formatTime } from "@/lib/utils";
import { Code, NodeStatusPill } from "@/components/ui/status-pill";
import {
  CloudCog, ListChecks, Send, RefreshCw, Database, Gauge, Wrench,
  CheckCircle2, RotateCcw, PlayCircle, ShieldCheck, FileText, Workflow,
} from "lucide-react";

const NODE_ICON: Record<GraphNodeName, React.ElementType> = {
  environment: CloudCog,
  planning: ListChecks,
  scan_submit: Send,
  scan_poll: RefreshCw,
  scan_collect: Database,
  risk_evaluation: Gauge,
  operational_planning: Wrench,
  review_task: CheckCircle2,
  reset_index: RotateCcw,
  execution: PlayCircle,
  verification: ShieldCheck,
  report: FileText,
};

function fmtMs(ms?: number) {
  if (!ms) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function GraphTimeline({
  nodes, currentNode, dense = false,
}: { nodes: GraphNode[]; currentNode?: GraphNodeName; dense?: boolean }) {
  return (
    <div className="space-y-1">
      <div className="mb-2 flex items-center gap-2 px-1 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        <Workflow className="h-3.5 w-3.5 text-primary" />
        LangGraph timeline
      </div>
      <ol className="relative">
        {nodes.map((n, i) => {
          const Icon = NODE_ICON[n.name];
          const isLast = i === nodes.length - 1;
          const isCurrent = currentNode === n.name;
          return (
            <li key={n.name} className="relative flex gap-3">
              <div className="flex flex-col items-center pt-1">
                <div
                  className={cn(
                    "grid h-7 w-7 place-items-center rounded-full ring-2 transition-colors",
                    n.status === "completed" && "bg-status-success/15 ring-status-success/40 text-status-success",
                    n.status === "running"   && "bg-severity-info/15 ring-severity-info/40 text-severity-info",
                    n.status === "waiting"   && "bg-status-warning/15 ring-status-warning/40 text-status-warning",
                    n.status === "failed"    && "bg-status-error/15 ring-status-error/40 text-status-error",
                    n.status === "skipped"   && "bg-bg-elevated ring-border text-text-muted",
                    n.status === "queued"    && "bg-bg-elevated ring-border text-text-secondary",
                    isCurrent && "shadow-[0_0_18px_-2px_hsl(var(--primary)/0.6)]",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" />
                </div>
                {!isLast && <div className="my-1 w-px flex-1 bg-border/60" />}
              </div>

              <div className={cn("mb-2 flex-1 rounded-lg border border-border/60 bg-card/40 p-3 transition-colors", isCurrent && "border-primary/40 bg-primary/5")}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Code>{n.name}</Code>
                    {n.checkpointed && (
                      <span title="Checkpointed" className="text-[9px] uppercase tracking-wider text-text-muted">●</span>
                    )}
                  </div>
                  <NodeStatusPill status={n.status} />
                </div>
                {!dense && (
                  <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-text-secondary">
                    {n.startedAt && <div>started <span className="font-mono text-text-primary">{formatTime(n.startedAt)}</span></div>}
                    {n.durationMs !== undefined && <div>dur <span className="font-mono text-text-primary">{fmtMs(n.durationMs)}</span></div>}
                  </div>
                )}
                {!dense && n.outputSummary && (
                  <div className="mt-1.5 text-[11px] leading-relaxed text-text-secondary">
                    <span className="text-primary">←</span> {n.outputSummary}
                  </div>
                )}

                {n.pollIterations && n.pollIterations.length > 0 && (
                  <div className="mt-2 space-y-1">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">poll iterations</div>
                    <div className="space-y-1">
                      {n.pollIterations.map((p) => (
                        <div key={p.index} className="flex items-center justify-between rounded border border-border/50 bg-bg-elevated/40 px-2 py-1 text-[11px]">
                          <span className="font-mono text-text-primary">poll #{p.index}</span>
                          <span className="text-text-secondary">
                            <span className="font-mono">{p.completedAfter}</span> done · <span className="font-mono">{p.pendingAfter}</span> pending · <span className="font-mono">+{p.newFindings}</span> findings
                          </span>
                          <span className="font-mono text-text-muted">{fmtMs(p.durationMs)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
