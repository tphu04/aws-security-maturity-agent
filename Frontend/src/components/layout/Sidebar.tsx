import {
  ShieldCheck, MessageSquarePlus, ListTree, History, FileText,
  Settings as SettingsIcon, Wrench, LifeBuoy, Cloud, ClipboardCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRouter, type ViewName } from "@/state/router";
import { AwsStatusPill } from "@/components/ui/status-pill";
import type { AwsConnectionStatus } from "@/types/pdca";

interface NavItem {
  view: ViewName;
  label: string;
  icon: React.ElementType;
  badge?: string;
}

const PRIMARY: NavItem[] = [
  { view: "workspace", label: "New Scan",     icon: MessageSquarePlus },
  { view: "run_detail", label: "Runs",        icon: ListTree },
  { view: "history",   label: "Scan History", icon: History },
  { view: "report",    label: "Reports",      icon: FileText },
];
const SECONDARY: NavItem[] = [
  { view: "approvals", label: "Approvals",    icon: ClipboardCheck },
  { view: "results",   label: "Results",      icon: Wrench },
  { view: "settings",  label: "AWS Settings", icon: SettingsIcon },
];

export function Sidebar({
  awsStatus, awsAccountMask,
}: { awsStatus: AwsConnectionStatus; awsAccountMask: string }) {
  const { view, go } = useRouter();

  const Item = ({ item }: { item: NavItem }) => {
    const active = view === item.view;
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

      {/* Nav */}
      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4 scrollbar-thin">
        <div>
          <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Workspace</div>
          <div className="space-y-1">{PRIMARY.map((i) => <Item key={i.view + i.label} item={i} />)}</div>
        </div>
        <div>
          <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-wider text-text-muted">Tools</div>
          <div className="space-y-1">{SECONDARY.map((i) => <Item key={i.view + i.label} item={i} />)}</div>
        </div>
      </nav>

      {/* Footer */}
      <div className="space-y-2 border-t border-border/60 p-3">
        <div className="rounded-lg border border-border/60 bg-bg-elevated/40 p-3">
          <div className="flex items-center gap-2">
            <Cloud className="h-3.5 w-3.5 text-primary" />
            <span className="text-[11px] font-medium text-text-primary">AWS</span>
            <AwsStatusPill status={awsStatus} className="ml-auto" />
          </div>
          <div className="mt-1 font-mono text-[11px] text-text-secondary">{awsAccountMask}</div>
        </div>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-text-secondary hover:bg-bg-elevated/60 hover:text-text-primary"
        >
          <LifeBuoy className="h-4 w-4" /> Help & Docs
        </button>
        <div className="flex items-center gap-2 rounded-lg bg-bg-elevated/30 px-3 py-2">
          <div className="grid h-7 w-7 place-items-center rounded-full bg-primary/20 text-[11px] font-semibold text-primary">PT</div>
          <div className="leading-tight">
            <div className="text-xs font-medium text-text-primary">Phú Trần</div>
            <div className="text-[10px] text-text-muted">Demo · local mode</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
