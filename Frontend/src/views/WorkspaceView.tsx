import { useCallback, useEffect, useRef, useState } from "react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ChatInput } from "@/components/chat/ChatInput";
import { ToolTracePanel } from "@/components/evidence/ToolTracePanel";
import { TopBar } from "@/components/layout/TopBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { AppShell } from "@/components/layout/AppShell";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useRouter } from "@/state/router";
import { useRun, newId } from "@/state/run";
import type { RunSession, SuggestionChip, AssistantCard, QASource, IntentMeta, IntentKind } from "@/types/pdca";
import { mockClassify, mockAnswerQA, mockSuggestChips } from "@/data/mockQA";
import { chatbotApi, type BackendChatMessage, type BackendSuggestion } from "@/lib/api";
import { useSelection } from "@/state/selection";
import type { PromptChip } from "@/components/chat/ChatInput";

interface Props {
  // Kept in signature for back-compat with callers; we now read from context.
  run: RunSession;
  setRun: React.Dispatch<React.SetStateAction<RunSession>>;
}

// Phase 0: classifier lives in FE (mock). Phase 1 moves to backend /v1/chat.
const KNOWN_GROUPS = ["s3", "iam", "ec2", "rds", "kms", "ecr", "vpc", "cloudtrail", "guardduty"];

function pickService(text: string): string | undefined {
  const lower = text.toLowerCase();
  return KNOWN_GROUPS.find((g) => new RegExp(`\\b${g}\\b`).test(lower));
}

function suggestionToPromptChip(s: BackendSuggestion): PromptChip {
  return { label: s.label, kind: s.kind, payload: s.payload };
}

