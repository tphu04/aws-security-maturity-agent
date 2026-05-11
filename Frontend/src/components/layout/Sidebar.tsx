import {
  ShieldCheck, MessageSquarePlus, History, FileText,
  Settings as SettingsIcon, Wrench, Cloud, ClipboardCheck, Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRouter, type ViewName } from "@/state/router";
import { AwsStatusPill } from "@/components/ui/status-pill";
import { useRun } from "@/state/run";
import type { AwsConnectionStatus } from "@/types/pdca";

const THREAD_KEY = "pdca.chat.thread_id";

interface NavItem {
  view: ViewName;
  label: string;
  icon: React.ElementType;
}

// Flat single list — section headers were noise when each section held 2-3
// items. Order roughly follows the user's journey: chat → runs/results
// drill-down → reports → approvals queue → settings.
const NAV: NavItem[] = [
  { view: "workspace", label: "Chat",      icon: MessageSquarePlus },
  { view: "history",   label: "Runs",      icon: History },
  { view: "results",   label: "Results",   icon: Wrench },
  { view: "report",    label: "Reports",   icon: FileText },
  { view: "approvals", label: "Approvals", icon: ClipboardCheck },
  { view: "settings",  label: "Settings",  icon: SettingsIcon },
];

export function Sidebar({
  awsStatus, awsAccountMask,
}: { awsStatus: AwsConnectionStatus; awsAccountMask: string }) {
  const { view, go } = useRouter();
  const { clearMessages } = useRun();

  const startNewChat = () => {
    try { localStorage.removeItem(THREAD_KEY); } catch { /* ignore */ }
    clearMessages();
    go("workspace");
  };

  const Item = ({ item }: { item: NavItem }) => {
    // History entry also lights up when drilled into a single run_detail.
    const active = view === item.view || (item.view === "history" && view === "run_detail");
    const Icon = item.icon;
    return (
      <button
        type="button"
        onClick={() => go(item.view)}
        className={cn(
          "group relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
          active
            ? "bg-primary/10 text-primary ring-1 ring-inset ring-primary/30"
            : "text-text-secondary hover:bg-bg-elevated/60 hover:text-text-primary",
        )}
      >
        <Icon className={cn("h-4 w-4", active ? "text-primary" : "text-text-secondary group-hover:text-text-primary")} />
        <span className="truncate">{item.label}</span>
      </button>
    );
  };

  return (
    <aside className="hidden w-sidebar-width shrink-0 flex-col border-r border-border/60 bg-bg-surface/70 backdrop-blur-md md:flex">
      {/* Brand */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border/60 px-4">
        <div className="relative grid h-8 w-8 place-items-center rounded-md bg-primary/15 ring-1 ring-primary/30">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-primary animate-pulse-soft shadow-[0_0_8px_2px_hsl(var(--primary))]" />
        </div>
        <div className="leading-tight">
          <div className="font-display text-[13px] font-semibold tracking-tight">PDCA Prowler</div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">Agent · v0.1</div>
        </div>
      </div>

      {/* New Chat CTA */}
      <div className="px-3 pt-3">
        <button
          type="button"
          onClick={startNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-primary/40 bg-primary/10 px-3 py-2 text-sm font-medium text-primary transition-colors hover:bg-primary/20 hover:border-primary/60"
        >
          <Plus className="h-4 w-4" /> New chat
        </button>
      </div>

      {/* Nav (flat) */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4 scrollbar-thin">
        {NAV.map((i) => <Item key={i.view + i.label} item={i} />)}
      </nav>

      {/* Footer — only the AWS pill; user card + help-stub removed */}
      <div className="border-t border-border/60 p-3">
        <div className="rounded-lg border border-border/60 bg-bg-elevated/40 p-3">
          <div className="flex items-center gap-2">
            <Cloud className="h-3.5 w-3.5 text-primary" />
            <span className="text-[11px] font-medium text-text-primary">AWS</span>
            <AwsStatusPill status={awsStatus} className="ml-auto" />
          </div>
          <div className="mt-1 font-mono text-[11px] text-text-secondary">{awsAccountMask}</div>
        </div>
      </div>
    </aside>
  );
}
