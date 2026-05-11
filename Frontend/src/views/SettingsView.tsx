import { useEffect, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { AwsStatusPill, Code } from "@/components/ui/status-pill";
import {
  ShieldCheck, Save, RefreshCw, Info, CheckCircle2, XCircle, SlidersHorizontal, Globe,
} from "lucide-react";
import type { RunSession } from "@/types/pdca";
import { loadEndpoints, saveEndpoints, scannerApi, ragApi, chatbotApi } from "@/lib/api";
import { useRun } from "@/state/run";
import { FloatingToggles } from "@/components/floating-toggles";

type ProbeState = "idle" | "checking" | "ok" | "error";

export function SettingsView({ run }: { run: RunSession }) {
  const { refreshScannerHealth, refreshEnvironment } = useRun();

  const initial = loadEndpoints();
  const [scannerUrl, setScannerUrl] = useState(initial.scanner);
  const [ragUrl, setRagUrl]         = useState(initial.rag);
  const [chatbotUrl, setChatbotUrl] = useState(initial.chatbot ?? "/api/chatbot");
  const [scannerProbe, setScannerProbe] = useState<{ state: ProbeState; reason?: string }>({ state: "idle" });
  const [ragProbe, setRagProbe]         = useState<{ state: ProbeState; reason?: string }>({ state: "idle" });
  const [chatbotProbe, setChatbotProbe] = useState<{ state: ProbeState; reason?: string }>({ state: "idle" });
  const [savedAt, setSavedAt]           = useState<string | null>(null);

  const persistEndpoints = () => {
    saveEndpoints({
      scanner: scannerUrl.trim(),
      rag: ragUrl.trim(),
      chatbot: chatbotUrl.trim() || undefined,
    });
    setSavedAt(new Date().toLocaleTimeString());
  };

  const testConnection = async () => {
    persistEndpoints();
    setScannerProbe({ state: "checking" });
    setRagProbe({ state: "checking" });
    setChatbotProbe({ state: "checking" });
    const [s, r, c] = await Promise.all([scannerApi.ping(), ragApi.ping(), chatbotApi.ping()]);
    setScannerProbe(s.ok ? { state: "ok" } : { state: "error", reason: s.reason });
    setRagProbe(r.ok ? { state: "ok" } : { state: "error", reason: r.reason });
    setChatbotProbe(c.ok ? { state: "ok" } : { state: "error", reason: c.reason });
    void refreshScannerHealth();
    void refreshEnvironment();
  };

  // Probe once on mount so the UI reflects reality without user action.
  useEffect(() => {
    void testConnection();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <PageShell
      run={run}
      title="Settings"
      subtitle="Endpoints, AWS connection status, and personal preferences."
      actions={<AwsStatusPill status={run.awsEnvironment.status} />}
    >
      <div className="mx-auto grid max-w-3xl gap-5">
        {/* ── Endpoints ────────────────────────────────────────────── */}
        <Card className="p-6">
          <div className="mb-5 flex items-center gap-2">
            <Globe className="h-4 w-4 text-primary" />
            <h2 className="text-base font-semibold">Service endpoints</h2>
          </div>

          <div className="grid gap-4">
            <Field label="Scanner API URL">
              <div className="flex items-center gap-2">
                <Input
                  value={scannerUrl}
                  onChange={(e) => setScannerUrl(e.target.value)}
                  className="font-mono"
                />
                <ProbeBadge probe={scannerProbe} />
              </div>
            </Field>

            <Field label="RAG API URL">
              <div className="flex items-center gap-2">
                <Input
                  value={ragUrl}
                  onChange={(e) => setRagUrl(e.target.value)}
                  className="font-mono"
                />
                <ProbeBadge probe={ragProbe} />
              </div>
            </Field>

            <Field label="Chatbot API URL">
              <div className="flex items-center gap-2">
                <Input
                  value={chatbotUrl}
                  onChange={(e) => setChatbotUrl(e.target.value)}
                  className="font-mono"
                  placeholder="http://127.0.0.1:9002 (drives /v1/environment, /v1/chat, /v1/runs)"
                />
                <ProbeBadge probe={chatbotProbe} />
              </div>
            </Field>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border/60 pt-4">
            <Button onClick={persistEndpoints}><Save className="h-4 w-4" /> Save</Button>
            <Button variant="outline" onClick={testConnection}>
              <RefreshCw className="h-4 w-4" /> Test connection
            </Button>
            {savedAt && (
              <span className="ml-auto text-[11px] text-text-muted">Saved at {savedAt}</span>
            )}
          </div>
        </Card>

        {/* ── AWS connection (read-only) ──────────────────────────── */}
        <Card className="p-6">
          <div className="mb-4 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-status-success" />
            <h2 className="text-base font-semibold">AWS connection</h2>
          </div>
          <p className="mb-3 text-[11px] text-text-muted">
            Credentials are read by the backend from environment variables. This panel reflects
            what the agent currently sees — use least-privilege / read-only IAM for scanning.
          </p>
          <div className="grid grid-cols-1 gap-1.5 text-[12px] sm:grid-cols-2">
            <Row k="Status"        v={<AwsStatusPill status={run.awsEnvironment.status} />} />
            <Row k="Account"       v={<Code>{run.awsEnvironment.accountMask}</Code>} />
            <Row k="Region"        v={<Code>{run.awsEnvironment.region}</Code>} />
            <Row k="Credential"    v={run.awsEnvironment.credentialType} />
            <Row k="Buckets seen"  v={<span className="font-mono">{run.awsEnvironment.bucketsDiscovered}</span>} />
            <Row k="Last validated" v={<span className="font-mono">{new Date(run.awsEnvironment.lastValidatedAt).toLocaleString()}</span>} />
          </div>
        </Card>

        {/* ── Preferences ─────────────────────────────────────────── */}
        <Card className="p-6">
          <div className="mb-3 flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            <h2 className="text-base font-semibold">Preferences</h2>
          </div>
          <p className="mb-3 text-[11px] text-text-muted">
            Language and theme persist in this browser only.
          </p>
          <FloatingToggles variant="inline" />
        </Card>
      </div>
    </PageShell>
  );
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={"block " + (className ?? "")}>
      <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-wider text-text-muted">{label}</span>
      {children}
    </label>
  );
}

function ProbeBadge({ probe }: { probe: { state: ProbeState; reason?: string } }) {
  const cls = "grid h-9 w-9 shrink-0 place-items-center rounded-md border";
  if (probe.state === "ok")       return <span className={cls + " border-status-success/40 bg-status-success/10 text-status-success"} title="Reachable"><CheckCircle2 className="h-4 w-4" /></span>;
  if (probe.state === "error")    return <span className={cls + " border-status-error/40 bg-status-error/10 text-status-error"} title={probe.reason ?? "Unreachable"}><XCircle className="h-4 w-4" /></span>;
  if (probe.state === "checking") return <span className={cls + " border-border/60 text-text-muted"} title="Checking…"><RefreshCw className="h-4 w-4 animate-spin" /></span>;
  return <span className={cls + " border-border/60 text-text-muted"}><Info className="h-4 w-4" /></span>;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-text-muted">{k}</span>
      <span className="text-text-primary">{v}</span>
    </div>
  );
}
