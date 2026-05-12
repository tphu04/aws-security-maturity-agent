import React, { useEffect, useReducer, useRef } from "react";
import { api, type ChatStreamEvent, type BackendChatMessage } from "./api";
import { initialState, reducer, nid } from "./reducer";
import { newProjectionState, projectRun, type ProjectionState } from "./projectors/runToLines";
import { threadMessagesToLines, findLastRunId } from "./projectors/threadToLines";
import type { LogLine, QaLine, UserLine, EventLine, ExecLine } from "./types";

import { Sidebar } from "./components/Sidebar";
import { Header } from "./components/Header";
import { Composer } from "./components/Composer";
import { Settings } from "./components/Settings";
import { EmptyState } from "./components/EmptyState";
import { UserMessage, AssistantMessage } from "./components/MessageBubble";
import { ActivityCard } from "./components/ActivityCard";
import { ApprovalCard } from "./components/ApprovalCard";

const POLL_FAST_MS = 3000;
const POLL_SLOW_MS = 8000;
const POLL_DONE    = new Set(["completed", "failed"]);


export default function App() {
  const [s, dispatch] = useReducer(reducer, initialState);
  const [atBottom, setAtBottom] = React.useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickyRef = useRef(true);
  const projectionRef = useRef<ProjectionState>(newProjectionState());
  const abortRef = useRef<AbortController | null>(null);
  // Refs so polling loop reads current values without restarting on status change.
  const runIdRef       = useRef<string | null>(null);
  const runStatusRef   = useRef<string | null>(null);
  const forceTickRef   = useRef<(() => void) | null>(null); // trigger an immediate poll

  // ───── boot: ping + env + threads ─────
  useEffect(() => {
    let alive = true;
    (async () => {
      const ping = await api.ping();
      if (!alive) return;
      dispatch({ t: "setConn", v: ping.ok ? "connected" : "offline" });
      if (!ping.ok) return;

      try {
        const env = await api.getEnvironment();
        if (alive) dispatch({ t: "setEnv", env });
      } catch { /* non-fatal */ }

      try {
        dispatch({ t: "setThreadsLoading", v: true });
        const list = await api.listThreads(50);
        if (alive) dispatch({ t: "setThreads", threads: list.items });
      } catch { /* non-fatal */ }
      finally {
        if (alive) dispatch({ t: "setThreadsLoading", v: false });
      }
    })();
    return () => { alive = false; };
  }, []);

  // ───── auto-scroll: only for outgoing user messages (not for agent events) ─────
  const lastUserLineCount = useRef(0);
  useEffect(() => {
    const userCount = s.lines.filter(l => l.k === "user").length;
    if (userCount > lastUserLineCount.current) {
      // User just sent a message — scroll to bottom so they see the reply.
      lastUserLineCount.current = userCount;
      const el = scrollRef.current;
      if (el) el.scrollTop = el.scrollHeight;
      stickyRef.current = true;
      setAtBottom(true);
    }
  }, [s.lines]);

  function onScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const isBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 60;
    stickyRef.current = isBottom;
    setAtBottom(isBottom);
  }

  function scrollToBottom() {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    stickyRef.current = true;
    setAtBottom(true);
  }

  // ───── polling loop — keyed only on runId so it never restarts mid-run ─────
  useEffect(() => {
    if (!s.runId) return;
    runIdRef.current = s.runId;
    runStatusRef.current = s.runStatus;

    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      if (cancelled) return;
      const rid = runIdRef.current;
      if (!rid) return;
      try {
        const run = await api.getRun(rid);
        if (cancelled) return;

        // Project new log lines (findings, events, approvals…).
        const proj = projectRun(run, projectionRef.current);
        if (proj.add.length) dispatch({ t: "addLines", lines: proj.add });
        for (const u of proj.update) dispatch({ t: "patchEvent", id: u.id, patch: u.patch });
        for (const r of proj.resolveApprovals) dispatch({ t: "resolveApproval", taskId: r.taskId, decision: r.decision });

        // Sync status into state without restarting the loop.
        if (run.status !== runStatusRef.current) {
          runStatusRef.current = run.status;
          dispatch({ t: "setRunStatus", status: run.status });
        }

        if (!POLL_DONE.has(run.status)) {
          // Use fast interval unless actively waiting for user approval.
          const delay = run.status === "waiting_for_approval" ? POLL_SLOW_MS : POLL_FAST_MS;
          timer = window.setTimeout(tick, delay);
        }
      } catch (e) {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : String(e);
        const isAbort = (e instanceof Error && e.name === "AbortError") || msg.toLowerCase().includes("abort");
        if (!isAbort) {
          dispatch({ t: "addLine", line: errLine(`poll failed: ${msg}`) });
        }
        timer = window.setTimeout(tick, POLL_SLOW_MS);
      }
    };

    // Expose a way to trigger an immediate poll (e.g. right after an approval).
    forceTickRef.current = () => {
      if (timer) clearTimeout(timer);
      timer = window.setTimeout(tick, 200);
    };

    timer = window.setTimeout(tick, 300);
    return () => {
      cancelled = true;
      forceTickRef.current = null;
      if (timer) clearTimeout(timer);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.runId]); // intentionally only keyed on runId

  // ───── submit ─────
  function submit(forced?: string) {
    const text = (forced ?? s.input).trim();
    if (!text || s.busy) return;

    if (text === "clear") { dispatch({ t: "clear" }); dispatch({ t: "submit", text }); return; }
    if (text === "report" && s.runId) {
      window.open(api.reportUrl(s.runId), "_blank");
      dispatch({ t: "submit", text });
      return;
    }

    dispatch({ t: "addLine", line: userLine(text) });
    dispatch({ t: "submit", text });

    const qaId = nid();
    dispatch({ t: "addLine", line: { id: qaId, ts: Date.now(), k: "qa", markdown: "", done: false } as QaLine });
    dispatch({ t: "setBusy", v: true });

    abortRef.current?.abort();
    abortRef.current = api.chatStream(text, (ev) => handleStreamEvent(ev, qaId), {
      threadId: s.threadId ?? undefined,
      runId: s.runId ?? undefined,
    });
  }

  function handleStreamEvent(ev: ChatStreamEvent, qaId: string) {
    switch (ev.type) {
      case "meta": {
        if (ev.data.thread_id && !s.threadId) dispatch({ t: "setThread", threadId: ev.data.thread_id });
        if (ev.data.run_id) {
          if (ev.data.run_id !== runIdRef.current) {
            projectionRef.current = newProjectionState();
            runIdRef.current = ev.data.run_id;
            runStatusRef.current = null;
            dispatch({ t: "setRun", runId: ev.data.run_id, status: null });
          }
        }
        dispatch({ t: "finishQa", id: qaId, intent: { ...ev.data.intent } });
        break;
      }
      case "delta":
        if (ev.data.text) dispatch({ t: "appendQa", id: qaId, delta: ev.data.text });
        break;
      case "sources":
        dispatch({ t: "finishQa", id: qaId, sources: ev.data as unknown as QaLine["sources"] });
        break;
      case "messages":
        for (const m of ev.data) absorbMessage(m, qaId);
        break;
      case "done":
        dispatch({ t: "finishQa", id: qaId });
        dispatch({ t: "setBusy", v: false });
        // Refresh threads list once a response completes — title may have updated.
        api.listThreads(50).then(list => dispatch({ t: "setThreads", threads: list.items })).catch(() => {});
        break;
      case "error":
        dispatch({ t: "addLine", line: errLine(`stream error: ${ev.data.message}`) });
        dispatch({ t: "finishQa", id: qaId });
        dispatch({ t: "setBusy", v: false });
        break;
    }
  }

  function absorbMessage(m: BackendChatMessage, qaId: string) {
    switch (m.type) {
      case "qa_answer": {
        const md = (m.payload?.markdown as string) ?? (m.payload?.text as string) ?? "";
        dispatch({ t: "appendQa", id: qaId, delta: md });
        const sources = (m.payload?.sources as QaLine["sources"]) ?? undefined;
        if (sources) dispatch({ t: "finishQa", id: qaId, sources });
        break;
      }
      case "text": {
        const txt = (m.payload?.text as string) ?? "";
        if (txt) dispatch({ t: "appendQa", id: qaId, delta: txt });
        break;
      }
      case "run_started": {
        const rid = (m.payload?.run_id as string) ?? null;
        if (rid && rid !== runIdRef.current) {
          projectionRef.current = newProjectionState();
          runIdRef.current = rid;
          runStatusRef.current = null;
          dispatch({ t: "setRun", runId: rid, status: null });
          dispatch({ t: "appendQa", id: qaId, delta: `\n\nĐang khởi tạo scan run \`${rid}\` …` });
        }
        break;
      }
      case "suggest_action": {
        const prompt = (m.payload?.prompt as string) ?? "Gợi ý:";
        const chips = (m.payload?.chips as Array<{ label: string; payload: string }>) ?? [];
        const md = `\n\n${prompt}\n` + chips.map(c => `- \`${c.payload}\` — ${c.label}`).join("\n");
        dispatch({ t: "appendQa", id: qaId, delta: md });
        break;
      }
      case "error":
        dispatch({ t: "addLine", line: errLine((m.payload?.message as string) ?? "unknown error") });
        break;
    }
  }

  // ───── threads ─────
  async function pickThread(id: string) {
    if (id === s.threadId) return;
    abortRef.current?.abort();
    dispatch({ t: "setLoadingThread", v: true });
    try {
      const res = await api.getThreadMessages(id);
      const lines = threadMessagesToLines(res.messages);
      const lastRun = findLastRunId(res.messages);
      projectionRef.current = newProjectionState();
      runIdRef.current = lastRun;
      runStatusRef.current = null;
      dispatch({ t: "loadConversation", threadId: id, lines, runId: lastRun });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      dispatch({ t: "addLine", line: errLine(`load thread failed: ${msg}`) });
    } finally {
      dispatch({ t: "setLoadingThread", v: false });
    }
  }

  function newChat() {
    abortRef.current?.abort();
    projectionRef.current = newProjectionState();
    runIdRef.current = null;
    runStatusRef.current = null;
    dispatch({ t: "newChat" });
  }

  async function deleteThread(id: string): Promise<void> {
    try {
      await api.deleteThread(id);
      if (id === s.threadId) newChat();
      const list = await api.listThreads(50);
      dispatch({ t: "setThreads", threads: list.items });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      dispatch({ t: "addLine", line: errLine(`delete failed: ${msg}`) });
    }
  }

  // ───── approvals ─────
  async function decide(taskId: string, decision: "approved" | "rejected" | "skipped") {
    if (!s.runId) return;

    // Optimistic resolve — card unlocks immediately.
    dispatch({ t: "resolveApproval", taskId, decision });
    projectionRef.current.emitted.add(`resolved:${taskId}:${decision}`);

    // Count total approval tasks shown vs resolved in this run.
    const emitted = projectionRef.current.emitted;
    const totalShown   = [...emitted].filter(k => k.startsWith("approval:")).length;
    const totalResolved = [...emitted].filter(k => k.startsWith("resolved:")).length;
    const allDone = totalResolved >= totalShown && totalShown > 0;
    const transitionKey = "transition:all-resolved";

    if (allDone && !emitted.has(transitionKey)) {
      emitted.add(transitionKey);
      dispatch({
        t: "addLine",
        line: {
          id: nid(), ts: Date.now(), k: "event", icon: "▸",
          text: `Đã xem xét ${totalShown} task — đang tiến hành thực thi…`,
          tone: "info",
        } as import("./types").EventLine,
      });
      // Scroll to show the transition line if user is within ~400px of bottom.
      const el = scrollRef.current;
      if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 400) {
        setTimeout(() => { el.scrollTop = el.scrollHeight; }, 80);
      }
    }

    try {
      await api.approve(s.runId, taskId, decision);
    } catch (e) {
      const status = (e as { status?: number }).status;
      const msg = e instanceof Error ? e.message : String(e);
      if (status !== 409 && status !== 404) {
        dispatch({ t: "addLine", line: errLine(`approve failed: ${msg}`) });
      }
    }

    // Trigger immediate poll to surface execution/verification events.
    forceTickRef.current?.();
  }

  function pendingApprovalId(): string | null {
    for (let i = s.lines.length - 1; i >= 0; i--) {
      const l = s.lines[i];
      if (l.k === "approval" && l.task?.id && !l.resolved) return l.task.id;
    }
    return null;
  }

  function onShortcut(k: "a" | "r" | "d" | "s") {
    const id = pendingApprovalId();
    if (!id) return;
    if (k === "a") decide(id, "approved");
    else if (k === "r") decide(id, "rejected");
    else if (k === "s") decide(id, "skipped");
    else if (k === "d") {
      const block = document.querySelector(`[data-approval="${id}"]`);
      if (!block) return;
      const det = block.querySelectorAll("details");
      if (det.length > 0) {
        const last = det[det.length - 1] as HTMLDetailsElement;
        last.open = !last.open;
      }
    }
  }

  // ───── render ─────
  const groups = groupLines(s.lines);
  const showEmpty = !s.loadingThread && s.lines.length === 0;

  return (
    <div className="h-full flex bg-bg text-fg">
      {s.sidebarOpen && (
        <Sidebar
          threads={s.threads}
          activeThreadId={s.threadId}
          loading={s.threadsLoading}
          onNew={newChat}
          onPick={pickThread}
          onOpenSettings={() => dispatch({ t: "toggleSettings" })}
          onClose={() => dispatch({ t: "toggleSidebar" })}
          onDelete={deleteThread}
        />
      )}

      <main className="flex-1 flex flex-col min-w-0">
        <Header
          env={s.env}
          conn={s.conn}
          sidebarOpen={s.sidebarOpen}
          onToggleSidebar={() => dispatch({ t: "toggleSidebar" })}
        />

        <div className="relative flex-1 flex flex-col min-h-0">
          <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl px-4 py-4">
              {s.loadingThread && <div className="text-dim text-sm py-8 text-center">đang tải hội thoại…</div>}

              {showEmpty && <EmptyState onPick={(p) => submit(p)} />}

              {groups.map((g, i) => {
              if (g.kind === "user")     return <UserMessage      key={g.items[0].id} line={g.items[0] as UserLine} />;
              if (g.kind === "qa")       return <AssistantMessage key={g.items[0].id} line={g.items[0] as QaLine} />;
              if (g.kind === "approval") {
                const l = g.items[0];
                if (l.k !== "approval") return null;
                return <ApprovalCard key={l.id} line={l} onDecide={decide} />;
              }
              if (g.kind === "activity") {
                return <ActivityCard key={`act-${i}-${g.items[0].id}`} lines={g.items as (EventLine | ExecLine)[]} />;
              }
              if (g.kind === "error") {
                return (
                  <div key={`err-${i}`} className="mx-auto my-2 max-w-3xl text-sm text-err bg-errSoft border border-err/30 rounded-lg px-3 py-2">
                    {g.items.map(it => "text" in it ? it.text : "").join(" · ")}
                  </div>
                );
              }
              return null;
            })}
            </div>
          </div>

          {/* Scroll-to-bottom button — visible when user has scrolled up */}
          {!atBottom && (
            <button
              onClick={scrollToBottom}
              className="absolute bottom-4 right-6 w-9 h-9 rounded-full bg-panel border border-border shadow-card text-dim hover:text-fg hover:border-borderStrong flex items-center justify-center text-base"
              title="Cuộn xuống"
            >↓</button>
          )}
        </div>

        <Composer
          value={s.input}
          busy={s.busy}
          pendingApproval={pendingApprovalId() !== null}
          onChange={(v) => dispatch({ t: "setInput", v })}
          onSubmit={() => submit()}
          onHistoryPrev={() => dispatch({ t: "historyPrev" })}
          onHistoryNext={() => dispatch({ t: "historyNext" })}
          onShortcut={onShortcut}
        />
      </main>

      {s.showSettings && <Settings onClose={() => dispatch({ t: "toggleSettings" })} />}
    </div>
  );
}

