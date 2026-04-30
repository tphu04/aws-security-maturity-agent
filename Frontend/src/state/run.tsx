import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import type { ChatMessage, RunHistoryRow, RunSession, ScanJob } from "@/types/pdca";
import { mockRun } from "@/data/mockRun";
import { chatbotApi, scannerApi, ApiError } from "@/lib/api";
import {
  environmentFromBackend,
  findingsFromJob,
  jobToScanJob,
  runHistoryFromBackend,
} from "@/lib/adapters";

// ─── Context shape ───────────────────────────────────────────────────

export type ApiMode = "mock" | "live" | "degraded";

interface RunContextValue {
  run: RunSession;
  setRun: React.Dispatch<React.SetStateAction<RunSession>>;
  mode: ApiMode;
  scannerOnline: boolean | null;
  chatbotOnline: boolean | null;
  activeRunId: string | null;
  refreshScannerHealth: () => Promise<void>;
  refreshEnvironment: () => Promise<void>;
  // Legacy scanner-only path (still used as fallback when chatbot offline):
  submitGroupScan: (group: string) => Promise<{ jobId: string } | { error: string }>;
  submitChecksScan: (checkIds: string) => Promise<{ jobId: string } | { error: string }>;
  approveTask: (taskId: string) => void;
  rejectTask: (taskId: string) => void;
  appendMessage: (msg: ChatMessage) => void;
  // Chatbot API helpers (Sprint 2+):
  listHistory: () => Promise<RunHistoryRow[]>;
  createRun: (prompt: string, scope?: string) => Promise<{ runId: string } | { error: string }>;
  loadRun: (runId: string) => Promise<void>;
}

const RunContext = createContext<RunContextValue | null>(null);

// ─── Provider ────────────────────────────────────────────────────────

const newId = (p: string) => `${p}-${Math.random().toString(36).slice(2, 8)}`;

export function RunProvider({ children }: { children: React.ReactNode }) {
  const [run, setRun] = useState<RunSession>(mockRun);
  const [scannerOnline, setScannerOnline] = useState<boolean | null>(null);
  const [chatbotOnline, setChatbotOnline] = useState<boolean | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const pollers = useRef<Map<string, number>>(new Map());
  const runPoller = useRef<number | null>(null);

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

  useEffect(() => {
    void refreshScannerHealth();
    void refreshEnvironment();
    return () => {
      pollers.current.forEach((id) => window.clearInterval(id));
      pollers.current.clear();
    };
  }, [refreshScannerHealth, refreshEnvironment]);

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
        } else if (job.status === "failed") {
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

  const decideTask = (decision: "approved" | "rejected") => async (taskId: string) => {
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

  const appendMessage = useCallback((msg: ChatMessage) => {
    setRun((r) => ({ ...r, messages: [...r.messages, msg] }));
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

  const stopRunPolling = () => {
    if (runPoller.current !== null) {
      window.clearInterval(runPoller.current);
      runPoller.current = null;
    }
  };

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
        messages:          snap.messages          ?? prev.messages          ?? [],
        report:            snap.report            ?? prev.report,
        awsEnvironment:    (snap.awsEnvironment && Object.keys(snap.awsEnvironment).length > 0)
                              ? snap.awsEnvironment
                              : prev.awsEnvironment,
      } as RunSession));
      // Stop polling once the run is terminal.
      if (snap.status === "completed" || snap.status === "failed") {
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
      scannerOnline, chatbotOnline, activeRunId,
      refreshScannerHealth, refreshEnvironment,
      submitGroupScan, submitChecksScan,
      approveTask, rejectTask, appendMessage,
      listHistory, createRun, loadRun,
    }),
    // setRun/submit*/startPolling are stable via closures over refs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [run, mode, scannerOnline, chatbotOnline, activeRunId],
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used inside <RunProvider>");
  return ctx;
}

export { newId };
