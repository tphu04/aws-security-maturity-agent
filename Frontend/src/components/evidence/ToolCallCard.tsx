import type { ToolCall } from "@/types/pdca";
import { Code, ToolCategoryPill, ToolStatusPill, Pill } from "@/components/ui/status-pill";
import { cn, formatTime } from "@/lib/utils";
import { useSelection } from "@/state/selection";

export function ToolCallCard({ call }: { call: ToolCall }) {
  const { selection, selectFinding } = useSelection();
  const linked = !!call.relatedFindingId && selection.findingId === call.relatedFindingId;

  return (
    <div
      className={cn(
        "rounded-lg border border-border/60 bg-card/50 p-3 transition-colors",
        linked && "border-primary/40 bg-primary/5",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <Code className="truncate">{call.name}</Code>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <ToolCategoryPill category={call.category} />
            {call.manualOnly && <Pill tone="violet">manual_only</Pill>}
            <ToolStatusPill status={call.status} />
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[10px] text-text-muted">{formatTime(call.timestamp)}</div>
          {call.durationMs !== undefined && (
            <div className="font-mono text-[10px] text-text-secondary">
              {call.durationMs < 1000 ? `${call.durationMs}ms` : `${(call.durationMs / 1000).toFixed(2)}s`}
            </div>
          )}
        </div>
      </div>
      <div className="mt-2 space-y-1 font-mono text-[11px] leading-relaxed">
        <div className="flex gap-1.5">
          <span className="text-text-muted">→</span>
          <span className="break-words text-text-secondary">{JSON.stringify(call.inputPayload)}</span>
        </div>
        {call.outputSummary && (
          <div className="flex gap-1.5">
            <span className="text-primary">←</span>
            <span className="break-words text-text-primary">{call.outputSummary}</span>
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] text-text-muted">
        {call.relatedGraphNode && <span>node <Code className="ml-1 px-1 py-0">{call.relatedGraphNode}</Code></span>}
        {call.relatedFindingId && (
          <button
            onClick={() => selectFinding(call.relatedFindingId)}
            className="ml-auto text-primary/80 underline-offset-2 hover:underline"
          >
            finding:{call.relatedFindingId}
          </button>
        )}
      </div>
    </div>
  );
}
