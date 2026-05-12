import { Menu, PanelRightOpen, PanelRightClose, Download, Settings, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Code } from "@/components/ui/status-pill";
import { useRouter } from "@/state/router";
import type { RunSession } from "@/types/pdca";
import { cn } from "@/lib/utils";

// Human-readable label for each run status. Kept colocated with the dot
// indicator below so the topbar stays self-contained.
const STATUS_LABEL: Record<string, string> = {
  idle: "idle",
  validating_environment: "validating env",
  planning: "planning",
  submitting_scan: "submitting scan",
  polling: "polling",
  collecting_findings: "collecting findings",
  evaluating_risk: "evaluating risk",
  waiting_for_approval: "waiting approval",
  executing_remediation: "remediating",
  verifying: "verifying",
  generating_report: "generating report",
  completed: "completed",
  cancelled: "cancelled",
  failed: "failed",
};

interface Props {
  run: RunSession;
  onOpenTrace?: () => void;
  onOpenNav?: () => void;
  traceOpen?: boolean;
}

// Map the single source-of-truth `RunStatus` to a colored dot. We avoid
// duplicating it with `node`/`report`/AWS pills — those live in the right
// panel where the user can drill down.
const STATUS_DOT: Record<string, string> = {
  idle:                     "bg-text-muted",
  validating_environment:   "bg-severity-info animate-pulse",
  planning:                 "bg-severity-info animate-pulse",
  submitting_scan:          "bg-severity-info animate-pulse",
  polling:                  "bg-severity-info animate-pulse",
  collecting_findings:      "bg-severity-info animate-pulse",
  evaluating_risk:          "bg-severity-info animate-pulse",
  waiting_for_approval:     "bg-status-warning animate-pulse",
  executing_remediation:    "bg-severity-info animate-pulse",
  verifying:                "bg-severity-info animate-pulse",
  generating_report:        "bg-severity-info animate-pulse",
  completed:                "bg-status-success",
  cancelled:                "bg-text-muted",
  failed:                   "bg-status-error",
};

export function TopBar({ run, onOpenTrace, onOpenNav, traceOpen }: Props) {
  const { go } = useRouter();
  const dot = STATUS_DOT[run.status] ?? "bg-text-muted";

  return (
    <header className="relative z-20 flex h-14 items-center justify-between gap-2 border-b border-border/60 bg-bg-base/70 px-3 backdrop-blur-md md:px-5">
      <div className="flex min-w-0 items-center gap-2 md:gap-3">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onOpenNav} aria-label="Open navigation">
          <Menu className="h-5 w-5" />
        </Button>
        <div className="hidden items-center gap-2 md:flex">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span className="font-display text-sm font-semibold tracking-tight">PDCA Prowler Agent</span>
        </div>
        <div className="hidden h-6 w-px bg-border md:block" />
        <div className="hidden min-w-0 items-center gap-2 md:flex">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">run</span>
          <Code className="truncate">{run.id}</Code>
        </div>
      </div>

      {/* Single status indicator. Detail lives in the right panel. */}
      <div className="flex items-center gap-2">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-bg-elevated/40 px-2.5 py-1 text-[11px] text-text-secondary">
          <span className={cn("h-2 w-2 rounded-full shadow-[0_0_6px_currentColor]", dot)} />
          <span className="font-medium">{STATUS_LABEL[run.status] ?? run.status}</span>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        <Button variant="outline" size="sm" className="hidden lg:inline-flex" onClick={() => go("report")}>
          <Download className="h-4 w-4" /> Export
        </Button>
        <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={() => go("settings")} aria-label="Settings">
          <Settings className="h-4 w-4" />
        </Button>
        <Button
          variant={traceOpen ? "secondary" : "outline"}
          size="sm"
          onClick={onOpenTrace}
          aria-label="Toggle trace panel"
          className="gap-1.5"
        >
          {traceOpen
            ? <PanelRightClose className="h-4 w-4" />
            : <PanelRightOpen  className="h-4 w-4" />}
          <span className="hidden sm:inline">Trace</span>
        </Button>
      </div>
    </header>
  );
}
