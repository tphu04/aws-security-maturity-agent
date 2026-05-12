import type { AwsEnvironment, LogLine, RunSession, EventLine, QaLine } from "./types";
import type { BackendThreadSummary } from "./api";

export type ConnStatus = "checking" | "connected" | "offline";

export interface UiState {
  lines: LogLine[];
  input: string;
  inputHistory: string[];
  historyIdx: number;       // -1 = current input, else index from end
  threadId: string | null;  // null = new chat (not yet persisted)
  threads: BackendThreadSummary[];
  threadsLoading: boolean;
  runId: string | null;
  runStatus: RunSession["status"] | null;
  env: AwsEnvironment | null;
  conn: ConnStatus;
  busy: boolean;            // a chat stream is in flight
  loadingThread: boolean;
  showSettings: boolean;
  sidebarOpen: boolean;
}

export const initialState: UiState = {
  lines: [],
  input: "",
  inputHistory: [],
  historyIdx: -1,
  threadId: null,
  threads: [],
  threadsLoading: false,
  runId: null,
  runStatus: null,
  env: null,
  conn: "checking",
  busy: false,
  loadingThread: false,
  showSettings: false,
  sidebarOpen: true,
};

export type Action =
  | { t: "setInput"; v: string }
  | { t: "submit"; text: string }
  | { t: "addLine"; line: LogLine }
  | { t: "addLines"; lines: LogLine[] }
  | { t: "patchEvent"; id: string; patch: Partial<EventLine> }
  | { t: "appendQa"; id: string; delta: string }
  | { t: "finishQa"; id: string; sources?: QaLine["sources"]; intent?: QaLine["intent"] }
  | { t: "resolveApproval"; taskId: string; decision: "approved" | "rejected" | "skipped" }
  | { t: "setEnv"; env: AwsEnvironment | null }
  | { t: "setConn"; v: ConnStatus }
  | { t: "setThread"; threadId: string | null }
  | { t: "setRun"; runId: string | null; status?: RunSession["status"] | null }
  | { t: "setRunStatus"; status: RunSession["status"] | null }
  | { t: "setBusy"; v: boolean }
  | { t: "toggleSettings" }
  | { t: "toggleSidebar" }
  | { t: "clear" }
  | { t: "setThreads"; threads: BackendThreadSummary[] }
  | { t: "setThreadsLoading"; v: boolean }
  | { t: "setLoadingThread"; v: boolean }
  | { t: "loadConversation"; threadId: string | null; lines: LogLine[]; runId: string | null }
  | { t: "newChat" }
  | { t: "historyPrev" }
  | { t: "historyNext" };

export function reducer(s: UiState, a: Action): UiState {
  switch (a.t) {
    case "setInput": return { ...s, input: a.v, historyIdx: -1 };
    case "submit": {
      const trimmed = a.text.trim();
      if (!trimmed) return s;
      const hist = [...s.inputHistory, trimmed].slice(-50);
      return { ...s, input: "", inputHistory: hist, historyIdx: -1 };
    }
    case "addLine":  return { ...s, lines: [...s.lines, a.line] };
    case "addLines": return a.lines.length === 0 ? s : { ...s, lines: [...s.lines, ...a.lines] };
    case "patchEvent": {
      const next = s.lines.map(l => l.id === a.id && l.k === "event" ? { ...l, ...a.patch } as EventLine : l);
      return { ...s, lines: next };
    }
    case "appendQa": {
      const next = s.lines.map(l => l.id === a.id && l.k === "qa"
        ? ({ ...l, markdown: l.markdown + a.delta } as QaLine)
        : l);
      return { ...s, lines: next };
    }
    case "finishQa": {
      const next = s.lines.map(l => l.id === a.id && l.k === "qa"
        ? ({ ...l, done: true, sources: a.sources ?? l.sources, intent: a.intent ?? l.intent } as QaLine)
        : l);
      return { ...s, lines: next };
    }
    case "resolveApproval": {
      const next = s.lines.map(l =>
        l.k === "approval" && l.task?.id === a.taskId && !l.resolved
          ? { ...l, resolved: a.decision }
          : l);
      return { ...s, lines: next };
    }
    case "setEnv":  return { ...s, env: a.env };
    case "setConn": return { ...s, conn: a.v };
    case "setThread": return { ...s, threadId: a.threadId };
    case "setRun":  return { ...s, runId: a.runId, runStatus: a.status ?? s.runStatus };
    case "setRunStatus": return { ...s, runStatus: a.status };
    case "setBusy": return { ...s, busy: a.v };
    case "toggleSettings": return { ...s, showSettings: !s.showSettings };
    case "toggleSidebar":  return { ...s, sidebarOpen: !s.sidebarOpen };
    case "clear":   return { ...s, lines: [] };
    case "setThreads":        return { ...s, threads: a.threads };
    case "setThreadsLoading": return { ...s, threadsLoading: a.v };
    case "setLoadingThread":  return { ...s, loadingThread: a.v };
    case "loadConversation":
      return { ...s, threadId: a.threadId, lines: a.lines, runId: a.runId, runStatus: null, loadingThread: false };
    case "newChat":
      return { ...s, threadId: null, lines: [], runId: null, runStatus: null, input: "", historyIdx: -1 };
    case "historyPrev": {
      if (s.inputHistory.length === 0) return s;
      const idx = Math.min(s.historyIdx + 1, s.inputHistory.length - 1);
      return { ...s, historyIdx: idx, input: s.inputHistory[s.inputHistory.length - 1 - idx] ?? "" };
    }
    case "historyNext": {
      if (s.historyIdx <= 0) return { ...s, historyIdx: -1, input: "" };
      const idx = s.historyIdx - 1;
      return { ...s, historyIdx: idx, input: s.inputHistory[s.inputHistory.length - 1 - idx] ?? "" };
    }
  }
}

export function nid(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
