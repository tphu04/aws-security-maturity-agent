import type { BackendThreadMessage } from "../api";
import type { LogLine, QaLine, UserLine, EventLine } from "../types";

let counter = 0;
function nid(): string { counter += 1; return `th-${Date.now()}-${counter}`; }

/**
 * Convert persisted backend thread messages into renderable LogLines so a
 * user can resume an earlier conversation. Run-derived events are NOT
 * reconstructed here — instead, if any assistant message references a
 * `run_id`, the caller resumes polling for that run and the run projector
 * fills in the event lines.
 */
export function threadMessagesToLines(messages: BackendThreadMessage[]): LogLine[] {
  const out: LogLine[] = [];
  for (const m of messages) {
    const ts = m.created_at * 1000;
    if (m.role === "user") {
      const text = m.content || (m.payload?.text as string) || "";
      out.push({ id: nid(), ts, k: "user", text } as UserLine);
      continue;
    }
    // assistant
    switch (m.message_type) {
      case "qa_answer": {
        const md = (m.payload?.markdown as string) ?? m.content ?? "";
        const sources = (m.payload?.sources as QaLine["sources"]) ?? undefined;
        const intentMeta = m.intent_meta as QaLine["intent"] | undefined;
        out.push({
          id: nid(), ts, k: "qa", markdown: md, done: true,
          sources, intent: intentMeta,
        } as QaLine);
        break;
      }
      case "run_started": {
        const rid = (m.payload?.run_id as string) ?? m.run_id ?? "";
        out.push({
          id: nid(), ts, k: "event", icon: "▸",
          text: `previous scan run · ${rid || "(unknown id)"}`,
          tone: "info",
        } as EventLine);
        break;
      }
      case "suggest_action":
      case "text":
      default: {
        const txt = (m.payload?.text as string) ?? (m.payload?.markdown as string) ?? m.content ?? "";
        if (!txt) continue;
        out.push({
          id: nid(), ts, k: "qa", markdown: txt, done: true,
        } as QaLine);
      }
    }
  }
  return out;
}

/** Returns the most recent run_id referenced in the message list, if any. */
export function findLastRunId(messages: BackendThreadMessage[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.run_id) return m.run_id;
    if (m.message_type === "run_started" && m.payload?.run_id) return m.payload.run_id as string;
  }
  return null;
}
