import { useState } from "react";
import {
  ShieldCheck, ArrowRight, Sparkles, Search, MessageCircleQuestion, FileText,
  ChevronDown, Workflow, Cloud, ClipboardCheck, Wrench, Activity, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/status-pill";
import { useRouter } from "@/state/router";
import { cn } from "@/lib/utils";

const QUICK_PROMPTS: { label: string; payload: string; icon: "scan" | "qa" }[] = [
  { label: "Scan S3 in my account",      payload: "scan s3",                                icon: "scan" },
  { label: "What is S3 public access?",  payload: "What is S3 public access?",              icon: "qa" },
  { label: "Quét IAM",                    payload: "scan iam",                               icon: "scan" },
  { label: "Best practices cho RDS",     payload: "What are AWS RDS security best practices?", icon: "qa" },
];

const WORKFLOW_STAGES = [
  { icon: Cloud,         label: "Plan",   desc: "Hiểu yêu cầu + lập kế hoạch quét" },
  { icon: Activity,      label: "Do",     desc: "Chạy Prowler, thu thập finding" },
  { icon: ClipboardCheck,label: "Check",  desc: "Đánh giá rủi ro + HITL approve" },
  { icon: Wrench,        label: "Act",    desc: "Remediate + verify + export DOCX" },
];

export function LandingView() {
  const { go } = useRouter();
  const [moreOpen, setMoreOpen] = useState(false);

  const startWith = (payload: string) => {
    // Stash the first prompt so WorkspaceView can pick it up if desired.
    try { sessionStorage.setItem("pdca.initial_prompt", payload); } catch { /* ignore */ }
    go("workspace");
  };

  return (
    <div className="relative min-h-screen overflow-y-auto bg-background scrollbar-thin">
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" />

      {/* Top bar */}
      <header className="relative z-20 mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-primary/15 ring-1 ring-primary/30">
            <ShieldCheck className="h-4 w-4 text-primary" />
          </div>
          <div className="font-display text-base font-semibold tracking-tight">PDCA Prowler Agent</div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setMoreOpen(true)}>How it works</Button>
          <Button variant="ghost" size="sm" onClick={() => go("settings")}>Settings</Button>
          <Button size="sm" onClick={() => go("workspace")}>
            Open chat <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </header>

      {/* Hero */}
      <section className="relative z-10 mx-auto flex max-w-3xl flex-col items-center px-6 pb-12 pt-10 text-center">
        <Pill tone="primary" className="mb-5">
          <Sparkles className="h-3 w-3" /> LangGraph · Prowler · DOCX
        </Pill>
        <h1 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight text-text-primary md:text-5xl">
          AWS security scans qua một{" "}
          <span className="text-gradient-cyan">AI agent minh bạch</span>
        </h1>
        <p className="mt-5 max-w-xl text-base leading-relaxed text-text-secondary md:text-lg">
          Hỏi đáp bảo mật AWS, hoặc yêu cầu quét bằng câu hỏi tự nhiên. Agent dùng Prowler, hiển thị mọi bước reasoning, chờ bạn duyệt trước khi remediate, và xuất báo cáo DOCX.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button size="lg" onClick={() => go("workspace")}>
            Bắt đầu chat <ArrowRight className="h-4 w-4" />
          </Button>
          <Button size="lg" variant="outline" onClick={() => setMoreOpen(true)}>
            How it works
          </Button>
        </div>

        <div className="mt-10 w-full">
          <div className="mb-2 text-[11px] uppercase tracking-wider text-text-muted">Thử nhanh</div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q.label}
                type="button"
                onClick={() => startWith(q.payload)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[12px] text-text-secondary transition-colors",
                  q.icon === "scan"
                    ? "border-primary/40 hover:bg-primary/10 hover:text-primary"
                    : "border-brand-violet/40 hover:bg-brand-violet/10 hover:text-brand-violet",
                )}
              >
                {q.icon === "scan"
                  ? <Search className="h-3.5 w-3.5" />
                  : <MessageCircleQuestion className="h-3.5 w-3.5" />}
                {q.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* How-it-works modal */}
      {moreOpen && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-bg-base/80 px-4 backdrop-blur-sm"
          onClick={() => setMoreOpen(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-2xl rounded-2xl border border-border/70 bg-card/95 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Workflow className="h-4 w-4 text-primary" />
                <h2 className="font-display text-lg font-semibold">How the agent works</h2>
              </div>
              <button
                type="button"
                onClick={() => setMoreOpen(false)}
                className="rounded-md p-1 text-text-muted hover:bg-bg-elevated/60 hover:text-text-primary"
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <p className="text-sm leading-relaxed text-text-secondary">
              Đây là <span className="font-medium text-text-primary">stateful agentic workflow</span> chạy trên LangGraph.
              Mỗi yêu cầu quét được phân loại intent (qa/scan/mixed) rồi đẩy qua 4 giai đoạn PDCA:
            </p>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {WORKFLOW_STAGES.map((s) => (
                <div key={s.label} className="rounded-lg border border-border/60 bg-bg-elevated/30 p-3 text-center">
                  <s.icon className="mx-auto h-4 w-4 text-primary" />
                  <div className="mt-1 text-xs font-semibold uppercase tracking-wider text-text-primary">{s.label}</div>
                  <div className="mt-1 text-[11px] leading-snug text-text-secondary">{s.desc}</div>
                </div>
              ))}
            </div>
            <details className="mt-4 group" open>
              <summary className="flex cursor-pointer items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary">
                <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
                <span>Components</span>
              </summary>
              <ul className="mt-2 space-y-1.5 text-[12px] text-text-secondary">
                <li className="flex items-start gap-2"><Sparkles className="mt-0.5 h-3 w-3 text-primary" /> Intent classifier (Ollama JSON-mode) + rule fast-path</li>
                <li className="flex items-start gap-2"><Sparkles className="mt-0.5 h-3 w-3 text-primary" /> RAG (ChromaDB) chứa Prowler checks + AWS docs</li>
                <li className="flex items-start gap-2"><Sparkles className="mt-0.5 h-3 w-3 text-primary" /> Prowler scanner qua REST API</li>
                <li className="flex items-start gap-2"><Sparkles className="mt-0.5 h-3 w-3 text-primary" /> HITL approval node — agent dừng chờ user duyệt remediation</li>
                <li className="flex items-start gap-2"><FileText className="mt-0.5 h-3 w-3 text-primary" /> Report generation (Markdown + DOCX)</li>
              </ul>
            </details>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setMoreOpen(false)}>Đóng</Button>
              <Button size="sm" onClick={() => { setMoreOpen(false); go("workspace"); }}>
                Bắt đầu <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}

      <footer className="relative z-10 border-t border-border/40 px-6 py-6 text-center text-[11px] text-text-muted">
        Thesis demo · PDCA Prowler Agent · v0.2
      </footer>
    </div>
  );
}
