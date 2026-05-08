import { useEffect, useState } from "react";
import { PageShell } from "@/components/layout/PageShell";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AwsStatusPill, Code } from "@/components/ui/status-pill";
import { ShieldCheck, KeyRound, Save, RefreshCw, Trash2, Eye, EyeOff, Info, CheckCircle2, XCircle } from "lucide-react";
import type { RunSession } from "@/types/pdca";
import { loadEndpoints, saveEndpoints, scannerApi, ragApi, chatbotApi } from "@/lib/api";
import { useRun } from "@/state/run";

const REGIONS = ["us-east-1", "us-west-2", "ap-southeast-1", "eu-west-1"];
const SCOPES  = ["Full AWS account", "S3 only", "IAM only", "EC2 only", "Custom services"];

type ProbeState = "idle" | "checking" | "ok" | "error";

export function SettingsView({ run }: { run: RunSession }) {
  const { refreshScannerHealth, refreshEnvironment } = useRun();
  const [show, setShow] = useState(false);
  const [region, setRegion] = useState(run.awsEnvironment.region);
  const [scope, setScope] = useState("S3 only");

  const initial = loadEndpoints();
  const [scannerUrl, setScannerUrl] = useState(initial.scanner);
  const [ragUrl, setRagUrl]         = useState(initial.rag);
  const [chatbotUrl, setChatbotUrl] = useState(initial.chatbot ?? "http://127.0.0.1:9002");
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
      title="AWS Connection Settings"
      subtitle="Configure AWS access before scanning. Use least-privilege or read-only credentials."
      actions={<AwsStatusPill status={run.awsEnvironment.status} />}
    >
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card className="p-6">
          <div className="mb-5 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" />
            <h2 className="text-base font-semibold">Credentials</h2>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Field label="AWS Access Key ID">
              <Input defaultValue="AKIA••••••••8Q2X" className="font-mono" />
            </Field>

            <Field label="AWS Secret Access Key">
              <div className="relative">
                <Input type={show ? "text" : "password"} defaultValue="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" className="pr-10 font-mono" />
                <button type="button" onClick={() => setShow((s) => !s)} className="absolute inset-y-0 right-2 grid place-items-center text-text-muted hover:text-text-primary">
                  {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </Field>

            <Field label="AWS Session Token (optional)" className="md:col-span-2">
              <Textarea placeholder="Paste session token if using temporary credentials…" className="min-h-[80px] rounded-md border border-border bg-bg-elevated/40 p-3 font-mono" />
            </Field>

            <Field label="Default Region">
              <select
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                className="h-10 w-full rounded-md border border-border bg-bg-elevated/40 px-3 text-sm focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/30"
              >
                {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>

            <Field label="Default Scan Scope">
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value)}
                className="h-10 w-full rounded-md border border-border bg-bg-elevated/40 px-3 text-sm focus:outline-none focus:border-primary/60 focus:ring-2 focus:ring-primary/30"
              >
                {SCOPES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>

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

            <Field label="Chatbot API URL" className="md:col-span-2">
              <div className="flex items-center gap-2">
                <Input
                  value={chatbotUrl}
                  onChange={(e) => setChatbotUrl(e.target.value)}
                  className="font-mono"
                  placeholder="http://127.0.0.1:9002 (optional — drives /v1/environment, /v1/runs)"
                />
                <ProbeBadge probe={chatbotProbe} />
              </div>
            </Field>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2 border-t border-border/60 pt-5">
            <Button onClick={persistEndpoints}><Save className="h-4 w-4" /> Save Endpoints</Button>
            <Button variant="outline" onClick={testConnection}>
              <RefreshCw className="h-4 w-4" /> Test Connection
            </Button>
            <Button variant="ghost" className="text-status-error hover:text-status-error">
              <Trash2 className="h-4 w-4" /> Clear Credentials
            </Button>
            {savedAt && (
              <span className="ml-auto text-[11px] text-text-muted">Saved at {savedAt}</span>
            )}
          </div>
        </Card>

        <div className="space-y-4">
          <Card className="p-5">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-status-success" />
              <h3 className="text-sm font-semibold">Security note</h3>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-text-secondary">
              Use least-privilege or read-only credentials for scanning. Remediation actions may require additional permissions and always require user approval through the HITL flow.
            </p>
          </Card>

          <Card className="p-5">
            <h3 className="mb-2 text-sm font-semibold">Connection state</h3>
            <div className="space-y-1.5 text-[11px]">
              <Row k="Status" v={<AwsStatusPill status={run.awsEnvironment.status} />} />
              <Row k="Account" v={<Code>{run.awsEnvironment.accountMask}</Code>} />
              <Row k="Region" v={<Code>{run.awsEnvironment.region}</Code>} />
              <Row k="Type" v={run.awsEnvironment.credentialType} />
              <Row k="Last validated" v={<span className="font-mono">{new Date(run.awsEnvironment.lastValidatedAt).toLocaleString()}</span>} />
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-severity-info" />
              <h3 className="text-sm font-semibold">UI states surfaced</h3>
            </div>
            <ul className="mt-2 space-y-1 text-[11px] text-text-secondary">
              {["not_connected","validating","connected","error","expired_session","missing_permissions"].map((s) => (
                <li key={s} className="flex items-center justify-between">
                  <Code>{s}</Code>
                  <AwsStatusPill status={s as never} />
                </li>
              ))}
            </ul>
          </Card>
        </div>
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
  if (probe.state === "ok")      return <span className={cls + " border-status-success/40 bg-status-success/10 text-status-success"} title="Reachable"><CheckCircle2 className="h-4 w-4" /></span>;
  if (probe.state === "error")   return <span className={cls + " border-status-error/40 bg-status-error/10 text-status-error"} title={probe.reason ?? "Unreachable"}><XCircle className="h-4 w-4" /></span>;
  if (probe.state === "checking")return <span className={cls + " border-border/60 text-text-muted"} title="Checking…"><RefreshCw className="h-4 w-4 animate-spin" /></span>;
  return <span className={cls + " border-border/60 text-text-muted"}><Info className="h-4 w-4" /></span>;
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-text-muted">{k}</span>
      <span className="text-text-primary">{v}</span>
    </div>
  );
}
