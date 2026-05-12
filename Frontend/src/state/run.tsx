import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import type { ChatMessage, RunHistoryRow, RunSession, ScanJob } from "@/types/pdca";
import { emptyRun } from "@/data/mockRun";
import { chatbotApi, scannerApi, ApiError, type BackendThreadSummary } from "@/lib/api";
import { findLastRunId, threadMessagesToChatMessages } from "@/lib/chatAdapters";
import {
  environmentFromBackend,
  findingsFromJob,
  jobToScanJob,
  runHistoryFromBackend,
} from "@/lib/adapters";

// ─── Context shape ───────────────────────────────────────────────────

export type ApiMode = "mock" | "live" | "degraded";

const THREAD_KEY = "pdca.chat.thread_id";

interface RunContextValue {
  run: RunSession;
  setRun: React.Dispatch<React.SetStateAction<RunSession>>;
  mode: ApiMode;
  scannerOnline: boolean | null;
  chatbotOnline: boolean | null;
  activeRunId: string | null;
  activeThreadId: string | null;
  threads: BackendThreadSummary[];
  threadsLoading: boolean;
  refreshScannerHealth: () => Promise<void>;
  refreshEnvironment: () => Promise<void>;
  refreshThreads: () => Promise<void>;
  // Legacy scanner-only path (still used as fallback when chatbot offline):
  submitGroupScan: (group: string) => Promise<{ jobId: string } | { error: string }>;
  submitChecksScan: (checkIds: string) => Promise<{ jobId: string } | { error: string }>;
  approveTask: (taskId: string) => void;
  rejectTask: (taskId: string) => void;
  skipTask: (taskId: string) => void;
  appendMessage: (msg: ChatMessage) => void;
  upsertMessage: (msg: ChatMessage) => void;
  clearMessages: () => void;
  resetConversation: () => void;
  createConversation: () => Promise<void>;
  activateThread: (threadId: string) => void;
  loadThread: (threadId: string) => Promise<void>;
  deleteThread: (threadId: string) => Promise<void>;
  cancelActiveRun: () => Promise<void>;
  // Chatbot API helpers (Sprint 2+):
  listHistory: () => Promise<RunHistoryRow[]>;
  createRun: (prompt: string, scope?: string) => Promise<{ runId: string } | { error: string }>;
  loadRun: (runId: string) => Promise<void>;
}

const RunContext = createContext<RunContextValue | null>(null);

// ─── Provider ────────────────────────────────────────────────────────

const newId = (p: string) => `${p}-${Math.random().toString(36).slice(2, 8)}`;

