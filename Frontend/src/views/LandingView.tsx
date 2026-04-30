import {
  ShieldCheck, ArrowRight, Eye, Workflow, Cloud, Send, RefreshCw, Filter,
  Gauge, Wrench, ClipboardCheck, FileText, Sparkles, Terminal, Activity,
  AlertTriangle, BookOpen, Hand, BarChart3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Code, Pill } from "@/components/ui/status-pill";
import { useRouter } from "@/state/router";

export function LandingView() {
  const { go } = useRouter();
  return (
    <div className="relative min-h-screen overflow-y-auto bg-background scrollbar-thin">
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" />

      {/* Top nav */}
      <header className="relative z-20 mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-primary/15 ring-1 ring-primary/30">
            <ShieldCheck className="h-4 w-4 text-primary" />
          </div>
          <div className="font-display text-base font-semibold tracking-tight">PDCA Prowler Agent</div>
        </div>
        <nav className="hidden items-center gap-7 text-sm text-text-secondary md:flex">
          <a href="#features" className="hover:text-text-primary">Features</a>
          <a href="#workflow" className="hover:text-text-primary">Workflow</a>
          <a href="#problem"  className="hover:text-text-primary">Why</a>
        </nav>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => go("settings")}>AWS Settings</Button>
          <Button size="sm" onClick={() => go("workspace")}>Open Workspace <ArrowRight className="h-4 w-4" /></Button>
        </div>
      </header>

      {/* Hero */}
      <section className="relative z-10 mx-auto grid max-w-7xl gap-10 px-6 pb-16 pt-6 lg:grid-cols-2 lg:gap-12 lg:pt-10">
        <div className="flex flex-col justify-center">
          <Pill tone="primary" className="self-start">
            <Sparkles className="h-3 w-3" /> LangGraph · Prowler · DOCX
          </Pill>
          <h1 className="mt-4 font-display text-4xl font-extrabold leading-[1.05] tracking-tight text-text-primary md:text-5xl lg:text-6xl">
            Run AWS security scans through a{" "}
            <span className="text-gradient-cyan">transparent AI agent</span>
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-text-secondary md:text-lg">
            PDCA Prowler Agent lets users request AWS security scans in natural language, runs Prowler through backend APIs, traces every LangGraph step, asks for approval before remediation, verifies changes, and generates a DOCX report.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={() => go("workspace")}>
              Start Scan <ArrowRight className="h-4 w-4" />
            </Button>
            <Button size="lg" variant="outline" onClick={() => go("report")}>
              <Eye className="h-4 w-4" /> Preview Report
            </Button>
          </div>
          <div className="mt-6 flex flex-wrap gap-1.5">
            {["LangGraph workflow", "Prowler scan", "Human approval", "Remediation verification", "DOCX export"].map((t) => (
              <Pill key={t} tone="neutral">{t}</Pill>
            ))}
          </div>
        </div>

        {/* Hero mockup */}
        <div className="relative">
          <div className="absolute -inset-6 rounded-3xl bg-gradient-to-br from-primary/15 via-transparent to-brand-violet/15 blur-2xl" />
          <Card className="relative overflow-hidden border-border/70 bg-card/80">
            <div className="flex items-center justify-between border-b border-border/60 px-4 py-2.5 text-[11px] text-text-muted">
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-status-error/60" />
                <span className="h-2.5 w-2.5 rounded-full bg-status-warning/60" />
                <span className="h-2.5 w-2.5 rounded-full bg-status-success/60" />
              </div>
              <div className="font-mono">workspace · run_2026_0427_s3_001</div>
            </div>
            <div className="grid grid-cols-3">
              <div className="col-span-2 space-y-3 border-r border-border/60 p-4">
                <div className="rounded-lg border border-border/60 bg-bg-elevated/40 p-3">
                  <div className="text-[10px] uppercase tracking-wider text-text-muted">You</div>
                  <p className="mt-1 text-sm text-text-primary">Scan my S3 service for security issues.</p>
                </div>
                <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
                  <div className="flex items-center gap-1.5">
                    <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-primary">Environment checked</span>
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-text-secondary">
                    <span>account <Code>1234••••90</Code></span>
                    <span>region <Code>ap-southeast-1</Code></span>
                    <span>buckets <span className="font-mono text-text-primary">4</span></span>
                    <span>RAG <span className="text-status-success">up</span></span>
                  </div>
                </div>
                <div className="rounded-lg border border-status-warning/30 bg-status-warning/5 p-3">
                  <div className="flex items-center gap-1.5">
                    <Wrench className="h-3.5 w-3.5 text-status-warning" />
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-status-warning">Remediation tool found</span>
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">High-severity public bucket exposure. Remediate?</p>
                  <div className="mt-2 flex gap-1.5">
                    <span className="rounded-md bg-primary px-2 py-0.5 text-[10px] font-medium text-primary-foreground">Yes, remediate</span>
                    <span className="rounded-md border border-border/60 px-2 py-0.5 text-[10px] text-text-secondary">Show details</span>
                  </div>
                </div>
              </div>
              <div className="space-y-3 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">Trace</div>
                {[
                  { i: <Send className="h-3 w-3" />, t: "scan_submit" },
                  { i: <RefreshCw className="h-3 w-3" />, t: "scan_poll ×4" },
                  { i: <Filter className="h-3 w-3" />, t: "scan_collect" },
                  { i: <Gauge className="h-3 w-3" />, t: "risk_evaluation" },
                  { i: <Hand className="h-3 w-3" />, t: "review_task" },
                ].map((n, i) => (
                  <div key={i} className="flex items-center gap-2 rounded border border-border/50 bg-bg-elevated/40 px-2 py-1.5">
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-primary/15 text-primary">{n.i}</span>
                    <span className="font-mono text-[11px] text-text-primary">{n.t}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between border-t border-border/60 bg-bg-elevated/30 px-4 py-2">
              <div className="flex items-center gap-2 text-[10px] text-text-muted">
                <FileText className="h-3 w-3 text-primary" /> pdca-prowler-s3-report.docx · ready
              </div>
              <span className="rounded-md bg-primary/15 px-2 py-0.5 text-[10px] font-medium text-primary">Preview</span>
            </div>
          </Card>
        </div>
      </section>

      {/* Problem */}
      <section id="problem" className="relative z-10 mx-auto max-w-7xl px-6 py-16">
        <div className="mb-8 max-w-3xl">
          <Pill tone="warning"><Terminal className="h-3 w-3" /> The CLI problem</Pill>
          <h2 className="mt-3 font-display text-3xl font-bold tracking-tight md:text-4xl">
            Prowler is powerful, but CLI workflows are hard to explain
          </h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
          {[
            { icon: Terminal,   t: "CLI-heavy scanning",     d: "Users must know commands, flags, groups, checks, profiles, and output formats." },
            { icon: Activity,   t: "Long-running jobs",      d: "Submission, polling, collection, and parsing are not obvious to non-technical users." },
            { icon: AlertTriangle, t: "Raw findings",         d: "Output must be normalized, prioritized, and converted into understandable risks." },
            { icon: ShieldCheck,t: "Controlled remediation", d: "Cloud changes should never happen automatically without explicit user approval." },
            { icon: FileText,   t: "Reports take time",      d: "Findings, evidence, decisions, and verification must be turned into a clean report." },
          ].map((c) => (
            <Card key={c.t} className="p-4">
              <div className="grid h-9 w-9 place-items-center rounded-lg bg-status-warning/10 text-status-warning ring-1 ring-status-warning/30">
                <c.icon className="h-4 w-4" />
              </div>
              <h3 className="mt-3 text-sm font-semibold text-text-primary">{c.t}</h3>
              <p className="mt-1 text-xs leading-relaxed text-text-secondary">{c.d}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* Workflow */}
      <section id="workflow" className="relative z-10 mx-auto max-w-7xl px-6 pb-16">
        <div className="mb-8 max-w-3xl">
          <Pill tone="primary"><Workflow className="h-3 w-3" /> PDCA</Pill>
          <h2 className="mt-3 font-display text-3xl font-bold tracking-tight md:text-4xl">
            A guided PDCA workflow for AWS cloud security
          </h2>
        </div>
        <div className="grid gap-3 md:grid-cols-5">
          {[
            { t: "Plan",   d: "Agent understands user intent and builds a scan plan.",                  icon: Cloud },
            { t: "Do",     d: "Agent submits Prowler jobs and polls until results are ready.",          icon: Send },
            { t: "Check",  d: "Agent evaluates risk and maps evidence to findings.",                    icon: Gauge },
            { t: "Act",    d: "Agent proposes remediation and waits for human approval.",               icon: Hand },
            { t: "Verify & Report", d: "Agent verifies changes and generates a DOCX report.",            icon: FileText },
          ].map((s, i) => (
            <Card key={s.t} className="p-4">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-text-muted">step {i + 1}</span>
                <div className="grid h-7 w-7 place-items-center rounded-md bg-primary/15 text-primary ring-1 ring-primary/30">
                  <s.icon className="h-3.5 w-3.5" />
                </div>
              </div>
              <h3 className="mt-2 font-display text-base font-semibold text-text-primary">{s.t}</h3>
              <p className="mt-1 text-xs leading-relaxed text-text-secondary">{s.d}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="relative z-10 mx-auto max-w-7xl px-6 pb-20">
        <div className="mb-8 max-w-3xl">
          <Pill tone="violet"><Sparkles className="h-3 w-3" /> What's inside</Pill>
          <h2 className="mt-3 font-display text-3xl font-bold tracking-tight md:text-4xl">
            From natural-language requests to verified remediation
          </h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[
            { icon: Sparkles, t: "Natural-language requests", d: "Ask in plain English — \"Scan S3\", \"Check IAM risks\", \"Run a full AWS scan\"." },
            { icon: Cloud,    t: "AWS connection",            d: "Configure access key, secret, optional session token, region, and default scope." },
            { icon: Workflow, t: "LangGraph timeline",        d: "Every node from environment → report is shown with status, duration, and checkpoint." },
            { icon: Send,     t: "Prowler scan jobs",         d: "POST /v1/scan/group + polling /v1/job/{id} surfaced as cards." },
            { icon: BookOpen, t: "Tool registry",             d: "Tools grouped by scanner / knowledge / remediation, with manual-only flag." },
            { icon: Hand,     t: "Human-in-the-loop",         d: "Agent pauses before remediation and waits for explicit approval." },
            { icon: ShieldCheck, t: "Verification",           d: "Re-runs the failing check and shows before/after evidence." },
            { icon: FileText, t: "DOCX preview & export",     d: "Preview and download a polished report with executive summary and appendix." },
          ].map((f) => (
            <Card key={f.t} className="p-4">
              <div className="grid h-9 w-9 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/30">
                <f.icon className="h-4 w-4" />
              </div>
              <h3 className="mt-3 text-sm font-semibold text-text-primary">{f.t}</h3>
              <p className="mt-1 text-xs leading-relaxed text-text-secondary">{f.d}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="relative z-10 mx-auto max-w-7xl px-6 pb-24">
        <Card className="overflow-hidden">
          <div className="grid items-center gap-6 p-8 md:grid-cols-[1fr_auto] md:p-10">
            <div>
              <h3 className="font-display text-2xl font-bold tracking-tight md:text-3xl">
                Open the workspace and walk through a real S3 scan
              </h3>
              <p className="mt-2 max-w-xl text-sm text-text-secondary">
                A full mock run — environment validation, planning, submit, 4 poll iterations, normalize, evaluate, approve, execute, verify, and a DOCX report — is preloaded.
              </p>
            </div>
            <div className="flex flex-wrap gap-3 md:justify-end">
              <Button size="lg" onClick={() => go("workspace")}>
                Open Workspace <ArrowRight className="h-4 w-4" />
              </Button>
              <Button size="lg" variant="outline" onClick={() => go("results")}>
                <BarChart3 className="h-4 w-4" /> Results dashboard
              </Button>
              <Button size="lg" variant="ghost" onClick={() => go("approvals")}>
                <ClipboardCheck className="h-4 w-4" /> Approvals queue
              </Button>
            </div>
          </div>
        </Card>
      </section>

      <footer className="relative z-10 mx-auto max-w-7xl border-t border-border/60 px-6 py-8 text-center text-[11px] text-text-muted">
        © 2026 PDCA Prowler Agent — Thesis demo · Frontend mock-mode · No backend connection
      </footer>
    </div>
  );
}
