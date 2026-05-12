import React from "react";
import type { BackendThreadSummary } from "../api";

interface Props {
  threads: BackendThreadSummary[];
  activeThreadId: string | null;
  loading: boolean;
  onNew: () => void;
  onPick: (id: string) => void;
  onOpenSettings: () => void;
  onClose: () => void;
  onDelete: (id: string) => Promise<void> | void;
}

function relTime(epoch: number): string {
  const d = Date.now() / 1000 - epoch;
  if (d < 60) return "vừa xong";
  if (d < 3600) return `${Math.floor(d / 60)} phút`;
  if (d < 86400) return `${Math.floor(d / 3600)} giờ`;
  if (d < 86400 * 7) return `${Math.floor(d / 86400)} ngày`;
  return new Date(epoch * 1000).toLocaleDateString("vi-VN");
}

function groupThreads(threads: BackendThreadSummary[]) {
  const today: BackendThreadSummary[] = [];
  const week: BackendThreadSummary[] = [];
  const older: BackendThreadSummary[] = [];
  const now = Date.now() / 1000;
  for (const t of threads) {
    const age = now - t.updated_at;
    if (age < 86400) today.push(t);
    else if (age < 86400 * 7) week.push(t);
    else older.push(t);
  }
  return { today, week, older };
}

export function Sidebar({
  threads, activeThreadId, loading, onNew, onPick, onOpenSettings, onClose, onDelete,
}: Props) {
  const groups = groupThreads(threads);

  return (
    <aside className="w-64 shrink-0 bg-sidebar border-r border-border flex flex-col h-full">
      <div className="p-3 flex items-center gap-2">
        <button
          onClick={onNew}
          className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg bg-panel border border-border hover:bg-elevated shadow-soft text-left text-sm font-medium"
        >
          <span className="text-brand text-base leading-none">+</span>
          <span>New chat</span>
        </button>
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-elevated text-dim"
          title="Hide sidebar"
        >‹</button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {loading && <div className="px-2 py-1 text-xs text-dim">đang tải…</div>}
        {!loading && threads.length === 0 && (
          <div className="px-2 py-3 text-xs text-dim">Chưa có cuộc trò chuyện nào.</div>
        )}
        <Group label="Hôm nay"      items={groups.today}  activeId={activeThreadId} onPick={onPick} onDelete={onDelete} />
        <Group label="Tuần này"     items={groups.week}   activeId={activeThreadId} onPick={onPick} onDelete={onDelete} />
        <Group label="Trước đó"     items={groups.older}  activeId={activeThreadId} onPick={onPick} onDelete={onDelete} />
      </div>

      <div className="border-t border-border p-2 flex items-center gap-1">
        <button
          onClick={onOpenSettings}
          className="flex-1 px-3 py-2 rounded-lg hover:bg-elevated text-left text-sm text-dim flex items-center gap-2"
        >
          <span>⚙</span><span>Settings</span>
        </button>
      </div>
    </aside>
  );
}

function Group({ label, items, activeId, onPick, onDelete }: {
  label: string; items: BackendThreadSummary[]; activeId: string | null;
  onPick: (id: string) => void; onDelete: (id: string) => Promise<void> | void;
}) {
  const [deletingId, setDeletingId] = React.useState<string | null>(null);
  if (items.length === 0) return null;

  async function handleDelete(e: React.MouseEvent, threadId: string) {
    e.stopPropagation();
    if (!confirm("Xoá cuộc trò chuyện này?")) return;
    setDeletingId(threadId);
    try {
      await onDelete(threadId);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="mt-3 first:mt-0">
      <div className="px-2 mb-1 text-[11px] uppercase tracking-wider text-dim font-medium">{label}</div>
      {items.map(t => (
        <div
          key={t.thread_id}
          className={
            "group relative flex items-center gap-1 rounded-lg pr-1 " +
            (t.thread_id === activeId ? "bg-elevated" : "hover:bg-elevated/70")
          }
        >
          <button
            onClick={() => onPick(t.thread_id)}
            className="flex-1 text-left px-2 py-1.5 truncate text-sm"
            title={t.title}
          >
            <span className={t.thread_id === activeId ? "text-fg font-medium" : "text-fg"}>
              {t.title || "(không có tiêu đề)"}
            </span>
          </button>
          <button
            onClick={(e) => handleDelete(e, t.thread_id)}
            disabled={deletingId === t.thread_id}
            className="opacity-0 group-hover:opacity-100 text-dim hover:text-err px-1.5 disabled:opacity-30"
            title="Xoá"
          >{deletingId === t.thread_id ? "…" : "×"}</button>
        </div>
      ))}
    </div>
  );
}