export function RunProvider({ children }: { children: React.ReactNode }) {
  const [run, setRun] = useState<RunSession>(emptyRun);
  const [scannerOnline, setScannerOnline] = useState<boolean | null>(null);
  const [chatbotOnline, setChatbotOnline] = useState<boolean | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(() => {
    try { return localStorage.getItem(THREAD_KEY); } catch { return null; }
  });
  const [threads, setThreads] = useState<BackendThreadSummary[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const pollers = useRef<Map<string, number>>(new Map());
  const runPoller = useRef<number | null>(null);

  const stopRunPolling = () => {
    if (runPoller.current !== null) {
      window.clearInterval(runPoller.current);
      runPoller.current = null;
    }
  };

  const refreshScannerHealth = useCallback(async () => {
    const r = await scannerApi.ping();
    setScannerOnline(r.ok);
  }, []);

  const refreshEnvironment = useCallback(async () => {
    const ping = await chatbotApi.ping();
    setChatbotOnline(ping.ok);
    if (!ping.ok) return;
    try {
      const env = await chatbotApi.getEnvironment();
      setRun((r) => ({ ...r, awsEnvironment: environmentFromBackend(env) }));
    } catch {
      // leave the existing (mock) environment in place
    }
  }, []);

  const refreshThreads = useCallback(async () => {
    if (!chatbotApi.isConfigured()) return;
    setThreadsLoading(true);
    try {
      const list = await chatbotApi.listThreads(80, 0);
      setThreads(list.items);
    } catch {
      // Sidebar can stay usable even if history fetch fails.
    } finally {
      setThreadsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshScannerHealth();
    void refreshEnvironment();
    void refreshThreads();

    // Auto-retry probes every 3s until both services are confirmed online.
    // Stops once both are up so it doesn't poll forever.
    const retryId = window.setInterval(() => {
      if (chatbotOnline && scannerOnline) {
        window.clearInterval(retryId);
        return;
      }
      if (!chatbotOnline) void refreshEnvironment();
      if (!scannerOnline) void refreshScannerHealth();
    }, 3_000);

    return () => {
      window.clearInterval(retryId);
      pollers.current.forEach((id) => window.clearInterval(id));
      pollers.current.clear();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshScannerHealth, refreshEnvironment, refreshThreads]);

  const mode: ApiMode =
    scannerOnline === null ? "mock" :
    scannerOnline          ? "live" : "degraded";

  // ─── Scan job polling ────────────────────────────────────────────

  const upsertScanJob = (job: ScanJob) => {
    setRun((r) => {
      const existing = r.scanJobs.findIndex((j) => j.id === job.id);
      const scanJobs = existing >= 0
        ? r.scanJobs.map((j, i) => (i === existing ? job : j))
        : [...r.scanJobs, job];
      return { ...r, scanJobs };
    });
  };

  const startPolling = (jobId: string) => {
    if (pollers.current.has(jobId)) return;
    const tick = async () => {
      try {
        const job = await scannerApi.getJob(jobId);
        const scanJob = jobToScanJob(job);
        upsertScanJob(scanJob);

        if (job.status === "completed") {
          const findings = findingsFromJob(job);
          setRun((r) => {
            const existingIds = new Set(r.findings.map((f) => f.id));
            const merged = [...r.findings, ...findings.filter((f) => !existingIds.has(f.id))];
            return { ...r, findings: merged, status: "completed", currentNode: "scan_collect" };
          });
          stopPolling(jobId);
        } else if (job.status === "cancelled") {
          setRun((r) => ({ ...r, status: "cancelled" }));
          stopPolling(jobId);
        } else if (job.status === "failed" || job.status === "timeout") {
          setRun((r) => ({ ...r, status: "failed" }));
          stopPolling(jobId);
        }
      } catch {
        // Soft-fail; the next tick may recover.
      }
    };
    void tick();
    const handle = window.setInterval(tick, 4_000);
    pollers.current.set(jobId, handle);
  };

  const stopPolling = (jobId: string) => {
    const h = pollers.current.get(jobId);
    if (h !== undefined) {
      window.clearInterval(h);
      pollers.current.delete(jobId);
    }
  };

  // ─── Actions ─────────────────────────────────────────────────────

  const submitGroupScan: RunContextValue["submitGroupScan"] = async (group) => {
    try {
      const res = await scannerApi.submitGroup(group);
      const placeholder: ScanJob = {
        id: res.job_id,
        apiEndpoint: "POST /v1/scan/group",
        httpMethod: "POST",
        taskType: "group",
        taskValue: group,
        status: "pending",
        submittedAt: new Date().toISOString(),
      };
      upsertScanJob(placeholder);
      setRun((r) => ({ ...r, status: "submitting_scan", currentNode: "scan_submit" }));
      startPolling(res.job_id);
      return { jobId: res.job_id };
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : (e as Error).message;
      return { error: msg };
    }
  };

  const submitChecksScan: RunContextValue["submitChecksScan"] = async (checkIds) => {
    try {
      const res = await scannerApi.submitChecks(checkIds);
      const placeholder: ScanJob = {
        id: res.job_id,
        apiEndpoint: "POST /v1/scan/checks",
        httpMethod: "POST",
        taskType: "checks",
        taskValue: checkIds,
        status: "pending",
        submittedAt: new Date().toISOString(),
      };
      upsertScanJob(placeholder);
      setRun((r) => ({ ...r, status: "submitting_scan", currentNode: "scan_submit" }));
      startPolling(res.job_id);
      return { jobId: res.job_id };
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : (e as Error).message;
      return { error: msg };
    }
  };

  const decideTask = (decision: "approved" | "rejected" | "skipped") => async (taskId: string) => {
    // Optimistic UI update
    setRun((r) => ({
      ...r,
      remediationTasks: r.remediationTasks.map((t) =>
        t.id === taskId ? { ...t, decision } : t,
      ),
    }));
    if (activeRunId && chatbotApi.isConfigured()) {
      try {
        await chatbotApi.approve(activeRunId, taskId, decision);
        // Trigger an immediate refetch so executionLogs/verifications appear
        // promptly after backend transitions out of waiting_for_approval.
        void fetchRunSnapshot(activeRunId);
      } catch {
        // soft-fail; UI already shows optimistic state
      }
    }
  };
  const approveTask = useCallback(decideTask("approved"), [activeRunId]);
  const rejectTask  = useCallback(decideTask("rejected"), [activeRunId]);
  const skipTask    = useCallback(decideTask("skipped"), [activeRunId]);

  const cancelActiveRun = useCallback(async () => {
    const pendingJobs = run.scanJobs.filter((j) =>
      j.status === "pending" || j.status === "running",
    );
    if (!activeRunId && pendingJobs.length === 0) return;

    try {
      if (activeRunId && chatbotApi.isConfigured()) {
        await chatbotApi.cancelRun(activeRunId);
        stopRunPolling();
        void fetchRunSnapshot(activeRunId);
      } else {
        await Promise.allSettled(pendingJobs.map((j) => scannerApi.cancelJob(j.id)));
      }
    } finally {
      pendingJobs.forEach((j) => stopPolling(j.id));
      setRun((r) => ({
        ...r,
        status: "cancelled",
        scanJobs: r.scanJobs.map((j) =>
          pendingJobs.some((p) => p.id === j.id)
            ? { ...j, status: "cancelled", finishedAt: new Date().toISOString() }
            : j,
        ),
      }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeRunId, run.scanJobs]);

  const appendMessage = useCallback((msg: ChatMessage) => {
    setRun((r) => ({ ...r, messages: [...r.messages, msg] }));
  }, []);

  // Upsert: replace existing message with same id, or append if not found.
  const upsertMessage = useCallback((msg: ChatMessage) => {
    setRun((r) => {
      const idx = r.messages.findIndex((m) => m.id === msg.id);
      if (idx === -1) return { ...r, messages: [...r.messages, msg] };
      const msgs = [...r.messages];
      msgs[idx] = msg;
      return { ...r, messages: msgs };
    });
  }, []);

  const clearMessages = useCallback(() => {
    setRun((r) => ({ ...r, messages: [] }));
  }, []);

  const listHistory = useCallback(async (): Promise<RunHistoryRow[]> => {
    if (!chatbotApi.isConfigured()) return [];
    try {
      const list = await chatbotApi.listRuns(50, 0);
      return list.items.map(runHistoryFromBackend);
    } catch {
      return [];
    }
  }, []);

  const resetConversation = useCallback(() => {
    stopRunPolling();
    pollers.current.forEach((id) => window.clearInterval(id));
    pollers.current.clear();
    setActiveRunId(null);
    setActiveThreadId(null);
    try { localStorage.removeItem(THREAD_KEY); } catch { /* ignore */ }
    setRun((prev) => ({
      ...emptyRun,
      startedAt: new Date().toISOString(),
      lastCheckpointAt: new Date().toISOString(),
      awsEnvironment: prev.awsEnvironment,
      graphNodes: [],
      scanJobs: [],
      toolCalls: [],
      evidence: [],
      findings: [],
      remediationTasks: [],
      executionLogs: [],
      verifications: [],
      messages: [],
      ragBundle: undefined,
      report: {
        ...emptyRun.report,
        runId: "",
        sections: [],
      },
    }));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const activateThread = useCallback((threadId: string) => {
    setActiveThreadId(threadId);
    try { localStorage.setItem(THREAD_KEY, threadId); } catch { /* ignore */ }
  }, []);

  const createConversation = useCallback(async () => {
    stopRunPolling();
    pollers.current.forEach((id) => window.clearInterval(id));
    pollers.current.clear();
    setActiveRunId(null);

    const resetRun = (prev: RunSession): RunSession => ({
      ...emptyRun,
      startedAt: new Date().toISOString(),
      lastCheckpointAt: new Date().toISOString(),
      awsEnvironment: prev.awsEnvironment,
      graphNodes: [],
      scanJobs: [],
      toolCalls: [],
      evidence: [],
      findings: [],
      remediationTasks: [],
      executionLogs: [],
      verifications: [],
      messages: [],
      ragBundle: undefined,
      report: {
        ...emptyRun.report,
        runId: "",
        sections: [],
      },
    });

    if (!chatbotApi.isConfigured()) {
      setActiveThreadId(null);
      try { localStorage.removeItem(THREAD_KEY); } catch { /* ignore */ }
      setRun(resetRun);
      return;
    }

    try {
      const thread = await chatbotApi.createThread("New chat");
      setActiveThreadId(thread.thread_id);
      try { localStorage.setItem(THREAD_KEY, thread.thread_id); } catch { /* ignore */ }
      setThreads((items) => [thread, ...items.filter((t) => t.thread_id !== thread.thread_id)]);
      setRun(resetRun);
    } catch {
      setActiveThreadId(null);
      try { localStorage.removeItem(THREAD_KEY); } catch { /* ignore */ }
      setRun(resetRun);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchRunSnapshot = async (runId: string) => {
    try {
      const snap = (await chatbotApi.getRun(runId)) as Partial<RunSession>;
      // Merge — preserve existing client-only fields (e.g. checkpointer).
      setRun((prev) => ({
        ...prev,
        ...snap,
        // Some FE components expect arrays even when backend omits.
        graphNodes:        snap.graphNodes        ?? prev.graphNodes        ?? [],
        scanJobs:          snap.scanJobs          ?? prev.scanJobs          ?? [],
        toolCalls:         snap.toolCalls         ?? prev.toolCalls         ?? [],
        evidence:          snap.evidence          ?? prev.evidence          ?? [],
        findings:          snap.findings          ?? prev.findings          ?? [],
        remediationTasks:  snap.remediationTasks  ?? prev.remediationTasks  ?? [],
        executionLogs:     snap.executionLogs     ?? prev.executionLogs     ?? [],
        verifications:     snap.verifications     ?? prev.verifications     ?? [],
        // Keep FE chat messages — backend messages shape differs.
        messages:          prev.messages,
        report:            snap.report            ?? prev.report,
        ragBundle:         snap.ragBundle         ?? prev.ragBundle,
        awsEnvironment:    (snap.awsEnvironment && Object.keys(snap.awsEnvironment).length > 0)
                              ? snap.awsEnvironment
                              : prev.awsEnvironment,
      } as RunSession));
      // Stop polling once the run is terminal.
      if (snap.status === "completed" || snap.status === "failed" || snap.status === "cancelled") {
        stopRunPolling();
      }
    } catch {
      // soft-fail; next tick will retry
    }
  };

  const startRunPolling = (runId: string) => {
    stopRunPolling();
    setActiveRunId(runId);
    void fetchRunSnapshot(runId);
    runPoller.current = window.setInterval(() => void fetchRunSnapshot(runId), 3_000);
  };

  const loadRun = useCallback(async (runId: string) => {
    startRunPolling(runId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadThread = useCallback(async (threadId: string) => {
    if (!chatbotApi.isConfigured()) return;
    try {
      const res = await chatbotApi.getThreadMessages(threadId);
      const messages = threadMessagesToChatMessages(res.messages);
      const lastRunId = findLastRunId(res.messages);
      stopRunPolling();
      pollers.current.forEach((id) => window.clearInterval(id));
      pollers.current.clear();
      setActiveThreadId(threadId);
      setActiveRunId(lastRunId);
      try { localStorage.setItem(THREAD_KEY, threadId); } catch { /* ignore */ }
      setRun((prev) => ({
        ...emptyRun,
        startedAt: new Date().toISOString(),
        lastCheckpointAt: new Date().toISOString(),
        awsEnvironment: prev.awsEnvironment,
        messages,
      }));
      if (lastRunId) startRunPolling(lastRunId);
    } catch {
      await refreshThreads();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshThreads]);

  const deleteThread = useCallback(async (threadId: string) => {
    await chatbotApi.deleteThread(threadId);
    if (threadId === activeThreadId) resetConversation();
    await refreshThreads();
  }, [activeThreadId, refreshThreads, resetConversation]);

  const createRun: RunContextValue["createRun"] = async (prompt, scope) => {
    if (!chatbotApi.isConfigured()) {
      return { error: "Chatbot API not configured" };
    }
    try {
      const res = await chatbotApi.createRun(prompt, scope);
      startRunPolling(res.run_id);
      return { runId: res.run_id };
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : (e as Error).message;
      return { error: msg };
    }
  };

  const value = useMemo<RunContextValue>(
    () => ({
      run, setRun, mode,
      scannerOnline, chatbotOnline, activeRunId, activeThreadId, threads, threadsLoading,
      refreshScannerHealth, refreshEnvironment, refreshThreads,
      submitGroupScan, submitChecksScan,
      approveTask, rejectTask, skipTask, appendMessage, upsertMessage, clearMessages, resetConversation,
      createConversation, activateThread, loadThread, deleteThread,
      cancelActiveRun,
      listHistory, createRun, loadRun,
    }),
    // setRun/submit*/startPolling are stable via closures over refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [run, mode, scannerOnline, chatbotOnline, activeRunId, activeThreadId, threads, threadsLoading],
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used inside <RunProvider>");
  return ctx;
}

export { newId };
