import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageView } from "./ChatMessage";
import type { ChatMessage, Finding, RemediationTask, SuggestionChip } from "@/types/pdca";

interface Props {
  messages: ChatMessage[];
  findings: Finding[];
  tasks: RemediationTask[];
  onApproveTask?: (id: string) => void;
  onRejectTask?: (id: string) => void;
  onShowTask?: (id: string) => void;
  onPreviewReport?: () => void;
  onSuggestionChip?: (chip: SuggestionChip) => void;
  onSourceClick?: (checkId?: string) => void;
}

export function ChatWindow({ messages, findings, tasks, onApproveTask, onRejectTask, onShowTask, onPreviewReport, onSuggestionChip, onSourceClick }: Props) {
  const findingsById = Object.fromEntries(findings.map((f) => [f.id, f]));
  const tasksById = Object.fromEntries(tasks.map((t) => [t.id, t]));
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length]);

  return (
    <ScrollArea className="h-full scrollbar-thin">
      <div className="mx-auto max-w-3xl pb-8 pt-4">
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
              onShowTask={onShowTask}
              onPreviewReport={onPreviewReport}
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
