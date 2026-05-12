import { useEffect, useRef } from "react";

interface Props {
  value: string;
  busy: boolean;
  pendingApproval: boolean;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onHistoryPrev: () => void;
  onHistoryNext: () => void;
  onShortcut: (k: "a" | "r" | "d" | "s") => void;
}

export function Composer({
  value, busy, pendingApproval, onChange, onSubmit, onHistoryPrev, onHistoryNext, onShortcut,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { ref.current?.focus(); }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [value]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
      return;
    }
    if (e.key === "ArrowUp" && (value === "" || (ref.current?.selectionStart ?? 0) === 0)) {
      e.preventDefault();
      onHistoryPrev();
      return;
    }
    if (e.key === "ArrowDown" && (value === "" || (ref.current?.selectionStart ?? 0) === value.length)) {
      e.preventDefault();
      onHistoryNext();
      return;
    }
    if (pendingApproval && value === "") {
      if (e.key === "a") { e.preventDefault(); onShortcut("a"); return; }
      if (e.key === "r") { e.preventDefault(); onShortcut("r"); return; }
      if (e.key === "s") { e.preventDefault(); onShortcut("s"); return; }
      if (e.key === "d") { e.preventDefault(); onShortcut("d"); return; }
    }
  }

  const placeholder = pendingApproval
    ? "Trả lời, hoặc nhấn a/r/s/d cho approval…"
    : busy
    ? "đang trả lời…"
    : "Hỏi bất cứ điều gì, hoặc 'quét s3'…";

  return (
    <div className="px-4 pb-4 pt-2 bg-bg">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 bg-panel border border-border rounded-2xl shadow-soft px-3 py-2 focus-within:border-borderStrong">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder={placeholder}
            className="flex-1 bg-transparent resize-none outline-none placeholder:text-muted py-2 max-h-[200px]"
          />
          <button
            onClick={onSubmit}
            disabled={busy || value.trim() === ""}
            className="shrink-0 w-9 h-9 rounded-full bg-brand text-white grid place-items-center disabled:bg-muted disabled:cursor-not-allowed hover:opacity-90 transition"
            title="Send (Enter)"
            aria-label="Send"
          >
            <span className="text-base leading-none">↑</span>
          </button>
        </div>
        <div className="mt-1.5 px-1 text-[11px] text-dim flex items-center gap-3">
          <span>Enter để gửi · Shift+Enter xuống dòng · ↑/↓ lịch sử</span>
          {pendingApproval && <span className="text-warn">a / r / s · d (approval)</span>}
        </div>
      </div>
    </div>
  );
}
