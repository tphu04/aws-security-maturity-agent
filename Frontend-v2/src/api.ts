// Thin chatbot API client — only the endpoints v2 needs.

import type { AwsEnvironment, RunSession } from "./types";

const STORAGE_KEY = "pdca.v2.endpoints";

export interface EndpointConfig {
  chatbot: string;
  scanner: string;
  rag: string;
}

const DEFAULT_ENDPOINTS: EndpointConfig = {
  chatbot: (import.meta.env.VITE_CHATBOT_API_URL as string | undefined) ?? "/api/chatbot",
  scanner: (import.meta.env.VITE_SCANNER_API_URL as string | undefined) ?? "/api/scanner",
  rag: (import.meta.env.VITE_RAG_API_URL as string | undefined) ?? "/api/rag",
};

export function loadEndpoints(): EndpointConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ENDPOINTS;
    return { ...DEFAULT_ENDPOINTS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_ENDPOINTS;
  }
}

export function saveEndpoints(cfg: Partial<EndpointConfig>): EndpointConfig {
  const next = { ...loadEndpoints(), ...cfg };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, msg: string) {
    super(`API ${status}: ${msg}`);
    this.status = status;
  }
}

async function req<T>(path: string, init: RequestInit = {}, timeoutMs = 12_000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  const base = loadEndpoints().chatbot.replace(/\/+$/, "");
  try {
    const res = await fetch(base + path, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body?.detail ?? body?.message ?? detail;
      } catch { /* ignore */ }
      throw new ApiError(res.status, String(detail));
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

export interface BackendChatMessage {
  type: "qa_answer" | "suggest_action" | "run_started" | "text" | "error";
  payload: Record<string, unknown>;
}

export interface BackendChatResponse {
  messages: BackendChatMessage[];
  intent: {
    intent: "qa" | "scan" | "mixed";
    confidence: number;
    reason?: string;
    target_service?: string | null;
    finding_ref?: string | null;
  };
  thread_id: string;
  run_id?: string | null;
}

export type ChatStreamEvent =
  | { type: "meta"; data: { thread_id: string; intent: BackendChatResponse["intent"]; run_id?: string | null } }
  | { type: "sources"; data: Array<Record<string, unknown>> }
  | { type: "delta"; data: { text: string } }
  | { type: "messages"; data: BackendChatMessage[] }
  | { type: "done"; data: Record<string, unknown> }
  | { type: "error"; data: { message: string } };

export interface BackendThreadSummary {
  thread_id: string;
  title: string;
  last_role: string;
  last_content: string;
  last_run_id?: string | null;
  message_count: number;
  created_at: number;
  updated_at: number;
}

export interface BackendThreadMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  message_type: BackendChatMessage["type"] | "user_text";
  payload: Record<string, unknown>;
  intent_meta?: Record<string, unknown> | null;
  run_id?: string | null;
  created_at: number;
}

export const api = {
  async ping(): Promise<{ ok: true } | { ok: false; reason: string }> {
    try {
      await req<{ ok: boolean }>("/v1/ping", {}, 3000);
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: (e as Error).message };
    }
  },

  getEnvironment(): Promise<AwsEnvironment> {
    return req("/v1/environment");
  },

  getRun(runId: string): Promise<RunSession> {
    return req(`/v1/runs/${encodeURIComponent(runId)}`, {}, 30_000);
  },

  approve(runId: string, taskId: string, decision: "approved" | "rejected" | "skipped"): Promise<{ ok: boolean }> {
    return req(`/v1/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(taskId)}`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
  },

  listThreads(limit = 50, offset = 0): Promise<{ items: BackendThreadSummary[] }> {
    return req(`/v1/threads?limit=${limit}&offset=${offset}`);
  },

  getThreadMessages(threadId: string, limit = 200): Promise<{ thread_id: string; messages: BackendThreadMessage[] }> {
    return req(`/v1/threads/${encodeURIComponent(threadId)}/messages?limit=${limit}`);
  },

  deleteThread(threadId: string): Promise<{ ok: boolean }> {
    return req(`/v1/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  },

  reportUrl(runId: string, format: "markdown" | "json" = "markdown"): string {
    const base = loadEndpoints().chatbot.replace(/\/+$/, "");
    return `${base}/v1/runs/${encodeURIComponent(runId)}/report?format=${format}`;
  },

  /**
   * SSE chat stream. Returns an AbortController so the caller can cancel.
   */
  chatStream(
    prompt: string,
    onEvent: (ev: ChatStreamEvent) => void,
    opts?: { threadId?: string; runId?: string },
  ): AbortController {
    const ac = new AbortController();
    const base = loadEndpoints().chatbot.replace(/\/+$/, "");
    (async () => {
      try {
        const resp = await fetch(base + "/v1/chat/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Accept": "text/event-stream" },
          body: JSON.stringify({
            prompt,
            thread_id: opts?.threadId,
            run_id: opts?.runId,
            history: [],
          }),
          signal: ac.signal,
        });
        if (!resp.ok || !resp.body) {
          onEvent({ type: "error", data: { message: `HTTP ${resp.status}` } });
          return;
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buf = "";
        try {
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let idx;
            while ((idx = buf.indexOf("\n\n")) !== -1) {
              const frame = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              const ev = parseSseFrame(frame);
              if (ev) onEvent(ev);
            }
          }
        } finally {
          reader.cancel().catch(() => {});
        }
      } catch (e) {
        if (e instanceof Error && e.name === "AbortError") return;
        const msg = e instanceof Error ? e.message : String(e);
        onEvent({ type: "error", data: { message: msg } });
      }
    })();
    return ac;
  },
};

const SSE_VALID_TYPES = new Set(["meta", "delta", "sources", "messages", "done", "error"]);

function parseSseFrame(frame: string): ChatStreamEvent | null {
  const lines = frame.split(/\r?\n/);
  let event = "message";
  const dataParts: string[] = [];
  for (const ln of lines) {
    if (ln.startsWith("event:")) event = ln.slice(6).trim();
    else if (ln.startsWith("data:")) dataParts.push(ln.slice(5).trim());
  }
  if (dataParts.length === 0) return null;
  if (!SSE_VALID_TYPES.has(event)) return null;
  try {
    const data = JSON.parse(dataParts.join("\n"));
    return { type: event as ChatStreamEvent["type"], data };
  } catch {
    return null;
  }
}
