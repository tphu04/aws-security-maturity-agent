// Projects a RunSession snapshot into LogLine[] additions.
//
// Strategy: keep a per-run "fingerprint" of what we've already emitted, then
// only emit *new* lines on each poll. The fingerprint is derived from stable
// IDs (jobId, taskId, log timestamps). The polling line is special: only one
// per scan job, updated in place via its stable id.

import type { LogLine, RunSession, EventLine, ApprovalLine, ExecLine } from "../types";

const POLL_DONE_STATUSES = new Set(["completed", "failed"]);

// Labels for the in-place status line (silent nodes that don't emit own lines).
const NODE_LABEL: Record<string, string> = {
  operational_planning: "đang lên kế hoạch khắc phục…",
  review_task:          "chờ phê duyệt…",
  reset_index:          "chuẩn bị thực thi…",
  execution:            "đang thực thi remediation…",
  verification:         "đang xác minh kết quả…",
  generating_report:    "đang tạo báo cáo…",
};

// Phase transition markers — appear ONCE, AFTER approval cards, so user can
// follow progress even when scrolled down. These are keyed by run.status so
// they emit when the run first enters each phase.
const PHASE_HEADER: Partial<Record<string, string>> = {
  executing_remediation: "▶ Bắt đầu thực thi remediation",
  verifying:             "▶ Bắt đầu xác minh kết quả",
  generating_report:     "▶ Đang tạo báo cáo…",
};

export interface ProjectionState {
  emitted: Set<string>;
  pollLineByJob: Map<string, string>;
  statusLineId: string | null;   // in-place "current node" indicator
}

export function newProjectionState(): ProjectionState {
  return { emitted: new Set(), pollLineByJob: new Map(), statusLineId: null };
}

interface ProjectionResult {
  add: LogLine[];
  update: Array<{ id: string; patch: Partial<EventLine> }>;
  resolveApprovals: Array<{ taskId: string; decision: "approved" | "rejected" | "skipped" }>;
}

