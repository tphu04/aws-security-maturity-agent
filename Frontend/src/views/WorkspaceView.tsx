import { useState } from "react";
import type { ChatMessage } from "@/types/pdca";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ChatInput } from "@/components/chat/ChatInput";
import { ToolTracePanel } from "@/components/evidence/ToolTracePanel";
import { TopBar } from "@/components/layout/TopBar";
import { Sidebar } from "@/components/layout/Sidebar";
import { AppShell } from "@/components/layout/AppShell";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { useRouter } from "@/state/router";
import { useRun, newId } from "@/state/run";
import type { RunSession } from "@/types/pdca";

interface Props {
  // Kept in signature for back-compat with callers; we now read from context.
  run: RunSession;
  setRun: React.Dispatch<React.SetStateAction<RunSession>>;
}

// Crude intent parser: pick first AWS service token mentioned. Good enough
// for Sprint 1 — proper NLU comes from the chatbot orchestrator.
const KNOWN_GROUPS = ["s3", "iam", "ec2", "rds", "kms", "ecr", "vpc", "cloudtrail", "guardduty"];

function parseScanIntent(text: string): { group?: string } {
  const lower = text.toLowerCase();
  if (!/scan|check|audit|kiểm tra|quét/.test(lower)) return {};
  for (const g of KNOWN_GROUPS) {
    if (new RegExp(`\\b${g}\\b`).test(lower)) return { group: g };
  }
  return {};
}

export function WorkspaceView(_: Props) {
  const {
    run, appendMessage, submitGroupScan, createRun,
    mode, chatbotOnline, approveTask, rejectTask,
  } = useRun();
  const [pending, setPending] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const { go } = useRouter();

  const handleSend = async (text: string) => {
    const now = new Date();
    appendMessage({ id: newId("m"), role: "user", timestamp: now.toISOString(), text });

    const intent = parseScanIntent(text);
    setPending(true);

    if (!intent.group) {
      appendMessage({
        id: newId("m"), role: "assistant",
        timestamp: new Date().toISOString(),
        cards: [{ kind: "text", text: `I can run AWS Prowler scans. Try: "scan s3", "scan iam", "audit ec2". (mode=${mode})` }],
      });
      setPending(false);
      return;
    }

    // Preferred path: full PDCA orchestrator via chatbot API.
    if (chatbotOnline) {
      const res = await createRun(text, `${intent.group} scan`);
      if ("runId" in res) {
        appendMessage({
          id: newId("m"), role: "assistant",
          timestamp: new Date().toISOString(),
          cards: [
            { kind: "text", text: `Run **${res.runId}** started. The agent will scan ${intent.group}, evaluate risk, propose remediation, and pause for your approval.` },
          ],
        });
      } else {
        appendMessage({
          id: newId("m"), role: "assistant",
          timestamp: new Date().toISOString(),
          cards: [{ kind: "text", text: `Run start failed: ${res.error}` }],
        });
      }
      setPending(false);
      return;
    }

    // Fallback: scanner-only path.
    const result = await submitGroupScan(intent.group);
    appendMessage("jobId" in result
      ? {
          id: newId("m"), role: "assistant",
          timestamp: new Date().toISOString(),
          cards: [
            { kind: "scan_submitted", api: "POST /v1/scan/group", group: intent.group,
              jobId: result.jobId, status: "pending", nextNode: "scan_poll" },
            { kind: "text", text: `Chatbot offline — used scanner directly. job ${result.jobId}. Findings will appear when done.` },
          ],
        }
      : {
          id: newId("m"), role: "assistant",
          timestamp: new Date().toISOString(),
          cards: [{ kind: "text", text: `Scan submit failed: ${result.error}` }],
        });
    setPending(false);
  };

  return (
    <AppShell
      sidebar={<Sidebar awsStatus={run.awsEnvironment.status} awsAccountMask={run.awsEnvironment.accountMask} />}
      topBar={<TopBar run={run} onOpenTrace={() => setTraceOpen(true)} />}
      rightPanel={<ToolTracePanel run={run} />}
      inputBar={<ChatInput onSend={handleSend} pending={pending} />}
    >
      <ChatWindow
        messages={run.messages}
        findings={run.findings}
        tasks={run.remediationTasks}
        onApproveTask={approveTask}
        onRejectTask={rejectTask}
        onShowTask={() => go("approvals")}
        onPreviewReport={() => go("report")}
      />
      <Dialog open={traceOpen} onOpenChange={setTraceOpen}>
        <DialogContent side="right" className="border-l">
          <DialogTitle className="sr-only">Tool & Evidence Trace</DialogTitle>
          <ToolTracePanel run={run} />
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
