import type {
  AssistantCard,
  ChatMessage,
  IntentKind,
  IntentMeta,
  QASource,
  SuggestionChip,
} from "@/types/pdca";
import type { BackendChatMessage, BackendThreadMessage } from "@/lib/api";

export function backendMessageToCards(m: BackendChatMessage): AssistantCard[] {
  const p = m.payload || {};
  switch (m.type) {
    case "qa_answer": {
      const intentMeta = p.intentMeta as { classified?: IntentKind; confidence?: number; reason?: string } | undefined;
      return [{
        kind: "qa_answer",
        markdown: String(p.markdown ?? p.text ?? ""),
        sources: (p.sources as QASource[] | undefined) ?? [],
        intentMeta: intentMeta && intentMeta.classified && typeof intentMeta.confidence === "number"
          ? { classified: intentMeta.classified, confidence: intentMeta.confidence, reason: intentMeta.reason } satisfies IntentMeta
          : undefined,
      }];
    }
    case "suggest_action": {
      return [{
        kind: "suggest_action",
        prompt: typeof p.prompt === "string" ? p.prompt : undefined,
        chips: (p.chips as SuggestionChip[] | undefined) ?? [],
      }];
    }
    case "run_started": {
      return [{ kind: "text", text: String(p.text ?? `Run ${p.run_id ?? ""} started.`) }];
    }
    case "text":
    case "error":
    default:
      return [{ kind: "text", text: String(p.text ?? p.markdown ?? "(empty message)") }];
  }
}

export function threadMessagesToChatMessages(messages: BackendThreadMessage[]): ChatMessage[] {
  return messages.map((m) => {
    const timestamp = new Date(m.created_at * 1000).toISOString();
    if (m.role === "user") {
      return {
        id: `srv-${m.id}`,
        role: "user",
        timestamp,
        text: m.content || String(m.payload?.text ?? ""),
      };
    }
    const type = m.message_type === "user_text" ? "text" : m.message_type;
    return {
      id: `srv-${m.id}`,
      role: "assistant",
      timestamp,
      cards: backendMessageToCards({ type, payload: m.payload }),
    };
  });
}

export function findLastRunId(messages: BackendThreadMessage[]): string | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (m.run_id) return m.run_id;
    if (m.message_type === "run_started" && m.payload?.run_id) {
      return String(m.payload.run_id);
    }
  }
  return null;
}