export function projectRun(run: RunSession, st: ProjectionState): ProjectionResult {
  const add: LogLine[] = [];
  const update: ProjectionResult["update"] = [];
  const resolveApprovals: ProjectionResult["resolveApprovals"] = [];

  const push = (key: string, mk: () => LogLine) => {
    if (st.emitted.has(key)) return;
    st.emitted.add(key);
    add.push(mk());
  };

  const now = () => Date.now();
  const nid = () => `${now()}-${Math.random().toString(36).slice(2, 10)}`;

  // 1. environment
  if (run.awsEnvironment?.accountMask) {
    const env = run.awsEnvironment;
    push(`env:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▸",
      text: `environment ok (account ${env.accountMask}, region ${env.region})`,
      tone: "default",
    }));
  }

  // 2. planning — derive from graphNodes
  const graphNodes = run.graphNodes ?? [];
  const planningNode = graphNodes.find(n => n.name === "planning" && n.status === "completed");
  if (planningNode) {
    // Prefer real output from BE; "ready" is last-resort fallback.
    const planText = planningNode.outputSummary?.trim() || planningNode.inputSummary?.trim() || "ready";
    push(`plan:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▸",
      text: `planning · ${planText}`,
      reasoning: planningNode.outputSummary !== planText ? planningNode.outputSummary : undefined,
      tone: "default",
    }));
  }

  // 3. scan jobs: submit + polling (in-place) + finish
  for (const job of (run.scanJobs ?? [])) {
    push(`submit:${job.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▸",
      text: `scan_submit · ${job.id} (${job.taskType}=${job.taskValue})`,
      tone: "default",
    }));

    const total = job.totalChecks ?? 0;
    const done = job.completedChecks ?? 0;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;

    if (job.status === "running" || (job.status === "pending" && total > 0)) {
      const existingId = st.pollLineByJob.get(job.id);
      if (!existingId) {
        const id = nid();
        st.pollLineByJob.set(job.id, id);
        add.push({
          id, ts: now(), k: "event", icon: "▸",
          text: `polling`, progress: { done, total },
          tone: "info",
        } as EventLine);
      } else {
        update.push({ id: existingId, patch: { progress: { done, total }, text: "polling" } });
      }
    }

    if (job.status === "completed") {
      const pollId = st.pollLineByJob.get(job.id);
      if (pollId) {
        update.push({
          id: pollId,
          patch: { text: `polling complete (${done}/${total || done})`, progress: { done: total || done, total: total || done }, tone: "ok", icon: "✓" },
        });
      }
      // resultCount is often null on the job object; fall back to completedChecks.
      const resultCount = job.resultCount ?? job.completedChecks ?? 0;
      push(`done:${job.id}`, () => ({
        id: nid(), ts: now(), k: "event", icon: "✓",
        text: `scan completed · ${resultCount} checks`,
        tone: "ok",
      }));
    } else if (job.status === "failed" || job.status === "timeout") {
      push(`fail:${job.id}`, () => ({
        id: nid(), ts: now(), k: "event", icon: "✗",
        text: `scan ${job.status} · ${job.id}`, tone: "err",
      }));
    }
  }

  // 4. findings collected — once per run when findings appear
  const findings = run.findings ?? [];
  if (findings.length > 0) {
    const failed = findings.filter(f => f.status === "FAIL").length;
    const manual = findings.filter(f => f.status === "MANUAL").length;
    push(`collected:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▸",
      text: `collected: ${findings.length} findings (${failed} fail${manual ? `, ${manual} manual` : ""})`,
      tone: "default",
    }));
  }

  // 5. risk evaluation — fingerprint when risk_evaluation node done
  const riskNode = graphNodes.find(n => n.name === "risk_evaluation" && n.status === "completed");
  if (riskNode) {
    // Use BE's own summary if available (reflects LLM scoring).
    // Fall back to FE-side count only when outputSummary is absent.
    const sev = countSeverity(run);
    const riskSummary = riskNode.outputSummary?.trim()
      ? riskNode.outputSummary.trim()
      : `high=${sev.high} medium=${sev.medium} low=${sev.low}`;
    push(`risk:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▸",
      text: `risk: ${riskSummary}`,
      reasoning: riskNode.outputSummary ? undefined : `FE-computed từ ${run.findings?.length ?? 0} findings (BE không trả outputSummary)`,
      tone: "warn",
    }));
  }

  // 6. approvals — emit the current pending task.
  //    Check both run.status and currentNode because the BE adapter may set
  //    currentNode="review_task" before status is fully synced to
  //    "waiting_for_approval".
  // Use only run.status for approval gating — currentNode may lag behind when
  // BE processes remaining tasks in bulk after the first acknowledge.
  const isWaiting = run.status === "waiting_for_approval";
  const tasks = run.remediationTasks ?? [];
  if (isWaiting) {
    // Show tasks one at a time (HITL processes per current_task_index).
    // NEEDS_ACTION: treat null/undefined/pending/manual_required as pending.
    // Skip tasks whose approval card was already emitted — the BE may not
    // update decision in remediationTasks immediately, so we use st.emitted
    // as the authoritative "already shown" tracker.
    const NEEDS_ACTION = new Set([undefined, null, "", "pending", "manual_required"]);
    const pending = tasks.find(t =>
      NEEDS_ACTION.has(t.decision as string | undefined | null) &&
      !st.emitted.has(`approval:${t.id}`)
    );
    if (pending) {
      push(`approval:${pending.id}`, () => ({
        id: nid(), ts: now(), k: "approval", task: pending,
      } as ApprovalLine));
    }
  }

  // Also: if any approval line was emitted earlier for a task that is now
  // resolved, mark it so the caller can resolve the card.
  for (const task of tasks) {
    const RESOLVED = ["approved", "rejected", "skipped"] as const;
    if (RESOLVED.includes(task.decision as typeof RESOLVED[number])) {
      const key = `resolved:${task.id}:${task.decision}`;
      if (!st.emitted.has(key) && st.emitted.has(`approval:${task.id}`)) {
        st.emitted.add(key);
        resolveApprovals.push({ taskId: task.id, decision: task.decision as typeof RESOLVED[number] });
      }
    }
  }

  // 6b. Phase transition markers — visible milestones AFTER approval cards.
  const phaseLabel = PHASE_HEADER[run.status as string];
  if (phaseLabel) {
    push(`phase:${run.status}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▶",
      text: phaseLabel,
      tone: "info",
    }));
  }

  // 7. execution logs — clean BE's raw JSON message dump
  for (const log of (run.executionLogs ?? [])) {
    const key = `exec:${log.taskId}:${log.timestamp}`;
    let displayMessage = log.message || "";
    if (displayMessage.trim().startsWith("{")) {
      try {
        const parsed = JSON.parse(displayMessage);
        displayMessage = parsed.message || parsed.error || "";
      } catch { /* keep original */ }
    }
    const statusLabel =
      log.status === "success"         ? "đã thực thi" :
      log.status === "manual_required" ? "cần xử lý thủ công" :
      log.status === "failed"          ? "thực thi thất bại" :
      log.status;
    push(key, () => ({
      id: nid(), ts: now(), k: "exec",
      text: `${statusLabel} · ${log.toolName}${displayMessage ? ` — ${displayMessage}` : ""}`,
      ok: log.status === "success",
    } as ExecLine));
  }

  // 8. verifications
  //   - PASS findings: aggregate into one summary line (avoid N identical lines)
  //   - Manual/failed: show individually with resource for distinction
  const verifications = run.verifications ?? [];
  const passList    = verifications.filter(v => v.result === "passed");
  const manualList  = verifications.filter(v => v.result === "manual_required" || v.result === "partial");
  const failedList  = verifications.filter(v => v.result === "failed");

  // Aggregate PASS — single line, updates in place via fingerprint on count.
  if (passList.length > 0) {
    const passKey = `verify-pass-summary:${passList.length}`;
    push(passKey, () => ({
      id: nid(), ts: now(), k: "event", icon: "✓",
      text: `Đã xác minh ${passList.length} finding (PASS)`,
      tone: "ok",
    }));
  }

  // Manual — dedupe by toolName+resource to avoid same row twice
  const manualSeen = new Set<string>();
  for (const v of manualList) {
    const dedupeKey = `${v.toolName}:${v.resource}`;
    if (manualSeen.has(dedupeKey)) continue;
    manualSeen.add(dedupeKey);
    push(`verify:${v.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "▸",
      text: `Chờ xử lý thủ công · ${v.toolName || "—"}${v.resource ? ` · ${v.resource}` : ""}`,
      tone: "info",
    }));
  }

  // Failed — show with resource
  const failedSeen = new Set<string>();
  for (const v of failedList) {
    const dedupeKey = `${v.toolName}:${v.resource}`;
    if (failedSeen.has(dedupeKey)) continue;
    failedSeen.add(dedupeKey);
    push(`verify:${v.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "✗",
      text: `Xác minh thất bại · ${v.toolName || "—"}${v.resource ? ` · ${v.resource}` : ""}`,
      tone: "err",
    }));
  }

  // 9. report
  if (run.report?.status === "ready") {
    push(`report:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "✓",
      text: `Báo cáo sẵn sàng: ${run.report.filename} — gõ "report" để tải`,
      tone: "ok",
    }));
  }

  // 10. terminal
  if (run.status === "completed") {
    const durMs = Number(run.durationMs);
    const durStr = Number.isFinite(durMs) && durMs > 0
      ? ` (${Math.round(durMs / 1000)}s)`
      : "";
    push(`completed:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "✓",
      text: `Hoàn tất pipeline${durStr}`,
      tone: "ok",
    }));
  } else if (run.status === "failed") {
    push(`failed:${run.id}`, () => ({
      id: nid(), ts: now(), k: "event", icon: "✗",
      text: `Pipeline thất bại`, tone: "err",
    }));
  }

  // 11. In-place "current node" status indicator for silent states.
  //     Stored in ProjectionState so it persists across polls without
  //     needing a separate ref in App.tsx (which was causing duplicates).
  const label = NODE_LABEL[run.currentNode] ?? NODE_LABEL[run.status as string];
  if (label && !POLL_DONE_STATUSES.has(run.status)) {
    if (!st.statusLineId) {
      const id = nid();
      st.statusLineId = id;
      add.push({ id, ts: now(), k: "event", icon: "▸", text: label, tone: "info" } as EventLine);
    } else {
      update.push({ id: st.statusLineId, patch: { text: label } });
    }
  } else if (st.statusLineId && POLL_DONE_STATUSES.has(run.status)) {
    const ok = run.status === "completed";
    update.push({ id: st.statusLineId, patch: { text: ok ? "hoàn tất." : "thất bại.", tone: ok ? "ok" : "err", icon: ok ? "✓" : "✗" } });
    st.statusLineId = null;
  } else if (st.statusLineId && !label) {
    // Node has its own visible line — remove the transient indicator.
    update.push({ id: st.statusLineId, patch: { text: "" } });
    st.statusLineId = null;
  }

  return { add, update, resolveApprovals };
}

function countSeverity(run: RunSession) {
  const c = { high: 0, medium: 0, low: 0 };
  for (const f of (run.findings ?? [])) {
    if (f.status !== "FAIL") continue;
    if (f.severity === "critical" || f.severity === "high") c.high++;
    else if (f.severity === "medium") c.medium++;
    else c.low++;
  }
  return c;
}
