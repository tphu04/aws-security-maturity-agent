// Thin HTTP client shared by all backend integrations.
// See ./contracts.md for the canonical FE↔BE contract.

export interface BackendJob {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed" | "timeout" | "cancelled";
  task_type: "group" | "custom_file" | string;
  task_value: string;
  command_details: string;
  submitted_time: number;
  start_time?: number | null;
  end_time?: number | null;
  duration_seconds?: number | null;
  summary_text?: string | null;
  result?: unknown[] | null;
  error?: { error: string; details?: string } | null;
}

export interface BackendJobListItem {
  job_id: string;
  status: BackendJob["status"];
  details: string;
  submitted_time: number;
}

export interface BackendJobList {
  items: BackendJobListItem[];
  limit: number;
  offset: number;
}

export interface ScanSubmitResponse {
  status: "pending";
  job_id: string;
  message: string;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

const STORAGE_KEY = "pdca.endpoints";

export interface EndpointConfig {
  scanner: string;
  rag: string;
  chatbot?: string;
}

// In dev, use Vite proxy paths (same-origin, no CORS preflight).
// In production build, fall back to explicit URLs via env vars.
const DEFAULT_ENDPOINTS: EndpointConfig = {
  scanner: import.meta.env.VITE_SCANNER_API_URL ?? "/api/scanner",
  rag:     import.meta.env.VITE_RAG_API_URL     ?? "/api/rag",
  chatbot: import.meta.env.VITE_CHATBOT_API_URL ?? "/api/chatbot",
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

async function request<T>(
  base: string,
  path: string,
  init: RequestInit = {},
  timeoutMs = 10_000,
): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(base.replace(/\/+$/, "") + path, {
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
    clearTimeout(timer);
  }
}

// ───────────── Scanner API (existing) ─────────────

export const scannerApi = {
  submitGroup(group: string): Promise<ScanSubmitResponse> {
    return request(loadEndpoints().scanner, "/v1/scan/group", {
      method: "POST",
      body: JSON.stringify({ group }),
    });
  },

  submitChecks(checkIds: string): Promise<ScanSubmitResponse> {
    return request(loadEndpoints().scanner, "/v1/scan/checks", {
      method: "POST",
      body: JSON.stringify({ check_ids: checkIds }),
    });
  },

  submitCustom(filename: string): Promise<ScanSubmitResponse> {
    return request(loadEndpoints().scanner, "/v1/scan/custom", {
      method: "POST",
      body: JSON.stringify({ filename }),
    });
  },

  getJob(jobId: string): Promise<BackendJob> {
    return request(loadEndpoints().scanner, `/v1/job/${encodeURIComponent(jobId)}`);
  },

  cancelJob(jobId: string): Promise<{ ok: boolean; job_id: string; status: BackendJob["status"] }> {
    return request(loadEndpoints().scanner, `/v1/job/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    });
  },

  listJobs(limit = 50, offset = 0): Promise<BackendJobList> {
    return request(
      loadEndpoints().scanner,
      `/v1/jobs?limit=${limit}&offset=${offset}`,
    );
  },

  // Lightweight reachability probe.
  async ping(): Promise<{ ok: true } | { ok: false; reason: string }> {
    try {
      await request(loadEndpoints().scanner, "/v1/jobs?limit=1", {}, 4_000);
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: e instanceof Error ? e.message : String(e) };
    }
  },
};

// ───────────── RAG API (read-only probe for now) ─────────────

export const ragApi = {
  async ping(): Promise<{ ok: true } | { ok: false; reason: string }> {
    try {
      await request(loadEndpoints().rag, "/", {}, 4_000);
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: e instanceof Error ? e.message : String(e) };
    }
  },
};

// ───────────── Chatbot API ─────────────

export interface BackendEnvironment {
  status: "not_connected" | "validating" | "connected" | "error" | "expired_session" | "missing_permissions";
  accountMask: string;
  region: string;
  credentialType: string;
  lastValidatedAt: string;
  bucketsDiscovered: number;
  ragAvailable: boolean;
}

export interface BackendRunListItem {
  id: string;
  target: string;
  status: string;
  startedAt: string;
  durationMs: number;
  findingsTotal: number;
  remediated: number;
  reportStatus: "pending" | "ready" | "failed";
  awsAccountMask: string;
  kind: "run" | "scan_job";
}

export interface BackendRunList {
  items: BackendRunListItem[];
  limit: number;
  offset: number;
}

function chatbotBase(): string | null {
  return loadEndpoints().chatbot ?? null;
}

export const chatbotApi = {
  isConfigured: () => Boolean(chatbotBase()),

  async ping(): Promise<{ ok: true } | { ok: false; reason: string }> {
    const base = chatbotBase();
    if (!base) return { ok: false, reason: "no chatbot URL configured" };
    try {
      // /v1/ping: < 5 ms, no AWS calls, no heavy JSON schema.
      await request(base, "/v1/ping", {}, 2_000);
      return { ok: true };
    } catch (e) {
      return { ok: false, reason: e instanceof Error ? e.message : String(e) };
    }
  },

  getEnvironment(): Promise<BackendEnvironment> {
    return request(chatbotBase()!, "/v1/environment", {}, 12_000);
  },

  createRun(prompt: string, scope?: string): Promise<{ run_id: string; thread_id: string; status: string }> {
    return request(chatbotBase()!, "/v1/runs", {
      method: "POST",
      body: JSON.stringify({ prompt, scope }),
    });
  },

  listRuns(limit = 50, offset = 0): Promise<BackendRunList> {
    return request(chatbotBase()!, `/v1/runs?limit=${limit}&offset=${offset}`);
  },

  // Returns the FE-shaped RunSession directly — orchestrator already emits
  // it in the canonical shape, so no adapter needed.
  getRun(runId: string): Promise<unknown> {
    return request(chatbotBase()!, `/v1/runs/${encodeURIComponent(runId)}`);
  },

  approve(runId: string, taskId: string, decision: "approved" | "rejected" | "skipped"): Promise<{ ok: boolean }> {
    return request(chatbotBase()!, `/v1/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(taskId)}`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
  },

  cancelRun(runId: string): Promise<{ ok: boolean; run_id: string; status: string }> {
    return request(chatbotBase()!, `/v1/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
    }, 15_000);
  },