// ───── grouping ─────

type Group =
  | { kind: "user"; items: LogLine[] }
  | { kind: "qa"; items: LogLine[] }
  | { kind: "approval"; items: LogLine[] }
  | { kind: "activity"; items: LogLine[] }
  | { kind: "error"; items: LogLine[] };

function groupLines(lines: LogLine[]): Group[] {
  const out: Group[] = [];
  for (const l of lines) {
    if (l.k === "event" || l.k === "exec") {
      const last = out[out.length - 1];
      if (last && last.kind === "activity") last.items.push(l);
      else out.push({ kind: "activity", items: [l] });
    } else if (l.k === "user") {
      out.push({ kind: "user", items: [l] });
    } else if (l.k === "qa") {
      out.push({ kind: "qa", items: [l] });
    } else if (l.k === "approval") {
      out.push({ kind: "approval", items: [l] });
    } else if (l.k === "error") {
      const last = out[out.length - 1];
      if (last && last.kind === "error") last.items.push(l);
      else out.push({ kind: "error", items: [l] });
    }
  }
  return out;
}

// ───── helpers ─────

function userLine(text: string): UserLine {
  return { id: nid(), ts: Date.now(), k: "user", text };
}

function errLine(text: string): LogLine {
  return { id: nid(), ts: Date.now(), k: "error", text };
}
