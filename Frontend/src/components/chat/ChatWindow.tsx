import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChatMessageView } from "./ChatMessage";
import type { ChatMessage, Finding, RemediationTask, SuggestionChip } from "@/types/pdca";
import { Code, Pill, SeverityPill } from "@/components/ui/status-pill";
import { ShieldCheck, X } from "lucide-react";

interface Props {
  messages: ChatMessage[];
  findings: Finding[];
  tasks: RemediationTask[];
  onApproveTask?: (id: string) => void;
  onRejectTask?: (id: string) => void;
  onSkipTask?: (id: string) => void;
  onShowTask?: (id: string) => void;
  onPreviewReport?: () => void;
  onDownloadReport?: () => void;
  onSuggestionChip?: (chip: SuggestionChip) => void;
  onSourceClick?: (checkId?: string) => void;
}

export function ChatWindow({ messages, findings, tasks, onApproveTask, onRejectTask, onSkipTask, onShowTask, onPreviewReport, onDownloadReport, onSuggestionChip, onSourceClick }: Props) {
  const findingsById = Object.fromEntries(findings.map((f) => [f.id, f]));
  const tasksById = Object.fromEntries(tasks.map((t) => [t.id, t]));
  const pendingTasks = tasks
    .filter((t) => t.decision === "pending" || t.decision === "manual_required")
    .sort((a, b) => Number(a.manualOnly || a.decision === "manual_required") - Number(b.manualOnly || b.decision === "manual_required"));
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length]);

  return (
    <ScrollArea className="h-full scrollbar-thin">
      <div className="mx-auto max-w-3xl pb-8 pt-4">
        {pendingTasks.length > 0 && (
          <QuickApprovalQueue
            tasks={pendingTasks}
            onApproveTask={onApproveTask}
            onRejectTask={onRejectTask}
            onSkipTask={onSkipTask}
          />
        )}
        {messages.map((m, i) => {
          const prev = messages[i - 1];
          const isFirstInGroup = !prev || prev.role !== m.role;
          return (
            <ChatMessageView
              key={m.id}
              message={m}
              isFirstInGroup={isFirstInGroup}
              findingsById={findingsById}
              tasksById={tasksById}
              onApproveTask={onApproveTask}
              onRejectTask={onRejectTask}
              onSkipTask={onSkipTask}
              onShowTask={onShowTask}
              onPreviewReport={onPreviewReport}
              onDownloadReport={onDownloadReport}
              onSuggestionChip={onSuggestionChip}
              onSourceClick={onSourceClick}
            />
          );
        })}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  );
}

function QuickApprovalQueue({
  tasks, onApproveTask, onRejectTask, onSkipTask,
}: {
  tasks: RemediationTask[];
  onApproveTask?: (id: string) => void;
  onRejectTask?: (id: string) => void;
  onSkipTask?: (id: string) => void;
}) {
  return (
    <div className="sticky top-0 z-10 px-4 pb-3 md:px-6">
      <Card className="overflow-hidden border-status-warning/40 bg-bg-surface/95 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between gap-3 border-b border-border/60 px-4 py-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-text-primary">
            <ShieldCheck className="h-3.5 w-3.5 text-status-warning" />
            Pending approvals
          </div>
          <Pill tone="warning">{tasks.length} waiting</Pill>
        </div>
        <div className="divide-y divide-border/40">
          {tasks.map((t) => {
            const isManual = t.manualOnly || t.decision === "manual_required";
            return (
              <div key={t.id} className="grid gap-2 px-4 py-2.5 text-[11px] md:grid-cols-[1fr_auto] md:items-center">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <SeverityPill severity={t.severity} />
                    {isManual && <Pill tone="violet">manual</Pill>}
                    <Code>{t.toolName}</Code>
                  </div>
                  <div className="mt-1 truncate text-text-primary">{t.findingTitle}</div>
                  <div className="mt-0.5 truncate text-text-muted">{t.resource}</div>
                </div>
                <div className="flex flex-wrap justify-end gap-1.5">
                  {isManual ? (
                    <Button size="sm" className="h-8 px-2.5 text-xs" onClick={() => onSkipTask?.(t.id)}>
                      <ShieldCheck className="h-3.5 w-3.5" /> Confirm
                    </Button>
                  ) : (
                    <>
                      <Button size="sm" className="h-8 px-2.5 text-xs" onClick={() => onApproveTask?.(t.id)}>
                        <ShieldCheck className="h-3.5 w-3.5" /> Remediate
                      </Button>
                      <Button variant="outline" size="sm" className="h-8 px-2.5 text-xs" onClick={() => onRejectTask?.(t.id)}>
                        <X className="h-3.5 w-3.5" /> Keep
                      </Button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
