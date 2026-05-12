import { useState } from "react";
import type { ApprovalLine } from "../types";

interface Props {
  line: ApprovalLine;
  onDecide: (taskId: string, decision: "approved" | "rejected" | "skipped") => void;
}

export function ApprovalBlock({ line, onDecide }: Props) {
  const [showDetails, setShowDetails] = useState(false);
  const t = line.task;
  const resolved = line.resolved;

  return (
    <div className="my-2 border-l-2 border-warn pl-3 py-1">
      <div className="flex items-center gap-2">
        <span className="text-warn">⚠</span>
        <span className="font-bold">Pending approval:</span>
        <span>{t.toolName}</span>
        <span className="text-dim">· severity={t.severity}</span>
      </div>
      <div className="text-dim mt-0.5"><span className="inline-block w-20">Resource:</span> {t.resource}</div>
      <div className="text-dim"><span className="inline-block w-20">Proposed:</span> <code className="text-fg">{t.proposedAction}</code></div>
      <div className="text-dim"><span className="inline-block w-20">Impact:</span> {t.expectedImpact}</div>

      {(t.ragSteps?.length || t.ragEffort || t.ragRollback) && (
        <details className="mt-1 text-dim text-[12px]">
          <summary>
            <span className="chev">▸</span> RAG guidance
            {t.ragEffort && <> · effort={t.ragEffort}</>}
          </summary>
          <div className="pl-4 mt-1 space-y-1">
            {t.ragSteps && t.ragSteps.length > 0 && (
              <ol className="list-decimal pl-4">
                {t.ragSteps.map(s => (
                  <li key={s.order}>
                    <span className="text-dim">[{s.type}]</span>{" "}
                    <code className="text-fg">{s.snippet}</code>
                    {s.prerequisite && <div className="text-dim pl-2">prereq: {s.prerequisite}</div>}
                  </li>
                ))}
              </ol>
            )}
            {t.ragRollback && <div>rollback: <code>{t.ragRollback}</code></div>}
            {t.ragSideEffects && t.ragSideEffects.length > 0 && (
              <div>side effects: {t.ragSideEffects.join(", ")}</div>
            )}
          </div>
        </details>
      )}

      <details
        open={showDetails}
        onToggle={(e) => setShowDetails((e.target as HTMLDetailsElement).open)}
        className="mt-1 text-dim text-[12px]"
      >
        <summary><span className="chev">▸</span> tool params · permission</summary>
        <div className="pl-4 mt-1 space-y-1">
          <div>permission: <code>{t.requiredAwsPermission}</code></div>
          <pre className="!my-1">{JSON.stringify(t.toolParams, null, 2)}</pre>
          {t.guardChecks && (
            <div className="text-dim">
              guards: registered={String(t.guardChecks.registeredTool)} ·
              remediation={String(t.guardChecks.isRemediationCategory)} ·
              auto={String(t.guardChecks.notManualOnly)}
            </div>
          )}
        </div>
      </details>

      <div className="mt-2 flex items-center gap-2">
        {resolved ? (
          <span className={resolved === "approved" ? "text-accent" : resolved === "rejected" ? "text-err" : "text-dim"}>
            {resolved === "approved" ? "✓ approved" : resolved === "rejected" ? "✗ rejected" : "↷ skipped"}
          </span>
        ) : (
          <>
            <button
              onClick={() => onDecide(t.id, "approved")}
              className="px-2 py-0.5 border border-accent text-accent hover:bg-accent/10 rounded"
            >Approve</button>
            <button
              onClick={() => onDecide(t.id, "rejected")}
              className="px-2 py-0.5 border border-err text-err hover:bg-err/10 rounded"
            >Reject</button>
            <button
              onClick={() => onDecide(t.id, "skipped")}
              className="px-2 py-0.5 border border-dim text-dim hover:bg-dim/10 rounded"
            >Skip</button>
            <button
              onClick={() => setShowDetails(v => !v)}
              className="px-2 py-0.5 border border-border text-fg hover:bg-border/40 rounded"
            >Details</button>
            <span className="ml-auto text-dim text-[11px]">a / r / s · d</span>
          </>
        )}
      </div>
    </div>
  );
}
