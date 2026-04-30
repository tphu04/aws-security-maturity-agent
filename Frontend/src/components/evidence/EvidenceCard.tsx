import type { Evidence } from "@/types/pdca";
import { Code, FindingStatusPill, SeverityPill, VerificationPill, DecisionPill, Pill } from "@/components/ui/status-pill";
import { cn, formatTime } from "@/lib/utils";
import { useSelection } from "@/state/selection";
import { useEffect, useRef } from "react";

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const { selection, selectEvidence } = useSelection();
  const isSel = selection.evidenceId === evidence.id;
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isSel) ref.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [isSel]);

  const handleClick = () =>
    selectEvidence(evidence.id, {
      findingId: evidence.relatedFindingId,
      messageId: evidence.relatedMessageId,
    });

  return (
    <div
      ref={ref}
      onClick={handleClick}
      className={cn(
        "cursor-pointer rounded-lg border border-border/60 bg-card/50 p-3 transition-all",
        isSel
          ? "ring-2 ring-primary/60 shadow-[0_0_18px_-4px_hsl(var(--primary)/0.5)]"
          : "hover:border-border",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Pill tone="neutral" className="font-mono">{evidence.kind}</Pill>
          <Code>{evidence.id}</Code>
        </div>
        <span className="font-mono text-[10px] text-text-muted">{formatTime(evidence.timestamp)}</span>
      </div>

      {evidence.kind === "scanner_job" && (
        <div className="mt-2 space-y-1 text-[11px]">
          <div className="flex items-center gap-1.5"><Pill tone="primary" className="font-mono">{evidence.httpMethod}</Pill> <Code>{evidence.apiEndpoint}</Code></div>
          <div className="text-text-secondary">job <Code>{evidence.jobId}</Code> · task <Code>{evidence.taskType}={evidence.taskValue}</Code></div>
          {typeof evidence.resultCount === "number" && (
            <div className="text-text-muted">{evidence.resultCount} checks · status <span className="text-text-primary">{evidence.status}</span></div>
          )}
        </div>
      )}

      {evidence.kind === "finding" && (
        <div className="mt-2 space-y-1.5 text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <SeverityPill severity={evidence.severity} />
            <FindingStatusPill status={evidence.status} />
            <Code className="ml-auto">{evidence.prowlerCheckId}</Code>
          </div>
          <div className="text-text-secondary"><Code>{evidence.resource}</Code></div>
          <p className="text-text-primary/90">{evidence.snippet}</p>
        </div>
      )}

      {evidence.kind === "remediation" && (
        <div className="mt-2 space-y-1.5 text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <Code>{evidence.toolName}</Code>
            <DecisionPill decision={evidence.decision} />
            <VerificationPill status={evidence.verificationStatus} />
          </div>
          <div className="text-text-secondary"><Code>{evidence.resource}</Code></div>
          <div className="grid gap-1 text-text-secondary">
            <div><span className="text-status-error">before:</span> {evidence.beforeState}</div>
            <div><span className="text-status-success">after:</span> {evidence.afterState}</div>
          </div>
        </div>
      )}

      {evidence.kind === "verification" && (
        <div className="mt-2 space-y-1.5 text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill tone={evidence.result === "PASS" ? "success" : evidence.result === "FAIL" ? "danger" : "violet"}>{evidence.result}</Pill>
            <Code>{evidence.prowlerCheckId}</Code>
          </div>
          <p className="text-text-primary/90">{evidence.snippet}</p>
        </div>
      )}

      <div className="mt-2 flex items-center justify-between text-[10px] text-text-muted">
        {evidence.sourceNode && <span>node <Code className="ml-1 px-1 py-0">{evidence.sourceNode}</Code></span>}
        {evidence.relatedFindingId && <span>→ finding {evidence.relatedFindingId}</span>}
      </div>
    </div>
  );
}
