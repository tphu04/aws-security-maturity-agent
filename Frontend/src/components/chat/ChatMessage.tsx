import { cn, formatTime } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import type {
  ChatMessage, RemediationTask, Finding, AssistantCard,
  RemediationOfferCard as RemOffer,
} from "@/types/pdca";
import {
  EnvironmentCheckCardView, PlanningCardView, ScanSubmittedCardView,
  PollingCardView, FindingsCollectedCardView, RiskEvaluationCardView,
  RemediationOfferCardView, RemediationExecutionCardView, VerificationCardView,
  ReportReadyCardView,
} from "./ChatCards";

interface Props {
  message: ChatMessage;
  tasksById: Record<string, RemediationTask>;
  findingsById: Record<string, Finding>;
  onApproveTask?: (id: string) => void;
  onRejectTask?: (id: string) => void;
  onShowTask?: (id: string) => void;
  onPreviewReport?: () => void;
}

function renderCard(card: AssistantCard, idx: number, props: Props) {
  const key = `${props.message.id}-${idx}`;
  switch (card.kind) {
    case "environment_check":   return <EnvironmentCheckCardView   key={key} card={card} />;
    case "planning":            return <PlanningCardView           key={key} card={card} />;
    case "scan_submitted":      return <ScanSubmittedCardView      key={key} card={card} />;
    case "polling":             return <PollingCardView            key={key} card={card} />;
    case "findings_collected":  return <FindingsCollectedCardView  key={key} card={card} />;
    case "risk_evaluation":     return <RiskEvaluationCardView     key={key} card={card} />;
    case "remediation_offer": {
      const offer = card as RemOffer;
      const task = props.tasksById[offer.taskId];
      if (!task) return null;
      return (
        <RemediationOfferCardView
          key={key} card={offer} task={task}
          onApprove={() => props.onApproveTask?.(offer.taskId)}
          onReject={() => props.onRejectTask?.(offer.taskId)}
          onShowDetails={() => props.onShowTask?.(offer.taskId)}
        />
      );
    }
    case "remediation_execution": return <RemediationExecutionCardView key={key} card={card} />;
    case "verification":          return <VerificationCardView key={key} card={card} finding={props.findingsById[card.findingId]} />;
    case "report_ready":          return <ReportReadyCardView key={key} card={card} onPreview={props.onPreviewReport} />;
    case "text":
      return (
        <div key={key} className="rounded-2xl border border-border/70 bg-card/60 px-4 py-2.5 text-sm leading-relaxed">
          {card.text}
        </div>
      );
  }
}

export function ChatMessageView(props: Props) {
  const { message } = props;
  const isUser = message.role === "user";

  return (
    <div className={cn("flex w-full gap-3 px-4 py-3 md:px-6 animate-fade-in-up", isUser ? "justify-end" : "justify-start")}>
      {!isUser && (
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/15 ring-1 ring-primary/30">
          <Bot className="h-4 w-4 text-primary" />
        </div>
      )}
      <div className={cn("flex max-w-[760px] flex-col gap-2", isUser && "items-end")}>
        <div className="flex items-center gap-2 text-[11px] text-text-muted">
          <span className="font-medium text-text-secondary">{isUser ? "You" : "PDCA Prowler Agent"}</span>
          <span className="font-mono">{formatTime(message.timestamp)}</span>
        </div>
        {message.text && (
          <div
            className={cn(
              "rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
              isUser
                ? "bg-primary/10 text-text-primary border border-primary/30 rounded-br-sm"
                : "bg-card/60 border border-border/70 rounded-bl-sm",
            )}
          >
            {message.text}
          </div>
        )}
        {message.cards?.map((c, i) => renderCard(c, i, props))}
      </div>
      {isUser && (
        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-bg-elevated ring-1 ring-border">
          <User className="h-4 w-4 text-text-secondary" />
        </div>
      )}
    </div>
  );
}
