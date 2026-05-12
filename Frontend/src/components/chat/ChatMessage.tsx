import { cn, formatTime } from "@/lib/utils";
import { ShieldCheck } from "lucide-react";
import type {
  ChatMessage, RemediationTask, Finding, AssistantCard,
  RemediationOfferCard as RemOffer, SuggestionChip,
} from "@/types/pdca";
import {
  EnvironmentCheckCardView, PlanningCardView, ScanSubmittedCardView,
  PollingCardView, FindingsCollectedCardView, RiskEvaluationCardView,
  RemediationOfferCardView, RemediationExecutionCardView, VerificationCardView,
  VerificationSummaryCardView, ReportReadyCardView, QAAnswerCardView, SuggestActionCardView,
} from "./ChatCards";

interface Props {
  message: ChatMessage;
  tasksById: Record<string, RemediationTask>;
  findingsById: Record<string, Finding>;
  onApproveTask?: (id: string) => void;
  onRejectTask?: (id: string) => void;
  onSkipTask?: (id: string) => void;
  onShowTask?: (id: string) => void;
  onPreviewReport?: () => void;
  onDownloadReport?: () => void;
  onSuggestionChip?: (chip: SuggestionChip) => void;
  onSourceClick?: (checkId?: string) => void;
  isFirstInGroup?: boolean;
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
          onSkip={() => props.onSkipTask?.(offer.taskId)}
        />
      );
    }
    case "remediation_execution": return <RemediationExecutionCardView key={key} card={card} />;
    case "verification":          return <VerificationCardView key={key} card={card} finding={props.findingsById[card.findingId]} />;
    case "verification_summary":  return <VerificationSummaryCardView key={key} card={card} findingsById={props.findingsById} />;
    case "report_ready":          return <ReportReadyCardView key={key} card={card} onPreview={props.onPreviewReport} onDownload={props.onDownloadReport} />;
    case "text":
      return (
        <p key={key} className="text-sm leading-relaxed text-text-secondary">
          {card.text}
        </p>
      );
    case "qa_answer":
      return <QAAnswerCardView key={key} card={card} onSourceClick={props.onSourceClick} />;
    case "suggest_action":
      return <SuggestActionCardView key={key} card={card} onChipClick={props.onSuggestionChip} />;
  }
}

export function ChatMessageView(props: Props) {
  const { message, isFirstInGroup = true } = props;
  const isUser = message.role === "user";
  const hasCards = (message.cards?.length ?? 0) > 0;

  if (isUser) {
    return (
      <div className="flex justify-end px-4 py-1 md:px-6 animate-fade-in-up">
        <div className="max-w-[70%]">
          <div
            className="rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm leading-relaxed text-primary-foreground shadow-sm"
          >
            {message.text}
          </div>
          <div className="mt-1 text-right text-[10px] text-text-muted">
            {formatTime(message.timestamp)}
          </div>
        </div>
      </div>
    );
  }

  // Agent messages
  return (
    <div className="px-4 py-1 md:px-6 animate-fade-in-up">
      {/* Avatar + name only on first message in a group */}
      {isFirstInGroup && (
        <div className="mb-2 flex items-center gap-2">
          <div className="grid h-6 w-6 place-items-center rounded-md bg-primary/15 ring-1 ring-primary/30">
            <ShieldCheck className="h-3.5 w-3.5 text-primary" />
          </div>
          <span className="text-[12px] font-semibold text-text-secondary">PDCA Prowler Agent</span>
          <span className="text-[10px] text-text-muted">{formatTime(message.timestamp)}</span>
        </div>
      )}

      {/* Content — left-indented to align with avatar */}
      <div className={cn("space-y-2", isFirstInGroup ? "pl-8" : "pl-8")}>
        {message.text && (
          <p className="text-sm leading-relaxed text-text-secondary">{message.text}</p>
        )}
        {hasCards && (
          <div className="space-y-2">
            {message.cards?.map((c, i) => renderCard(c, i, props))}
          </div>
        )}
      </div>
    </div>
  );
}