// Map a single backend ChatMessage → one or more AssistantCards.
function backendMessageToCards(m: BackendChatMessage): AssistantCard[] {
  const p = m.payload || {};
  switch (m.type) {
    case "qa_answer": {
      const intentMeta = p.intentMeta as { classified?: IntentKind; confidence?: number; reason?: string } | undefined;
      return [{
        kind: "qa_answer",
        markdown: String(p.markdown ?? ""),
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
      return [{ kind: "text", text: String(p.text ?? "(empty message)") }];
  }
}

const THREAD_KEY = "pdca.chat.thread_id";

export function WorkspaceView(_: Props) {
  const {
    run, setRun, appendMessage, upsertMessage, submitGroupScan, createRun, loadRun,
    mode, chatbotOnline, approveTask, rejectTask,
  } = useRun();
  const [pending, setPending] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<PromptChip[]>([]);
  // Track which pipeline stages have already been announced in chat so we
  // don't duplicate cards across polling ticks.
  const announcedRef = useRef<Set<string>>(new Set());
  const threadIdRef = useRef<string | undefined>(typeof window !== "undefined" ? localStorage.getItem(THREAD_KEY) || undefined : undefined);
  const [hydrated, setHydrated] = useState(false);
  const { go } = useRouter();
  const { selectEvidence } = useSelection();

  // Reset dynamic state when chat is cleared (e.g. New chat button).
  // Sidebar already removed the localStorage entry; sync the ref.
  useEffect(() => {
    if (run.messages.length === 0) {
      setSuggestions([]);
      try {
        const stored = localStorage.getItem(THREAD_KEY) || undefined;
        if (stored !== threadIdRef.current) threadIdRef.current = stored;
      } catch { /* ignore */ }
    }
  }, [run.messages.length]);

  // If LandingView stashed an initial prompt (quick-start chip click), fire it.
  useEffect(() => {
    let pending = "";
    try { pending = sessionStorage.getItem("pdca.initial_prompt") || ""; } catch { /* ignore */ }
    if (!pending) return;
    try { sessionStorage.removeItem("pdca.initial_prompt"); } catch { /* ignore */ }
    // Defer so router transition completes first.
    setTimeout(() => { void handleSend(pending); }, 50);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // On first mount (when backend online), hydrate from persisted thread.
  useEffect(() => {
    if (hydrated) return;
    if (!chatbotOnline) { setHydrated(true); return; }
    const tid = threadIdRef.current;
    if (!tid) { setHydrated(true); return; }
    (async () => {
      try {
        const res = await chatbotApi.getThreadMessages(tid);
        for (const m of res.messages) {
          if (m.role === "user") {
            appendMessage({ id: `srv-${m.id}`, role: "user", timestamp: new Date(m.created_at * 1000).toISOString(), text: m.content });
          } else {
            const cards = backendMessageToCards({ type: m.message_type === "user_text" ? "text" : m.message_type, payload: m.payload });
            appendMessage({ id: `srv-${m.id}`, role: "assistant", timestamp: new Date(m.created_at * 1000).toISOString(), cards });
          }
        }
      } catch (e) {
        // Thread missing on server (db reset?) → drop it.
        if (e instanceof Error && /404/.test(e.message)) {
          localStorage.removeItem(THREAD_KEY);
          threadIdRef.current = undefined;
        }
      } finally {
        setHydrated(true);
      }
    })();
  }, [chatbotOnline, hydrated, appendMessage]);

  const sendAssistant = (cards: AssistantCard[]) => {
    appendMessage({
      id: newId("m"), role: "assistant",
      timestamp: new Date().toISOString(),
      cards,
    });
  };

  const runScanFlow = async (text: string, service: string) => {
    if (chatbotOnline) {
      const res = await createRun(text, `${service} scan`);
      if ("runId" in res) {
        sendAssistant([{ kind: "text", text: `Run **${res.runId}** started. The agent will scan ${service}, evaluate risk, propose remediation, and pause for your approval.` }]);
      } else {
        sendAssistant([{ kind: "text", text: `Run start failed: ${res.error}` }]);
      }
      return;
    }
    const result = await submitGroupScan(service);
    if ("jobId" in result) {
      sendAssistant([
        { kind: "scan_submitted", api: "POST /v1/scan/group", group: service,
          jobId: result.jobId, status: "pending", nextNode: "scan_poll" },
        { kind: "text", text: `Chatbot offline — used scanner directly. job ${result.jobId}. Findings will appear when done.` },
      ]);
    } else {
      sendAssistant([{ kind: "text", text: `Scan submit failed: ${result.error}` }]);
    }
  };

  const dispatchMock = async (text: string) => {
    const intent = mockClassify(text);

    if (intent.classified === "scan") {
      const svc = pickService(text);
      if (!svc) {
        sendAssistant([{ kind: "text", text: `Tôi hiểu bạn muốn quét, nhưng chưa rõ service. Thử: "scan s3", "scan iam", "audit ec2". (mode=${mode})` }]);
        return;
      }
      await runScanFlow(text, svc);
      return;
    }

    if (intent.classified === "qa") {
      sendAssistant([mockAnswerQA(text, intent)]);
      return;
    }

    sendAssistant([mockAnswerQA(text, intent), mockSuggestChips(text)]);
  };

  const dispatchBackend = async (text: string) =>
    new Promise<void>((resolve) => {
      const streamingId = newId("m");
      let createdStreaming = false;
      let buffer = "";
      let sources: QASource[] = [];
      let finalReplaced = false;
      let intentMeta: IntentMeta | undefined;

      const ensureStreamingCard = () => {
        if (createdStreaming) return;
        createdStreaming = true;
        appendMessage({
          id: streamingId,
          role: "assistant",
          timestamp: new Date().toISOString(),
          cards: [{ kind: "qa_answer", markdown: "", sources: [], intentMeta }],
        });
      };

      const patchStreaming = (markdown: string, srcs: QASource[]) => {
        ensureStreamingCard();
        setRun((r) => ({
          ...r,
          messages: r.messages.map((m) => m.id === streamingId
            ? { ...m, cards: [{ kind: "qa_answer", markdown, sources: srcs, intentMeta }] }
            : m),
        }));
      };

      chatbotApi.chatStream(text, (ev) => {
        switch (ev.type) {
          case "meta":
            if (ev.data.thread_id && ev.data.thread_id !== threadIdRef.current) {
              threadIdRef.current = ev.data.thread_id;
              try { localStorage.setItem(THREAD_KEY, ev.data.thread_id); } catch { /* ignore */ }
            }
            const i = ev.data.intent;
            intentMeta = { classified: i.intent, confidence: i.confidence, reason: i.reason };
            break;
          case "sources":
            sources = (ev.data as unknown as QASource[]) || [];
            patchStreaming(buffer, sources);
            break;
          case "delta":
            buffer += ev.data.text || "";
            patchStreaming(buffer, sources);
            break;
          case "messages": {
            finalReplaced = true;
            const cards = ev.data.flatMap(backendMessageToCards);
            if (createdStreaming) {
              setRun((r) => ({
                ...r,
                messages: r.messages.map((m) => m.id === streamingId ? { ...m, cards } : m),
              }));
            } else {
              sendAssistant(cards);
            }
            // Kick off run polling when backend started a scan.
            const runStartMsg = ev.data.find((m) => m.type === "run_started");
            if (runStartMsg?.payload?.run_id) {
              void loadRun(String(runStartMsg.payload.run_id));
            }
            break;
          }
          case "suggestions":
            setSuggestions((ev.data || []).map(suggestionToPromptChip));
            break;
          case "error":
            if (!finalReplaced) {
              sendAssistant([{ kind: "text", text: `Stream error: ${ev.data.message}` }]);
            }
            break;
          case "done":
            resolve();
            break;
        }
      }, {
        threadId: threadIdRef.current,
        runId: run.id?.startsWith("R-") ? run.id : undefined,
      });
    });

  const handleSend = async (text: string) => {
    appendMessage({ id: newId("m"), role: "user", timestamp: new Date().toISOString(), text });
    setPending(true);
    try {
      if (chatbotOnline) {
        await dispatchBackend(text);
      } else {
        await dispatchMock(text);
      }
    } finally {
      setPending(false);
    }
  };

  const handleChip = (chip: SuggestionChip) => {
    // Treat chip click as the user sending the chip's payload.
    void handleSend(chip.payload);
  };

  // Synthesize pipeline stage cards into chat as the run progresses.
  // Rules:
  //  - Each stage card is announced once (tracked in announcedRef).
  //  - Polling card is a standalone message with stable id so it can be
  //    upserted (progress bar updated) without creating duplicates.
  //  - Each new non-polling stage gets its own message so cards appear
  //    incrementally in the chat thread.
  const injectStageCards = useCallback((r: RunSession) => {
    if (!r.id) return;
    const announced = announcedRef.current;
    const key = (s: string) => `${r.id}:${s}`;
    const node = (name: string) => r.graphNodes.find((n) => n.name === name);

    const emit = (cards: AssistantCard[]) => {
      if (!cards.length) return;
      appendMessage({ id: newId("stage"), role: "assistant", timestamp: new Date().toISOString(), cards });
    };

    // ── environment_check ──────────────────────────────────────────
    if (node("environment")?.status === "completed" && !announced.has(key("env"))) {
      announced.add(key("env"));
      emit([{
        kind: "environment_check",
        awsCredentials: r.awsEnvironment.credentialType,
        account: r.awsEnvironment.accountMask,
        region: r.awsEnvironment.region,
        bucketsDiscovered: r.awsEnvironment.bucketsDiscovered,
        ragAvailable: r.awsEnvironment.ragAvailable,
        runId: r.id,
      }]);
    }

    // ── planning ───────────────────────────────────────────────────
    if (node("planning")?.status === "completed" && !announced.has(key("plan"))) {
      announced.add(key("plan"));
      const groups = r.scanJobs.map((j) => j.taskValue).filter(Boolean);
      emit([{
        kind: "planning",
        scanner: "Prowler",
        provider: "AWS",
        scope: r.id,
        groups: groups.length ? groups : ["s3"],
        specificChecks: "—",
        expectedOutput: "findings",
        nextNode: "scan_submit",
      }]);
    }

    // ── scan_submitted ─────────────────────────────────────────────
    if (node("scan_submit")?.status === "completed" && !announced.has(key("submit")) && r.scanJobs.length) {
      announced.add(key("submit"));
      const job = r.scanJobs[0];
      emit([{ kind: "scan_submitted", api: job.apiEndpoint, group: job.taskValue, jobId: job.id, status: job.status, nextNode: "scan_poll" }]);
    }

    // ── polling (standalone upsertable message) ────────────────────
    const pollNode = node("scan_poll");
    if (pollNode && (pollNode.status === "running" || pollNode.status === "completed") && r.scanJobs.length) {
      const job = r.scanJobs[0];
      const pollMsg = {
        id: key("poll_msg"),  // stable id for upsert
        role: "assistant" as const,
        timestamp: new Date().toISOString(),
        cards: [{
          kind: "polling" as const,
          jobId: job.id,
          pollCount: pollNode.pollIterations?.length ?? 0,
          status: (pollNode.status === "completed" ? "completed" : "running") as "running" | "completed" | "pending",
          progressDone:  job.completedChecks ?? 0,
          progressTotal: job.totalChecks ?? 1,
          pendingJobs:   r.scanJobs.filter((j) => j.status === "pending"   || j.status === "running").length,
          completedJobs: r.scanJobs.filter((j) => j.status === "completed").length,
        }],
      };
      if (!announced.has(key("poll_msg"))) {
        announced.add(key("poll_msg"));
        appendMessage(pollMsg);        // first time → append
      } else {
        upsertMessage(pollMsg);        // subsequent ticks → patch in-place
      }
    }

    // ── findings_collected ─────────────────────────────────────────
    if (node("scan_collect")?.status === "completed" && !announced.has(key("collect")) && r.findings.length) {
      announced.add(key("collect"));
      emit([{
        kind: "findings_collected",
        rawFindings: r.findings.length,
        failed: r.findings.filter((f) => f.status === "FAIL").length,
        passed: r.findings.filter((f) => f.status === "PASS").length,
        manual: r.findings.filter((f) => f.status === "MANUAL").length,
        node: "scan_collect",
        snapshot: new Date().toLocaleTimeString(),
      }]);
    }

    // ── risk_evaluation ────────────────────────────────────────────
    if (node("risk_evaluation")?.status === "completed" && !announced.has(key("risk"))) {
      announced.add(key("risk"));
      const fail = (s: string) => r.findings.filter((f) => f.severity === s && f.status === "FAIL").length;
      emit([{
        kind: "risk_evaluation",
        high: fail("high") + fail("critical"),
        medium: fail("medium"),
        low: fail("low"),
        manualReview: r.findings.filter((f) => f.status === "MANUAL").length,
        prioritized: r.remediationTasks.length,
      }]);
    }

    // ── remediation_offer (one per pending task) ───────────────────
    for (const task of r.remediationTasks) {
      const offerKey = key(`offer:${task.id}`);
      if (!announced.has(offerKey) && task.decision === "pending") {
        announced.add(offerKey);
        emit([{ kind: "remediation_offer", taskId: task.id }]);
      }
    }

    // ── remediation_execution (after decision made) ────────────────
    for (const task of r.remediationTasks) {
      const execKey = key(`exec:${task.id}`);
      if (!announced.has(execKey) && task.decision !== "pending") {
        announced.add(execKey);
        const log = r.executionLogs.find((l) => l.taskId === task.id);
        emit([{
          kind: "remediation_execution",
          taskId: task.id,
          toolName: task.toolName,
          decision: task.decision,
          status: log ? (log.status === "success" ? "success" : log.status === "failed" || log.status === "error" ? "failed" : "running") : "running",
          guardChecks: task.guardChecks,
        }]);
      }
    }

    // ── verification (one per result) ──────────────────────────────
    for (const v of r.verifications) {
      const vKey = key(`verify:${v.id}`);
      if (!announced.has(vKey)) {
        announced.add(vKey);
        emit([{
          kind: "verification",
          findingId: v.findingId,
          beforeState: v.beforeState,
          afterState: v.afterState,
          verificationStatus: v.result,
        }]);
      }
    }

    // ── report_ready ───────────────────────────────────────────────
    if (r.report?.status === "ready" && !announced.has(key("report"))) {
      announced.add(key("report"));
      emit([{ kind: "report_ready", filename: r.report.filename, includes: r.report.sections.map((s) => s.title) }]);
    }
  }, [appendMessage, upsertMessage]);

  // Watch run changes triggered by polling and inject stage cards.
  useEffect(() => {
    if (run.id) injectStageCards(run);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.graphNodes, run.findings, run.remediationTasks, run.scanJobs]);

  // Reset announced set when starting a new chat / new run.
  useEffect(() => {
    if (run.messages.length === 0) announcedRef.current = new Set();
  }, [run.messages.length]);

  // QA source click → locate corresponding evidence/finding in the right panel.
  const handleSourceClick = (checkId?: string) => {
    if (!checkId) return;
    const ev = run.evidence.find(
      (e) => (e.kind === "finding" || e.kind === "verification") &&
             "prowlerCheckId" in e && e.prowlerCheckId === checkId,
    );
    const finding = run.findings.find((f) => f.prowlerCheckId === checkId);
    if (ev) {
      selectEvidence(ev.id, { findingId: finding?.id });
      setTraceOpen(true);
    } else if (finding) {
      selectEvidence(undefined, { findingId: finding.id });
      setTraceOpen(true);
    }
  };

  return (
    <AppShell
      sidebar={<Sidebar awsStatus={run.awsEnvironment.status} awsAccountMask={run.awsEnvironment.accountMask} />}
      topBar={<TopBar run={run} onOpenTrace={() => setTraceOpen((v) => !v)} traceOpen={traceOpen} />}
      inputBar={<ChatInput onSend={handleSend} pending={pending} suggestions={suggestions} />}
    >
      <div className="relative flex h-full min-h-0">
        {/* Main chat */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <ChatWindow
            messages={run.messages}
            findings={run.findings}
            tasks={run.remediationTasks}
            onApproveTask={(id) => {
              const task = run.remediationTasks.find((t) => t.id === id);
              appendMessage({ id: newId("m"), role: "user", timestamp: new Date().toISOString(),
                text: `✅ Approved: ${task?.findingTitle ?? id}` });
              approveTask(id);
            }}
            onRejectTask={(id) => {
              const task = run.remediationTasks.find((t) => t.id === id);
              appendMessage({ id: newId("m"), role: "user", timestamp: new Date().toISOString(),
                text: `❌ Rejected: ${task?.findingTitle ?? id}` });
              rejectTask(id);
            }}
            onShowTask={() => go("approvals")}
            onPreviewReport={() => go("report")}
            onSuggestionChip={handleChip}
            onSourceClick={handleSourceClick}
          />
        </div>

        {/* Trace panel — slide-in from right, overlay on mobile, side-by-side on xl */}
        {traceOpen && (
          <aside className="
            absolute inset-y-0 right-0 z-20 flex w-full flex-col
            border-l border-border/60 bg-bg-surface/95 backdrop-blur-md
            shadow-2xl transition-all
            sm:w-[400px]
            xl:relative xl:shadow-none xl:w-[380px]
          ">
            <ToolTracePanel run={run} />
          </aside>
        )}

        {/* Backdrop on mobile when trace open */}
        {traceOpen && (
          <div
            className="absolute inset-0 z-10 bg-black/40 xl:hidden"
            onClick={() => setTraceOpen(false)}
          />
        )}
      </div>
    </AppShell>
  );
}
