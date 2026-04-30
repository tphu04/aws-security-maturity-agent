import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessageView } from "./ChatMessage";
import type { ChatMessage, Finding, RemediationTask } from "@/types/pdca";

interface Props {
  messages: ChatMessage[];
  findings: Finding[];
  tasks: RemediationTask[];
  onApproveTask?: (id: string) => void;
  onRejectTask?: (id: string) => void;
  onShowTask?: (id: string) => void;
  onPreviewReport?: () => void;
}

export function ChatWindow({ messages, findings, tasks, onApproveTask, onRejectTask, onShowTask, onPreviewReport }: Props) {
  const findingsById = Object.fromEntries(findings.map((f) => [f.id, f]));
  const tasksById = Object.fromEntries(tasks.map((t) => [t.id, t]));
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length]);

  return (
    <ScrollArea className="h-full scrollbar-thin">
      <div className="mx-auto max-w-4xl pb-6 pt-3">
        {messages.map((m) => (
          <ChatMessageView
            key={m.id}
            message={m}
            findingsById={findingsById}
            tasksById={tasksById}
            onApproveTask={onApproveTask}
            onRejectTask={onRejectTask}
            onShowTask={onShowTask}
            onPreviewReport={onPreviewReport}
          />
        ))}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  );
}