  // Unified chat — Phase 1. Backend classifies intent and routes:
  //  - qa     → { messages: [qa_answer] }
  //  - scan   → { messages: [run_started], run_id }
  //  - action → { messages: [text] }   (Phase 3 wires real action)
  //  - mixed  → { messages: [qa_answer, suggest_action] }
  chat(prompt: string, opts?: { threadId?: string; runId?: string; history?: { role: "user" | "assistant"; content: string }[] }): Promise<BackendChatResponse> {
    return request(chatbotBase()!, "/v1/chat", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        thread_id: opts?.threadId,
        run_id: opts?.runId,
        history: opts?.history ?? [],
      }),
    }, 60_000);
  },

  listThreads(limit = 50, offset = 0): Promise<BackendThreadList> {
    return request(chatbotBase()!, `/v1/threads?limit=${limit}&offset=${offset}`);
  },

  createThread(title = "New chat"): Promise<BackendThreadSummary> {
    return request(chatbotBase()!, "/v1/threads", {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },

  getThreadMessages(threadId: string, limit = 200): Promise<BackendThreadMessages> {
    return request(chatbotBase()!, `/v1/threads/${encodeURIComponent(threadId)}/messages?limit=${limit}`);
  },

  deleteThread(threadId: string): Promise<{ ok: boolean; thread_id: string }> {
    return request(chatbotBase()!, `/v1/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  },

  reportUrl(runId: string, format: "pdf" | "markdown" | "json" = "pdf", download = false): string {
    const base = chatbotBase();
    if (!base) return "#";
    const params = new URLSearchParams({ format });
    if (download) params.set("download", "1");
    return joinUrl(base, `/v1/runs/${encodeURIComponent(runId)}/report?${params.toString()}`);
  },

  /**
   * SSE-streamed variant of `chat`. Returns an AbortController so the caller
   * can cancel. Events arrive via `onEvent` — see ChatStreamEvent for shape.
   *
   * Falls back to a regular chat call if the browser lacks streaming support
   * (very old) or fetch throws — caller can detect via the final "error" event.
   */
  chatStream(
    prompt: string,
    onEvent: (ev: ChatStreamEvent) => void,
    opts?: { threadId?: string; runId?: string; signal?: AbortSignal },
  ): AbortController {
    const ac = new AbortController();
    if (opts?.signal) opts.signal.addEventListener("abort", () => ac.abort());
    const base = chatbotBase();
    if (!base) {
      queueMicrotask(() => onEvent({ type: "error", data: { message: "no chatbot URL configured" } }));
      return ac;
    }
    (async () => {
      try {
        const resp = await fetch(joinUrl(base, "/v1/chat/stream"), {
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
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          // SSE frames are terminated by a blank line ("\n\n").
          let idx;
          while ((idx = buf.indexOf("\n\n")) !== -1) {
            const frame = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            const ev = parseSseFrame(frame);
            if (ev) onEvent(ev);
          }
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        onEvent({ type: "error", data: { message: (e as Error).message || String(e) } });
      }
    })();
    return ac;
  },
};

export type ChatStreamEvent =
  | { type: "meta"; data: { thread_id: string; intent: BackendChatResponse["intent"]; run_id?: string | null } }
  | { type: "sources"; data: Array<Record<string, unknown>> }
  | { type: "delta"; data: { text: string } }
  | { type: "messages"; data: BackendChatMessage[] }
  | { type: "suggestions"; data: BackendSuggestion[] }
  | { type: "done"; data: Record<string, unknown> }
  | { type: "error"; data: { message: string } };

function joinUrl(base: string, path: string): string {
  return base.replace(/\/+$/, "") + path;
}

function parseSseFrame(frame: string): ChatStreamEvent | null {
  const lines = frame.split(/\r?\n/);
  let event = "message";
  const dataParts: string[] = [];
  for (const ln of lines) {
    if (ln.startsWith("event:")) event = ln.slice(6).trim();
    else if (ln.startsWith("data:")) dataParts.push(ln.slice(5).trim());
  }
  if (dataParts.length === 0) return null;
  const raw = dataParts.join("\n");
  try {
    const data = JSON.parse(raw);
    return { type: event as ChatStreamEvent["type"], data };
  } catch {
    return null;
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
    source?: string;
  };
  thread_id: string;
  run_id?: string | null;
  suggestions?: BackendSuggestion[];
}

export interface BackendSuggestion {
  label: string;
  kind: "qa" | "scan";
  payload: string;
}

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

export interface BackendThreadList {
  items: BackendThreadSummary[];
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

export interface BackendThreadMessages {
  thread_id: string;
  messages: BackendThreadMessage[];
}
