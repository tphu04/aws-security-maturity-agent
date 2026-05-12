import {
  ShieldCheck, MessageSquarePlus, History, FileText,
  Settings as SettingsIcon, Wrench, Cloud, Plus,
  Trash2,
} from "lucide-react";
import type React from "react";
import { cn } from "@/lib/utils";
import { useRouter, type ViewName } from "@/state/router";
import { AwsStatusPill } from "@/components/ui/status-pill";
import { useRun } from "@/state/run";
import type { AwsConnectionStatus } from "@/types/pdca";
import type { BackendThreadSummary } from "@/lib/api";

interface NavItem {
  view: ViewName;
  label: string;
  icon: React.ElementType;
}

const NAV: NavItem[] = [
  { view: "workspace", label: "Chat",      icon: MessageSquarePlus },
  { view: "history",   label: "Runs",      icon: History },
  { view: "results",   label: "Results",   icon: Wrench },
  { view: "report",    label: "Reports",   icon: FileText },
  { view: "settings",  label: "Settings",  icon: SettingsIcon },
];

export function Sidebar({
  awsStatus, awsAccountMask,
}: { awsStatus: AwsConnectionStatus; awsAccountMask: string }) {
  const { view, go } = useRouter();
  const {
    createConversation,
    activeThreadId,
    threads,
    threadsLoading,
    loadThread,
    deleteThread,
  } = useRun();

  const startNewChat = () => {
    void createConversation();
    go("workspace");
  };

  const pickThread = (threadId: string) => {
    void loadThread(threadId);
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
      <nav className="space-y-1 px-3 py-4">
        {NAV.map((i) => <Item key={i.view + i.label} item={i} />)}
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto border-t border-border/60 px-3 py-3 scrollbar-thin">
        <div className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
          Chat sessions
        </div>
        {threadsLoading && (
          <div className="px-1 py-2 text-xs text-text-muted">Đang tải…</div>
        )}
        {!threadsLoading && threads.length === 0 && (
          <div className="px-1 py-2 text-xs text-text-muted">Chưa có cuộc trò chuyện.</div>
        )}
        <ThreadGroup
          label="Hôm nay"
          items={groupThreads(threads).today}
          activeId={activeThreadId}
          onPick={pickThread}
          onDelete={deleteThread}
        />
        <ThreadGroup
          label="Tuần này"
          items={groupThreads(threads).week}
          activeId={activeThreadId}
          onPick={pickThread}
          onDelete={deleteThread}
        />
        <ThreadGroup
          label="Trước đó"
          items={groupThreads(threads).older}
          activeId={activeThreadId}
          onPick={pickThread}
          onDelete={deleteThread}
        />
      </div>

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

function groupThreads(threads: BackendThreadSummary[]) {
  const today: BackendThreadSummary[] = [];
  const week: BackendThreadSummary[] = [];
  const older: BackendThreadSummary[] = [];
  const now = Date.now() / 1000;
  for (const thread of threads) {
    const age = now - thread.updated_at;
    if (age < 86_400) today.push(thread);
    else if (age < 86_400 * 7) week.push(thread);
    else older.push(thread);
  }
  return { today, week, older };
}

function relTime(epoch: number): string {
  const delta = Date.now() / 1000 - epoch;
  if (delta < 60) return "vừa xong";
  if (delta < 3_600) return `${Math.floor(delta / 60)} phút`;
  if (delta < 86_400) return `${Math.floor(delta / 3_600)} giờ`;
  if (delta < 86_400 * 7) return `${Math.floor(delta / 86_400)} ngày`;
  return new Date(epoch * 1000).toLocaleDateString("vi-VN");
}

function ThreadGroup({
  label,
  items,
  activeId,
  onPick,
  onDelete,
}: {
  label: string;
  items: BackendThreadSummary[];
  activeId: string | null;
  onPick: (id: string) => void;
  onDelete: (id: string) => Promise<void>;
}) {
  if (!items.length) return null;

  const handleDelete = (event: React.MouseEvent, threadId: string) => {
    event.stopPropagation();
    if (!window.confirm("Xoá cuộc trò chuyện này?")) return;
    void onDelete(threadId);
  };

  return (
    <div className="mt-3 first:mt-0">
      <div className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className="space-y-1">
        {items.map((thread) => {
          const active = thread.thread_id === activeId;
          return (
            <div
              key={thread.thread_id}
              className={cn(
                "group flex items-center gap-1 rounded-lg pr-1 transition-colors",
                active ? "bg-primary/10 ring-1 ring-inset ring-primary/25" : "hover:bg-bg-elevated/60",
              )}
            >
              <button
                type="button"
                onClick={() => onPick(thread.thread_id)}
                className="min-w-0 flex-1 px-2 py-2 text-left"
                title={thread.title}
              >
                <div className={cn("truncate text-xs", active ? "font-medium text-primary" : "text-text-primary")}>
                  {thread.title || "New chat"}
                </div>
                <div className="mt-0.5 flex min-w-0 items-center gap-1 text-[10px] text-text-muted">
                  <span>{relTime(thread.updated_at)}</span>
                  <span>·</span>
                  <span className="truncate">{thread.last_content || `${thread.message_count} messages`}</span>
                </div>
              </button>
              <button
                type="button"
                onClick={(event) => handleDelete(event, thread.thread_id)}
                className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-text-muted opacity-0 transition hover:bg-status-error/10 hover:text-status-error group-hover:opacity-100"
                aria-label="Delete chat"
                title="Xoá"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
