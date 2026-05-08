// Thin HTTP client shared by all backend integrations.
// See ./contracts.md for the canonical FE↔BE contract.

export interface BackendJob {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
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

const DEFAULT_ENDPOINTS: EndpointConfig = {
  scanner: import.meta.env.VITE_SCANNER_API_URL ?? "http://127.0.0.1:9001",
  rag:     import.meta.env.VITE_RAG_API_URL     ?? "http://localhost:9005",
  chatbot: import.meta.env.VITE_CHATBOT_API_URL ?? "http://127.0.0.1:9002",
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
      // Long timeout: /v1/environment calls boto3 STS + S3 + RAG, can be ~5s.
      await request(base, "/v1/environment", {}, 12_000);
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
};
